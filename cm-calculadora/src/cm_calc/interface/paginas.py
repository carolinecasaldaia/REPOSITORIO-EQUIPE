"""Páginas da interface."""

from __future__ import annotations

import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import streamlit as st

from ..extracao import aprovacao as ap
from ..extracao.adaptador import QuadroBloqueado
from ..extracao.modelos import StatusParametro as S
from ..extracao.quadro import montar_quadro
from ..motor.atualizacao import Acumulacao, ContagemJuros
from ..motor.encargos import ContagemAtraso
from ..motor.numeros import brl
from ..servicos import demonstrativos as dm
from ..servicos import liquidacao as lq
from ..servicos.indices import carregar_series, salvar_serie, serie_de_csv
from . import componentes as ui

OPCOES_CALCULO = {
    "calculo.convencao_tempo": ["meses_civis", "meses_30", "dias_base_360", "dias_base_365"],
    "calculo.ordem_imputacao": ["juros_primeiro", "capital_primeiro"],
    "calculo.arredondamento": ["2;HALF_UP;por_parcela", "2;HALF_EVEN;por_parcela", "2;HALF_UP;final", "2;HALF_UP;integral", "2;DOWN;por_parcela"],
}


# --- Início ------------------------------------------------------------------------------------

def inicio() -> None:
    ui.topo("Painel")
    c = ui.caso_atual()
    if c is None:
        st.markdown("Selecione ou crie um caso na barra lateral para começar.")
    else:
        q = ui.quadro(c)
        docs = c.documentos_importados()
        pend = ap.bloqueios(q) if q else []
        conf = sum(p.status is S.CONFIRMADO for p in q.parametros.values()) if q else 0
        total = sum(p.status is not S.INFORMATIVO for p in q.parametros.values()) if q else 0
        resultados = lq.listar_resultados(c.pasta_resultados)
        st.subheader(f"Caso {c.id}")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Documentos importados", len(docs))
        k2.metric("Parâmetros confirmados", f"{conf}/{total}" if q else "—")
        k3.metric("Pendências", len(pend) if q else "—")
        k4.metric("Cálculos executados", len(resultados))
        st.markdown("#### Etapas")
        etapas = [
            ("Documentos importados", bool(docs)),
            ("Dados extraídos (quadro de parâmetros)", q is not None),
            ("Conferência concluída — sem pendências", q is not None and not pend),
            ("Cálculo executado", bool(resultados)),
        ]
        for nome, ok in etapas:
            st.markdown(f"{'✅' if ok else '⬜'} {nome}")
    st.divider()
    st.caption("Processamento 100% local. Nenhum documento é enviado a serviços externos. Os resultados são apoio "
               "técnico e dependem de conferência da advogada responsável.")


# --- Documentos ----------------------------------------------------------------------------------

def documentos() -> None:
    ui.topo("Documentos")
    c = ui.exige_caso()
    if c is None:
        return
    arquivos = st.file_uploader("Adicionar documentos (PDF, XLSX, CSV)", type=["pdf", "xlsx", "csv"],
                                accept_multiple_files=True, key="upload")
    if arquivos and st.button("Importar documentos selecionados", type="primary"):
        for a in arquivos:
            try:
                st.write(c.importar_bytes(a.name, a.getvalue()))
            except ValueError as e:
                st.error(str(e))
    if ui.modo_demonstracao() and st.button("Carregar documentos fictícios de demonstração", key="demo"):
        from ..demonstracao.documentos import gerar_caso_completo
        with tempfile.TemporaryDirectory() as t:
            for arq in gerar_caso_completo(Path(t)).values():
                c.importar(arq)
        st.success("Documentos fictícios importados.")

    docs = c.documentos_importados()
    st.markdown(f"#### Documentos do caso ({len(docs)})")
    if docs:
        st.dataframe([{"Arquivo": d["arquivo"], "Nome original": d["original"], "SHA-256": d["sha256"][:16] + "…",
                       "Importado em": d["importado_em"].replace("T", " ")} for d in docs],
                     hide_index=True, use_container_width=True)
    st.markdown("#### Leitura e extração")
    q = ui.quadro(c)
    tem_conferencia = q is not None and any(p.confirmado_por for p in q.parametros.values())
    descartar = True
    if tem_conferencia:
        st.warning("Este caso já tem parâmetros conferidos. Uma nova extração gera um quadro novo; o atual será "
                   "guardado como cópia de segurança.")
        descartar = st.checkbox("Entendo e quero refazer a extração", key="descartar")
    if st.button("Ler e extrair dados", disabled=not docs or not descartar, key="extrair"):
        problemas = c.verificar_integridade()
        if problemas:
            st.error("Integridade comprometida: " + "; ".join(problemas))
            return
        if q is not None:
            backup = c.arquivo_quadro.with_name(f"quadro-{datetime.now():%Y%m%d-%H%M%S}.json")
            ap.salvar(q, backup)
        with st.spinner("Lendo documentos localmente…"):
            lidos, avisos = c.ler_documentos()
            novo = montar_quadro(c.id, lidos, avisos)
            ui.salvar(c, novo)
        st.success(f"{len(lidos)} documento(s) lidos; {len(novo.parametros)} parâmetros; "
                   f"{len(novo.ocorrencias)} ocorrências. Siga para **Conferência**.")
    q = ui.quadro(c)
    if q:
        st.dataframe([{"Arquivo": d.arquivo, "Páginas": d.paginas, "Tipo identificado": d.tipo.value,
                       "Data": d.data.strftime("%d/%m/%Y") if d.data else "", "Confiança": f"{d.confianca:.0%}"}
                      for d in q.documentos], hide_index=True, use_container_width=True)


