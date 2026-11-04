"""Validação pericial com parecer FICTÍCIO calculado de forma independente do motor."""

from collections import Counter
from decimal import Decimal

import json
import pytest
from openpyxl import Workbook

from cm_calc import cli
from cm_calc.validacao.comparacao import consistencia_interna
from cm_calc.validacao.ficha import carregar_ficha, gerar_modelo, pendencias_ficha
from cm_calc.validacao.leitura_parecer import ler_parecer_pdf, ler_parecer_xlsx, verificar_anonimizacao, texto_pdf
from cm_calc.validacao.modelos import Classe
from cm_calc.validacao.pasta import Validacao
from tests.validacao import parecer_ficticio as PF


@pytest.fixture(autouse=True)
def dados(tmp_path, monkeypatch):
    monkeypatch.setenv("CM_CALC_DADOS", str(tmp_path / "dados"))


@pytest.fixture
def pasta():
    v = Validacao("VAL-TESTE")
    v.preparar()
    liberar_para_teste(v, PF.gerar_pdf(v.pasta / "parecer" / "parecer.pdf"))
    PF.preencher_ficha(v.pasta / "ficha.xlsx")
    (v.pasta / "indices" / "INPC_FICT.csv").write_text(PF.csv_indice(), encoding="utf-8")
    (v.pasta / "indices" / "INPC_FICT.fonte.txt").write_text("série fictícia de teste", encoding="utf-8")
    return v


def liberar_para_teste(v, arq):
    """Registra a liberação como o comando 'liberar' faria (arquivo fictício)."""
    import hashlib, json
    with (v.pasta / "anonimizacao" / "liberacoes.jsonl").open("a") as f:
        f.write(json.dumps({"arquivo": arq.name, "sha256": hashlib.sha256(arq.read_bytes()).hexdigest()}) + "\n")
    return arq


@pytest.fixture
def resultado(pasta):
    return pasta.executar()[0]


# --- Leitura do parecer ------------------------------------------------------------------------

def test_tabelas_extraidas_do_pdf_conferem_com_o_gerador(tmp_path):
    p = ler_parecer_pdf(PF.gerar_pdf(tmp_path / "p.pdf").read_bytes(), "p.pdf")
    assert set(p.tabelas) == {"AP01", "AP02", "AP03"}
    for ap, ref, cols in (("AP01", PF.ap01(), {"juros": "juros", "saldo": "saldo", "prestacao": "prest"}),
                          ("AP02", PF.ap02(), {"juros": "juros", "saldo": "saldo", "amortizacao": "amort"}),
                          ("AP03", PF.ap03(), {"pago": "pago", "restituir": "rest", "total": "total"})):
        linhas = p.tabelas[ap].linhas
        assert len(linhas) == len(ref)
        for lp, lr in zip(linhas, ref):
            assert lp.numero == lr["n"] and lp.data == lr["d"]
            for col, chave in cols.items():
                assert lp.valores[col] == lr[chave], (ap, lp.numero, col)
    assert p.tabelas["AP01"].totais["juros"] == sum(l["juros"] for l in PF.ap01())


def test_indicios_de_metodologia(tmp_path):
    p = ler_parecer_pdf(PF.gerar_pdf(tmp_path / "p.pdf").read_bytes(), "p.pdf")
    achados = {(m.tema, m.descricao.split()[0]) for m in p.metodologia}
    assert ("capitalização", "capitalizacao") in achados
    temas = {m.tema for m in p.metodologia}
    assert {"base de dias", "correção monetária", "juros de mora", "restituição", "arredondamento", "data-base"} <= temas
    assert not any("10/02/2023" in m.descricao for m in p.metodologia)          # tabela não vira indício


