#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Abre a calculadora em http://127.0.0.1 em vez de abrir o arquivo direto.

Por que: a pasta do escritório fica em
  .../GoogleDrive-contato@carolinemacedoadv.com/Meu Drive/Documentos Escritório /...
e esse caminho tem um "@" e um ESPAÇO NO FIM de "Documentos Escritório". Ao
transformar isso num endereço "file://", o trecho vira ".../Documentos%20Escritório%20/",
e vários navegadores (Firefox e Safari entre eles) cortam esse espaço final ou
tratam o "@" como usuário/senha — e aí não acham o arquivo. Servindo em
127.0.0.1 o caminho deixa de importar e qualquer navegador abre.

Continua tudo na máquina: o servidor só aceita conexão local (127.0.0.1) e
serve um único arquivo, a página da calculadora. Nada vai para a internet.

Bônus: em http:// o navegador também guarda o rascunho do formulário e baixa os
.docx sem as restrições que o Safari impõe a páginas abertas como arquivo.
"""
import functools
import http.server
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading

AQUI = os.path.dirname(os.path.abspath(__file__))
PAGINA = os.path.join(AQUI, 'calculadora_revisional.html')
NOME = 'calculadora_revisional.html'
PASTA_SERVIDA = os.path.join(tempfile.gettempdir(), 'calculadora-revisional-cm')
PORTA_PREFERIDA = 8795


class Silencioso(http.server.SimpleHTTPRequestHandler):
    """Igual ao servidor padrão, mas sem poluir a janela com log de acesso."""

    def log_message(self, *args):
        pass


class Servidor(socketserver.TCPServer):
    allow_reuse_address = True


def abrir_servidor():
    manipulador = functools.partial(Silencioso, directory=PASTA_SERVIDA)
    for porta in (PORTA_PREFERIDA, 0):
        try:
            return Servidor(('127.0.0.1', porta), manipulador)
        except OSError:
            continue
    return None


def main():
    if not os.path.exists(PAGINA):
        print('ERRO: não encontrei a página em', PAGINA)
        return 1

    os.makedirs(PASTA_SERVIDA, exist_ok=True)
    shutil.copy2(PAGINA, os.path.join(PASTA_SERVIDA, NOME))

    servidor = abrir_servidor()
    if servidor is None:
        print('ERRO: não consegui abrir o servidor local.')
        return 1

    porta = servidor.server_address[1]
    url = 'http://127.0.0.1:%d/%s' % (porta, NOME)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    print('Endereço da calculadora:')
    print()
    print('    %s' % url)
    print()
    print('Se o navegador não abrir sozinho, copie o endereço acima e cole na')
    print('barra de endereços — funciona no Chrome, no Safari e no Firefox.')
    print()
    subprocess.run(['open', url], check=False)

    try:
        input('Deixe esta janela aberta enquanto usa a calculadora.\n'
              'Quando terminar, pressione Enter para fechar. ')
    except (EOFError, KeyboardInterrupt):
        pass
    servidor.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
