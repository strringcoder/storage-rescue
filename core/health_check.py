"""
Módulo de Classificação de Saúde do Dispositivo (core/health_check.py).
Avalia o estado global do dispositivo cruzando status operacional, partições,
integridade USB e telemetria SMART.
"""

from __future__ import annotations

from typing import Tuple

from core.models import DiskDevice, HealthStatus


def evaluate_device_health(device: DiskDevice) -> Tuple[HealthStatus, str]:
    """
    Determina a classificação semântica do dispositivo:
    - Crítico (Vermelho): 0 bytes / No Media, falha SMART grave, erro de E/S, Pred Fail.
    - Atenção (Amarelo): Partição RAW, disco não inicializado, sem partições montadas,
      disco offline, somente leitura involuntário ou alerta SMART moderado.
    - Normal (Verde): Online, partições íntegras e sem alertas lógicos ou físicos.
    - Não disponível (Cinza): Estado indeterminado.
    """
    op_upper = (device.operational_status or "").upper()

    # 1. Verificações Críticas (Vermelho)
    if device.is_no_media or device.is_zero_bytes or device.capacity_bytes <= 0:
        return (
            HealthStatus.CRITICAL,
            "Crítico: Mídia não reconhecida (0 bytes / No Media). Possível falha física ou adaptador USB.",
        )

    if device.smart_info.status_label == HealthStatus.CRITICAL:
        return (
            HealthStatus.CRITICAL,
            f"Crítico (SMART): {device.smart_info.summary_text}",
        )

    if any(term in op_upper for term in ("ERROR", "ERRO", "LOST COMMUNICATION", "FAILED", "PRED FAIL")):
        return (
            HealthStatus.CRITICAL,
            f"Crítico: Falha operacional reportada pelo controlador ({device.operational_status}).",
        )

    # 2. Verificações de Atenção (Amarelo)
    warnings = []

    if device.smart_info.status_label == HealthStatus.WARNING:
        warnings.append(device.smart_info.summary_text)

    if device.is_offline or "OFFLINE" in op_upper:
        warnings.append("Disco encontra-se Offline no sistema operacional")

    if device.is_uninitialized or "RAW" in device.partition_style.upper():
        warnings.append("Disco não inicializado ou sem tabela de partições (RAW)")

    if device.has_raw_partition:
        warnings.append("Contém partição em formato RAW (sistema de arquivos ilegível/corrompido)")

    if not device.partitions and not device.is_uninitialized:
        warnings.append("Disco reconhecido mas sem partições alocadas")

    if device.is_read_only:
        warnings.append("Dispositivo em modo Somente Leitura (Proteção contra gravação ativa)")

    # Verifica partições de dados sem letra atribuída (exceto EFI/Sistema/MSR/Recuperação)
    unmounted_data_parts = [
        p
        for p in device.partitions
        if not p.drive_letter
        and not p.is_system
        and not any(
            t in p.partition_type.upper()
            for t in ("SYSTEM", "RESERVED", "RECOVERY", "EFI")
        )
    ]
    if unmounted_data_parts:
        warnings.append(
            f"{len(unmounted_data_parts)} partição(ões) de dados sem letra de unidade atribuída"
        )

    if warnings:
        return HealthStatus.WARNING, "Atenção: " + " | ".join(warnings)

    # 3. Normal (Verde)
    if "OK" in op_upper or "ONLINE" in op_upper:
        if device.smart_info.supported and device.smart_info.status_label == HealthStatus.NORMAL:
            return (
                HealthStatus.NORMAL,
                "Operacional e com telemetria SMART verificada dentro dos parâmetros normais.",
            )
        return (
            HealthStatus.NORMAL,
            "Operacional (Volumes acessíveis; consulte SMART com privilégios de Admin para laudo físico completo).",
        )

    return HealthStatus.UNKNOWN, "Estado de saúde não pôde ser determinado integralmente."
