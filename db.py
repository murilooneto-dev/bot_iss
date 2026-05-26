from __future__ import annotations

import json
import logging
import os
import sqlite3
import unicodedata
from datetime import datetime

from config import DB_PATH, FISCAL_DB_PATH

_log = logging.getLogger(__name__)


def _norm_municipio(value: str) -> str:
    """'Juazeiro do Norte' → 'juazeirodonorte'"""
    nfd = unicodedata.normalize("NFD", value)
    ascii_only = nfd.encode("ascii", "ignore").decode("ascii")
    return ascii_only.lower().replace(" ", "")


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
    if not os.path.exists(FISCAL_DB_PATH):
        _log.error("Banco fiscal não encontrado: %s", FISCAL_DB_PATH)
        return []

    try:
        with sqlite3.connect(FISCAL_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT payload FROM app_data LIMIT 1").fetchone()
    except Exception as exc:
        _log.error("Erro ao conectar ao banco fiscal: %s", exc)
        return []

    if not row:
        _log.warning("app_data vazio no banco fiscal")
        return []

    try:
        payload = json.loads(row["payload"])
    except Exception as exc:
        _log.error("Erro ao decodificar payload do banco fiscal: %s", exc)
        return []

    empresas: list[dict] = []
    for cliente in payload.get("clientesData", []):
        if not cliente.get("enviaIss"):
            continue
        login = (cliente.get("loginIss") or "").strip()
        senha = (cliente.get("senhaIss") or "").strip()
        municipio = (cliente.get("municipio") or "").strip()
        email = (cliente.get("emailEnvioIss") or "").strip()
        if not login or not senha or not municipio:
            _log.warning("Cliente sem dados ISS completos, ignorando: %s", cliente.get("nome", "?"))
            continue
        empresas.append({
            "id": None,
            "cnpj": (cliente.get("cnpj") or "").strip(),
            "login": login,
            "senha": senha,
            "municipio": _norm_municipio(municipio),
            "email_destino": email,
            "razao_social": (cliente.get("nome") or "").strip(),
        })

    return empresas


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
