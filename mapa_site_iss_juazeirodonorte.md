# Mapa Completo do Site — ISS Eletrônico Juazeiro do Norte
**URL Base:** `https://iss.speedgov.com.br/juazeirodonorte/`
**Sistema:** SpeedGov / Intersol Soluções — ISS Eletrônico Municipal
**Contribuinte logado (sessão de exemplo):** DF MEDICINA APLICADA LTDA | Inscrição 1568190 | CNPJ 40.620.996/0001-52 | Tipo: EMPRESA | Simples: NÃO | Data Limite: 31/03/3000

---

## 1. TELA DE LOGIN
**URL:** `https://iss.speedgov.com.br/juazeirodonorte/login`
**Título:** ISS ELETRÔNICO — PREFEITURA MUNICIPAL JUAZEIRO DO NORTE
**Form action:** `POST /juazeirodonorte/sessions`

### Campos
| Campo | Tipo | name | id | Placeholder / Notas |
|---|---|---|---|---|
| Tipo de usuário | radio | `tipo` | `tipo` | value="empresa" (padrão: selecionado) |
| Tipo de usuário | radio | `tipo` | `tipo` | value="contador" |
| Inscrição / CNPJ / CPF | text | `inscricao` | `inscricao` | "Inscrição ou CNPJ ou CPF" |
| Senha | password | `senha` | `senha` | "Senha" |
| Token CSRF | hidden | `authenticity_token` | — | Preenchido automaticamente |
| Entrar | submit button | — | — | class="btn btn-block btn-primary mt-3" |

### Links Extras
- **Recuperar senha:** `GET /juazeirodonorte/recupera`

### Seletores CSS-chave
```
input#inscricao        → campo de login
input#senha            → campo de senha
input[name="tipo"]     → radio Empresa/Autônomo ou Contador
button[type="submit"]  → botão Entrar
a[href*="recupera"]    → link "Recuperar senha"
```

---

## 2. CABEÇALHO (top bar) — presente em todas as telas logadas
Dados exibidos na navbar superior (não editáveis na interface, lidos da sessão):

| Campo | Valor Exemplo | Seletor |
|---|---|---|
| Inscrição | 1568190 | `nav li:nth-child(1) span` / ref_10 |
| Nome / Razão Social | DF MEDICINA APLICADA LTDA... | ref_12 |
| CNPJ | 40.620.996/0001-52 | ref_14 |
| Tipo | EMPRESA | ref_16 |
| Simples Nacional | NÃO | ref_18 |
| Data Limite | 31/03/3000 | ref_20 |

---

## 3. DASHBOARD — PÁGINA INICIAL
**URL:** `https://iss.speedgov.com.br/juazeirodonorte/`
**Título da página:** Página Inicial

### Cards de Resumo
| Card | Valor | Seletor |
|---|---|---|
| Boletos Abertos | 64 | `[ref_69]` / card azul |
| Notas Recusadas | 0 | `[ref_70]` / card vermelho |

### Seções
- **Últimas Mensagens Recebidas** — tabela com link para cada mensagem
  - URL de mensagem individual: `/juazeirodonorte/mensagens/TIMESTAMP`
  - Link "Outras mensagens...": `/juazeirodonorte/mensagens`
- **Importante!** — aviso vermelho da prefeitura (link para decreto PDF externo)
- **Data Limite de Encerramento 2026** — tabela mês a mês (Janeiro → Dezembro + Jan/2027)

### Modal "ATENÇÃO" (exibido no carregamento)
- Botão de fechar: `button "Entendi"` — `[ref_126]`

---

## 4. MENU LATERAL (sidebar)
Presente em todas as telas. Seletor do container: `aside` / `complementary [ref_26]`

