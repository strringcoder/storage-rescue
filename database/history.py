"""
Módulo de Consulta e Registro de Histórico (database/history.py).
Permite consultar o último diagnóstico realizado para exibição no Dashboard.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from core.logger import logger
from database.database import DB_PATH, get_connection, init_database


class HistoryRepository:
    """Repositório para leitura e gravação do histórico de diagnósticos em SQLite."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        init_database(self.db_path)

    def get_last_diagnostic_summary(self) -> str:
        """
        Retorna a data/hora e o dispositivo do último diagnóstico registrado no banco,
        ou uma mensagem padrão caso ainda não haja diagnósticos salvos.
        """
        try:
            with get_connection(self.db_path) as conn:
                row = conn.execute(
                    """
                    SELECT created_at, model, health_status
                    FROM diagnostics_history
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()
                if row:
                    return f"{row['created_at']} ({row['model']} — {row['health_status']})"
        except Exception as exc:
            logger.debug("Falha ao consultar último diagnóstico: %s", exc)
        return f"Varredura em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
