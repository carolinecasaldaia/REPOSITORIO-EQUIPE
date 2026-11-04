# RADAR B&A — Mapeamento Técnico das Fontes Judiciais
### FASE 1 · Caroline Macedo Advocacia
**Data do levantamento:** 18/08/2026
**Escopo:** 27 Tribunais de Justiça estaduais + APIs oficiais do CNJ
**Método:** todas as afirmações abaixo foram **testadas empiricamente** nesta data. Nada foi presumido. As respostas cruas estão em `evidencias/`.

---

## 1. Sumário executivo — leia isto primeiro

Três conclusões mudam o desenho do projeto em relação ao que foi originalmente imaginado:

**1. O DataJud NÃO serve para localizar processos por cliente.** A API pública do CNJ **não expõe as partes** — nem nome, nem CPF, nem polo. Testei a existência de 10 nomes de campo possíveis (`partes`, `poloAtivo`, `autor`, `cpf`, `documento`…): **todos retornaram zero documentos**. Uma busca textual livre por `"BANCO PAN"` em todos os campos do índice do TJAL retornou **0 resultados**. Não há como perguntar ao DataJud "existe processo contra o CPF X".

**2. Mesmo que expusesse, o DataJud chegaria tarde demais.** Medi a defasagem de ingestão nos 27 tribunais: ela varia de ~2 semanas a **~2 meses**. No TJSP — que sozinho concentra 15.103 buscas e apreensões por mês — a B&A mais recente visível na API foi ajuizada em **30/06/2026**, ou seja, **49 dias de atraso**. Em busca e apreensão a liminar de apreensão do veículo costuma sair em dias. Um radar com 49 dias de latência avisaria o escritório depois que o carro já foi apreendido.

**3. Existe uma fonte melhor, e ela resolve o problema: o DJEN / API Comunica do CNJ.** É pública, sem autenticação, **nacional**, atualizada em **D+1**, e — decisivo — **traz o nome das partes, o polo (ativo/passivo), a classe processual, o órgão julgador e o número do processo**. Consultei nome de parte e obtive de volta, em segundos, a busca e apreensão correspondente com o banco autor identificado.

> **Arquitetura recomendada:** o **DJEN é o motor de detecção**; o **e-SAJ é o confirmador por CPF** onde é permitido (5 tribunais, incluindo o TJSP); o **DataJud é apenas enriquecimento histórico**, nunca detecção.

**Dimensão do problema:** o Brasil registra **49.358 novas buscas e apreensões por mês** (classe CNJ 81, maio/2026). O TJSP responde por 31% desse total.

---

## 2. Fonte A — DataJud / API Pública do CNJ

| Item | Resultado testado |
|---|---|
| Endpoint | `https://api-publica.datajud.cnj.jus.br/api_publica_<tj>/_search` |
| Autenticação | API Key pública do CNJ, header `Authorization: APIKey <chave>` |
| Disponibilidade | **27/27 tribunais responderam HTTP 200** |
| Tempo de resposta | 0,4 s a 2,0 s |
| Tecnologia | Elasticsearch exposto (aceita `query`, `aggs`, `sort`, `_source`) |
| **Consulta por CPF** | **❌ IMPOSSÍVEL — campo inexistente** |
| **Consulta por nome** | **❌ IMPOSSÍVEL — campo inexistente** |
| Defasagem | ⚠️ 2 semanas a 2 meses, conforme o tribunal |

### 2.1 Campos realmente disponíveis

Documento de amostra do TJAL — esta é a **totalidade** do que a API entrega:

```
id, tribunal, grau, numeroProcesso, dataAjuizamento, nivelSigilo,
orgaoJulgador{codigo,nome,codigoMunicipioIBGE}, classe{codigo,nome},
sistema{codigo,nome}, formato{codigo,nome}, dataHoraUltimaAtualizacao,
movimentos[{codigo,nome,dataHora,complementosTabelados}], assuntos[{codigo,nome}]
```

