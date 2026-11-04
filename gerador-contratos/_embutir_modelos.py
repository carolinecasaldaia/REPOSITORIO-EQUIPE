#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Embute os quatro MODELOS MESTRES .docx dentro de gerador_contratos.html.

Roda automaticamente toda vez que o "Gerar Contratos.command" é aberto — é o
que faz a página passar a usar o texto novo depois de você editar um modelo
no Word.
"""
import base64
import os
import re
import shutil
import sys
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
PAGINA = os.path.join(AQUI, 'gerador_contratos.html')

MODELOS = [
    ('modeloContrato',   'MODELO MESTRE - CONTRATO.docx'),
    ('modeloProcuracao', 'MODELO MESTRE - PROCURACAO.docx'),
    ('modeloHipo',       'MODELO MESTRE - DECLARACAO DE HIPOSSUFICIENCIA.docx'),
    ('modeloResidencia', 'MODELO MESTRE - DECLARACAO DE RESIDENCIA.docx'),
]


def regravar_sem_compressao(caminho):
    """O Word regrava o .docx compactado; a página lê o pacote sem
    descompactar, então o arquivo é normalizado para ZIP_STORED."""
    z = zipfile.ZipFile(caminho)
    precisa = any(i.compress_type != zipfile.ZIP_STORED for i in z.infolist())
    if not precisa:
        z.close()
        return False
    itens = [(i.filename, z.read(i.filename)) for i in z.infolist()]
    z.close()
    tmp = caminho + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_STORED) as out:
        for nome, dados in itens:
            out.writestr(nome, dados)
    shutil.move(tmp, caminho)
    return True


def main():
    if not os.path.exists(PAGINA):
        print('ERRO: não encontrei a página em', PAGINA)
        return 1

    html = open(PAGINA, encoding='utf-8').read()
    total = 0

    for identificador, arquivo in MODELOS:
        caminho = os.path.join(AQUI, arquivo)
        if not os.path.exists(caminho):
            print('ERRO: não encontrei o modelo', arquivo)
            return 1
        if regravar_sem_compressao(caminho):
            print('  %s normalizado (gravado sem compressão)' % arquivo)

        with open(caminho, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        b64 = '\n'.join(b64[i:i + 120] for i in range(0, len(b64), 120))

        padrao = (r'(<script id="%s" type="text/plain">)(.*?)(</script>)'
                  % re.escape(identificador))
        html, n = re.subn(padrao,
                          lambda m: m.group(1) + '\n' + b64 + '\n' + m.group(3),
                          html, count=1, flags=re.S)
        if not n:
            print('ERRO: não achei o espaço do modelo "%s" na página.' % identificador)
            return 1
        total += len(b64)

    open(PAGINA, 'w', encoding='utf-8').write(html)
    print('  4 modelos embutidos no gerador (%.0f KB)' % (total / 1024))
    return 0


if __name__ == '__main__':
    sys.exit(main())
