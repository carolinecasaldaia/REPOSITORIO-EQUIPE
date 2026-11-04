#!/bin/bash
# ---------------------------------------------------------------------------
# Painel da automação que baixa do Autentique os contratos já assinados por
# todas as partes e arquiva na pasta do cliente em PREPARAÇÃO PARA INGRESSO.
#
# A automação roda sozinha de hora em hora. Este atalho é o painel: ver o que
# foi baixado, buscar na hora, ligar/desligar o automático e guardar a chave.
#
# Instala tudo sozinho na primeira execução, num ambiente isolado em
# ~/.baixar-autentique/venv — não mexe no Python do sistema.
# ---------------------------------------------------------------------------

set -uo pipefail
cd "$(dirname "$0")" || exit 1

PROJETO="$(pwd)"
CASA="$HOME/.baixar-autentique"
VENV="$CASA/venv"
PY="$VENV/bin/python3"
ENVFILE="$CASA/.env"

titulo() { printf "\n\033[1m%s\033[0m\n" "$1"; printf '%.0s─' {1..64}; echo; }
aviso()  { printf "\033[33m%s\033[0m\n" "$1"; }
erro()   { printf "\033[31m%s\033[0m\n" "$1"; }
ok()     { printf "\033[32m%s\033[0m\n" "$1"; }

# ---------------------------------------------------------------------------
# Instalação (só na primeira vez)
# ---------------------------------------------------------------------------
instalar() {
    mkdir -p "$CASA" && chmod 700 "$CASA"

    if [ ! -x "$PY" ]; then
        titulo "Primeira execução — preparando o programa"
        echo "Isso acontece só uma vez e leva menos de um minuto."
        python3 -m venv "$VENV" || {
            erro "Não consegui preparar o ambiente Python."
            echo "Abra o Terminal e rode:  xcode-select --install"
            return 1
        }
        "$PY" -m pip install --quiet --upgrade pip
    fi

    if ! "$PY" -c "import pypdf" 2>/dev/null; then
        echo "Instalando a biblioteca de leitura de PDF..."
        "$PY" -m pip install --quiet pypdf || {
            erro "Não consegui baixar a biblioteca pypdf. Confira a internet."
            return 1
        }
    fi

    if [ ! -f "$ENVFILE" ] && [ -f "$PROJETO/.env.example" ]; then
        cp "$PROJETO/.env.example" "$ENVFILE"
        chmod 600 "$ENVFILE"
    fi

    # Atalho na Área de Trabalho.
    local area="$HOME/Desktop"
    [ -d "$HOME/Área de Trabalho" ] && area="$HOME/Área de Trabalho"
    if [ -d "$area" ] && [ ! -e "$area/Baixar Contratos Assinados" ]; then
        osascript -e "tell application \"Finder\" to make alias file to POSIX file \"$PROJETO/Baixar Contratos Assinados.command\" at POSIX file \"$area\"" >/dev/null 2>&1
        osascript -e "tell application \"Finder\" to set name of alias file \"Baixar Contratos Assinados.command\" of folder (POSIX file \"$area\" as alias) to \"Baixar Contratos Assinados\"" >/dev/null 2>&1
    fi
    return 0
}

tem_chave() {
    grep -q "^AUTENTIQUE_TOKEN=\"\{0,1\}[^\"]\+" "$ENVFILE" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
menu() {
    while true; do
        titulo "CONTRATOS ASSINADOS NO AUTENTIQUE"
        "$PY" executar.py status 2>/dev/null
        cat <<'MENU'

  1) Ver o que já foi baixado (abre o relatório)
  2) Buscar contratos assinados agora
  3) Só conferir, sem gravar nada
  4) Ligar o automático (de hora em hora, no horário comercial)
  5) Desligar o automático
  6) Baixar contratos assinados de antes (histórico)
  7) Guardar a chave da API do Autentique
  8) Testar a conexão com o Autentique
  9) Liberar o acesso ao Google Drive (para ela rodar sozinha)
  0) Sair
MENU
        read -r -p $'\nO que você quer fazer? ' escolha
        case "$escolha" in
            1) "$PY" executar.py pendencias ;;
            2) "$PY" executar.py rodar --abrir ;;
            3) "$PY" executar.py conferir ;;
            4) "$PY" executar.py agendador --instalar ;;
            5) "$PY" executar.py agendador --remover ;;
            6) read -r -p "Quantos dias para trás? [Enter = 30] " dias
               if [ -n "$dias" ]; then "$PY" executar.py historico --dias "$dias"
               else "$PY" executar.py historico; fi ;;
            7) "$PY" executar.py chave ;;
            8) "$PY" executar.py testar ;;
            9) "$PY" executar.py liberar ;;
            0|q|Q) echo "Até logo."; break ;;
            *) aviso "Opção não reconhecida." ;;
        esac
        echo; read -r -p "Enter para voltar ao menu..." _
    done
}

# ---------------------------------------------------------------------------

clear
if ! instalar; then
    erro "A instalação não terminou. Nada foi executado."
    read -r -p "Enter para fechar..." _
    exit 1
fi

if ! tem_chave; then
    titulo "Falta a chave da API do Autentique"
    echo "Sem ela a automação não consegue ver seus documentos."
    echo
    echo "  1. Entre no painel do Autentique (painel.autentique.com.br)"
    echo "  2. Configurações → Chaves de API → gerar uma chave"
    echo "  3. Copie a chave e cole na janela que vai abrir agora"
    echo
    read -r -p "Enter para colar a chave (ou digite p para pular): " resposta
    [ "$resposta" != "p" ] && "$PY" executar.py chave
    echo; read -r -p "Enter para continuar..." _
fi

menu