```
Menu Principal
├── Área do Prestador         href="#item1"
│   ├── Notas Fiscais         /modulo1/notas?...
│   ├── Escriturações         /modulo1/escrituracoes?...
│   └── Notas Recusadas       /modulo1/recusadas
│
├── Área do Tomador           href="#item3"
│   ├── Escrituração          /module3/escrituracoes?...
│   ├── Notas Recebidas       /module3/recebidas?...
│   ├── Notas Recebidas pelo ADN  /module3/recebidas_adn
│   ├── Notas Tomadas Declaradas  /module3/tomadas_declaradas
│   └── Enviar Remessa        /module3/enviadas
│
├── Mensagens                 href="#item9"
│   └── Caixa Postal          /mensagens
│
├── Boletos                   href="#item4"  [badge: 64]
│   ├── Boletos Abertos       /modulo4/boletos?...
│   ├── Boletos Pagos         /modulo4/boletos?...
│   ├── Gerar Boleto por Nota /modulo4/boletos_por_nota
│   └── Resumo Anual          /modulo4/boletos_por_ano
│
├── Obras                     href="#item5"
│   ├── Minhas Obras          /obras/minhas
│   └── Cadastro de Obras     /obras
│
├── Relatórios                href="#item6"
│   ├── Relatório Situacional /pdfs/situacional         [gera PDF direto]
│   ├── Comprovante de Inscrição /pdfs/comprovante      [gera PDF direto]
│   └── Livro de Registros    /module6/livro_de_registros
│
├── Configurações             href="#item7"
│   ├── Alterar Senha         /module5/senha
│   ├── Contador/Procurador   /module5/contador
│   └── Logomarca             /module5/logomarca
│
├── WebService                href="#item8"
│   └── Versão 1.0            href="#versao1"
│       ├── Lista de Lotes    /lotes
│       ├── Documentação      /modulo2/documentacao
│       └── Downloads         /module5/downloads
│
└── Sair                      /juazeirodonorte/logout
```

---

## 5. ÁREA DO PRESTADOR

### 5.1 Notas Fiscais (Lista)
**URL:** `/juazeirodonorte/modulo1/notas` (com params de filtro)
**Título:** Nota Fiscal de Serviço — Lista de notas fiscais emitidas

#### Botões de ação (topo direito)
| Botão | Ação | URL |
|---|---|---|
| Nova Nota | Abre form de emissão | `/nota_nacional/new` |
| Exportar PDF | Gera PDF filtrado | `/modulo1/pdf_notas?...` |
| Exportar Excel | Gera .xls filtrado | `/modulo1/notas.xls?...` |

#### Filtros (collapsible "FILTROS")
| Campo | Tipo | name / seletor | Opções |
|---|---|---|---|
| Data Inicial | date text | `q[nfedataini_gteq]` | — |
| Data Final | date text | `q[nfedatafim_lteq]` | — |
| Nome ou CPF ou CNPJ | text | `q[...]` | — |
| Número | text | `q[nfenum_eq]` | — |
| Número do RPS | text | `q[...]` | — |
| Número Nota Nacional | text | `q[...]` | — |
| Situação da Nota | select `[ref_24]` | `q[nfetrib_eq]` | T / G / I / M / J / A |
| Retida? | select `[ref_25]` | `q[...]` | SIM(1) / NÃO(2) |
| Status da Nota | select `[ref_26]` | `q[nfestat_eq]` | ABERTA(A) / FECHADA(F) / CANCELADA(C) |
| Mês Competência | select `[ref_27]` | `q[nfecompmes_eq]` | 1–12 (JANEIRO–DEZEMBRO) |
| Ano Competência | select `[ref_28]` | `q[nfecompano_eq]` | 2000–2026 |
| Situação no Tomador | select `[ref_29]` | `q[...]` | DECLARADA(D) / NÃO DECLARADA(N) |
| Filtrar | submit `[ref_30]` | — | — |
| Todas as Notas | button `[ref_31]` | — | Remove filtro de mês/ano |

#### Colunas da tabela
`#` | `Data` | `Competência` | `Doc. Tomador` | `Nome Tomador` | `Valor` | `Retida` | `Situação` | `Valor ISS` | `Nº Nacional` | `Nota Nacional?`

