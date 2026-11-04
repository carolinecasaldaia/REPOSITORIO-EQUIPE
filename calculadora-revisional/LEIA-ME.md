# Calculadora Revisional

Anexe o contrato bancário em PDF, informe quantas parcelas o cliente pagou e quantas
estão em atraso. A página devolve os mesmos números da planilha de cálculo do escritório.

Quando o cliente **não tem o contrato**, clique em *Não tenho o contrato* e digite os
dados que ele informar: o cálculo é exatamente o mesmo.

## Como abrir

Clique duas vezes em **Calculadora Revisional.command**.

Na primeira vez ele cria um atalho chamado *Calculadora Revisional* na sua Área de
Trabalho — depois disso, é só clicar nesse atalho. Deixe a janela preta aberta enquanto
estiver usando; ao terminar, pressione Enter nela para fechar.

Não precisa de internet. O contrato é lido dentro do seu computador e não sai daqui.

## Como usar — com o contrato

1. **Anexe o contrato** — arraste o PDF ou clique para escolher.
2. **Confira os dados** — o que foi lido do contrato aparece marcado em verde embaixo de
   cada campo. O que está em amarelo é estimativa minha: confira com atenção. Qualquer
   campo pode ser corrigido à mão.
3. **Informe as parcelas pagas.** As parcelas em atraso vêm sugeridas pelas datas do
   contrato — corrija se o cliente disser outra coisa.
4. **Leia os resultados** à direita.

## Como usar — sem o contrato

Clique em **Não tenho o contrato**, no alto da coluna da esquerda. A área de anexar o PDF
sai da frente e entra a lista do que perguntar ao cliente. Peça o carnê, o boleto ou o
extrato do app do banco e digite:

- valor do veículo e valor da entrada;
- valor da parcela e quantidade de parcelas;
- data do 1º vencimento;
- quantas parcelas já pagou e quantas estão em atraso;
- parcela balão, se houver, e se ela já foi paga.

Enquanto faltar algum dos três campos essenciais (valor do veículo, valor da parcela e
quantidade de parcelas), o painel da direita diz exatamente o que falta. Assim que os três
estiverem preenchidos, os números saem sozinhos — iguais aos da leitura automática.

**Se o cliente só souber quanto financiou:** no campo *Como você tem o valor financiado*,
troque para **Sei só quanto foi financiado**. Os campos de veículo e entrada dão lugar a um
único campo de valor financiado, e é esse número que entra na conta. Na planilha exportada,
"Valor do Bem" e "Valor da Entrada" saem como *não informado* — o resto vem completo.

O texto do WhatsApp muda sozinho nesse caso: em vez de "a partir do contrato apresentado",
ele diz que os valores vêm das informações prestadas pelo cliente e ficam sujeitos à
conferência do contrato.

Se o PDF anexado não abrir (contrato escaneado, protegido por AES-256 ou ilegível), o aviso
traz um botão **Preencher à mão** que já leva para esse modo.

Os percentuais (30% de previsão de acordo, 16% de honorários contratuais e 1% no depósito
judicial) já vêm no padrão do escritório e podem ser alterados caso a caso.

Os honorários são sempre os **16% contratuais sobre o valor residual do valor total do
contrato** — o mesmo número na previsão e no fechamento. Ele não muda conforme o valor do
acordo.

## O que sai daqui

- **Baixar planilha** — arquivo `.xlsx` com três abas (Planilha de Cálculo, Acordo e
  Honorários, Cronograma), nos mesmos lugares da planilha que você já usa. Salve na pasta
  do cliente.
- **Copiar resumo** — texto pronto para mandar no WhatsApp da lead.
- **Copiar todos os números** — para colar onde quiser.
- **Imprimir / salvar em PDF** — versão limpa, sem os botões.

## Contrato protegido por senha

Se o PDF pedir senha, aparece um campo para digitá-la. Costuma ser o CPF do cliente (só
os números) ou vir escrita no nome do arquivo. Contratos com proteção AES-256 não abrem
por aqui: abra no Adobe Reader, salve uma cópia sem senha e anexe de novo.

## Contrato digitalizado

Se o contrato for foto ou scan, não existe texto para ler — a página avisa, oferece o botão
*Preencher à mão* e você digita os campos. Todo o resto continua funcionando igual.

## Bancos testados

Aymoré, Banco Honda, Banco PAN e Banco Safra, que têm layouts de contrato bem diferentes
entre si. O Safra traz as parcelas balão discriminadas e elas são reconhecidas sozinhas.
Se algum contrato de outro banco não for lido direito, me mande o arquivo que eu ajusto.

## Uma diferença que vale saber

O **valor financiado** aqui segue a fórmula do escritório: valor do veículo menos a
entrada. O valor financiado que consta no contrato (já com IOF e tarifas embutidos) é
maior, e aparece à parte, como informação — é justamente essa diferença que interessa
na revisional.

## Também existe na web

A mesma página está publicada em
https://claude.ai/code/artifact/fc7da8fd-ca66-4c1d-aeec-8e790afac4de
para abrir do celular ou de outro computador. Lá o download sai como `.csv` em vez de
`.xlsx`, por limitação da plataforma — o Excel abre normalmente.

## Arquivos desta pasta

- `Calculadora Revisional.command` — o atalho que você clica.
- `calculadora_revisional.html` — a página em si (funciona sozinha).
- `_abrir_calculadora.py` — abre a página em http://127.0.0.1 (o caminho da pasta do
  Drive tem "@" e espaço no fim, e vários navegadores não conseguem abrir por `file://`).
- `_fontes/` — o código separado em partes, com o `build.py` que remonta a página.
