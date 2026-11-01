"""
Janela Principal do Storage Rescue (interface/main_window.py).
Integra a barra lateral de navegação, o trabalhador assíncrono de inventário e diagnóstico (QThread)
e os módulos da aplicação.
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from core.diagnostics_engine import (
    DeviceDiagnosticReport,
    DiagnosticsEngine,
    UsbBusDiagnosticItem,
)
from core.disk_manager import DiskManager
from core.logger import logger
from core.models import DashboardMetrics, DiskDevice
from database.history import HistoryRepository
from interface.dashboard import DashboardView
from interface.devices import DevicesView
from interface.diagnostics import DiagnosticsView
from interface.formatting import FormattingView
from interface.recovery import RecoveryView
from interface.reports import ReportsView
from interface.theme import APP_STYLESHEET


class InventoryWorker(QThread):
    """Thread de segundo plano para varredura somente leitura e diagnóstico dos dispositivos."""

    inventory_ready = Signal(list, object, list, list)

    def __init__(
        self,
        disk_manager: DiskManager,
        diagnostics_engine: DiagnosticsEngine,
        history_repo: HistoryRepository,
        simulation_mode: bool = False,
    ) -> None:
        super().__init__()
        self.disk_manager = disk_manager
        self.diagnostics_engine = diagnostics_engine
        self.history_repo = history_repo
        self.simulation_mode = simulation_mode

    def run(self) -> None:
        devices = self.disk_manager.collect_inventory(simulation_mode=self.simulation_mode)
        usb_items, io_events_by_disk = self.diagnostics_engine.scan_usb_bus_and_ghost_devices(
            simulation_mode=self.simulation_mode
        )
        reports = self.diagnostics_engine.diagnose_all_devices(
            devices=devices,
            io_events_by_disk=io_events_by_disk,
        )
        last_diag = self.history_repo.get_last_diagnostic_summary()
        metrics = self.disk_manager.compute_dashboard_metrics(
            devices=devices,
            last_diagnostic_time=last_diag,
            is_simulation=self.simulation_mode,
        )
        self.inventory_ready.emit(devices, metrics, reports, usb_items)


class MainWindow(QMainWindow):
    """Janela principal de bancada do aplicativo Storage Rescue."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Storage Rescue — Diagnóstico, Recuperação e Manutenção de Armazenamento")
        self.resize(1380, 860)
        self.setStyleSheet(APP_STYLESHEET)

        self.disk_manager = DiskManager(use_smartctl=True)
        self.diagnostics_engine = DiagnosticsEngine()
        self.history_repo = HistoryRepository()
        self.simulation_mode = False
        self._worker: InventoryWorker | None = None
        self._nav_buttons: List[QPushButton] = []

        self._build_ui()
        self.trigger_inventory_refresh()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Barra Lateral (Sidebar)
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(255)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(14, 18, 14, 16)
        side_layout.setSpacing(6)

        brand_title = QLabel("🛡️ STORAGE RESCUE")
        brand_title.setStyleSheet("color: #38BDF8; font-size: 16px; font-weight: 900; letter-spacing: 0.8px;")
        brand_sub = QLabel("Bancada Técnica Windows 10/11")
        brand_sub.setStyleSheet("color: #64748B; font-size: 11px; font-weight: 600; margin-bottom: 12px;")
        side_layout.addWidget(brand_title)
        side_layout.addWidget(brand_sub)

        nav_items = [
            ("📊 Dashboard Principal", 0),
            ("💽 Dispositivos e Partições", 1),
            ("🩺 Diagnóstico Completo", 2),
            ("🛠️ Recuperação Lógica (Etapa 5)", 3),
            ("🧹 Preparação Segura (Etapa 6)", 4),
            ("📋 Histórico e Relatórios (Etapa 3)", 5),
        ]

        for label_text, page_idx in nav_items:
            btn = QPushButton(label_text)
            btn.setObjectName("NavButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, idx=page_idx: self.switch_page(idx))
            side_layout.addWidget(btn)
            self._nav_buttons.append(btn)

        side_layout.addStretch()

        # Card de Segurança Nível 1 na barra lateral
        sec_box = QFrame()
        sec_box.setStyleSheet(
            "background-color: #052E16; border: 1px solid #22C55E; border-radius: 8px; padding: 8px;"
        )
        sec_layout = QVBoxLayout(sec_box)
        sec_layout.setContentsMargins(8, 8, 8, 8)
        sec_layout.setSpacing(4)
        sec_title = QLabel("🔒 NÍVEL 1 ATIVO")
        sec_title.setStyleSheet("color: #22C55E; font-weight: 800; font-size: 11px;")
        sec_desc = QLabel(
            "Modo Somente Leitura.\nNenhuma alteração de partição, letra ou formatação é executada sem autorização."
        )
        sec_desc.setStyleSheet("color: #BBF7D0; font-size: 11px;")
        sec_desc.setWordWrap(True)
        sec_layout.addWidget(sec_title)
        sec_layout.addWidget(sec_desc)
        side_layout.addWidget(sec_box)

        main_layout.addWidget(sidebar)

        # Conteúdo Principal (Páginas Empilhadas)
        self.stack = QStackedWidget()
        self.dashboard_view = DashboardView()
        self.devices_view = DevicesView()
        self.diagnostics_view = DiagnosticsView()
        self.recovery_view = RecoveryView()
        self.formatting_view = FormattingView()
        self.reports_view = ReportsView()

        self.stack.addWidget(self.dashboard_view)
        self.stack.addWidget(self.devices_view)
        self.stack.addWidget(self.diagnostics_view)
        self.stack.addWidget(self.recovery_view)
        self.stack.addWidget(self.formatting_view)
        self.stack.addWidget(self.reports_view)

        main_layout.addWidget(self.stack, stretch=1)

        # Conexões de sinais
        self.dashboard_view.refresh_requested.connect(self.trigger_inventory_refresh)
        self.dashboard_view.simulation_toggled.connect(self._on_simulation_toggled)
        self.dashboard_view.device_selected.connect(self._on_device_inspect_requested)
        self.diagnostics_view.run_diagnostics_requested.connect(self.trigger_inventory_refresh)

        # Barra de Status inferior
        status_bar = QStatusBar()
        status_bar.setStyleSheet("background-color: #0F172A; color: #94A3B8; border-top: 1px solid #1E293B;")
        self.setStatusBar(status_bar)
        self.statusBar().showMessage("Pronto — Nível 1 (Diagnóstico e Inventário Somente Leitura)")

        self.switch_page(0)

    def switch_page(self, index: int) -> None:
        """Alterna a página visível no QStackedWidget e destaca o botão correspondente."""
        self.stack.setCurrentIndex(index)
        for idx, btn in enumerate(self._nav_buttons):
            btn.setProperty("active", "true" if idx == index else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _on_simulation_toggled(self, enabled: bool) -> None:
        self.simulation_mode = enabled
        self.trigger_inventory_refresh()

    def _on_device_inspect_requested(self, device: DiskDevice) -> None:
        self.devices_view.select_device(device)
        self.switch_page(1)

    def trigger_inventory_refresh(self) -> None:
        """Inicia a varredura de discos e diagnóstico em background sem bloquear a interface."""
        if self._worker and self._worker.isRunning():
            return

        self.dashboard_view.set_loading_state(True)
        mode_str = "Modo Simulação de Bancada" if self.simulation_mode else "Hardware Real (Somente Leitura)"
        self.statusBar().showMessage(f"Consultando e diagnosticando dispositivos ({mode_str})...")

        self._worker = InventoryWorker(
            disk_manager=self.disk_manager,
            diagnostics_engine=self.diagnostics_engine,
            history_repo=self.history_repo,
            simulation_mode=self.simulation_mode,
        )
        self._worker.inventory_ready.connect(self._on_inventory_ready)
        self._worker.start()

    def _on_inventory_ready(
        self,
        devices: List[DiskDevice],
        metrics: DashboardMetrics,
        reports: List[DeviceDiagnosticReport],
        usb_items: List[UsbBusDiagnosticItem],
    ) -> None:
        self.dashboard_view.set_loading_state(False)
        self.dashboard_view.update_dashboard(devices, metrics)
        self.devices_view.set_devices(devices)
        self.diagnostics_view.update_diagnostics(reports, usb_items)

        mode_tag = "[SIMULAÇÃO DE BANCADA]" if self.simulation_mode else "[SOMENTE LEITURA REAL]"
        self.statusBar().showMessage(
            f"{mode_tag} Diagnóstico atualizado: {metrics.total_disks} disco(s) | "
            f"Capacidade Total: {metrics.total_capacity_formatted} | "
            f"Alertas em Discos: {metrics.alert_devices_count} | "
            f"Ocorrências no Barramento USB/Kernel: {len(usb_items)}"
        )
        logger.info(
            "Interface atualizada: %d discos, %d laudos, %d ocorrências USB/Kernel.",
            len(devices),
            len(reports),
            len(usb_items),
        )
