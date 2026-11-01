"""
Módulo de Confirmações e Governança de Segurança (security/confirmations.py).
Implementa as regras dos 3 níveis de segurança operacional do Storage Rescue.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from core.device_identity import verify_device_identity
from core.models import DiskDevice, SecurityLevel


@dataclass(frozen=True)
class SecurityPolicy:
    """Descreve a política de segurança aplicável a cada nível operacional."""

    level: SecurityLevel
    title: str
    description: str
    allows_write: bool
    allows_destructive: bool
    requires_phrase_confirmation: bool


SECURITY_POLICIES = {
    SecurityLevel.LEVEL_1_DIAGNOSTIC: SecurityPolicy(
        level=SecurityLevel.LEVEL_1_DIAGNOSTIC,
        title="NÍVEL 1 — DIAGNÓSTICO (SOMENTE LEITURA)",
        description=(
            "Modo estritamente somente leitura. Não modifica partições, "
            "não formata volumes e não altera letras de unidade."
        ),
        allows_write=False,
        allows_destructive=False,
        requires_phrase_confirmation=False,
    ),
    SecurityLevel.LEVEL_2_REPAIR: SecurityPolicy(
        level=SecurityLevel.LEVEL_2_REPAIR,
        title="NÍVEL 2 — REPARO LÓGICO (NÃO DESTRUTIVO)",
        description=(
            "Operações lógicas não destrutivas com explicação prévia, "
            "confirmação expressa do técnico e registro em log."
        ),
        allows_write=True,
        allows_destructive=False,
        requires_phrase_confirmation=False,
    ),
    SecurityLevel.LEVEL_3_PREPARATION: SecurityPolicy(
        level=SecurityLevel.LEVEL_3_PREPARATION,
        title="NÍVEL 3 — PREPARAÇÃO E FORMATAÇÃO (ESTRUTURAL)",
        description=(
            "Exige fluxo de 8 etapas, bloqueio de discos do sistema, "
            "frase de confirmação e revalidação de Modelo, Serial e Capacidade."
        ),
        allows_write=True,
        allows_destructive=True,
        requires_phrase_confirmation=True,
    ),
}


def validate_level3_preconditions(
    selected_device: DiskDevice,
    refreshed_device: DiskDevice,
    typed_phrase: str,
    expected_phrase: str,
) -> Tuple[bool, str]:
    """
    Valida rigorosamente todas as pré-condições de Nível 3 antes de permitir
    qualquer operação estrutural (usada na Etapa 6).
    """
    if selected_device.is_protected or refreshed_device.is_protected:
        reasons = ", ".join(selected_device.protection_reasons or refreshed_device.protection_reasons)
        return (
            False,
            f"OPERAÇÃO BLOQUEADA: O disco selecionado é protegido pelo sistema ({reasons}).",
        )

    if typed_phrase.strip() != expected_phrase.strip():
        return (
            False,
            "Frase de confirmação incorreta. A operação foi cancelada por segurança.",
        )

    if not verify_device_identity(selected_device, refreshed_device):
        return (
            False,
            "ALERTA DE SEGURANÇA: A identidade física do dispositivo (Modelo, Serial ou Capacidade) "
            "mudou desde a seleção inicial. Operação abortada imediatamente.",
        )

    return True, "Identidade e pré-condições de segurança validadas com sucesso."
