"""Script temporário: roda o bot para apenas 1 empresa (id=97)."""
from __future__ import annotations

import asyncio
import io
import logging
import os
import sys
import warnings

# Força UTF-8 no terminal Windows para evitar UnicodeEncodeError
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
    handlers=[logging.StreamHandler()],
)


async def main():
    ensure_tables()
    empresas = [e for e in get_all_empresas() if e["id"] == 97]
    if not empresas:
        print("Empresa id=97 não encontrada.")
        return

    empresa = empresas[0]
    empresa_id = empresa.get("id")
    login_str = empresa["login"]
    senha = empresa["senha"]
    municipio = empresa["municipio"]
    email_destino = empresa["email_destino"]

    company_dir = os.path.join(DOWNLOAD_DIR, f"{municipio}_{login_str}")
    os.makedirs(company_dir, exist_ok=True)

    session = ISSSession(municipio=municipio, download_dir=company_dir, headless=False)  # headless=False para ver o browser
    files_downloaded = []
    total_notas = 0.0

    try:
        await session.start()
        await session.login(login_str, senha)

        mes = session.mes_atual
        ano = session.ano_atual
        print(f"\n>>> Competência processada: {mes:02d}/{ano}")

        # Notas Fiscais
        notas = await session.get_notas_mes_atual()
        total_notas = session.sum_notas(notas)
        print(f">>> NFS-e encontradas: {len(notas)} | Total: R$ {total_notas:.2f}")
        update_empresa_total(empresa_id, total_notas)

        # Escriturações
        escrit = await session.check_escrituracao_mes_atual()
        if escrit is None:
            print(">>> Escrituração NÃO existe — criando...")
            escrit = await session.nova_escrituracao(total_notas)
            if escrit is None:
                raise RuntimeError("Escrituração não encontrada após criação.")
            print(f">>> Escrituração criada: {escrit}")
        else:
            print(f">>> Escrituração EXISTENTE — situação: {escrit['situacao']}")
            print(f"    notanumdec={escrit['notanumdec']} | mes={escrit['mes']} | ano={escrit['ano']}")

        # Download Declaração
        if escrit.get("notanumdec"):
            path = await session.download_declaracao(
                mes=escrit["mes"], ano=escrit["ano"],
                notanumdec=escrit["notanumdec"],
                full_url=escrit.get("declaracao_url"),
            )
            if path:
                files_downloaded.append(path)
                print(f">>> Declaração salva: {os.path.basename(path)}")
            else:
                print(">>> AVISO: Declaração não pôde ser baixada")
        else:
            print(">>> AVISO: notanumdec indisponível — declaração ignorada")

        # Download Boleto ISS
        boletos = await session.download_boletos_iss(mes=escrit["mes"], ano=escrit["ano"])
        files_downloaded.extend(boletos)
        if boletos:
            print(f">>> Boleto(s) ISS salvos: {[os.path.basename(p) for p in boletos]}")
        else:
            print(">>> Nenhum boleto ISS disponível (ok, será ignorado)")

        # Download Situacional
        sit = await session.download_situacional()
        if sit:
            files_downloaded.append(sit)
            print(f">>> Situacional salvo: {os.path.basename(sit)}")
        else:
            print(">>> AVISO: Situacional não pôde ser baixado")

        # E-mail
        print(f"\n>>> Enviando e-mail para {email_destino} com {len(files_downloaded)} arquivo(s)...")
        if files_downloaded:
            subject = f"ISS {municipio.upper()} — {login_str} — {mes:02d}/{ano}"
            body = (
                f"Documentos ISS de {mes:02d}/{ano}\n"
                f"Empresa: {login_str} | Município: {municipio}\n"
                f"Total NFS-e: R$ {total_notas:.2f}\n\n"
                + "\n".join(f"  - {os.path.basename(p)}" for p in files_downloaded)
            )
            send_files(email_destino, subject, body, files_downloaded)
            print(">>> E-mail enviado com sucesso!")

        log_result(empresa_id, municipio, login_str, "ok", total_notas,
                   [os.path.basename(p) for p in files_downloaded])
        print("\n[OK] TESTE CONCLUIDO COM SUCESSO")

    except Exception as exc:
        print(f"\n[ERRO]: {exc}")
        import traceback; traceback.print_exc()
        log_result(empresa_id, municipio, login_str, "erro", total_notas,
                   [os.path.basename(p) for p in files_downloaded], erro=str(exc))
    finally:
        await session.logout()
        await session.close()


asyncio.run(main())
