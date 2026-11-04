"""Imagens residuais (VAL-001, 2ª reprovação: "1 imagem restante" — imagem EM LINHA de 468x12 px no rodapé
da pág. 2). Tudo com PDFs FICTÍCIOS que reproduzem a forma e a estrutura, nunca o conteúdo."""

import json
import zlib

import pymupdf
import pytest

from cm_calc.privacidade.anonimizacao import (anonimizar_pdf, inventario_imagens, neutralizar_imagens_restantes,
                                              remover_imagens_em_linha)

FIN = "Valor financiado R$ 30.000,00 em 10/01/2023 a 2,5% a.m."
W, H = 468, 12


def _inline(dados: bytes, extra: bytes = b"", y=126) -> bytes:
    return (b"q 468 0 0 12 72 %d cm BI /W 468 /H 12 /CS /RGB /BPC 8" % y + extra + b" ID " + dados + b"\nEI Q\n")


def _pdf(tmp_path, nome, *, conteudo_extra=b"", montar=None):
    doc = pymupdf.open()
    pg = doc.new_page(width=612, height=792)
    pg.insert_text((72, 100), FIN, fontsize=8)
    pg.insert_text((72, 640), "Perita do juízo — laudo de 10/02/2023", fontsize=8)
    if conteudo_extra:
        cx = pg.get_contents()[0]
        doc.update_stream(cx, doc.xref_stream(cx) + b"\n" + conteudo_extra)
    if montar:
        montar(doc, pg)
    arq = tmp_path / f"{nome}.pdf"
    doc.save(arq)
    return arq


def _conferir_financeiro(arq):
    with pymupdf.open(arq) as d:
        t = d[0].get_text("text")
    for tok in ("30.000,00", "10/01/2023", "2,5%", "10/02/2023"):
        assert tok in t, tok


# --- reprodução da forma do caso real ------------------------------------------------------------

def test_faixa_em_linha_no_rodape_e_removida(tmp_path):
    arq = _pdf(tmp_path, "faixa", conteudo_extra=_inline(bytes([200, 30, 30] * W * H)))
    with pymupdf.open(arq) as o:
        inv = inventario_imagens(o)
    assert len(inv) == 1 and inv[0]["origem"].startswith("em linha") and inv[0]["pixels"] == "468x12"
    assert inv[0]["zona"] == "rodapé"
    r = anonimizar_pdf(arq, tmp_path / "faixa-anon.pdf")
    assert r.verificacao.imagens == 0 and r.verificacao.aprovada, r.resumo()
    _conferir_financeiro(r.destino)


@pytest.mark.parametrize("variante", ["dados_com_EI", "comprimida_sem_L", "hex_sem_L", "com_L"])
def test_redacao_que_falha_e_coberta_pela_rede_de_seguranca(tmp_path, monkeypatch, variante):
    """Simula a falha real: a redação do MuPDF NÃO remove a imagem. A rede de segurança precisa remover."""
    cru = bytearray([200, 30, 30] * W * H)
    cru[300:304] = b" EI "                                          # bytes que imitam o operador dentro dos dados
    dados, extra = {
        "dados_com_EI": (bytes(cru), b""),
        "comprimida_sem_L": (zlib.compress(bytes(cru)), b" /F /Fl"),
        "hex_sem_L": (bytes(cru).hex().encode() + b">", b" /F /AHx"),
        "com_L": (zlib.compress(bytes(cru)), b" /F /Fl /L %d" % len(zlib.compress(bytes(cru)))),
    }[variante]
    arq = _pdf(tmp_path, variante, conteudo_extra=_inline(dados, extra))
    original = pymupdf.Page.apply_redactions

    def redacao_sem_imagens(self, *a, **k):
        k["images"] = pymupdf.PDF_REDACT_IMAGE_NONE
        return original(self, *a, **k)

    monkeypatch.setattr(pymupdf.Page, "apply_redactions", redacao_sem_imagens)
    r = anonimizar_pdf(arq, tmp_path / f"{variante}-anon.pdf")
    assert r.imagens_neutralizadas >= 1
    assert r.verificacao.imagens == 0 and r.verificacao.aprovada, r.resumo()
    _conferir_financeiro(r.destino)


def test_rede_de_seguranca_tambem_desliga_imagem_xobject(tmp_path, monkeypatch):
    def m(doc, pg):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 20), False)
        pg.insert_image(pymupdf.Rect(72, 700, 252, 760), pixmap=pix)
    arq = _pdf(tmp_path, "xobj", montar=m)
    original = pymupdf.Page.apply_redactions
    monkeypatch.setattr(pymupdf.Page, "apply_redactions",
                        lambda self, *a, **k: original(self, *a, **{**k, "images": pymupdf.PDF_REDACT_IMAGE_NONE}))
    r = anonimizar_pdf(arq, tmp_path / "xobj-anon.pdf")
    assert r.verificacao.imagens == 0 and r.verificacao.aprovada, r.resumo()


