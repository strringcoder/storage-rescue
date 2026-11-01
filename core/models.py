"""
Modelos de dados tipados do Storage Rescue.
Representam discos físicos, partições, volumes, indicadores SMART e métricas do Dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class HealthStatus(str, Enum):
    """Classificação semântica de saúde e integridade do dispositivo."""

    NORMAL = "Normal"
    WARNING = "Atenção"
    CRITICAL = "Crítico"
    UNKNOWN = "Não disponível"


class SecurityLevel(int, Enum):
    """Níveis de segurança operacional do Storage Rescue."""

    LEVEL_1_DIAGNOSTIC = 1   # Somente leitura (Inventário, SMART, Diagnóstico)
    LEVEL_2_REPAIR = 2       # Reparo lógico não destrutivo (Atribuir letra, Montagem)
    LEVEL_3_PREPARATION = 3  # Formatação e alterações estruturais (8 passos obrigatórios)


def format_bytes(size_bytes: int) -> str:
    """
    Converte um valor em bytes para uma representação legível (KB, MB, GB, TB)
    acompanhada da indicação exata quando necessário.
    """
    if size_bytes <= 0:
        return "0 bytes"
    units = ["bytes", "KB", "MB", "GB", "TB", "PB"]
    value = float(size_bytes)
    unit_index = 0
    while value >= 1024.0 and unit_index < len(units) - 1:
        value /= 1024.0
        unit_index += 1
    if unit_index == 0:
        return f"{int(value)} bytes"
    return f"{value:.2f} {units[unit_index]}"


@dataclass
class VolumeInfo:
    """Representa um volume lógico associado a uma partição."""

    drive_letter: str = ""
    label: str = ""
    file_system: str = "Não Identificado"
    size_bytes: int = 0
    free_bytes: int = 0
    health_status: str = "Desconhecido"
    operational_status: str = "Desconhecido"
    is_raw: bool = False


@dataclass
class PartitionInfo:
    """Representa uma partição física de um disco."""

    disk_number: int
    partition_number: int
    size_bytes: int = 0
    offset_bytes: int = 0
    partition_type: str = "Desconhecido"
    drive_letter: str = ""
    is_boot: bool = False
    is_system: bool = False
    is_active: bool = False
    is_hidden: bool = False
    is_offline: bool = False
    volume: Optional[VolumeInfo] = None


@dataclass
class SmartSummary:
    """Resumo de telemetria SMART e contadores de confiabilidade do dispositivo."""

    supported: bool = False
    source: str = "Não disponível"
    temperature_celsius: Optional[int] = None
    power_on_hours: Optional[int] = None
    reallocated_sectors: Optional[int] = None
    pending_sectors: Optional[int] = None
    uncorrectable_errors: Optional[int] = None
    wear_level_percent: Optional[int] = None
    read_errors_total: Optional[int] = None
    write_errors_total: Optional[int] = None
    status_label: HealthStatus = HealthStatus.UNKNOWN
    summary_text: str = "Informações SMART não disponíveis para este controlador"
    alerts: List[str] = field(default_factory=list)


@dataclass
class DiskDevice:
    """
    Representa um dispositivo físico de armazenamento inventariado pelo Storage Rescue.
    Inclui todos os campos exigidos na Interface Principal e nos módulos de segurança.
    """

    disk_number: int
    manufacturer: str
    model: str
    serial_number: str
    capacity_bytes: int
    connection_type: str          # SATA, NVMe, USB, SD/MMC, SAS, etc.
    file_systems_summary: str     # Ex: "NTFS (C:)", "RAW", "Sem Partição"
    partition_style: str          # GPT, MBR, RAW, Não Inicializado
    operational_status: str       # Online, Offline, No Media, Somente Leitura, Erro E/S
    temperature_celsius: Optional[int] = None
    smart_info: SmartSummary = field(default_factory=SmartSummary)
    health_status: HealthStatus = HealthStatus.UNKNOWN
    health_reason: str = ""

    # Metadados adicionais para segurança, diagnóstico e detalhamento
    device_id: str = ""           # Ex: \\.\PHYSICALDRIVE0
    pnp_device_id: str = ""       # PNPDeviceID do controlador
    media_type: str = "Não especificado"  # SSD, HDD, Removível
    is_removable: bool = False
    is_usb: bool = False
    is_no_media: bool = False
    is_zero_bytes: bool = False
    is_offline: bool = False
    is_read_only: bool = False
    is_uninitialized: bool = False
    has_raw_partition: bool = False
    unallocated_bytes: int = 0

    # Flags de proteção crítica (Nível 3 bloqueado se qualquer flag for True)
    is_system_disk: bool = False
    is_boot_disk: bool = False
    has_pagefile: bool = False
    has_hibernation: bool = False
    protection_reasons: List[str] = field(default_factory=list)

    # Partições associadas
    partitions: List[PartitionInfo] = field(default_factory=list)

    # Identidade única composta (Modelo + Serial + Capacidade)
    composite_identity: str = ""

    @property
    def capacity_formatted(self) -> str:
        """Retorna a capacidade formatada para exibição humana."""
        if self.capacity_bytes <= 0 or self.is_no_media:
            return "0 bytes (Sem Mídia)"
        return f"{format_bytes(self.capacity_bytes)} ({self.capacity_bytes:,} B)".replace(",", ".")

    @property
    def temperature_formatted(self) -> str:
        """Retorna a temperatura formatada em graus Celsius ou indicação de indisponibilidade."""
        if self.temperature_celsius is not None and self.temperature_celsius > 0:
            return f"{self.temperature_celsius} °C"
        return "Não disponível"

    @property
    def smart_formatted(self) -> str:
        """Retorna o resumo legível das informações SMART."""
        if not self.smart_info.supported:
            return "Não suportado / Indisponível"
        return f"{self.smart_info.status_label.value} — {self.smart_info.summary_text}"

    @property
    def is_protected(self) -> bool:
        """Indica se o disco possui qualquer proteção crítica de sistema."""
        return bool(
            self.is_system_disk
            or self.is_boot_disk
            or self.has_pagefile
            or self.has_hibernation
            or self.protection_reasons
        )


@dataclass
class DashboardMetrics:
    """Indicadores consolidados exibidos no topo da tela inicial (Dashboard)."""

    total_disks: int = 0
    connected_summary: str = "0 dispositivos"
    total_capacity_bytes: int = 0
    alert_devices_count: int = 0
    last_diagnostic_timestamp: str = "Nenhum diagnóstico registrado"
    is_simulation_mode: bool = False

    @property
    def total_capacity_formatted(self) -> str:
        """Retorna a soma total de capacidade formatada."""
        return format_bytes(self.total_capacity_bytes)
