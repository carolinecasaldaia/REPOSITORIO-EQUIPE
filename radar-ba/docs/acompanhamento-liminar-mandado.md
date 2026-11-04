# RADAR B&A — Liminar deferida e mandado expedido
**Data:** 18/08/2026 · **Baseline:** 216 processos · 365 dias · 0 erros

---

## 1. O que mudou no pedido

O escritório passou a querer duas coisas distintas, e elas exigem caminhos diferentes:

| Objetivo | Pergunta | Caminho |
|---|---|---|
| **A** | Por CPF: surgiu busca e apreensão nova? | e-SAJ por CPF |
| **B** | No processo que já conheço: saiu liminar ou mandado? | DJEN por nº do processo |

---

## 2. TJSP migrou para o eproc — o que isso custa

Verificado em 18/08/2026:

| | Situação |
|---|---|
| e-SAJ TJSP | ✅ no ar com `DOCPARTE`, mas **só o acervo anterior à migração** |
| eproc TJSP | ✅ no ar |
| **eproc: busca por CPF** | ❌ **não existe** — o formulário aceita só `num_processo` e `instancia` |
| eproc: CAPTCHA | ❌ presente (`hdnInfraCaptcha`) |
| TJAL migrou? | **Não** — `eproc1g.tjal.jus.br` responde 403 e o e-SAJ segue com `DOCPARTE` |

**Não há caminho lícito por CPF para processo novo em SP.** Impacto na carteira: 21 dos 358 clientes (6%). A cobertura do e-SAJ por CPF cai de 83% para **78%** (278 clientes), sustentada por Alagoas.

---

## 3. Objetivo B: como foi resolvido

### 3.1 Por que o DataJud não serve

Levantei os códigos de movimento por amostragem de 600 processos de classe 81:

| Código | Movimento | Serve? |
|---|---|---|
| **60** + complemento `tipo_de_documento = Mandado` | Expedição de documento | ✅ sinal preciso de mandado |
| 106 / 985 | Mandado (106 tem `resultado = entregue / não entregue`) | ✅ cumprimento |
| **339** | **Liminar** | ⚠️ **não diz se foi deferida ou indeferida** |
| 332 | Antecipação de tutela | ⚠️ idem |

Somado ao atraso de 1 a 2 meses, o DataJud fica como conferência e histórico — nunca como alerta.

### 3.2 O DJEN serve, e o texto é explícito

Em **um único dia** no TJAL (14/08/2026): 215 publicações de classe 81, com **31 liminares deferidas** e **47 mandados**.

> *"com base no art. 3º do Decreto-lei n.º 911/69, **concedo liminarmente a BUSCA E APREENSÃO** do veículo descrito na inicial"*
>
> *"AUTOR: Banco Honda S/A. — **Expeça-se novo mandado** de busca e apreensão"*

### 3.3 O ganho decisivo: consultar por NÚMERO

Consultar por número **contorna o cego estrutural** relatado na carga inicial. Quando a intimação é dirigida só ao advogado do banco — justamente o caso da primeira decisão, a liminar — o nome do cliente não aparece nem nos destinatários nem no texto, e nenhuma busca por nome a encontra. **Pelo número, encontra.**

Os dois objetivos, portanto, se completam: o A detecta o processo novo, o B vigia o que já se conhece sem depender do nome.

---

## 4. O classificador e os falsos positivos que ele evita

`src/servicos/classificador_movimentos.py` lê o inteiro teor e devolve:

`LIMINAR_DEFERIDA` · `LIMINAR_INDEFERIDA` · `MANDADO_EXPEDIDO` · `MANDADO_CUMPRIDO` · `VEICULO_APREENDIDO` · `CITACAO`

Validado contra 60 publicações reais. Encontrou **dois falsos positivos** que teriam virado alerta urgente indevido:

| Texto real | Lido errado como | Correção |
|---|---|---|
| *"sob pena de o Oficial de Justiça devolver o mandado, **se não cumprido** em trinta dias"* | mandado cumprido | veto de negação |
| *"tornando definitiva a **liminar outrora concedida**"* (sentença) | liminar nova | veto de anterioridade |

Ambos barrados sem perder nenhuma detecção verdadeira. O indeferimento é sempre avaliado **antes** do deferimento, senão *"INDEFIRO o pedido de liminar"* cairia na regra errada.

---

## 5. Baseline: 216 processos, 365 dias

```
Processos consultados : 216
Menções encontradas   : 352
Fatos distintos       : 288
Processos com evento  : 126 de 216
Erros                 : 0
```

| Evento | Fatos | |
|---|---|---|
| **LIMINAR_DEFERIDA** | **87** | 🚨 |
| **MANDADO_EXPEDIDO** | **82** | 🚨 |
| MANDADO_CUMPRIDO | 31 | 🚨 |
| VEICULO_APREENDIDO | 24 | 🚨 |
| CITACAO | 56 | |
| LIMINAR_INDEFERIDA | 8 | |

### Um defeito corrigido no caminho

A primeira versão avisava **352 vezes** — porque uma liminar deferida é mencionada de novo em cada despacho seguinte, e cada menção virava alerta. Um processo antigo dispararia o mesmo aviso cinco vezes.

Agora o histórico registra **cada menção** (serve para a linha do tempo do processo), mas o aviso sai **uma vez por processo e por tipo de evento**: 352 menções → **288 avisos**.

---

## 6. Como usar

```bash
python3 executar.py acompanhar --dias 7      # rotina
python3 executar.py acompanhar --dias 365    # refazer o histórico
python3 executar.py acompanhar --dias 7 --limite 20   # teste rápido
```

Custo: **uma requisição por processo**. Com 216 processos a 10 req/min, a rotina leva ~22 minutos.

---

## 7. Situação das duas frentes

| Objetivo | Estado | Cobertura |
|---|---|---|
| **A — B&A nova por CPF** | ⏸️ pronto, **desligado** aguardando análise dos Termos de Uso | 278 clientes (78%) — AL, CE, AM |
| **A — B&A nova em SP** | ❌ sem caminho lícito após a migração para o eproc | 21 clientes (6%) |
| **B — Liminar / mandado** | ✅ **funcionando** | 216 processos, imune ao cego estrutural |

**181 testes passando**, nenhum tocando a rede.