# --- Contrato ------------------------------------------------------------------------------------

def contrato() -> None:
    ui.topo("Dados contratuais")
    c = ui.exige_caso()
    q = ui.exige_quadro(c) if c else None
    if q is None:
        return
    for grupo, titulo in (("contrato", "Contrato"), ("composição", "Composição do financiamento (tarifas, seguros, IOF)")):
        params = [p for p in q.parametros.values() if p.grupo == grupo]
        st.markdown(f"#### {titulo}")
        if params:
            st.dataframe(ui.tabela_parametros(params), hide_index=True, use_container_width=True)
            ui.trechos(params)
        else:
            st.caption("Nenhum item localizado.")


# --- Título judicial -----------------------------------------------------------------------------

def titulo() -> None:
    ui.topo("Comandos judiciais")
    c = ui.exige_caso()
    q = ui.exige_quadro(c) if c else None
    if q is None:
        return
    params = [p for p in q.parametros.values() if p.grupo == "título judicial"]
    st.markdown("#### Comandos vigentes do título (dispositivo das decisões)")
    st.dataframe([{**linha, "Decisão": p.fontes[0].tipo_documento.value if p.fontes else ""}
                  for linha, p in zip(ui.tabela_parametros(params), params)], hide_index=True, use_container_width=True)
    ui.trechos(params)
    if q.modificacoes:
        st.markdown("#### Modificações por decisões posteriores")
        for m in q.modificacoes:
            st.markdown(f"- {m.descricao}")
    st.markdown("#### Alegações das partes não reconhecidas (fora do cálculo)")
    if q.alegacoes:
        for a in q.alegacoes:
            st.markdown(f"- {a.tema.value} — `{a.chave}` — {a.fonte.referencia()}")
    else:
        st.caption("Nenhuma.")


# --- Pendências -----------------------------------------------------------------------------------

def pendencias() -> None:
    ui.topo("Pendências e divergências")
    c = ui.exige_caso()
    q = ui.exige_quadro(c) if c else None
    if q is None:
        return
    pend = ap.bloqueios(q)
    if pend:
        st.error(f"{len(pend)} pendência(s) impedem o cálculo definitivo.")
        for x in pend:
            st.markdown(f"- {x}")
    else:
        st.success("Nenhuma pendência obrigatória. O cálculo definitivo está liberado.")
    st.markdown("#### Ocorrências")
    filtro = st.radio("Mostrar", ["Todas", "Só as que bloqueiam"], horizontal=True, key="filtro_ocorr")
    ocorr = [o for o in q.ocorrencias if filtro == "Todas" or o.bloqueia]
    st.dataframe([{"Tipo": o.tipo.value, "Bloqueia": "sim" if o.bloqueia else "não", "Descrição": o.texto,
                   "Referência": "; ".join(f.referencia() for f in o.fontes[:2]),
                   "Ciência": f"{o.ciencia_por} ({o.ciencia_em:%d/%m/%Y %H:%M})" if o.ciencia_por else ""} for o in ocorr],
                 hide_index=True, use_container_width=True)


# --- Conferência ----------------------------------------------------------------------------------

def _det_texto(d: dict[str, str]) -> str:
    return "\n".join(f"{k}={v}" for k, v in d.items())


