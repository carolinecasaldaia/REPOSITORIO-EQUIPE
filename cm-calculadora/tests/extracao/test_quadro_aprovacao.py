"""Consolidação do título, documentos ausentes, aprovação e integração com o motor."""

from datetime import date
from decimal import Decimal

import pytest

from cm_calc.documentos.modelos import Documento, Pagina, TipoDocumento as T
from cm_calc.extracao import aprovacao as ap
from cm_calc.extracao.adaptador import QuadroBloqueado, executar_revisao, montar_entrada
from cm_calc.extracao.modelos import StatusParametro as S, TipoOcorrencia as O
from cm_calc.extracao.quadro import montar_quadro
from cm_calc.extracao.relatorio import quadro_markdown
from cm_calc.motor.datas import vencimentos_mensais
from cm_calc.motor.financiamento import ParcelaPrevista, calcular_parcela_regular
from cm_calc.motor.indebito import Modalidade
from cm_calc.motor.numeros import D, ModoArredondamento, PoliticaArredondamento
from cm_calc.motor.taxas import ConvencaoTempo, Regime, Taxa
from tests.extracao.conftest import ler
from tests.fixtures import documentos_ficticios as F

ADV = "Advogada Responsável (teste)"


def doc(texto, tipo, id_, data=None):
    return Documento(id=id_, arquivo=f"{id_}.pdf", sha256="0", tipo=tipo, confianca=1.0, data=data,
                     paginas=[Pagina(numero=1, texto=texto)])


# --- Consolidação: acórdão e embargos modificam a sentença ---------------------------------

def test_modificacoes_pelo_acordao(quadro):
    p = quadro.parametros
    assert p["titulo.repeticao"].valor == "simples"                          # sentença: dobro -> acórdão: simples
    assert p["titulo.repeticao"].fontes[0].tipo_documento is T.ACORDAO
    assert p["titulo.honorarios"].detalhes_vigentes()["percentual"] == "12"  # 10% -> 12% (base herdada)
    assert p["titulo.honorarios"].detalhes_vigentes()["base"] == "valor da condenacao"
    assert {m.chave for m in quadro.modificacoes} == {"repeticao", "honorarios"}
    # o que o acórdão não tocou continua vindo da sentença
    assert p["titulo.correcao"].fontes[0].tipo_documento is T.SENTENCA
    assert p["titulo.resultado_recurso"].status is S.INFORMATIVO
    assert p["titulo.resultado_embargos_1"].valor == "rejeitados"


def test_alegacoes_nao_reconhecidas_e_fundamentacao(quadro):
    assert [a.chave for a in quadro.alegacoes] == ["exclusao:registro de contrato"]
    fund = [o for o in quadro.ocorrencias if o.tipo is O.FUNDAMENTACAO_SEM_DISPOSITIVO]
    assert {("compensação" in o.texto) or ("capitalização" in o.texto) for o in fund} == {True}
    assert "titulo.compensacao" not in quadro.parametros           # fundamentação não vira parâmetro
    contr = [o for o in quadro.ocorrencias if o.tipo is O.CONTRADICAO and "41.000" in o.texto]
    assert contr and not contr[0].bloqueia                          # alegação diverge do contrato


def test_juros_por_taxa_media_exige_valor(quadro):
    p = quadro.parametros["titulo.juros_remuneratorios"]
    assert p.status is S.INSUFICIENTE and any("taxa média" in o for o in p.observacoes)


def test_pagamentos_e_contradicao(quadro):
    assert [pg.parcela for pg in quadro.pagamentos] == [1, 2, 3, 4, 5]
    p4 = next(pg for pg in quadro.pagamentos if pg.parcela == 4)
    assert (p4.data_pagamento, p4.valor, p4.encargos) == (date(2023, 5, 25), "2252.46", "89.40")
    assert p4.fonte.tipo_documento is T.COMPROVANTE                 # comprovante prevalece sobre a planilha
    o = next(o for o in quadro.ocorrencias if o.id == "pag-contradicao-2")
    assert o.bloqueia and "2163.60" in o.texto


