#!/bin/bash
# Atalho clicável do Separador de Documentos do Autentique.
# Na primeira execução prepara o ambiente Python (precisa de internet só nessa vez).

cd "$(dirname "$0")" || exit 1

AMBIENTE="$HOME/.separador-autentique/venv"
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

"$PY" "./separar_autentique.py" --interativo

echo
read -r -p "Pressione Enter para fechar esta janela."
