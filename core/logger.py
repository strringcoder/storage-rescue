"""
Módulo de configuração de logs detalhados do Storage Rescue.
Garante rastreabilidade completa de todas as leituras de hardware, alertas e operações de segurança.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"
REPORTS_DIR = BASE_DIR / "reports"


def setup_logger(name: str = "storage_rescue") -> logging.Logger:
    """
    Configura e retorna o logger principal da aplicação com saída rotativa em arquivo e console.

    Args:
        name: Nome do logger a ser configurado.

    Returns:
        Instância de logging.Logger pronta para uso.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(module)s:%(funcName)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log_file = LOGS_DIR / "storage_rescue.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB por arquivo
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


logger = setup_logger()
