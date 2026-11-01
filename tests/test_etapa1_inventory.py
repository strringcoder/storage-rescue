"""
Testes Automatizados e Simulados da Etapa 1 (tests/test_etapa1_inventory.py).
Valida o inventário de discos, parsing de dados CIM/PowerShell, detecção de dispositivos
USB 0 bytes / No Media, partições RAW, proteções de disco de sistema e interface PySide6
em modo offscreen (sem modificar discos reais).
"""

from __future__ import annotations

import os
import unittest

from core.device_identity import (
    build_composite_identity,
    resolve_manufacturer,
    verify_device_identity,
)
from core.disk_manager import DiskManager
from core.models import HealthStatus
from security.confirmations import validate_level3_preconditions


class TestEtapa1Inventory(unittest.TestCase):
    """Bateria de testes de unidade e integração simulada da Etapa 1."""

    def setUp(self) -> None:
        self.dm = DiskManager(use_smartctl=False)

    def test_simulated_inventory_completeness(self) -> None:
        """Verifica se o inventário simulado preenche todos os 11 campos obrigatórios e estados de saúde."""
        devices = self.dm.collect_inventory(simulation_mode=True)
        self.assertEqual(len(devices), 4)

        # Disco 0: NVMe do Sistema (Normal + Protegido)
        d0 = devices[0]
        self.assertEqual(d0.disk_number, 0)
        self.assertEqual(d0.connection_type, "NVMe")
        self.assertEqual(d0.partition_style, "GPT")
        self.assertEqual(d0.health_status, HealthStatus.NORMAL)
        self.assertTrue(d0.is_protected)
        self.assertIn("NTFS (C:)", d0.file_systems_summary)
        self.assertEqual(d0.temperature_formatted, "38 °C")

        # Disco 1: HD SATA com partição RAW e setores pendentes (Atenção)
        d1 = devices[1]
        self.assertEqual(d1.health_status, HealthStatus.WARNING)
        self.assertTrue(d1.has_raw_partition)
        self.assertIn("RAW", d1.file_systems_summary)

        # Disco 2: Adaptador USB Generic External 0 bytes / No Media (Crítico)
        d2 = devices[2]
        self.assertEqual(d2.model, "Generic External")
        self.assertEqual(d2.capacity_bytes, 0)
        self.assertTrue(d2.is_no_media)
        self.assertTrue(d2.is_zero_bytes)
        self.assertEqual(d2.health_status, HealthStatus.CRITICAL)
        self.assertIn("0 bytes", d2.capacity_formatted)

        # Disco 3: Pendrive Kingston sem letra de unidade (Atenção)
        d3 = devices[3]
        self.assertEqual(d3.health_status, HealthStatus.WARNING)
        self.assertIn("Sem Letra", d3.file_systems_summary)

    def test_parse_hybrid_wmi_and_msft_payload(self) -> None:
        """
        Testa o parser quando um dispositivo USB aparece no Win32_DiskDrive,
        mas falha ao montar no Get-Disk (cenário real de bancada).
        """
        mock_payload = {
            "WmiDisks": [
                {
                    "Index": 0,
                    "DeviceID": r"\\.\PHYSICALDRIVE0",
                    "Model": "SAMSUNG MZ7TN512HDHP-00007",
                    "Manufacturer": "(Unidades de disco padrão)",
                    "SerialNumber": "S38UNY0HA08910",
                    "InterfaceType": "IDE",
                    "MediaType": "Fixed hard disk media",
                    "Size": 512105932800,
                    "Partitions": 2,
                    "Status": "OK",
                },
                {
                    "Index": 2,
                    "DeviceID": r"\\.\PHYSICALDRIVE2",
                    "Model": "Generic External USB Device",
                    "Manufacturer": "(Unidades de disco padrão)",
                    "SerialNumber": "190610101002888     ",
                    "InterfaceType": "USB",
                    "MediaType": "External hard disk media",
                    "Size": 120031511040,
                    "Partitions": None,
                    "Status": "OK",
                },
            ],
            "MsftDisks": [
                {
                    "Number": 0,
                    "FriendlyName": "SAMSUNG MZ7TN512HDHP-00007",
                    "SerialNumber": "S38UNY0HA08910",
                    "BusType": "SATA",
                    "PartitionStyle": "GPT",
                    "OperationalStatus": "Online",
                    "HealthStatus": "Healthy",
                    "Size": 512110190592,
                    "AllocatedSize": 512109142016,
                    "IsBoot": True,
                    "IsSystem": True,
                    "IsOffline": False,
                    "IsReadOnly": False,
                }
            ],
            "PhysicalDisks": [],
            "Partitions": [
                {
                    "DiskNumber": 0,
                    "PartitionNumber": 1,
                    "DriveLetter": "C",
                    "Size": 512000000000,
                    "Offset": 1048576,
                    "Type": "Basic",
                    "IsBoot": True,
                    "IsSystem": True,
                }
            ],
            "Volumes": [
                {
                    "DriveLetter": "C",
                    "FileSystemLabel": "Sistema",
                    "FileSystem": "NTFS",
                    "Size": 512000000000,
                    "SizeRemaining": 250000000000,
                    "HealthStatus": "Healthy",
                    "OperationalStatus": "OK",
                }
            ],
            "Pagefiles": [{"Name": r"C:\pagefile.sys"}],
            "Reliability": {"0": {"Temperature": 35, "PowerOnHours": 1200, "ReadErrorsUncorrected": 0}},
        }

        devices = self.dm.parse_inventory_payload(mock_payload, check_smartctl=False)
        self.assertEqual(len(devices), 2)

        # Verifica Disco 0
        disk0 = devices[0]
        self.assertEqual(disk0.manufacturer, "Samsung Electronics")
        self.assertEqual(disk0.connection_type, "SATA")
        self.assertTrue(disk0.is_protected)
        self.assertEqual(disk0.health_status, HealthStatus.NORMAL)

        # Verifica Disco 2 (presente apenas no Win32_DiskDrive e sem partições)
        disk2 = devices[1]
        self.assertEqual(disk2.disk_number, 2)
        self.assertEqual(disk2.serial_number, "190610101002888")
        self.assertIn("USB", disk2.connection_type)
        self.assertEqual(disk2.health_status, HealthStatus.WARNING)

    def test_identity_and_level3_security_protections(self) -> None:
        """Garante que discos protegidos pelo sistema jamais passem na validação de Nível 3."""
        devices = self.dm.collect_inventory(simulation_mode=True)
        system_disk = devices[0]
        usb_disk = devices[3]

        # Disco do sistema deve ser bloqueado mesmo com frase correta
        ok, msg = validate_level3_preconditions(
            selected_device=system_disk,
            refreshed_device=system_disk,
            typed_phrase="CONFIRMAR FORMATACAO",
            expected_phrase="CONFIRMAR FORMATACAO",
        )
        self.assertFalse(ok)
        self.assertIn("OPERAÇÃO BLOQUEADA", msg)

        # Se o dispositivo mudar de serial/modelo após reconexão USB, deve abortar
        self.assertFalse(verify_device_identity(usb_disk, system_disk))

        # Mesmo dispositivo USB não protegido e com frase exata deve validar
        ok_usb, _ = validate_level3_preconditions(
            selected_device=usb_disk,
            refreshed_device=usb_disk,
            typed_phrase="LIMPAR DISCO",
            expected_phrase="LIMPAR DISCO",
        )
        self.assertTrue(ok_usb)

    def test_manufacturer_inference(self) -> None:
        """Verifica se fabricantes genéricos do Windows são traduzidos para o fabricante real."""
        self.assertEqual(
            resolve_manufacturer("(Unidades de disco padrão)", "SanDisk SD8SBBU480G1122"),
            "SanDisk (Western Digital)",
        )
        self.assertEqual(
            resolve_manufacturer("(Standard disk drives)", "SAMSUNG MZ7TN512HDHP-00007"),
            "Samsung Electronics",
        )

    def test_gui_offscreen_rendering(self) -> None:
        """Testa a criação e atualização do Dashboard PySide6 em modo offscreen."""
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from interface.dashboard import DashboardView
        from interface.devices import DevicesView

        app = QApplication.instance() or QApplication([])
        devices = self.dm.collect_inventory(simulation_mode=True)
        metrics = self.dm.compute_dashboard_metrics(devices, is_simulation=True)

        dash = DashboardView()
        dash.update_dashboard(devices, metrics)
        self.assertEqual(dash.table.rowCount(), 4)

        dev_view = DevicesView()
        dev_view.set_devices(devices)
        self.assertEqual(dev_view.device_combo.count(), 4)
        self.assertTrue(app is not None)


if __name__ == "__main__":
    unittest.main()
