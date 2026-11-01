"""
Tela Inicial / Dashboard Principal do Storage Rescue (interface/dashboard.py).
Apresenta os 5 indicadores de resumo de bancada e a lista visual completa de dispositivos
com os 11 atributos técnicos obrigatórios e classificação por cores (Verde, Amarelo, Vermelho, Cinza).
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import DashboardMetrics, DiskDevice, HealthStatus
from interface.theme import get_status_palette


class KpiCard(QFrame):
    """Card de indicador numérico exibido no topo do Dashboard."""

    def __init__(self, title: str, value: str, subtitle: str = "", accent_color: str = "#3B82F6") -> None:
        super().__init__()
        self.setObjectName("KpiCard")
        self.setMinimumHeight(96)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        self.title_lbl = QLabel(title.upper())
        self.title_lbl.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 700; letter-spacing: 0.6px;")

        self.value_lbl = QLabel(value)
        self.value_lbl.setStyleSheet(f"color: {accent_color}; font-size: 20px; font-weight: 800;")
        self.value_lbl.setWordWrap(True)

        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setStyleSheet("color: #64748B; font-size: 11px;")
        self.sub_lbl.setWordWrap(True)

        layout.addWidget(self.title_lbl)
        layout.addWidget(self.value_lbl)
        layout.addWidget(self.sub_lbl)

    def update_content(self, value: str, subtitle: str = "", accent_color: str = "#F8FAFC") -> None:
        """Atualiza o valor principal, subtítulo e cor de destaque do card."""
        self.value_lbl.setText(value)
        self.value_lbl.setStyleSheet(f"color: {accent_color}; font-size: 19px; font-weight: 800;")
        self.sub_lbl.setText(subtitle)


class DeviceVisualCard(QFrame):
    """
    Card visual rico representando um único dispositivo conectado no Dashboard.
    Exibe todos os 11 campos obrigatórios com destaque semântico por cores.
    """

    inspect_clicked = Signal(object)

    def __init__(self, device: DiskDevice) -> None:
        super().__init__()
        self.device = device
        self.setObjectName("DeviceCard")
        primary_color, bg_badge = get_status_palette(device.health_status)

        self.setStyleSheet(
            f"""
            QFrame#DeviceCard {{
                background-color: #111827;
                border: 1px solid #1E293B;
                border-left: 5px solid {primary_color};
                border-radius: 10px;
            }}
            QFrame#DeviceCard:hover {{
                background-color: #151F32;
                border: 1px solid #3B82F6;
                border-left: 5px solid {primary_color};
            }}
            """
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(10)

        # Cabeçalho do Card: Número do Disco + Modelo + Badges de Status e Proteção
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        disk_badge = QLabel(f"DISCO {device.disk_number}")
        disk_badge.setStyleSheet(
            "background-color: #1E293B; color: #38BDF8; font-weight: 800; "
            "font-size: 12px; padding: 4px 10px; border-radius: 6px;"
        )
        header_layout.addWidget(disk_badge)

        model_lbl = QLabel(f"{device.model}")
        model_lbl.setStyleSheet("color: #F8FAFC; font-size: 15px; font-weight: 800;")
        header_layout.addWidget(model_lbl)

        conn_badge = QLabel(device.connection_type)
        conn_badge.setStyleSheet(
            "background-color: #1E3A8A; color: #93C5FD; font-weight: 700; "
            "font-size: 11px; padding: 3px 8px; border-radius: 5px;"
        )
        header_layout.addWidget(conn_badge)

        if device.is_protected:
            prot_badge = QLabel("🛡️ DISCO DO SISTEMA PROTEGIDO")
            prot_badge.setToolTip("\n".join(device.protection_reasons))
            prot_badge.setStyleSheet(
                "background-color: #172554; color: #60A5FA; border: 1px solid #2563EB; "
                "font-weight: 700; font-size: 11px; padding: 3px 8px; border-radius: 5px;"
            )
            header_layout.addWidget(prot_badge)

        header_layout.addStretch()

        status_badge = QLabel(f"● {device.health_status.value.upper()}")
        status_badge.setStyleSheet(
            f"background-color: {bg_badge}; color: {primary_color}; border: 1px solid {primary_color}; "
            "font-weight: 800; font-size: 11px; padding: 4px 12px; border-radius: 12px;"
        )
        header_layout.addWidget(status_badge)

        inspect_btn = QPushButton("🔍 Inspecionar Detalhes")
        inspect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        inspect_btn.clicked.connect(lambda: self.inspect_clicked.emit(self.device))
        header_layout.addWidget(inspect_btn)

        main_layout.addLayout(header_layout)

        # Grade com os 11 atributos técnicos obrigatórios
        grid = QGridLayout()
        grid.setHorizontalSpacing(22)
        grid.setVerticalSpacing(6)

        fields = [
            ("1. Número do Disco", f"Disco {device.disk_number} ({device.device_id})"),
            ("2. Fabricante", device.manufacturer),
            ("3. Modelo", device.model),
            ("4. Número de Série", device.serial_number),
            ("5. Capacidade Real Detectada", device.capacity_formatted),
            ("6. Tipo de Conexão", device.connection_type),
            ("7. Sistema de Arquivos", device.file_systems_summary),
            ("8. Estilo de Partição", device.partition_style),
            ("9. Status Operacional", device.operational_status),
            ("10. Temperatura", device.temperature_formatted),
        ]

        for idx, (label_text, val_text) in enumerate(fields):
            row = idx // 5
            col = idx % 5
            cell = QVBoxLayout()
            cell.setSpacing(2)
            k_lbl = QLabel(label_text)
            k_lbl.setStyleSheet("color: #64748B; font-size: 11px; font-weight: 600;")
            v_lbl = QLabel(val_text)
            v_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            v_lbl.setWordWrap(True)

            # Destaque para 0 bytes / RAW / No Media
            if "0 bytes" in val_text or "No Media" in val_text or "RAW" in val_text:
                v_lbl.setStyleSheet(f"color: {primary_color}; font-size: 12px; font-weight: 700;")
            else:
                v_lbl.setStyleSheet("color: #E2E8F0; font-size: 12px; font-weight: 600;")

            cell.addWidget(k_lbl)
            cell.addWidget(v_lbl)
            grid.addLayout(cell, row, col)

        main_layout.addLayout(grid)

        # Linha 11: Informações SMART + Diagnóstico Rápido de Status
        smart_bar = QFrame()
        smart_bar.setStyleSheet(
            "background-color: #0B1120; border: 1px solid #1E293B; border-radius: 6px;"
        )
        smart_layout = QHBoxLayout(smart_bar)
        smart_layout.setContentsMargins(12, 8, 12, 8)
        smart_layout.setSpacing(16)

        smart_lbl = QLabel(f"<b>11. Informações SMART:</b> {device.smart_formatted}")
        smart_lbl.setStyleSheet("color: #CBD5E1; font-size: 12px;")
        smart_lbl.setWordWrap(True)
        smart_layout.addWidget(smart_lbl, stretch=1)

        reason_lbl = QLabel(f"<b>Avaliação:</b> {device.health_reason}")
        reason_lbl.setStyleSheet(f"color: {primary_color}; font-size: 12px;")
        reason_lbl.setWordWrap(True)
        smart_layout.addWidget(reason_lbl, stretch=1)

        main_layout.addWidget(smart_bar)


class DashboardView(QWidget):
    """
    Tela Principal (Dashboard) do Storage Rescue.
    Exibe KPIs consolidados, botão de atualização, alternador de modo simulação
    e a lista visual/tabular dos dispositivos conectados.
    """

    refresh_requested = Signal()
    simulation_toggled = Signal(bool)
    device_selected = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._is_simulation = False
        self._devices: List[DiskDevice] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 16, 20, 16)
        root_layout.setSpacing(14)

        # Barra superior do Dashboard
        top_bar = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title_lbl = QLabel("Painel Geral de Armazenamento (Dashboard)")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: #F8FAFC;")
        subtitle_lbl = QLabel(
            "Inventário em tempo real (Nível 1: Somente Leitura) • HDs SATA, SSDs SATA/NVMe, Pendrives e Adaptadores USB"
        )
        subtitle_lbl.setStyleSheet("font-size: 12px; color: #94A3B8;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(subtitle_lbl)
        top_bar.addLayout(title_box)

        top_bar.addStretch()

        # Botão para alternar Modo Simulação de Bancada (para testar cenários críticos com segurança)
        self.sim_btn = QPushButton("🧪 Modo Simulação de Bancada: DESATIVADO")
        self.sim_btn.setCheckable(True)
        self.sim_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sim_btn.setToolTip(
            "Ativa dispositivos virtuais de teste (Pendrive 0 bytes/No Media, HD RAW, NVMe Saudável) "
            "sem modificar discos reais."
        )
        self.sim_btn.clicked.connect(self._on_simulation_clicked)
        top_bar.addWidget(self.sim_btn)

        # Botão Atualizar Dispositivos
        self.refresh_btn = QPushButton("🔄 Atualizar Dispositivos")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        top_bar.addWidget(self.refresh_btn)

        root_layout.addLayout(top_bar)

        # Linha dos 5 KPIs exigidos na Seção 3
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(12)

        self.kpi_total_disks = KpiCard("1. Discos Encontrados", "0", "Varrendo barramentos...")
        self.kpi_connected = KpiCard("2. Dispositivos Conectados", "0", "Internos e USB")
        self.kpi_capacity = KpiCard("3. Capacidade Total", "0 GB", "Soma real detectada")
        self.kpi_alerts = KpiCard("4. Dispositivos com Alertas", "0", "Atenção ou Crítico")
        self.kpi_last_diag = KpiCard("5. Último Diagnóstico", "—", "Histórico SQLite")

        for card in (
            self.kpi_total_disks,
            self.kpi_connected,
            self.kpi_capacity,
            self.kpi_alerts,
            self.kpi_last_diag,
        ):
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            kpi_layout.addWidget(card)

        root_layout.addLayout(kpi_layout)

        # Área rolável com os Cards Visuais de Dispositivos e Tabela Resumo
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_content)
        self.scroll_layout.setContentsMargins(0, 4, 4, 8)
        self.scroll_layout.setSpacing(12)

        # Seção: Lista Visual de Dispositivos Conectados
        section_lbl = QLabel("LISTA VISUAL DOS DISPOSITIVOS CONECTADOS")
        section_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 800; letter-spacing: 0.8px;")
        self.scroll_layout.addWidget(section_lbl)

        self.cards_container = QVBoxLayout()
        self.cards_container.setSpacing(12)
        self.scroll_layout.addLayout(self.cards_container)

        # Seção: Tabela Comparativa Consolidada (11 Colunas)
        table_lbl = QLabel("TABELA TÉCNICA COMPARATIVA (TODOS OS ATRIBUTOS)")
        table_lbl.setStyleSheet(
            "color: #94A3B8; font-size: 12px; font-weight: 800; letter-spacing: 0.8px; margin-top: 8px;"
        )
        self.scroll_layout.addWidget(table_lbl)

        self.table = QTableWidget(0, 11)
        self.table.setMinimumHeight(210)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setHorizontalHeaderLabels(
            [
                "Nº Disco",
                "Fabricante",
                "Modelo",
                "Número de Série",
                "Capacidade Real",
                "Conexão",
                "Sistema de Arquivos",
                "Estilo Partição",
                "Status Operacional",
                "Temp.",
                "Informações SMART",
            ]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(self._on_table_double_clicked)
        self.scroll_layout.addWidget(self.table)

        self.scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        root_layout.addWidget(scroll, stretch=1)

    def _on_simulation_clicked(self, checked: bool) -> None:
        self._is_simulation = checked
        if checked:
            self.sim_btn.setText("🧪 Modo Simulação de Bancada: ATIVO")
            self.sim_btn.setStyleSheet(
                "background-color: #451A03; color: #FBBF24; border: 1px solid #F59E0B; font-weight: 700;"
            )
        else:
            self.sim_btn.setText("🧪 Modo Simulação de Bancada: DESATIVADO")
            self.sim_btn.setStyleSheet("")
        self.simulation_toggled.emit(checked)

    def set_loading_state(self, loading: bool) -> None:
        """Ativa ou desativa o estado de carregamento no botão Atualizar."""
        self.refresh_btn.setEnabled(not loading)
        self.sim_btn.setEnabled(not loading)
        if loading:
            self.refresh_btn.setText("⏳ Atualizando Inventário...")
        else:
            self.refresh_btn.setText("🔄 Atualizar Dispositivos")

    def update_dashboard(self, devices: List[DiskDevice], metrics: DashboardMetrics) -> None:
        """Popula os KPIs, os cards visuais e a tabela comparativa com o inventário atualizado."""
        self._devices = devices

        # 1. Atualiza KPIs
        self.kpi_total_disks.update_content(
            f"{metrics.total_disks} Disco(s)",
            "Modo Simulação Ativo" if metrics.is_simulation_mode else "Hardware Físico Detectado",
            "#38BDF8",
        )
        self.kpi_connected.update_content(
            metrics.connected_summary,
            "Barramentos SATA / NVMe / USB",
            "#E2E8F0",
        )
        self.kpi_capacity.update_content(
            metrics.total_capacity_formatted,
            f"{metrics.total_capacity_bytes:,} bytes totais".replace(",", "."),
            "#22C55E",
        )

        alert_color = "#22C55E" if metrics.alert_devices_count == 0 else "#F59E0B"
        if any(d.health_status == HealthStatus.CRITICAL for d in devices):
            alert_color = "#EF4444"

        self.kpi_alerts.update_content(
            f"{metrics.alert_devices_count} em Alerta",
            "Nenhum alerta detectado" if metrics.alert_devices_count == 0 else "Requer inspeção técnica",
            alert_color,
        )
        self.kpi_last_diag.update_content(
            metrics.last_diagnostic_timestamp,
            "Modo Nível 1 (Somente Leitura)",
            "#CBD5E1",
        )

        # 2. Limpa e recria os Cards Visuais
        while self.cards_container.count():
            item = self.cards_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not devices:
            empty_lbl = QLabel("Nenhum dispositivo de armazenamento encontrado.")
            empty_lbl.setStyleSheet("color: #94A3B8; font-size: 14px; padding: 20px;")
            self.cards_container.addWidget(empty_lbl)
        else:
            for dev in devices:
                card = DeviceVisualCard(dev)
                card.inspect_clicked.connect(self.device_selected.emit)
                self.cards_container.addWidget(card)

        # 3. Atualiza Tabela Comparativa
        self.table.setRowCount(len(devices))
        for row_idx, dev in enumerate(devices):
            primary_color, _ = get_status_palette(dev.health_status)
            row_values = [
                f"Disco {dev.disk_number}",
                dev.manufacturer,
                dev.model,
                dev.serial_number,
                dev.capacity_formatted,
                dev.connection_type,
                dev.file_systems_summary,
                dev.partition_style,
                f"{dev.operational_status} ({dev.health_status.value})",
                dev.temperature_formatted,
                dev.smart_formatted,
            ]
            for col_idx, text in enumerate(row_values):
                item = QTableWidgetItem(text)
                if col_idx in (0, 8):
                    item.setForeground(Qt.GlobalColor.white)
                    item.setToolTip(dev.health_reason)
                self.table.setItem(row_idx, col_idx, item)

    def _on_table_double_clicked(self, row: int, _col: int) -> None:
        if 0 <= row < len(self._devices):
            self.device_selected.emit(self._devices[row])
