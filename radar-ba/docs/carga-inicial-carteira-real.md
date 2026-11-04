# RADAR B&A — Carga inicial com a carteira real
**Data:** 18/08/2026 · **Fonte:** `A - RODAGEM/RODAGEM PROCESSUAL 2026.xlsx`
**Execução:** 358 clientes · janela de 90 dias · 359 consultas · 53 minutos · 0 clientes perdidos

---

## 1. O resultado do cruzamento

A planilha marca **205 clientes com BUSCA** — esse é o gabarito. O radar varreu 90 dias de publicações e encontrou **362 processos** para **121 clientes**.

| | planilha diz **SIM** | planilha diz **NÃO** |
|---|---|---|
| **radar achou** | **87** | 34 |
| **radar não achou** | 118 | 119 |

**Cobertura bruta: 42,4%.** Antes de tirar conclusão desse número, duas coisas precisam ser ditas.

---

## 2. O número bruto é enganoso — e o filtrado é melhor

### 2.1 Comparação desigual

A coluna BUSCA é **histórica** (marca quem já teve busca e apreensão, em qualquer época). O radar olhou **90 dias de publicações**. Um processo de 2023 sem andamento publicado nesse intervalo não podia aparecer — e não aparecer, nesse caso, é o comportamento correto.

Cobertura por safra da busca e apreensão:

| Ano da B&A | Clientes | Radar achou | Cobertura |
|---|---|---|---|
| **2026** | 51 | 23 | **45,1%** |
| 2025 | 98 | 30 | 30,6% |
| 2024 | 40 | 9 | 22,5% |
| 2023 | 9 | 5 | 55,6% |
| 2022 ou antes | 7 | 2 | 28,6% |

A cobertura sobe nas safras recentes, como se espera de um detector de casos novos.

### 2.2 Homônimo: 75% do que foi encontrado

Dos 362 processos, **272 estavam em estado diferente do cadastro do cliente**. Um único "Marcos Antônio da Silva" (cadastrado em AL) puxou **24 processos** espalhados pelo país. Outros: "José Roberto da Silva" 21, "Samuel dos Santos" 16, "Valdinei da Silva" 13.

E havia um processo **de 1984** classificado como 🚨 CRÍTICO, porque a régua olhava a data de publicação no diário e não a de ajuizamento.

---

## 3. Duas correções aplicadas

O número CNJ já carrega o **ano de ajuizamento** e o **tribunal** — eu não estava usando nenhum dos dois. Criei `src/util/cnj.py`, **validado contra os 360 processos reais** desta carga: zero divergência entre o tribunal deduzido do número e o informado pelo DJEN.

**Correção 1 — prioridade com o ano real.** Processo ajuizado há 2 anos ou mais nunca é CRÍTICO; publicação recente nele é andamento de rotina.

| | Antes | Depois |
|---|---|---|
| 🚨 CRÍTICO | 362 | **181** |
| 🟡 ATENÇÃO | 0 | 181 |

**Correção 2 — plausibilidade** (`src/servicos/plausibilidade.py`). Pontua estado do processo × estado do cliente, nome pouco distintivo e quantidade de achados do mesmo nome. Não descarta nada sozinho — rebaixa e explica, porque um cliente pode ter se mudado.

### Calibração medida

| Corte | Processos | Clientes | Acertos | Fora do gabarito | Cobertura |
|---|---|---|---|---|---|
| sem filtro | 362 | 121 | 87 | 34 | 42,4% |
| ≥ 0,30 | 188 | 110 | 82 | 28 | 40,0% |
| **≥ 0,60** | **76** | **73** | **69** | **4** | **33,7%** |
| ≥ 0,90 | 65 | 62 | 58 | 4 | 28,3% |

**Recomendo o corte em 0,60:** corta **79% do ruído** e reduz os achados fora do gabarito de 34 para **4**, ao custo de 18 acertos. Vinte alertas por dia que valem a pena conferir são úteis; trezentos e sessenta não são.

---

## 4. O achado mais importante: um cego estrutural do DJEN

Investiguei os 23 clientes com B&A **de 2026** que o radar não achou, consultando o DJEN pelo número do processo. Duas causas, e a segunda é séria:

**Causa 1 — publicação fora da janela.** Processos com publicações entre fevereiro e maio, fora dos 90 dias. Resolve-se ampliando a janela.

