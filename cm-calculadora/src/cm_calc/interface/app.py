"""CM | Calculadora Judicial Bancária — aplicativo Streamlit.

Iniciar:  ./iniciar.sh            (casos reais em ~/CM-Calculos-Dados)
          ./iniciar-demo.sh       (dados fictícios em pasta separada)
"""

from __future__ import annotations

import streamlit as st

from cm_calc.casos import Caso, listar_casos
from cm_calc.interface import componentes as ui
from cm_calc.interface import paginas as pg

st.set_page_config(page_title="CM | Calculadora Judicial Bancária", page_icon="⚖️", layout="wide",
                   initial_sidebar_state="expanded")

PAGINAS = {
    "Início": pg.inicio,
    "Documentos": pg.documentos,
    "Dados contratuais": pg.contrato,
    "Comandos judiciais": pg.titulo,
    "Pendências": pg.pendencias,
    "Conferência": pg.conferencia,
    "Cálculo": pg.calculo,
    "Resultados": pg.resultados,
}


def _criar_caso() -> None:
    novo = (st.session_state.get("novo_caso") or "").strip().upper()
    try:
        Caso(novo).criar()
        st.session_state["sel_caso"] = novo
        st.session_state["erro_caso"] = None
    except ValueError as e:
        st.session_state["erro_caso"] = str(e)


with st.sidebar:
    st.markdown("### ⚖️ CM | Calculadora")
    st.caption("Caroline Macedo Advocacia · uso interno")
    st.selectbox("Caso", listar_casos(), index=None, placeholder="Selecione…", key="sel_caso")
    with st.expander("Novo caso"):
        st.text_input("Identificador interno (sem nome ou CPF)", key="novo_caso", placeholder="ex.: REV-2026-001")
        st.button("Criar caso", key="criar_caso", on_click=_criar_caso)
        if st.session_state.get("erro_caso"):
            st.error(st.session_state["erro_caso"])
    st.text_input("Responsável pela conferência", key="responsavel")
    st.divider()
    pagina = st.radio("Navegação", list(PAGINAS), key="pagina", label_visibility="collapsed")
    if ui.modo_demonstracao():
        st.caption("🧪 Modo demonstração")

PAGINAS[pagina]()