def _det_dict(s: str) -> dict[str, str]:
    out = {}
    for linha in s.splitlines():
        if "=" in linha:
            k, v = linha.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def conferencia() -> None:
    ui.topo("Conferência e aprovação")
    c = ui.exige_caso()
    q = ui.exige_quadro(c) if c else None
    if q is None:
        return
    resp = ui.responsavel()
    if not resp:
        st.warning("Informe a **responsável pela conferência** na barra lateral para habilitar as aprovações.")
    pend = ap.bloqueios(q)
    st.caption(f"{len(pend)} pendência(s) restantes.")
    so_pendentes = st.toggle("Mostrar só o que falta conferir", value=True, key="so_pendentes")

    grupos = ["contrato", "composição", "título judicial", "cálculo"]
    for g in grupos:
        params = [p for p in q.parametros.values() if p.grupo == g and p.status is not S.INFORMATIVO
                  and (not so_pendentes or p.status not in (S.CONFIRMADO, S.REJEITADO))]
        if not params:
            continue
        st.markdown(f"#### {g.capitalize()}")
        for p in params:
            with st.expander(f"{ui.ICONE[p.status]} {p.descricao} — {ui.valor_exibido(p) or '(sem valor)'}"):
                _formulario_parametro(c, q, p, resp)

    st.markdown("#### Pagamentos")
    st.dataframe([{"Parcela": pg.parcela, "Vencimento": pg.vencimento.strftime("%d/%m/%Y") if pg.vencimento else "",
                   "Pagamento": pg.data_pagamento.strftime("%d/%m/%Y") if pg.data_pagamento else "?",
                   "Valor pago": brl(Decimal(pg.valor)) if pg.valor else "?",
                   "Encargos incluídos": brl(Decimal(pg.encargos)) if pg.encargos else "",
                   "Fonte": pg.fonte.referencia()} for pg in q.pagamentos], hide_index=True, use_container_width=True)
    if q.pagamentos_status is S.CONFIRMADO:
        st.success(f"Pagamentos confirmados por {q.pagamentos_confirmados_por}.")
    elif st.button("Confirmar lista de pagamentos", disabled=not resp or not q.pagamentos, key="conf_pag"):
        ap.confirmar_pagamentos(q, resp)
        ui.salvar(c, q)
        st.rerun()

    bloq = [o for o in q.ocorrencias if o.bloqueia and not o.ciencia_por]
    if bloq:
        st.markdown("#### Ocorrências que exigem ciência")
        for o in bloq:
            col1, col2 = st.columns([5, 1])
            col1.markdown(f"**{o.tipo.value}** — {o.texto}")
            if col2.button("Dar ciência", key=f"ciencia_{o.id}", disabled=not resp):
                ap.dar_ciencia(q, o.id, resp)
                ui.salvar(c, q)
                st.rerun()


def _formulario_parametro(c, q, p, resp: str) -> None:
    st.markdown(f"**Situação:** {p.status.value}")
    for f in p.fontes[:3]:
        st.caption(f"{f.referencia()} — “{f.trecho}”")
    for obs in p.observacoes:
        st.markdown(f"- {obs}")
    chave = p.id.replace(":", "_").replace(".", "_").replace(" ", "_")
    valor = None
    if p.id in OPCOES_CALCULO:
        valor = st.selectbox("Valor", OPCOES_CALCULO[p.id], index=None, placeholder="Escolha…", key=f"v_{chave}")
    elif p.status is S.CONFLITANTE:
        opcoes = [a.valor for a in p.alternativas]
        rotulos = {a.valor: f"{a.exibicao} — {a.fonte.referencia()}" for a in p.alternativas}
        valor = st.radio("Escolha o valor correto", opcoes, index=None, format_func=rotulos.get, key=f"v_{chave}")
    else:
        novo = st.text_input("Valor (altere só se estiver incorreto)", value=p.valor_vigente() or "", key=f"v_{chave}")
        valor = novo if novo != (p.valor or "") or p.status is S.AUSENTE else None
        if p.status is S.AUSENTE and not novo:
            valor = None
    det = st.text_area("Detalhes (uma linha por item: chave=valor)", value=_det_texto(p.detalhes_vigentes()),
                       key=f"d_{chave}", height=90)
    obs = st.text_input("Observação (opcional)", key=f"o_{chave}")
    b1, b2, b3 = st.columns([1, 1, 2])
    if b1.button("Confirmar", key=f"c_{chave}", type="primary", disabled=not resp):
        detalhes = _det_dict(det)
        try:
            ap.confirmar(q, p.id, resp, valor=valor,
                         detalhes=detalhes if detalhes != p.detalhes else None, observacao=obs or None)
            ui.salvar(c, q)
            st.rerun()
        except ap.AprovacaoInvalida as e:
            st.error(str(e))
    motivo = b3.text_input("Motivo da rejeição", key=f"m_{chave}", label_visibility="collapsed",
                           placeholder="Motivo da rejeição")
    if b2.button("Rejeitar", key=f"r_{chave}", disabled=not resp):
        try:
            ap.rejeitar(q, p.id, resp, motivo)
            ui.salvar(c, q)
            st.rerun()
        except ap.AprovacaoInvalida as e:
            st.error(str(e))


