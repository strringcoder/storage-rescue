"""
Tela de Inspeção Detalhada de Dispositivos e Partições (interface/devices.py).
Exibe a árvore de partições, volumes montados/ocultos, assinatura de identidade composta
e flags de proteção de sistema para o dispositivo selecionado.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import DiskDevice, format_bytes
from interface.theme import get_status_palette


class DevicesView(QWidget):
    """Visão técnica aprofundada de um dispositivo físico e suas partições/volumes."""

    def __init__(self) -> None:
        super().__init__()
        self._devices: List[DiskDevice] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        # Seletor de dispositivo
        top_bar = QHBoxLayout()
        title = QLabel("Inspeção Técnica de Dispositivos e Partições")
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #F8FAFC;")
        top_bar.addWidget(title)
        top_bar.addStretch()

        selector_lbl = QLabel("Selecionar Dispositivo:")
        selector_lbl.setStyleSheet("color: #94A3B8; font-weight: 600;")
        top_bar.addWidget(selector_lbl)

        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(360)
        self.device_combo.currentIndexChanged.connect(self._on_Combo_changed)
        top_bar.addWidget(self.device_combo)

        layout.addLayout(top_bar)

        # Painel de Identidade Física e Segurança
        self.identity_panel = QFrame()
        self.identity_panel.setObjectName("SectionPanel")
        id_layout = QVBoxLayout(self.identity_panel)
        id_layout.setContentsMargins(16, 14, 16, 14)
        id_layout.setSpacing(10)

        self.header_lbl = QLabel("Selecione um disco para visualizar seus detalhes técnicos.")
        self.header_lbl.setStyleSheet("font-size: 16px; font-weight: 800; color: #F8FAFC;")
        id_layout.addWidget(self.header_lbl)

        self.details_grid = QGridLayout()
        self.details_grid.setHorizontalSpacing(24)
        self.details_grid.setVerticalSpacing(8)
        id_layout.addLayout(self.details_grid)

        self.protection_banner = QLabel("")
        self.protection_banner.setWordWrap(True)
        id_layout.addWidget(self.protection_banner)

        layout.addWidget(self.identity_panel)

        # Tabela de Partições e Volumes do Disco Selecionado
        part_title = QLabel("MAPA DE PARTIÇÕES E VOLUMES DO DISPOSITIVO")
        part_title.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 800; letter-spacing: 0.8px;")
        layout.addWidget(part_title)

        self.part_table = QTableWidget(0, 9)
        self.part_table.setAlternatingRowColors(True)
        self.part_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.part_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.part_table.verticalHeader().setVisible(False)
        self.part_table.setHorizontalHeaderLabels(
            [
                "Partição #",
                "Letra",
                "Rótulo (Label)",
                "Sistema de Arquivos",
                "Tipo de Partição",
                "Tamanho Total",
                "Espaço Livre",
                "Flags (Boot/Sistema)",
                "Status do Volume",
            ]
        )
        p_header = self.part_table.horizontalHeader()
        p_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        p_header.setStretchLastSection(True)
        layout.addWidget(self.part_table, stretch=1)

    def set_devices(self, devices: List[DiskDevice]) -> None:
        """Atualiza a lista de dispositivos disponíveis no seletor."""
        self._devices = devices
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for dev in devices:
            self.device_combo.addItem(
                f"Disco {dev.disk_number} — {dev.model} ({dev.capacity_formatted}) [{dev.health_status.value}]"
            )
        self.device_combo.blockSignals(False)

        if devices:
            self.device_combo.setCurrentIndex(0)
            self._render_device(devices[0])

    def select_device(self, target: DiskDevice) -> None:
        """Seleciona diretamente o dispositivo informado pelo Dashboard."""
        for idx, dev in enumerate(self._devices):
            if dev.disk_number == target.disk_number and dev.composite_identity == target.composite_identity:
                self.device_combo.setCurrentIndex(idx)
                self._render_device(dev)
                break

    def _on_Combo_changed(self, index: int) -> None:
        if 0 <= index < len(self._devices):
            self._render_device(self._devices[index])

    def _render_device(self, dev: Optional[DiskDevice]) -> None:
        if not dev:
            return

        primary_color, bg_color = get_status_palette(dev.health_status)
        self.header_lbl.setText(
            f"Disco {dev.disk_number}: {dev.manufacturer} — {dev.model} ({dev.health_status.value})"
        )
        self.header_lbl.setStyleSheet(f"font-size: 16px; font-weight: 800; color: {primary_color};")

        # Limpa grid anterior
        while self.details_grid.count():
            item = self.details_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        specs = [
            ("Caminho Físico (DeviceID)", dev.device_id),
            ("Fabricante", dev.manufacturer),
            ("Modelo", dev.model),
            ("Número de Série", dev.serial_number),
            ("Capacidade Real Detectada", dev.capacity_formatted),
            ("Espaço Não Alocado", format_bytes(dev.unallocated_bytes)),
            ("Tipo de Conexão / Mídia", f"{dev.connection_type} ({dev.media_type})"),
            ("Estilo de Partição", dev.partition_style),
            ("Sistemas de Arquivos", dev.file_systems_summary),
            ("Status Operacional", dev.operational_status),
            ("Temperatura Atual", dev.temperature_formatted),
            ("Identidade Composta (Segurança)", dev.composite_identity),
        ]

        for idx, (k, v) in enumerate(specs):
            r = idx // 4
            c = idx % 4
            box = QWidget()
            b_layout = QVBoxLayout(box)
            b_layout.setContentsMargins(0, 0, 0, 0)
            b_layout.setSpacing(2)
            kl = QLabel(k)
            kl.setStyleSheet("color: #64748B; font-size: 11px; font-weight: 700;")
            vl = QLabel(str(v))
            vl.setStyleSheet("color: #F8FAFC; font-size: 12px; font-weight: 600;")
            vl.setWordWrap(True)
            b_layout.addWidget(kl)
            b_layout.addWidget(vl)
            self.details_grid.addWidget(box, r, c)

        if dev.is_protected:
            reasons_str = " • ".join(dev.protection_reasons)
            self.protection_banner.setText(
                f"🛡️ PROTEÇÃO DE SISTEMA ATIVA: {reasons_str}. "
                "Operações destrutivas (Nível 3 - Formatação/Limpeza) estão bloqueadas para este dispositivo."
            )
            self.protection_banner.setStyleSheet(
                "background-color: #172554; color: #93C5FD; border: 1px solid #2563EB; "
                "padding: 8px 12px; border-radius: 6px; font-weight: 700;"
            )
        else:
            self.protection_banner.setText(
                f"Diagnóstico Inicial: {dev.health_reason} | SMART: {dev.smart_formatted}"
            )
            self.protection_banner.setStyleSheet(
                f"background-color: {bg_color}; color: {primary_color}; border: 1px solid {primary_color}; "
                "padding: 8px 12px; border-radius: 6px; font-weight: 600;"
            )

        # Popula tabela de partições
        self.part_table.setRowCount(len(dev.partitions))
        for row_idx, part in enumerate(dev.partitions):
            vol = part.volume
            letter_str = f"{part.drive_letter}:" if part.drive_letter else "(Sem Letra)"
            label_str = vol.label if (vol and vol.label) else "—"
            fs_str = vol.file_system if vol else "Não Montado / Sistema"
            free_str = format_bytes(vol.free_bytes) if (vol and vol.free_bytes > 0) else "—"
            vol_status = f"{vol.operational_status} ({vol.health_status})" if vol else "Partição Reservada/Oculta"

            flags = []
            if part.is_boot:
                flags.append("Boot")
            if part.is_system:
                flags.append("Sistema/EFI")
            if part.is_active:
                flags.append("Ativa")
            if part.is_hidden:
                flags.append("Oculta")
            flags_str = ", ".join(flags) if flags else "Dados"

            cols = [
                f"Partição #{part.partition_number}",
                letter_str,
                label_str,
                fs_str,
                part.partition_type,
                format_bytes(part.size_bytes),
                free_str,
                flags_str,
                vol_status,
            ]
            for col_idx, val in enumerate(cols):
                self.part_table.setItem(row_idx, col_idx, QTableWidgetItem(val))