#### Botões por linha (ações)
| Ícone | Ação | URL padrão |
|---|---|---|
| Imprimir | PDF da nota | `/pdfs/{id}/notafiscal` |
| Substituir | Nova nota substituta | `/nota_nacional/new?subs_id={id}` |
| Copiar | Cópia da nota | `/nota_nacional/new?copy_id={id}` |
| XML | Download XML | `/modulo1/{id}/xml` |
| E-mail | Enviar por e-mail | `/modulo1/{id}/email` |
| Cancelar | Cancela a nota | `/modulo1/{id}/cancela` |
| Imprimir Nota Nacional | PDF ADN | button inline |

---

### 5.2 Nova Nota Fiscal (Formulário de Emissão)
**URL:** `/juazeirodonorte/nota_nacional/new`
**Título:** Nota Fiscal de Serviço — Emissão de nota fiscal de serviço

#### Seção: Identificação da NFS-e
| Campo | Tipo | Seletor | Notas |
|---|---|---|---|
| Data de Emissão | date `[ref_16]` | `input[type=date]` | Pré-preenchido com data atual |
| Mês Competência | select `[ref_17]` | — | Jan–Dez (valores 1–12) |
| Ano Competência | number `[ref_18]` | — | Ex: 2026 |
| Número do RPS | text `[ref_19]` | — | Opcional |
| Data do RPS | text `[ref_20]` | — | Opcional |
| Situação Simples Nacional | select `[ref_21]` | — | Não optante / MEI / ME-EPP |
| Regime Especial Tributação | select `[ref_22]` | — | 0-Nenhum / 1-Cooperativa / ... / 6-Sociedade Profissionais |
| Informar Série e Número da DPS | checkbox `[ref_23]` | — | Expande campos Série e Número da DPS |

#### Seção: Tomador do Serviço
| Campo | Tipo | Seletor | Notas |
|---|---|---|---|
| Localização do tomador | radio `[ref_24/25/26]` | — | "Tomador não informado" / "Brasil" / "Exterior" |
| CPF/CNPJ * | text `[ref_27]` | — | Pressione TAB para consultar |
| Nome/Razão Social * | text `[ref_28]` | — | Preenchido ao consultar CNPJ |
| Insc. Estadual | text `[ref_29]` | — | |
| Insc. Municipal | text `[ref_30]` | — | |
| Telefone | text `[ref_31]` | — | |
| Tipo * (logradouro) | text `[ref_32]` | — | Ex: Rua, Av |
| Logradouro * | text `[ref_33]` | — | |
| Número * | text `[ref_34]` | — | |
| Complemento | text `[ref_35]` | — | |
| Bairro * | text | — | |
| Cidade * | text | — | Autocomplete |
| UF * | text | — | |
| CEP * | text | — | 8 dígitos |
| E-mail | text | — | |
| (se Exterior) NIF, motivo, endereço completo | — | — | Campos condicionais |

#### Seção: Intermediário do Serviço
- Radio: Intermediário não informado / Brasil / Exterior
- Campos idênticos ao Tomador quando Brasil/Exterior selecionado

#### Seção: Serviço Prestado
| Campo | Tipo | Notas |
|---|---|---|
| Histórico/Descrição do Serviço * | textarea | "Descreva o serviço prestado..." |
| Serviço (Código Tributação Municipal) * | select2 | "Selecione o serviço..." |
| Código Tributação Nacional * | select2 | "Selecione o código..." |
| Código NBS * | select2 | Nomenclatura Brasileira de Serviços |
| Tributação ISSQN | select | Operação tributável / Suspensa / etc. |
| ISS Retido | select | Não retido / Retido |
| Alíquota ISS (%) * | number | |
| Valor do Serviço (R$) * | number | |
| Dedução (R$) | number | |
| Desconto Incondicionado (R$) | number | |
| Desconto Condicionado (R$) | number | |

