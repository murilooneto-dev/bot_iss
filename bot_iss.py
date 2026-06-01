"""
Bot ISS — Automação do ISS Eletrônico SpeedGov por fila de empresas.

Fluxo (competência = mês anterior):
  1. Verificar NFS-e emitidas (Prestador > Notas Fiscais)
  2. Escrituração Prestador:
       Com notas → Fechar Notas de Serviço → mês anterior → Continuar
       Sem notas → Declarar Sem Movimento → mês anterior → Fechamento da Declaração → confirmar
  3. Downloads: declaração PDF, boleto ISS, relatório situacional
  4. Área do Tomador: Nova Declaração → Declarar Sem Movimento → mês anterior
       → Fechamento da Declaração → confirmar → Imprimir Declaração → salvar PDF
  5. E-mail final com todos os arquivos gerados

Uso:
    python bot_iss.py

Pré-requisitos:
    pip install -r requirements.txt
    playwright install chromium
    Copie .env.example para .env e configure as variáveis.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import sys
import urllib.request
import warnings
from datetime import date

# Força UTF-8 no terminal Windows
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Suprime aviso inofensivo do asyncio no Windows ao encerrar pipes
warnings.filterwarnings("ignore", message="unclosed transport", category=ResourceWarning)

from config import DOWNLOAD_DIR, FISCAL_SYSTEM_URL, HEADLESS
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


def atualizar_tarefa_fiscal(cnpj: str, mes: int, ano: int, tarefa: str, valor: str) -> None:
    """Notifica o Sistema Fiscal para marcar uma tarefa como concluída (ou com erro).

    Chama POST /api/bot-iss/update-tarefa no servidor local.
    Se o servidor não estiver rodando, apenas loga o aviso sem interromper o bot.

    O período enviado é o mês CORRENTE (mês em que o trabalho está sendo feito),
    não o mês de competência (mês anterior). Ex: bot roda em junho/2026 → período 06/2026.
    """
    hoje = date.today()
    periodo = f"{hoje.month:02d}/{hoje.year}"
    payload = json.dumps({"cnpj": cnpj, "periodo": periodo, "tarefa": tarefa, "valor": valor}).encode()
    url = f"{FISCAL_SYSTEM_URL}/api/bot-iss/update-tarefa"
    try:
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read())
            if body.get("ok"):
                logger.info("Sistema Fiscal — tarefa '%s' de %s (%s) atualizada para '%s'", tarefa, cnpj, periodo, valor)
            else:
                logger.warning("Sistema Fiscal — resposta inesperada: %s", body)
    except Exception as exc:
        logger.warning("Sistema Fiscal — não foi possível atualizar tarefa (servidor offline?): %s", exc)


async def process_empresa(empresa: dict) -> None:
    empresa_id = empresa.get("id")
    login_str = empresa["login"]
    cnpj = empresa.get("cnpj") or login_str
    senha = empresa["senha"]
    municipio = empresa["municipio"]
    email_destino = empresa["email_destino"]
    razao_social = empresa.get("razao_social") or login_str

    company_dir = os.path.join(DOWNLOAD_DIR, f"{municipio}_{login_str}")
    os.makedirs(company_dir, exist_ok=True)

    session = ISSSession(municipio=municipio, download_dir=company_dir, headless=HEADLESS)
    files_downloaded: list[str] = []
    total_notas = 0.0
    mes = session.mes_atual
    ano = session.ano_atual

    try:
        await session.start()
        await session.login(login_str, senha)

        mes = session.mes_atual
        ano = session.ano_atual
        logger.info("[%s | %s@%s] Competência: %02d/%d", razao_social, login_str, municipio, mes, ano)

        # ── 1. Verificar NFS-e emitidas ────────────────────────────────
        notas = await session.get_notas_mes_atual()
        total_notas = session.sum_notas(notas)
        tem_movimento = total_notas > 0
        logger.info(
            "[%s] NFS-e: %d nota(s) | Total: R$ %.2f | %s",
            login_str, len(notas), total_notas,
            "COM MOVIMENTO" if tem_movimento else "SEM MOVIMENTO",
        )

        if empresa_id is not None:
            update_empresa_total(empresa_id, total_notas)

        # ── 2. Escrituração Prestador ──────────────────────────────────
        # Verifica se já existe escrituração para não criar duplicata
        escrit = await session.check_escrituracao_mes_atual()

        if escrit is None:
            logger.info("[%s] Sem escrituração — executando Nova Declaração (%s)...",
                        login_str, "COM MOVIMENTO" if tem_movimento else "SEM MOVIMENTO")
            escrit = await session.nova_declaracao_prestador(tem_movimento=tem_movimento)
            if escrit is None:
                raise RuntimeError(
                    "Escrituração não encontrada na lista após criação. "
                    "Verifique manualmente o sistema."
                )
            logger.info("[%s] Escrituração criada: %s", login_str, escrit)
        else:
            situacao = escrit["situacao"].upper()
            logger.info(
                "[%s] Escrituração já existente — situação: %s | NFS-e: R$ %.2f",
                login_str, situacao, total_notas,
            )

        # ── 3. Downloads ───────────────────────────────────────────────
        # Declaração PDF
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

        # Boleto ISS — via ícone "Lista de Boletos da Competência" na linha da escrituração
        # (navega para Escriturações, clica no ícone de boleto da linha do mês)
        await session._ir_prestador("Escriturações")
        boleto_paths = await session.download_boletos_escrituracao(mes=escrit["mes"], ano=escrit["ano"])
        if not boleto_paths:
            # Fallback: menu Boletos com filtro
            logger.info("[%s] Fallback — tentando boletos via menu Boletos", login_str)
            boleto_paths = await session.download_boletos_iss(mes=escrit["mes"], ano=escrit["ano"])
        files_downloaded.extend(boleto_paths)

        # Relatório Situacional
        sit_path = await session.download_situacional()
        if sit_path:
            files_downloaded.append(sit_path)
        else:
            logger.warning("[%s] Relatório Situacional não pôde ser baixado", login_str)

        # ── 4. Área do Tomador — Nova Declaração Sem Movimento ─────────
        try:
            tomador_files = await session.fechar_escrituracoes_tomador()
            files_downloaded.extend(tomador_files)
            logger.info(
                "[%s] Área do Tomador — concluído (%d arquivo(s))",
                login_str, len(tomador_files),
            )
        except Exception as tomador_exc:
            logger.error("[%s] Área do Tomador — ERRO: %s", login_str, tomador_exc, exc_info=True)
            shot_path = await session.screenshot_erro("tomador_erro_final")
            extra_files = [shot_path] if shot_path else []
            subject_err = f"[ERRO] ISS {municipio.upper()} — {razao_social} — Tomador {mes:02d}/{ano}"
            body_err = (
                f"RESUMO — CNPJ: {cnpj}\n"
                f"Município: {municipio.upper()} | Competência: {mes:02d}/{ano}\n"
                f"NFS-e emitidas: R$ {total_notas:.2f}\n"
                f"Escrituração: {escrit.get('situacao', '—') if escrit else '—'}\n"
                f"Arquivos: (Área do Tomador com erro)\n"
                f"E-mail: {email_destino}\n"
                f"Status: ERRO ✗ (Tomador)\n\n"
                f"Detalhe do erro: {tomador_exc}\n\n"
                f"Screenshot da tela no momento do erro em anexo."
            )
            send_files(email_destino, subject_err, body_err, extra_files)
            logger.info("[%s] E-mail de erro (Tomador) enviado para %s", login_str, email_destino)

        # ── 5. E-mail final ────────────────────────────────────────────
        if files_downloaded:
            subject = f"ISS {municipio.upper()} — {razao_social} — {mes:02d}/{ano}"
            arquivos_lista = "\n".join(f"  - {os.path.basename(p)}" for p in files_downloaded)
            body = (
                f"RESUMO — CNPJ: {cnpj}\n"
                f"Município: {municipio.upper()} | Competência: {mes:02d}/{ano}\n"
                f"NFS-e emitidas: R$ {total_notas:.2f}"
                + (" (SEM MOVIMENTO)" if not tem_movimento else "")
                + f"\nEscrituração: {escrit.get('situacao', 'FECHADA') if escrit else 'FECHADA'}\n"
                f"Arquivos:\n{arquivos_lista}\n"
                f"E-mail: {email_destino}\n"
                f"Status: OK ✔"
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

        # ── Integração Sistema Fiscal ──────────────────────────────────
        atualizar_tarefa_fiscal(cnpj, mes, ano, "ISS", date.today().isoformat())

        logger.info(
            "\n"
            "╔══════════════════════════════════════════════════════════╗\n"
            "  RESUMO — %s\n"
            "  Login: %s | Município: %s\n"
            "  Competência: %02d/%d\n"
            "  NFS-e emitidas: R$ %.2f%s\n"
            "  Escrituração: %s\n"
            "  Arquivos gerados (%d):\n"
            "%s"
            "  E-mail enviado para: %s\n"
            "  Status: OK ✔\n"
            "╚══════════════════════════════════════════════════════════╝",
            razao_social,
            login_str, municipio,
            mes, ano,
            total_notas,
            " (SEM MOVIMENTO)" if not tem_movimento else "",
            escrit.get("situacao", "—") if escrit else "—",
            len(files_downloaded),
            "".join(f"    - {os.path.basename(p)}\n" for p in files_downloaded) or "    (nenhum)\n",
            email_destino,
        )

    except Exception as exc:
        logger.error("[%s | %s@%s] ERRO: %s", razao_social, login_str, municipio, exc, exc_info=True)
        shot_path = await session.screenshot_erro("erro_geral")
        extra_files = [shot_path] if shot_path else []
        try:
            subject_err = f"[ERRO] ISS {municipio.upper()} — {razao_social} — {mes:02d}/{ano}"
            arquivos_parciais = "\n".join(f"  - {os.path.basename(p)}" for p in files_downloaded) or "  (nenhum)"
            body_err = (
                f"RESUMO — CNPJ: {cnpj}\n"
                f"Município: {municipio.upper()} | Competência: {mes:02d}/{ano}\n"
                f"NFS-e emitidas: R$ {total_notas:.2f}\n"
                f"Escrituração: —\n"
                f"Arquivos:\n{arquivos_parciais}\n"
                f"E-mail: {email_destino}\n"
                f"Status: ERRO ✗\n\n"
                f"Detalhe do erro: {exc}\n\n"
                f"Screenshot da tela no momento do erro em anexo."
            )
            send_files(email_destino, subject_err, body_err, files_downloaded + extra_files)
            logger.info("[%s] E-mail de erro enviado para %s", login_str, email_destino)
        except Exception as mail_exc:
            logger.error("[%s] Falha ao enviar e-mail de erro: %s", login_str, mail_exc)
        log_result(
            empresa_id=empresa_id,
            municipio=municipio,
            login=login_str,
            status="erro",
            total_notas=total_notas,
            arquivos=[os.path.basename(p) for p in files_downloaded],
            erro=str(exc),
        )
        atualizar_tarefa_fiscal(cnpj, mes, ano, "ISS", "ERRO")
    finally:
        await session.logout()
        await session.close()


async def main() -> None:
    logger.info("=== Bot ISS iniciado ===")
    ensure_tables()

    empresas = get_all_empresas()

    cnpjs_env = os.environ.get("BOT_ISS_CNPJS", "").strip()
    if cnpjs_env:
        allowed = {c.strip() for c in cnpjs_env.split(",") if c.strip()}
        empresas = [e for e in empresas if e.get("cnpj") in allowed]
        logger.info("Filtrando por CNPJs selecionados: %s", sorted(allowed))

    if not empresas:
        logger.warning("Nenhuma empresa na fila para processar.")
        return

    logger.info("Fila: %d empresa(s)", len(empresas))

    for empresa in empresas:
        logger.info(
            "--- Iniciando: %s (%s @ %s) ---",
            empresa.get("razao_social") or empresa["login"],
            empresa["login"],
            empresa["municipio"],
        )
        await process_empresa(empresa)

    logger.info("=== Bot ISS concluído ===")


if __name__ == "__main__":
    asyncio.run(main())
