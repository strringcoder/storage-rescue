"""
Módulo de Identidade de Dispositivos (device_identity.py).
Garante que nenhum disco seja identificado apenas pelo seu número (DiskNumber),
que pode mudar após reconexões USB, utilizando uma chave composta (Modelo + Serial + Capacidade).
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict

from core.models import DiskDevice

# Mapa de prefixos e nomes conhecidos para inferência de fabricante quando o WMI/CIM
# retorna "(Unidades de disco padrão)" ou "(Standard disk drives)"
KNOWN_VENDORS: Dict[str, str] = {
    "KINGSTON": "Kingston Technology",
    "SANDISK": "SanDisk (Western Digital)",
    "WDC": "Western Digital",
    "WD ": "Western Digital",
    "WESTERN DIGITAL": "Western Digital",
    "SEAGATE": "Seagate Technology",
    "ST1": "Seagate Technology",
    "ST2": "Seagate Technology",
    "ST3": "Seagate Technology",
    "ST4": "Seagate Technology",
    "ST5": "Seagate Technology",
    "SAMSUNG": "Samsung Electronics",
    "CRUCIAL": "Crucial (Micron)",
    "CT2": "Crucial (Micron)",
    "CT5": "Crucial (Micron)",
    "CT1": "Crucial (Micron)",
    "MICRON": "Micron Technology",
    "ADATA": "ADATA Technology",
    "PATRIOT": "Patriot Memory",
    "CORSAIR": "Corsair",
    "TOSHIBA": "Toshiba / Kioxia",
    "KIOXIA": "Kioxia",
    "HITACHI": "HGST / Hitachi",
    "HGST": "HGST (Western Digital)",
    "LEXAR": "Lexar",
    "MULTILASER": "Multilaser",
    "INTEL": "Intel Corporation",
    "SK HYNIX": "SK hynix",
    "HYNIX": "SK hynix",
    "NVME": "Controlador NVMe Padrão",
    "GENERIC": "Genérico (Controlador USB)",
}


def resolve_manufacturer(raw_manufacturer: str, model: str, pnp_device_id: str = "") -> str:
    """
    Determina o fabricante real do dispositivo, substituindo textos genéricos do Windows
    como '(Standard disk drives)' ou '(Unidades de disco padrão)' a partir do modelo ou PNP ID.
    """
    cleaned = (raw_manufacturer or "").strip()
    generic_terms = {
        "",
        "(standard disk drives)",
        "(unidades de disco padrão)",
        "(unidades de disco padrao)",
        "unknown",
        "desconhecido",
        "microsoft",
    }

    if cleaned and cleaned.lower() not in generic_terms:
        return cleaned

    search_space = f"{model} {pnp_device_id}".upper()
    for prefix, vendor_name in KNOWN_VENDORS.items():
        if prefix in search_space:
            return vendor_name

    # Tenta extrair a primeira palavra do modelo se parecer uma marca
    tokens = re.split(r"[\s_\-]+", (model or "").strip())
    if tokens and len(tokens[0]) >= 3 and tokens[0].isalpha():
        return tokens[0].title()

    return "Genérico / Não Informado pelo Firmware"


def normalize_serial(raw_serial: str) -> str:
    """Limpa espaços excedentes e caracteres de controle do número de série."""
    if not raw_serial:
        return "NÃO DISPONÍVEL"
    cleaned = re.sub(r"[\x00-\x1f\x7f]+", "", str(raw_serial)).strip()
    return cleaned if cleaned else "NÃO DISPONÍVEL"


def build_composite_identity(model: str, serial: str, capacity_bytes: int) -> str:
    """
    Gera um identificador composto determinístico baseado em Modelo + Serial + Capacidade.
    Essencial para revalidar a identidade do dispositivo antes de operações de Nível 2 ou 3.
    """
    norm_model = (model or "DESCONHECIDO").strip().upper()
    norm_serial = normalize_serial(serial).upper()
    raw_key = f"MODEL:{norm_model}|SERIAL:{norm_serial}|CAP:{int(capacity_bytes)}"
    short_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:12].upper()
    return f"{norm_model}::{norm_serial}::{int(capacity_bytes)}::{short_hash}"


def verify_device_identity(target: DiskDevice, refreshed: DiskDevice) -> bool:
    """
    Verifica se o dispositivo reconsultado no sistema corresponde exatamente
    ao mesmo hardware selecionado pelo técnico (mesmo Modelo, Serial e Capacidade).
    """
    if not target or not refreshed:
        return False
    return (
        target.model.strip().upper() == refreshed.model.strip().upper()
        and normalize_serial(target.serial_number).upper()
        == normalize_serial(refreshed.serial_number).upper()
        and int(target.capacity_bytes) == int(refreshed.capacity_bytes)
        and target.composite_identity == refreshed.composite_identity
    )