#### Seção: Local da Prestação
| Campo | Tipo | Notas |
|---|---|---|
| Município Emissor | select | Pré-preenchido: JUAZEIRO DO NORTE-CE |
| Município Prestação do Serviço * | select | "Selecione o município..." |
| País da Prestação do Serviço | select | Default: Brasil |

#### Seção: Tributos Federais (PIS/COFINS)
| Campo | Tipo | Notas |
|---|---|---|
| Situação Tributária PIS/COFINS | select | 00-Nenhum / demais CSTs |
| Base de Cálculo (R$) | number | |
| Tipo de Retenção | select | PIS/COFINS/CSLL Não Retidos / Retidos |
| Alíquota PIS (%) | number | Ex: 0.65 |
| Valor PIS (R$) | number (readonly) | |
| Alíquota COFINS (%) | number | Ex: 3.00 |
| Valor COFINS (R$) | number (readonly) | |
| Retenção CP/INSS (R$) | number | |
| Retenção IRRF (R$) | number | |
| Retenção CSLL (R$) | number | |

#### Seção: Informações Complementares (opcionais — collapsible)
Checkboxes para expandir sub-seções:
- **Benefício Fiscal Municipal** → Tipo de Benefício, Número do Benefício (14 dígitos)
- **Informações de Obra** → dados do ART/obra
- **Suspensão de Exigibilidade** → processo judicial/administrativo
- **Reembolso/Repasse** → dados do reembolso
- **Comércio Exterior** → campos internacionais
- **IBS/CBS (Reforma Tributária)** → campos da reforma tributária

#### Botão de envio
`button "Confirmar emissão da Nota Nacional"` → POST para `/nota_nacional`

---

### 5.3 Escriturações do Prestador (Lista)
**URL:** `/juazeirodonorte/modulo1/escrituracoes`
**Título:** Área de Escrituração do Prestador — Lista de escriturações

#### Botões de ação
| Botão | URL |
|---|---|
| Nova Declaração | abre modal/form inline |
| Exportar PDF | `/modulo1/pdf_escrituracoes?...` |

#### Filtros
| Campo | Tipo | Opções |
|---|---|---|
| Mês Competência `[ref_20]` | select | Jan–Dez |
| Ano Competência `[ref_21]` | select | 2000–2026 |
| Situação da Declaração `[ref_22]` | select | ABERTA(A) / FECHADA(F) / CANCELADA(C) / PENDENTE(P) |
| Filtrar `[ref_23]` | submit | |
| Limpar Filtro `[ref_24]` | button | |

#### Colunas da tabela
`Competência` | `Número` | `Possui Movimento?` | `Situação` | `Data Fechamento` | `Adicional` | `ISS Calculado` | `ISS Devido`

#### Botões por linha
| Botão | URL |
|---|---|
| Lista de boletos da competência | `/modulo4/boletos?q[pclmesref_eq]={mes}&...` |
| Imprimir declaração | `/pdfs/declaracao?mes={m}&ano={a}&notanumdec={n}&tipo=P&notatipdecl=N` |
| Imprimir Certificado | `/modulo1/certificados?mes={m}&ano={a}&notanumdec={n}` |
| Lista de Notas da Declaração | `/modulo1/declaracao_notas?q[notames_eq]={m}&...` |

---

### 5.4 Notas Recusadas
**URL:** `/juazeirodonorte/modulo1/recusadas`
**Título:** Nota Fiscal de Serviço — RECUSADAS
**Aviso:** Banner laranja — "As notas listadas abaixo foram rejeitadas pelo tomador de serviço e devem ser canceladas."

#### Filtros
| Campo | Tipo |
|---|---|
| Número | text |
| Mês Competência | select |
| Ano Competência | select |
| Filtrar / Todas as Notas | buttons |

#### Colunas da tabela
`#` | `Data` | `Competência` | `Doc. Tomador` | `Nome Tomador` | `Valor` | `Retida` | `Situação` | `Valor ISS`