Não há `partes`. **Isto é uma decisão de projeto do CNJ, não uma limitação contornável** — a Resolução CNJ 331/2020 e a Portaria 160/2020 disponibilizam apenas metadados processuais, e a exposição de partes esbarraria na LGPD. Registro a limitação e **não proponho contorná-la**.

### 2.2 Armadilha técnica descoberta: `dataAjuizamento` está corrompido no índice

O campo `dataAjuizamento` chega como string `yyyyMMddHHmmss` (ex.: `20260630235628`), mas o mapping do Elasticsearch o interpreta como **`epoch_millis`**. Resultado: um processo ajuizado em 30/06/2026 é indexado internamente **no ano 2612**.

Prova: um histograma anual do TJSP na classe 81 devolve buckets `1941…2025` (documentos gravados em ISO) **e** buckets `2584…2612` (documentos gravados em `yyyyMMddHHmmss`) — duas escalas de tempo incompatíveis no mesmo índice.

**Consequência prática para o código da FASE 2:**
- ❌ **Nunca** filtrar com semântica de data (`{"gte":"2026-03-01"}`) — retorna resultado errado silenciosamente.
- ✅ Filtrar com o **número cru**: `{"range":{"dataAjuizamento":{"gte":20260301000000,"lt":20260401000000}}}`.
- ✅ Sempre normalizar a data no cliente, tratando os dois formatos.
- ✅ `grau` é campo `text` — **não aceita agregação nem ordenação** (erro `Fielddata is disabled`). Usar `sistema.codigo` e `classe.codigo`, que são numéricos.

### 2.3 Defasagem medida, tribunal a tribunal

Número de buscas e apreensões (classe 81) por mês de ajuizamento, conforme visível na API em 18/08/2026:

| Defasagem | Tribunais |
|---|---|
| ✅ ~2 semanas | TJCE, TJDFT, TJES, TJPA, TJTO |
| ⚠️ ~1 mês | TJAC, TJAL, TJAM, TJAP, TJBA, TJMA, TJMG, TJMT, TJPB, TJPI, TJRO, TJRR, TJRS, TJSE |
| 🔴 ~2 meses | TJGO, TJMS, **TJPE**, TJPR, TJRJ, TJRN, TJSC, **TJSP** |

Os dois tribunais escolhidos para a prova de conceito (TJSP e TJPE) estão **na pior faixa**.

### 2.4 Qualidade dos metadados

Anomalias reais encontradas, que o classificador precisará tolerar:
- `sistema: "Inválido"` em 100% do TJSE, 48% do TJAP, 38% do TJRJ, 28% do TJMG.
- TJSP registra 18% das B&A como "Projudi", embora o tribunal opere e-SAJ — provável resíduo de migração.
- Datas de ajuizamento absurdas (ex.: ano 4022 no TJAC).

**Veredito do DataJud:** útil para **enriquecer** um processo já conhecido (classe, assunto, órgão julgador, movimentações) e para **estatística de carteira**. Inútil para detecção.

---

## 3. Fonte B — DJEN / API Comunica (CNJ) ⭐ **fonte primária recomendada**

Diário de Justiça Eletrônico Nacional, instituído pela Resolução CNJ 455/2022. Consolida citações e intimações de todos os tribunais.

| Item | Resultado testado |
|---|---|
| Endpoint | `https://comunicaapi.pje.jus.br/api/v1/comunicacao` |
| Autenticação | **nenhuma** |
| CAPTCHA | **nenhum** |
| Cobertura | **nacional** (dispensa iterar tribunal a tribunal) |
| Atualização | **D+1** — em 18/08 já havia publicações de 17/08 |
| **Nome das partes** | ✅ **sim**, com polo (`A` = ativo, `P` = passivo) |
| **Classe processual** | ✅ `nomeClasse` + `codigoClasse` |
| CPF | ❌ não retorna |
| Rate limit | **20 req/min** (header `x-ratelimit-limit: 20`), reset ~60 s, HTTP 429 ao exceder |
| Paginação | ✅ até **1.000 itens/página**, sem duplicatas entre páginas |

