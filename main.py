"""
Ponto de entrada principal do aplicativo Storage Rescue (main.py).
Inicializa o sistema de logs, banco SQLite e a interface gráfica PySide6.
Permite também execução em modo CLI somente leitura (--cli-inventory e --cli-diagnose).
"""

from __future__ import annotations

import argparse
import sys

from core.diagnostics_engine import DiagnosticsEngine
from core.disk_manager import DiskManager
from core.logger import logger
from database.database import init_database


def run_cli_inventory(simulation: bool = False) -> int:
    """Executa uma varredura de inventário somente leitura no terminal para inspeção técnica."""
    init_database()
    dm = DiskManager(use_smartctl=True)
    devices = dm.collect_inventory(simulation_mode=simulation)
    metrics = dm.compute_dashboard_metrics(devices, is_simulation=simulation)

    print("=" * 88)
    print("STORAGE RESCUE — INVENTÁRIO DE DISPOSITIVOS (NÍVEL 1: SOMENTE LEITURA)")
    print("=" * 88)
    print(f"Discos encontrados     : {metrics.total_disks}")
    print(f"Dispositivos conectados: {metrics.connected_summary}")
    print(f"Capacidade total       : {metrics.total_capacity_formatted}")
    print(f"Dispositivos em alerta : {metrics.alert_devices_count}")
    print("-" * 88)

    for d in devices:
        prot = f" [PROTEGIDO: {', '.join(d.protection_reasons)}]" if d.is_protected else ""
        print(f"[Disco {d.disk_number}] {d.manufacturer} | {d.model}{prot}")
        print(f"  • Serial            : {d.serial_number}")
        print(f"  • Capacidade Real   : {d.capacity_formatted}")
        print(f"  • Conexão / Estilo  : {d.connection_type} | {d.partition_style}")
        print(f"  • Sist. de Arquivos : {d.file_systems_summary}")
        print(f"  • Status Operacional: {d.operational_status} [{d.health_status.value}]")
        print(f"  • Temperatura       : {d.temperature_formatted}")
        print(f"  • SMART             : {d.smart_formatted}")
        print(f"  • Avaliação         : {d.health_reason}")
        print("-" * 88)

    return 0


def run_cli_diagnose(simulation: bool = False) -> int:
    """Executa o Diagnóstico Completo (Etapa 2) em modo texto somente leitura."""
    init_database()
    dm = DiskManager(use_smartctl=True)
    engine = DiagnosticsEngine()

    devices = dm.collect_inventory(simulation_mode=simulation)
    usb_items, io_events_by_disk = engine.scan_usb_bus_and_ghost_devices(simulation_mode=simulation)
    reports = engine.diagnose_all_devices(devices, io_events_by_disk=io_events_by_disk)

    print("=" * 88)
    print("STORAGE RESCUE — DIAGNÓSTICO COMPLETO (ETAPA 2 • NÍVEL 1: SOMENTE LEITURA)")
    print("=" * 88)
    for rep in reports:
        print(rep.format_plain_text())
        print()

    print("=" * 88)
    print(f"AUDITORIA DE PORTAS USB E DISPOSITIVOS AUSENTES NO 'LIST DISK' ({len(usb_items)} ocorrências)")
    print("=" * 88)
    for item in usb_items:
        print(f"[{item.category}] {item.name} ({item.status})")
        print(f"  • ID / Evento    : {item.instance_id}")
        print(f"  • Última Conexão : {item.last_arrival} | Última Queda/Remoção: {item.last_removal}")
        print(f"  • Explicação     : {item.explanation}")
        print(f"  • Recomendação   : {item.recommendation}")
        print("-" * 88)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Storage Rescue — Diagnóstico, Recuperação e Manutenção de Armazenamento"
    )
    parser.add_argument(
        "--cli-inventory",
        action="store_true",
        help="Executa o inventário em modo texto (somente leitura) e exibe o resumo no console.",
    )
    parser.add_argument(
        "--cli-diagnose",
        action="store_true",
        help="Executa o diagnóstico completo (Etapa 2) e auditoria de barramento USB no console.",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Inicia com o inventário simulado de bancada para testes seguros.",
    )
    args = parser.parse_args()

    init_database()

    if args.cli_inventory:
        return run_cli_inventory(simulation=args.simulate)
    if args.cli_diagnose:
        return run_cli_diagnose(simulation=args.simulate)

    from PySide6.QtWidgets import QApplication
    from interface.main_window import MainWindow

    logger.info("Iniciando interface gráfica do Storage Rescue...")
    app = QApplication(sys.argv)
    app.setApplicationName("Storage Rescue")
    app.setOrganizationName("StorageRescueBench")

    window = MainWindow()
    if args.simulate:
        window.dashboard_view.sim_btn.click()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
