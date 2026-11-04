#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Constrói os quatro MODELOS MESTRES .docx a partir de _conteudo_modelos.py,
reaproveitando o timbrado, as fontes, os estilos e as margens dos contratos
reais do escritório.

Rode este script apenas se quiser reconstruir os modelos do zero.
Para o dia a dia, basta editar o .docx no Word — o "Gerar Contratos.command"
já reembute o modelo editado na página toda vez que abre.
"""
import os
import re
import shutil
import sys
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from _conteudo_modelos import (BLOCOS_CONTRATO, BLOCOS_PROCURACAO,
                               BLOCOS_HIPOSSUFICIENCIA, BLOCOS_RESIDENCIA)

# Contrato real usado como fonte do timbrado / estilos / margens.
# Os quatro documentos do onboarding compartilham o mesmo cabeçalho e rodapé.
FONTE = os.path.join(
    os.path.dirname(AQUI), 'PREPARAÇÃO PARA INGRESSO', 'JUNHO 2026',
    '17 - OK - CARLOS DANIEL DA SILVA',
    'CONTRATO DE PRESTAÇÃO DE SERVIÇOS COMPLETO - ATUALIZADO 06:2026.docx')

SAIDAS = [
    ('MODELO MESTRE - CONTRATO.docx', BLOCOS_CONTRATO),
    ('MODELO MESTRE - PROCURACAO.docx', BLOCOS_PROCURACAO),
    ('MODELO MESTRE - DECLARACAO DE HIPOSSUFICIENCIA.docx', BLOCOS_HIPOSSUFICIENCIA),
    ('MODELO MESTRE - DECLARACAO DE RESIDENCIA.docx', BLOCOS_RESIDENCIA),
]

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

# ------------------------------------------------------------------ formatos
# (propriedades de parágrafo, propriedades de texto)  — copiadas dos
# documentos reais do escritório, cláusula por cláusula.

GARAMOND = ('<w:rFonts w:ascii="Garamond" w:hAnsi="Garamond" w:cs="Arial"/>'
            '<w:spacing w:val="2"/><w:sz w:val="22"/><w:szCs w:val="22"/>')
WEB = ('<w:pStyle w:val="NormalWeb"/><w:shd w:val="clear" w:color="auto" w:fill="FFFFFF"/>'
       '<w:spacing w:before="0" w:beforeAutospacing="0" w:after="0" '
       'w:afterAutospacing="0" w:line="360" w:lineRule="auto"/>')

FORMATOS = {
    # ---- contrato
    'titulo':      ('<w:jc w:val="center"/>', '<w:b/><w:sz w:val="28"/><w:szCs w:val="28"/>'),
    'vazio':       ('<w:jc w:val="both"/>', ''),
    'cab':         ('<w:spacing w:line="360" w:lineRule="auto"/>'
                    '<w:ind w:left="142" w:firstLine="1701"/><w:jc w:val="both"/>',
                    '<w:rFonts w:cs="Tahoma"/><w:bCs/>'),
    'p':           ('<w:spacing w:line="360" w:lineRule="auto"/><w:jc w:val="both"/>', ''),
    'lista':       ('<w:spacing w:line="360" w:lineRule="auto"/><w:jc w:val="both"/>', ''),
    'centro':      ('<w:jc w:val="center"/>', ''),
    'assin':       ('<w:jc w:val="center"/>', ''),
    # ---- procuração
    'pr_titulo':   ('<w:spacing w:before="101"/><w:ind w:left="1527" w:right="1540"/>'
                    '<w:jc w:val="center"/>', '<w:b/><w:sz w:val="28"/><w:szCs w:val="28"/>'),
    'pr_sub':      ('<w:pStyle w:val="Ttulo11"/><w:spacing w:before="148"/>', ''),
    'pr_corpo':    ('<w:pStyle w:val="Corpodetexto"/>'
                    '<w:spacing w:before="200" w:line="360" w:lineRule="auto"/>'
                    '<w:ind w:left="142" w:right="116" w:firstLine="1701"/>'
                    '<w:jc w:val="both"/>', '<w:rFonts w:cs="Tahoma"/><w:bCs/>'),
    'pr_centro':   ('<w:spacing w:before="191"/><w:ind w:left="1527" w:right="1545"/>'
                    '<w:jc w:val="center"/>', ''),
    'pr_centro_b': ('<w:spacing w:before="101"/><w:ind w:left="1527" w:right="1540"/>'
                    '<w:jc w:val="center"/>', '<w:b/>'),
    'pr_vazio':    ('<w:pStyle w:val="Corpodetexto"/>', ''),
    # ---- declarações
    'dc_titulo':   ('<w:pStyle w:val="Corpodetexto"/><w:spacing w:before="1"/>'
                    '<w:jc w:val="center"/>',
                    '<w:rFonts w:ascii="Garamond" w:hAnsi="Garamond"/><w:b/><w:bCs/>'
                    '<w:sz w:val="28"/><w:szCs w:val="28"/>'),
    'dc_corpo':    (WEB + '<w:ind w:firstLine="1418"/><w:jc w:val="both"/>', GARAMOND),
    'dc_cita':     (WEB + '<w:ind w:left="2268"/><w:jc w:val="both"/>',
                    '<w:rFonts w:ascii="Garamond" w:hAnsi="Garamond" w:cs="Arial"/>'
                    '<w:spacing w:val="2"/><w:sz w:val="20"/><w:szCs w:val="20"/>'),
    'dc_vazio':    (WEB + '<w:jc w:val="both"/>', GARAMOND),
    'dc_centro':   ('<w:pStyle w:val="NormalWeb"/>'
                    '<w:shd w:val="clear" w:color="auto" w:fill="FFFFFF"/>'
                    '<w:spacing w:before="0" w:beforeAutospacing="0" w:after="480" '
                    'w:afterAutospacing="0" w:line="360" w:lineRule="auto"/>'
                    '<w:jc w:val="center"/>', GARAMOND),
    'dc_assin':    ('<w:pStyle w:val="NormalWeb"/>'
                    '<w:shd w:val="clear" w:color="auto" w:fill="FFFFFF"/>'
                    '<w:spacing w:before="0" w:beforeAutospacing="0" w:after="480" '
                    'w:afterAutospacing="0" w:line="276" w:lineRule="auto"/>'
                    '<w:jc w:val="center"/>',
                    '<w:rFonts w:ascii="Garamond" w:hAnsi="Garamond"/><w:b/><w:bCs/>'
                    '<w:sz w:val="22"/><w:szCs w:val="22"/>'),
}

MARCADOR = re.compile(r'\{\{[+-][A-Z_0-9]+\}\}')
CAMPO = re.compile(r'\{\{[A-Z_0-9#]+\}\}')


def esc(t):
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def runs(texto, base):
    """Transforma o texto marcado em <w:r>. Cada {{+TAG}} / {{-TAG}} sai em um
    run próprio, sozinho, para que o gerador possa recortar o trecho inteiro
    sem quebrar o XML."""
    saida = []
    negrito = False
    sublinha = False
    buffer = []
    quebra = [False]  # a próxima escrita começa com <w:br/>

    def rpr():
        extra = ''
        if negrito or sublinha:
            extra += '<w:b/>'
        if sublinha:
            extra += '<w:u w:val="single"/>'
        return '<w:rPr>%s%s</w:rPr>' % (base, extra) if (base or extra) else ''

    def descarrega():
        if not buffer and not quebra[0]:
            return
        br = '<w:br/>' if quebra[0] else ''
        quebra[0] = False
        texto_run = ''.join(buffer)
        del buffer[:]
        if not texto_run and not br:
            return
        corpo = ('<w:t xml:space="preserve">%s</w:t>' % esc(texto_run)) if texto_run else ''
        saida.append('<w:r>%s%s%s</w:r>' % (rpr(), br, corpo))

    i = 0
    while i < len(texto):
        m = MARCADOR.match(texto, i)
        if m:
            descarrega()
            saida.append('<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>'
                         % (rpr(), m.group(0)))
            i = m.end()
            continue
        m = CAMPO.match(texto, i)
        if m:
            # nome de campo entra literal: o "_" dele não é marcação
            buffer.append(m.group(0))
            i = m.end()
            continue
        c = texto[i]
        if c == '*':
            descarrega()
            negrito = not negrito
        elif c == '_':
            descarrega()
            sublinha = not sublinha
        elif c == '¶':
            descarrega()
            quebra[0] = True
        else:
            buffer.append(c)
        i += 1
    descarrega()
    return ''.join(saida)


def paragrafo(tipo, texto=''):
    ppr, base = FORMATOS[tipo]
    rpr = '<w:rPr>%s</w:rPr>' % base if base else ''
    return '<w:p><w:pPr>%s%s</w:pPr>%s</w:p>' % (ppr, rpr, runs(texto, base) if texto else '')


def marcador_condicional(tag, tipo_vazio):
    """Parágrafo vermelho e pequeno que delimita um bloco opcional. Fica
    visível no Word para a advogada saber onde o bloco começa e termina."""
    ppr = FORMATOS[tipo_vazio][0]
    rpr = ('<w:rPr><w:color w:val="C00000"/><w:sz w:val="16"/>'
           '<w:szCs w:val="16"/></w:rPr>')
    return ('<w:p><w:pPr>%s%s</w:pPr><w:r>%s<w:t xml:space="preserve">[[%s]]</w:t>'
            '</w:r></w:p>' % (ppr, rpr, rpr, tag))


def montar(blocos):
    vazio = 'vazio' if blocos is BLOCOS_CONTRATO else (
        'pr_vazio' if blocos is BLOCOS_PROCURACAO else 'dc_vazio')
    out = []
    for bloco in blocos:
        tipo = bloco[0]
        texto = bloco[1] if len(bloco) > 1 else ''
        if tipo == 'cond':
            out.append(marcador_condicional(texto, vazio))
        else:
            out.append(paragrafo(tipo, texto))
    return ''.join(out)


def main():
    if not os.path.exists(FONTE):
        print('ERRO: não encontrei o contrato-fonte em', FONTE)
        return 1
    z = zipfile.ZipFile(FONTE)
    original = z.read('word/document.xml').decode('utf-8')
    sect = re.search(r'<w:sectPr[^>]*>.*?</w:sectPr>', original, re.S).group(0)
    sect = re.sub(r'\sw:rsid\w*="[^"]*"', '', sect)

    # relações do documento, menos os hyperlinks dos e-mails do cliente antigo
    rels_orig = z.read('word/_rels/document.xml.rels').decode('utf-8')
    rels = [m.group(0) for m in re.finditer(r'<Relationship [^>]*/>', rels_orig)
            if 'TargetMode="External"' not in m.group(0)]
    rels_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                'relationships">' + ''.join(rels) + '</Relationships>')

    copiar = [n for n in z.namelist()
              if n not in ('word/document.xml', 'word/_rels/document.xml.rels')]

    for nome, blocos in SAIDAS:
        caminho = os.path.join(AQUI, nome)
        documento = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                     '<w:document %s><w:body>%s%s</w:body></w:document>'
                     % (NS, montar(blocos), sect))
        if os.path.exists(caminho):
            shutil.copy2(caminho, caminho + '.bak')
        # ZIP_STORED: a página web lê o pacote sem precisar descompactar
        with zipfile.ZipFile(caminho, 'w', zipfile.ZIP_STORED) as out:
            for item in copiar:
                out.writestr(item, z.read(item))
            out.writestr('word/document.xml', documento.encode('utf-8'))
            out.writestr('word/_rels/document.xml.rels', rels_xml.encode('utf-8'))
        print('OK -> %s (%d bytes)' % (nome, os.path.getsize(caminho)))
    z.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