def test_documentos_ausentes(arquivos):
    docs, av = ler([arquivos["sentenca"], arquivos["embargos"]])
    docs.append(doc("CERTIDÃO\nCertifico que foi interposta apelação pelo réu.", T.CERTIDAO, "cert#1"))
    q = montar_quadro("T-5", docs, av)
    ids = {o.id for o in q.ocorrencias if o.tipo is O.DOCUMENTO_AUSENTE}
    assert {"ausente-contrato", "ausente-pagamentos", "ausente-acordao", "ausente-transito"} <= ids
    assert "ausente-sentenca" not in ids
    assert q.parametros["contrato.valor_financiado"].status is S.AUSENTE


def test_embargos_mencionados_sem_decisao(arquivos):
    docs, av = ler([arquivos["sentenca"]])
    docs.append(doc("CERTIDÃO\nCertifico que foram opostos embargos de declaração pelo réu.", T.CERTIDAO, "c#1"))
    q = montar_quadro("T-6", docs, av)
    assert any(o.id == "ausente-embargos" for o in q.ocorrencias)


def test_provimento_sem_capitulo_identificado(arquivos):
    docs, av = ler([arquivos["sentenca"]])
    acordao = ("ACÓRDÃO\nACORDAM, em Câmara Fictícia, por unanimidade, dar provimento ao recurso.\n"
               "Sala das Sessões, 01 de julho de 2024.")
    docs.append(doc(acordao, T.ACORDAO, "ac#1", date(2024, 7, 1)))
    q = montar_quadro("T-7", docs, av)
    assert any(o.id.startswith("provimento-sem-capitulo") and o.bloqueia for o in q.ocorrencias)


def test_reforma_do_resultado_bloqueia(arquivos):
    docs, av = ler([arquivos["sentenca"]])
    acordao = ("ACÓRDÃO\nAnte o exposto, dou provimento ao recurso para julgar improcedentes os pedidos iniciais.\n"
               "Sala das Sessões, 01 de julho de 2024.")
    docs.append(doc(acordao, T.ACORDAO, "ac#1", date(2024, 7, 1)))
    q = montar_quadro("T-8", docs, av)
    assert q.parametros["titulo.resultado"].valor == "improcedente"
    assert any(o.tipo is O.MODIFICACAO and o.bloqueia for o in q.ocorrencias)


def test_parcela_duplicada_na_planilha(tmp_path):
    p = tmp_path / "dup.csv"
    p.write_text("Parcela;Data pagamento;Valor pago\n3;05/04/2023;2.163,06\n3;06/04/2023;2.163,06\n", encoding="utf-8")
    docs, av = ler([p])
    q = montar_quadro("T-9", docs, av)
    assert any(o.id.startswith("pag-dup-3") for o in q.ocorrencias)


# --- Aprovação ---------------------------------------------------------------------------------

def test_quadro_novo_esta_bloqueado(quadro):
    pend = ap.bloqueios(quadro)
    assert any("calculo.convencao_tempo" in x for x in pend)
    assert any("pagamentos" in x for x in pend)
    with pytest.raises(QuadroBloqueado):
        montar_entrada(quadro)


def test_regras_de_confirmacao(quadro):
    with pytest.raises(ap.AprovacaoInvalida, match="responsável"):
        ap.confirmar(quadro, "contrato.n_parcelas", "  ")
    with pytest.raises(ap.AprovacaoInvalida, match="informe o valor"):
        ap.confirmar(quadro, "calculo.convencao_tempo", ADV)
    with pytest.raises(ap.AprovacaoInvalida, match="lacunas"):
        ap.confirmar(quadro, "titulo.juros_remuneratorios", ADV)
    ap.confirmar(quadro, "contrato.n_parcelas", ADV)
    p = quadro.parametros["contrato.n_parcelas"]
    assert p.status is S.CONFIRMADO and p.confirmado_por == ADV and p.confirmado_em is not None
    ap.rejeitar(quadro, "titulo.exclusao:registro de contrato", ADV, "teste de rejeição")
    assert quadro.parametros["titulo.exclusao:registro de contrato"].status is S.REJEITADO


