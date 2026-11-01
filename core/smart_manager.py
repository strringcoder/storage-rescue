"""
Módulo de Consulta SMART e Telemetria de Confiabilidade (core/smart_manager.py).
Processa dados de MSFT_StorageReliabilityCounter, Win32_DiskDrive e smartmontools (quando presente).
Respeita a regra: nunca declarar um disco saudável apenas porque o Windows reporta 'Healthy'.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.logger import logger
from core.models import HealthStatus, SmartSummary


def find_smartctl_executable() -> Optional[str]:
    """Localiza o binário do smartctl (smartmontools) no PATH ou nos diretórios padrão do Windows."""
    in_path = shutil.which("smartctl")
    if in_path:
        return in_path

    candidates = [
        r"C:\Program Files\smartmontools\bin\smartctl.exe",
        r"C:\Program Files (x86)\smartmontools\bin\smartctl.exe",
    ]
    for path_str in candidates:
        if Path(path_str).is_file():
            return path_str
    return None


def query_smartctl_json(disk_number: int) -> Optional[Dict[str, Any]]:
    """
    Executa smartctl -a -j /dev/pd<disk_number> em modo somente leitura caso o smartmontools
    esteja instalado no computador do técnico.
    """
    exe = find_smartctl_executable()
    if not exe:
        return None

    try:
        cmd = [exe, "-a", "-j", f"/dev/pd{disk_number}"]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=6,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.stdout:
            return json.loads(proc.stdout)
    except Exception as exc:
        logger.debug("Falha ao consultar smartctl no disco %d: %s", disk_number, exc)
    return None


def _safe_int(val: Any) -> Optional[int]:
    """Converte um valor para inteiro se for válido, ou retorna None."""
    if val is None or val == "":
        return None
    try:
        parsed = int(val)
        return parsed if parsed >= 0 else None
    except (ValueError, TypeError):
        return None


def build_smart_summary(
    disk_number: int,
    raw_reliability: Optional[Dict[str, Any]],
    wmi_status: str,
    win_health_status: str,
    is_usb: bool,
    is_no_media: bool,
    smartctl_data: Optional[Dict[str, Any]] = None,
) -> SmartSummary:
    """
    Constrói o SmartSummary combinando telemetria smartctl, contadores nativos do Windows
    (MSFT_StorageReliabilityCounter) e status de predição de falha.
    """
    if is_no_media:
        return SmartSummary(
            supported=False,
            source="Indisponível (Sem Mídia)",
            status_label=HealthStatus.CRITICAL,
            summary_text="Mídia ausente ou não reconhecida pelo controlador (0 bytes)",
            alerts=["Não é possível ler SMART sem mídia física reconhecida."],
        )

    alerts: List[str] = []
    temp_c: Optional[int] = None
    power_hours: Optional[int] = None
    reallocated: Optional[int] = None
    pending: Optional[int] = None
    uncorrectable: Optional[int] = None
    wear: Optional[int] = None
    read_errors: Optional[int] = None
    write_errors: Optional[int] = None
    source = "Não disponível"
    has_deep_telemetry = False

    # 1. Dados oriundos do smartmontools (quando disponível ou simulado)
    if smartctl_data:
        source = "smartmontools (SMART Direto)"
        has_deep_telemetry = True
        temp_obj = smartctl_data.get("temperature", {})
        if isinstance(temp_obj, dict):
            temp_c = _safe_int(temp_obj.get("current"))
        poh_obj = smartctl_data.get("power_on_time", {})
        if isinstance(poh_obj, dict):
            power_hours = _safe_int(poh_obj.get("hours"))

        # Atributos ATA SMART
        ata_table = smartctl_data.get("ata_smart_attributes", {}).get("table", [])
        for attr in ata_table:
            attr_id = attr.get("id")
            raw_val = _safe_int(attr.get("raw", {}).get("value"))
            if attr_id == 5:
                reallocated = raw_val
            elif attr_id == 197:
                pending = raw_val
            elif attr_id in (187, 198):
                uncorrectable = (uncorrectable or 0) + (raw_val or 0)
            elif attr_id in (177, 231, 233) and raw_val is not None and raw_val <= 100:
                wear = raw_val

        # Log de saúde NVMe
        nvme_log = smartctl_data.get("nvme_smart_health_information_log", {})
        if nvme_log:
            temp_c = temp_c or _safe_int(nvme_log.get("temperature"))
            power_hours = power_hours or _safe_int(nvme_log.get("power_on_hours"))
            wear = wear if wear is not None else _safe_int(nvme_log.get("percentage_used"))
            media_err = _safe_int(nvme_log.get("media_errors"))
            if media_err is not None:
                uncorrectable = media_err

    # 2. Dados oriundos do MSFT_StorageReliabilityCounter
    if raw_reliability and isinstance(raw_reliability, dict):
        r_temp = _safe_int(raw_reliability.get("Temperature"))
        r_poh = _safe_int(raw_reliability.get("PowerOnHours"))
        r_wear = _safe_int(raw_reliability.get("Wear"))
        r_read_uncorr = _safe_int(raw_reliability.get("ReadErrorsUncorrected"))
        r_write_uncorr = _safe_int(raw_reliability.get("WriteErrorsUncorrected"))
        r_read_tot = _safe_int(raw_reliability.get("ReadErrorsTotal"))
        r_write_tot = _safe_int(raw_reliability.get("WriteErrorsTotal"))
        r_realloc = _safe_int(raw_reliability.get("ReallocatedSectors"))
        r_pending = _safe_int(raw_reliability.get("PendingSectors"))

        if any(
            v is not None and v > 0
            for v in (r_temp, r_poh, r_wear, r_read_uncorr, r_write_uncorr, r_realloc, r_pending)
        ) or r_temp is not None:
            has_deep_telemetry = True
            if source == "Não disponível":
                source = "Windows StorageReliabilityCounter (CIM)"

        if temp_c is None and r_temp and r_temp > 0:
            temp_c = r_temp
        if power_hours is None and r_poh is not None:
            power_hours = r_poh
        if wear is None and r_wear is not None:
            wear = r_wear
        if reallocated is None and r_realloc is not None:
            reallocated = r_realloc
        if pending is None and r_pending is not None:
            pending = r_pending
        if r_read_tot is not None:
            read_errors = r_read_tot
        if r_write_tot is not None:
            write_errors = r_write_tot
        if r_read_uncorr is not None or r_write_uncorr is not None:
            uncorrectable = (uncorrectable or 0) + (r_read_uncorr or 0) + (r_write_uncorr or 0)

    # Avaliação rigorosa dos indicadores coletados
    wmi_upper = (wmi_status or "").strip().upper()
    win_upper = (win_health_status or "").strip().upper()

    if "PRED FAIL" in wmi_upper or "ERROR" in wmi_upper or "UNHEALTHY" in win_upper:
        alerts.append("Alerta de falha iminente reportado pelo firmware/SMART (Pred Fail).")

    if reallocated is not None and reallocated > 0:
        alerts.append(f"Setores realocados detectados: {reallocated}.")
    if pending is not None and pending > 0:
        alerts.append(f"Setores pendentes (instáveis) detectados: {pending}.")
    if uncorrectable is not None and uncorrectable > 0:
        alerts.append(f"Erros não corrigíveis de mídia/leitura: {uncorrectable}.")
    if temp_c is not None:
        if temp_c >= 65:
            alerts.append(f"Temperatura crítica: {temp_c} °C (risco térmico elevado).")
        elif temp_c >= 52:
            alerts.append(f"Temperatura elevada: {temp_c} °C (recomenda-se verificar ventilação).")
    if wear is not None and wear >= 85:
        alerts.append(f"Desgaste acentuado de células SSD/NVMe: {wear}% utilizado.")

    # Classificação final (Nunca confia cegamente apenas no 'Healthy' do Windows!)
    if any(
        "falha iminente" in a.lower()
        or "não corrigíveis" in a.lower()
        or "temperatura crítica" in a.lower()
        or (reallocated is not None and reallocated >= 10)
        for a in alerts
    ):
        return SmartSummary(
            supported=True,
            source=source,
            temperature_celsius=temp_c,
            power_on_hours=power_hours,
            reallocated_sectors=reallocated,
            pending_sectors=pending,
            uncorrectable_errors=uncorrectable,
            wear_level_percent=wear,
            read_errors_total=read_errors,
            write_errors_total=write_errors,
            status_label=HealthStatus.CRITICAL,
            summary_text="; ".join(alerts),
            alerts=alerts,
        )

    if alerts or "WARNING" in win_upper or "DEGRADED" in wmi_upper:
        summary_msg = "; ".join(alerts) if alerts else "Alerta reportado pelo subsistema de disco"
        return SmartSummary(
            supported=True,
            source=source,
            temperature_celsius=temp_c,
            power_on_hours=power_hours,
            reallocated_sectors=reallocated,
            pending_sectors=pending,
            uncorrectable_errors=uncorrectable,
            wear_level_percent=wear,
            read_errors_total=read_errors,
            write_errors_total=write_errors,
            status_label=HealthStatus.WARNING,
            summary_text=summary_msg,
            alerts=alerts,
        )

    if has_deep_telemetry:
        details = []
        if temp_c:
            details.append(f"{temp_c} °C")
        if power_hours is not None:
            details.append(f"{power_hours}h uso")
        if reallocated == 0 and pending == 0:
            details.append("0 setores defeituosos")
        detail_str = f" ({', '.join(details)})" if details else ""
        return SmartSummary(
            supported=True,
            source=source,
            temperature_celsius=temp_c,
            power_on_hours=power_hours,
            reallocated_sectors=reallocated,
            pending_sectors=pending,
            uncorrectable_errors=uncorrectable,
            wear_level_percent=wear,
            read_errors_total=read_errors,
            write_errors_total=write_errors,
            status_label=HealthStatus.NORMAL,
            summary_text=f"Atributos SMART verificados sem erros{detail_str}",
            alerts=[],
        )

    # Caso o Windows reporte OK/Healthy, mas os contadores profundos SMART não estejam disponíveis
    # (ex: Ponte USB bloqueando SAT passthrough ou execução sem privilégio de Administrador/smartctl)
    if is_usb:
        reason = "Ponte USB sem repasse SMART completo (Status básico WMI: OK)"
    else:
        reason = "Contadores SMART detalhados requerem smartmontools/Admin (Status básico WMI: OK)"

    return SmartSummary(
        supported=False,
        source="WMI Básico (Sem contadores SMART profundos)",
        temperature_celsius=temp_c,
        status_label=HealthStatus.UNKNOWN,
        summary_text=reason,
        alerts=[],
    )