# --- Cálculo ---------------------------------------------------------------------------------------

def _sugestao_titulo(q) -> None:
    sug = []
    for pid, nome in (("titulo.correcao", "Correção"), ("titulo.juros_mora", "Juros de mora"),
                      ("titulo.repeticao", "Repetição"), ("titulo.honorarios", "Honorários")):
        p = q.parametros.get(pid)
        if p:
            det = ", ".join(f"{k}: {v}" for k, v in p.detalhes_vigentes().items())
            sug.append(f"**{nome}:** {p.valor_vigente()}{' — ' + det if det else ''} ({p.status.value})")
    if sug:
        st.info("Comandos do título para orientar os critérios:\n\n" + "\n\n".join(sug))


def _criterios(q, series) -> lq.CriteriosAtualizacao | None:
    st.markdown("#### Correção monetária e juros do indébito")
    _sugestao_titulo(q)
    with st.expander("Carregar série de índice (CSV local: competência;variação %)"):
        nome = st.text_input("Nome da série (ex.: INPC)", key="serie_nome").strip().upper()
        fonte = st.text_input("Fonte (órgão, tabela e data da consulta)", key="serie_fonte")
        embute = st.checkbox("Taxa que já embute correção (ex.: Selic)", key="serie_embute")
        arq = st.file_uploader("Arquivo CSV", type=["csv"], key="serie_csv")
        if st.button("Carregar série", key="serie_carregar", disabled=not (nome and fonte and arq)):
            try:
                s = serie_de_csv(nome, arq.getvalue(), fonte, embute)
                salvar_serie(s)
                st.success(f"Série {s.nome}: {len(s.valores)} meses ({min(s.valores)} a {max(s.valores)}).")
            except ValueError as e:
                st.error(str(e))
    nomes = ["(sem correção monetária)"] + sorted(series)
    sel = st.selectbox("Índice de correção", nomes, index=None, placeholder="Escolha…", key="crit_serie")
    c1, c2 = st.columns(2)
    m_ini = c1.radio("Mês do pagamento entra na correção?", ["sim", "não"], index=None, horizontal=True, key="crit_mini")
    m_fim = c2.radio("Mês da data-base entra na correção?", ["sim", "não"], index=None, horizontal=True, key="crit_mfim")
    j1, j2, j3 = st.columns(3)
    taxa = j1.number_input("Juros de mora (% ao mês; vazio = sem juros)", min_value=0.0, max_value=10.0, value=None,
                           step=0.25, format="%.4f", key="crit_juros")
    inicio = j2.date_input("Termo inicial dos juros", value=None, format="DD/MM/YYYY", key="crit_jini")
    contagem = j3.radio("Contagem dos juros", [x.value for x in ContagemJuros], index=None, key="crit_jcont",
                        format_func={"dias_30": "dias corridos ÷ 30", "meses_civis": "meses civis + dias ÷ 30"}.get)
    a1, a2 = st.columns(2)
    acum = a1.radio("Acumulação dos juros", [x.value for x in Acumulacao], index=None, horizontal=True, key="crit_acum",
                    format_func={"soma": "soma (juros simples)", "produto": "produto (compostos)"}.get)
    atraso = a2.radio("Contagem do atraso (encargos)", [x.value for x in ContagemAtraso], index=None, horizontal=True,
                      key="crit_atraso", format_func={"dias_30": "dias ÷ 30", "meses_civis": "meses civis + dias ÷ 30"}.get)
    just = st.text_area("Fundamentação (trecho do título / decisão da advogada)", key="crit_just")
    if None in (sel, m_ini, m_fim, contagem, acum, atraso):
        return None
    return lq.CriteriosAtualizacao(
        serie_correcao=None if sel.startswith("(") else sel, incluir_mes_inicial=m_ini == "sim",
        incluir_mes_final=m_fim == "sim",
        juros_taxa_mensal=(Decimal(str(taxa)) / 100) if taxa else None,   # number_input devolve float: convertido pelo texto
        juros_inicio=inicio, juros_contagem=ContagemJuros(contagem), acumulacao=Acumulacao(acum),
        contagem_atraso=ContagemAtraso(atraso), justificativa=just)


