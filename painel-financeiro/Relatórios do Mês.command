#!/bin/bash
# Atalho clicável dos Relatórios Mensais aos Clientes.
# Na primeira execução prepara o ambiente Python (precisa de internet só nessa vez).

cd "$(dirname "$0")" || exit 1

AMBIENTE="$HOME/.relatorios-clientes/venv"
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
  "$AMBIENTE/bin/pip" install --quiet reportlab openpyxl || {
    echo "Não consegui baixar as bibliotecas. Confira a conexão com a internet."
    read -r -p "Pressione Enter para fechar."
    exit 1
  }
  echo "Pronto."
fi

# Atalho na Área de Trabalho (criado uma única vez).
ATALHO="Relatórios do Mês"
if [ ! -e "$HOME/Desktop/$ATALHO" ] && [ ! -L "$HOME/Desktop/$ATALHO" ]; then
  osascript >/dev/null 2>&1 <<APPLESCRIPT
tell application "Finder"
  set novo to make alias file to POSIX file "$PWD/Relatórios do Mês.command" at POSIX file "$HOME/Desktop"
  set name of novo to "$ATALHO"
end tell
APPLESCRIPT
fi

"$PY" "./gerar_relatorios.py" --interativo

echo
read -r -p "Pressione Enter para fechar esta janela."
