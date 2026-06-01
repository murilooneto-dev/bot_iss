"""
ISSSession — Playwright session for ISS Eletrônico (SpeedGov/Intersol).

Navegação 100% por cliques como um humano.
Único page.goto permitido: a URL de login (ponto de entrada).
Delay de 5 segundos após cada carregamento de página.

Fluxo (competência = mês anterior):
  1. Login → preenche formulário e clica Entrar
  2. Prestador > Notas Fiscais → filtra mes/ano, coleta NFS-e
  3. Prestador > Escriturações → cria via "Fechar Notas de Serviço" ou "Declarar Sem Movimento"
  4. Clica em Imprimir para baixar declaração PDF
  5. Prestador > Boletos → filtra mes/ano, baixa boletos ISS
  6. Relatório Situacional → clica no link do menu
  7. Tomador > Escriturações → Nova Declaração → Declarar Sem Movimento → confirma → imprime
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import date
from urllib.parse import parse_qs, urlparse

from playwright.async_api import BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)

BASE_ISS = "https://iss.speedgov.com.br"
DELAY_PAGINA = 5000   # ms — pausa após cada carregamento de página
DELAY_ANIMACAO = 800  # ms — pausa para animação de dropdown/modal

MESES_PT = [
    "", "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL",
    "MAIO", "JUNHO", "JULHO", "AGOSTO",
    "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO",
]


def _parse_brl(value_str: str) -> float:
    clean = re.sub(r"[^\d,]", "", value_str)
    if not clean:
        return 0.0
    try:
        return float(clean.replace(",", "."))
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
    # Helpers de espera e clique
    # ------------------------------------------------------------------

    async def _aguardar_pagina(self, descricao: str = "") -> None:
        """Aguarda a página carregar + delay humano de 5 segundos."""
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=30000)
        except Exception:
            pass
        await self.page.wait_for_timeout(DELAY_PAGINA)
        if descricao:
            logger.info("Página carregada: %s — URL: %s", descricao, self.page.url)

    async def _clicar_link(self, keywords: list[str], descricao: str = "", scope: str = "body") -> str | None:
        """Localiza por JS e clica no primeiro link/botão visível que contenha uma das keywords.

        Retorna o href clicado, ou None se não encontrou.
        Aguarda 5 segundos após o clique.
        """
        href = await self.page.evaluate(
            """
            ([scope_sel, keywords]) => {
                const root = scope_sel === 'body'
                    ? document
                    : (document.querySelector(scope_sel) || document);
                for (const el of root.querySelectorAll('a, button, input[type="submit"], input[type="button"]')) {
                    const text = (el.textContent || el.value || '').toLowerCase().trim();
                    const href  = (el.href  || '').toLowerCase();
                    if (keywords.some(k => text.includes(k) || href.includes(k.replace(/ /g,'_')))) {
                        if (el.offsetParent !== null) {
                            el.click();
                            return el.href || el.textContent.trim();
                        }
                    }
                }
                return null;
            }
            """,
            [scope, [k.lower() for k in keywords]],
        )
        if href:
            logger.info("Clicou em '%s' → %s", descricao or keywords[0], href)
            await self._aguardar_pagina(descricao)
        return href

    async def _screenshot(self, nome: str) -> None:
        try:
            await self.page.screenshot(
                path=os.path.join(self.download_dir, f"{nome}.png"),
                full_page=True,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Navegação pelo menu (cliques humanos)
    # ------------------------------------------------------------------

    async def _expandir_secao_menu(self, keywords_secao: list[str]) -> None:
        """Clica no item de menu pai (ex: 'Área do Prestador') para expandir o submenu.

        Não aguarda navegação de página — só abre o accordion/dropdown.
        """
        await self.page.evaluate(
            """
            (keywords) => {
                for (const el of document.querySelectorAll('a, button, li > span, li > div')) {
                    const text = (el.textContent || '').toLowerCase().trim();
                    if (keywords.some(k => text.includes(k)) && el.offsetParent !== null) {
                        el.click();
                        return;
                    }
                }
            }
            """,
            [k.lower() for k in keywords_secao],
        )
        await self.page.wait_for_timeout(DELAY_ANIMACAO)

    async def _clicar_submenu(self, keywords_item: list[str], excluir_hrefs: list[str] | None = None) -> bool:
        """Dentro do submenu expandido, clica no item com as keywords.

        Exclui links cujo href contenha strings em excluir_hrefs (ex: 'modulo1').
        Aguarda 5 segundos após o clique.
        """
        excluir = excluir_hrefs or []
        clicou = await self.page.evaluate(
            """
            ([keywords, excluir]) => {
                for (const el of document.querySelectorAll('a')) {
                    const text = (el.textContent || '').toLowerCase().trim();
                    const href  = (el.href || '').toLowerCase();
                    const matchText = keywords.some(k => text.includes(k.toLowerCase()));
                    const excluido = excluir.some(e => href.includes(e.toLowerCase()));
                    if (matchText && !excluido && el.offsetParent !== null) {
                        el.click();
                        return el.href || text;
                    }
                }
                return null;
            }
            """,
            [[k.lower() for k in keywords_item], excluir],
        )
        if clicou:
            logger.info("Submenu clicado: %s → %s", keywords_item[0], clicou)
            await self._aguardar_pagina(keywords_item[0])
            return True
        return False

    async def _ir_prestador(self, item: str, excluir: list[str] | None = None) -> None:
        """Navega para: menu Área do Prestador → item do submenu."""
        logger.info("Navegando: Área do Prestador > %s", item)
        await self._expandir_secao_menu(["área do prestador", "prestador"])
        ok = await self._clicar_submenu([item], excluir_hrefs=excluir)
        if not ok:
            raise RuntimeError(f"Item '{item}' não encontrado no submenu Área do Prestador.")

    async def _ir_tomador(self, item: str) -> None:
        """Navega para: menu Área do Tomador → item do submenu (exclui modulo1)."""
        logger.info("Navegando: Área do Tomador > %s", item)
        await self._expandir_secao_menu(["área do tomador", "tomador"])
        ok = await self._clicar_submenu([item], excluir_hrefs=["modulo1"])
        if not ok:
            raise RuntimeError(f"Item '{item}' não encontrado no submenu Área do Tomador.")

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def login(self, login_str: str, senha: str) -> None:
        """Único page.goto do bot — ponto de entrada no sistema."""
        logger.info("Login: %s @ %s", login_str, self.municipio)
        await self.page.goto(f"{self.base_url}/login")
        await self._aguardar_pagina("Login")

        await self.page.check('input[name="tipo"][value="empresa"]')
        await self.page.fill("input#inscricao", login_str)
        await self.page.fill("input#senha", senha)

        await self.page.click('button[type="submit"]', timeout=60000)
        # Aguarda redirecionamento pós-login (networkidle é mais confiável aqui)
        try:
            await self.page.wait_for_url(
                lambda url: "/login" not in url and "/sessions" not in url,
                timeout=30000,
            )
        except Exception:
            pass
        await self.page.wait_for_load_state("networkidle", timeout=30000)
        await self.page.wait_for_timeout(DELAY_PAGINA)

        if "/login" in self.page.url or "/sessions" in self.page.url:
            raise RuntimeError(f"Login falhou para {login_str} em {self.municipio}")

        await self._fechar_modal_atencao()
        await self._screenshot("login_ok")
        logger.info("Login OK — URL: %s", self.page.url)

    async def _fechar_modal_atencao(self) -> None:
        """Fecha o modal 'ATENÇÃO' / 'Entendi' do dashboard, se presente."""
        try:
            for texto in ["Entendi", "Fechar", "OK", "Ciente"]:
                btn = self.page.locator(f'button:has-text("{texto}")')
                if await btn.count() > 0 and await btn.first.is_visible():
                    await btn.first.click()
                    await self.page.wait_for_timeout(400)
                    return
        except Exception:
            pass

    async def logout(self) -> None:
        try:
            await self._clicar_link(["sair", "logout", "encerrar sessão"], "Logout")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Filtro de competência (clique no formulário da página)
    # ------------------------------------------------------------------

    async def _aplicar_filtro_mes_ano(self, mes: int, ano: int) -> None:
        """Preenche os campos de filtro de mês/ano na página atual e clica em Filtrar."""
        await self.page.evaluate(
            """
            ([mes, ano]) => {
                // Tenta selects
                for (const sel of document.querySelectorAll('select:not([disabled])')) {
                    const opts = [...sel.options].map(o => parseInt(o.value)).filter(v => !isNaN(v));
                    if (opts.length === 0) continue;
                    if (opts.every(v => v >= 0 && v <= 12) && opts.length <= 13) {
                        sel.value = String(mes);
                        sel.dispatchEvent(new Event('change', {bubbles:true}));
                    } else if (opts.some(v => v >= 2000)) {
                        sel.value = String(ano);
                        sel.dispatchEvent(new Event('change', {bubbles:true}));
                    }
                }
                // Tenta inputs de texto (mes/ano)
                for (const inp of document.querySelectorAll('input[type="text"], input[type="number"]')) {
                    const name = (inp.name || inp.id || '').toLowerCase();
                    if (name.includes('mes') || name.includes('month')) {
                        inp.value = String(mes).padStart(2,'0');
                        inp.dispatchEvent(new Event('input', {bubbles:true}));
                    } else if (name.includes('ano') || name.includes('year')) {
                        inp.value = String(ano);
                        inp.dispatchEvent(new Event('input', {bubbles:true}));
                    }
                }
            }
            """,
            [mes, ano],
        )
        await self.page.wait_for_timeout(300)
        # Clica em Filtrar
        filtrou = await self._clicar_link(["filtrar", "pesquisar", "buscar", "aplicar"], "Filtrar")
        if not filtrou:
            # Tenta submit do formulário
            await self.page.evaluate("""
                () => {
                    const btn = document.querySelector('input[type="submit"], button[type="submit"]');
                    if (btn) btn.click();
                }
            """)
            await self._aguardar_pagina("Filtrar (submit)")

    # ------------------------------------------------------------------
    # Notas Fiscais
    # ------------------------------------------------------------------

    async def get_notas_mes_atual(self) -> list[dict]:
        """Acessa Prestador > Notas Fiscais via menu, filtra pela competência e coleta NFS-e."""
        mes, ano = self.mes_atual, self.ano_atual
        await self._ir_prestador("Notas Fiscais")
        await self._screenshot("notas_01_lista")

        await self._aplicar_filtro_mes_ano(mes, ano)
        await self._screenshot("notas_02_filtrado")

        all_rows: list[dict] = []
        while True:
            rows = await self._parse_notas_table()
            all_rows.extend(rows)
            # Próxima página
            next_link = self.page.locator(
                'a[rel="next"], .pagination a:has-text("›"), .pagination a:has-text("Próximo")'
            )
            if await next_link.count() > 0:
                await next_link.first.click()
                await self._aguardar_pagina("Notas — próxima página")
            else:
                break

        logger.info("get_notas_mes_atual — %d nota(s) encontrada(s)", len(all_rows))
        return all_rows

    async def _parse_notas_table(self) -> list[dict]:
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
        total = sum(
            _parse_brl(n.get("valor", "0"))
            for n in notas
            if "CANCELADA" not in n.get("situacao", "").upper()
        )
        return round(total, 2)

    # ------------------------------------------------------------------
    # Escriturações — Verificação
    # ------------------------------------------------------------------

    async def check_escrituracao_mes_atual(self) -> dict | None:
        """Acessa Prestador > Escriturações via menu e verifica se já existe para o mês."""
        mes, ano = self.mes_atual, self.ano_atual
        await self._ir_prestador("Escriturações")
        await self._screenshot("escrit_01_lista")
        return await self._find_escrituracao_in_table(mes, ano)

    async def _find_escrituracao_in_table(self, mes: int, ano: int) -> dict | None:
        mes_nome = MESES_PT[mes] if 1 <= mes <= 12 else ""
        patterns = [mes_nome, f"{mes:02d}/{ano}", f"{mes}/{ano}"]
        result = await self.page.evaluate(
            """
            ([patterns, ano]) => {
                for (const tr of document.querySelectorAll('table tbody tr')) {
                    const cells = [...tr.querySelectorAll('td')].map(td => td.textContent.trim());
                    const comp = (cells[0] || '').toUpperCase();
                    const anoStr = String(ano);
                    if (!patterns.some(p => p && comp.includes(p.toUpperCase()))) continue;
                    if (!comp.includes(anoStr)) continue;
                    const situacao = cells[3] || '';
                    if (situacao.toUpperCase().includes('CANCELADA')) continue;
                    const links = [...tr.querySelectorAll('a[href]')].map(a => ({href: a.href, text: a.textContent.trim()}));
                    return { cells, links, situacao, numero: cells[1] || '' };
                }
                return null;
            }
            """,
            [patterns, ano],
        )
        if not result:
            return None

        links = result["links"]
        decl_url = next((l["href"] for l in links if "/pdfs/declaracao" in l["href"]), None)
        boleto_list_url = next((l["href"] for l in links if "/modulo4/boletos" in l["href"]), None)
        imprimir_text = next((l["text"] for l in links if "imprimir" in l["text"].lower() or "/pdfs/" in l["href"]), None)

        notanumdec: str | None = None
        row_mes, row_ano = mes, ano

        if decl_url:
            params = parse_qs(urlparse(decl_url).query)
            notanumdec = params.get("notanumdec", [None])[0]
            row_mes = int(params.get("mes", [str(mes)])[0])
            row_ano = int(params.get("ano", [str(ano)])[0])

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

    # ------------------------------------------------------------------
    # Execução de Declaração — fluxo único (Prestador e Tomador)
    # ------------------------------------------------------------------

    async def _executar_declaracao(self, prefixo: str, tem_movimento: bool = False) -> str | None:
        """Fluxo padrão de declaração — igual para Prestador e Tomador:

        1. Clica em Nova Declaração
        1b. No modal: clica "Fechar Notas de Serviço" (com notas) ou "Declarar Sem Movimento" (sem notas)
        2. Seleciona mês de competência (mês anterior)
        3. Clica em Fechamento de Declaração
        4. Confirma o pop-up / box (OK)
        5. Clica em Imprimir / Salvar e retorna o caminho do PDF

        Aguarda a página carregar completamente antes de cada interação.
        """
        mes, ano = self.mes_atual, self.ano_atual
        filename = f"{prefixo}_{mes:02d}_{ano}.pdf"

        # ── 1. Nova Declaração ─────────────────────────────────────────
        logger.info("[%s] Passo 1 — clicando em Nova Declaração", prefixo)
        nova_btn = self.page.locator(
            'a:has-text("Nova Declaração"), button:has-text("Nova Declaração")'
        )
        await nova_btn.first.click()
        # Aguarda modal ou nova seção aparecer
        modal_sel = '.modal.show, .modal[style*="display: block"], .modal[style*="display:block"]'
        try:
            await self.page.wait_for_selector(modal_sel, timeout=5000)
            ctx = modal_sel
            logger.info("[%s] Modal detectado", prefixo)
        except Exception:
            ctx = "body"
            logger.info("[%s] Sem modal — usando body", prefixo)
        await self.page.wait_for_timeout(DELAY_ANIMACAO)
        await self._screenshot(f"{prefixo}_01_nova_decl")

        # ── 1b. Escolha no modal: Fechar Notas ou Declarar Sem Movimento ──
        if tem_movimento:
            opcao_keywords = ["fechar notas de serviço", "fechar notas", "fechar nota"]
            opcao_label = "Fechar Notas de Serviço"
        else:
            opcao_keywords = ["declarar sem movimento", "sem movimento"]
            opcao_label = "Declarar Sem Movimento"

        logger.info("[%s] Passo 1b — clicando em '%s'", prefixo, opcao_label)
        clicou_opcao = await self.page.evaluate(
            """
            ([ctx, keywords]) => {
                const root = ctx === 'body' ? document : (document.querySelector(ctx) || document);
                for (const el of root.querySelectorAll('a, button, input[type="submit"], input[type="button"]')) {
                    const text = (el.textContent || el.value || '').toLowerCase().trim();
                    if (keywords.some(k => text.includes(k)) && el.offsetParent !== null) {
                        el.click();
                        return el.textContent.trim() || true;
                    }
                }
                return false;
            }
            """,
            [ctx, opcao_keywords],
        )
        if clicou_opcao:
            logger.info("[%s] Opção '%s' clicada: %s", prefixo, opcao_label, clicou_opcao)
        else:
            logger.warning("[%s] Opção '%s' não encontrada no modal — prosseguindo sem ela", prefixo, opcao_label)
        await self.page.wait_for_timeout(DELAY_PAGINA)
        await self._screenshot(f"{prefixo}_01b_opcao_modal")

        # Reavalia contexto após clique na opção (pode ter aberto nova página/seção)
        try:
            await self.page.wait_for_selector(modal_sel, timeout=3000)
            ctx = modal_sel
        except Exception:
            ctx = "body"

        # ── 2. Seleciona mês de competência (mês anterior) ────────────
        logger.info("[%s] Passo 2 — selecionando competência %02d/%d", prefixo, mes, ano)
        MESES_NOME = ["", "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
                      "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
        selecionado = await self.page.evaluate(
            """
            ([mes, ano, ctx, mesesNome]) => {
                const root = ctx === 'body' ? document : (document.querySelector(ctx) || document);
                const log = [];
                const nomeMes = mesesNome[mes] || '';   // ex: "MAIO"

                function setSelect(sel, valor, isMes) {
                    // 1) valor numérico exato e zero-padded
                    const tentativas = [String(valor), String(valor).padStart(2, '0')];
                    for (const v of tentativas) {
                        if ([...sel.options].some(o => o.value === v)) {
                            sel.value = v;
                            sel.dispatchEvent(new Event('change', {bubbles: true}));
                            return 'num:' + v;
                        }
                    }
                    // 2) nome do mês em PT-BR (para selects com texto "MAIO", "JUNHO"...)
                    if (isMes && nomeMes) {
                        for (const o of sel.options) {
                            const txt = o.text.trim().toUpperCase();
                            const val = o.value.trim().toUpperCase();
                            if (txt === nomeMes || val === nomeMes) {
                                sel.value = o.value;
                                sel.dispatchEvent(new Event('change', {bubbles: true}));
                                return 'nome:' + o.value;
                            }
                        }
                    }
                    // 3) texto genérico igual ao valor
                    for (const o of sel.options) {
                        if (o.text.trim() === String(valor) || o.text.trim() === String(valor).padStart(2,'0')) {
                            sel.value = o.value;
                            sel.dispatchEvent(new Event('change', {bubbles: true}));
                            return 'txt:' + o.value;
                        }
                    }
                    return null;
                }

                function isMesSelect(sel) {
                    const id   = (sel.id   || '').toLowerCase();
                    const name = (sel.name || '').toLowerCase();
                    // Label associada
                    const label = sel.labels && sel.labels[0] ? sel.labels[0].textContent.toLowerCase() : '';
                    // Verifica por nome/id/label
                    if (id.includes('mes') || name.includes('mes') || label.includes('mês') || label.includes('mes')) return true;
                    if (id.includes('month') || name.includes('month')) return true;
                    if (id.includes('competencia') || name.includes('competencia')) return true;
                    // Heurística: opções numéricas de 1–12 (ou com nomes de meses)
                    const opts = [...sel.options].filter(o => o.value !== '');
                    if (opts.length >= 12 && opts.length <= 13) {
                        const nums = opts.map(o => parseInt(o.value)).filter(v => !isNaN(v));
                        if (nums.length >= 12 && nums.every(v => v >= 1 && v <= 12)) return true;
                    }
                    return false;
                }

                function isAnoSelect(sel) {
                    const id   = (sel.id   || '').toLowerCase();
                    const name = (sel.name || '').toLowerCase();
                    const label = sel.labels && sel.labels[0] ? sel.labels[0].textContent.toLowerCase() : '';
                    if (id.includes('ano') || name.includes('ano') || label.includes('ano')) return true;
                    if (id.includes('year') || name.includes('year')) return true;
                    // Heurística: opções >= 2000
                    const opts = [...sel.options].filter(o => o.value !== '');
                    const nums = opts.map(o => parseInt(o.value)).filter(v => !isNaN(v));
                    if (nums.length > 0 && nums.every(v => v >= 2000)) return true;
                    return false;
                }

                const selects = [...root.querySelectorAll('select:not([disabled])')];
                let mesFilled = false, anoFilled = false;

                // Primeira passagem: por nome/id/label (mais confiável)
                for (const sel of selects) {
                    if (!mesFilled && isMesSelect(sel)) {
                        const r = setSelect(sel, mes, true);
                        if (r !== null) { mesFilled = true; log.push('mes=' + r + ' (id=' + sel.id + ', name=' + sel.name + ')'); }
                    }
                }
                for (const sel of selects) {
                    if (!anoFilled && isAnoSelect(sel)) {
                        const r = setSelect(sel, ano, false);
                        if (r !== null) { anoFilled = true; log.push('ano=' + r + ' (id=' + sel.id + ', name=' + sel.name + ')'); }
                    }
                }

                // Segunda passagem: heurística para o que ficou faltando
                if (!mesFilled || !anoFilled) {
                    for (const sel of selects) {
                        const opts = [...sel.options].filter(o => o.value !== '');
                        // Detecta select de mês: opções numéricas 1-12 OU opções com nomes de meses PT
                        const nums = opts.map(o => parseInt(o.value)).filter(v => !isNaN(v));
                        const hasMesNome = opts.some(o => {
                            const t = o.text.trim().toUpperCase();
                            return ['JANEIRO','FEVEREIRO','MARÇO','ABRIL','MAIO','JUNHO',
                                    'JULHO','AGOSTO','SETEMBRO','OUTUBRO','NOVEMBRO','DEZEMBRO'].includes(t);
                        });
                        if (!mesFilled && (hasMesNome || (nums.length >= 12 && nums.every(v => v >= 0 && v <= 12)))) {
                            const r = setSelect(sel, mes, true);
                            if (r !== null) { mesFilled = true; log.push('mes_heuristica=' + r); }
                        } else if (!anoFilled && nums.some(v => v >= 2000)) {
                            const r = setSelect(sel, ano, false);
                            if (r !== null) { anoFilled = true; log.push('ano_heuristica=' + r); }
                        }
                    }
                }

                return { mesFilled, anoFilled, log };
            }
            """,
            [mes, ano, ctx, MESES_NOME],
        )
        logger.info("[%s] Passo 2 — resultado: %s", prefixo, selecionado)
        if not selecionado.get("mesFilled"):
            logger.warning("[%s] Passo 2 — MÊS não foi selecionado!", prefixo)
        if not selecionado.get("anoFilled"):
            logger.warning("[%s] Passo 2 — ANO não foi selecionado!", prefixo)
        await self.page.wait_for_timeout(DELAY_PAGINA)
        await self._screenshot(f"{prefixo}_02_mes_selecionado")

        # ── 3. Clica em CONTINUAR ─────────────────────────────────────
        # Ambos os fluxos passam por "Continuar" após selecionar o mês.
        # Com movimento: Continuar → página com "Confirmar Encerramento"
        # Sem movimento: Continuar / "Fechamento de Declaração" → popup de confirmação
        logger.info("[%s] Passo 3 — clicando em Continuar / Fechamento", prefixo)
        clicou3 = await self.page.evaluate(
            """
            ([ctx, keywords]) => {
                const root = ctx === 'body' ? document : (document.querySelector(ctx) || document);
                for (const el of root.querySelectorAll('a, button, input[type="submit"], input[type="button"]')) {
                    const text = (el.textContent || el.value || '').toLowerCase().trim();
                    const href  = (el.href || '').toLowerCase();
                    if (keywords.some(k => text.includes(k) || href.includes(k.replace(/ /g,'_')))
                        && el.offsetParent !== null) {
                        el.click();
                        return text;
                    }
                }
                return null;
            }
            """,
            [ctx, ["continuar", "fechamento de declaração", "fechamento da declaração", "fechamento"]],
        )
        if not clicou3:
            raise RuntimeError(f"[{prefixo}] Botão 'Continuar' não encontrado no passo 3.")
        logger.info("[%s] Passo 3 — clicado: '%s'", prefixo, clicou3)
        await self.page.wait_for_load_state("domcontentloaded")
        await self.page.wait_for_timeout(DELAY_PAGINA)
        await self._screenshot(f"{prefixo}_03_continuar")
        logger.info("[%s] Passo 3 — URL: %s", prefixo, self.page.url)

        # ── 4. Com movimento → clica "Confirmar Encerramento" ─────────
        #       Sem movimento → confirma popup/modal de fechamento
        if tem_movimento:
            logger.info("[%s] Passo 4 — clicando em Confirmar Encerramento", prefixo)
            clicou4 = await self.page.evaluate(
                """
                (keywords) => {
                    for (const el of document.querySelectorAll('a, button, input[type="submit"], input[type="button"]')) {
                        const text = (el.textContent || el.value || '').toLowerCase().trim();
                        if (keywords.some(k => text.includes(k)) && el.offsetParent !== null) {
                            el.click();
                            return text;
                        }
                    }
                    return null;
                }
                """,
                ["confirmar encerramento", "encerramento", "confirmar"],
            )
            if clicou4:
                logger.info("[%s] Passo 4 — clicado: '%s'", prefixo, clicou4)
                await self.page.wait_for_load_state("domcontentloaded")
                await self.page.wait_for_timeout(DELAY_PAGINA)
            else:
                logger.warning("[%s] Passo 4 — 'Confirmar Encerramento' não encontrado", prefixo)

            # ── 4b. Janela de confirmação pós-encerramento → clicar OK ─
            logger.info("[%s] Passo 4b — confirmando janela pós-encerramento (OK)", prefixo)
            self.page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
            await self.page.wait_for_timeout(1000)
            confirmou4b = False
            for sel_ok in [
                'button:has-text("OK")',
                'button:has-text("Ok")',
                'button:has-text("Confirmar")',
                'button:has-text("Fechar")',
                'button:has-text("Sim")',
                'input[type="submit"]',
                'button[type="submit"]',
            ]:
                btn = self.page.locator(sel_ok)
                if await btn.count() > 0 and await btn.first.is_visible():
                    await btn.first.click()
                    confirmou4b = True
                    logger.info("[%s] Passo 4b — confirmado via: %s", prefixo, sel_ok)
                    break
            if confirmou4b:
                await self.page.wait_for_load_state("domcontentloaded")
                await self.page.wait_for_timeout(DELAY_PAGINA)
            else:
                logger.info("[%s] Passo 4b — nenhuma janela extra encontrada", prefixo)
            await self._screenshot(f"{prefixo}_04b_ok_encerramento")
        else:
            logger.info("[%s] Passo 4 — verificando pop-up/box de confirmação", prefixo)
            self.page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
            await self.page.wait_for_timeout(1000)
            confirmou = False
            for sel_confirm in [
                'button:has-text("Confirmar")',
                'button:has-text("Sim")',
                'button:has-text("OK")',
                'input[type="submit"]',
                'button[type="submit"]',
            ]:
                btn = self.page.locator(sel_confirm)
                if await btn.count() > 0 and await btn.first.is_visible():
                    await btn.first.click()
                    confirmou = True
                    logger.info("[%s] Confirmou via: %s", prefixo, sel_confirm)
                    break
            if confirmou:
                await self.page.wait_for_load_state("domcontentloaded")
                await self.page.wait_for_timeout(DELAY_PAGINA)
            else:
                logger.info("[%s] Passo 4 — nenhum popup encontrado", prefixo)
        await self._screenshot(f"{prefixo}_04_confirmado")
        logger.info("[%s] Passo 4 — URL: %s", prefixo, self.page.url)

        # ── 5. Imprimir / Salvar PDF ───────────────────────────────────
        logger.info("[%s] Passo 5 — clicando em Imprimir / Salvar PDF", prefixo)
        path = await self._baixar_por_clique(
            ["imprimir declaração", "imprimir declaracao", "imprimir", "/pdfs/declaracao"],
            filename,
        )
        if path:
            logger.info("[%s] PDF salvo: %s", prefixo, path)
        else:
            logger.warning("[%s] Link de impressão não encontrado na página atual.", prefixo)
        await self._screenshot(f"{prefixo}_05_pdf")
        return path

    async def nova_declaracao_prestador(self, tem_movimento: bool = False) -> dict | None:
        """Prestador > Escriturações > executa os 5 passos de declaração.

        Args:
            tem_movimento: True se há NFS-e no período (clica "Fechar Notas de Serviço"),
                           False para declarar sem movimento.
        """
        mes, ano = self.mes_atual, self.ano_atual
        await self._ir_prestador("Escriturações")
        await self._screenshot("prestador_00_lista")
        await self._executar_declaracao("declaracao_prestador", tem_movimento=tem_movimento)
        return await self._find_escrituracao_in_table(mes, ano)

    # ------------------------------------------------------------------
    # Helpers de formulário de Nova Declaração
    # ------------------------------------------------------------------

    async def _abrir_nova_declaracao(self) -> str:
        """Clica em 'Nova Declaração' e retorna o seletor de contexto (modal ou 'body')."""
        nova_btn = self.page.locator(
            'a:has-text("Nova Declaração"), button:has-text("Nova Declaração")'
        )
        await nova_btn.first.click()
        await self.page.wait_for_timeout(DELAY_ANIMACAO)

        modal_sel = '.modal.show, .modal[style*="display: block"], .modal[style*="display:block"]'
        try:
            await self.page.wait_for_selector(modal_sel, timeout=4000)
            logger.info("_abrir_nova_declaracao — modal detectado")
            return modal_sel
        except Exception:
            logger.info("_abrir_nova_declaracao — sem modal, usando body")
            return "body"

    async def _selecionar_mes_ano_form(self, mes: int, ano: int, ctx: str = "body") -> None:
        """Seleciona mês e ano nos selects do contexto (modal ou body)."""
        await self.page.wait_for_timeout(400)
        # Reutiliza a mesma lógica robusta do passo 2 da declaração
        await self.page.evaluate(
            """
            ([mes, ano, ctx]) => {
                const root = ctx === 'body' ? document : (document.querySelector(ctx) || document);
                function setSelect(sel, valor) {
                    const tentativas = [String(valor), String(valor).padStart(2, '0')];
                    for (const v of tentativas) {
                        if ([...sel.options].some(o => o.value === v)) {
                            sel.value = v;
                            sel.dispatchEvent(new Event('change', {bubbles: true}));
                            return v;
                        }
                    }
                    for (const o of sel.options) {
                        if (o.text.trim() === String(valor) || o.text.trim() === String(valor).padStart(2,'0')) {
                            sel.value = o.value;
                            sel.dispatchEvent(new Event('change', {bubbles: true}));
                            return o.value;
                        }
                    }
                    return null;
                }
                const selects = [...root.querySelectorAll('select:not([disabled])')];
                let mesFilled = false, anoFilled = false;
                for (const sel of selects) {
                    const id = (sel.id || '').toLowerCase(), name = (sel.name || '').toLowerCase();
                    const label = sel.labels && sel.labels[0] ? sel.labels[0].textContent.toLowerCase() : '';
                    if (!mesFilled && (id.includes('mes') || name.includes('mes') || label.includes('mês') || label.includes('mes'))) {
                        if (setSelect(sel, mes) !== null) mesFilled = true;
                    }
                    if (!anoFilled && (id.includes('ano') || name.includes('ano') || label.includes('ano'))) {
                        if (setSelect(sel, ano) !== null) anoFilled = true;
                    }
                }
                if (!mesFilled || !anoFilled) {
                    for (const sel of selects) {
                        const opts = [...sel.options].filter(o => o.value !== '');
                        const nums = opts.map(o => parseInt(o.value)).filter(v => !isNaN(v));
                        if (!mesFilled && nums.length >= 12 && nums.every(v => v >= 0 && v <= 12)) {
                            if (setSelect(sel, mes) !== null) mesFilled = true;
                        } else if (!anoFilled && nums.some(v => v >= 2000)) {
                            if (setSelect(sel, ano) !== null) anoFilled = true;
                        }
                    }
                }
            }
            """,
            [mes, ano, ctx],
        )

    async def _confirmar_acao(self) -> None:
        """Confirma dialog nativo (confirm/alert) ou modal Bootstrap de confirmação."""
        self.page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
        await self.page.wait_for_timeout(800)
        for sel in ['button:has-text("Confirmar")', 'button:has-text("Sim")',
                    'button:has-text("OK")', 'button[type="submit"]']:
            btn = self.page.locator(sel)
            if await btn.count() > 0 and await btn.first.is_visible():
                await btn.first.click()
                await self._aguardar_pagina("Confirmação")
                return

    # ------------------------------------------------------------------
    # Downloads — por clique em links da página
    # ------------------------------------------------------------------

    async def _baixar_por_clique(self, keywords: list[str], filename: str) -> str | None:
        """Localiza link de impressão/download na página, clica e salva o arquivo.

        Suporta dois modos:
        - Download direto (arquivo baixado automaticamente pelo browser)
        - Popup / nova aba (PDF abre em nova aba; fecha após download)
        """
        filepath = os.path.join(self.download_dir, filename)

        # Encontra o href do link antes de clicar
        href = await self.page.evaluate(
            """
            (keywords) => {
                for (const el of document.querySelectorAll('a[href]')) {
                    const text = (el.textContent || '').toLowerCase().trim();
                    const href  = el.href.toLowerCase();
                    if (keywords.some(k => text.includes(k) || href.includes(k))) {
                        return el.href;
                    }
                }
                return null;
            }
            """,
            [k.lower() for k in keywords],
        )

        if not href:
            logger.warning("_baixar_por_clique — link não encontrado para: %s", keywords)
            return None

        logger.info("_baixar_por_clique — clicando em: %s → %s", keywords[0], href)

        # Tenta capturar como download de arquivo
        try:
            async with self.page.expect_download(timeout=15000) as dl_info:
                await self.page.evaluate(
                    "(href) => { const a = document.querySelector(`a[href='${href}']`) || [...document.querySelectorAll('a')].find(el => el.href === href); if (a) a.click(); }",
                    href,
                )
            download = await dl_info.value
            await download.save_as(filepath)
            logger.info("Download salvo: %s", filepath)
            return filepath
        except Exception:
            pass

        # Tenta capturar como popup/nova aba
        try:
            async with self.page.expect_popup(timeout=10000) as popup_info:
                await self.page.evaluate(
                    "(href) => { const a = [...document.querySelectorAll('a')].find(el => el.href === href); if (a) a.click(); }",
                    href,
                )
            popup = await popup_info.value
            await popup.wait_for_load_state("domcontentloaded", timeout=15000)
            await popup.wait_for_timeout(2000)
            popup_url = popup.url
            content_type = ""
            try:
                # Baixa o conteúdo via request usando cookies da sessão
                resp = await self._context.request.get(popup_url)
                content_type = resp.headers.get("content-type", "")
                if resp.ok and ("pdf" in content_type or len(await resp.body()) > 1000):
                    with open(filepath, "wb") as f:
                        f.write(await resp.body())
                    logger.info("PDF via popup salvo: %s", filepath)
                    await popup.close()
                    return filepath
            except Exception:
                pass
            await popup.close()
        except Exception as exc:
            logger.warning("_baixar_por_clique — popup falhou: %s", exc)

        return None

    async def download_declaracao(
        self,
        mes: int,
        ano: int,
        notanumdec: str,
        full_url: str | None = None,
    ) -> str | None:
        """Clica em 'Imprimir Declaração' na tabela de escriturações e baixa o PDF."""
        filename = f"declaracao_{mes:02d}_{ano}_{notanumdec}.pdf"

        # Tenta clicar no link de imprimir da linha da tabela
        path = await self._baixar_por_clique(
            ["imprimir declaração", "imprimir declaracao", "/pdfs/declaracao"],
            filename,
        )
        if path:
            return path

        # Fallback: usa o URL que já conhecemos (via request, sem page.goto)
        if full_url:
            try:
                resp = await self._context.request.get(full_url)
                ct = resp.headers.get("content-type", "")
                if resp.ok and "pdf" in ct.lower():
                    fp = os.path.join(self.download_dir, filename)
                    with open(fp, "wb") as f:
                        f.write(await resp.body())
                    logger.info("Declaração (fallback request): %s", fp)
                    return fp
            except Exception as exc:
                logger.warning("download_declaracao fallback falhou: %s", exc)

        return None

    async def download_boletos_escrituracao(self, mes: int, ano: int) -> list[str]:
        """Clica no ícone 'Lista de Boletos da Competência' na linha da escrituração
        e baixa todos os boletos disponíveis na página seguinte.

        Deve ser chamado quando a página atual já está em Prestador > Escriturações.
        """
        logger.info("download_boletos_escrituracao — buscando ícone de boleto na linha %02d/%d", mes, ano)
        mes_nome = MESES_PT[mes] if 1 <= mes <= 12 else ""
        patterns = [mes_nome, f"{mes:02d}/{ano}", f"{mes}/{ano}"]

        # Clica no ícone de boleto (primeiro ícone/link) da linha correspondente ao mês
        href_boleto_lista = await self.page.evaluate(
            """
            ([patterns, ano]) => {
                const anoStr = String(ano);
                for (const tr of document.querySelectorAll('table tbody tr')) {
                    const cells = [...tr.querySelectorAll('td')].map(td => td.textContent.trim());
                    const comp = (cells[0] || '').toUpperCase();
                    if (!patterns.some(p => p && comp.includes(p.toUpperCase()))) continue;
                    if (!comp.includes(anoStr)) continue;
                    // Procura link com "boleto" no href ou title/tooltip contendo "boleto"
                    const links = [...tr.querySelectorAll('a[href]')];
                    for (const a of links) {
                        const href  = (a.href  || '').toLowerCase();
                        const title = (a.title || a.getAttribute('data-original-title') || a.textContent || '').toLowerCase();
                        if (href.includes('boleto') || title.includes('boleto') || title.includes('lista')) {
                            return a.href;
                        }
                    }
                    // Fallback: primeiro ícone da linha (costuma ser o de boleto)
                    if (links.length > 0) return links[0].href;
                }
                return null;
            }
            """,
            [patterns, ano],
        )

        if not href_boleto_lista:
            logger.warning("download_boletos_escrituracao — ícone de boleto não encontrado na linha")
            return []

        logger.info("download_boletos_escrituracao — clicando em lista de boletos: %s", href_boleto_lista)

        # Clica no link e aguarda a página de boletos carregar
        await self.page.evaluate(
            "(href) => { const a = [...document.querySelectorAll('a')].find(el => el.href === href); if (a) a.click(); }",
            href_boleto_lista,
        )
        await self._aguardar_pagina("Lista de Boletos da Competência")
        await self._screenshot("boletos_escrituracao_01_lista")
        logger.info("download_boletos_escrituracao — URL: %s", self.page.url)

        # Verifica se há registros na página
        tem_registros = await self.page.evaluate("""
            () => {
                const rows = document.querySelectorAll('table tbody tr');
                // Ignora linha de "nenhum registro"
                if (rows.length === 0) return false;
                const texto = (rows[0].textContent || '').toLowerCase();
                if (texto.includes('nenhum') || texto.includes('não há') || texto.includes('sem registro')) return false;
                return true;
            }
        """)

        if not tem_registros:
            logger.info("download_boletos_escrituracao — nenhum boleto disponível para %02d/%d", mes, ano)
            return []

        # Coleta todos os links "Imprimir Boleto" da página
        boleto_hrefs = await self.page.evaluate("""
            () => {
                const hrefs = [];
                document.querySelectorAll('table tbody tr').forEach((tr, i) => {
                    // Ignora linhas pagas ou canceladas
                    const rowText = tr.textContent.toLowerCase();
                    if (rowText.includes('pago') || rowText.includes('cancelad')) return;
                    // Busca link de imprimir boleto
                    for (const a of tr.querySelectorAll('a[href]')) {
                        const href  = (a.href  || '').toLowerCase();
                        const title = (a.title || a.getAttribute('data-original-title') || a.textContent || '').toLowerCase();
                        if (href.includes('boleto') || title.includes('imprimir') || title.includes('boleto')) {
                            hrefs.push({ href: a.href, idx: i });
                            break;
                        }
                    }
                });
                return hrefs;
            }
        """)

        downloaded: list[str] = []
        for item in boleto_hrefs:
            filename = f"boleto_iss_{mes:02d}_{ano}_{item['idx'] + 1}.pdf"
            path = await self._baixar_por_clique(
                ["imprimir boleto", "boleto", item["href"].lower()[-40:]],
                filename,
            )
            if path:
                downloaded.append(path)
                logger.info("download_boletos_escrituracao — boleto salvo: %s", path)
            else:
                logger.warning("download_boletos_escrituracao — falhou ao baixar boleto idx=%d", item["idx"])

        logger.info("download_boletos_escrituracao — %d boleto(s) baixado(s)", len(downloaded))
        return downloaded

    async def download_boletos_iss(self, mes: int, ano: int) -> list[str]:
        """Prestador > Boletos via menu → filtra mes/ano → baixa boletos ISS."""
        await self._ir_prestador("Boletos")
        await self._screenshot("boletos_01_lista")

        await self._aplicar_filtro_mes_ano(mes, ano)
        await self._screenshot("boletos_02_filtrado")

        # Coleta linhas de boletos ISS em aberto
        boleto_rows = await self.page.evaluate("""
            () => {
                const rows = [];
                document.querySelectorAll('table tbody tr').forEach(tr => {
                    const cells = [...tr.querySelectorAll('td')].map(td => td.textContent.trim());
                    const link = tr.querySelector('a[href*="/pdfs/"][href*="boleto"]');
                    if (!link) return;
                    rows.push({
                        tributo:   cells[4] || '',
                        situacao:  cells[10] || '',
                        href: link.href,
                    });
                });
                return rows;
            }
        """)

        downloaded: list[str] = []
        for i, row in enumerate(boleto_rows):
            if "ISS" not in row.get("tributo", "").upper():
                continue
            situacao = row.get("situacao", "").upper()
            if any(s in situacao for s in ("PAGO", "CANCELADA")):
                continue
            filename = f"boleto_iss_{mes:02d}_{ano}_{i+1}.pdf"
            # Clica no link de impressão do boleto
            path = await self._baixar_por_clique(
                [row["href"].lower()[-30:], "imprimir boleto", "/pdfs/"],
                filename,
            )
            if path:
                downloaded.append(path)

        if not downloaded:
            logger.info("Nenhum boleto ISS disponível para %02d/%d", mes, ano)

        return downloaded

    async def download_situacional(self) -> str | None:
        """Clica em 'Situacional' no menu lateral e baixa o PDF."""
        filename = f"situacional_{self.mes_atual:02d}_{self.ano_atual}.pdf"

        # Tenta clicar no menu "Situacional" / "Relatório Situacional"
        path = await self._baixar_por_clique(
            ["situacional", "relatório situacional", "relatorio situacional"],
            filename,
        )
        if path:
            return path

        # Fallback: procura link na página atual
        await self._clicar_link(
            ["situacional", "relatório situacional"],
            "Situacional",
        )
        path = await self._baixar_por_clique(
            ["situacional", "imprimir", "download"],
            filename,
        )
        return path

    # ------------------------------------------------------------------
    # Área do Tomador — Nova Declaração (mesmo fluxo do Prestador)
    # ------------------------------------------------------------------

    async def fechar_escrituracoes_tomador(self) -> list[str]:
        """Tomador > Escriturações → executa os mesmos 5 passos de declaração.

        Retorna lista de arquivos baixados (declaração PDF do tomador).
        """
        # ── Navega para Tomador > Escriturações pelo menu ──────────────
        await self._ir_tomador("Escrituração")
        await self._screenshot("tomador_00_lista")
        logger.info("fechar_escrituracoes_tomador — URL: %s", self.page.url)

        # ── Executa os 5 passos (igual ao Prestador) ───────────────────
        path = await self._executar_declaracao("tomador_declaracao")

        downloaded: list[str] = []
        if path:
            downloaded.append(path)

        logger.info("fechar_escrituracoes_tomador — concluído, %d arquivo(s)", len(downloaded))
        return downloaded

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------

    async def screenshot_erro(self, nome: str = "erro") -> str:
        """Tira screenshot da página atual e salva em download_dir."""
        path = os.path.join(self.download_dir, f"{nome}.png")
        try:
            await self.page.screenshot(path=path, full_page=True)
            logger.info("Screenshot de erro salvo: %s", path)
        except Exception as exc:
            logger.warning("Não foi possível tirar screenshot: %s", exc)
            return ""
        return path
