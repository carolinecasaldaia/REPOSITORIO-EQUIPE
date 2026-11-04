#!/bin/bash
# Atalho clicável da Calculadora Revisional.
# Abre a página em http://127.0.0.1, que qualquer navegador consegue abrir.
# Não precisa de internet e não usa nenhum site: o contrato é lido nesta máquina
# e não sai daqui.

cd "$(dirname "$0")" || exit 1

echo "Calculadora Revisional — Caroline Macedo Advocacia"
echo

# Atalho na Área de Trabalho (criado uma única vez).
ATALHO="Calculadora Revisional"
if [ ! -e "$HOME/Desktop/$ATALHO" ] && [ ! -L "$HOME/Desktop/$ATALHO" ]; then
  osascript >/dev/null 2>&1 <<APPLESCRIPT
tell application "Finder"
  set novo to make alias file to POSIX file "$PWD/Calculadora Revisional.command" at POSIX file "$HOME/Desktop"
  set name of novo to "$ATALHO"
end tell
APPLESCRIPT
  echo "Criei o atalho \"$ATALHO\" na sua Área de Trabalho."
  echo
fi

/usr/bin/python3 "./_abrir_calculadora.py"
