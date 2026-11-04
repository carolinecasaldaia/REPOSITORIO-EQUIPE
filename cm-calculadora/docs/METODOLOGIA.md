# Metodologia do motor matemático — v0.3.0 (Fase 2 complementada)

## 1. Precisão e arredondamento

| Item | Regra |
|---|---|
| Tipo numérico | `decimal.Decimal` em todo o motor. `float` é recusado (`D(0.1)` → erro) e um teste impede `float(` e `math` no código do motor. |
| Precisão interna | 34 dígitos significativos (decimal128). Intermediários não são arredondados. |
| Política | `PoliticaArredondamento(casas, modo, arredondar_cada_parcela)`, declarada por caso e impressa em cada passo da memória. Não há política implícita. |
| Modos | `HALF_UP` (meio para cima), `HALF_EVEN` (meio para o par), `DOWN` (truncar), `UP`. |
| Por parcela | `arredondar_cada_parcela=True` arredonda juros de cada evento/parcela ao centavo (como os sistemas bancários). `False`: só o resultado. |
| Resíduo | O resíduo final da tabela (efeito do arredondamento da prestação) **não** é absorvido na última parcela: vira ressalva de divergência. |
| Limite | Até 20 casas, para caber na precisão interna. |

## 2. Taxas e tempo

- **Composto:** taxas equivalentes, `(1+ia) = (1+im)^12`; fator `(1+i)^t`.
- **Simples:** taxas proporcionais, `ia = 12·im`; fator `1 + i·t`.
- **Convenção de tempo** (obrigatória, por caso):
  - `meses_civis`: meses de calendário completos + dias/30;
  - `meses_30`: dias corridos/30;
  - `dias_base_360` / `dias_base_365`: dias corridos, com taxa diária equivalente à anual.
- O fator composto não depende do fracionamento: capitalizar em etapas dá o mesmo que de uma vez (há teste de propriedade para isso).

## 3. Prestação (AP01/AP02)

Equivalência na data da liberação:

    VF = Σ R/F(lib, vk)  +  Σ Pj/F(lib, vj)     ⇒     R = (VF − Σ Pj/Fj) / Σ 1/Fk

Cobre Price mensal, capitalização diária, carência, parcelas reforçadas, intercaladas ou balão (valores fixos) e juros simples com desconto racional por parcela.
Também estão implementados o coeficiente Price `i/(1−(1+i)^−n)`, SAC e Gauss `VF(1+in)/[n(1+i(n−1)/2)]`. O Gauss só deve ser usado se o título o determinar.

## 4. Conta gráfica (evolução do saldo)

O saldo fica em duas contas: `capital` e `juros_pendentes`. Os juros de cada intervalo incidem sobre:
- capital + juros pendentes (composto); ou
- só o capital (simples, sem juros sobre juros).

Cada pagamento é imputado na ordem declarada (juros→capital ou capital→juros); não há padrão. Pagamento acima do saldo vira `excedente`, que não rende a taxa do contrato.
Identidades verificadas em toda execução: `pago = juros pagos + amortização + excedente` e `inicial + juros − juros pagos − amortização = saldo final`.

## 5. Revisão (AP02)

- Taxa revisada, regime e convenção vêm do título, com a origem registrada.
- Itens excluídos (tarifas e seguros), cada um com citação do título:
  - financiados saem do valor financiado;
  - pagos à parte viram indébito na data do pagamento.
- O IOF reflexo **não** é excluído por presunção (gera pendência).
- Com parcelas reforçadas, é obrigatório escolher entre `manter_valor` e `proporcional`.

## 6. Encargos e descaracterização da mora

- Os encargos de atraso são calculados por componente: multa, juros de mora, remuneratórios na mora e comissão de permanência.
- A descaracterização zera **só** os componentes listados no título, no período indicado.
- Restituição do veículo, perdas e danos, multas e devolução de parcelas **nunca** decorrem automaticamente. Só entram como `VerbaAutorizada`, que exige o trecho literal do título.

## 7. Diferenças (AP03), indébito e atualização

- Para cada pagamento: diferença = (parcela paga + encargos pagos) − (parcela revisada + encargos revisados devidos).
- **Diferença positiva:** restituição simples, em dobro ou em dobro a partir de uma data de corte, conforme o título. Depois, atualização.
- **Diferença negativa:** listada à parte, sem atualização automática (pendência).
- **Atualização:**
  - valor corrigido = `V × Π(1+índice mensal)`;
  - juros = valor corrigido × Σ% (soma) ou × (Π(1+%)−1) (produto);
  - índice, termo inicial dos juros, inclusão do mês inicial/final e forma de acumulação são parâmetros obrigatórios.
