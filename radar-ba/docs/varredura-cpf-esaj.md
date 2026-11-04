# RADAR B&A — Varredura por CPF/CNPJ no e-SAJ
**Data:** 18/08/2026 · **Autorização:** expressa, do escritório
**Execução:** 299 consultas · 25 minutos · **0 erros**

---

## 1. Base normativa levantada antes de ligar

A busca por documento **não é brecha**: a [Resolução CNJ nº 121/2010](https://atos.cnj.jus.br/atos/detalhar/92), art. 4º, III, determina que a consulta processual pública na internet permita localizar processos pelo número de inscrição das partes no cadastro de contribuintes. O art. 1º garante acesso aos dados básicos a qualquer pessoa, sem cadastro.

Não foi localizado termo de uso publicado para o e-SAJ do TJAL, nem `robots.txt` em nenhum dos cinco domínios. O único termo encontrado é o do [TJSPMobile](https://www.tjsp.jus.br/tjspmobile/termodeuso) — do aplicativo, não da consulta web.

Salvaguardas em operação: identificação no User-Agent, **1 consulta a cada 5 segundos**, restrição a clientes da carteira e **parada imediata** se o tribunal recusar ou passar a exigir CAPTCHA.

---

## 2. Resultado

```
Clientes consultados            299
Processos CONFIRMADOS por documento  175
Clientes com B&A confirmada     149  de 358
Erros                             0
```

| Classe | Processos |
|---|---|
| Busca e Apreensão em Alienação Fiduciária | 159 |
| Execução de Título Extrajudicial | 16 |

| Ano de ajuizamento | 2026 | 2025 | 2024 | 2023 | 2022 | 2021 |
|---|---|---|---|---|---|---|
| Processos | **42** | 81 | 40 | 7 | 2 | 1 |

---

## 3. O que o CPF encontrou e o nome não

| | Processos |
|---|---|
| **Só no e-SAJ (a busca por nome perdia)** | **111** |
| Em ambos | 64 |
| Só no DJEN | 298 (majoritariamente homônimos) |

| | Clientes |
|---|---|
| Passaram de `POSSIBLE_MATCH` para `CONFIRMED_MATCH` | **71** |
| Encontrados **só** pelo documento | **78** |

Os 111 processos exclusivos do e-SAJ confirmam o diagnóstico do cego estrutural: quando a intimação é dirigida apenas ao advogado do banco, o nome do cliente não aparece em nenhum campo da publicação. Dois casos que eu havia isolado como perdidos — `0711036-56.2026.8.02.0001` e `0707181-69.2026.8.02.0001` — foram achados pelo documento.

---

## 4. Contra o gabarito da planilha

| | |
|---|---|
| Marcados com BUSCA na RODAGEM | 205 |
| **Encontrados pelo documento** | **145 — 71% de cobertura** |
| Achados fora do gabarito | 4 |

Salto de cobertura em relação à busca por nome:

| Método | Cobertura | Ruído |
|---|---|---|
| DJEN por nome, sem filtro | 42,4% | 34 clientes fora do gabarito |
| DJEN por nome, plausibilidade ≥ 0,60 | 33,7% | 4 |
| **e-SAJ por documento** | **71%** | **4** |

Os 29% não encontrados concentram-se fora de Alagoas (o e-SAJ não alcança PJe, eproc e Projudi) e no acervo de São Paulo posterior à migração.

---

## 5. Quatro casos que a planilha não registrava

Não são falsos positivos: são processos reais, confirmados por documento, contra clientes que a RODAGEM **não marca** com BUSCA. Merecem conferência.

| Cliente | Processo | Classe | Foro |
|---|---|---|---|
| Carlos Henrique Lisboa Loureiro Farias | 0742260-12.**2026**.8.02.0001 | Busca e Apreensão em Alienação Fiduciária | Foro de Maceió |
| Elizabete Santos da Rocha | 0701190-93.2025.8.02.0051 | Busca e Apreensão em Alienação Fiduciária | Foro de Rio Largo |
| José Everivaldo Silva de Lima | 0749679-54.2024.8.02.0001 | Busca e Apreensão em Alienação Fiduciária | — |
| Sheila Patricia Batista | 0701154-58.2025.8.02.0081 | Execução de Título Extrajudicial | 10º Juizado Especial Cível da Capital |

---

## 6. Três defeitos que a carteira real revelou

Nenhum aparecia nos testes sintéticos. Todos corrigidos e cobertos por teste.

### 6.1 Falso CAPTCHA — bloqueava tudo

A detecção procurava a palavra `captcha` no corpo da resposta. O e-SAJ carrega um JavaScript **adormecido**, que apenas repassa um parâmetro `uuidCaptcha` quando ele existe na URL. Resultado: **toda consulta era recusada** com "passou a exigir CAPTCHA".

Agora a detecção exige um desafio de verdade — `g-recaptcha`, `grecaptcha`, imagem de captcha ou campo de entrada. **Não há CAPTCHA na consulta por documento.**

### 6.2 Resultado único não era lido

Quando a busca acha **um só** processo, o e-SAJ abre direto a página de detalhe em vez da listagem. O parser só entendia a lista — perdia justamente o caso mais preciso: o cliente com um único processo.

A página de detalhe traz mais informação que a lista: **data de distribuição** e **as duas partes**, o que permite identificar o banco.

### 6.3 As revisionais do escritório entravam como busca e apreensão

O mais grave. Sem código de classe, o classificador caía na regra de texto e **usava o assunto**. "Procedimento Comum Cível" com assunto "Alienação Fiduciária" — que é tipicamente a **revisional ajuizada pelo próprio escritório** — era alertada como busca e apreensão contra o cliente.

Corrigido: a regra de texto olha **só o nome da classe**. O assunto reforça uma classe alvo, mas nunca a estabelece. Também foi criada a ponte nome→código, para que "Busca e Apreensão em Alienação Fiduciária" valha como classe 81 (confiança 0,98) em vez de texto genérico (0,65).

---

## 7. Limitação que fica

**O banco só é identificado em 47 dos 175 processos (27%).** Na listagem o e-SAJ exibe apenas a parte que casou com a busca — o cliente —, não o autor. Só a página de detalhe traz as duas partes.

Não é bloqueante: o número do processo já permite enriquecer pelo DJEN (`acompanhar`) ou pelo DataJud. Fica como próximo passo.

---

## 8. Situação das duas frentes

| Objetivo | Estado | Cobertura |
|---|---|---|
| **A — B&A nova por CPF** | ✅ **funcionando** | 71% do gabarito · 299 clientes · 25 min |
| **A — B&A nova em SP (pós-migração)** | ❌ sem caminho lícito | 21 clientes |
| **B — Liminar / mandado** | ✅ funcionando | 216 processos |

```bash
python3 executar.py varrer-esaj    # objetivo A
python3 executar.py acompanhar     # objetivo B
```

**189 testes passando**, nenhum tocando a rede.
