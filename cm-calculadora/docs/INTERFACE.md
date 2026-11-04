# Interface — v0.5.0 (Fase 4)

## Iniciar

| Uso | Comando no Terminal | Endereço |
|---|---|---|
| Casos reais | `~/cm-calculadora/iniciar.sh` | http://localhost:8501 |
| Demonstração (dados fictícios) | `~/cm-calculadora/iniciar-demo.sh` | http://localhost:8502 |

Para encerrar: `Ctrl+C` na janela do Terminal (ou fechar a janela).

- O servidor aceita conexões só deste computador (`127.0.0.1`); o acesso pelo IP da rede é recusado.
- As estatísticas de uso do Streamlit estão desligadas (`.streamlit/config.toml` e o script de inicialização).
- O modo demonstração grava em `~/CM-Calculos-Dados/_demonstracao`, separado dos casos reais.

## Páginas

1. **Início:** identificação do escritório, caso selecionado, indicadores e etapas.
2. **Documentos:**
   - adiciona PDF, XLSX e CSV;
   - lista os documentos com o hash;
   - "Ler e extrair dados" refaz o quadro e guarda cópia do anterior, se já houver conferência.
3. **Dados contratuais:** parâmetros do contrato e composição, com referência e trecho de origem.
4. **Comandos judiciais:** comandos vigentes, decisão de origem, modificações e alegações não reconhecidas.
5. **Pendências:** o que bloqueia o cálculo e todas as ocorrências.
6. **Conferência:**
   - confirmar ou rejeitar cada parâmetro (exige a responsável informada na barra lateral);
   - escolher entre valores conflitantes;
   - completar lacunas nos detalhes (`chave=valor`);
   - confirmar a lista de pagamentos;
   - dar ciência às ocorrências.
7. **Cálculo:**
   - tipo: recálculo AP01 × AP02, liquidação revisional ou busca e apreensão após a venda;
   - data-base;
   - critérios de correção e juros, sem opção pré-marcada;
   - série de índice (CSV local com fonte);
   - base dos honorários;
   - compensação;
   - dados da venda.

   O botão "Executar cálculo definitivo" fica desabilitado enquanto houver pendência.
8. **Resultados:**
   - indicadores e resumo;
   - AP01, AP02, comparativo, AP03, ressalvas e memória de cálculo;
   - aviso se o quadro mudou depois da execução;
   - download do registro em JSON. Excel e PDF ficam para a Fase 6.

## Arquitetura

`interface/` (telas) → `servicos/liquidacao.py` (orquestração, sem fórmulas) → `extracao/adaptador.py` → `motor/`.
`servicos/demonstrativos.py` monta as tabelas usadas na tela, as mesmas que alimentarão a exportação.
