# Gerador de Onboarding

Lê o contrato de prestação de serviços assinado e preenche sozinho o onboarding
do cliente, gravando o PDF na subpasta **ONBOARDING** da pasta do cliente.

Substitui o preenchimento manual do formulário do `gerador_pdf.html`.

## Como usar

1. Dê **dois cliques** em **Gerar Onboarding do Cliente** (na Área de Trabalho).
2. Aperte **Enter** para o cliente mais recente, ou digite o número de outro da
   lista — ou arraste a pasta do cliente para a janela.
3. Confira os dados que ele leu do contrato.
   - Para corrigir qualquer campo, digite o **número** dele e o novo valor.
   - Nas **buscas e apreensões** ele pergunta o banco adverso, porque esse dado
     não consta no contrato.
4. Aperte **Enter** para gerar. O PDF sai em
   `<pasta do cliente>/ONBOARDING/onboarding_<nome>.pdf`.

Na primeira vez o programa se prepara sozinho (precisa de internet só nessa vez).

> Se o macOS avisar que "não pode ser aberto porque é de um desenvolvedor não
> identificado": clique com o botão direito no arquivo → **Abrir** → **Abrir**.
> Isso só acontece uma vez.

## O que ele lê do contrato

| Campo | De onde vem |
|---|---|
| Primeiro nome | nome do Cliente Contratante (preâmbulo) |
| Serviço | Cláusula 1ª — "Ação Revisional" ou "Busca e Apreensão" |
| Banco adverso | Cláusula 1ª — "em desfavor do Banco ..." |
| Veículo | Cláusula 1ª — "referente ao contrato do veículo ..." |
| Entrada e data | Cláusula 2ª — "Entrada no valor de ... na data de ..." |
| Parcelas, 1ª e última | Cláusula 2ª — "N (...) parcelas de ... com início em ... e a última em ..." |
| Total dos honorários | Cláusula 2ª — "a importância de ..." |
| Forma de pagamento | Cartão se o contrato disser "CARTÃO DE CRÉDITO NA RECORRÊNCIA"; senão Boleto |

Quando o contrato divide o parcelamento em dois valores diferentes, ele soma as
quantidades e descreve os dois — igual era feito à mão
(ex.: `01 de R$ 563,35 e 14 de R$ 413,35`).

**O banco não aparece nos contratos de busca e apreensão.** Nesses casos o
programa pergunta na hora.

**Sempre confira os dados na tela antes de gerar.** O que estiver na tela é
exatamente o que vai para o PDF.

## De onde vem o desenho do PDF

Do próprio `gerador_pdf.html` (a pasta acima desta). O programa abre aquela
página num navegador invisível, preenche os campos e recolhe o PDF pronto —
por isso o resultado é idêntico ao do preenchimento manual, e **qualquer
mudança que você fizer no `gerador_pdf.html` passa a valer aqui também**.

Precisa do **Google Chrome** instalado (ou Edge/Brave/Chromium). Nada é enviado
para a internet: o documento do cliente não sai da máquina.

## Uso pela linha de comando (opcional)

```bash
~/.gerador-onboarding/venv/bin/python "gerar_onboarding.py" --help
```

| Opção | Para que serve |
|---|---|
| `--listar` | Só mostra o que foi lido do contrato, não gera nada |
| `--sobrescrever` | Substitui o onboarding existente em vez de criar `(2)` |
| `--saida ARQUIVO` | Grava o PDF nesse caminho em vez da subpasta ONBOARDING |

## Se algo sair errado

- **"Não achei o PDF do contrato"**: o contrato precisa estar na subpasta
  `CONTRATO HO` do cliente. Se ainda não estiver separado, rode antes o
  **Separar Documentos do Autentique**.
- **Campos em branco / "não consegui ler o texto deste contrato"**: o PDF é
  digitalizado (imagem, sem texto). Dá para preencher tudo à mão na tela.
- **Veículo com letras separadas** (ex.: `COMPASS LON G T`): é assim que o texto
  está dentro do PDF do contrato. Corrija pelo número 4.
- **"não encontrei o Google Chrome"**: instale o Chrome (gratuito) em
  https://www.google.com/chrome.
- **Arquivo já existente não é sobrescrito**: o novo sai como `... (2).pdf`.
