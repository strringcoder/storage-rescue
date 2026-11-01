"""
Módulo de Conexão e Esquema SQLite (database/database.py).
Inicializa o banco de dados local para registro de diagnósticos e auditoria.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.logger import BASE_DIR, logger

DB_PATH = BASE_DIR / "database" / "storage_rescue.db"


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Retorna uma conexão SQLite configurada com Row factory."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_database(db_path: Path = DB_PATH) -> None:
    """Cria as tabelas de histórico caso ainda não existam."""
    try:
        with get_connection(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS diagnostics_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    disk_number INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    serial_number TEXT NOT NULL,
                    capacity_bytes INTEGER NOT NULL,
                    connection_type TEXT NOT NULL,
                    health_status TEXT NOT NULL,
                    problems_found TEXT NOT NULL,
                    operations_performed TEXT NOT NULL,
                    operation_result TEXT NOT NULL
                )
                """
            )
            conn.commit()
    except Exception as exc:
        logger.error("Erro ao inicializar banco SQLite: %s", exc)
