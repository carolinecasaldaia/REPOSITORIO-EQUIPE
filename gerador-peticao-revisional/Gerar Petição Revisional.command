#!/bin/bash
# Abre o gerador de petição inicial da ação revisional.
# Antes de abrir, atualiza a página com a versão atual do modelo mestre,
# para que qualquer alteração feita no Word já valha na próxima petição.

PASTA="$(cd "$(dirname "$0")" && pwd)"
cd "$PASTA" || exit 1

clear
echo ""
echo "  ╭──────────────────────────────────────────────────────────╮"
echo "  │   GERADOR DE PETIÇÃO INICIAL — AÇÃO REVISIONAL           │"
echo "  │   Caroline Macedo Advocacia                              │"
echo "  ╰──────────────────────────────────────────────────────────╯"
echo ""

if [ ! -f "MODELO MESTRE - AÇÃO REVISIONAL.docx" ]; then
  echo "  ✗ Não encontrei o arquivo:"
  echo "    MODELO MESTRE - AÇÃO REVISIONAL.docx"
  echo ""
  echo "  Ele precisa estar nesta mesma pasta:"
  echo "  $PASTA"
  echo ""
  read -n 1 -s -r -p "  Pressione qualquer tecla para fechar."
  exit 1
fi

echo "  Conferindo o modelo do escritório..."
python3 _embutir_modelo.py || {
  echo ""
  echo "  ✗ Não consegui preparar o modelo. Chame o suporte."
  read -n 1 -s -r -p "  Pressione qualquer tecla para fechar."
  exit 1
}

# atalho na Área de Trabalho, criado uma única vez
ATALHO="$HOME/Desktop/Gerar Petição Revisional"
if [ ! -e "$ATALHO" ]; then
  osascript >/dev/null 2>&1 <<EOF
tell application "Finder"
  make new alias file at (path to desktop folder) to (POSIX file "$PASTA/Gerar Petição Revisional.command")
  set name of result to "Gerar Petição Revisional"
end tell
EOF
  echo "  ✓ Criei o atalho \"Gerar Petição Revisional\" na sua Área de Trabalho."
fi

echo "  Abrindo o gerador no navegador..."
open "$PASTA/gerador_peticao.html"

echo ""
echo "  ─────────────────────────────────────────────────────────────"
echo "  Pronto. O formulário está aberto no navegador."
echo ""
echo "  1. Preencha os dados do cliente e do contrato"
echo "  2. Marque as teses que se aplicam ao caso"
echo "  3. Clique em GERAR PETIÇÃO — o .docx vai para a pasta Downloads"
echo "  4. Abra no Word, cole os prints das cláusulas nos pontos"
echo "     marcados em vermelho e revise antes de protocolar"
echo ""
echo "  Pode fechar esta janela preta."
echo "  ─────────────────────────────────────────────────────────────"
echo ""
sleep 2
