from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from config import DB_PATH


def _conn():
    return sqlite3.connect(DB_PATH)


def ensure_tables() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS bot_empresas (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                login         TEXT NOT NULL,
                senha         TEXT NOT NULL,
                municipio     TEXT NOT NULL,
                email_destino TEXT NOT NULL,
                total_notas   REAL,
                updated_at    TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS bot_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                empresa_id  INTEGER,
                municipio   TEXT,
                login       TEXT,
                status      TEXT,
                total_notas REAL,
                arquivos    TEXT,
                erro        TEXT,
                timestamp   TEXT
            )
        """)
        c.commit()


def get_all_empresas() -> list[dict]:
    with _conn() as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM bot_empresas").fetchall()]


def update_empresa_total(empresa_id: int, total_notas: float) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE bot_empresas SET total_notas = ?, updated_at = ? WHERE id = ?",
            (total_notas, datetime.now().isoformat(), empresa_id),
        )
        c.commit()


def log_result(
    empresa_id: int | None,
    municipio: str,
    login: str,
    status: str,
    total_notas: float,
    arquivos: list[str],
    erro: str | None = None,
) -> None:
    with _conn() as c:
        c.execute(
            """
            INSERT INTO bot_log (empresa_id, municipio, login, status, total_notas, arquivos, erro, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                empresa_id,
                municipio,
                login,
                status,
                total_notas,
                json.dumps(arquivos, ensure_ascii=False),
                erro,
                datetime.now().isoformat(),
            ),
        )
        c.commit()