#### Botões por linha
- Imprimir PDF
- Cancelar nota (ícone vermelho)

---

## 6. ÁREA DO TOMADOR

### 6.1 Escrituração do Tomador (Lista)
**URL:** `/juazeirodonorte/module3/escrituracoes`
**Título:** Área de Escrituração — Lista de escriturações
Estrutura idêntica ao Prestador (5.3), com variações:
- Exportar PDF: `/module3/pdf_escrituracoes?...`
- Botões por linha (sem Imprimir Certificado, sem campo Adicional como ação)

#### Colunas
`Competência` | `Número` | `Possui Movimento?` | `Situação` | `Data Fechamento` | `Adicional` | `ISS Calculado` | `ISS Devido`

---

### 6.2 Notas Recebidas
**URL:** `/juazeirodonorte/module3/recebidas`
**Título:** Notas Fiscais de Serviços Recebidas — Lista de notas fiscais recebidas pelo tomador

#### Botões de ação
| Botão | URL |
|---|---|
| Declarar Notas | button (abre modal de declaração) |
| Exportar PDF | `/module3/pdf_notas?...` |
| Exportar Excel | `/module3/recebidas.xls?...` |

#### Filtros
| Campo | Tipo | Seletor | Opções |
|---|---|---|---|
| Data Inicial | text `[ref_21]` | — | — |
| Data Final | text `[ref_22]` | — | — |
| Número | text `[ref_23]` | — | — |
| Número Nota Nacional | text `[ref_24]` | — | — |
| Número do RPS | text `[ref_25]` | — | — |
| Nota Aceita? | select `[ref_26]` | — | Pendente(P) / Aceita(A) / Recusada(R) / Não Incidente(N) |
| Situação Pelo Prestador | select `[ref_27]` | — | DECLARADA(D) / NÃO DECLARADA(N) |
| Mês Competência | select `[ref_28]` | — | Jan–Dez |
| Ano Competência | select `[ref_29]` | — | 2000–2026 |
| Nome do Prestador | text `[ref_30]` | — | — |
| Situação Pelo Tomador | select `[ref_31]` | — | DECLARADA(D) / NÃO DECLARADA(N) |

#### Colunas da tabela
`#` | `Data` | `Competência` | `Doc. Prestador` | `Nome Prestador` | `Tributação` | `Valor` | `Retida` | `Situação` | `Nº Nacional` | `Nota Nacional?` | `Valor ISS` | `Situação Aceite` | `Declarada Tomador`

**Legenda:** E = Nota Eletrônica | A = Nota Avulsa

---

### 6.3 Notas Recebidas pelo ADN
**URL:** `/juazeirodonorte/module3/recebidas_adn`
**Título:** Notas Fiscais de Serviços Recebidas pelo ADN (Ambiente de Dados Nacional)

#### Botão de ação
`Declarar Notas Eletrônicas` | Exportar Excel

#### Filtros
| Campo | Tipo |
|---|---|
| Data Inicial | text |
| Data Final | text |
| Número DPS | text |
| Número Nota Nacional | text |
| Nota Aceita? | select |
| Mês Competência | select |
| Ano Competência | select |
| Nome do Prestador | text |

#### Colunas da tabela
`#` | `Data` | `Competência` | `Doc. Prestador` | `Nome Prestador` | `Tributação` | `Retida` | `Nº Nacional` | `Nota Nacional?` | `Valor Base Cálculo` | `Valor Líquido` | `Valor ISS` | `Situação Aceite` | `Declarada Tomador`

---

### 6.4 Notas Tomadas Declaradas
**URL:** `/juazeirodonorte/module3/tomadas_declaradas`
**Título:** Notas Fiscais de Serviços Tomadas e Declaradas

#### Filtros
| Campo | Tipo |
|---|---|
| Razão Social | text |
| CPF/CNPJ | text |
| Número da Nota | text |
| Forma de Entrada | select |
| Retida? | select |
| Data Inicial | text |
| Data Final | text |
| Mês Competência | select |
| Ano Competência | select |

