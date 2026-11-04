#!/bin/zsh
# CM | Calculadora Judicial Bancária — casos reais (~/CM-Calculos-Dados).
# Acesso só neste computador: http://localhost:8501
cd "${0:A:h}"
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
unset CM_CALC_MODO CM_CALC_DADOS
exec /opt/homebrew/bin/uv run streamlit run src/cm_calc/interface/app.py --server.address 127.0.0.1 --server.port 8501