def test_imagem_so_nos_recursos_nao_desenhada(tmp_path):
    def m(doc, pg):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 30, 10), False)
        pg.insert_image(pymupdf.Rect(72, 700, 162, 730), pixmap=pix)
        cx = pg.get_contents()
        for x in cx:                                   # apaga o "Do": a imagem fica só nos recursos
            doc.update_stream(x, doc.xref_stream(x).replace(b" Do", b" %Do"))
    arq = _pdf(tmp_path, "recurso", montar=m)
    with pymupdf.open(arq) as o:
        inv = inventario_imagens(o)
    assert [i["origem"] for i in inv] == ["só referenciada nos recursos (não desenhada)"]
    r = anonimizar_pdf(arq, tmp_path / "recurso-anon.pdf")
    assert r.verificacao.imagens == 0 and r.verificacao.aprovada, r.resumo()


# --- leitor léxico: não confunde texto com operador ------------------------------------------------

def test_remocao_lexica_preserva_texto_que_contem_BI_e_EI():
    fluxo = (b"BT /F1 8 Tf 72 100 Td (BI ID EI e \\(BI\\) no texto) Tj ET\n% comentario BI\n"
             + _inline(bytes([1, 2, 3] * W * H)) + b"BT (fim) Tj ET")
    novo, n = remover_imagens_em_linha(fluxo)
    assert n == 1
    assert b"(BI ID EI e \\(BI\\) no texto) Tj" in novo and b"% comentario BI" in novo and b"(fim) Tj" in novo
    assert b" ID " not in novo.replace(b"(BI ID EI", b"")


# --- imagens grandes: possível gráfico/tabela -> conferência humana --------------------------------

def _grafico(doc, pg):
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 400, 300), False)
    pix.set_rect(pix.irect, (240, 240, 255))
    pg.insert_image(pymupdf.Rect(72, 150, 540, 500), pixmap=pix)          # ~35% da página


def test_imagem_grande_fica_retida_exportada_e_reprova(tmp_path):
    arq = _pdf(tmp_path, "grafico", montar=_grafico)
    revisao = tmp_path / "anonimizados" / "revisao-imagens"
    r = anonimizar_pdf(arq, tmp_path / "grafico-anon.pdf", pasta_revisao=revisao)
    assert len(r.imagens_retidas) == 1 and r.imagens_retidas[0]["pagina"] == 1
    assert (revisao / r.imagens_retidas[0]["arquivo_para_conferencia"]).exists()     # só no disco local
    assert r.verificacao.imagens == 1 and not r.verificacao.aprovada                  # zero resíduos exigido
    det = r.resumo()["verificacao"]["imagens_restantes_detalhe"][0]
    assert "conferência humana" in det["funcao_provavel"]
    with pymupdf.open(r.destino) as d:
        assert len(d[0].get_image_info()) == 1                                         # não removida sem decisão


def test_imagem_grande_removida_so_com_decisao_expressa(tmp_path):
    arq = _pdf(tmp_path, "grafico2", montar=_grafico)
    r = anonimizar_pdf(arq, tmp_path / "grafico2-anon.pdf", remover_imagens_grandes=True)
    assert r.imagens_retidas == [] and r.verificacao.imagens == 0 and r.verificacao.aprovada
    _conferir_financeiro(r.destino)


def test_retida_em_linha_nao_e_apagada_pela_rede_de_seguranca(tmp_path):
    grande = b"q 468 0 0 300 72 200 cm BI /W 4 /H 4 /CS /G /BPC 8 ID " + bytes(16) + b"\nEI Q\n"
    arq = _pdf(tmp_path, "grande-inline", conteudo_extra=grande)
    r = anonimizar_pdf(arq, tmp_path / "gi-anon.pdf")
    assert len(r.imagens_retidas) == 1 and not r.verificacao.aprovada
    with pymupdf.open(r.destino) as d:
        assert len(d[0].get_image_info()) == 1


# --- relatórios: só metadados ----------------------------------------------------------------------

def test_inventario_e_resumo_sem_conteudo(tmp_path):
    arq = _pdf(tmp_path, "meta", conteudo_extra=_inline(bytes([9, 9, 9] * W * H)), montar=_grafico)
    with pymupdf.open(arq) as o:
        inv = inventario_imagens(o)
    chaves = {"pagina", "origem", "pixels", "bits", "cores", "mascara_ou_1bit", "posicao_pt", "area_pct_pagina",
              "zona", "dentro_da_pagina", "funcao_provavel"}
    assert all(set(i) == chaves for i in inv)
    r = anonimizar_pdf(arq, tmp_path / "meta-anon.pdf", pasta_revisao=tmp_path / "rev")
    texto = json.dumps(r.resumo(), ensure_ascii=False)
    assert "digest" not in texto and "Perita do juízo" not in texto


def test_cabecalho_compacto_gravado_pelo_mupdf():
    """Formato real regravado pelo MuPDF: sem espaço antes de ID ('/F[/AHx/Fl]ID')."""
    dados = zlib.compress(bytes(W * H * 3)).hex().encode() + b">"
    fluxo = b"q 468 0 0 12 72 126 cm BI /W 468/H 12/BPC 8/CS/RGB/D[0 1 0 1 0 1]/F[/AHx/Fl]ID " + dados + b" EI Q q Q"
    novo, n = remover_imagens_em_linha(fluxo)
    assert n == 1 and novo == b"q 468 0 0 12 72 126 cm  Q q Q"
