#!/usr/bin/env python3
"""Monta a página final: corpo + libs inlined. Também gera a versão de teste local."""
import re, time, pathlib

SP = pathlib.Path(__file__).parent
body = (SP / 'app-body.html').read_text()
pdfx = (SP / 'pdfextract.js').read_text()
parse = (SP / 'parsecontrato.js').read_text()
app = (SP / 'app.js').read_text()

# a página publicada é envolvida por <head>/<body> — nada de doctype/html/head/body aqui
final = body + "\n<script>\n" + pdfx + "\n" + parse + "\n" + app + "\n</script>\n"
(SP / 'calculadora.html').write_text(final)

# versão local para teste (precisa do esqueleto)
v = str(time.time_ns() % 1000000)
local = ("<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">"
         "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"></head><body>\n"
         + final + "\n</body></html>")
(SP / 'local.html').write_text(local)
print('calculadora.html', len(final), 'bytes ·', final.count('\n'), 'linhas')