#### Colunas da tabela
`#` | `Nome do Prestador` | `Documento` | `Data de Emissão` | `Competência` | `Número` | `Forma Entrada` | `Retida` | `Serviço` | `Alíquota` | `Valor Faturado` | `Valor ISS`

#### Exportação
- Exportar PDF | Exportar Excel (topo direito)

---

### 6.5 Enviar Remessa
**URL:** `/juazeirodonorte/module3/enviadas`
**Título:** Minhas Remessas — Lista de Remessas Enviadas

#### Botão de ação
`Enviar Remessa` (topo direito) → abre formulário de upload de XML

#### Informação exibida
- Card: "Documentação para envio de XML" — link para `/modulo2/documentacao`

#### Colunas da tabela
`Ano` | `Mês` | `#` | `Data` | `Descrição` | `Tipo` | `Situação`

---

## 7. MENSAGENS

### 7.1 Caixa Postal (Lista)
**URL:** `/juazeirodonorte/mensagens`
**Título:** Mensagens — Lista de mensagens

#### Botão de ação
`Nova Mensagem` → `/juazeirodonorte/mensagens/new`

#### Itens listados (cada mensagem)
- **Assunto** (link clicável)
- **Enviado Por:** nome do remetente
- **Prévia** do texto
- **Data relativa** (ex: "a 2 meses")
- URL de detalhe: `/mensagens/TIMESTAMP` (ex: `/mensagens/2026-03-10%2007:52:44`)

---

## 8. BOLETOS

### 8.1 Boletos Abertos / Boletos Pagos (Lista)
**URL:** `/juazeirodonorte/modulo4/boletos` (com params de filtro)
**Título:** Meus Boletos — Lista de boletos

#### Filtros
| Campo | Tipo | Seletor | Opções |
|---|---|---|---|
| Tributo | select `[ref_17]` | — | AMAJU / ASA / CEMIT / ... / ISS / TFE / TVS / TX / ... (60+ tipos) |
| Ano Competência | select `[ref_18]` | — | 2000–2026 |
| Mês Competência | select `[ref_19]` | — | Jan–Dez |
| Situação | select `[ref_20]` | — | ABERTO(A) / PAGO(F) / PARCELADO(G) |
| Filtrar | submit `[ref_21]` | — | — |

#### Colunas da tabela
`#Crédito` | `#Parcela` | `Mês` | `Exercício` | `Tributo` | `Tipo de Receita` | `Referente a` | `Vencimento` | `Valor Original` | `Valor Atual` | `Situação`

#### Botões por linha
| Ícone | Ação | URL |
|---|---|---|
| Imprimir boleto | Gera PDF do boleto | `/pdfs/{titnum}/boleto?parcela={pclnum}` |
| Alterar vencimento | Editar data de vencimento | `/modulo4/vencimento?titnum={n}&pclnum={p}` |

#### Link Resumo Anual
`[ref_15]` → `/modulo4/boletos_por_ano?...`

---

### 8.2 Gerar Boleto por Nota
**URL:** `/juazeirodonorte/modulo4/boletos_por_nota`
**Título:** Gerar Boleto por Nota — Lista de notas fiscais emitidas

#### Filtros
| Campo | Tipo |
|---|---|
| Nome ou CPF ou CNPJ | text |
| Número | text |
| Número do RPS | text |

#### Colunas da tabela
`#` | `Data` | `Competência` | `Doc. Tomador` | `Nome Tomador` | `Valor` | `Retida` | `Situação` | `Valor ISS`

#### Botão por linha
- Ícone barcode → gera boleto da nota específica

---

### 8.3 Resumo Anual
**URL:** `/juazeirodonorte/modulo4/boletos_por_ano`
**Título:** Meus Boletos — Resumo de valores declarados e boletos emitidos

#### Filtro
| Campo | Tipo | Seletor |
|---|---|---|
| Exercício | select | 2000–2026, default 2026 |

