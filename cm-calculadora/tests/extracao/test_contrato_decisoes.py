"""Extração contratual e de comandos judiciais (dispositivo × fundamentação × alegação)."""

from datetime import date
from decimal import Decimal

from cm_calc.documentos.modelos import Documento, Natureza, Pagina, TipoDocumento as T
from cm_calc.extracao.contrato import extrair_contrato
from cm_calc.extracao.decisoes import extrair_comandos, localizar_dispositivo
from cm_calc.extracao.modelos import StatusParametro as S, TipoOcorrencia as O
from cm_calc.extracao.quadro import montar_quadro
from tests.fixtures import documentos_ficticios as F


def doc(texto, tipo, id_="d#1", data=None):
    return Documento(id=id_, arquivo=f"{id_}.pdf", sha256="0", tipo=tipo, confianca=1.0, data=data,
                     paginas=[Pagina(numero=1, texto=texto)])


def campos(achados):
    out = {}
    for a in achados:
        out.setdefault(a.campo, []).append(a)
    return out


# --- Contrato ---------------------------------------------------------------------------

def test_campos_contratuais(quadro):
    p = quadro.parametros
    esperado = {
        "contrato.data_liberacao": "2023-01-05", "contrato.valor_liberado": "36000.00",
        "contrato.valor_financiado": "40000.00", "contrato.taxa_mensal": "0.022",
        "contrato.taxa_anual": "0.2984", "contrato.cet_anual": "0.3622", "contrato.n_parcelas": "24",
        "contrato.valor_parcela": "2163.06", "contrato.primeiro_vencimento": "2023-02-05",
        "contrato.multa_moratoria": "0.02", "contrato.juros_moratorios": "0.01", "contrato.capitalizacao": "mensal",
    }
    for k, v in esperado.items():
        assert p[k].status is S.EXTRAIDO, (k, p[k].status, p[k].alternativas)
        assert Decimal(p[k].valor) == Decimal(v) if v[0].isdigit() and "-" not in v else p[k].valor == v, k
    assert p["contrato.taxa_mensal"].fontes[0].pagina == 1
    assert "2,20%" in p["contrato.taxa_mensal"].fontes[0].trecho


def test_itens_e_forma_de_pagamento(quadro):
    p = quadro.parametros
    assert p["contrato.item:tarifa_de_cadastro"].detalhes["forma"] == "financiado"
    assert p["contrato.item:tarifa_de_avaliacao_do_bem"].detalhes["forma"] == "à vista"
    assert Decimal(p["contrato.item:iof"].valor) == Decimal("1100.00")
    # composição fecha (36.000 + 4.000 financiados = 40.000) => sem ocorrência
    assert not any(o.id == "composicao-nao-fecha" for o in quadro.ocorrencias)
    # Price com os dados lidos confere com a parcela => sem divergência
    assert not any(o.id == "parcela-diverge-price" for o in quadro.ocorrencias)
    assert any(o.id == "taxas-relacao" and "equivalentes" in o.texto for o in quadro.ocorrencias)


def test_rotulo_sem_valor_nao_captura_linha_vizinha():
    texto = "Valor total financiado: R$ 10.000,00 (inclui IOF e tarifas)\nTarifa de cadastro (financiada): R$ 700,00\n"
    c = campos(extrair_contrato(doc(texto, T.CONTRATO)))
    assert "contrato.item:iof" not in c
    assert c["contrato.item:tarifa_de_cadastro"][0].valor == "700.00"


def test_forma_nao_identificada_fica_insuficiente():
    texto = F.CONTRATO.replace("Tarifa de cadastro (financiada)", "Tarifa de cadastro")
    q = montar_quadro("T-1", [doc(texto, T.CONTRATO)], [])
    p = q.parametros["contrato.item:tarifa_de_cadastro"]
    assert p.status is S.INSUFICIENTE and "forma de pagamento" in p.observacoes[0]


def test_valores_conflitantes_e_campo_ausente():
    texto = F.CONTRATO.replace("Quantidade de parcelas: 24\n", "") + "\nValor da parcela: R$ 2.200,00\n"
    q = montar_quadro("T-2", [doc(texto, T.CONTRATO)], [])
    assert q.parametros["contrato.valor_parcela"].status is S.CONFLITANTE
    assert len(q.parametros["contrato.valor_parcela"].alternativas) == 2
    assert q.parametros["contrato.n_parcelas"].status is S.AUSENTE


def test_composicao_que_nao_fecha():
    texto = F.CONTRATO.replace("Valor total financiado: R$ 40.000,00", "Valor total financiado: R$ 40.250,00")
    q = montar_quadro("T-3", [doc(texto, T.CONTRATO)], [])
    o = next(o for o in q.ocorrencias if o.id == "composicao-nao-fecha")
    assert o.bloqueia and "250" in o.texto


def test_parcela_que_nao_bate_com_price():
    texto = F.CONTRATO.replace("R$ 2.163,06", "R$ 2.190,00")
    q = montar_quadro("T-4", [doc(texto, T.CONTRATO)], [])
    assert any(o.id == "parcela-diverge-price" and "capitalização diária" in o.texto for o in q.ocorrencias)


# --- Dispositivo × fundamentação × alegação -------------------------------------------------

