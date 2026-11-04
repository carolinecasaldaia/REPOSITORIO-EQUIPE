"""Componentes reutilizáveis da interface."""

from __future__ import annotations

import os

import streamlit as st

from ..casos import Caso
from ..extracao import aprovacao as ap
from ..extracao.modelos import Parametro, QuadroParametros, StatusParametro as S

ICONE = {S.CONFIRMADO: "✅", S.EXTRAIDO: "🔎", S.CONFLITANTE: "⚠️", S.INSUFICIENTE: "⚠️", S.AUSENTE: "❌",
         S.REJEITADO: "⛔", S.INFORMATIVO: "ℹ️"}

CSS = """
<style>
.cm-topo {border-bottom: 3px solid #1F3A5F; padding-bottom: .4rem; margin-bottom: 1rem;}
.cm-topo h1 {font-size: 1.55rem; margin: 0; color: #1F3A5F; letter-spacing: .02em;}
.cm-topo p {margin: .15rem 0 0; color: #5A6573; font-size: .95rem;}
.cm-demo {background: #FFF4D6; border: 1px solid #E8C55A; padding: .45rem .8rem; border-radius: 6px;
          font-size: .9rem; margin-bottom: .8rem;}
</style>
"""


def modo_demonstracao() -> bool:
    return os.environ.get("CM_CALC_MODO", "") == "demonstracao"


def topo(subtitulo: str) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(f"<div class='cm-topo'><h1>Caroline Macedo Advocacia</h1>"
                f"<p>CM | Calculadora Judicial Bancária · {subtitulo}</p></div>", unsafe_allow_html=True)
    if modo_demonstracao():
        st.markdown("<div class='cm-demo'><b>Modo demonstração</b> — somente dados fictícios. "
                    "Pasta de dados separada dos casos reais.</div>", unsafe_allow_html=True)


def caso_atual() -> Caso | None:
    cid = st.session_state.get("sel_caso")
    return Caso(cid) if cid else None


def responsavel() -> str:
    return (st.session_state.get("responsavel") or "").strip()


def quadro(caso: Caso) -> QuadroParametros | None:
    return ap.carregar(caso.arquivo_quadro) if caso.arquivo_quadro.exists() else None


def salvar(caso: Caso, q: QuadroParametros) -> None:
    ap.salvar(q, caso.arquivo_quadro)


def exige_caso() -> Caso | None:
    c = caso_atual()
    if c is None:
        st.info("Selecione ou crie um caso na barra lateral.")
    return c


def exige_quadro(c: Caso) -> QuadroParametros | None:
    q = quadro(c)
    if q is None:
        st.info("Ainda não há extração para este caso. Use **Documentos → Ler e extrair dados**.")
    return q


def valor_exibido(p: Parametro) -> str:
    if p.valor_confirmado is not None:
        return p.valor_confirmado
    if p.status is S.CONFLITANTE:
        return " / ".join(a.exibicao for a in p.alternativas)
    return p.exibicao or p.valor or ""


def referencias(p: Parametro, limite: int = 2) -> str:
    return "; ".join(f.referencia() for f in p.fontes[:limite])


def tabela_parametros(params: list[Parametro]) -> list[dict[str, str]]:
    return [{"": ICONE[p.status], "Parâmetro": p.descricao, "Valor": valor_exibido(p),
             "Detalhes": ", ".join(f"{k}: {v}" for k, v in p.detalhes_vigentes().items() if v and k not in ("item", "tipo")),
             "Situação": p.status.value, "Referência": referencias(p),
             "Observações": "; ".join(p.observacoes)} for p in params]


def trechos(params: list[Parametro]) -> None:
    with st.expander("Ver trechos de origem"):
        for p in params:
            for f in p.fontes:
                st.markdown(f"**{p.descricao}** — {f.referencia()}")
                st.caption(f.trecho)
