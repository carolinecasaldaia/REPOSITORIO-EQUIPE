#!/bin/bash
# Atalho clicável do Gerador de Contratos.
# Reembute os modelos mestres (para valer o que você editou no Word) e abre a
# página em http://127.0.0.1, que qualquer navegador consegue abrir.
# Não precisa de internet e não usa nenhum site: tudo roda nesta máquina.

cd "$(dirname "$0")" || exit 1

echo "Gerador de Contratos — Caroline Macedo Advocacia"
echo

# Atalho na Área de Trabalho (criado uma única vez).
ATALHO="Gerar Contratos"
if [ ! -e "$HOME/Desktop/$ATALHO" ] && [ ! -L "$HOME/Desktop/$ATALHO" ]; then
  osascript >/dev/null 2>&1 <<APPLESCRIPT
tell application "Finder"
  set novo to make alias file to POSIX file "$PWD/Gerar Contratos.command" at POSIX file "$HOME/Desktop"
  set name of novo to "$ATALHO"
end tell
APPLESCRIPT
  echo "Criei o atalho \"$ATALHO\" na sua Área de Trabalho."
  echo
fi

echo "Atualizando os modelos na página..."
/usr/bin/python3 "./_embutir_modelos.py" || {
  echo
  echo "Não consegui atualizar os modelos. A página vai abrir com a versão anterior."
}

echo
/usr/bin/python3 "./_abrir_gerador.py"