def test_dispositivo_localizado():
    d = doc(F.SENTENCA, T.SENTENCA)
    (a, b), = localizar_dispositivo(d)
    trecho = d.texto[a:b]
    assert trecho.startswith("Ante o exposto") and "Publique-se" not in trecho


def test_natureza_dos_comandos():
    cmds = extrair_comandos(doc(F.SENTENCA, T.SENTENCA))
    rec = {c.chave: c for c in cmds if c.natureza is Natureza.RECONHECIDO}
    fund = {c.chave for c in cmds if c.natureza is Natureza.FUNDAMENTACAO}
    assert rec["resultado"].efeito == "parcialmente procedente"
    assert rec["exclusao:tarifa de cadastro"].efeito.startswith("excluída")
    assert rec["exclusao:seguro prestamista"].efeito.startswith("excluída")
    assert rec["exclusao:registro de contrato"].efeito == "mantida (legal)"
    assert rec["mora"].detalhes["componentes"] == "multa,juros_mora"
    assert rec["correcao"].detalhes == {"indice": "inpc", "termo_inicial": "cada desembolso"}
    assert rec["juros_mora"].detalhes == {"taxa_mensal": "1", "termo_inicial": "a citacao"}
    assert rec["honorarios"].detalhes["percentual"] == "10" and rec["honorarios"].detalhes["devedor"] == "reu"
    assert "juros_mora" not in {c.chave for c in cmds if "afastando" in c.fonte.trecho and c.chave == "juros_mora"}
    assert {"capitalizacao", "compensacao"} <= fund and "capitalizacao" not in rec


def test_alegacoes_nunca_viram_comando_reconhecido():
    cmds = extrair_comandos(doc(F.PETICAO, T.PETICAO_INICIAL))
    assert cmds and all(c.natureza is Natureza.ALEGADO for c in cmds)


def test_ilegalidade_nao_e_lida_como_negacao():
    t = "Ante o exposto, JULGO PROCEDENTE o pedido para declarar a ilegalidade da tarifa de cadastro.\nP.R.I."
    rec = [c for c in extrair_comandos(doc(t, T.SENTENCA)) if c.natureza is Natureza.RECONHECIDO]
    assert next(c for c in rec if c.chave.startswith("exclusao")).efeito.startswith("excluída")


def test_lacunas_sao_apontadas():
    t = ("Ante o exposto, JULGO PROCEDENTE o pedido para limitar os juros remuneratórios à taxa média de mercado "
         "e condenar o réu à restituição dos valores pagos, com correção monetária e juros de mora.\nP.R.I.")
    rec = {c.chave: c for c in extrair_comandos(doc(t, T.SENTENCA)) if c.natureza is Natureza.RECONHECIDO}
    assert any("taxa média" in l for l in rec["juros_remuneratorios"].lacunas)
    assert set(rec["correcao"].lacunas) == {"índice de correção", "termo inicial da correção"}
    assert "taxa dos juros de mora" in rec["juros_mora"].lacunas
    assert rec["repeticao"].lacunas            # modalidade não especificada


def test_dobro_a_partir_de_data_e_capitalizacao_diaria():
    t = ("Ante o exposto, JULGO PROCEDENTE o pedido para afastar a capitalização diária dos juros, admitida a "
         "capitalização mensal; e condenar o réu à repetição do indébito, de forma simples quanto aos pagamentos "
         "anteriores e em dobro a partir de 30/03/2021.\nP.R.I.")
    rec = {c.chave: c for c in extrair_comandos(doc(t, T.SENTENCA)) if c.natureza is Natureza.RECONHECIDO}
    assert rec["capitalizacao"].efeito == "afastada" and "diaria" in rec["capitalizacao"].detalhes["modalidades"]
    assert rec["repeticao"].efeito == "dobro a partir de data"
    assert rec["repeticao"].detalhes["data_corte"] == "2021-03-30"


def test_busca_e_apreensao_improcedente_multa_e_perdas():
    t = ("SENTENÇA\nVistos.\nAnte o exposto, JULGO IMPROCEDENTE o pedido de busca e apreensão; condeno o autor ao "
         "pagamento da multa prevista no art. 3º, § 6º, do Decreto-Lei 911/1969; condeno o autor ao pagamento de "
         "perdas e danos, apurados pela tabela FIPE; determino a restituição do veículo ao réu.\nP.R.I.")
    rec = {c.chave: c for c in extrair_comandos(doc(t, T.SENTENCA)) if c.natureza is Natureza.RECONHECIDO}
    assert rec["resultado"].efeito == "improcedente"
    assert rec["multa_dl911"].efeito == "deferida" and rec["multa_dl911"].lacunas
    assert rec["perdas_danos"].efeito == "deferidas" and rec["perdas_danos"].detalhes["base"] == "tabela fipe"
    assert rec["restituicao_veiculo"].efeito == "determinada"


def test_descaracterizacao_sem_comando_nao_gera_multa_nem_perdas():
    t = "Ante o exposto, JULGO PARCIALMENTE PROCEDENTE o pedido para descaracterizar a mora.\nP.R.I."
    chaves = {c.chave for c in extrair_comandos(doc(t, T.SENTENCA)) if c.natureza is Natureza.RECONHECIDO}
    assert "mora" in chaves
    assert not chaves & {"multa_dl911", "perdas_danos", "restituicao_veiculo", "repeticao"}
