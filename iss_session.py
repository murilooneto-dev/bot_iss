"""
ISSSession — Playwright session for ISS Eletrônico (SpeedGov/Intersol).

URL base: https://iss.speedgov.com.br/{municipio}/
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date
from urllib.parse import parse_qs, urlparse

from playwright.async_api import BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)

BASE_ISS = "https://iss.speedgov.com.br"

# Meses em português — índice 1-12
MESES_PT = [
    "", "JANEIRO", "FEVEREIRO", "MAR", "ABRIL",
    "MAIO", "JUNHO", "JULHO", "AGOSTO",
    "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO",
]
# Nota: março usa "MAR" como prefixo para cobrir "MARÇO" e "MARCO" sem depender de acentos


def _parse_brl(value_str: str) -> float:
    """Parse Brazilian currency string (e.g. '1.234,56') to float."""
    # Remove tudo exceto dígitos e vírgula
    clean = re.sub(r"[^\d,]", "", value_str)
    if not clean:
        return 0.0
    # Substitui separador decimal brasileiro (vírgula) por ponto
    clean = clean.replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return 0.0


class ISSSession:
    def __init__(self, municipio: str, download_dir: str, headless: bool = True):
        self.municipio = municipio
        self.base_url = f"{BASE_ISS}/{municipio}"
        self.download_dir = download_dir
        self.headless = headless

        self._playwright = None
        self._browser = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None

        today = date.today()
        # Processa sempre a competência do mês imediatamente anterior ao atual
        if today.month == 1:
            self.mes_atual = 12
            self.ano_atual = today.year - 1
        else:
            self.mes_atual = today.month - 1
            self.ano_atual = today.year

        os.makedirs(download_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 900},
            locale="pt-BR",
        )
        self.page = await self._context.new_page()

    async def close(self) -> None:
        for obj in (self.page, self._context, self._browser, self._playwright):
            try:
                if obj:
                    await obj.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def login(self, login_str: str, senha: str) -> None:
        logger.info("Login: %s @ %s", login_str, self.municipio)
        await self.page.goto(f"{self.base_url}/login")
        await self.page.wait_for_load_state("networkidle")

        await self.page.check('input[name="tipo"][value="empresa"]')
        await self.page.fill("input#inscricao", login_str)
        await self.page.fill("input#senha", senha)
        await self.page.click('button[type="submit"]')
        await self.page.wait_for_load_state("networkidle")

        if "/login" in self.page.url or "/sessions" in self.page.url:
            raise RuntimeError(f"Login falhou para {login_str} em {self.municipio}")

        await self._dismiss_modal()
        logger.info("Login OK")

    async def _dismiss_modal(self) -> None:
        """Fecha o modal 'ATENÇÃO' do dashboard, se presente."""
        try:
            btn = self.page.locator('button:has-text("Entendi")')
            if await btn.count() > 0:
                await btn.first.click()
                await self.page.wait_for_timeout(400)
        except Exception:
            pass

    async def logout(self) -> None:
        try:
            await self.page.goto(f"{self.base_url}/logout")
            await self.page.wait_for_load_state("networkidle")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # PDF download helper
    # ------------------------------------------------------------------

    async def _download_pdf(self, url: str, filename: str) -> str | None:
        """Baixa um PDF usando os cookies da sessão e salva em download_dir."""
        filepath = os.path.join(self.download_dir, filename)
        try:
            resp = await self._context.request.get(url)
            content_type = resp.headers.get("content-type", "")
            if resp.ok and "pdf" in content_type.lower():
                with open(filepath, "wb") as f:
                    f.write(await resp.body())
                logger.info("PDF salvo: %s", filepath)
                return filepath
            else:
                logger.warning(
                    "Resposta inesperada para %s — status=%s content-type=%s",
                    url, resp.status, content_type,
                )
                return None
        except Exception as exc:
            logger.error("Erro ao baixar PDF %s: %s", url, exc)
            return None

    # ------------------------------------------------------------------
    # Notas Fiscais
    # ------------------------------------------------------------------

    async def get_notas_mes_atual(self) -> list[dict]:
        """Retorna todas as NFS-e do mês atual (inclui canceladas — filtre pelo chamador)."""
        mes, ano = self.mes_atual, self.ano_atual
        url = (
            f"{self.base_url}/modulo1/notas"
            f"?q[nfecompmes_eq]={mes}&q[nfecompano_eq]={ano}&commit=Filtrar"
        )
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

        all_rows: list[dict] = []
        while True:
            rows = await self._parse_notas_table()
            all_rows.extend(rows)

            next_link = self.page.locator(
                'a[rel="next"], .pagination a:has-text("›"), .pagination a:has-text("Próximo")'
            )
            if await next_link.count() > 0:
                await next_link.first.click()
                await self.page.wait_for_load_state("networkidle")
            else:
                break

        return all_rows

    async def _parse_notas_table(self) -> list[dict]:
        # Colunas: # | Data | Competência | Doc.Tomador | Nome Tomador | Valor | Retida | Situação | Valor ISS | ...
        return await self.page.evaluate("""
            () => {
                const rows = [];
                document.querySelectorAll('table tbody tr').forEach(tr => {
                    const cells = [...tr.querySelectorAll('td')].map(td => td.textContent.trim());
                    if (cells.length < 8) return;
                    rows.push({
                        data:        cells[1] || '',
                        competencia: cells[2] || '',
                        tomador:     cells[4] || '',
                        valor:       cells[5] || '0',
                        situacao:    cells[7] || '',
                        valorISS:    cells[8] || '0',
                    });
                });
                return rows;
            }
        """)

    def sum_notas(self, notas: list[dict]) -> float:
        """Soma o Valor das notas não canceladas."""
        total = sum(
            _parse_brl(n.get("valor", "0"))
            for n in notas
            if "CANCELADA" not in n.get("situacao", "").upper()
        )
        return round(total, 2)

    # ------------------------------------------------------------------
    # Escriturações
    # ------------------------------------------------------------------

    async def check_escrituracao_mes_atual(self) -> dict | None:
        """Verifica se já existe escrituração para o mês atual. Retorna dados da linha ou None."""
        mes, ano = self.mes_atual, self.ano_atual
        # Filtra pelo ano para reduzir volume (parâmetro Ransack mais provável)
        url = f"{self.base_url}/modulo1/escrituracoes?q[notaano_eq]={ano}&commit=Filtrar"
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

        result = await self._find_escrituracao_in_table(mes, ano)
        if result:
            return result

        # Fallback: sem filtro (caso o parâmetro Ransack seja diferente)
        await self.page.goto(f"{self.base_url}/modulo1/escrituracoes")
        await self.page.wait_for_load_state("networkidle")
        return await self._find_escrituracao_in_table(mes, ano)

    async def _find_escrituracao_in_table(self, mes: int, ano: int) -> dict | None:
        """Busca na tabela atual uma linha de escrituração para mes/ano (ignora canceladas).

        Aceita os formatos: 'ABRIL/2026', '04/2026' e '4/2026'.
        """
        mes_nome = MESES_PT[mes] if 1 <= mes <= 12 else ""
        # Possíveis variações do texto de competência que o sistema pode usar
        patterns = [
            mes_nome,           # "ABRIL" (presente em "ABRIL/2026")
            f"{mes:02d}/{ano}",  # "04/2026"
            f"{mes}/{ano}",      # "4/2026"
        ]
        result = await self.page.evaluate(
            """
            ([patterns, ano]) => {
                for (const tr of document.querySelectorAll('table tbody tr')) {
                    const cells = [...tr.querySelectorAll('td')].map(td => td.textContent.trim());
                    const comp = (cells[0] || '').toUpperCase();
                    // Verifica se a competência contém um dos padrões E o ano correto
                    const anoStr = String(ano);
                    const matchesComp = patterns.some(p => p && comp.includes(p.toUpperCase()));
                    const matchesAno  = comp.includes(anoStr);
                    if (!matchesComp || !matchesAno) continue;
                    const situacao = cells[3] || '';
                    if (situacao.toUpperCase().includes('CANCELADA')) continue;
                    const links = [...tr.querySelectorAll('a[href]')].map(a => a.href);
                    const numero = cells[1] || '';
                    return { cells, links, situacao, numero };
                }
                return null;
            }
            """,
            [patterns, ano],
        )
        if not result:
            return None

        links: list[str] = result["links"]
        decl_url = next((l for l in links if "/pdfs/declaracao" in l), None)
        boleto_list_url = next((l for l in links if "/modulo4/boletos" in l), None)

        notanumdec: str | None = None
        row_mes, row_ano = mes, ano

        if decl_url:
            params = parse_qs(urlparse(decl_url).query)
            notanumdec = params.get("notanumdec", [None])[0]
            row_mes = int(params.get("mes", [str(mes)])[0])
            row_ano = int(params.get("ano", [str(ano)])[0])

        # Fallback: número da coluna da tabela
        if not notanumdec and result.get("numero"):
            notanumdec = result["numero"].strip()

        return {
            "mes": row_mes,
            "ano": row_ano,
            "notanumdec": notanumdec,
            "declaracao_url": decl_url,
            "boleto_list_url": boleto_list_url,
            "situacao": result["situacao"],
        }

    async def nova_escrituracao(self, total_nfs: float) -> dict | None:
        """Cria nova escrituração para o mês atual. Retorna dados da linha criada."""
        mes, ano = self.mes_atual, self.ano_atual
        debug_dir = self.download_dir

        await self.page.goto(f"{self.base_url}/modulo1/escrituracoes")
        await self.page.wait_for_load_state("networkidle")

        # Screenshot: lista antes de criar
        await self.page.screenshot(path=os.path.join(debug_dir, "debug_01_lista_antes.png"), full_page=True)

        # Clica em "Nova Declaração"
        nova_btn = self.page.locator('a:has-text("Nova Declaração"), button:has-text("Nova Declaração")')
        await nova_btn.first.click()

        # Espera modal Bootstrap abrir (até 5 s) — se não abrir, assume nova página
        modal_sel = '.modal.show, .modal[style*="display: block"], .modal[style*="display:block"]'
        modal_abriu = False
        try:
            await self.page.wait_for_selector(modal_sel, timeout=5000)
            modal_abriu = True
            logger.info("nova_escrituracao — modal detectado")
        except Exception:
            await self.page.wait_for_timeout(1500)
            logger.info("nova_escrituracao — modal nao detectado, assume form inline/nova pagina")

        # Screenshot: estado após clicar (modal aberto ou nova página)
        await self.page.screenshot(path=os.path.join(debug_dir, "debug_02_apos_click_nova.png"), full_page=True)
        logger.info("nova_escrituracao — URL após click: %s", self.page.url)

        # Inspecionar selects: dentro do modal (se abriu) ou em toda a página
        ctx_sel = modal_sel if modal_abriu else "body"
        select_info = await self.page.evaluate(
            """
            (ctx) => {
                const container = ctx === 'body' ? document : document.querySelector(ctx);
                if (!container) return [];
                return [...container.querySelectorAll('select')].map(sel => ({
                    name: sel.name, id: sel.id,
                    options: [...sel.options].map(o => ({ value: o.value, text: o.text }))
                }));
            }
            """,
            ctx_sel,
        )
        logger.info("nova_escrituracao — selects no contexto '%s': %s", ctx_sel, select_info)

        # Preenche mês/ano e valor SOMENTE dentro do modal (ou da página se não há modal)
        await self._fill_competencia_form(mes, ano, total_nfs, ctx=ctx_sel)

        # Screenshot: após preencher o formulário
        await self.page.screenshot(path=os.path.join(debug_dir, "debug_03_form_preenchido.png"), full_page=True)

        # Submete — procura botão de submit dentro do modal se possível
        submitted = await self._js_click_submit(ctx=ctx_sel)
        if not submitted:
            await self.page.screenshot(path=os.path.join(debug_dir, "debug_04_sem_submit.png"), full_page=True)
            raise RuntimeError("Botão de submit não encontrado no formulário Nova Declaração")

        await self.page.wait_for_timeout(2000)
        await self.page.wait_for_load_state("networkidle")

        # Screenshot: após submissão
        await self.page.screenshot(path=os.path.join(debug_dir, "debug_04_apos_submit.png"), full_page=True)
        logger.info("nova_escrituracao — URL após submit: %s", self.page.url)

        # Se redirecionou para outra página, volta para a lista
        if "escrituracoes" not in self.page.url:
            logger.info("nova_escrituracao — redirecionou, voltando para lista...")
            await self.page.goto(f"{self.base_url}/modulo1/escrituracoes")
            await self.page.wait_for_load_state("networkidle")

        # Inspecionar todas as linhas da tabela para diagnóstico
        all_rows = await self.page.evaluate("""
            () => [...document.querySelectorAll('table tbody tr')].map(tr =>
                [...tr.querySelectorAll('td')].map(td => td.textContent.trim())
            )
        """)
        logger.info("nova_escrituracao — linhas na tabela após criação: %s", all_rows)

        await self.page.screenshot(path=os.path.join(debug_dir, "debug_05_lista_depois.png"), full_page=True)

        return await self._find_escrituracao_in_table(mes, ano)

    async def _fill_competencia_form(self, mes: int, ano: int, total_nfs: float, ctx: str = "body") -> None:
        """Preenche selects de mês/ano e tenta preencher campo de valor no formulário ativo."""
        valor_str = f"{total_nfs:.2f}".replace(".", ",")
        await self.page.evaluate(
            """
            ([mes, ano, valorStr, ctx]) => {
                const root = ctx === 'body' ? document : (document.querySelector(ctx) || document);
                const selects = [...root.querySelectorAll('select:not([disabled])')];

                let mesFilled = false;
                let anoFilled = false;

                for (const sel of selects) {
                    const opts = [...sel.options];
                    const nums = opts.map(o => parseInt(o.value)).filter(v => !isNaN(v));
                    if (nums.length === 0) continue;

                    // Select de mês: valores 1-12 (máx 13 opções incluindo placeholder)
                    if (!mesFilled && nums.every(v => v >= 0 && v <= 12) && nums.length <= 13) {
                        sel.value = String(mes);
                        sel.dispatchEvent(new Event('change', { bubbles: true }));
                        mesFilled = true;
                        continue;
                    }
                    // Select de ano: contém valores >= 2000
                    if (!anoFilled && nums.some(v => v >= 2000)) {
                        sel.value = String(ano);
                        sel.dispatchEvent(new Event('change', { bubbles: true }));
                        anoFilled = true;
                    }
                }

                // Tenta preencher campo de valor se existir
                if (parseFloat(valorStr.replace(',', '.')) > 0) {
                    const patterns = ['valor', 'total', 'servico', 'movimento'];
                    for (const inp of root.querySelectorAll('input[type="text"], input[type="number"], input:not([type])')) {
                        const name = (inp.name || inp.id || inp.placeholder || '').toLowerCase();
                        if (patterns.some(p => name.includes(p))) {
                            inp.value = valorStr;
                            inp.dispatchEvent(new Event('input', { bubbles: true }));
                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                            break;
                        }
                    }
                }
            }
            """,
            [mes, ano, valor_str, ctx],
        )

    async def _js_click_submit(self, ctx: str = "body") -> bool:
        """Clica no botão de submit visível dentro do contexto (modal ou página)."""
        return await self.page.evaluate(
            """
            (ctx) => {
                const root = ctx === 'body' ? document : (document.querySelector(ctx) || document);
                // Botões type=submit visíveis
                for (const btn of root.querySelectorAll('button[type="submit"], input[type="submit"]')) {
                    if (btn.offsetParent !== null) { btn.click(); return true; }
                }
                // Botões com texto de confirmação
                const keywords = ['confirmar', 'salvar', 'declarar', 'enviar', 'ok', 'criar'];
                for (const btn of root.querySelectorAll('button')) {
                    const text = btn.textContent.toLowerCase().trim();
                    if (keywords.some(k => text.includes(k)) && btn.offsetParent !== null) {
                        btn.click(); return true;
                    }
                }
                return false;
            }
            """,
            ctx,
        )

    # ------------------------------------------------------------------
    # Downloads
    # ------------------------------------------------------------------

    async def download_declaracao(
        self,
        mes: int,
        ano: int,
        notanumdec: str,
        full_url: str | None = None,
    ) -> str | None:
        """Baixa o PDF da declaração e retorna o caminho do arquivo."""
        url = full_url or (
            f"{self.base_url}/pdfs/declaracao"
            f"?mes={mes}&ano={ano}&notanumdec={notanumdec}&tipo=P&notatipdecl=N"
        )
        filename = f"declaracao_{mes:02d}_{ano}_{notanumdec}.pdf"
        return await self._download_pdf(url, filename)

    async def download_boletos_iss(self, mes: int, ano: int) -> list[str]:
        """Baixa todos os boletos de ISS em aberto para a competência. Retorna lista de caminhos."""
        url = (
            f"{self.base_url}/modulo4/boletos"
            f"?q[pclmesref_eq]={mes}&q[credito_titexerc_eq]={ano}&commit=Filtrar"
        )
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")

        # Colunas: #Crédito(0) | #Parcela(1) | Mês(2) | Exercício(3) | Tributo(4) |
        #          Tipo Receita(5) | Referente(6) | Vencimento(7) | Val.Orig(8) | Val.Atual(9) | Situação(10)
        boleto_rows = await self.page.evaluate("""
            () => {
                const rows = [];
                document.querySelectorAll('table tbody tr').forEach(tr => {
                    const cells = [...tr.querySelectorAll('td')].map(td => td.textContent.trim());
                    const printLink = tr.querySelector('a[href*="/pdfs/"][href*="/boleto"]');
                    if (!printLink) return;
                    rows.push({
                        tributo:   cells[4] || '',
                        situacao:  cells[10] || '',
                        boletoUrl: printLink.href,
                    });
                });
                return rows;
            }
        """)

        downloaded: list[str] = []
        for i, row in enumerate(boleto_rows):
            tributo = row.get("tributo", "").upper()
            situacao = row.get("situacao", "").upper()

            if "ISS" not in tributo:
                continue
            if any(s in situacao for s in ("PAGO", "CANCELADA")):
                continue

            filename = f"boleto_iss_{mes:02d}_{ano}_{i + 1}.pdf"
            path = await self._download_pdf(row["boletoUrl"], filename)
            if path:
                downloaded.append(path)

        if not downloaded:
            logger.info("Nenhum boleto ISS disponível para %02d/%d", mes, ano)

        return downloaded

    async def download_situacional(self) -> str | None:
        """Baixa o Relatório Situacional PDF."""
        url = f"{self.base_url}/pdfs/situacional"
        filename = f"situacional_{self.mes_atual:02d}_{self.ano_atual}.pdf"
        return await self._download_pdf(url, filename)
