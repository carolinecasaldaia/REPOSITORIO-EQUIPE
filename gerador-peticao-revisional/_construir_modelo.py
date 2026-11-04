#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Constrói o arquivo MODELO MESTRE - AÇÃO REVISIONAL.docx a partir de
_conteudo_modelo.py, reaproveitando o timbrado, as fontes e as margens
das petições reais do escritório.

Rode este script apenas se quiser reconstruir o modelo do zero.
Para o dia a dia, basta editar o .docx no Word.
"""
import os, re, shutil, zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
import sys
sys.path.insert(0, AQUI)
from _conteudo_modelo import BLOCOS, LINHAS_QUADRO

# Petição real usada como fonte do timbrado / estilos / tema
PETICAO_FONTE = os.path.join(
    os.path.dirname(os.path.dirname(AQUI)),
    'ELIEZER CICERO VASCONCELOS DA SILVA', 'PETIÇÕES',
    'Petição Inicial - Revisional - Capitalização Diária - Banco BV - ELIEZER CICERO VASCONCELOS DA SILVA.docx')

SAIDA = os.path.join(AQUI, 'MODELO MESTRE - AÇÃO REVISIONAL.docx')

NS = ('xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
      'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
      'xmlns:o="urn:schemas-microsoft-com:office:office" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
      'xmlns:v="urn:schemas-microsoft-com:vml" '
      'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:w10="urn:schemas-microsoft-com:office:word" '
      'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml" '
      'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
      'mc:Ignorable="w14 wp14"')


def esc(t):
    return (t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def par(texto, jc='both', bold=False, sz=24, ind=0, cor='000000',
        line=360, after=120, italic=False, borda=False, fundo=None, before=0):
    ppr = ['<w:pPr>']
    if borda:
        ppr.append('<w:pBdr>'
                   '<w:top w:val="single" w:sz="4" w:space="1" w:color="000000"/>'
                   '<w:left w:val="single" w:sz="4" w:space="4" w:color="000000"/>'
                   '<w:bottom w:val="single" w:sz="4" w:space="1" w:color="000000"/>'
                   '<w:right w:val="single" w:sz="4" w:space="4" w:color="000000"/>'
                   '</w:pBdr>')
    if fundo:
        ppr.append('<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % fundo)
    if ind:
        ppr.append('<w:ind w:left="%d"/>' % ind)
    ppr.append('<w:spacing w:before="%d" w:after="%d" w:line="%d" w:lineRule="auto"/>' % (before, after, line))
    ppr.append('<w:jc w:val="%s"/>' % jc)
    rpr = '<w:rPr>%s%s<w:color w:val="%s"/><w:sz w:val="%d"/><w:szCs w:val="%d"/></w:rPr>' % (
        '<w:b/>' if bold else '', '<w:i/>' if italic else '', cor, sz, sz)
    ppr.append(rpr)
    ppr.append('</w:pPr>')
    corpo = ''
    if texto:
        corpo = '<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % (rpr, esc(texto))
    return '<w:p>%s%s</w:p>' % (''.join(ppr), corpo)


def celula(texto, largura, fundo=None, bold=False, jc='left'):
    shd = '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % fundo if fundo else ''
    return ('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s'
            '<w:vAlign w:val="center"/></w:tcPr>%s</w:tc>'
            % (largura, shd, par(texto, jc=jc, bold=bold, sz=22, line=240, after=0)))


def tabela_contrato():
    """Quadro do contrato. Cada linha carrega o marcador {{?CAMPO}} para que o
    gerador possa eliminar as linhas não preenchidas."""
    L1, L2 = 4253, 1984
    out = ['<w:tbl><w:tblPr>'
           '<w:tblW w:w="6237" w:type="dxa"/><w:tblInd w:w="1271" w:type="dxa"/>'
           '<w:tblBorders>'
           '<w:top w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
           '<w:left w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
           '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
           '<w:right w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
           '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
           '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
           '</w:tblBorders><w:tblLayout w:type="fixed"/>'
           '</w:tblPr><w:tblGrid><w:gridCol w:w="%d"/><w:gridCol w:w="%d"/></w:tblGrid>' % (L1, L2)]
    out.append('<w:tr>%s%s</w:tr>' % (
        celula('Discriminação do Contrato de Financiamento nº {{CONTRATO_NUM}}', L1, fundo='D9D9D9', bold=True),
        celula('Valor de Referência', L2, fundo='D9D9D9', bold=True, jc='center')))
    for chave, rotulo, tipo in LINHAS_QUADRO:
        prefixo = 'R$ ' if tipo == 'moeda' else ''
        sufixo = '%' if tipo == 'perc' else ''
        out.append('<w:tr>%s%s</w:tr>' % (
            celula('{{?%s}}%s' % (chave, rotulo), L1),
            celula('%s{{%s}}%s' % (prefixo, chave, sufixo), L2, jc='center')))
    out.append('</w:tbl>')
    return ''.join(out)


def montar_corpo():
    saida = []
    for bloco in BLOCOS:
        tipo = bloco[0]
        texto = bloco[1] if len(bloco) > 1 else ''
        if tipo.startswith('+') or tipo.startswith('-'):
            # marcador de bloco condicional (visível em vermelho para a advogada)
            saida.append(par('[[%s]]' % tipo, jc='left', sz=16, cor='C00000', after=0, line=240))
        elif tipo == 'bar':
            saida.append(par(texto, jc='center', bold=True, sz=24,
                             borda=True, fundo='D9D9D9', before=240, after=240, line=240))
        elif tipo == 'h':
            saida.append(par(texto, jc='both', bold=True, before=240, after=120))
        elif tipo == 'p':
            saida.append(par(texto))
        elif tipo == 'pb':
            saida.append(par(texto, bold=True))
        elif tipo == 'c':
            saida.append(par(texto, jc='center', bold=True))
        elif tipo == 'q':
            saida.append(par(texto, jc='both', sz=20, ind=2268, line=240, after=120))
        elif tipo == 'qf':
            saida.append(par(texto, jc='both', sz=20, ind=2268, line=240, after=120))
        elif tipo == 'lista':
            saida.append(par(texto, jc='both', ind=709))
        elif tipo == 'img':
            saida.append(par(texto, jc='center', sz=20, cor='C00000', italic=True))
        elif tipo == 'vazio':
            saida.append(par('', after=0))
        elif tipo == 'tabela_contrato':
            saida.append(tabela_contrato())
        else:
            raise ValueError('bloco desconhecido: %r' % tipo)
    return ''.join(saida)


def main():
    z = zipfile.ZipFile(PETICAO_FONTE)
    doc_original = z.read('word/document.xml').decode('utf-8')
    sect = re.search(r'<w:sectPr[^>]*>.*?</w:sectPr>', doc_original, re.S).group(0)
    # limpa rsids do sectPr, mantendo referências de cabeçalho/rodapé
    sect = re.sub(r'\sw:rsid\w*="[^"]*"', '', sect)

    documento = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                 '<w:document %s><w:body>%s%s</w:body></w:document>'
                 % (NS, montar_corpo(), sect))

    rels_original = z.read('word/_rels/document.xml.rels').decode('utf-8')
    # mantém só as relações usadas pelo novo documento
    manter = ('styles', 'settings', 'webSettings', 'fontTable', 'theme',
              'header', 'footer', 'numbering', 'endnotes', 'footnotes')
    rels = []
    for m in re.finditer(r'<Relationship [^>]*/>', rels_original):
        tag = m.group(0)
        if any(k in tag for k in manter):
            rels.append(tag)
    rels_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + ''.join(rels) + '</Relationships>')

    copiar = ['[Content_Types].xml', '_rels/.rels', 'word/styles.xml', 'word/settings.xml',
              'word/webSettings.xml', 'word/fontTable.xml', 'word/theme/theme1.xml',
              'word/numbering.xml', 'word/footnotes.xml', 'word/endnotes.xml',
              'word/header1.xml', 'word/footer1.xml',
              'word/_rels/header1.xml.rels', 'word/_rels/footer1.xml.rels',
              'word/media/image5.png', 'word/media/image6.png',
              'docProps/core.xml', 'docProps/app.xml']

    if os.path.exists(SAIDA):
        shutil.copy2(SAIDA, SAIDA + '.bak')

    # ZIP_STORED: o gerador na página web lê o pacote sem precisar descompactar
    with zipfile.ZipFile(SAIDA, 'w', zipfile.ZIP_STORED) as out:
        for nome in copiar:
            if nome in z.namelist():
                out.writestr(nome, z.read(nome))
        out.writestr('word/document.xml', documento.encode('utf-8'))
        out.writestr('word/_rels/document.xml.rels', rels_xml.encode('utf-8'))
    z.close()
    print('OK ->', SAIDA, os.path.getsize(SAIDA), 'bytes')


if __name__ == '__main__':
    main()
