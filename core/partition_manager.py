"""
Módulo de Gerenciamento e Inspeção de Partições e Volumes (core/partition_manager.py).
Mapeia partições físicas e volumes lógicos em modo somente leitura, identificando
estilos GPT/MBR/RAW, sistemas de arquivos e espaços não alocados.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from core.models import PartitionInfo, VolumeInfo, format_bytes


def normalize_partition_style(raw_style: Any, capacity_bytes: int, is_no_media: bool) -> str:
    """
    Converte o valor de PartitionStyle do Windows (numérico ou string)
    em um rótulo padronizado ('GPT', 'MBR', 'RAW / Não Inicializado', 'Sem Mídia').
    """
    if is_no_media or capacity_bytes <= 0:
        return "Sem Mídia"

    style_map = {
        "0": "RAW (Não Inicializado)",
        "1": "MBR",
        "2": "GPT",
        "RAW": "RAW (Não Inicializado)",
        "MBR": "MBR",
        "GPT": "GPT",
    }
    key = str(raw_style if raw_style is not None else "").strip().upper()
    return style_map.get(key, key if key else "Não Identificado")


def build_partitions_for_disk(
    disk_number: int,
    raw_partitions: List[Dict[str, Any]],
    raw_volumes: List[Dict[str, Any]],
) -> List[PartitionInfo]:
    """
    Constrói a lista de objetos PartitionInfo para um determinado disco,
    associando cada partição ao seu respectivo VolumeInfo quando existente.
    """
    # Indexa volumes por letra de unidade quando disponível
    volumes_by_letter: Dict[str, VolumeInfo] = {}
    for v in raw_volumes:
        letter = str(v.get("DriveLetter") or "").replace(":", "").strip().upper()
        fs = str(v.get("FileSystem") or v.get("FileSystemType") or "").strip()
        if not fs or fs.upper() in ("UNKNOWN", "0", "NONE"):
            fs = "RAW"
        is_raw = fs.upper() == "RAW"
        vol_info = VolumeInfo(
            drive_letter=letter,
            label=str(v.get("FileSystemLabel") or "").strip(),
            file_system=fs,
            size_bytes=int(v.get("Size") or 0),
            free_bytes=int(v.get("SizeRemaining") or 0),
            health_status=str(v.get("HealthStatus") or "OK"),
            operational_status=str(v.get("OperationalStatus") or "OK"),
            is_raw=is_raw,
        )
        if letter:
            volumes_by_letter[letter] = vol_info

    partitions: List[PartitionInfo] = []
    for p in raw_partitions:
        try:
            p_disk = int(p.get("DiskNumber", -1))
        except (ValueError, TypeError):
            continue
        if p_disk != disk_number:
            continue

        part_num = int(p.get("PartitionNumber") or 0)
        size_b = int(p.get("Size") or 0)
        offset_b = int(p.get("Offset") or 0)
        p_type = str(p.get("Type") or "Desconhecido").strip()
        letter = str(p.get("DriveLetter") or "").replace(":", "").strip().upper()

        is_boot = bool(p.get("IsBoot", False))
        is_system = bool(p.get("IsSystem", False))
        is_active = bool(p.get("IsActive", False))
        is_hidden = bool(p.get("IsHidden", False))
        is_offline = bool(p.get("IsOffline", False))

        # Associa volume se tiver letra correspondente
        vol = volumes_by_letter.get(letter)

        # Caso a partição venha enriquecida com FileSystem direto do script PowerShell
        inline_fs = str(p.get("FileSystem") or "").strip()
        if not vol and inline_fs:
            is_raw_fs = inline_fs.upper() == "RAW"
            vol = VolumeInfo(
                drive_letter=letter,
                label=str(p.get("VolumeLabel") or "").strip(),
                file_system=inline_fs,
                size_bytes=size_b,
                free_bytes=int(p.get("FreeSpace") or 0),
                health_status=str(p.get("VolumeHealth") or "OK"),
                operational_status=str(p.get("VolumeStatus") or "OK"),
                is_raw=is_raw_fs,
            )

        partitions.append(
            PartitionInfo(
                disk_number=disk_number,
                partition_number=part_num,
                size_bytes=size_b,
                offset_bytes=offset_b,
                partition_type=p_type,
                drive_letter=letter,
                is_boot=is_boot,
                is_system=is_system,
                is_active=is_active,
                is_hidden=is_hidden,
                is_offline=is_offline,
                volume=vol,
            )
        )

    partitions.sort(key=lambda item: item.partition_number)
    return partitions


def summarize_file_systems(
    partitions: List[PartitionInfo],
    partition_style: str,
    is_no_media: bool,
    wmi_partitions_count: int = 0,
) -> Tuple[str, bool]:
    """
    Gera um resumo claro dos sistemas de arquivos e letras de unidade do disco,
    além de indicar se há alguma partição em estado RAW.

    Returns:
        Tupla (resumo_texto, possui_particao_raw)
    """
    if is_no_media:
        return "Sem Mídia (0 bytes)", False

    if not partitions:
        if "RAW" in partition_style.upper() or "NÃO INICIALIZADO" in partition_style.upper():
            return "Sem Partição (Disco RAW / Não Inicializado)", True
        if wmi_partitions_count > 0:
            return f"{wmi_partitions_count} partição(ões) sem volume montado", False
        return "Sem Partição (100% Não Alocado)", False

    entries: List[str] = []
    has_raw = False

    for part in partitions:
        if part.volume:
            fs = part.volume.file_system or "RAW"
            if part.volume.is_raw or fs.upper() == "RAW":
                has_raw = True
            if part.drive_letter:
                entries.append(f"{fs} ({part.drive_letter}:)")
            else:
                entries.append(f"{fs} (Sem Letra, {format_bytes(part.size_bytes)})")
        else:
            p_type_upper = part.partition_type.upper()
            if "SYSTEM" in p_type_upper or part.is_system:
                entries.append("EFI/Sistema")
            elif "RESERVED" in p_type_upper:
                entries.append("Reservado MSR")
            elif "RECOVERY" in p_type_upper:
                entries.append("Recuperação")
            elif "UNKNOWN" in p_type_upper:
                has_raw = True
                entries.append(f"RAW/Desconhecido ({format_bytes(part.size_bytes)})")
            else:
                if part.drive_letter:
                    entries.append(f"Volume ({part.drive_letter}:)")
                else:
                    entries.append(f"Partição #{part.partition_number} (Sem Letra)")

    # Remove duplicados preservando ordem para resumos limpos
    unique_entries: List[str] = []
    for item in entries:
        if item not in unique_entries:
            unique_entries.append(item)

    return ", ".join(unique_entries), has_raw
