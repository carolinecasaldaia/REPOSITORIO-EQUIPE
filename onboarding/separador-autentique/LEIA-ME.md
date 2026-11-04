# Separador de Documentos do Autentique

Substitui o passo manual no iLovePDF. Pega o PDF único baixado do Autentique e
grava cada documento em arquivo separado, já com o relatório de assinaturas
anexado ao final de cada um — exatamente como era feito à mão.

## Como usar

1. Baixe o PDF assinado do Autentique (vai para a pasta **Downloads**).
2. Dê **dois cliques** em `Separar Documentos.command`.
3. Aperte **Enter** para usar o PDF mais recente (ou digite o número de outro da lista).
4. Confira a estrutura que aparece na tela.
5. **Arraste a pasta do cliente** para a janela do Terminal e aperte Enter
   (ou só Enter para criar uma pasta `SEPARADOS - ...` em Downloads).
6. Enter para confirmar. Pronto.

Na primeira vez o programa se prepara sozinho (precisa de internet só nessa vez).

> Se o macOS avisar que "não pode ser aberto porque é de um desenvolvedor não
> identificado": clique com o botão direito no arquivo → **Abrir** → **Abrir**.
> Isso só acontece uma vez.

## O que ele gera

| Documento | Arquivo | Vai para |
|---|---|---|
| Contrato de Prestação de Serviços | `Contrato HO Assinado.pdf` | `CONTRATO HO` |
| Procuração | `Procuracao Assinada.pdf` | `DOC ESCRITÓRIO` |
| Declaração de Hipossuficiência | `Declaracao de Hipo Assinada.pdf` | `DOC ESCRITÓRIO` |
| Declaração de Residência (quando houver) | `Declaracao de Residencia Assinada.pdf` | `DOC ESCRITÓRIO` |

As subpastas só são usadas se já existirem na pasta do cliente. Ele também
reconhece as grafias antigas (`CONTRATO DE HONORÁRIOS`, `DOC CLIENTE` etc.).
Se a pasta escolhida não tiver nenhuma dessas subpastas, os arquivos ficam
soltos dentro dela.

Arquivo já existente **não é sobrescrito**: o novo sai como `... (2).pdf`.

## Como ele decide onde cortar

Não usa número fixo de páginas — lê o texto de cada página:

- Começo de documento: título na primeira linha da página
  (`CONTRATO DE PRESTAÇÃO DE SERVIÇOS`, `PROCURAÇÃO`,
  `DECLARAÇÃO DE HIPOSSUFICIÊNCIA`, `DECLARAÇÃO DE RESIDÊNCIA`).
- Relatório de assinaturas: página que começa com `Identificador:` e cita
  `autentique.com.br` — dali até o fim.
- A folha avulsa "Assinado com Assinatura Eletrônica / Hash SHA256" é
  descartada, porque esse conteúdo já está no relatório de assinaturas
  (mesmo critério usado na separação manual).

Por isso funciona com contrato de 4, 5, 9, 10 ou 12 páginas, e com 3 ou 4
documentos no mesmo envelope.

**Sempre confira a estrutura mostrada na tela antes de confirmar.**

## Uso pela linha de comando (opcional)

```bash
~/.separador-autentique/venv/bin/python "separar_autentique.py" --help
```

| Opção | Para que serve |
|---|---|
| `--listar` | Só mostra a estrutura detectada, não grava nada |
| `--destino PASTA` | Define a pasta do cliente |
| `--sem-relatorio` | Não anexa o relatório de assinaturas aos documentos |
| `--manter-validacao` | Mantém a folha de hash/validação avulsa |
| `--sobrescrever` | Substitui arquivos já existentes no destino |

## Se algo sair errado

- **"Nenhum documento reconhecido"**: o PDF provavelmente é digitalizado
  (imagem, sem texto) ou não é o arquivo do Autentique.
- **Documento não separado** (ex.: aparece tudo como contrato): o título mudou
  no modelo. Os títulos reconhecidos ficam na lista `TIPOS`, no começo do
  arquivo `separar_autentique.py`.
- **Aviso "Relatório de auditoria não encontrado"**: o PDF não tem as páginas
  de auditoria do Autentique. A separação acontece assim mesmo, só que sem
  anexar o relatório.
