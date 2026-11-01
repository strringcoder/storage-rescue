"""
Módulo Visual de Recuperação Lógica (interface/recovery.py).
Estrutura base preparada para a Etapa 5 (Recuperação lógica não destrutiva - Nível 2).
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class RecoveryView(QWidget):
    """Tela do Módulo de Recuperação Lógica (Nível 2 - Reparo Não Destrutivo), prevista para a Etapa 5."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Módulo de Recuperação Lógica (Nível 2 — Operações Não Destrutivas)")
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #F8FAFC;")
        layout.addWidget(title)

        panel = QFrame()
        panel.setObjectName("SectionPanel")
        p_layout = QVBoxLayout(panel)
        p_layout.setContentsMargins(20, 18, 20, 18)

        info = QLabel(
            "<b>Etapa 5 do Cronograma de Desenvolvimento</b><br><br>"
            "Ferramentas para tentar recuperar o acesso lógico sem apagar dados:<br>"
            "• Atribuir letra de unidade e consultar informações de montagem<br>"
            "• Identificar partições ocultas ou sem montagem<br>"
            "• Verificar status de volumes e sistemas de arquivos<br>"
            "• Detectar discos offline<br><br>"
            "<i>Regra de Segurança Nível 2:</i> Nenhuma operação é executada automaticamente. "
            "Toda alteração explica previamente os impactos e exige confirmação expressa."
        )
        info.setStyleSheet("color: #CBD5E1; font-size: 13px;")
        info.setWordWrap(True)
        p_layout.addWidget(info)

        layout.addWidget(panel)
        layout.addStretch()