### 3.1 Prova de funcionamento

Consulta nacional por `nomeParte=CAMILA COSTA ALVES`, janela de 30 dias, **sem filtro de tribunal**:

```
TJSP  4000116-76.2026.8.26.0405  BUSCA E APREENSÃO EM ALIENAÇÃO FIDUCIÁRIA
      passivo = CAMILA COSTA ALVES   ativo = ITAU UNIBANCO HOLDING S.A.
TJSP  4051190-26.2026.8.26.0000  AGRAVO DE INSTRUMENTO
      passivo = ITAU UNIBANCO S.A.   ativo = CAMILA COSTA ALVES
```

Isto é **exatamente o alerta que o escritório precisa**: cliente no polo passivo, banco identificado, classe correta, tribunal e vara — em D+1.

### 3.2 Parâmetros: o que funciona e o que é ignorado

Testado um a um, comparando contagens:

| Parâmetro | Funciona? | Observação |
|---|---|---|
| `nomeParte` | ✅ **sim** | filtro real e preciso |
| `numeroProcesso` | ✅ sim | retornou 11 comunicações do processo |
| `siglaTribunal` | ✅ sim | opcional; omitir = busca nacional |
| `dataDisponibilizacaoInicio` / `Fim` | ✅ sim | formato `YYYY-MM-DD` |
| `itensPorPagina` / `pagina` | ✅ sim | até 1.000 |
| `texto` | ✅ sim | busca no inteiro teor |
| **`codigoClasse`** | ❌ **IGNORADO** | retorna Execução, Habilitação de Crédito etc. |
| **`classe`** | ❌ **IGNORADO** | — |
| parâmetros inexistentes | ❌ ignorados **em silêncio** | não há erro — risco de falsa confiança |

> ⚠️ **Regra para a FASE 2:** a API **aceita e ignora** parâmetros desconhecidos sem erro. **Filtrar classe processual sempre no nosso lado**, nunca confiando no servidor. Todo filtro novo deve ser validado comparando contagens com e sem o parâmetro.

### 3.3 Semântica de `nomeParte` — origem dos falsos negativos

| Consulta | Resultado |
|---|---|
| `CAMILA COSTA ALVES` (exato) | 2 ✅ |
| `CAMILA COSTA` (prefixo) | 441 |
| `CAMILA` | 10.000 (teto) |
| `COSTA ALVES CAMILA` (ordem trocada) | **0** ❌ |
| `CAMILA COSTA ALVEZ` (1 letra errada) | **0** ❌ |

É casamento por **sequência exata de caracteres**, sem tolerância a erro, abreviação ou inversão. **Um nome cadastrado com uma letra divergente do registro do tribunal produz falso negativo silencioso.** Mitigação obrigatória na FASE 2 — ver §7.

### 3.4 Volume e viabilidade operacional

O TJAL sozinho publica **mais de 5.000 comunicações/dia**. Duas estratégias possíveis:

- **Varredura nacional** (baixar tudo e filtrar localmente): ~300–500 requisições/dia a 1.000 itens/página ⇒ **15–25 min/dia** dentro do limite de 20 req/min. Permite casamento aproximado (fuzzy) local e gera inteligência de mercado.
- **Consulta por cliente** (1 requisição por cliente/dia): 3.000 clientes ⇒ **2,5 h/dia**. Mais barata em banda, porém refém do casamento exato do §3.3.

**Recomendo a varredura nacional como padrão**, com consulta por nome como reforço pontual.

---

## 4. Fonte C — e-SAJ (consulta por CPF) ⭐ **confirmador**

