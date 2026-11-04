"""Anonimização: camadas difíceis do PDF (v0.6.9). Tudo com material FICTÍCIO.

Reproduz a falha do VAL-001 (certidão em colunas: rótulos numa linha, valores na de baixo) e testa
texto fora da página, branco/minúsculo, XObjects, imagens em linha, camadas ocultas, estruturas
internas (formulário, assinatura digital, texto alternativo, rótulos de página, ActualText),
desenhos vetoriais e revisões incrementais — sempre conferindo que os dados financeiros permanecem.
"""

import hashlib
import zlib

import pymupdf
import pytest

from cm_calc.privacidade.anonimizacao import (anonimizar_pdf, detectar, detectar_por_posicao, texto_estrutural,
                                              verificar_pdf)

FIN = "Valor financiado R$ 30.000,00 em 10/01/2023 a 2,5% a.m."
FIN_TOKENS = ("30.000,00", "10/01/2023", "2,5%")
CPF_FICT = "529.982.247-25"          # CPF fictício com dígitos verificadores válidos (só para teste)


def novo_pdf(tmp_path, nome, montar):
    doc = pymupdf.open()
    pg = doc.new_page()
    pg.insert_text((40, 40), FIN, fontsize=8)
    montar(doc, pg)
    arq = tmp_path / f"{nome}.pdf"
    doc.save(arq)
    doc.close()
    return arq


def colunas(pg, y, celulas, size=8):
    for x, t in celulas:
        pg.insert_text((x, y), t, fontsize=size)


def tudo_no_arquivo(arq) -> str:
    """Texto de TODAS as camadas: páginas sem recorte, objetos, fluxos descomprimidos e bytes crus."""
    partes = [arq.read_bytes().decode("latin-1")]
    with pymupdf.open(arq) as d:
        for p in d:
            partes.append(p.get_text("text", flags=0, clip=pymupdf.INFINITE_RECT()))
        for x in range(1, d.xref_length()):
            try:
                partes.append(d.xref_object(x, compressed=False))
                if d.xref_is_stream(x):
                    partes.append(d.xref_stream(x).decode("latin-1"))
            except Exception:
                pass
        partes.append(texto_estrutural(d))
    return "\n".join(partes).lower()


def anonimizar_e_conferir(tmp_path, arq, segredos, termos=None):
    r = anonimizar_pdf(arq, tmp_path / f"{arq.stem}-anon.pdf", termos=termos)
    t = tudo_no_arquivo(r.destino)
    for s in segredos:
        assert s.lower() not in t, s
    with pymupdf.open(r.destino) as d:
        visivel = " ".join(p.get_text("text") for p in d)
    for tok in FIN_TOKENS:
        assert tok in visivel, tok
    return r


# --- 1. Falha do VAL-001: certidão em colunas reais --------------------------------------------------

def test_certidao_em_colunas_reais(tmp_path):
    def m(doc, pg):
        pg.insert_text((40, 90), "CERTIDÃO DE REGISTRO E REGULARIDADE", fontsize=9)
        colunas(pg, 110, [(40, "NOME"), (220, "REGISTRO"), (300, "CPF"), (400, "RG")])
        colunas(pg, 122, [(40, "FULANA PERITA FICTICIA"), (220, "77777"), (300, CPF_FICT), (400, "1234567890")])
        colunas(pg, 140, [(40, "TIPO REGISTRO"), (220, "SITUAÇÃO")])
        colunas(pg, 152, [(40, "Principal PF"), (220, "Ativo")])
    arq = novo_pdf(tmp_path, "certidao", m)
    r = anonimizar_e_conferir(tmp_path, arq, ["77777", "1234567890", CPF_FICT, "fulana"])
    assert r.verificacao.aprovada, r.resumo()
    assert "Principal PF" in tudo_no_arquivo(r.destino).title() or "principal pf" in tudo_no_arquivo(r.destino)


def test_verificacao_reprova_certidao_em_colunas_nao_tratada(tmp_path):
    """A verificação, sozinha, precisa achar o resíduo que a v0.6.8 deixou passar."""
    def m(doc, pg):
        colunas(pg, 110, [(40, "NOME"), (220, "REGISTRO"), (400, "RG")])
        colunas(pg, 122, [(40, "[NOME]"), (220, "77777"), (400, "1234567890")])
    arq = novo_pdf(tmp_path, "residuo", m)
    v = verificar_pdf(arq, arq, hashlib.sha256(arq.read_bytes()).hexdigest(), [], [], [])
    assert v.residuos_padrao.get("IDENTIFICADOR") == 2 and not v.aprovada


