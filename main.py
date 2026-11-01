"""
Ponto de entrada principal do aplicativo Storage Rescue (main.py).
Inicializa o sistema de logs, banco SQLite e a interface gráfica PySide6.
Permite também execução em modo CLI somente leitura (--cli-inventory) para verificação rápida.
"""

from __future__ import annotations

import argparse
import sys

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
        "--simulate",
        action="store_true",
        help="Inicia com o inventário simulado de bancada para testes seguros.",
    )
    args = parser.parse_args()

    init_database()

    if args.cli_inventory:
        return run_cli_inventory(simulation=args.simulate)

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
