# Meta Ads

Gerencia as campanhas do Facebook/Instagram do escritório pela Marketing API do
Meta. Usa só o Python que já vem no Mac (nada para instalar).

## Onde fica cada coisa

| O quê | Onde |
|---|---|
| Código | esta pasta (`executar.py`, `src/meta.py`) |
| Token e conta padrão | `~/.meta-ads/.env` (permissão 600, fora do Git e do Drive) |
| Histórico de toda alteração feita | `~/.meta-ads/historico.log` |

O token é do **System User "AUTOMAÇÕES"** (app `automacoes`): não expira e tem
`ads_management`, `ads_read`, `pages_manage_ads`, `business_management` e WhatsApp.
Para trocá-lo: `python3 executar.py chave` (abre uma janela oculta, valida e grava).

## Consultar (não muda nada)

```bash
python3 executar.py testar                       # o token está ok?
python3 executar.py contas                       # contas de anúncios e páginas
python3 executar.py campanhas                    # --todas inclui arquivadas
python3 executar.py conjuntos --campanha ID
python3 executar.py anuncios  --conjunto ID
python3 executar.py desempenho                   # últimos 7 dias, por campanha
python3 executar.py desempenho --periodo last_30d --nivel ad
python3 executar.py desempenho ID --desde 2026-10-01 --ate 2026-10-31 --diario
```

Em "resultados" aparecem **leads** e **conversas** (WhatsApp/Direct), com o
custo de cada um.

## Alterar

Toda alteração mostra antes o que vai mudar e pede `s` para confirmar
(`--sim` pula a pergunta). Tudo que é criado nasce **pausado**.

```bash
python3 executar.py pausar ID [ID ...]           # campanha, conjunto ou anúncio
python3 executar.py ativar ID [ID ...]
python3 executar.py orcamento ID --diario 80     # em reais; ou --total 1500
python3 executar.py renomear ID "Novo nome"
python3 executar.py duplicar ID                  # cópia completa, pausada
python3 executar.py criar-campanha --nome "[FORMS] Revisional" --objetivo OUTCOME_LEADS --diario 50
```

Outra conta: acrescente `--conta act_485095314294256`.

## Observações

- Um anúncio só roda se a campanha **e** o conjunto dele também estiverem ativos.
- O orçamento fica na campanha (CBO, como em `[C1]`/`[C2]`/`[C3]`) **ou** nos
  conjuntos (ABO, como em `[FORMS]`/`[Whatsapp]`). O comando avisa se você
  mexer no nível errado.
- Anúncio de **crédito/financiamento** pode exigir a categoria especial
  `FINANCIAL_PRODUCTS_SERVICES` (`criar-campanha ... --categoria-especial FINANCIAL_PRODUCTS_SERVICES`).