O e-SAJ oferece a opção **"Documento da Parte" (`cbPesquisa=DOCPARTE`)** — busca direta por CPF/CNPJ, **sem CAPTCHA**.

**Teste real executado** no TJAL com o CNPJ do Banco Pan (`59285411000113` — pessoa jurídica, dado público; deliberadamente não usei CPF de pessoa física em teste):

```
HTTP 200 · 87.081 bytes · sem captcha · sem bloqueio
Processos retornados: 0701883-50.2026.8.02.0081, 0701567-37.2026.8.02.0081,
                      0701422-78.2026.8.02.0081, 0701348-24.2026.8.02.0081 …
```

Retorna número do processo e classe, **em tempo real** (resultados de 2026 em diante) — sem a defasagem do DataJud.

Disponibilidade testada em 12 domínios:

| Tribunal | e-SAJ | Busca por documento | CAPTCHA |
|---|---|---|---|
| **TJSP** | ✅ | ✅ `DOCPARTE` | não |
| **TJAL** | ✅ | ✅ `DOCPARTE` | não |
| **TJAC** | ✅ | ✅ `DOCPARTE` | não |
| **TJAM** | ✅ | ✅ `DOCPARTE` | não |
| **TJCE** | ✅ | ✅ `DOCPARTE` | não |
| TJMS | ✅ | ❌ só nome / nº | não |
| TJSC, TJSE, TJBA, TJRN, TJPB, TJMT | ❌ inexistente (404/403/DNS) | — | — |

**Cobertura:** os 5 tribunais com CPF automatizável somam **17.750 B&A/mês — 36% do volume nacional**, incluindo o TJSP.

> ⚖️ **Ressalva jurídica — decisão sua, não minha.** A ausência de CAPTCHA é um fato técnico, não uma autorização. Antes de automatizar o e-SAJ é preciso ler os **Termos de Uso de cada tribunal**, e a automação deve ser **identificada, em ritmo baixo (sugiro ≤ 1 req/5 s), restrita a clientes com procuração, e sem qualquer técnica de evasão**. Deixei isso como item bloqueante da FASE 2 — ver §8.

---

## 5. Fonte D — PJe Consulta Pública (13 tribunais) 🔒 **vedada à automação**

Formulário do PJe (testado no TJPE, TJMG, TJBA) — os campos são exatamente os que precisaríamos:

```
Processo · Nome da Parte · Nome do advogado · Classe judicial ·
CPF/CNPJ · OAB · Data de Autuação (De / Até)
```

Permitiria, em tese, "todas as B&A ajuizadas ontem contra o CPF X". **Porém o formulário é protegido por reCAPTCHA** (confirmado no HTML: `recaptcha`, `ReCaptcha`).

**Decisão:** conforme sua diretriz expressa de nunca quebrar CAPTCHA, os tribunais PJe ficam com **detecção via DJEN + conferência humana**, retornando `MANUAL_REVIEW_REQUIRED`. Não há solução automatizada legítima e não vou inventar uma.

Tribunais afetados: TJAP, TJBA, TJDFT, TJES, TJMA, TJMG, TJMT, TJPA, TJPB, TJPE, TJPI, TJRJ, TJRN, TJRO.

---

## 6. Fonte E — eproc e Projudi 🔒 **vedada à automação**

- **eproc** (TJPR, TJRS, TJGO, TJRR, TJAM): o TJRS respondeu **HTTP 403 a requisição não-navegador** — proteção anti-bot explícita. Contorná-la violaria sua regra. TJPR mudou de endpoint (404 na URL testada).
- **Projudi** (TJSC, TJRS, TJTO, TJRJ parcial): consulta pública com CAPTCHA e restrições de acesso a partes.

Ambos: **DJEN + conferência humana**.

---

## 7. Tabela consolidada — 27 Tribunais de Justiça

