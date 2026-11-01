"""
Módulo Visual de Diagnóstico (interface/diagnostics.py).
Estrutura base preparada para a Etapa 2 (Diagnóstico completo em modo somente leitura - Nível 1).
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class DiagnosticsView(QWidget):
    """Tela do Módulo de Diagnóstico (Nível 1 - Somente Leitura), a ser expandida na Etapa 2."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Módulo de Diagnóstico Automático (Nível 1 — Somente Leitura)")
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #F8FAFC;")
        layout.addWidget(title)

        panel = QFrame()
        panel.setObjectName("SectionPanel")
        p_layout = QVBoxLayout(panel)
        p_layout.setContentsMargins(20, 18, 20, 18)
        p_layout.setSpacing(10)

        info = QLabel(
            "<b>Etapa 2 do Cronograma de Desenvolvimento</b><br><br>"
            "Este módulo analisará cada dispositivo inventariado em modo <b>100% Somente Leitura</b> "
            "para identificar e explicar em linguagem técnica acessível:<br>"
            "• Disco reconhecido sem partição ou espaço não alocado<br>"
            "• Disco sem letra de unidade ou partição RAW<br>"
            "• Disco Offline ou Não Inicializado<br>"
            "• Dispositivo USB com 0 bytes / No Media / Falha de comunicação no adaptador SATA-USB<br>"
            "• Divergência de capacidade e problemas de integridade SMART"
        )
        info.setStyleSheet("color: #CBD5E1; font-size: 13px; line-height: 1.5;")
        info.setWordWrap(True)
        p_layout.addWidget(info)

        layout.addWidget(panel)
        layout.addStretch()
