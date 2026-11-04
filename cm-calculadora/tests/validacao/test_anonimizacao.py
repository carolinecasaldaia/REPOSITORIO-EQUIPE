"""Anonimização local de parecer FICTÍCIO com dados pessoais em todos os lugares usuais."""

import hashlib
import json

import pymupdf
import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment

from cm_calc import cli
from cm_calc.privacidade.anonimizacao import anonimizar_csv, anonimizar_pdf, anonimizar_xlsx, detectar, protegido
from cm_calc.validacao.pasta import Validacao
from tests.validacao import parecer_ficticio as PF

PII = ["JOANA EXEMPLO DA SILVA", "Joana", "123.456.789-09", "Rua das Flores", "01000-000", "91234-5678",
       "joana@exemplo.com", "0001234-56.2023.8.26.0000", "2023-000777", "Fulana Perita Teste", "CORECON",
       "12345678", "pje.tjsp.jus.br", "987.654.321-00", "PROPOSTA-ABC-77", "ABC1D23"]
CAPA = """PARECER TÉCNICO-PERICIAL (FICTÍCIO)
Processo nº 0001234-56.2023.8.26.0000
Autor: JOANA EXEMPLO DA SILVA, brasileira, inscrita no CPF 123.456.789-09, residente na Rua das Flores, 100,
CEP 01000-000, telefone (11) 91234-5678, e-mail joana@exemplo.com. Veículo placa ABC1D23.
Cédula de Crédito Bancário nº 2023-000777, proposta interna PROPOSTA-ABC-77.
Perita: Dra. Fulana Perita Teste, CORECON/SP nº 12.345
O valor financiado foi de R$ 30.000,00 à taxa de 2,5% a.m., com liberação em 10/01/2023.
A perícia foi requerida pela autora JOANA EXEMPLO
DA SILVA, conforme despacho.
Assinado eletronicamente por: FULANA PERITA TESTE - 10/10/2024
Num. 12345678 - Pág. 1   https://pje.tjsp.jus.br/validacao?id=99887766
"""


def parecer_sujo(destino):
    PF.gerar_pdf(destino)
    pdf = pymupdf.open(destino)
    capa = pdf.new_page(pno=0)
    capa.insert_text((40, 60), CAPA, fontsize=8)
    capa.insert_text((40, 300), "CPF oculto 987.654.321-00", fontsize=8, render_mode=3)      # texto invisível
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 80, 24), False)
    pix.set_rect(pix.irect, (20, 20, 20))
    capa.insert_image(pymupdf.Rect(40, 320, 160, 356), pixmap=pix)                            # "assinatura"
    capa.add_text_annot((300, 320), "Obs.: cliente Joana ligou")
    pdf.embfile_add("dados.txt", b"CPF 123.456.789-09")
    pdf.set_metadata({"author": "Fulana Perita Teste", "title": "Parecer Joana Exemplo", "subject": "processo 0001234"})
    pdf.set_toc([[1, "Parecer - JOANA EXEMPLO DA SILVA", 1], [1, "AP01", 3]])
    tmp = destino.with_suffix(".tmp.pdf")
    pdf.save(tmp)
    pdf.close()
    tmp.replace(destino)
    return destino


def texto_total(arq) -> str:
    with pymupdf.open(arq) as d:
        partes = []
        for p in d:
            partes += [p.get_text("text"), " ".join(w[4] for w in p.get_text("words"))]
        partes.append(json.dumps(d.metadata, ensure_ascii=False))
        partes.append(d.get_xml_metadata() or "")
        partes.append(json.dumps(d.get_toc(), ensure_ascii=False))
        for i in range(d.embfile_count()):
            partes.append(d.embfile_get(i).decode("latin-1"))
        for p in d:
            for a in p.annots() or []:
                partes.append(a.info.get("content", ""))
    return "\n".join(partes)


@pytest.fixture(autouse=True)
def dados(tmp_path, monkeypatch):
    monkeypatch.setenv("CM_CALC_DADOS", str(tmp_path / "dados"))


