#!/bin/zsh
# CM | Calculadora Judicial Bancária — MODO DEMONSTRAÇÃO (dados fictícios, pasta separada).
# Acesso só neste computador: http://localhost:8502
cd "${0:A:h}"
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
export CM_CALC_MODO=demonstracao
export CM_CALC_DADOS="$HOME/CM-Calculos-Dados/_demonstracao"
mkdir -p "$CM_CALC_DADOS" && chmod 700 "$CM_CALC_DADOS"
exec /opt/homebrew/bin/uv run streamlit run src/cm_calc/interface/app.py --server.address 127.0.0.1 --server.port 8502
