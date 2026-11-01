"""
Módulo Visual de Histórico e Relatórios (interface/reports.py).
Estrutura base preparada para a Etapa 3 (Histórico SQLite, exportação TXT/JSON e Ficha Técnica).
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class ReportsView(QWidget):
    """Tela do Módulo de Histórico SQLite e Exportação de Relatórios, prevista para a Etapa 3."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Histórico de Diagnósticos e Relatórios Técnicos (SQLite / TXT / JSON)")
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #F8FAFC;")
        layout.addWidget(title)

        panel = QFrame()
        panel.setObjectName("SectionPanel")
        p_layout = QVBoxLayout(panel)
        p_layout.setContentsMargins(20, 18, 20, 18)

        info = QLabel(
            "<b>Etapa 3 do Cronograma de Desenvolvimento</b><br><br>"
            "Armazenamento em banco SQLite local (<code>database/storage_rescue.db</code>) contendo:<br>"
            "• Data do diagnóstico, Dispositivo analisado, Modelo, Serial e Capacidade<br>"
            "• Problemas encontrados, Operações realizadas e Resultado das operações<br>"
            "• Exportação de laudos em <b>TXT</b>, <b>JSON</b> e geração de <b>Ficha Técnica de Manutenção</b>."
        )
        info.setStyleSheet("color: #CBD5E1; font-size: 13px;")
        info.setWordWrap(True)
        p_layout.addWidget(info)

        layout.addWidget(panel)
        layout.addStretch()
