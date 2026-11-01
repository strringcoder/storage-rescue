"""
Módulo Gerenciador de Inventário de Discos (core/disk_manager.py).
Realiza a varredura estritamente em MODO SOMENTE LEITURA (Nível 1 de Segurança)
combinando APIs Nativas do Windows (DeviceIoControl: IOCTL_STORAGE_QUERY_PROPERTY e
IOCTL_DISK_GET_DRIVE_GEOMETRY_EX, GetVolumeInformationW) com PowerShell/CIM filtrado
apenas para discos com mídia ativa, evitando travamentos de E/S em adaptadores USB
defeituosos (0 bytes / No Media).
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import struct
import subprocess
import winreg
from typing import Any, Dict, List, Optional, Set, Tuple

from core.device_identity import (
    build_composite_identity,
    normalize_serial,
    resolve_manufacturer,
)
from core.health_check import evaluate_device_health
from core.logger import logger
from core.models import (
    DashboardMetrics,
    DiskDevice,
    HealthStatus,
    PartitionInfo,
    SmartSummary,
    VolumeInfo,
)
from core.partition_manager import (
    build_partitions_for_disk,
    normalize_partition_style,
    summarize_file_systems,
)
from core.smart_manager import build_smart_summary, query_smartctl_json
from core.usb_manager import analyze_usb_health, normalize_connection_type
from security.protections import evaluate_disk_protections, get_system_critical_drive_letters

# Constantes da API Nativa Win32 (Somente Leitura de Metadados)
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
IOCTL_DISK_GET_DRIVE_GEOMETRY_EX = 0x000700A0
IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400


def _read_cstring(buf: bytes, offset: int) -> str:
    """Extrai uma string ASCII terminada em nulo a partir de um buffer binário."""
    if offset <= 0 or offset >= len(buf):
        return ""
    end = buf.find(b"\x00", offset)
    raw_slice = buf[offset : end if end != -1 else len(buf)]
    return raw_slice.decode("ascii", errors="ignore").strip()


def _read_disk_enum_registry() -> Dict[int, str]:
    """
    Lê a chave HKLM\\SYSTEM\\CurrentControlSet\\Services\\disk\\Enum em modo somente leitura
    para obter o PNPDeviceID instantaneamente sem bloquear em chamadas WMI.
    """
    enum_map: Dict[int, str] = {}
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Services\disk\Enum",
            0,
            winreg.KEY_READ,
        ) as key:
            count_val, _ = winreg.QueryValueEx(key, "Count")
            for idx in range(int(count_val)):
                try:
                    pnp_val, _ = winreg.QueryValueEx(key, str(idx))
                    enum_map[idx] = str(pnp_val)
                except OSError:
                    pass
    except OSError as exc:
        logger.debug("Não foi possível ler Services\\disk\\Enum no Registro: %s", exc)
    return enum_map


def query_native_win32_disks(max_drives: int = 24) -> List[Dict[str, Any]]:
    """
    Consulta instantaneamente (< 5ms) os discos físicos \\\\.\\PhysicalDrive0..N usando
    DeviceIoControl (IOCTL_STORAGE_QUERY_PROPERTY e IOCTL_DISK_GET_DRIVE_GEOMETRY_EX)
    sem exigir privilégios de Administrador e sem travar em pontes USB defeituosas (0 bytes).
    """
    if os.name != "nt":
        return []

    k32 = ctypes.windll.kernel32
    k32.CreateFileW.restype = wintypes.HANDLE
    pnp_map = _read_disk_enum_registry()
    candidate_indices = sorted(set(range(max_drives)) | set(pnp_map.keys()))

    native_disks: List[Dict[str, Any]] = []

    for idx in candidate_indices:
        device_path = f"\\\\.\\PhysicalDrive{idx}"
        handle = k32.CreateFileW(
            device_path,
            0,  # FILE_ANY_ACCESS: consulta descritores sem tocar nos setores de dados
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if handle in (-1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF, None):
            continue

        try:
            bytes_returned = wintypes.DWORD(0)

            # 1. Consulta geometria / capacidade real (falha imediatamente se for No Media / 0 bytes)
            geom_buf = ctypes.create_string_buffer(256)
            geom_ok = bool(
                k32.DeviceIoControl(
                    handle,
                    IOCTL_DISK_GET_DRIVE_GEOMETRY_EX,
                    None,
                    0,
                    geom_buf,
                    256,
                    ctypes.byref(bytes_returned),
                    None,
                )
            )
            size_bytes = struct.unpack_from("<q", geom_buf.raw, 24)[0] if geom_ok else 0

            # 2. Consulta descritor de hardware (STORAGE_DEVICE_DESCRIPTOR)
            query = struct.pack("<III", 0, 0, 0)  # StorageDeviceProperty, PropertyStandardQuery
            prop_buf = ctypes.create_string_buffer(1024)
            prop_ok = bool(
                k32.DeviceIoControl(
                    handle,
                    IOCTL_STORAGE_QUERY_PROPERTY,
                    query,
                    len(query),
                    prop_buf,
                    1024,
                    ctypes.byref(bytes_returned),
                    None,
                )
            )

            vendor = ""
            product = ""
            revision = ""
            serial = ""
            bus_type_code = 0
            removable = False

            if prop_ok:
                raw = prop_buf.raw
                (
                    _ver,
                    _sz,
                    _dev_type,
                    _dev_mod,
                    rem_byte,
                    _cmd_q,
                    v_off,
                    p_off,
                    r_off,
                    s_off,
                    bus_type_code,
                ) = struct.unpack_from("<IIBBBBIIIII", raw, 0)
                removable = bool(rem_byte)
                vendor = _read_cstring(raw, v_off)
                product = _read_cstring(raw, p_off)
                revision = _read_cstring(raw, r_off)
                serial = _read_cstring(raw, s_off)

            if vendor and product and not product.upper().startswith(vendor.upper()):
                full_model = f"{vendor} {product}".strip()
            else:
                full_model = (product or vendor or f"Disco Físico {idx}").strip()

            native_disks.append(
                {
                    "Index": idx,
                    "DeviceID": device_path,
                    "PNPDeviceID": pnp_map.get(idx, ""),
                    "Vendor": vendor,
                    "Product": product,
                    "Revision": revision,
                    "Model": full_model,
                    "Manufacturer": vendor,
                    "SerialNumber": serial,
                    "BusType": str(bus_type_code),
                    "Removable": removable,
                    "GeometryOk": geom_ok,
                    "Size": max(0, int(size_bytes)),
                    "Status": "OK" if geom_ok and size_bytes > 0 else "No Media (Sem Mídia)",
                }
            )
        finally:
            k32.CloseHandle(handle)

    return native_disks


def query_native_volume_info(drive_letter: str) -> Optional[Dict[str, Any]]:
    """
    Consulta informações de um volume montado (ex: 'C') via APIs nativas Win32
    GetVolumeInformationW e GetDiskFreeSpaceExW sem bloquear em outros discos.
    """
    if os.name != "nt" or not drive_letter:
        return None

    letter = drive_letter.replace(":", "").replace("\\", "").strip().upper()
    if not letter:
        return None

    root_path = f"{letter}:\\"
    k32 = ctypes.windll.kernel32

    vol_name_buf = ctypes.create_unicode_buffer(261)
    fs_name_buf = ctypes.create_unicode_buffer(261)
    serial_num = wintypes.DWORD(0)
    max_comp_len = wintypes.DWORD(0)
    fs_flags = wintypes.DWORD(0)

    vol_ok = bool(
        k32.GetVolumeInformationW(
            ctypes.c_wchar_p(root_path),
            vol_name_buf,
            260,
            ctypes.byref(serial_num),
            ctypes.byref(max_comp_len),
            ctypes.byref(fs_flags),
            fs_name_buf,
            260,
        )
    )

    free_avail = ctypes.c_ulonglong(0)
    total_bytes = ctypes.c_ulonglong(0)
    total_free = ctypes.c_ulonglong(0)
    space_ok = bool(
        k32.GetDiskFreeSpaceExW(
            ctypes.c_wchar_p(root_path),
            ctypes.byref(free_avail),
            ctypes.byref(total_bytes),
            ctypes.byref(total_free),
        )
    )

    if vol_ok:
        fs_name = fs_name_buf.value or "RAW"
        return {
            "DriveLetter": letter,
            "FileSystemLabel": vol_name_buf.value or "",
            "FileSystem": fs_name,
            "Size": int(total_bytes.value) if space_ok else 0,
            "SizeRemaining": int(total_free.value) if space_ok else 0,
            "HealthStatus": "Healthy",
            "OperationalStatus": "OK",
        }

    # Se a letra existe no sistema mas GetVolumeInformationW falhou, frequentemente é partição RAW
    if os.path.exists(root_path) or k32.GetDriveTypeW(ctypes.c_wchar_p(root_path)) > 1:
        return {
            "DriveLetter": letter,
            "FileSystemLabel": "",
            "FileSystem": "RAW",
            "Size": 0,
            "SizeRemaining": 0,
            "HealthStatus": "Warning",
            "OperationalStatus": "RAW / Ilegível",
        }

    return None


class DiskManager:
    """
    Gerenciador principal de inventário de dispositivos de armazenamento.
    Opera exclusivamente em Nível 1 (Somente Leitura) durante a coleta.
    """

    def __init__(self, use_smartctl: bool = True) -> None:
        self.use_smartctl = use_smartctl

    def collect_inventory(self, simulation_mode: bool = False) -> List[DiskDevice]:
        """
        Coleta a lista completa de dispositivos de armazenamento conectados ao sistema
        (ou retorna os dispositivos de simulação de bancada se simulation_mode=True).
        """
        if simulation_mode:
            logger.info("Carregando inventário em Modo Simulação de Bancada (Somente Leitura).")
            return self.get_simulated_inventory()

        logger.info("Iniciando varredura somente leitura via API Nativa Win32 + PowerShell/CIM...")
        native_disks = query_native_win32_disks()
        healthy_indices = [
            int(d["Index"])
            for d in native_disks
            if d.get("GeometryOk") and int(d.get("Size") or 0) > 0
        ]

        raw_payload = self._run_filtered_powershell(healthy_indices, native_disks)
        devices = self.parse_inventory_payload(raw_payload, check_smartctl=self.use_smartctl)
        logger.info("Inventário concluído: %d dispositivo(s) identificado(s).", len(devices))
        return devices

    def _run_filtered_powershell(
        self,
        healthy_indices: List[int],
        native_disks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Executa consulta PowerShell filtrada APENAS para os discos com mídia ativa,
        impedindo que o subsistema MSFT_Disk trave em dispositivos USB '0 bytes / No Media'.
        """
        msft_disks: List[Dict[str, Any]] = []
        partitions: List[Dict[str, Any]] = []
        volumes: List[Dict[str, Any]] = []
        reliability: Dict[str, Any] = {}

        if healthy_indices:
            nums_csv = ",".join(str(i) for i in healthy_indices)
            ps_script = f"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'SilentlyContinue'
