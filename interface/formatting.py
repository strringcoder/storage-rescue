"""
Módulo Visual de Preparação e Formatação Segura (interface/formatting.py).
Estrutura base preparada para a Etapa 6 (Preparação guiada com 8 passos de segurança - Nível 3).
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class FormattingView(QWidget):
    """Tela do Módulo de Preparação e Formatação Segura (Nível 3), prevista para a Etapa 6."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Módulo de Preparação e Formatação Segura (Nível 3 — Confirmação Reforçada)")
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #F8FAFC;")
        layout.addWidget(title)

        panel = QFrame()
        panel.setObjectName("SectionPanel")
        p_layout = QVBoxLayout(panel)
        p_layout.setContentsMargins(20, 18, 20, 18)

        info = QLabel(
            "<b>Etapa 6 do Cronograma de Desenvolvimento</b><br><br>"
            "Assistente guiado em <b>8 etapas obrigatórias de segurança</b> para preparar dispositivos para reutilização:<br>"
            "1. Seleção manual pelo técnico (nunca automática)<br>"
            "2. Apresentação de Modelo, Serial e Capacidade Real<br>"
            "3. Confirmação de seleção do dispositivo<br>"
            "4. Verificação e bloqueio absoluto de discos de Sistema, Boot, Paginação e Hibernação<br>"
            "5. Resumo completo das alterações (GPT/MBR, NTFS/exFAT/FAT32, Letra e Rótulo)<br>"
            "6. Digitação manual de frase de segurança<br>"
            "7. Revalidação da identidade composta (Modelo + Serial + Capacidade) imediatamente antes da execução<br>"
            "8. Execução controlada e auditada em log"
        )
        info.setStyleSheet("color: #CBD5E1; font-size: 13px;")
        info.setWordWrap(True)
        p_layout.addWidget(info)

        layout.addWidget(panel)
        layout.addStretch()
