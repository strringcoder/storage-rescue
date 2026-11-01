"""
Módulo de Proteção de Discos Críticos (security/protections.py).
Identifica e bloqueia modificações estruturais em discos de inicialização,
sistema (Windows), arquivo de paginação (pagefile.sys) e hibernação (hiberfil.sys).
"""

from __future__ import annotations

import os
from typing import List, Set

from core.logger import logger
from core.models import DiskDevice


def get_system_critical_drive_letters() -> Set[str]:
    """
    Retorna o conjunto de letras de unidade críticas para a execução do sistema operacional
    (ex: 'C'), verificando variáveis de ambiente do Windows e arquivos de paginação/hibernação.
    """
    critical_letters: Set[str] = set()

    system_drive = os.environ.get("SystemDrive", "C:").replace(":", "").strip().upper()
    if system_drive:
        critical_letters.add(system_drive)

    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    if len(system_root) >= 2 and system_root[1] == ":":
        critical_letters.add(system_root[0].upper())

    # Verifica existência de pagefile.sys, swapfile.sys ou hiberfil.sys em letras montadas
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        root_path = f"{letter}:\\"
        if not os.path.exists(root_path):
            continue
        for sys_file in ("pagefile.sys", "swapfile.sys", "hiberfil.sys"):
            try:
                if os.path.exists(os.path.join(root_path, sys_file)):
                    critical_letters.add(letter)
            except OSError:
                # Se houver bloqueio de permissão em arquivo de sistema na raiz, protege por precaução
                pass

    return critical_letters


def evaluate_disk_protections(
    device: DiskDevice,
    pagefile_letters: Set[str] | None = None,
    hiberfile_letters: Set[str] | None = None,
) -> List[str]:
    """
    Avalia se o disco contém partições de boot, sistema do Windows, arquivo de paginação
    ou hibernação, preenchendo as flags de proteção no objeto DiskDevice.
    """
    reasons: List[str] = []
    system_drive = os.environ.get("SystemDrive", "C:").replace(":", "").strip().upper()
    pf_letters = {l.upper() for l in (pagefile_letters or set())}
    hb_letters = {l.upper() for l in (hiberfile_letters or set())}

    if device.is_boot_disk:
        reasons.append("Disco de Inicialização (Boot)")

    if device.is_system_disk:
        reasons.append("Disco do Sistema Operacional (Windows)")

    for part in device.partitions:
        letter = (part.drive_letter or "").replace(":", "").strip().upper()
        if part.is_boot and "Disco de Inicialização (Boot)" not in reasons:
            device.is_boot_disk = True
            reasons.append("Disco de Inicialização (Boot)")
        if (part.is_system or (letter and letter == system_drive)):
            device.is_system_disk = True
            if "Disco do Sistema Operacional (Windows)" not in reasons:
                reasons.append("Disco do Sistema Operacional (Windows)")
        if letter and letter in pf_letters:
            device.has_pagefile = True
            if "Contém Arquivo de Paginação (pagefile.sys)" not in reasons:
                reasons.append("Contém Arquivo de Paginação (pagefile.sys)")
        if letter and letter in hb_letters:
            device.has_hibernation = True
            if "Contém Arquivo de Hibernação (hiberfil.sys)" not in reasons:
                reasons.append("Contém Arquivo de Hibernação (hiberfil.sys)")

    if device.has_pagefile and "Contém Arquivo de Paginação (pagefile.sys)" not in reasons:
        reasons.append("Contém Arquivo de Paginação (pagefile.sys)")
    if device.has_hibernation and "Contém Arquivo de Hibernação (hiberfil.sys)" not in reasons:
        reasons.append("Contém Arquivo de Hibernação (hiberfil.sys)")

    device.protection_reasons = reasons
    if reasons:
        logger.debug(
            "Disco %d (%s) marcado como PROTEGIDO: %s",
            device.disk_number,
            device.model,
            ", ".join(reasons),
        )
    return reasons