@pytest.fixture
def resultado(tmp_path):
    original = parecer_sujo(tmp_path / "original.pdf")
    h = hashlib.sha256(original.read_bytes()).hexdigest()
    r = anonimizar_pdf(original, tmp_path / "anon.pdf", termos=["PROPOSTA-ABC-77"])
    return r, original, h


def test_original_nao_e_alterado(resultado):
    r, original, h = resultado
    assert hashlib.sha256(original.read_bytes()).hexdigest() == h == r.sha256_original
    assert "JOANA EXEMPLO DA SILVA" in texto_total(original)              # o original segue com os dados


def test_dados_pessoais_removidos_de_todas_as_camadas(resultado):
    r, _, _ = resultado
    t = texto_total(r.destino).lower()
    for dado in PII:
        assert dado.lower() not in t, dado
    with pymupdf.open(r.destino) as d:
        assert sum(len(p.get_images()) for p in d) == 0
        assert d.embfile_count() == 0 and d.get_toc() == []
        assert not any(v for k, v in d.metadata.items() if k not in ("format", "encryption"))
        assert all(not list(p.annots() or []) for p in d)
        assert all(not p.search_for("Joana") for p in d)                  # nem a busca do leitor de PDF encontra


def test_dados_matematicos_preservados(resultado):
    r, _, _ = resultado
    v = r.verificacao
    assert v.tabelas_identicas is True
    assert not v.tokens_ausentes and v.tokens_financeiros_preservados == v.tokens_financeiros_original > 100
    t = texto_total(r.destino)
    for valor in ("R$ 30.000,00", "2,5% a.m.", "10/01/2023"):
        assert valor in t, valor


def test_verificacao_aprovada_e_resumo_sem_dados_pessoais(resultado):
    r, _, _ = resultado
    assert r.verificacao.aprovada, r.resumo()
    resumo = json.dumps(r.resumo(), ensure_ascii=False).lower()
    for dado in PII:
        assert dado.lower() not in resumo, dado
    tipos = r.resumo()["remocoes_por_tipo"]
    assert {"CPF", "NOME", "PROCESSO", "CONTRATO", "EMAIL", "TELEFONE", "TERMO_INFORMADO", "URL"} <= set(tipos)
    assert r.imagens_removidas == 1


def test_valores_financeiros_nunca_sao_removidos():
    assert protegido("1.234,56") and protegido("R$ 30.000,00") and protegido("2,5%") and protegido("10/01/2023")
    itens = detectar("Valor: R$ 1.234,56", termos=["1.234,56", "10/01/2023"])
    assert itens == []


