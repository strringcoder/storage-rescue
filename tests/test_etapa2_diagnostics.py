"""
Testes Automatizados e Simulados da Etapa 2 (tests/test_etapa2_diagnostics.py).
Valida os 12 cenários de diagnóstico em modo somente leitura (Nível 1),
a geração de laudos explicativos em linguagem simples, a auditoria de barramento USB
para dispositivos ausentes no 'list disk' e a interface gráfica DiagnosticsView.
"""

from __future__ import annotations

import os
import unittest

from core.diagnostics_engine import DiagnosticsEngine
from core.disk_manager import DiskManager
from core.models import DiskDevice, HealthStatus, PartitionInfo, SmartSummary, VolumeInfo


class TestEtapa2Diagnostics(unittest.TestCase):
    """Bateria de testes de unidade e simulação para o Módulo de Diagnóstico (Etapa 2)."""

    def setUp(self) -> None:
        self.engine = DiagnosticsEngine()
        self.dm = DiskManager(use_smartctl=False)

    def test_simulated_devices_diagnostics(self) -> None:
        """Verifica os laudos gerados para os 4 dispositivos simulados de bancada."""
        devices = self.dm.collect_inventory(simulation_mode=True)
        usb_items, io_events = self.engine.scan_usb_bus_and_ghost_devices(simulation_mode=True)
        reports = self.engine.diagnose_all_devices(devices, io_events_by_disk=io_events)

        self.assertEqual(len(reports), 4)
        self.assertGreaterEqual(len(usb_items), 2)

        # Disco 0: NVMe saudável
        self.assertEqual(reports[0].overall_status, HealthStatus.NORMAL)
        self.assertEqual(reports[0].findings[0].code, "DEVICE_HEALTHY_LOGICAL")

        # Disco 1: HD SATA com Partição RAW e alerta SMART
        r1_codes = {f.code for f in reports[1].findings}
        self.assertIn("PARTITION_RAW", r1_codes)
        self.assertIn("SMART_INTEGRITY_ALERT", r1_codes)

        # Disco 2: Generic External 0 bytes / No Media + Evento 153 de erro de leitura LBA
        r2_codes = {f.code for f in reports[2].findings}
        self.assertEqual(reports[2].overall_status, HealthStatus.CRITICAL)
        self.assertIn("USB_NO_MEDIA_0_BYTES", r2_codes)
        self.assertIn("READ_IO_ERRORS", r2_codes)
        plain_text = reports[2].format_plain_text()
        self.assertIn("O controlador USB foi identificado", plain_text)
        self.assertIn("POSSÍVEIS CAUSAS:", plain_text)
        self.assertIn("RECOMENDAÇÃO:", plain_text)

        # Disco 3: Pendrive Kingston com partição sem letra de unidade
        r3_codes = {f.code for f in reports[3].findings}
        self.assertIn("PARTITION_MISSING_DRIVE_LETTER", r3_codes)

    def test_all_remaining_diagnostic_rules(self) -> None:
        """
        Testa cenários específicos: Disco Offline, Disco Não Inicializado,
        Disco Sem Partição, Espaço Não Alocado e Capacidade Divergente do Modelo.
        """
        # 1. Disco Offline + Não Inicializado + Capacidade Divergente (Modelo diz 500GB, mas tem 32GB)
        dev_anomaly = DiskDevice(
            disk_number=4,
            manufacturer="Kingston Technology",
            model="Kingston SSD 500GB",
            serial_number="000000000000",
            capacity_bytes=32 * 1024 * 1024 * 1024,  # 32 GiB em um modelo 500GB!
            connection_type="USB",
            file_systems_summary="Sem Partição",
            partition_style="RAW (Não Inicializado)",
            operational_status="Offline",
            is_usb=True,
            is_offline=True,
            is_uninitialized=True,
            unallocated_bytes=32 * 1024 * 1024 * 1024,
            smart_info=SmartSummary(supported=True, read_errors_total=12),
        )
        rep = self.engine.diagnose_device(dev_anomaly)
        codes = {f.code for f in rep.findings}

        self.assertEqual(rep.overall_status, HealthStatus.CRITICAL)
        self.assertIn("USB_BRIDGE_FALLBACK_SERIAL", codes)
        self.assertIn("DISK_OFFLINE", codes)
        self.assertIn("DISK_UNINITIALIZED", codes)
        self.assertIn("UNALLOCATED_SPACE", codes)
        self.assertIn("CAPACITY_MISMATCH", codes)
        self.assertIn("SMART_READ_RETRIES", codes)

        # 2. Disco Inicializado (GPT) mas sem nenhuma partição criada
        dev_no_part = DiskDevice(
            disk_number=5,
            manufacturer="Seagate",
            model="Seagate Expansion",
            serial_number="SG991122",
            capacity_bytes=250_000_000_000,
            connection_type="SATA",
            file_systems_summary="Sem Partição (100% Não Alocado)",
            partition_style="GPT",
            operational_status="Online",
            is_uninitialized=False,
            partitions=[],
        )
        rep_no_part = self.engine.diagnose_device(dev_no_part)
        self.assertIn("DISK_NO_PARTITIONS", {f.code for f in rep_no_part.findings})

    def test_diagnostics_view_offscreen(self) -> None:
        """Valida a renderização da tela DiagnosticsView no PySide6 em modo offscreen."""
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from interface.diagnostics import DiagnosticsView

        app = QApplication.instance() or QApplication([])
        devices = self.dm.collect_inventory(simulation_mode=True)
        usb_items, io_events = self.engine.scan_usb_bus_and_ghost_devices(simulation_mode=True)
        reports = self.engine.diagnose_all_devices(devices, io_events_by_disk=io_events)

        view = DiagnosticsView()
        view.update_diagnostics(reports, usb_items)
        self.assertEqual(view.filter_combo.count(), 5)  # "Todos" + 4 discos
        self.assertTrue(app is not None)


if __name__ == "__main__":
    unittest.main()