def aprovar_tudo(q, taxa_revisada="1,60"):
    tecnicos = {"calculo.convencao_tempo": "meses_civis", "calculo.arredondamento": "2;HALF_UP;por_parcela",
                "calculo.ordem_imputacao": "juros_primeiro"}
    for pid, p in q.parametros.items():
        if p.status is S.INFORMATIVO:
            continue
        if pid in tecnicos:
            ap.confirmar(q, pid, ADV, valor=tecnicos[pid])
        elif pid == "titulo.juros_remuneratorios":
            ap.confirmar(q, pid, ADV, detalhes={"taxa_mensal": taxa_revisada},
                         observacao="taxa média BACEN da modalidade (valor fictício de teste)")
        elif pid == "contrato.item:tarifa_de_avaliacao_do_bem":
            ap.confirmar(q, pid, ADV, detalhes={"data_pagamento": "2023-01-05"})
        else:
            ap.confirmar(q, pid, ADV)
    ap.confirmar_pagamentos(q, ADV)
    for o in q.ocorrencias:
        if o.bloqueia:
            ap.dar_ciencia(q, o.id, ADV)


def test_fluxo_completo_ate_o_motor(quadro):
    aprovar_tudo(quadro)
    assert ap.bloqueios(quadro) == []
    e = montar_entrada(quadro)
    assert e.valor_financiado == D("40000.00") and len(e.parcelas) == 24
    assert {i.descricao for i in e.revisao.itens_excluidos} == {"tarifa de cadastro", "seguro prestamista"}
    assert e.regra_restituicao.modalidade is Modalidade.SIMPLES                 # efeito do acórdão
    assert e.descaracterizacao and {c.value for c in e.descaracterizacao.componentes_afastados} == {"multa", "juros_mora"}
    assert e.honorarios.percentual == D("0.12")
    assert e.revisao.origem_taxa.trecho and "taxa média" in e.revisao.origem_taxa.trecho.lower()

    r, mem = executar_revisao(e)
    assert r.valor_financiado_revisado == D("37600.00")                         # 40.000 − 900 − 1.500
    pol = PoliticaArredondamento(casas=2, modo=ModoArredondamento.MEIO_PARA_CIMA, arredondar_cada_parcela=True)
    parcelas = [ParcelaPrevista(numero=k + 1, vencimento=d) for k, d in enumerate(vencimentos_mensais(date(2023, 2, 5), 24))]
    direto = calcular_parcela_regular(D("37600.00"), date(2023, 1, 5), parcelas,
                                      Taxa(mensal=D("0.016"), regime=Regime.COMPOSTO, convencao=ConvencaoTempo.MESES_CIVIS), pol)
    assert r.parcela_regular_revisada == direto.parcela_regular
    assert all(p.origem for p in mem.passos)


def test_alteracao_pela_advogada_prevalece(quadro):
    aprovar_tudo(quadro)
    ap.confirmar(quadro, "titulo.repeticao", ADV, valor="dobro a partir de data", detalhes={"data_corte": "2023-03-01"})
    e = montar_entrada(quadro)
    assert e.regra_restituicao.modalidade is Modalidade.DOBRO_A_PARTIR_DE
    assert e.regra_restituicao.data_corte == date(2023, 3, 1)


def test_item_a_vista_sem_data_bloqueia(quadro):
    aprovar_tudo(quadro)
    ap.confirmar(quadro, "titulo.exclusao:tarifa de avaliacao do bem", ADV, valor="excluída (ilegal/abusiva)")
    quadro.parametros["contrato.item:tarifa_de_avaliacao_do_bem"].detalhes_confirmados = None
    with pytest.raises(QuadroBloqueado, match="data_pagamento"):
        montar_entrada(quadro)


def test_salvar_carregar_e_relatorio(quadro, tmp_path):
    ap.salvar(quadro, tmp_path / "q.json")
    q2 = ap.carregar(tmp_path / "q.json")
    assert q2.model_dump() == quadro.model_dump()
    md = quadro_markdown(q2)
    assert "Modificações do título" in md and "NÃO reconhecidas" in md and "Pendências" in md