@pytest.mark.parametrize("rotulo,valor", [
    ("R.G.", "12.345.678-9"), ("RG nº", "MG-12.345.678"), ("Nº REGISTRO", "AL-1234/O"), ("IDENTIDADE", "1234567 SSP/AL"),
    ("CNH", "01234567890"), ("Matrícula", "445566"), ("PIS/PASEP", "123.45678.90-1"), ("CTPS", "1234567"),
    ("Passaporte", "FX123456"), ("Título de eleitor", "1234 5678 9012"),
])
def test_variacoes_de_rotulo_e_formato_em_colunas(tmp_path, rotulo, valor):
    def m(doc, pg):
        colunas(pg, 110, [(40, rotulo), (300, "SITUAÇÃO")])
        colunas(pg, 122, [(40, valor), (300, "Ativo")])
    anonimizar_e_conferir(tmp_path, novo_pdf(tmp_path, "var", m), [valor])


@pytest.mark.parametrize("frase,valor", [
    ("RG nº 98.765.432-1 SSP/AL", "98.765.432-1"), ("R.G.: MG-12.345.678", "12.345.678"),
    ("Matrícula 445566", "445566"), ("PIS 123.45678.90-1", "123.45678.90-1"),
    ("CTPS 1234567 série 0012", "1234567"), ("Registro: 77777", "77777"),
    ("Carteira de Identidade 1234567890", "1234567890"),
])
def test_variacoes_na_mesma_linha(tmp_path, frase, valor):
    def m(doc, pg):
        pg.insert_text((40, 120), f"Qualificação: {frase}; valor da causa R$ 1.234,56.", fontsize=8)
    anonimizar_e_conferir(tmp_path, novo_pdf(tmp_path, "linha", m), [valor])


def test_rotulo_e_valor_em_celulas_lado_a_lado(tmp_path):
    def m(doc, pg):
        colunas(pg, 110, [(40, "RG:"), (200, "1234567890")])
        colunas(pg, 122, [(40, "Registro"), (200, "77777")])
    anonimizar_e_conferir(tmp_path, novo_pdf(tmp_path, "lado", m), ["1234567890", "77777"])


# --- 2. Sem falsos positivos: tabelas, valores, datas e fórmulas ------------------------------------

def test_tabela_financeira_com_rotulos_parecidos_fica_intacta(tmp_path):
    def m(doc, pg):
        colunas(pg, 110, [(40, "Nº"), (80, "Registro"), (180, "Vencimento"), (280, "Valor (R$)"), (380, "Fator")])
        colunas(pg, 122, [(40, "1"), (80, "Pagamento"), (180, "10/02/2023"), (280, "1.104,74"), (380, "1,0123456")])
        colunas(pg, 134, [(40, "2"), (80, "Pagamento"), (180, "10/03/2023"), (280, "1.104,74"), (380, "1,0234567")])
        pg.insert_text((40, 160), "Fórmula: PMT = PV × i / (1 − (1 + i)^−n), com n = 60 e i = 2,5%", fontsize=8)
        pg.insert_text((40, 175), "Registro de 2023 conforme Anexo 3; matrícula do imóvel não informada.", fontsize=8)
    arq = novo_pdf(tmp_path, "tabela", m)
    r = anonimizar_pdf(arq, tmp_path / "tabela-anon.pdf")
    with pymupdf.open(arq) as o, pymupdf.open(r.destino) as d:
        assert o[0].get_text("text") == d[0].get_text("text")       # nada removido
    assert r.remocoes == [] and r.verificacao.aprovada


def test_numeros_de_tabela_sob_rotulo_de_documento_nao_sao_financeiros_removidos(tmp_path):
    """Sob um rótulo de documento, valor monetário/data nunca é removido (guarda financeira)."""
    def m(doc, pg):
        colunas(pg, 110, [(40, "REGISTRO"), (200, "DATA")])
        colunas(pg, 122, [(40, "1.234,56"), (200, "10/01/2023")])
    r = anonimizar_pdf(novo_pdf(tmp_path, "guarda", m), tmp_path / "g.pdf")
    assert not r.verificacao.tokens_ausentes and r.verificacao.aprovada


# --- 3. Texto pesquisável escondido -----------------------------------------------------------------