- **Proteções da atualização:**
  - cada mês pertence a um único critério (o vigente no dia 1º), para não contar o mês de transição duas vezes;
  - uma série que já embute correção (ex.: Selic) não pode ser cumulada com índice de correção no mesmo mês;
  - índice ausente interrompe o cálculo: o motor não estima nem interpola.

## 8. Compensação e honorários

- **Compensação:** só entre valores na mesma data-base.
- **Honorários:** base (condenação, proveito econômico, valor da causa ou valor fixo), percentual e cota (sucumbência recíproca) vêm do título. O valor da base é informado, não deduzido.

## 9. Auditoria

Cada resultado gera um `Passo` com etapa, descrição, fórmula, entradas, resultado, origem documental e data de referência. As ressalvas são de quatro tipos: pendência, divergência, alerta e premissa.

## 10. Composição do financiamento e CET (v0.3.0)

- `valor financiado = valor liberado + Σ itens financiados` (IOF, tarifas, seguros, serviços, outros). Itens pagos à vista ficam em separado, com data.
- Se o valor financiado declarado no contrato não bater com a soma dos componentes, gera ressalva de divergência. O motor não ajusta para fechar.
- **Exclusões do título, com um único destino por item:**
  - item financiado sai do valor financiado do AP02 e é devolvido pela redução das parcelas, inclusive dos juros que incidiam sobre ele;
  - item à vista vira indébito avulso no AP03.
- **Controle de duplicidade** (`ControleUtilizacao`): recusa que o mesmo item ou crédito seja excluído, restituído ou compensado duas vezes.
- **CET:** referência na Res. CMN 3.517/2007 (**conferir o texto oficial**).
  - Fórmula: `FC0 = Σ FCj/(1+CET)^((dj−d0)/365)`.
  - FC0 = valor liberado menos as despesas pagas à vista no ato.
  - A taxa é obtida por bisseção, com precisão melhor que 1e-18.
  - Se o CET calculado diferir do declarado no contrato, gera ressalva de divergência.

## 11. Veículo: venda, multa do DL 911/1969 e perdas e danos (v0.3.0)

- **Saldo após a venda** (todas as posições na data da alienação):
  `saldo revisado + despesas comprovadas − venda − créditos do consumidor`.
  - Despesas só entram se o título mandar abatê-las **e** se estiverem comprovadas.
  - Créditos do consumidor só entram se o título mandar compensá-los ali.
  - Resultado positivo é saldo remanescente do consumidor; negativo, valor a restituir a ele.
  - A comparação entre venda e FIPE é só informativa: o motor não emite juízo sobre o preço.
- **Multa do art. 3º, §6º, do DL 911/1969** (redação da Lei 10.931/2004, **conferir o texto oficial**):
  - exige trecho do título;
  - exige improcedência da busca e apreensão e bem alienado, ou confirmação expressa da advogada;
  - percentual e base vêm do título; se o percentual diferir de 50%, gera divergência;
  - o que é "valor originalmente financiado" fica sempre como pendência de confirmação.
- **Perdas e danos (FIPE):**
  - valor FIPE informado com mês de referência e fonte, sem consulta automática;
  - deduções conforme o título;
  - atualização pelos critérios informados;
  - a cumulação com a multa gera ressalva (premissa).
- A descaracterização da mora não aciona nenhum desses cálculos.

## 12. Aperfeiçoamentos após a validação VAL-001 (v0.6.7)

- **Políticas de arredondamento** (`casas;modo;quando`):
  - `por_parcela`: prestação e juros de cada evento arredondados ao centavo;
  - `final`: só o resultado final, mas a prestação é cobrável ao centavo;
  - `integral`: nada é arredondado antes do resultado final, nem a prestação.
- **Juros anteriores ao pagamento** (`juros_desde_antes_do_valor`): só quando o título determina, com o trecho citado; gera ressalva. O padrão continua sendo contar juros a partir da data do valor.
- **Fases consolidadas** (`atualizar_por_fases`): ao fim de cada fase, corrigido + juros viram a base da fase seguinte (por exemplo, INPC + mora até a citação e depois Selic sobre o subtotal).
  - Em precisão integral, a base segue exata.
  - Com `por_parcela`, a base é o total arredondado da fase.
