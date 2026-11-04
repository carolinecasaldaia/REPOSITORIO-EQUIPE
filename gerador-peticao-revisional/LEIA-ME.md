# Gerador de Petição Inicial — Ação Revisional

Preenche a petição inicial da revisional a partir dos dados básicos do cliente,
já no modelo e no timbrado do escritório.

## Como usar

1. Dois cliques em **Gerar Petição Revisional** (na Área de Trabalho ou nesta pasta).
   Na primeira vez o macOS avisa que o arquivo veio da internet — clique com o
   **botão direito → Abrir** e confirme. Depois disso o duplo clique funciona normal.
2. O formulário abre no navegador. Preencha os dados, marque as teses do caso.
3. **Gerar petição** — o `.docx` cai na pasta Downloads, com o nome
   `Petição Inicial - Revisional - <Banco> - <CLIENTE>.docx`.
4. Abra no Word, cole os prints das cláusulas nos pontos marcados em vermelho e revise.

O rascunho fica guardado no navegador: se fechar a página no meio, ao reabrir os
dados continuam lá. Nada sai do computador — não há site nem servidor envolvido.

## O que o gerador calcula sozinho

| Campo | Cálculo |
|---|---|
| Parcelas restantes | nº de parcelas − parcelas pagas |
| Total já pago | valor da parcela × parcelas pagas |
| Saldo devedor | valor da parcela × parcelas restantes |
| Parcela cobrada a maior | (parcela − parcela incontroversa) ÷ parcela |
| Juros acima do Bacen | taxa do contrato − taxa média Bacen (mensal e anual) |
| Acréscimo sobre o liberado | (total financiado − valor liberado) ÷ valor liberado |
| Total incontroverso | parcela incontroversa × parcelas restantes |
| Valor da causa | total incontroverso (pode ser sobrescrito no campo) |
| Valores por extenso | todos, em português |

O **quadro do contrato** monta só as linhas que você preencheu — se o contrato não
tem seguro, a linha do seguro não aparece.

A **numeração romana** dos tópicos do capítulo “DO DIREITO” se refaz sozinha
conforme as teses marcadas.

## As teses (o que entra e o que sai)

| Tese | Fundamento | Quando marcar |
|---|---|---|
| Capitalização diária | Tema 28 do STJ · REsp 1.826.463/SC | contrato prevê capitalização diária sem taxa do dia |
| Juros acima da média Bacen | Tema 28 · REsp 1.061.530/RS | taxa do contrato acima da média divulgada pelo Bacen |
| Juros de mora acima de 1% a.m. | Súmula 379 do STJ | contrato prevê mora superior a 1% ao mês |
| Tarifa de avaliação | Tema 958 do STJ | cobrada tarifa de avaliação |
| Encargos abusivos / venda casada | Tema 972 do STJ | há seguro, tarifa de cadastro ou registro |
| Seguro prestamista | Tema 972 do STJ | tópico específico do seguro (junto com a de cima) |
| Da competência | art. 101, I, do CDC | cliente de outro estado / foro do domicílio do réu |
| Da renegociação | Súmula 286 do STJ | contrato veio de refinanciamento ou confissão de dívida |

Também dá para escolher entre **depósito integral** e **depósito do valor incontroverso**
— o texto da tutela e dos pedidos muda junto.

## Cadastro de bancos

O menu de bancos já vem com BV, PAN e Volkswagen com os dados exatos que o
escritório usou nas iniciais anteriores. Os demais vêm com o endereço, mas
**sem CNPJ** — confira o CNPJ da matriz antes de protocolar e clique em
**Salvar este banco na lista** para que ele fique pronto na próxima vez.

## Alterar o modelo

O texto todo mora em **MODELO MESTRE - AÇÃO REVISIONAL.docx**, nesta pasta.
Abra no Word, altere jurisprudência, redação, o que quiser, e salve.
Da próxima vez que abrir o gerador pelo atalho, a página já usa a versão nova.

No modelo você vai ver:

- `{{CAMPO}}` — lugar que o gerador preenche (ex.: `{{AUTOR_NOME}}`).
  **Não quebre esses códigos ao editar** — se o Word dividir um deles no meio,
  ele deixa de ser preenchido e aparece no aviso de "campos em branco".
- `[[+TESE]]` … `[[-TESE]]` em vermelho — início e fim de um bloco opcional.
  Tudo entre os dois só entra se a tese estiver marcada no formulário.
- Textos em vermelho `[INSERIR AQUI O PRINT ...]` — onde colar as imagens das cláusulas.

Se quiser **acrescentar uma tese nova**, escreva o texto entre marcadores novos
(`[[+MINHATESE]]` … `[[-MINHATESE]]`) e peça para incluir a caixinha no formulário.

## Arquivos da pasta

| Arquivo | Para que serve |
|---|---|
| `Gerar Petição Revisional.command` | o atalho de dois cliques |
| `gerador_peticao.html` | o formulário (funciona sozinho, sem internet) |
| `MODELO MESTRE - AÇÃO REVISIONAL.docx` | **o modelo — é aqui que se edita o texto** |
| `_embutir_modelo.py` | leva o modelo para dentro da página (roda sozinho) |
| `_construir_modelo.py` / `_conteudo_modelo.py` | reconstroem o modelo do zero; não precisa mexer |

## Antes de protocolar — sempre conferir

- CNPJ e endereço da **matriz** do banco (é onde a citação eletrônica funciona)
- Os prints das cláusulas colados nos pontos em vermelho
- A jurisprudência estadual: o modelo traz ementas do **TJ-AL** e do STJ. Em ação
  de outro estado, vale trocar as do TJ-AL por precedentes do tribunal local
- Valor da causa e o valor incontroverso conferidos com a planilha