def test_texto_fora_da_area_da_pagina(tmp_path):
    def m(doc, pg):
        pg.insert_text((40, 900), f"CPF {CPF_FICT} FULANA PERITA FICTICIA", fontsize=8)
        pg.insert_text((-300, 100), "Perita Fulana", fontsize=8)
    r = anonimizar_e_conferir(tmp_path, novo_pdf(tmp_path, "fora", m), [CPF_FICT, "fulana"])
    assert r.verificacao.aprovada and r.verificacao.texto_fora_da_pagina == 0


def test_verificacao_reprova_texto_fora_da_pagina(tmp_path):
    arq = novo_pdf(tmp_path, "fora2", lambda doc, pg: pg.insert_text((40, 900), "qualquer coisa", fontsize=8))
    v = verificar_pdf(arq, arq, hashlib.sha256(arq.read_bytes()).hexdigest(), [], [], [])
    assert v.texto_fora_da_pagina == 2 and not v.aprovada


def test_texto_branco_minusculo_e_invisivel(tmp_path):
    def m(doc, pg):
        pg.insert_text((40, 200), "Perita: Fulana Perita Ficticia", fontsize=8, color=(1, 1, 1))
        pg.insert_text((40, 220), "RG 1234567890", fontsize=0.5)
        pg.insert_text((40, 240), f"CPF {CPF_FICT}", fontsize=8, render_mode=3)
    anonimizar_e_conferir(tmp_path, novo_pdf(tmp_path, "oculto", m), ["fulana", "1234567890", CPF_FICT])


def test_texto_dentro_de_xobject(tmp_path):
    def m(doc, pg):
        src = pymupdf.open()
        sp = src.new_page(width=300, height=100)
        sp.insert_text((10, 30), "Perita: Fulana Perita Ficticia", fontsize=8)
        sp.insert_text((10, 50), f"CPF {CPF_FICT}", fontsize=8)
        pg.show_pdf_page(pymupdf.Rect(40, 300, 340, 400), src, 0)
    anonimizar_e_conferir(tmp_path, novo_pdf(tmp_path, "xobj", m), ["fulana", CPF_FICT])


def test_camada_opcional_oculta(tmp_path):
    def m(doc, pg):
        oc = doc.add_ocg("Camada fictícia", on=False)
        pg.insert_text((40, 260), f"Perita: Fulana Perita Ficticia CPF {CPF_FICT}", fontsize=8, oc=oc)
    r = anonimizar_e_conferir(tmp_path, novo_pdf(tmp_path, "ocg", m), ["fulana", CPF_FICT])
    assert r.camadas_opcionais == 1 and r.resumo()["camadas_opcionais_reveladas"] == 1


# --- 4. Metadados, anotações, assinaturas e estruturas internas ------------------------------------

def test_formulario_assinatura_digital_e_estruturas_internas(tmp_path):
    def m(doc, pg):
        w = pymupdf.Widget()
        w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        w.field_name = "FULANA PERITA FICTICIA"
        w.field_value = f"CPF {CPF_FICT}"
        w.rect = pymupdf.Rect(40, 500, 200, 520)
        pg.add_widget(w)
        cat = doc.pdf_catalog()
        x = doc.get_new_xref()
        doc.update_object(x, "<< /Certs [ (CN=FULANA PERITA FICTICIA:52998224725) ] >>")
        doc.xref_set_key(cat, "DSS", f"{x} 0 R")
        x2 = doc.get_new_xref()
        doc.update_object(x2, "<< /Type /StructTreeRoot /K << /S /Figure /Alt (Assinatura de Fulana Perita Ficticia) >> >>")
        doc.xref_set_key(cat, "StructTreeRoot", f"{x2} 0 R")
        doc.xref_set_key(cat, "PageLabels", "<< /Nums [0 << /P (Fulana-) >>] >>")
        x3 = doc.get_new_xref()
        doc.update_object(x3, "<< /Type /Metadata /Subtype /XML /Length 0 >>")
        doc.update_stream(x3, b"<x:xmpmeta><dc:creator>Fulana Perita Ficticia</dc:creator></x:xmpmeta>")
        doc.xref_set_key(pg.xref, "Metadata", f"{x3} 0 R")
        pg.add_text_annot((300, 320), "Obs.: Fulana ligou")
        doc.set_metadata({"author": "Fulana Perita Ficticia", "keywords": CPF_FICT})
        cx = pg.get_contents()[0]
        doc.update_stream(cx, doc.xref_stream(cx) + b"\n/Span <</ActualText (RG 1234567890)>> BDC EMC\n")
    r = anonimizar_e_conferir(tmp_path, novo_pdf(tmp_path, "estruturas", m),
                              ["fulana", "52998224725", CPF_FICT, "1234567890"])
    v = r.verificacao
    assert v.aprovada and v.estruturas_internas == 0 and v.residuos_estruturais == {} and v.anotacoes == 0