def _venda() -> lq.DadosVenda | None:
    st.markdown("#### Venda do veículo")
    v1, v2, v3 = st.columns(3)
    data_v = v1.date_input("Data da alienação", value=None, format="DD/MM/YYYY", key="v_data")
    valor = v2.number_input("Valor da venda (R$)", min_value=0.0, value=None, step=100.0, format="%.2f", key="v_valor")
    compr = v3.checkbox("Venda comprovada por documento", key="v_compr")
    st.caption("Despesas da venda (remoção, pátio, leiloeiro…)")
    import pandas as pd   # só para a tabela editável; valores voltam a Decimal abaixo
    vazio = pd.DataFrame({"descricao": pd.Series(dtype="str"), "valor": pd.Series(dtype="float"),
                          "data": pd.Series(dtype="datetime64[ns]"), "comprovada": pd.Series(dtype="bool")})
    linhas = st.data_editor(vazio, num_rows="dynamic", key="v_despesas", use_container_width=True, column_config={
        "descricao": st.column_config.TextColumn("Descrição"),
        "valor": st.column_config.NumberColumn("Valor (R$)", format="%.2f", min_value=0.0),
        "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "comprovada": st.column_config.CheckboxColumn("Comprovada", default=False)})
    abater = st.checkbox("O título autoriza abater as despesas comprovadas", key="v_abater")
    compensar_cred = st.checkbox("O título autoriza compensar os créditos do consumidor (AP03) nesta apuração", key="v_comp")
    trecho = st.text_area("Trecho do título que fundamenta a apuração", key="v_trecho")
    if data_v is None or valor is None:
        return None
    despesas = []
    for d in linhas.to_dict("records"):
        if d.get("descricao") and pd.notna(d.get("valor")) and pd.notna(d.get("data")):
            dt = d["data"].date() if hasattr(d["data"], "date") else d["data"]
            despesas.append(lq.DespesaVenda(descricao=str(d["descricao"]), valor=Decimal(f"{d['valor']:.2f}"), data=dt,
                                            comprovada=bool(d.get("comprovada"))))
    return lq.DadosVenda(data_alienacao=data_v, valor_venda=Decimal(f"{valor:.2f}"), venda_comprovada=compr,
                         despesas=despesas, abater_despesas=abater, compensar_creditos=compensar_cred, trecho_titulo=trecho)


def calculo() -> None:
    ui.topo("Cálculo")
    c = ui.exige_caso()
    q = ui.exige_quadro(c) if c else None
    if q is None:
        return
    series = carregar_series()
    tipo = lq.TipoCalculo(st.radio("Tipo de cálculo", [t.value for t in lq.TipoCalculo], key="tipo"))
    data_base = None
    if tipo is not lq.TipoCalculo.VENDA:
        data_base = st.date_input("Data-base do cálculo", value=None, format="DD/MM/YYYY", key="data_base")
    else:
        st.caption("Na apuração após a venda, a data-base é a data da alienação.")

    criterios, venda = None, None
    hon_ap03, hon_valor, compensar_saldo = True, None, False
    if tipo is lq.TipoCalculo.VENDA:
        venda = _venda()
        if venda and venda.compensar_creditos:
            criterios = _criterios(q, series)
    if tipo is lq.TipoCalculo.LIQUIDACAO:
        criterios = _criterios(q, series)
        if "titulo.honorarios" in q.parametros:
            st.markdown("#### Honorários")
            base = st.radio("Base de cálculo dos honorários", ["Total atualizado do AP03", "Valor informado"],
                            index=None, key="hon_base")
            hon_ap03 = base == "Total atualizado do AP03"
            if base == "Valor informado":
                v = st.number_input("Valor da base (R$)", min_value=0.0, value=None, format="%.2f", key="hon_valor")
                hon_valor = Decimal(f"{v:.2f}") if v is not None else None
            elif base is None:
                hon_ap03 = False
        compensar_saldo = st.checkbox("Compensar com o saldo devedor revisado na data-base", key="compensar")

    if data_base is None and tipo is not lq.TipoCalculo.VENDA:
        st.warning("Informe a data-base.")
        return
    if tipo is lq.TipoCalculo.VENDA and venda is None:
        st.warning("Informe a data da alienação e o valor da venda.")
        return
    op = lq.OpcoesCalculo(tipo=tipo, data_base=data_base or venda.data_alienacao,
                          responsavel=ui.responsavel(), criterios=criterios, honorarios_sobre_ap03=hon_ap03,
                          valor_base_honorarios=hon_valor, compensar_saldo_revisado=compensar_saldo, venda=venda)
    pend = lq.pendencias_calculo(q, op, series)
    st.divider()
    if pend:
        st.error("Cálculo definitivo bloqueado. Resolva as pendências:")
        for x in pend:
            st.markdown(f"- {x}")
    if st.button("Executar cálculo definitivo", type="primary", disabled=bool(pend), key="executar"):
        try:
            r = lq.executar(q, op, series)
        except (QuadroBloqueado, ValueError) as e:
            st.error(f"O motor recusou o cálculo: {e}")
            return
        arq = lq.salvar_resultado(r, c.pasta_resultados)
        st.session_state["resultado"] = arq.name
        st.success(f"Cálculo executado e registrado ({arq.name}). Veja em **Resultados**.")


# --- Resultados ------------------------------------------------------------------------------------

def resultados() -> None:
    ui.topo("Resultados")
    c = ui.exige_caso()
    if c is None:
        return
    arqs = lq.listar_resultados(c.pasta_resultados)
    if not arqs:
        st.info("Nenhum cálculo executado neste caso.")
        return
    nomes = [a.name for a in arqs]
    padrao = nomes.index(st.session_state["resultado"]) if st.session_state.get("resultado") in nomes else 0
    nome = st.selectbox("Execução", nomes, index=padrao, key="sel_resultado")
    r = lq.carregar_resultado(c.pasta_resultados / nome)
    q = ui.quadro(c)
    if q is not None and lq.hash_quadro(q) != r.hash_quadro:
        st.warning("O quadro de parâmetros foi alterado depois desta execução. Execute novamente para refletir a versão atual.")
    st.caption(f"{r.tipo.value} · executado por {r.executado_por} em {r.executado_em:%d/%m/%Y %H:%M} · "
               f"quadro {r.hash_quadro} · versão {r.versao}")

    k1, k2, k3 = st.columns(3)
    k1.metric("Parcela original", brl(r.parcela_original))
    k2.metric("Parcela revisada", brl(r.revisao.parcela_regular_revisada),
              delta=brl(r.revisao.parcela_regular_revisada - r.parcela_original), delta_color="inverse")
    if r.ap03:
        k3.metric("Indébito atualizado", brl(r.ap03.total_atualizado))
    elif r.venda:
        k3.metric("Saldo remanescente", brl(r.venda.saldo_remanescente_consumidor))

    abas = st.tabs(["Resumo", "AP01 — original", "AP02 — revisada", "Comparativo", "AP03 — diferenças",
                    "Ressalvas", "Memória de cálculo", "Exportar"])
    with abas[0]:
        st.dataframe([{"Item": k, "Valor": v} for k, v in dm.resumo(r)], hide_index=True, use_container_width=True)
    with abas[1]:
        st.dataframe(dm.linhas_evolucao(r.ap01), hide_index=True, use_container_width=True)
    with abas[2]:
        st.dataframe(dm.linhas_evolucao(r.ap02), hide_index=True, use_container_width=True)
    with abas[3]:
        st.line_chart(dm.comparativo_saldos(r), x="Parcela", y=["Saldo original", "Saldo revisado"])
        st.caption("Gráfico apenas ilustrativo; os valores oficiais estão nas tabelas.")
    with abas[4]:
        if r.ap03:
            st.dataframe(dm.linhas_diferencas(r), hide_index=True, use_container_width=True)
        else:
            st.caption("Este tipo de cálculo não inclui o AP03.")
    with abas[5]:
        st.dataframe(dm.linhas_ressalvas(r), hide_index=True, use_container_width=True)
    with abas[6]:
        st.dataframe(dm.linhas_memoria(r), hide_index=True, use_container_width=True)
    with abas[7]:
        st.download_button("Baixar registro completo (JSON)", r.model_dump_json(indent=1), file_name=nome,
                           mime="application/json", key="baixar_json")
        st.button("Planilha Excel (Fase 6)", disabled=True, key="exp_xlsx")
        st.button("Relatório PDF (Fase 6)", disabled=True, key="exp_pdf")
        st.caption("A exportação em Excel e PDF será implementada na Fase 6, a partir destas mesmas tabelas.")