#### Colunas da tabela
`Referente ao Mês` | `Total Declarado` | `Boletos Abertos` | `Boletos Pagos` | `Boletos Parcelados` | `Total Boletos`

#### Botão por linha
- Ícone barcode → lista de boletos do mês

---

## 9. OBRAS

### 9.1 Minhas Obras
**URL:** `/juazeirodonorte/obras/minhas`
**Título:** Minhas Obras — Lista de obras utilizadas para emissão de nota para sua empresa

#### Botão de ação
`Anexa Obra` → formulário de vínculo de obra

#### Filtros
| Campo | Tipo |
|---|---|
| Número da Obra | text |
| Logradouro | text |
| Bairro | text |
| Status | select |
| Situação da Obra | select |

---

### 9.2 Cadastro de Obras
**URL:** `/juazeirodonorte/obras`
**Título:** Cadastro de Obras — Lista de obras cadastradas para sua empresa

#### Botão de ação
`Cadastrar Obra` → abre formulário de nova obra

#### Filtros
| Campo | Tipo |
|---|---|
| Título da Obra | text |
| Número da Obra | text |
| Logradouro | text |
| Bairro | text |

---

## 10. RELATÓRIOS

### 10.1 Relatório Situacional
**URL:** `/juazeirodonorte/pdfs/situacional`
**Comportamento:** Gera e abre PDF diretamente no browser (viewer nativo)
**Propósito:** Relatório de situação fiscal do contribuinte

---

### 10.2 Comprovante de Inscrição
**URL:** `/juazeirodonorte/pdfs/comprovante`
**Comportamento:** Gera e abre PDF diretamente no browser
**Propósito:** Comprovante oficial de inscrição municipal

---

### 10.3 Livro de Registros
**URL:** `/juazeirodonorte/module6/livro_de_registros`
**Título:** Livro de Registros — Gera o livro de registros do exercício selecionado

#### Campos
| Campo | Tipo | Opções |
|---|---|---|
| Exercício | select | 2000–2026, default 2026 |
| Tipo de Livro | select | Prestador / (outros) |
| Gerar Livro | button submit | Gera PDF do livro |

---

## 11. CONFIGURAÇÕES

### 11.1 Alterar Senha
**URL:** `/juazeirodonorte/module5/senha`
**Título:** Alterar Senha — Altere sua senha de acesso

#### Campos
| Campo | Tipo | Notas |
|---|---|---|
| Senha | password | Nova senha |
| Confirmação de Senha | password | Confirmar nova senha |
| Salvar | submit button | `POST /module5/senha` |

---

### 11.2 Contador / Procurador
**URL:** `/juazeirodonorte/module5/contador`
**Título:** Contador/Procurador — Selecionar o contador/procurador da empresa

#### Botões de ação (topo direito)
| Botão | Ação |
|---|---|
| Atribuir Contador/Procurador | Abre form de vínculo |
| Cadastrar Procurador | Abre form de novo procurador |

#### Colunas da tabela
`#` | `Razão Social` | `CNPJ` | `CPF` | `E-mail` | `Tipo de Autorização`

#### Botão por linha
- Remover vínculo (ícone vermelho ×)

---

### 11.3 Logomarca
**URL:** `/juazeirodonorte/module5/logomarca`
**Título:** Alterar Logomarca — Altere a logomarca que é impressa na Nota Fiscal

#### Campos
| Campo | Tipo | Notas |
|---|---|---|
| Imagem atual | — | Exibe logo atual (se houver) |
| Selecione uma imagem | file input | Upload de nova imagem |
| Salvar | submit button | `POST /module5/logomarca` |

---

## 12. WEBSERVICE

### 12.1 Lista de Lotes
**URL:** `/juazeirodonorte/lotes`
**Título:** WebService — Lotes — Lista de lotes enviados via webservice

