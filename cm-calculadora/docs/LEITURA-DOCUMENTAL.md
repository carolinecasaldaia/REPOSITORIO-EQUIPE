# Leitura documental e quadro de parâmetros — v0.4.0 (Fase 3)

## Fluxo

```
importar  →  ler (PDF/CSV/XLSX/TXT)  →  segmentar  →  classificar  →  extrair
          →  consolidar o título  →  QUADRO  →  conferência/aprovação  →  motor
```

1. **Importar** (`casos.py`):
   - copia para `~/CM-Calculos-Dados/casos/<ID>/documentos/` em modo somente leitura (0400);
   - registra o SHA-256 no manifesto;
   - recusa ID com nome ou CPF;
   - a integridade é verificada antes de cada extração.
2. **Ler** (`documentos/leitura.py`):
   - extrai o texto com PyMuPDF, localmente;
   - página sem texto gera aviso de OCR necessário (o OCR não está instalado);
   - guarda a referência do PJe ("Num. X - Pág. Y") quando ela existe no rodapé.
3. **Segmentar um processo completo:** usa o sumário (marcadores) do PDF; se não houver, os cabeçalhos de cada página.
4. **Classificar** (`classificacao.py`):
   - pontuação por palavras-chave de cabeçalho e de corpo;
   - abaixo do limiar, o documento fica "não classificado", sem tipo forçado;
   - confiança abaixo de 0,5 gera ocorrência bloqueante.
5. **Extrair:**
   - **contrato** (`contrato.py`): rótulo + valor na mesma linha (ou na seguinte, se o rótulo estiver isolado). Lê valores, datas, taxas mensal/anual, CET, parcelas, encargos, capitalização e itens (IOF, tarifas, seguros, serviços), com a forma de pagamento (financiado, à vista ou indefinida);
   - **pagamentos** (`pagamentos.py`): comprovantes e planilhas, cruzados entre si;
   - **comandos** (`decisoes.py`): regras aplicadas cláusula a cláusula do dispositivo.
6. **Consolidar** (`consolidacao.py`): sentença → embargos → acórdão → embargos do acórdão → decisões posteriores. Prevalece, por tema, a decisão mais recente; a modificação fica registrada.
7. **Quadro** (`quadro.py`): parâmetros com status, valor, detalhes, fontes (arquivo, página, trecho) e observações, além das ocorrências.
8. **Aprovação** (`aprovacao.py`): confirmação com nome, data e hora; o adaptador (`adaptador.py`) recusa quadro com pendências.

## Distinção entre reconhecido e alegado

| Origem do texto | Natureza | Efeito |
|---|---|---|
| Dispositivo de sentença, acórdão, embargos ou decisão | reconhecido | vira parâmetro (após conferência) |
| Fundamentação de decisão | fundamentação | só gera ocorrência "tema só na fundamentação" |
| Petição inicial, contestação, razões de recurso | alegado | nunca vira parâmetro; lista de "alegações não reconhecidas" |

## Verificações automáticas

| Situação | Ocorrência | Bloqueia? |
|---|---|---|
| Falta contrato, sentença ou pagamentos | documento ausente | sim |
| Menção a apelação sem acórdão; embargos opostos sem decisão | documento ausente | sim |
| Sem certidão de trânsito em julgado | documento ausente | não (alerta) |
| Mesmo campo com valores diferentes no contrato | parâmetro conflitante | sim |
| Valor financiado ≠ valor liberado + itens financiados | contradição | sim |
| Parcela ≠ Price mensal com os dados lidos | divergência | não (indício técnico) |
| Comprovante × planilha divergentes; parcela duplicada | contradição | sim |
| Comando sem índice, termo inicial, taxa, base, modalidade... | informação insuficiente | sim |
| Recurso provido sem capítulo identificado; reforma do resultado | insuficiente / modificação | sim |
| Página sem texto; classificação incerta | OCR / classificação | sim |
| Alegação da parte divergente do contrato | contradição | não |

## Privacidade (modelo híbrido)

- Nada sai do computador: não há chamada de rede em nenhum módulo, e há teste para isso.
- **Pacote para o Claude** (`privacidade/pacote.py`):
  - contém só trechos ligados a parâmetros ou ocorrências: até 1.500 caracteres por trecho e no máximo 20 trechos;
  - os trechos são pseudonimizados localmente, e a tabela de correspondência não sai;
  - se sobrar algum dado pessoal, o pacote é recusado;
  - exige autorização com responsável, finalidade e escopo, que fica registrada em `claude/registro-envios.jsonl`.
- **Pseudonimização:** CPF, CNPJ, nomes (após rótulo ou qualificação), RG, OAB, placa, chassi, RENAVAM, e-mail, telefone, CEP, endereço, conta, número do processo e data de nascimento. Valores, datas, taxas e índices são mantidos.
- **Regras do Claude Code** (`.claude/settings.json`): bloqueiam a leitura e a escrita diretas de documentos, quadro e resultados dos casos; cada execução do `cm-calc` pede aprovação.

## Limitações conhecidas

- **Regras de texto:** a extração depende da redação. Contratos com tabelas em colunas, layouts de outros bancos ou nomenclaturas não catalogadas (`catalogo.py`) podem não ser reconhecidos. Nesses casos o campo aparece como ausente; nada é inventado.
- **PDF digitalizado:** sem OCR, não há texto. O Tesseract não está instalado (depende de autorização).
- **Cláusulas complexas** (várias determinações e exceções na mesma frase) podem gerar comandos incompletos. As lacunas ficam marcadas, e a conferência humana é obrigatória.
- **Nomes de pessoas:** só são detectados após rótulo ou qualificação. Nomes soltos no texto podem escapar da pseudonimização, e a verificação residual só os pega se já forem conhecidos. Por isso, todo pacote deve ser revisado antes da leitura.
- **Validação:** feita só com documentos fictícios. O desempenho em documentos reais é desconhecido até a Fase 5.
