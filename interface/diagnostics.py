"""
Tela Interativa do Módulo de Diagnóstico Completo (interface/diagnostics.py).
Implementa a Etapa 2 do Storage Rescue (Nível 1 de Segurança — Somente Leitura).
Exibe diagnósticos explicativos em linguagem simples para cada disco e audita o
barramento USB/PnP para pendrives que não aparecem no 'list disk'.
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.diagnostics_engine import (
    DeviceDiagnosticReport,
    DiagnosticFinding,
    UsbBusDiagnosticItem,
)
from interface.theme import get_status_palette


class FindingBlockWidget(QFrame):
    """Bloco visual que apresenta uma constatação de diagnóstico com linguagem simples e estruturada."""

    def __init__(self, finding: DiagnosticFinding, device_model: str, capacity_str: str) -> None:
        super().__init__()
        primary_color, bg_color = get_status_palette(finding.severity)

        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: #0B1120;
                border: 1px solid #1E293B;
                border-left: 4px solid {primary_color};
                border-radius: 8px;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        # Cabeçalho da constatação
        top_row = QHBoxLayout()
        title_lbl = QLabel(f"🔎 {finding.title}")
        title_lbl.setStyleSheet(f"color: {primary_color}; font-size: 14px; font-weight: 800; border: none;")
        top_row.addWidget(title_lbl)
        top_row.addStretch()

        sev_badge = QLabel(finding.severity.value.upper())
        sev_badge.setStyleSheet(
            f"background-color: {bg_color}; color: {primary_color}; border: 1px solid {primary_color}; "
            "font-size: 10px; font-weight: 800; padding: 2px 10px; border-radius: 10px;"
        )
        top_row.addWidget(sev_badge)
        layout.addLayout(top_row)

        # Bloco estruturado no padrão da especificação (Seção 4 e Seção 12)
        causes_html = "".join(f"<li>{c}</li>" for c in finding.possible_causes)
        body_html = (
            f"<b>DISPOSITIVO:</b> {device_model} &nbsp;|&nbsp; <b>CAPACIDADE:</b> {capacity_str}<br><br>"
            f"<b>DIAGNÓSTICO (O QUE FOI ENCONTRADO):</b><br>{finding.diagnosis}<br><br>"
            f"<b>O QUE SIGNIFICA:</b><br>{finding.meaning}<br><br>"
            f"<b>POSSÍVEIS CAUSAS:</b><ul style='margin-top:2px; margin-bottom:6px;'>{causes_html}</ul>"
            f"<b>RISCOS:</b><br>{finding.risks}<br><br>"
            f"<span style='color:{primary_color};'><b>PRÓXIMO PASSO RECOMENDADO:</b><br>{finding.recommendation}</span>"
        )

        body_lbl = QLabel(body_html)
        body_lbl.setStyleSheet("color: #E2E8F0; font-size: 12px; border: none;")
        body_lbl.setWordWrap(True)
        body_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(body_lbl)


class UsbBusItemCard(QFrame):
    """Card explicativo para eventos de barramento USB e pendrives ausentes no DiskPart."""

    def __init__(self, item: UsbBusDiagnosticItem) -> None:
        super().__init__()
        primary_color, bg_color = get_status_palette(item.severity)
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: #111827;
                border: 1px solid #1E293B;
                border-left: 4px solid {primary_color};
                border-radius: 8px;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        name_lbl = QLabel(f"🔌 {item.name}")
        name_lbl.setStyleSheet("color: #F8FAFC; font-size: 13px; font-weight: 800; border: none;")
        header.addWidget(name_lbl)
        header.addStretch()

        badge = QLabel(item.status)
        badge.setStyleSheet(
            f"background-color: {bg_color}; color: {primary_color}; border: 1px solid {primary_color}; "
            "font-size: 10px; font-weight: 800; padding: 2px 8px; border-radius: 8px;"
        )
        header.addWidget(badge)
        layout.addLayout(header)

        causes_html = "".join(f"<li>{c}</li>" for c in item.possible_causes)
        details_html = (
            f"<b>Identificador PnP/Evento:</b> <code>{item.instance_id}</code> &nbsp;|&nbsp; "
            f"<b>Última Conexão:</b> {item.last_arrival} &nbsp;|&nbsp; "
            f"<b>Última Queda/Remoção:</b> {item.last_removal}<br><br>"
            f"<b>ANÁLISE TÉCNICA:</b> {item.explanation}<br>"
            f"<b>POSSÍVEIS CAUSAS:</b><ul style='margin-top:2px; margin-bottom:4px;'>{causes_html}</ul>"
            f"<span style='color:{primary_color};'><b>RECOMENDAÇÃO DE BANCADA:</b> {item.recommendation}</span>"
        )
        details_lbl = QLabel(details_html)
        details_lbl.setStyleSheet("color: #CBD5E1; font-size: 12px; border: none;")
        details_lbl.setWordWrap(True)
        details_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(details_lbl)


class DiagnosticsView(QWidget):
    """
    Tela do Módulo de Diagnóstico Completo em Modo Somente Leitura (Etapa 2).
    """

    run_diagnostics_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._reports: List[DeviceDiagnosticReport] = []
        self._usb_items: List[UsbBusDiagnosticItem] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 16, 20, 16)
        root_layout.setSpacing(12)

        # Cabeçalho
        top_bar = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title = QLabel("Módulo de Diagnóstico Automático (Nível 1 — Somente Leitura)")
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #F8FAFC;")
        sub = QLabel(
            "Identifica problemas de partição, montagem, RAW, 0 bytes/No Media, erros LBA e pendrives invisíveis no DiskPart."
        )
        sub.setStyleSheet("font-size: 12px; color: #94A3B8;")
        title_col.addWidget(title)
        title_col.addWidget(sub)
        top_bar.addLayout(title_col)
        top_bar.addStretch()

        self.filter_combo = QComboBox()
        self.filter_combo.setMinimumWidth(260)
        self.filter_combo.addItem("Todos os Dispositivos")
        self.filter_combo.currentIndexChanged.connect(self._render_reports)
        top_bar.addWidget(self.filter_combo)

        self.copy_btn = QPushButton("📋 Copiar Laudo TXT")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self._copy_all_reports_to_clipboard)
        top_bar.addWidget(self.copy_btn)

        self.run_btn = QPushButton("🩺 Executar Diagnóstico Agora")
        self.run_btn.setObjectName("PrimaryButton")
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.clicked.connect(self.run_diagnostics_requested.emit)
        top_bar.addWidget(self.run_btn)

        root_layout.addLayout(top_bar)

        # Área rolável com os laudos e auditoria USB
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.scroll_layout = QVBoxLayout(content)
        self.scroll_layout.setContentsMargins(0, 4, 4, 12)
        self.scroll_layout.setSpacing(14)

        # Container de Laudos por Disco
        sec1_lbl = QLabel("1. LAUDOS DE DIAGNÓSTICO DOS DISPOSITIVOS CONECTADOS")
        sec1_lbl.setStyleSheet("color: #38BDF8; font-size: 12px; font-weight: 800; letter-spacing: 0.8px;")
        self.scroll_layout.addWidget(sec1_lbl)

        self.reports_container = QVBoxLayout()
        self.reports_container.setSpacing(12)
        self.scroll_layout.addLayout(self.reports_container)

        # Container de Auditoria de Barramento USB / Pendrives Invisíveis no DiskPart
        sec2_lbl = QLabel(
            "2. AUDITORIA DE PORTAS USB, EVENTOS DE KERNEL E PENDRIVES AUSENTES NO 'LIST DISK'"
        )
        sec2_lbl.setStyleSheet(
            "color: #F59E0B; font-size: 12px; font-weight: 800; letter-spacing: 0.8px; margin-top: 10px;"
        )
        self.scroll_layout.addWidget(sec2_lbl)

        # Guia rápido para pendrive fisicamente espetado que não aparece no list disk
        guide_frame = QFrame()
        guide_frame.setObjectName("SectionPanel")
        guide_layout = QVBoxLayout(guide_frame)
        guide_layout.setContentsMargins(14, 10, 14, 10)
        guide_lbl = QLabel(
            "<b>💡 Por que um Pendrive espetado na porta USB não aparece no <code>diskpart -> list disk</code>?</b><br>"
            "O <code>list disk</code> só lista dispositivos que concluíram a enumeração elétrica USB (D+/D-), carregaram o driver "
            "<code>USBSTOR.SYS</code> e criaram um objeto <code>\\\\.\\PhysicalDriveN</code>. Quando ele não aparece no <code>list disk</code>, "
            "ocorreu uma das 3 situações abaixo (auditadas automaticamente por este módulo):<br>"
            "• <b>Caso A (Falha de Descritor USB / Código 43 — <code>VID_0000&PID_0002</code>):</b> A porta sentiu presença elétrica, "
            "mas o controlador do pendrive travou e não enviou seu nome/VID.<br>"
            "• <b>Caso B (Queda/Desarme após Conexão):</b> O pendrive conectou e desarmou segundos depois por erro de leitura no bloco LBA 0 "
            "ou sobrecorrente (aparece abaixo como <i>Desconectado recentemente</i>).<br>"
            "• <b>Caso C (Morte Elétrica de 5V / Cristal / Fusível SMD):</b> Se o pendrive foi inserido agora e não gerou nem mesmo um "
            "evento de chegada na lista abaixo, não há sinal de <i>pull-up</i> nas linhas D+/D- (mau contato físico na porta, fusível de 5V aberto "
            "ou controlador queimado)."
        )
        guide_lbl.setStyleSheet("color: #CBD5E1; font-size: 12px;")
        guide_lbl.setWordWrap(True)
        guide_layout.addWidget(guide_lbl)
        self.scroll_layout.addWidget(guide_frame)

        self.usb_container = QVBoxLayout()
        self.usb_container.setSpacing(10)
        self.scroll_layout.addLayout(self.usb_container)

        self.scroll_layout.addStretch()
        scroll.setWidget(content)
        root_layout.addWidget(scroll, stretch=1)

    def update_diagnostics(
        self,
        reports: List[DeviceDiagnosticReport],
        usb_items: List[UsbBusDiagnosticItem],
    ) -> None:
        """Atualiza a interface com os novos laudos de diagnóstico e auditoria USB."""
        self._reports = reports
        self._usb_items = usb_items

        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()
        self.filter_combo.addItem("Todos os Dispositivos")
        for rep in reports:
            self.filter_combo.addItem(
                f"Disco {rep.device.disk_number}: {rep.device.model} [{rep.overall_status.value}]"
            )
        self.filter_combo.blockSignals(False)

        self._render_reports()
        self._render_usb_items()

    def _render_reports(self) -> None:
        while self.reports_container.count():
            item = self.reports_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        idx = self.filter_combo.currentIndex()
        selected_reports = (
            self._reports if idx <= 0 or idx - 1 >= len(self._reports) else [self._reports[idx - 1]]
        )

        for rep in selected_reports:
            dev = rep.device
            primary_color, bg_color = get_status_palette(rep.overall_status)

            card = QFrame()
            card.setObjectName("SectionPanel")
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(16, 14, 16, 14)
            c_layout.setSpacing(10)

            header = QHBoxLayout()
            h_lbl = QLabel(
                f"DISCO {dev.disk_number} — {dev.manufacturer} | {dev.model} "
                f"(Serial: {dev.serial_number} • {dev.capacity_formatted})"
            )
            h_lbl.setStyleSheet("color: #F8FAFC; font-size: 15px; font-weight: 800;")
            header.addWidget(h_lbl)
            header.addStretch()

            status_lbl = QLabel(f"LAUDO: {rep.overall_status.value.upper()}")
            status_lbl.setStyleSheet(
                f"background-color: {bg_color}; color: {primary_color}; border: 1px solid {primary_color}; "
                "font-weight: 800; font-size: 11px; padding: 4px 12px; border-radius: 10px;"
            )
            header.addWidget(status_lbl)
            c_layout.addLayout(header)

            for finding in rep.findings:
                c_layout.addWidget(
                    FindingBlockWidget(finding, dev.model, dev.capacity_formatted)
                )

            self.reports_container.addWidget(card)

    def _render_usb_items(self) -> None:
        while self.usb_container.count():
            item = self.usb_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._usb_items:
            ok_lbl = QLabel("Nenhuma falha de enumeração USB ou desconexão anômala recente registrada no PnP.")
            ok_lbl.setStyleSheet("color: #22C55E; font-weight: 700; padding: 8px;")
            self.usb_container.addWidget(ok_lbl)
            return

        for usb_item in self._usb_items:
            self.usb_container.addWidget(UsbBusItemCard(usb_item))

    def _copy_all_reports_to_clipboard(self) -> None:
        if not self._reports:
            return
        text_blocks = [rep.format_plain_text() for rep in self._reports]
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText("\n\n".join(text_blocks))
            self.copy_btn.setText("✅ Laudo Copiado!")