#### Filtros
| Campo | Tipo | Notas |
|---|---|---|
| Número do Lote | text | — |
| Número do RPS | text | — |
| Situação | select | Processado / Erro / Pendente etc. |
| Data de Recebimento Inicial | date | — |
| Data de Recebimento Final | date | — |

#### Colunas da tabela
`#` | `Recebido em` | `Processado em` | `Situação` | `Qtd. de RPS` | `Qtd. de Erros`

---

### 12.2 Documentação do WebService
**URL:** `/juazeirodonorte/modulo2/documentacao`
**Título:** Documentação do WebService

#### Itens listados (links de download)
| Item | Tipo |
|---|---|
| Ambiente de Teste | Link WSDL: `http://speedgov.com.br/wsmod/Nfes?wsdl` |
| Modelo Conceitual — Padrão Abrasf 1.0 | Download PDF |
| Manual de Integração — Padrão Abrasf 1.0 | Download PDF |
| XSD | Download ZIP (arquivos de validação) |
| Exemplos de arquivos XML | Download ZIP |

---

### 12.3 Downloads
**URL:** `/juazeirodonorte/module5/downloads`
**Título:** Downloads — Lista de programas para download

#### Itens listados
| Item | Descrição |
|---|---|
| Baixar XML | Programa para baixar XMLs das notas emitidas |
| Validar XML | Programa para validar estrutura do XML gerado |

---

## 13. URLS DE AÇÕES ESPECIAIS (padrões de URL para automação)

```
# Notas — por ID
/juazeirodonorte/pdfs/{id}/notafiscal           → PDF da nota
/juazeirodonorte/nota_nacional/new?subs_id={id} → Substituição
/juazeirodonorte/nota_nacional/new?copy_id={id} → Cópia
/juazeirodonorte/modulo1/{id}/xml               → Download XML
/juazeirodonorte/modulo1/{id}/email             → Enviar por e-mail
/juazeirodonorte/modulo1/{id}/cancela           → Cancelar nota

# Boletos — por número de título
/juazeirodonorte/pdfs/{titnum}/boleto?parcela={pclnum}   → PDF boleto
/juazeirodonorte/modulo4/vencimento?titnum={n}&pclnum={p} → Alterar vencimento

# Declarações — por mês/ano/número
/juazeirodonorte/pdfs/declaracao?mes={m}&ano={a}&notanumdec={n}&tipo=P&notatipdecl=N
/juazeirodonorte/modulo1/certificados?mes={m}&ano={a}&notanumdec={n}
/juazeirodonorte/modulo1/declaracao_notas?q[notames_eq]={m}&q[notaano_eq]={a}&q[notanumdec_eq]={n}

# Mensagens — por timestamp
/juazeirodonorte/mensagens/{TIMESTAMP}          → Detalhe da mensagem

# Autenticação
/juazeirodonorte/login                          → GET tela de login
/juazeirodonorte/sessions                       → POST login
/juazeirodonorte/logout                         → GET logout
```

---

## 14. OBSERVAÇÕES TÉCNICAS

- **Framework:** Ruby on Rails (URLs com `utf8=✓`, `authenticity_token`, padrão Ransack `q[campo_eq]`)
- **Filtros Ransack:** parâmetros seguem padrão `q[field_predicate]=value` (ex: `q[nfecompmes_eq]=5`)
- **Sessão:** tokens de sessão embutidos em alguns HREFs (bloqueados pelo browser-tool por conter cookies/query strings com dados de sessão)
- **PDFs:** gerados server-side e entregues diretamente como `Content-Type: application/pdf`
- **Select2:** utilizado nos campos de serviço (Código Tributação Municipal, Código Nacional, NBS)
- **Autenticidade do token:** necessário em todos os POSTs (`input[name="authenticity_token"]`)
- **Modal de aviso:** exibido ao carregar o dashboard — botão `Entendi` fecha sem recarregar
- **ADN:** Ambiente de Dados Nacional — integração nacional de NFS-e via SEFIN

---

*Mapa gerado em 25/05/2026 — exploração completa de todas as telas disponíveis na sessão.*