def test_planilha_da_perita(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "AP02"
    ws.append(["Evolução revisada"])
    ws.append(["Nº", "Vencimento", "Saldo Inicial", "Juros", "Amortização", "Prestação", "Saldo Final"])
    for l in PF.ap02():
        ws.append([l["n"], l["d"], float(l["ant"]), float(l["juros"]), float(l["amort"]), float(l["prest"]), float(l["saldo"])])
    arq = tmp_path / "perita.xlsx"
    wb.save(arq)
    t = ler_parecer_xlsx(arq.read_bytes(), arq.name)["AP02"]
    assert len(t.linhas) == 12 and t.linhas[6].valores["juros"] == PF.ap02()[6]["juros"]


def test_verificacao_de_anonimizacao(tmp_path):
    limpo = PF.gerar_pdf(tmp_path / "a.pdf")
    assert verificar_anonimizacao(texto_pdf(limpo.read_bytes())) == []
    sujo = PF.gerar_pdf(tmp_path / "b.pdf", "Requerente: MARIA TESTE DE SOUZA, CPF 123.456.789-09.\n")
    achados = verificar_anonimizacao(texto_pdf(sujo.read_bytes()))
    assert any(a.startswith("CPF") for a in achados) and any(a.startswith("NOME") for a in achados)
    assert not any("123.456" in a or "MARIA" in a for a in achados)           # o relatório não expõe o dado


# --- Ficha ------------------------------------------------------------------------------------

def test_modelo_de_ficha_e_pendencias(tmp_path):
    arq = gerar_modelo(tmp_path / "f.xlsx")
    f = carregar_ficha(arq.read_bytes())
    pend = pendencias_ficha(f, {"AP01", "AP02", "AP03"})
    assert any("data_liberacao" in p for p in pend) and any("parcelas" in p for p in pend)
    PF.preencher_ficha(arq)
    f = carregar_ficha(arq.read_bytes())
    assert pendencias_ficha(f, {"AP01", "AP02", "AP03"}) == []
    assert f.percentual("taxa_mensal_contrato") == Decimal("0.025")
    assert [p.tipo for p in f.parcelas].count("reforçada") == 1


def test_ficha_exige_tratamento_de_reforcadas_e_encargos(tmp_path):
    arq = gerar_modelo(tmp_path / "f.xlsx")
    PF.preencher_ficha(arq, tratamento_reforcadas="", encargos_no_ap03="")
    pend = pendencias_ficha(carregar_ficha(arq.read_bytes()), {"AP03"})
    assert any("tratamento_reforcadas" in p for p in pend) and any("encargos_no_ap03" in p for p in pend)


# --- Comparação e diagnóstico ------------------------------------------------------------------

def test_consistencia_interna_detecta_erro_material(tmp_path):
    p = ler_parecer_pdf(PF.gerar_pdf(tmp_path / "p.pdf").read_bytes(), "p.pdf")
    inc = consistencia_interna(p.tabelas["AP02"])
    assert {i.numero for i in inc} == {7}
    assert consistencia_interna(p.tabelas["AP01"]) == []


def test_ap01_capitalizacao_diaria_comprovada_por_cenario(resultado):
    melhor = resultado.cenarios["AP01"][0]
    assert melhor.nome == "dias_base_365, truncamento por parcela" and melhor.reproduz
    assert melhor.linhas_identicas == melhor.linhas == 60
    div = [c for c in resultado.comparacoes if c.apendice == "AP01" and c.classe is Classe.DIVERGENTE]
    assert div and all(c.justificativa.startswith("COMPROVADO") for c in div)
    juros1 = next(c for c in div if c.numero == 1 and c.coluna == "juros")
    assert juros1.perita == Decimal("764.56") and juros1.motor == Decimal("750.00")
    assert juros1.diferenca == Decimal("-14.56") and juros1.diferenca_pct is not None
    assert "capitalização diária pela taxa anual, base 365" in juros1.justificativa


def test_saldo_negativo_da_perita_equivale_ao_excedente_do_motor(resultado):
    """Linha 12 do AP01 (perita: saldo −27,45) no cenário diário: mesma informação, convenção diferente."""
    from cm_calc.motor.numeros import ModoArredondamento, PoliticaArredondamento
    from cm_calc.motor.taxas import ConvencaoTempo
    from cm_calc.validacao.comparacao import valor_motor_evolucao
    from cm_calc.validacao.reconstrucao import reconstruir
    f = Validacao("VAL-TESTE").ficha()
    r = reconstruir(f, {}, convencao_contrato=ConvencaoTempo.DIAS_BASE_365, com_ap03=False,
                    politica=PoliticaArredondamento(casas=2, modo=ModoArredondamento.TRUNCAR, arredondar_cada_parcela=True))
    l12 = r.ap01.linhas[-1]
    assert l12.saldo == 0 and l12.excedente == Decimal("27.45")
    assert valor_motor_evolucao(l12, "saldo") == PF.ap01()[-1]["saldo"] == Decimal("-27.45")


def test_ap02_erro_material_nao_e_atribuido_a_cenario(resultado):
    c = Counter(x.classe for x in resultado.comparacoes if x.apendice == "AP02")
    assert c[Classe.DIVERGENTE] == 2 and c[Classe.IDENTICO] == 58
    for x in resultado.comparacoes:
        if x.apendice == "AP02" and x.classe is Classe.DIVERGENTE:
            assert x.numero == 7 and x.coluna in ("juros", "amortizacao")
            assert x.justificativa.startswith("INCONSISTÊNCIA INTERNA DO PARECER")
            assert "NÃO REPRODUZIDO" in x.justificativa and "COMPROVADO" not in x.justificativa
    assert next(t for t in resultado.totais if "prestação regular" in t["item"])["diferenca"] == 0


def test_ap03_regra_de_meses_comprovada_e_juros_herdados(resultado):
    div = [c for c in resultado.comparacoes if c.apendice == "AP03" and c.classe is Classe.DIVERGENTE]
    assert {c.coluna for c in div} == {"corrigido", "juros_mora", "total"}
    corr = [c for c in div if c.coluna == "corrigido"]
    assert all("mês da data-base=sim" in c.justificativa and "COMPROVADO" in c.justificativa for c in corr)
    assert all("herdada do valor corrigido" in c.justificativa for c in div if c.coluna == "juros_mora")
    ident = {c.coluna for c in resultado.comparacoes if c.apendice == "AP03" and c.classe is Classe.IDENTICO}
    assert {"pago", "devido", "diferenca", "restituir"} <= ident                # nominal confere
    nominal = next(t for t in resultado.totais if "nominal" in t["item"])
    assert nominal["perita"] == nominal["motor"] == sum(l["rest"] for l in PF.ap03())
    assert next(t for t in resultado.totais if "total atualizado" in t["item"])["diferenca"] != 0


def test_relatorios_gerados(pasta):
    rv, md, xlsx = pasta.executar()
    texto = md.read_text(encoding="utf-8")
    for trecho in ("Metodologia da reconstrução", "Consistência interna do parecer", "Cenários de diagnóstico",
                   "Divergências", "não foram usados como entrada", "capitalizacao diaria"):
        assert trecho in texto, trecho
    from openpyxl import load_workbook
    wb = load_workbook(xlsx)
    assert {"Totais", "AP01", "AP02", "AP03", "Inconsistências perita", "Cenários"} <= set(wb.sheetnames)
    assert (pasta.pasta / "saida" / "comparativo.json").exists()


def test_motor_nao_usa_resultados_da_perita(pasta):
    """Mesma ficha, parecer com resultados adulterados: a reconstrução do motor não muda."""
    a = pasta.executar()[0].principal
    liberar_para_teste(pasta, PF.gerar_pdf(pasta.pasta / "parecer" / "parecer.pdf", texto_extra="(versão adulterada)\n"))
    b = pasta.executar()[0].principal
    assert a.ap01.model_dump() == b.ap01.model_dump() and a.ap02.model_dump() == b.ap02.model_dump()


def test_bloqueios(pasta):
    liberar_para_teste(pasta, PF.gerar_pdf(pasta.pasta / "parecer" / "parecer.pdf",
                                           "Requerente: MARIA TESTE DE SOUZA, CPF 123.456.789-09.\n"))
    with pytest.raises(PermissionError, match="dados pessoais"):
        pasta.executar()
    assert pasta.executar("Advogada (teste) — falso positivo conferido")[0] is not None
    (pasta.pasta / "indices" / "INPC_FICT.fonte.txt").unlink()
    with pytest.raises(ValueError, match="fonte oficial"):
        pasta.executar("Advogada (teste)")


def test_cli_validacao(pasta, capsys):
    assert cli.main(["validacao", "verificar", "VAL-TESTE"]) == 0
    out = capsys.readouterr().out
    assert "sem indícios de dados pessoais" in out and "AP01: 12 linhas" in out and "Pronto para executar" in out
    assert cli.main(["validacao", "executar", "VAL-TESTE"]) == 0
    assert "divergente(s)" in capsys.readouterr().out


def test_parecer_nao_liberado_ou_alterado_e_recusado(pasta):
    arq = pasta.pasta / "parecer" / "parecer.pdf"
    arq.write_bytes(arq.read_bytes() + b"\n% alterado")
    with pytest.raises(PermissionError, match="não liberado"):
        pasta.ler_parecer()


def test_versao_revogada_e_recusada_mesmo_se_liberada(pasta):
    import hashlib
    arq = pasta.pasta / "parecer" / "parecer.pdf"
    h = hashlib.sha256(arq.read_bytes()).hexdigest()
    pasta.revogar(h, "identificadores residuais", "Teste Fictício")
    with pytest.raises(PermissionError, match="REVOGADA"):
        pasta.ler_parecer()
    # registro de auditoria: só hash, motivo, responsável e data
    ultimo = json.loads((pasta.pasta / "anonimizacao" / "liberacoes.jsonl").read_text().splitlines()[-1])
    assert set(ultimo) == {"revogado", "sha256", "motivo", "por", "revogado_em"}
    # nova liberação do mesmo arquivo não desfaz a revogação
    liberar_para_teste(pasta, arq)
    with pytest.raises(PermissionError, match="REVOGADA"):
        pasta.ler_parecer()


def test_revogacao_exige_hash_liberado_motivo_e_responsavel(pasta):
    with pytest.raises(ValueError):
        pasta.revogar("abc", "motivo", "Fulano")
    with pytest.raises(ValueError, match="não consta"):
        pasta.revogar("0" * 64, "motivo", "Fulano")
    import hashlib
    h = hashlib.sha256((pasta.pasta / "parecer" / "parecer.pdf").read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="motivo"):
        pasta.revogar(h, " ", "Fulano")