def test_planilha_e_csv(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "AP01"
    ws.append(["Autor: JOANA EXEMPLO DA SILVA", "CPF 123.456.789-09"])
    ws.append(["Nº", "Juros"])
    ws.append([1, 764.56])
    ws["A1"].comment = Comment("anotação sobre Joana", "Fulana")
    wb.properties.creator = "Fulana Perita Teste"
    wb.save(tmp_path / "p.xlsx")
    rem, _ = anonimizar_xlsx(tmp_path / "p.xlsx", tmp_path / "p-anon.xlsx")
    w2 = load_workbook(tmp_path / "p-anon.xlsx")
    s = w2.active
    assert "JOANA" not in str(s["A1"].value) and "123.456" not in str(s["B1"].value)
    assert s["B3"].value == 764.56 and s["A1"].comment is None
    assert (w2.properties.creator or "") != "Fulana Perita Teste"
    (tmp_path / "c.csv").write_text("Autor;JOANA EXEMPLO DA SILVA\nCPF;123.456.789-09\nvalor;2.825,92\n", encoding="utf-8")
    rem, faltam = anonimizar_csv(tmp_path / "c.csv", tmp_path / "c-anon.csv")
    t = (tmp_path / "c-anon.csv").read_text()
    assert "JOANA" not in t and "123.456" not in t and "2.825,92" in t and faltam == 0


def test_fluxo_completo_na_pasta_de_validacao(tmp_path, capsys):
    v = Validacao("VAL-ANON")
    v.preparar()
    parecer_sujo(v.pasta / "original" / "parecer.pdf")
    h = hashlib.sha256((v.pasta / "original" / "parecer.pdf").read_bytes()).hexdigest()
    (v.pasta / "anonimizacao" / "termos.txt").write_text("# termos\nPROPOSTA-ABC-77\n", encoding="utf-8")
    assert cli.main(["validacao", "anonimizar", "VAL-ANON"]) == 0
    saida = capsys.readouterr().out
    assert "APROVADA" in saida
    for dado in PII:
        assert dado.lower() not in saida.lower(), dado                  # a tela não mostra dados pessoais
    verif = (v.pasta / "anonimizacao" / "verificacao.md").read_text()
    assert all(d.lower() not in verif.lower() for d in PII)
    detalhado = (v.pasta / "anonimizacao" / "relatorio-detalhado-documento-01.md").read_text()
    assert "123.456.789-09" in detalhado                                  # o detalhado (confidencial) mostra
    assert hashlib.sha256((v.pasta / "original" / "parecer.pdf").read_bytes()).hexdigest() == h
    # sem liberação, nada chega à pasta usada na validação
    assert not list((v.pasta / "parecer").iterdir())
    with pytest.raises(ValueError):
        v.liberar("documento-01-anonimizado.pdf", "parecer", " ")
    # sem a declaração expressa de conferência, a linha de comando não libera
    assert cli.main(["validacao", "liberar", "VAL-ANON", "documento-01-anonimizado.pdf", "--como", "parecer",
                     "--por", "Advogada (teste)"]) == 2
    assert not list((v.pasta / "parecer").iterdir())
    assert cli.main(["validacao", "liberar", "VAL-ANON", "documento-01-anonimizado.pdf", "--como", "parecer",
                     "--por", "Advogada (teste)", "--confirmo-conferencia"]) == 0
    assert (v.pasta / "parecer" / "documento-01-anonimizado.pdf").exists()
    reg = json.loads((v.pasta / "anonimizacao" / "liberacoes.jsonl").read_text().splitlines()[0])
    assert reg["responsavel"] == "Advogada (teste)" and reg["verificacao_aprovada"] is True
    # o parecer liberado alimenta a validação normalmente
    p = v.ler_parecer()
    assert set(p.tabelas) == {"AP01", "AP02", "AP03"}


def test_liberacao_exige_verificacao_aprovada(tmp_path):
    v = Validacao("VAL-ANON2")
    v.preparar()
    (v.pasta / "original" / "nota.docx").write_bytes(b"x")
    parecer_sujo(v.pasta / "original" / "parecer.pdf")
    resumos = v.anonimizar()
    docx = next(r for r in resumos if r["arquivo_original"] == "documento-01.docx (original)")
    assert docx["verificacao"]["aprovada"] is False and "converta para PDF" in docx["verificacao"]["observacao"]
    ver = json.loads((v.pasta / "anonimizacao" / "verificacao.json").read_text())
    ver[-1]["verificacao"]["aprovada"] = False                            # simula reprovação
    (v.pasta / "anonimizacao" / "verificacao.json").write_text(json.dumps(ver))
    with pytest.raises(PermissionError, match="não aprovada"):
        v.liberar("documento-02-anonimizado.pdf", "parecer", "Advogada")
    assert v.liberar("documento-02-anonimizado.pdf", "parecer", "Advogada", apesar_de="conferido manualmente").exists()


def test_planilha_com_rotulo_e_nome_em_celulas_vizinhas(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["Requerente", "MARIA TESTE DE SOUZA"])
    ws.append(["Saldo", 1234.56])
    wb.save(tmp_path / "v.xlsx")
    anonimizar_xlsx(tmp_path / "v.xlsx", tmp_path / "v-anon.xlsx")
    s = load_workbook(tmp_path / "v-anon.xlsx").active
    assert "MARIA" not in str(s["B1"].value) and s["B2"].value == 1234.56


# --- Regressão do diagnóstico VAL-001 (21/10/2026): material FICTÍCIO --------------------------

def _pdf(tmp_path, paginas):
    d = pymupdf.open()
    for texto in paginas:
        d.new_page().insert_text((40, 60), texto, fontsize=8)
    arq = tmp_path / "f.pdf"
    d.save(arq)
    return arq


def test_maiusculas_e_acentos_em_paginas_diferentes(tmp_path):
    arq = _pdf(tmp_path, ["Autor: JOSÉ CONCEIÇÃO GONÇALVES, brasileiro.\nValor: R$ 1.000,00",
                          "O autor José Conceição Gonçalves alega.\nTaxa de 2,5% a.m.",
                          "Assinado por josé conceição gonçalves em 10/10/2024."])
    r = anonimizar_pdf(arq, tmp_path / "a.pdf")
    t = texto_total(r.destino).lower()
    assert "conceição" not in t and "conceicao" not in t and "gonçalves" not in t
    assert r.verificacao.aprovada and r.verificacao.residuos_removidos == 0


def test_termo_digitado_em_minusculas_com_acento(tmp_path):
    arq = _pdf(tmp_path, ["A perita Ângela Müller Fictícia assina o laudo.\nR$ 2.000,00"])
    r = anonimizar_pdf(arq, tmp_path / "a.pdf", termos=["ângela müller fictícia"])
    t = texto_total(r.destino).lower()
    assert "ângela" not in t and "müller" not in t and r.verificacao.aprovada


def test_nome_quebrado_com_hifen_entre_linhas(tmp_path):
    arq = _pdf(tmp_path, ["Requerida pela autora JOSEFINA ALBU-\nQUERQUE TESTE, conforme despacho."])
    r = anonimizar_pdf(arq, tmp_path / "a.pdf", termos=["Josefina Albuquerque Teste"])
    t = texto_total(r.destino).lower()
    assert "josefina" not in t and "albu" not in t and "querque" not in t


def test_endereco_quebrado_entre_linhas(tmp_path):
    arq = _pdf(tmp_path, ["Consulta: https://www.exemplo-ficticio.invalid/sistema/consulta?id=\n998877665544&tipo=pdf ok\n"
                          "e-mail: perita.ficticia@exemplo.invalid\nValor R$ 3.000,00"])
    r = anonimizar_pdf(arq, tmp_path / "a.pdf")
    t = texto_total(r.destino)
    assert "998877665544" not in t and "exemplo-ficticio" not in t and "perita.ficticia" not in t
    assert "R$ 3.000,00" in t and r.verificacao.aprovada


def test_relatorio_informa_tipo_do_que_sobrou(tmp_path):
    from cm_calc.privacidade.anonimizacao import verificar_pdf
    arq = _pdf(tmp_path, ["Autor: JOANA EXEMPLO DA SILVA\nR$ 1,00"])
    v = verificar_pdf(arq, arq, hashlib.sha256(arq.read_bytes()).hexdigest(), ["JOANA EXEMPLO DA SILVA"], [], [],
                      {"JOANA EXEMPLO DA SILVA": "NOME"})
    assert v.residuos_removidos == 1 and v.reaparecendo_por_tipo == {"NOME": 1} and not v.aprovada


# --- Regressão do vazamento detectado na leitura do VAL-001 (21/10/2026): material FICTÍCIO --------

def test_cpf_sem_rotulo_em_assinatura_digital(tmp_path):
    # 52998224725 é um CPF fictício válido (dígitos verificadores corretos), usado só em teste
    arq = _pdf(tmp_path, ["Perita\nFULANA PERITA TESTE:52998224725\nAssinado de forma digital por FULANA PERITA "
                          "TESTE:52998224725\nDados: 2026.08.17 21:54:50 -03'00'\nValor R$ 1.234,56 em 11/05/2019"])
    r = anonimizar_pdf(arq, tmp_path / "a.pdf")
    t = texto_total(r.destino)
    assert "52998224725" not in t and "FULANA" not in t.upper()
    assert "R$ 1.234,56" in t and "11/05/2019" in t and r.verificacao.aprovada


def test_rotulo_e_valor_em_linhas_separadas(tmp_path):
    arq = _pdf(tmp_path, ["CERTIDÃO DE REGISTRO E REGULARIDADE\nNOME\nREGISTRO\n77777\nCPF\nRG\n1234567890\n"
                          "TIPO REGISTRO\nPrincipal PF"])
    r = anonimizar_pdf(arq, tmp_path / "a.pdf")
    t = texto_total(r.destino)
    assert "77777" not in t and "1234567890" not in t


def test_numero_de_processo_quebrado_entre_linhas(tmp_path):
    arq = _pdf(tmp_path, ["Acórdão de 10/12/2025, Processo nº 0700001-\n11.2025.8.02.0001 (fls. 269-284)."])
    r = anonimizar_pdf(arq, tmp_path / "a.pdf")
    t = texto_total(r.destino)
    assert "0700001" not in t and "11.2025.8.02.0001" not in t and "10/12/2025" in t


def test_numeros_financeiros_de_11_digitos_invalidos_nao_sao_removidos():
    from cm_calc.privacidade.anonimizacao import cpf_valido
    assert cpf_valido("52998224725") and not cpf_valido("12345678901") and not cpf_valido("11111111111")
    itens = detectar("Saldo 53965980000 e código 12345678901")
    assert not any(i.texto in ("53965980000", "12345678901") for i in itens)


# --- Regressão VAL-001 (23/10/2026): certidão com rótulos numa linha e valores na seguinte ---------

def test_certidao_em_colunas_rotulos_e_valores_desalinhados(tmp_path):
    # layout em colunas: o texto extraído traz os rótulos e DEPOIS os valores (dados fictícios)
    arq = _pdf(tmp_path, ["CERTIDÃO DE REGISTRO E REGULARIDADE\nNOME\nREGISTRO\nCPF\nRG\nFULANA PERITA FICTÍCIA\n"
                          "77777\n52998224725\n1234567890\nTIPO REGISTRO\nPrincipal PF\nValor R$ 1.234,56"])
    r = anonimizar_pdf(arq, tmp_path / "a.pdf", termos=["Fulana Perita Fictícia"])
    t = texto_total(r.destino)
    for dado in ("77777", "52998224725", "1234567890", "FULANA"):
        assert dado not in t.upper(), dado
    assert "R$ 1.234,56" in t
    assert r.verificacao.aprovada and r.verificacao.residuos_padrao == {}
    assert r.resumo()["versao_rotina"]


def test_residuo_identificador_reprova_a_verificacao(tmp_path):
    from cm_calc.privacidade.anonimizacao import verificar_pdf
    arq = _pdf(tmp_path, ["REGISTRO\n77777\nValor R$ 1,00"])
    v = verificar_pdf(arq, arq, hashlib.sha256(arq.read_bytes()).hexdigest(), [], [], [])
    assert v.residuos_padrao and not v.aprovada


def test_conferencia_financeira_estrita(tmp_path):
    """Se um valor financeiro sumir da cópia, a verificação reprova — mesmo que estivesse num trecho removido."""
    from cm_calc.privacidade.anonimizacao import verificar_pdf
    orig = _pdf(tmp_path, ["Assinado por FULANA TESTE Valor R$ 1.234,56"])
    d = pymupdf.open()
    d.new_page().insert_text((40, 60), "Assinado por [NOME]", fontsize=8)
    dest = tmp_path / "d.pdf"
    d.save(dest)
    v = verificar_pdf(orig, dest, hashlib.sha256(orig.read_bytes()).hexdigest(),
                      ["FULANA TESTE Valor R$ 1.234,56"], [], [], {"FULANA TESTE Valor R$ 1.234,56": "NOME"})
    assert v.tokens_ausentes == ["1.234,56"] and not v.aprovada