| Tribunal | UF | Sistema predominante | B&A/mês | DataJud: defasagem | Consulta pública por CPF | CAPTCHA | Automação por CPF | Fonte recomendada |
|---|---|---|---|---|---|---|---|---|
| **TJAC** | AC | SAJ | 124 | ⚠️ ~1 mês | ✅ e-SAJ `DOCPARTE` | não | ✅ **sim** | DJEN + e-SAJ por CPF |
| **TJAL** | AL | SAJ | 827 | ⚠️ ~1 mês | ✅ e-SAJ `DOCPARTE` | não | ✅ **sim** | DJEN + e-SAJ por CPF |
| **TJAM** | AM | Eproc + e-SAJ (legado) | 963 | ⚠️ ~1 mês | ✅ e-SAJ `DOCPARTE` | não | ✅ **sim** | DJEN + e-SAJ por CPF |
| **TJAP** | AP | PJe | 110 | ⚠️ ~1 mês | 🔒 existe, sob reCAPTCHA | **sim** | ❌ vedada | DJEN + conferência humana no PJe |
| **TJBA** | BA | PJe | 3.041 | ⚠️ ~1 mês | 🔒 existe, sob reCAPTCHA | **sim** | ❌ vedada | DJEN + conferência humana no PJe |
| **TJCE** | CE | SAJ | 1.733 | ✅ ~2 sem | ✅ e-SAJ `DOCPARTE` | não | ✅ **sim** | DJEN + e-SAJ por CPF |
| **TJDFT** | DF | PJe | 777 | ✅ ~2 sem | 🔒 existe, sob reCAPTCHA | **sim** | ❌ vedada | DJEN + conferência humana no PJe |
| **TJES** | ES | PJe | 870 | ✅ ~2 sem | 🔒 existe, sob reCAPTCHA | **sim** | ❌ vedada | DJEN + conferência humana no PJe |
| **TJGO** | GO | Eproc | 2.357 | 🔴 ~2 meses | 🔒 restrita | sim / anti-bot | ❌ vedada | DJEN + conferência humana |
| **TJMA** | MA | PJe | 683 | ⚠️ ~1 mês | 🔒 existe, sob reCAPTCHA | **sim** | ❌ vedada | DJEN + conferência humana no PJe |
| **TJMG** | MG | PJe | 2.855 | ⚠️ ~1 mês | 🔒 existe, sob reCAPTCHA | **sim** | ❌ vedada | DJEN + conferência humana no PJe |
| **TJMS** | MS | SAJ | 704 | 🔴 ~2 meses | ❌ só nome / nº | não | ⚠️ parcial | DJEN (nome) + conferência humana |
| **TJMT** | MT | PJe | 1.453 | ⚠️ ~1 mês | 🔒 existe, sob reCAPTCHA | **sim** | ❌ vedada | DJEN + conferência humana no PJe |
| **TJPA** | PA | PJe | 1.112 | ✅ ~2 sem | 🔒 existe, sob reCAPTCHA | **sim** | ❌ vedada | DJEN + conferência humana no PJe |
| **TJPB** | PB | PJe | 333 | ⚠️ ~1 mês | 🔒 existe, sob reCAPTCHA | **sim** | ❌ vedada | DJEN + conferência humana no PJe |
| **TJPE** | PE | PJe | 1.278 | 🔴 ~2 meses | 🔒 existe, sob reCAPTCHA | **sim** | ❌ vedada | DJEN + conferência humana no PJe |
| **TJPI** | PI | PJe | 528 | ⚠️ ~1 mês | 🔒 existe, sob reCAPTCHA | **sim** | ❌ vedada | DJEN + conferência humana no PJe |
| **TJPR** | PR | Eproc | 4.337 | 🔴 ~2 meses | 🔒 restrita | sim / anti-bot | ❌ vedada | DJEN + conferência humana |
| **TJRJ** | RJ | PJe | 1.658 | 🔴 ~2 meses | 🔒 existe, sob reCAPTCHA | **sim** | ❌ vedada | DJEN + conferência humana no PJe |
| **TJRN** | RN | PJe | 539 | 🔴 ~2 meses | 🔒 existe, sob reCAPTCHA | **sim** | ❌ vedada | DJEN + conferência humana no PJe |
| **TJRO** | RO | PJe | 329 | ⚠️ ~1 mês | 🔒 existe, sob reCAPTCHA | **sim** | ❌ vedada | DJEN + conferência humana no PJe |
| **TJRR** | RR | Eproc | 187 | ⚠️ ~1 mês | 🔒 restrita | sim / anti-bot | ❌ vedada | DJEN + conferência humana |
| **TJRS** | RS | Projudi | 2.964 | ⚠️ ~1 mês | 🔒 restrita | sim | ❌ vedada | DJEN + conferência humana |
| **TJSC** | SC | Projudi | 3.968 | 🔴 ~2 meses | 🔒 restrita | sim | ❌ vedada | DJEN + conferência humana |
| **TJSE** | SE | n/d (metadado inválido) | 257 | ⚠️ ~1 mês | 🔒 restrita | sim | ❌ vedada | DJEN + conferência humana |
| **TJSP** | SP | SAJ | 15.103 | 🔴 ~2 meses | ✅ e-SAJ `DOCPARTE` | não | ✅ **sim** | DJEN + e-SAJ por CPF |
| **TJTO** | TO | Projudi | 268 | ✅ ~2 sem | 🔒 restrita | sim | ❌ vedada | DJEN + conferência humana |

