#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Embute o MODELO MESTRE - AÇÃO REVISIONAL.docx dentro de gerador_peticao.html.

Precisa rodar sempre que o modelo for editado no Word — é o que faz a página
passar a gerar as petições com o texto novo. O arquivo .command já faz isso
sozinho toda vez que você abre o gerador.
"""
import base64, os, re, sys, zipfile, shutil

AQUI = os.path.dirname(os.path.abspath(__file__))
MODELO = os.path.join(AQUI, 'MODELO MESTRE - AÇÃO REVISIONAL.docx')
PAGINA = os.path.join(AQUI, 'gerador_peticao.html')


def regravar_sem_compressao(caminho):
    """O Word regrava o .docx compactado; a página lê o pacote sem descompactar,
    então o arquivo é normalizado para ZIP_STORED."""
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
    if not os.path.exists(MODELO):
        print('ERRO: não encontrei o modelo em', MODELO)
        return 1
    if not os.path.exists(PAGINA):
        print('ERRO: não encontrei a página em', PAGINA)
        return 1

    if regravar_sem_compressao(MODELO):
        print('  modelo normalizado (gravado sem compressão)')

    with open(MODELO, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('ascii')
    # quebra em linhas para o arquivo html não virar uma linha gigante
    b64 = '\n'.join(b64[i:i + 120] for i in range(0, len(b64), 120))

    html = open(PAGINA, encoding='utf-8').read()
    novo, n = re.subn(
        r'(<script id="modeloBase64" type="text/plain">)(.*?)(</script>)',
        lambda m: m.group(1) + '\n' + b64 + '\n' + m.group(3),
        html, count=1, flags=re.S)
    if not n:
        print('ERRO: não achei o espaço do modelo dentro do gerador_peticao.html')
        return 1
    open(PAGINA, 'w', encoding='utf-8').write(novo)
    print('  modelo embutido no gerador (%.0f KB)' % (len(b64) / 1024))
    return 0


if __name__ == '__main__':
    sys.exit(main())