**Causa 2 — a publicação não nomeia o cliente.** Em 3 das 5 amostras, a intimação foi dirigida **apenas ao advogado do banco**:

```
processo 0738465-95.2026.8.02.0001 — BUSCA E APREENSÃO EM ALIENAÇÃO FIDUCIÁRIA
   destinatários: [A: BANCO PAN SA]          ← nenhum polo passivo
   nome do cliente no texto da publicação: NÃO
```

Conferi o inteiro teor: **o nome do cliente não aparece em lugar nenhum** — nem nos destinatários, nem no texto. Nenhuma busca por nome pode encontrar essa publicação. E não é um caso raro nem inofensivo: é justamente a **primeira publicação** de uma busca e apreensão, quando o banco é intimado da liminar antes de o cliente ser citado — exatamente o momento que o radar existe para pegar.

**Isto não é defeito do código.** É limite da fonte, e nenhum ajuste de casamento de nomes resolve.

---

## 5. O que fecha esse buraco: o e-SAJ por CPF

O e-SAJ busca por **documento da parte**, independentemente de haver publicação. E a sua carteira está concentrada justamente onde ele funciona:

| | Clientes | % |
|---|---|---|
| Em estado com e-SAJ por CPF | **297** | **83%** |
| — Alagoas | 275 | 77% |
| — São Paulo | 21 | 6% |
| — Ceará / Amazonas | 3 | 1% |
| Fora do alcance do e-SAJ | 61 | 17% |

Custo de uma varredura completa por CPF: **297 consultas a uma cada 5 segundos = 25 minutos**.

O e-SAJ continua **desligado**, aguardando a análise dos Termos de Uso. A decisão é jurídica e é sua — mas agora ela tem número: ela decide se 83% da carteira tem confirmação por CPF e cobertura do cego estrutural, ou não.

---

## 6. Correções feitas no importador da carteira

| # | Problema na planilha real | Efeito | Correção |
|---|---|---|---|
| 1 | **6 clientes com CNPJ** (confecção, pizzaria, construtora, centro automotivo) | eram descartados — PJ também sofre busca e apreensão | suporte a CNPJ com a mesma proteção do CPF |
| 2 | **Cabeçalho desalinhado** em MARANHÃO e AMAPÁ | lia o número do processo no lugar do CPF | coluna localizada por conteúdo, com dígito verificador |
| 3 | **`Nº PROCESSO`** não reconhecido | nenhum processo era vinculado ao cliente | o `º` decompõe para `o` minúsculo; normalizar antes de maiusculizar |
| 4 | **Rate limit do DJEN** | 100% das consultas falhavam em escala real | ver abaixo |

### O rate limit, em detalhe

O servidor anuncia `x-ratelimit-limit: 20`. A 18/min **todas as consultas falharam**. Investigando: o DJEN devolve `retry-after` **negativo** (−57, −61, −64…) e um `x-ratelimit-reset` que **não avança enquanto continuamos pedindo** — insistir renova o castigo. O backoff de 3–9 s só realimentava o bloqueio.

Ritmo real medido: **10 req/min sustenta 15 consultas seguidas com zero erro.**

Correção: descartar `retry-after` negativo, usar o `reset` do servidor e **pausar o sistema inteiro por 60 s** ao tomar 429. Resultado na carga real: **20 ocorrências de 429, todas recuperadas, 0 clientes perdidos**.

---

## 7. Pendências da planilha

Quatro linhas ficaram de fora por não ter documento nenhum:

| Aba | Linha |
|---|---|
| PERNAMBUCO | 10 e 21 |
| BAHIA | 14 |
| PARANÁ | 11 |

Também há **duas abas de Amapá** (`AMAPA` e `AMAPÁ`) e `MATO GROSSO` está sem clientes.

---

## 8. Recomendação

1. **Adotar o corte de plausibilidade em 0,60** como padrão.
2. **Decidir sobre o e-SAJ.** É o que fecha o cego estrutural, e alcança 83% desta carteira.
3. **Rodar a diária com janela de 2 dias** (~6 min a 10 req/min) e refazer a carga histórica com janela de 365 dias uma única vez.
4. Completar as 4 linhas sem documento.

Testes: **155 passando**, nenhum tocando a rede.
