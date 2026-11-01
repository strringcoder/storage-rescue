"""
Módulo de Gerenciamento e Inspeção USB (core/usb_manager.py).
Identifica controladores USB, pontes SATA/NVMe-para-USB, dispositivos 'No Media',
capacidades zeradas (0 bytes) e possíveis falhas de comunicação USB.
"""

from __future__ import annotations

from typing import Dict, Tuple

# Assinaturas conhecidas de pontes/adaptadores USB-SATA/NVMe que frequentemente
# aparecem quando o disco conectado ao adaptador está com falha ou sem alimentação
USB_BRIDGE_SIGNATURES: Dict[str, str] = {
    "GENERIC EXTERNAL": "Controlador/Adaptador USB Genérico (Bridge SATA/USB)",
    "ASMT": "Controlador ASMedia USB-SATA Bridge",
    "JMICRON": "Controlador JMicron USB-SATA/NVMe Bridge",
    "JMS578": "Controlador JMicron JMS578 SATA-USB",
    "JMS583": "Controlador JMicron JMS583 NVMe-USB",
    "RTL9210": "Controlador Realtek RTL9210 NVMe/SATA-USB",
    "NORELSYS": "Controlador Norelsys USB Mass Storage",
    "INITIO": "Controlador Initio USB-SATA Bridge",
    "PROLIFIC": "Controlador Prolific USB Storage",
    "VLI": "Controlador VIA Labs USB Bridge",
    "SABRENT": "Adaptador/Case USB Sabrent",
    "ORICO": "Case/Dock USB Orico",
    "UGREEN": "Adaptador/Case USB Ugreen",
}


def normalize_connection_type(
    bus_type: str,
    interface_type: str,
    model: str = "",
    pnp_device_id: str = "",
) -> str:
    """
    Normaliza o tipo de barramento/conexão combinando informações do Storage API (BusType)
    com o WMI (InterfaceType) e o modelo do dispositivo.
    """
    bt = (bus_type or "").strip().upper()
    it = (interface_type or "").strip().upper()
    mdl = (model or "").strip().upper()
    pnp = (pnp_device_id or "").strip().upper()

    # Mapeamento de códigos numéricos de BusType do MSFT_Disk caso retorne inteiro
    bus_type_codes = {
        "1": "SCSI",
        "2": "ATAPI",
        "3": "ATA/IDE",
        "7": "USB",
        "8": "RAID",
        "10": "SAS",
        "11": "SATA",
        "12": "SD/MMC",
        "13": "MMC",
        "17": "NVMe",
    }
    if bt in bus_type_codes:
        bt = bus_type_codes[bt]

    if "NVME" in bt or "NVME" in mdl or "NVME" in pnp:
        if "USB" in bt or "USB" in it or "USBSTOR" in pnp:
            return "USB (Adaptador NVMe)"
        return "NVMe"

    if "USB" in bt or "USB" in it or "USBSTOR" in pnp:
        for sig in USB_BRIDGE_SIGNATURES:
            if sig in mdl:
                return "USB (Adaptador/Bridge Externo)"
        return "USB"

    if "SATA" in bt:
        return "SATA"

    if "SD" in bt or "MMC" in bt:
        return "Cartão SD/MMC"

    if "SAS" in bt:
        return "SAS"

    if "RAID" in bt:
        return "RAID"

    # No Windows, Win32_DiskDrive costuma reportar 'IDE' para unidades SATA AHCI
    if it == "IDE" or bt in ("ATA", "ATA/IDE", "ATAPI"):
        return "SATA"

    if bt and bt not in ("UNKNOWN", "0"):
        return bt

    if it and it not in ("UNKNOWN", ""):
        return it

    return "Não Identificado"


def analyze_usb_health(
    connection_type: str,
    model: str,
    capacity_bytes: int,
    operational_status: str,
    partitions_count: int,
) -> Tuple[bool, bool, str]:
    """
    Analisa sinais típicos de falha de dispositivos USB ou adaptadores SATA/USB.

    Returns:
        Tupla (is_usb, is_no_media, usb_diagnostic_note)
    """
    is_usb = "USB" in (connection_type or "").upper()
    op_upper = (operational_status or "").upper()
    mdl_upper = (model or "").upper()

    is_no_media = (
        "NO MEDIA" in op_upper
        or "SEM MÍDIA" in op_upper
        or capacity_bytes <= 0
    )

    bridge_desc = ""
    for sig, desc in USB_BRIDGE_SIGNATURES.items():
        if sig in mdl_upper:
            bridge_desc = desc
            break

    if is_usb and is_no_media:
        note = (
            "Controlador USB detectado com 0 bytes (No Media). "
            "A ponte USB respondeu, mas a mídia de armazenamento não foi reconhecida."
        )
        return is_usb, True, note

    if is_usb and bridge_desc and partitions_count == 0:
        note = (
            f"{bridge_desc} detectado sem partições válidas montadas. "
            "Verifique se o disco está inicializado ou se há falha de alimentação/comunicação."
        )
        return is_usb, False, note

    return is_usb, is_no_media, bridge_desc