> **Volume nacional de Busca e Apreensão (classe 81) em maio/2026: 49.358 processos novos no mês.**

*Volume = novas B&A ajuizadas em maio/2026 (último mês fechado com ingestão completa na maioria dos tribunais).*

---

---

## ⚠️ ATUALIZAÇÃO — 18/08/2026: TJSP migrou para o eproc

O TJSP migrou para o **eproc**. Processos novos passam a nascer lá; o e-SAJ
continua no ar, mas apenas para o acervo anterior à migração.

**Verificado nesta data:**

| | Situação |
|---|---|
| e-SAJ TJSP (`esaj.tjsp.jus.br/cpopg`) | ✅ no ar, ainda com `DOCPARTE` — **só alcança o acervo antigo** |
| eproc TJSP (`eproc1g.tjsp.jus.br`) | ✅ no ar, com consulta pública |
| eproc: busca por CPF | ❌ **não existe** — o formulário só aceita `num_processo` e `instancia` |
| eproc: CAPTCHA | ❌ presente (`hdnInfraCaptcha`) |

**Consequência para o radar:** o TJSP **perde a detecção por CPF para processos
novos**. Não há caminho lícito: o eproc não oferece busca por documento, e o que
oferece está atrás de CAPTCHA. Restam o DJEN por nome (com o cego estrutural
descrito em §5 do relatório da carga inicial) e o acompanhamento por número dos
processos já conhecidos.

**Impacto medido na carteira do escritório:** 21 dos 358 clientes estão em SP —
**6%**. A cobertura do e-SAJ por CPF cai de 83% para **78%** (278 clientes),
sustentada por Alagoas (275 clientes, e-SAJ intacto e com `DOCPARTE`, conferido
nesta data).

O TJAL **não** migrou: `eproc1g.tjal.jus.br` responde 403 e o e-SAJ segue com
busca por documento.


## 8. Classes processuais — taxonomia validada

Códigos confirmados por agregação no índice do TJSP (não presumidos):

### ✅ Alvos do radar

| Código | Classe | Uso |
|---|---|---|
| **81** | **Busca e Apreensão em Alienação Fiduciária** | 🎯 alvo principal — DL 911/1969 |
| **12154** | Execução de Título Extrajudicial | alvo secundário |
| **159** | Execução de Título Extrajudicial (código legado) | alvo secundário |
| **181** | Busca e Apreensão (cível genérica) | avaliar caso a caso |

