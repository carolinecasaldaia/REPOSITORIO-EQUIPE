# Cumprimento / liquidação de sentença revisional (sem perito)

```
uv run python ferramentas/baixar_series_bcb.py CASO/indices INPC=188 SELIC=4390 --desde 01/01/2019
uv run cm-calc cumprimento CASO/ficha.json --indices CASO/indices --saida CASO/saida
```

Saída: `memoria-<caso>-<data>.xlsx` (Resumo, AP01, AP02, AP03, Verbas, Memória, Ressalvas), `.md` e `.json`.
Pasta do caso: `~/CM-Calculos-Dados/cumprimento/<CASO>/` (dados de cliente nunca no repositório).

## Regras

- Só ENTRADAS na ficha. Cada critério do título leva `fonte` com `documento`, `localizacao` (fls.) e
  `trecho` LITERAL do dispositivo — sem trecho, o cálculo é recusado.
- Nada tem padrão: índice, termo inicial, citação, dobra, reforçadas, encargos, base de honorários.
  Se o título não diz, é decisão da advogada (registrar no trecho: "definido pela Dra. Caroline").
- Pagamentos vêm de documento (demonstrativo do banco, extratos, boletos), nunca presumidos.

## Campos

| Bloco | Campos |
|---|---|
| raiz | `caso`, `responsavel`, `data_base` (DD/MM/AAAA), `arredondamento` (`2;HALF_UP;por_parcela`) |
| `contrato` | `data_liberacao`, `valor_financiado`, `taxa_mensal`, `taxa_anual`, `regime` (composto/simples), `convencao` (`meses_30` = capitalização diária dias/30 · `meses_civis` = mensal · `dias_base_360/365`), `parcela_regular`, `parcelas` [{`numero`, `vencimento`, `valor_fixo` só nas reforçadas}], `fonte` |
| `revisao` | `taxa_mensal` / `taxa_anual` (do título: contratada, ou média BACEN — regra do escritório: financiamento de bens, mês da assinatura do contrato, SGS 25471 mensal e SGS 20749 anual), `regime` (simples se o título afastou a capitalização), `convencao`, `tratamento_reforcadas` (`proporcional` / `manter_valor`), `itens_excluidos` [{`descricao`, `valor`, `financiado`, `data_pagamento` se pago à parte, `fonte`}], `fonte` |
| `restituicao` | `modalidade` (`simples` / `dobro` / `dobro_a_partir_de` + `data_corte`), `fonte` |
| `pagamentos` | [{`numero`, `data`, `valor` (com encargos), `encargos`, `antecipada_com_desconto`, `fonte`}] |
| `encargos_contrato` | `multa`, `juros_mora_mensal`, `contagem` — obrigatório se houver encargos pagos |
| `descaracterizacao` | `componentes_afastados` (multa, juros_mora, juros_remuneratorios_mora, comissao_permanencia), `desde`, `ate`, `fonte` |
| `atualizacao` | `fases` [{`fim` (data ou `data_base`), `descricao`, `correcao` (INPC/IPCA/null), `juros` {`tipo` percentual_fixo/serie, `percentual_mensal`, `inicio`, `contagem`, `serie`}, `incluir_mes_inicial`, `incluir_mes_final`, `acumulacao_juros` (soma/produto), `juros_desde_antes_do_valor`}], `fonte` |
| `verbas` | [{`descricao`, `valor_fixo` ou `percentual`+`valor_base`, `data_base_verba`, `atualizacao` (mesmo formato), `fonte`}] — dano moral, dano material, multa do art. 3º, §6º, DL 911/69… |
| `honorarios` | `base` (valor da condenação / proveito econômico / valor atualizado da causa / valor fixo), `percentual`, `valor_base` (se não for a condenação), `cota_devedor`, `devedor`, `fonte` |

## Exemplo típico de fases (TJAL)

"juros de mora de 1% a.m. desde o vencimento da 1ª prestação e correção pelo INPC desde o pagamento,
até a citação; depois, só a SELIC":

```json
"atualizacao": {"fases": [
  {"fim": "07/02/2025", "descricao": "INPC + mora 1% a.m. até a citação", "correcao": "INPC",
   "juros": {"tipo": "percentual_fixo", "percentual_mensal": "1", "inicio": "11/05/2019", "contagem": "meses_civis"},
   "incluir_mes_inicial": false, "incluir_mes_final": true, "acumulacao_juros": "soma",
   "juros_desde_antes_do_valor": true},
  {"fim": "data_base", "descricao": "Selic após a citação", "correcao": null,
   "juros": {"tipo": "serie", "serie": "SELIC"},
   "incluir_mes_inicial": false, "incluir_mes_final": false, "acumulacao_juros": "produto"}],
 "fonte": {"documento": "Acórdão …", "localizacao": "fls. …", "trecho": "…"}}
```

Convenções de meses acima = as da perita no caso validado (VAL-001): INPC sem o mês do pagamento e com o
da citação; Selic sem o mês inicial nem o final. Outra convenção só com fundamento.

## Validação

Caso VAL-001 (parecer pericial real, capitalização diária afastada): o motor reproduziu ao centavo as
prestações do AP01 (diária) e do AP02 (mensal), os 60 fatores de INPC e o fator SELIC. As diferenças no
total vieram de inconsistências do próprio parecer (soma da tabela ≠ total declarado, citação e pagamentos
presumidos).
