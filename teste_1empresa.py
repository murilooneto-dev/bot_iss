"""Script de teste: roda o bot para apenas a primeira empresa da lista (browser visível)."""
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

warnings.filterwarnings("ignore", message="unclosed transport", category=ResourceWarning)

from config import DOWNLOAD_DIR
from db import ensure_tables, get_all_empresas, log_result, update_empresa_total
from email_sender import send_files
from iss_session import ISSSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[logging.StreamHandler()],
)


async def main():
    ensure_tables()
    empresas = get_all_empresas()
    if not empresas:
        print("Nenhuma empresa encontrada no banco.")
        return

    empresa = empresas[0]  # primeira da lista
    empresa_id = empresa.get("id")
    login_str = empresa["login"]
    senha = empresa["senha"]
    municipio = empresa["municipio"]
    email_destino = empresa["email_destino"]
    razao_social = empresa.get("razao_social") or login_str

    company_dir = os.path.join(DOWNLOAD_DIR, f"{municipio}_{login_str}")
    os.makedirs(company_dir, exist_ok=True)

    # headless=False para ver o browser durante o teste
    session = ISSSession(municipio=municipio, download_dir=company_dir, headless=False)
    files_downloaded: list[str] = []
    total_notas = 0.0

    try:
        await session.start()
        await session.login(login_str, senha)

        mes = session.mes_atual
        ano = session.ano_atual
        print(f"\n>>> Competência: {mes:02d}/{ano}")

        # ── 1. Verificar NFS-e ─────────────────────────────────────────
        notas = await session.get_notas_mes_atual()
        total_notas = session.sum_notas(notas)
        tem_movimento = total_notas > 0
        print(f">>> NFS-e: {len(notas)} nota(s) | Total: R$ {total_notas:.2f} | {'COM' if tem_movimento else 'SEM'} MOVIMENTO")
        update_empresa_total(empresa_id, total_notas)

        # ── 2. Escrituração Prestador ──────────────────────────────────
        escrit = await session.check_escrituracao_mes_atual()

        if escrit is None:
            print(f">>> Escrituração NÃO existe — executando Nova Declaração ({'COM' if tem_movimento else 'SEM'} MOVIMENTO)...")
            escrit = await session.nova_declaracao_prestador(tem_movimento=tem_movimento)
            if escrit is None:
                raise RuntimeError("Escrituração não encontrada na lista após criação.")
            print(f">>> Escrituração criada: {escrit}")
        else:
            print(f">>> Escrituração EXISTENTE — situação: {escrit['situacao']}")

        # ── 3. Downloads ───────────────────────────────────────────────
        if escrit.get("notanumdec"):
            path = await session.download_declaracao(
                mes=escrit["mes"], ano=escrit["ano"],
                notanumdec=escrit["notanumdec"],
                full_url=escrit.get("declaracao_url"),
            )
            if path:
                files_downloaded.append(path)
                print(f">>> Declaração: {os.path.basename(path)}")
            else:
                print(">>> AVISO: Declaração não pôde ser baixada")
        else:
            print(">>> AVISO: notanumdec indisponível — declaração ignorada")

        # Boletos via ícone na linha da escrituração
        await session._ir_prestador("Escriturações")
        boletos = await session.download_boletos_escrituracao(mes=escrit["mes"], ano=escrit["ano"])
        if not boletos:
            print(">>> Ícone de boleto sem registros — tentando fallback via menu Boletos...")
            boletos = await session.download_boletos_iss(mes=escrit["mes"], ano=escrit["ano"])
        files_downloaded.extend(boletos)
        if boletos:
            print(f">>> Boleto(s): {[os.path.basename(p) for p in boletos]}")
        else:
            print(">>> Nenhum boleto ISS disponível")

        sit = await session.download_situacional()
        if sit:
            files_downloaded.append(sit)
            print(f">>> Situacional: {os.path.basename(sit)}")
        else:
            print(">>> AVISO: Situacional não pôde ser baixado")

        # ── 4. Área do Tomador ─────────────────────────────────────────
        try:
            print(">>> Processando Área do Tomador...")
            tomador_files = await session.fechar_escrituracoes_tomador()
            files_downloaded.extend(tomador_files)
            print(f">>> Tomador concluído — {len(tomador_files)} arquivo(s)")
        except Exception as tomador_exc:
            print(f">>> ERRO Tomador: {tomador_exc}")
            import traceback; traceback.print_exc()

        # ── 5. E-mail final ────────────────────────────────────────────
        if files_downloaded:
            subject = f"ISS {municipio.upper()} — {razao_social} — {mes:02d}/{ano}"
            cnpj = empresa.get("cnpj") or login_str
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
            print(f"\n>>> Enviando e-mail para {email_destino} com {len(files_downloaded)} arquivo(s)...")
            send_files(email_destino, subject, body, files_downloaded)
            print(">>> E-mail enviado com sucesso!")

        log_result(empresa_id, municipio, login_str, "ok", total_notas,
                   [os.path.basename(p) for p in files_downloaded])

        arquivos_str = "".join(f"    - {os.path.basename(p)}\n" for p in files_downloaded) or "    (nenhum)\n"
        print(
            "\n"
            "╔══════════════════════════════════════════════════════════╗\n"
            f"  RESUMO — {razao_social}\n"
            f"  Login: {login_str} | Município: {municipio}\n"
            f"  Competência: {mes:02d}/{ano}\n"
            f"  NFS-e emitidas: R$ {total_notas:.2f}"
            + (" (SEM MOVIMENTO)" if not tem_movimento else "") + "\n"
            f"  Escrituração: {escrit.get('situacao', '—') if escrit else '—'}\n"
            f"  Arquivos gerados ({len(files_downloaded)}):\n"
            f"{arquivos_str}"
            f"  E-mail enviado para: {email_destino}\n"
            "  Status: OK ✔\n"
            "╚══════════════════════════════════════════════════════════╝"
        )

    except Exception as exc:
        print(f"\n[ERRO]: {exc}")
        import traceback; traceback.print_exc()
        log_result(empresa_id, municipio, login_str, "erro", total_notas,
                   [os.path.basename(p) for p in files_downloaded], erro=str(exc))
    finally:
        await session.logout()
        await session.close()


asyncio.run(main())
