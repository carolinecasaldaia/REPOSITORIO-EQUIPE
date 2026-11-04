#!/bin/bash
# Atalho clicável do Gerador de Onboarding.
# Na primeira execução prepara o ambiente Python (precisa de internet só nessa vez).

cd "$(dirname "$0")" || exit 1

AMBIENTE="$HOME/.gerador-onboarding/venv"
PY="$AMBIENTE/bin/python"

if [ ! -x "$PY" ]; then
  echo "Primeira execução: preparando o programa (leva menos de um minuto)..."
  echo
  /usr/bin/python3 -m venv "$AMBIENTE" || {
    echo "Não consegui preparar o ambiente Python."
    echo "Abra o Terminal e rode:  xcode-select --install"
    read -r -p "Pressione Enter para fechar."
    exit 1
  }
  "$AMBIENTE/bin/pip" install --quiet --upgrade pip
  "$AMBIENTE/bin/pip" install --quiet pypdf || {
    echo "Não consegui baixar a biblioteca pypdf. Confira a conexão com a internet."
    read -r -p "Pressione Enter para fechar."
    exit 1
  }
  echo "Pronto."
fi

# Atalho na Área de Trabalho (criado uma única vez).
ATALHO="Gerar Onboarding do Cliente"
if [ ! -e "$HOME/Desktop/$ATALHO" ] && [ ! -L "$HOME/Desktop/$ATALHO" ]; then
  osascript >/dev/null 2>&1 <<APPLESCRIPT
tell application "Finder"
  set novo to make alias file to POSIX file "$PWD/Gerar Onboarding.command" at POSIX file "$HOME/Desktop"
  set name of novo to "$ATALHO"
end tell
APPLESCRIPT
fi

"$PY" "./gerar_onboarding.py" --interativo

echo
read -r -p "Pressione Enter para fechar esta janela."