### ❌ Exclusões obrigatórias — evitam falso positivo grave

| Código | Classe | Por quê excluir |
|---|---|---|
| **309** | Pedido de Busca e Apreensão **Criminal** | matéria penal |
| **12072** | Busca e Apreensão **Infracional** | ato infracional |
| **1438** | Busca e Apreensão **Infância e Juventude** | menor — sigilo |
| **12079** | Execução de Título Extrajudicial **contra a Fazenda Pública** | polo incompatível |

> Filtrar por texto ("busca e apreensão") sem checar o código da classe misturaria **processo criminal e de menores** com alienação fiduciária. O classificador deve usar o **código** como sinal primário.

---

## 9. Riscos identificados e limitações honestas

| # | Risco | Gravidade | Mitigação proposta |
|---|---|---|---|
| 1 | **Nenhuma fonte automatizável cruza CPF em 22 dos 27 tribunais** | 🔴 alta | DJEN por nome ⇒ `POSSIBLE_MATCH`; confirmação humana |
| 2 | **Homônimos** — nome comum gera falso positivo | 🔴 alta | nunca auto-confirmar por nome; score + revisão |
| 3 | **Falso negativo silencioso** — nome com 1 letra divergente retorna 0 | 🔴 alta | normalização + variantes + auditoria de cobertura |
| 4 | e-SAJ: automação depende de análise dos Termos de Uso | 🟡 média | **item bloqueante** — validar antes de codar |
| 5 | DataJud com defasagem de até 2 meses | 🟡 média | não usar para detecção |
| 6 | `dataAjuizamento` corrompido (epoch_millis) | 🟡 média | filtro numérico cru + normalização |
| 7 | API Comunica ignora parâmetros inválidos em silêncio | 🟡 média | filtrar no cliente + teste de contagem |
| 8 | Rate limit 20 req/min no DJEN | 🟢 baixa | fila com token bucket |
| 9 | Processos em segredo de justiça não aparecem | 🟢 baixa | documentar como limite intransponível |
| 10 | Chave pública do DataJud pode ser rotacionada pelo CNJ | 🟢 baixa | `.env` + alerta no health check |

### O que este sistema **não** conseguirá fazer

Sendo direta, para não criar expectativa falsa:

1. **Não haverá certeza automática de identidade** fora dos 5 tribunais e-SAJ. Em 64% do volume nacional o alerta será `POSSIBLE_MATCH` sujeito a conferência humana.
2. **Não detectará o ajuizamento em si**, e sim a **primeira publicação** (citação/intimação) no DJEN — tipicamente dias após a distribuição. É o melhor disponível por meio lícito, mas não é instantâneo.
3. **Não verá processos em segredo de justiça.**
4. **Não substitui o monitoramento oficial por OAB** dos processos em que o escritório já atua.

---

## 10. Conclusão da FASE 1

| Fonte | Papel no RADAR B&A | Situação |
|---|---|---|
| **DJEN / API Comunica** | 🥇 **motor de detecção** — nacional, D+1, com partes e classe | ✅ testada e aprovada |
| **e-SAJ (`DOCPARTE`)** | 🥈 **confirmação por CPF** em 5 TJs / 36% do volume | ✅ testada · ⚖️ pendente análise de ToS |
| **DataJud** | 🥉 **enriquecimento e estatística** | ✅ testada · ❌ imprestável para detecção |
| **PJe / eproc / Projudi** | conferência **humana** | 🔒 CAPTCHA / anti-bot — automação descartada |

O objetivo do projeto continua alcançável, mas por um caminho diferente do previsto no plano original: **a espinha dorsal é o DJEN, não o DataJud**.

---

### Evidências

`evidencias/probe27.json` · `evidencias/latencia2.json` · `evidencias/sistemas.json`
Todos os testes são reproduzíveis com as consultas descritas neste documento.