def test_verificacao_reprova_dado_em_estrutura_interna(tmp_path):
    def m(doc, pg):
        x = doc.get_new_xref()
        doc.update_object(x, f"<< /Certs [ (CN=FULANA PERITA FICTICIA CPF {CPF_FICT}) ] >>")
        doc.xref_set_key(doc.pdf_catalog(), "DSS", f"{x} 0 R")
    arq = novo_pdf(tmp_path, "dss", m)
    v = verificar_pdf(arq, arq, hashlib.sha256(arq.read_bytes()).hexdigest(), [], [], [])
    assert v.residuos_estruturais.get("CPF") and v.estruturas_internas >= 1 and not v.aprovada


def test_revisao_incremental_anterior_nao_sobrevive(tmp_path):
    arq = novo_pdf(tmp_path, "incr", lambda doc, pg: doc.set_metadata({"author": "Fulana Perita Ficticia"}))
    doc = pymupdf.open(arq)
    doc.set_metadata({})
    doc.saveIncr()                    # o nome continua nos bytes da revisão anterior do ORIGINAL
    doc.close()
    assert b"Fulana" in arq.read_bytes()
    r = anonimizar_e_conferir(tmp_path, arq, ["fulana"])
    assert r.verificacao.revisoes == 1 and r.verificacao.aprovada


# --- 5. Elementos visuais ----------------------------------------------------------------------------

def _rubrica(pg, x=60, y=650, tracos=30):
    s = pg.new_shape()
    p0 = pymupdf.Point(x, y)
    for i in range(tracos):
        p1 = pymupdf.Point(x + i * 6, y - 10 + (i % 5) * 4)
        s.draw_bezier(p0, p0 + (3, -10), p1 + (-3, 10), p1)
        p0 = p1
    s.finish(color=(0, 0, 0), width=0.8)
    s.commit()


def test_assinatura_desenhada_em_vetor_e_removida_sem_apagar_texto(tmp_path):
    def m(doc, pg):
        pg.insert_text((40, 600), "Laudo concluído; saldo R$ 2.345,67.", fontsize=8)
        _rubrica(pg)
        pg.insert_text((60, 660), "Perita do juízo", fontsize=8)        # texto sobre a área da rubrica
        pg.draw_rect(pymupdf.Rect(40, 100, 500, 200))                      # moldura de tabela: não é rubrica
    r = anonimizar_e_conferir(tmp_path, novo_pdf(tmp_path, "rubrica", m), [])
    with pymupdf.open(r.destino) as d:
        t = d[0].get_text("text")
        assert "Perita do juízo" in t and "2.345,67" in t
        assert not any(any(it[0] == "c" for it in p["items"]) for p in d[0].get_drawings())
        assert any(p["rect"].width > 400 for p in d[0].get_drawings())        # a moldura continua
    assert r.vetores_removidos == 1 and r.verificacao.vetores_suspeitos == 0 and r.verificacao.aprovada


def test_imagem_em_linha_no_fluxo_da_pagina(tmp_path):
    def m(doc, pg):
        cx = pg.get_contents()[0]
        img = b"q 80 0 0 30 40 700 cm BI /W 2 /H 2 /CS /G /BPC 8 ID \x00\xff\xff\x00 EI Q\n"
        doc.update_stream(cx, doc.xref_stream(cx) + b"\n" + img)
    arq = novo_pdf(tmp_path, "inline", m)
    with pymupdf.open(arq) as o:
        assert len(o[0].get_image_info()) == 1 and o[0].get_images() == []     # invisível para get_images()
    r = anonimizar_e_conferir(tmp_path, arq, [])
    assert r.imagens_removidas == 1 and r.verificacao.imagens == 0 and r.verificacao.aprovada


def test_varredura_estrutural_decodifica_utf16_e_octal():
    d = pymupdf.open()
    d.new_page()
    x = d.get_new_xref()
    nome_utf16 = "Fulana Fictícia".encode("utf-16-be")
    d.update_object(x, f"<< /A <FEFF{nome_utf16.hex()}> /B (Jo\\343o Ficticio) >>")
    t = texto_estrutural(d)
    assert "Fulana Fictícia" in t and "João Ficticio" in t
