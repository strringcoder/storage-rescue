"""
Tema visual e paleta de cores semânticas do Storage Rescue (interface/theme.py).
Implementa o padrão de cores exigido na especificação:
- Verde: Normal
- Amarelo: Atenção
- Vermelho: Crítico
- Cinza: Não identificado / Não disponível
"""

from __future__ import annotations

from typing import Tuple

from core.models import HealthStatus

# Cores semânticas (Texto/Borda Principal, Fundo Suave)
STATUS_COLORS = {
    HealthStatus.NORMAL: ("#22C55E", "#052E16"),     # Verde: Normal
    HealthStatus.WARNING: ("#F59E0B", "#451A03"),    # Amarelo: Atenção
    HealthStatus.CRITICAL: ("#EF4444", "#450A0A"),   # Vermelho: Crítico
    HealthStatus.UNKNOWN: ("#94A3B8", "#1E293B"),    # Cinza: Não identificado
}


def get_status_palette(status: HealthStatus) -> Tuple[str, str]:
    """Retorna a tupla (cor_primaria_hex, cor_fundo_hex) para o status informado."""
    return STATUS_COLORS.get(status, ("#94A3B8", "#1E293B"))


APP_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0B1120;
    color: #E2E8F0;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}

QFrame#Sidebar {
    background-color: #0F172A;
    border-right: 1px solid #1E293B;
}

QFrame#TopHeader {
    background-color: #0F172A;
    border-bottom: 1px solid #1E293B;
}

QFrame#KpiCard {
    background-color: #111827;
    border: 1px solid #1E293B;
    border-radius: 10px;
}

QFrame#KpiCard:hover {
    border: 1px solid #334155;
}

QFrame#DeviceCard {
    background-color: #111827;
    border: 1px solid #1E293B;
    border-radius: 10px;
}

QFrame#DeviceCard:hover {
    background-color: #151F32;
    border: 1px solid #3B82F6;
}

QFrame#SectionPanel {
    background-color: #0F172A;
    border: 1px solid #1E293B;
    border-radius: 10px;
}

QPushButton {
    background-color: #1E293B;
    color: #F8FAFC;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #334155;
    border-color: #475569;
}

QPushButton#PrimaryButton {
    background-color: #2563EB;
    color: #FFFFFF;
    border: 1px solid #3B82F6;
}

QPushButton#PrimaryButton:hover {
    background-color: #1D4ED8;
}

QPushButton#PrimaryButton:disabled {
    background-color: #1E293B;
    color: #64748B;
    border-color: #1E293B;
}

QPushButton#NavButton {
    background-color: transparent;
    color: #94A3B8;
    border: none;
    border-radius: 8px;
    text-align: left;
    padding: 11px 14px;
    font-size: 13px;
    font-weight: 600;
}

QPushButton#NavButton:hover {
    background-color: #1E293B;
    color: #F8FAFC;
}

QPushButton#NavButton[active="true"] {
    background-color: #1D4ED8;
    color: #FFFFFF;
}

QTableWidget {
    background-color: #0F172A;
    alternate-background-color: #111827;
    color: #E2E8F0;
    gridline-color: #1E293B;
    border: 1px solid #1E293B;
    border-radius: 8px;
    selection-background-color: #1E3A8A;
    selection-color: #FFFFFF;
}

QHeaderView::section {
    background-color: #1E293B;
    color: #94A3B8;
    font-weight: 700;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #334155;
    border-right: 1px solid #0F172A;
}

QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollBar:vertical {
    background: #0F172A;
    width: 10px;
    margin: 0px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background: #334155;
    min-height: 24px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #475569;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QComboBox {
    background-color: #1E293B;
    color: #F8FAFC;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 600;
}
"""