$msftDisks = @(Get-Disk -Number {nums_csv} | Select-Object Number, FriendlyName, SerialNumber, Manufacturer, Model, BusType, PartitionStyle, OperationalStatus, HealthStatus, Size, AllocatedSize, IsBoot, IsSystem, IsOffline, IsReadOnly)
$partitions = @(Get-Partition -DiskNumber {nums_csv} | Select-Object DiskNumber, PartitionNumber, DriveLetter, Size, Offset, Type, IsBoot, IsSystem, IsActive, IsHidden, IsOffline)
$result = @{{
    MsftDisks = $msftDisks
    Partitions = $partitions
}}
$result | ConvertTo-Json -Depth 4 -Compress
"""
            try:
                cmd = [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    ps_script,
                ]
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=12,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                stdout = (proc.stdout or "").strip()
                if stdout:
                    json_start = stdout.find("{")
                    if json_start >= 0:
                        parsed = json.loads(stdout[json_start:])
                        msft_disks = self._ensure_list(parsed.get("MsftDisks"))
                        partitions = self._ensure_list(parsed.get("Partitions"))
            except Exception as exc:
                logger.warning("Aviso na consulta complementar PowerShell: %s", exc)

        # Coleta instantânea de volumes via API nativa Win32 para todas as letras das partições
        seen_letters: Set[str] = set()
        for part in partitions:
            dl = str(part.get("DriveLetter") or "").strip().upper()
            if dl and len(dl) == 1 and dl.isalpha() and dl not in seen_letters:
                seen_letters.add(dl)
                vol_data = query_native_volume_info(dl)
                if vol_data:
                    volumes.append(vol_data)

        return {
            "WmiDisks": native_disks,
            "MsftDisks": msft_disks,
            "PhysicalDisks": [],
            "Partitions": partitions,
            "Volumes": volumes,
            "Pagefiles": [],
            "Reliability": reliability,
        }

    def parse_inventory_payload(
        self,
        payload: Dict[str, Any],
        check_smartctl: bool = False,
    ) -> List[DiskDevice]:
        """
        Converte o dicionário JSON de inventário em uma lista ordenada de objetos DiskDevice
        enriquecidos com partições, volumes, SMART e proteções.
        """
        wmi_disks = self._ensure_list(payload.get("WmiDisks"))
        msft_disks = self._ensure_list(payload.get("MsftDisks"))
        phys_disks = self._ensure_list(payload.get("PhysicalDisks"))
        raw_partitions = self._ensure_list(payload.get("Partitions"))
        raw_volumes = self._ensure_list(payload.get("Volumes"))
        raw_pagefiles = self._ensure_list(payload.get("Pagefiles"))
        reliability_map: Dict[str, Any] = payload.get("Reliability") or {}

        wmi_by_num: Dict[int, Dict[str, Any]] = {}
        for wd in wmi_disks:
            if wd and wd.get("Index") is not None:
                wmi_by_num[int(wd["Index"])] = wd

        msft_by_num: Dict[int, Dict[str, Any]] = {}
        for md in msft_disks:
            if md and md.get("Number") is not None:
                msft_by_num[int(md["Number"])] = md

        phys_by_num: Dict[int, Dict[str, Any]] = {}
        for pd in phys_disks:
            if pd and pd.get("DeviceId") is not None:
                try:
                    phys_by_num[int(pd["DeviceId"])] = pd
                except (ValueError, TypeError):
                    pass

        pagefile_letters: Set[str] = set()
        for pf in raw_pagefiles:
            name = str((pf or {}).get("Name") or "")
            if len(name) >= 2 and name[1] == ":":
                pagefile_letters.add(name[0].upper())
        pagefile_letters |= get_system_critical_drive_letters()

        all_disk_numbers = sorted(set(wmi_by_num.keys()) | set(msft_by_num.keys()))
        devices: List[DiskDevice] = []

        for disk_num in all_disk_numbers:
            wmi = wmi_by_num.get(disk_num, {})
            msft = msft_by_num.get(disk_num, {})
            phys = phys_by_num.get(disk_num, {})
            rel_data = reliability_map.get(str(disk_num)) if isinstance(reliability_map, dict) else None

            raw_model = str(
                msft.get("FriendlyName")
                or msft.get("Model")
                or wmi.get("Model")
                or phys.get("FriendlyName")
                or f"Disco Físico {disk_num}"
            ).strip()
            raw_mfg = str(msft.get("Manufacturer") or wmi.get("Manufacturer") or "").strip()
            pnp_id = str(wmi.get("PNPDeviceID") or "").strip()
            manufacturer = resolve_manufacturer(raw_mfg, raw_model, pnp_id)

            raw_serial = (
                msft.get("SerialNumber")
                or wmi.get("SerialNumber")
                or phys.get("SerialNumber")
                or ""
            )
            serial_number = normalize_serial(str(raw_serial))

            # Se GeometryOk veio explicitamente False da API nativa Win32, a capacidade real é 0 bytes!
            geom_ok = wmi.get("GeometryOk", True)
            cap_msft = int(msft.get("Size") or 0)
            cap_wmi = int(wmi.get("Size") or 0)
            if geom_ok is False:
                capacity_bytes = 0
            else:
                capacity_bytes = cap_msft if cap_msft > 0 else cap_wmi

            allocated_bytes = int(msft.get("AllocatedSize") or 0)
            unallocated_bytes = (
                max(0, capacity_bytes - allocated_bytes) if allocated_bytes > 0 else 0
            )

            bus_type = str(msft.get("BusType") or wmi.get("BusType") or phys.get("BusType") or "")
            interface_type = str(wmi.get("InterfaceType") or "")
            connection_type = normalize_connection_type(bus_type, interface_type, raw_model, pnp_id)

            op_status_raw = (
                msft.get("OperationalStatus")
                or phys.get("OperationalStatus")
                or wmi.get("Status")
                or "Desconhecido"
            )
            if isinstance(op_status_raw, list):
                op_status = ", ".join(str(x) for x in op_status_raw)
            else:
                op_status = str(op_status_raw).strip()

            wmi_parts_count = int(wmi.get("Partitions") or 0)
            if not msft and wmi:
                if capacity_bytes <= 0 or geom_ok is False:
                    op_status = "No Media (Sem Mídia)"
                elif wmi_parts_count == 0 and "NO MEDIA" not in op_status.upper():
                    op_status = "Alerta de Montagem (Sem Tabela no Storage API)"

            is_offline = bool(msft.get("IsOffline", False)) or ("OFFLINE" in op_status.upper())
            is_read_only = bool(msft.get("IsReadOnly", False))

            is_usb, is_no_media, _ = analyze_usb_health(
                connection_type=connection_type,
                model=raw_model,
                capacity_bytes=capacity_bytes,
                operational_status=op_status,
                partitions_count=wmi_parts_count,
            )
            is_zero_bytes = capacity_bytes <= 0

            raw_part_style = msft.get("PartitionStyle")
            if raw_part_style is None and not msft and wmi_parts_count == 0:
                raw_part_style = "RAW"
            partition_style = normalize_partition_style(raw_part_style, capacity_bytes, is_no_media)
            is_uninitialized = (
                "RAW" in partition_style.upper() or "NÃO INICIALIZADO" in partition_style.upper()
            )

            partitions: List[PartitionInfo] = build_partitions_for_disk(
                disk_number=disk_num,
                raw_partitions=raw_partitions,
                raw_volumes=raw_volumes,
            )

            fs_summary, has_raw_part = summarize_file_systems(
                partitions=partitions,
                partition_style=partition_style,
                is_no_media=is_no_media,
                wmi_partitions_count=wmi_parts_count,
            )

            smartctl_json = (
                query_smartctl_json(disk_num) if (check_smartctl and not is_no_media) else None
            )
            wmi_status = str(wmi.get("Status") or "OK")
            win_health = str(msft.get("HealthStatus") or phys.get("HealthStatus") or "Unknown")

            if not rel_data and phys.get("Temperature"):
                rel_data = {"Temperature": phys.get("Temperature")}

            smart_summary = build_smart_summary(
                disk_number=disk_num,
                raw_reliability=rel_data,
                wmi_status=wmi_status,
                win_health_status=win_health,
                is_usb=is_usb,
                is_no_media=is_no_media,
                smartctl_data=smartctl_json,
            )

            media_type_raw = str(
                phys.get("MediaType")
                or wmi.get("MediaType")
                or ("USB Removível/Externo" if is_usb else "Unidade Fixa")
            )
            is_removable = (
                bool(wmi.get("Removable", False))
                or "REMOVABLE" in media_type_raw.upper()
                or "EXTERNAL" in media_type_raw.upper()
                or is_usb
            )

            device = DiskDevice(
                disk_number=disk_num,
                manufacturer=manufacturer,
                model=raw_model,
                serial_number=serial_number,
                capacity_bytes=capacity_bytes,
                connection_type=connection_type,
                file_systems_summary=fs_summary,
                partition_style=partition_style,
                operational_status=op_status,
                temperature_celsius=smart_summary.temperature_celsius,
                smart_info=smart_summary,
                device_id=str(wmi.get("DeviceID") or f"\\\\.\\PHYSICALDRIVE{disk_num}"),
                pnp_device_id=pnp_id,
                media_type=media_type_raw,
                is_removable=is_removable,
                is_usb=is_usb,
                is_no_media=is_no_media,
                is_zero_bytes=is_zero_bytes,
                is_offline=is_offline,
                is_read_only=is_read_only,
                is_uninitialized=is_uninitialized,
                has_raw_partition=has_raw_part,
                unallocated_bytes=unallocated_bytes,
                is_boot_disk=bool(msft.get("IsBoot", False)),
                is_system_disk=bool(msft.get("IsSystem", False)),
                partitions=partitions,
                composite_identity=build_composite_identity(
                    raw_model, serial_number, capacity_bytes
                ),
            )

            evaluate_disk_protections(device, pagefile_letters=pagefile_letters)
            health_status, health_reason = evaluate_device_health(device)
            device.health_status = health_status
            device.health_reason = health_reason

            devices.append(device)

        return devices

    @staticmethod
    def _ensure_list(val: Any) -> List[Dict[str, Any]]:
        """Garante que o item retornado pelo ConvertTo-Json seja sempre uma lista de dicionários."""
        if val is None:
            return []
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]
        if isinstance(val, dict):
            return [val]
        return []

    @staticmethod
    def compute_dashboard_metrics(
        devices: List[DiskDevice],
        last_diagnostic_time: Optional[str] = None,
        is_simulation: bool = False,
    ) -> DashboardMetrics:
        """
        Calcula os 5 indicadores principais da tela inicial (Dashboard) a partir
        da lista de dispositivos inventariados.
        """
        total_disks = len(devices)
        internal_count = sum(1 for d in devices if not d.is_usb and not d.is_removable)
        external_count = sum(1 for d in devices if d.is_usb or d.is_removable)
        total_cap = sum(max(0, d.capacity_bytes) for d in devices)
        alerts_count = sum(
            1
            for d in devices
            if d.health_status in (HealthStatus.WARNING, HealthStatus.CRITICAL)
        )

        connected_text = f"{internal_count} Interno(s) • {external_count} USB/Externo(s)"
        if total_disks == 0:
            connected_text = "Nenhum dispositivo detectado"

        return DashboardMetrics(
            total_disks=total_disks,
            connected_summary=connected_text,
            total_capacity_bytes=total_cap,
            alert_devices_count=alerts_count,
            last_diagnostic_timestamp=last_diagnostic_time or "Varredura inicial concluída",
            is_simulation_mode=is_simulation,
        )

    @staticmethod
    def get_simulated_inventory() -> List[DiskDevice]:
        """
        Retorna um conjunto completo de dispositivos simulados para testes seguros de bancada,
        cobrindo todos os estados visuais (Verde/Normal, Amarelo/Atenção, Vermelho/Crítico, Cinza)
        sem tocar nos discos reais do computador.
        """
        # 1. Disco 0: SSD NVMe do Sistema (Normal / Verde / Protegido)
        d0_parts = [
            PartitionInfo(
                disk_number=0,
                partition_number=1,
                size_bytes=100 * 1024 * 1024,
                partition_type="System",
                is_system=True,
            ),
            PartitionInfo(
                disk_number=0,
                partition_number=2,
                size_bytes=511_900_000_000,
                partition_type="Basic",
                drive_letter="C",
                is_boot=True,
                volume=VolumeInfo(
                    drive_letter="C",
                    label="Windows 11 Pro",
                    file_system="NTFS",
                    size_bytes=511_900_000_000,
                    free_bytes=284_500_000_000,
                    health_status="Healthy",
                    operational_status="OK",
                ),
            ),
        ]
        d0_smart = SmartSummary(
            supported=True,
            source="Simulação NVMe SMART",
            temperature_celsius=38,
            power_on_hours=4120,
            reallocated_sectors=0,
            pending_sectors=0,
            uncorrectable_errors=0,
            wear_level_percent=4,
            status_label=HealthStatus.NORMAL,
            summary_text="Atributos SMART verificados sem erros (38 °C, 4120h uso, Desgaste 4%)",
        )
        d0 = DiskDevice(
            disk_number=0,
            manufacturer="Samsung Electronics",
            model="Samsung SSD 980 PRO 500GB",
            serial_number="S5GXNF0R918234A",
            capacity_bytes=512_110_190_592,
            connection_type="NVMe",
            file_systems_summary="EFI/Sistema, NTFS (C:)",
            partition_style="GPT",
            operational_status="Online",
            temperature_celsius=38,
            smart_info=d0_smart,
            health_status=HealthStatus.NORMAL,
            health_reason="Operacional e com telemetria SMART verificada dentro dos parâmetros normais.",
            device_id=r"\\.\PHYSICALDRIVE0",
            media_type="SSD NVMe",
            is_system_disk=True,
            is_boot_disk=True,
            has_pagefile=True,
            protection_reasons=[
                "Disco de Inicialização (Boot)",
                "Disco do Sistema Operacional (Windows)",
                "Contém Arquivo de Paginação (pagefile.sys)",
            ],
            partitions=d0_parts,
            composite_identity=build_composite_identity(
                "Samsung SSD 980 PRO 500GB", "S5GXNF0R918234A", 512_110_190_592
            ),
        )

        # 2. Disco 1: HD SATA Secundário com Partição RAW e Setores Pendentes (Atenção / Amarelo)
        d1_parts = [
            PartitionInfo(
                disk_number=1,
                partition_number=1,
                size_bytes=1_000_204_886_016,
                partition_type="Basic",
                drive_letter="E",
                volume=VolumeInfo(
                    drive_letter="E",
                    label="",
                    file_system="RAW",
                    size_bytes=1_000_204_886_016,
                    free_bytes=0,
                    health_status="Warning",
                    operational_status="OK",
                    is_raw=True,
                ),
            )
        ]
        d1_smart = SmartSummary(
            supported=True,
            source="Simulação SATA SMART",
            temperature_celsius=46,
            power_on_hours=18940,
            reallocated_sectors=4,
            pending_sectors=2,
            uncorrectable_errors=0,
            status_label=HealthStatus.WARNING,
            summary_text="Setores realocados detectados: 4; Setores pendentes (instáveis) detectados: 2.",
            alerts=[
                "Setores realocados detectados: 4.",
                "Setores pendentes (instáveis) detectados: 2.",
            ],
        )
        d1 = DiskDevice(
            disk_number=1,
            manufacturer="Seagate Technology",
            model="ST1000DM010-2EP102",
            serial_number="ZN18K4LP",
            capacity_bytes=1_000_204_886_016,
            connection_type="SATA",
            file_systems_summary="RAW (E:)",
            partition_style="GPT",
            operational_status="Online",
            temperature_celsius=46,
            smart_info=d1_smart,
            health_status=HealthStatus.WARNING,
            health_reason=(
                "Atenção: Setores realocados detectados: 4; Setores pendentes (instáveis) detectados: 2. "
                "| Contém partição em formato RAW (sistema de arquivos ilegível/corrompido)"
            ),
            device_id=r"\\.\PHYSICALDRIVE1",
            media_type="HDD SATA",
            has_raw_partition=True,
            partitions=d1_parts,
            composite_identity=build_composite_identity(
                "ST1000DM010-2EP102", "ZN18K4LP", 1_000_204_886_016
            ),
        )

        # 3. Disco 2: Dispositivo USB com 0 bytes / No Media (Crítico / Vermelho)
        d2_smart = SmartSummary(
            supported=False,
            source="Indisponível (Sem Mídia)",
            status_label=HealthStatus.CRITICAL,
            summary_text="Mídia ausente ou não reconhecida pelo controlador (0 bytes)",
            alerts=["O controlador USB foi identificado, mas não foi possível reconhecer a mídia."],
        )
        d2 = DiskDevice(
            disk_number=2,
            manufacturer="Genérico (Controlador USB)",
            model="Generic External",
            serial_number="190610101002888",
            capacity_bytes=0,
            connection_type="USB (Adaptador/Bridge Externo)",
            file_systems_summary="Sem Mídia (0 bytes)",
            partition_style="Sem Mídia",
            operational_status="No Media (Sem Mídia)",
            temperature_celsius=None,
            smart_info=d2_smart,
            health_status=HealthStatus.CRITICAL,
            health_reason=(
                "Crítico: Mídia não reconhecida (0 bytes / No Media). "
                "Possível falha no adaptador SATA/USB, mau contato, alimentação ou defeito eletrônico no SSD."
            ),
            device_id=r"\\.\PHYSICALDRIVE2",
            media_type="USB External Bridge",
            is_removable=True,
            is_usb=True,
            is_no_media=True,
            is_zero_bytes=True,
            partitions=[],
            composite_identity=build_composite_identity("Generic External", "190610101002888", 0),
        )

        # 4. Disco 3: Pendrive USB Kingston com Partição Sem Letra de Unidade (Atenção / Amarelo)
        d3_parts = [
            PartitionInfo(
                disk_number=3,
                partition_number=1,
                size_bytes=64_000_000_000,
                partition_type="Basic",
                drive_letter="",
                volume=VolumeInfo(
                    drive_letter="",
                    label="BACKUP_TECNICO",
                    file_system="exFAT",
                    size_bytes=64_000_000_000,
                    free_bytes=19_200_000_000,
                    health_status="Healthy",
                    operational_status="OK",
                ),
            )
        ]
        d3_smart = SmartSummary(
            supported=False,
            source="Controlador USB Mass Storage",
            status_label=HealthStatus.UNKNOWN,
            summary_text="Controlador USB Flash não suporta comandos SMART ATA/NVMe",
        )
        d3 = DiskDevice(
            disk_number=3,
            manufacturer="Kingston Technology",
            model="Kingston DataTraveler 3.0",
            serial_number="001A4D5F92C1B870",
            capacity_bytes=64_021_856_256,
            connection_type="USB",
            file_systems_summary="exFAT (Sem Letra, 59.60 GB)",
            partition_style="MBR",
            operational_status="Online",
            temperature_celsius=None,
            smart_info=d3_smart,
            health_status=HealthStatus.WARNING,
            health_reason="Atenção: 1 partição(ões) de dados sem letra de unidade atribuída",
            device_id=r"\\.\PHYSICALDRIVE3",
            media_type="Pendrive USB",
            is_removable=True,
            is_usb=True,
            partitions=d3_parts,
            composite_identity=build_composite_identity(
                "Kingston DataTraveler 3.0", "001A4D5F92C1B870", 64_021_856_256
            ),
        )

        return [d0, d1, d2, d3]
