"""
Bot ISS — Automação do ISS Eletrônico SpeedGov por fila de empresas.

Uso:
    python bot_iss.py

Pré-requisitos:
    pip install -r requirements.txt
    playwright install chromium
    Copie .env.example para .env e configure as variáveis.

Tabela de entrada esperada (bot_empresas):
    id, login, senha, municipio, email_destino
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import sys
import warnings

# Força UTF-8 no terminal Windows
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Suprime aviso inofensivo do asyncio no Windows ao encerrar pipes
warnings.filterwarnings("ignore", message="unclosed transport", category=ResourceWarning)

from config import DOWNLOAD_DIR, HEADLESS
from db import ensure_tables, get_all_empresas, log_result, update_empresa_total
from email_sender import send_files
from iss_session import ISSSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot_iss.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("bot_iss")


async def process_empresa(empresa: dict) -> None:
    empresa_id = empresa.get("id")
    login_str = empresa["login"]
    senha = empresa["senha"]
    municipio = empresa["municipio"]
    email_destino = empresa["email_destino"]
    razao_social = empresa.get("razao_social") or login_str

    company_dir = os.path.join(DOWNLOAD_DIR, f"{municipio}_{login_str}")
    os.makedirs(company_dir, exist_ok=True)

    session = ISSSession(municipio=municipio, download_dir=company_dir, headless=HEADLESS)
    files_downloaded: list[str] = []
    total_notas = 0.0

    try:
        await session.start()
        await session.login(login_str, senha)

        mes = session.mes_atual
        ano = session.ano_atual
        logger.info("[%s | %s@%s] Competência: %02d/%d", razao_social, login_str, municipio, mes, ano)

        # ── Notas Fiscais ─────────────────────────────────────────────
        notas = await session.get_notas_mes_atual()
        total_notas = session.sum_notas(notas)
        logger.info("[%s] NFS-e: %d nota(s) | Total: R$ %.2f", login_str, len(notas), total_notas)

        if empresa_id is not None:
            update_empresa_total(empresa_id, total_notas)

        # ── Escriturações ──────────────────────────────────────────────
        escrit = await session.check_escrituracao_mes_atual()

        if escrit is None:
            logger.info("[%s] Escrituração não encontrada — criando...", login_str)
            escrit = await session.nova_escrituracao(total_notas)
            if escrit is None:
                raise RuntimeError(
                    "Escrituração não encontrada na lista após criação. "
                    "Verifique manualmente o sistema."
                )
            logger.info("[%s] Escrituração criada: %s", login_str, escrit)
        else:
            logger.info("[%s] Escrituração existente — situação: %s", login_str, escrit["situacao"])

        # ── Download Declaração ────────────────────────────────────────
        if escrit.get("notanumdec"):
            decl_path = await session.download_declaracao(
                mes=escrit["mes"],
                ano=escrit["ano"],
                notanumdec=escrit["notanumdec"],
                full_url=escrit.get("declaracao_url"),
            )
            if decl_path:
                files_downloaded.append(decl_path)
            else:
                logger.warning("[%s] Declaração não pôde ser baixada", login_str)
        else:
            logger.warning("[%s] notanumdec não disponível — download da declaração ignorado", login_str)

        # ── Download Boleto ISS ────────────────────────────────────────
        boleto_paths = await session.download_boletos_iss(mes=escrit["mes"], ano=escrit["ano"])
        files_downloaded.extend(boleto_paths)

        # ── Download Relatório Situacional ─────────────────────────────
        sit_path = await session.download_situacional()
        if sit_path:
            files_downloaded.append(sit_path)
        else:
            logger.warning("[%s] Relatório Situacional não pôde ser baixado", login_str)

        # ── Envio de E-mail ────────────────────────────────────────────
        if files_downloaded:
            subject = f"ISS {municipio.upper()} — {razao_social} — {mes:02d}/{ano}"
            body = (
                f"Documentos ISS de {mes:02d}/{ano}\n"
                f"Empresa: {razao_social} ({login_str}) | Município: {municipio}\n"
                f"Total NFS-e emitidas: R$ {total_notas:.2f}\n\n"
                f"Arquivos em anexo ({len(files_downloaded)}):\n"
                + "\n".join(f"  - {os.path.basename(p)}" for p in files_downloaded)
            )
            send_files(email_destino, subject, body, files_downloaded)
            logger.info("[%s] E-mail enviado para %s (%d arquivo(s))", login_str, email_destino, len(files_downloaded))
        else:
            logger.warning("[%s] Nenhum arquivo disponível para envio", login_str)

        log_result(
            empresa_id=empresa_id,
            municipio=municipio,
            login=login_str,
            status="ok",
            total_notas=total_notas,
            arquivos=[os.path.basename(p) for p in files_downloaded],
        )

    except Exception as exc:
        logger.error("[%s | %s@%s] ERRO: %s", razao_social, login_str, municipio, exc, exc_info=True)
        log_result(
            empresa_id=empresa_id,
            municipio=municipio,
            login=login_str,
            status="erro",
            total_notas=total_notas,
            arquivos=[os.path.basename(p) for p in files_downloaded],
            erro=str(exc),
        )
    finally:
        await session.logout()
        await session.close()


async def main() -> None:
    logger.info("=== Bot ISS iniciado ===")
    ensure_tables()

    empresas = get_all_empresas()
    if not empresas:
        logger.warning("Nenhuma empresa em bot_empresas. Insira registros e execute novamente.")
        return

    logger.info("Fila: %d empresa(s)", len(empresas))

    for empresa in empresas:
        logger.info("--- Iniciando: %s (%s @ %s) ---", empresa.get("razao_social") or empresa["login"], empresa["login"], empresa["municipio"])
        await process_empresa(empresa)

    logger.info("=== Bot ISS concluído ===")


if __name__ == "__main__":
    asyncio.run(main())
