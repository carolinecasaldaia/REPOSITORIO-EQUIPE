#!/bin/bash
# ---------------------------------------------------------------------------
# Painel da automação de cadastro no Astrea.
#
# A automação roda sozinha em segundo plano. Este atalho é o painel de
# controle: ver pendências, rodar na hora, ligar/desligar o automático,
# importar clientes antigos e configurar o acesso ao Astrea.
#
# Instala tudo sozinho na primeira execução, num ambiente isolado em
# ~/.cadastro-astrea/venv — não mexe no Python do sistema.
# ---------------------------------------------------------------------------

set -uo pipefail
cd "$(dirname "$0")" || exit 1

PROJETO="$(pwd)"
CASA="$HOME/.cadastro-astrea"
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
        titulo "Primeira execução — preparando o ambiente"
        echo "Isso acontece só uma vez e leva alguns minutos."
        python3 -m venv "$VENV" || { erro "Não foi possível criar o ambiente."; return 1; }
        "$PY" -m pip install --quiet --upgrade pip
    fi

    if ! "$PY" -c "import pypdf" 2>/dev/null; then
        echo "Instalando a biblioteca de leitura de PDF..."
        "$PY" -m pip install --quiet pypdf || return 1
    fi

    if ! "$PY" -c "import playwright" 2>/dev/null; then
        echo "Instalando o navegador automatizado (Playwright)..."
        "$PY" -m pip install --quiet playwright || return 1
        echo "Baixando o Chromium (uma vez só, ~150 MB)..."
        "$PY" -m playwright install chromium || aviso "Falhou o download do Chromium — dá para instalar depois."
    fi

    if [ ! -f "$ENVFILE" ]; then
        cp "$PROJETO/.env.example" "$ENVFILE"
        chmod 600 "$ENVFILE"
        aviso "Criado $ENVFILE (em modo TESTE, sem credenciais)."
    fi

    # Atalho na Área de Trabalho.
    local area="$HOME/Desktop"
    [ -d "$HOME/Área de Trabalho" ] && area="$HOME/Área de Trabalho"
    if [ -d "$area" ] && [ ! -e "$area/Cadastro Astrea" ]; then
        osascript -e "tell application \"Finder\" to make alias file to POSIX file \"$PROJETO/Cadastrar Clientes.command\" at POSIX file \"$area\"" >/dev/null 2>&1
        osascript -e "tell application \"Finder\" to set name of alias file \"Cadastrar Clientes.command\" of folder (POSIX file \"$area\" as alias) to \"Cadastro Astrea\"" >/dev/null 2>&1
    fi
    return 0
}

# ---------------------------------------------------------------------------
# Configuração do acesso ao Astrea
# ---------------------------------------------------------------------------
gravar_env() {   # gravar_env CHAVE VALOR
    local chave="$1" valor="$2"
    touch "$ENVFILE"; chmod 600 "$ENVFILE"
    if grep -q "^${chave}=" "$ENVFILE" 2>/dev/null; then
        local tmp; tmp="$(mktemp)"
        grep -v "^${chave}=" "$ENVFILE" > "$tmp"
        printf '%s=%s\n' "$chave" "$valor" >> "$tmp"
        mv "$tmp" "$ENVFILE"
    else
        printf '%s=%s\n' "$chave" "$valor" >> "$ENVFILE"
    fi
    chmod 600 "$ENVFILE"
}

modo_producao() {
    titulo "Sair do modo teste"
    aviso "Em produção a automação passa a CADASTRAR de verdade no Astrea."
    echo "Só faça isso depois de conferir o resultado do modo teste."
    read -r -p 'Digite PRODUCAO para confirmar: ' resposta
    if [ "$resposta" = "PRODUCAO" ]; then
        gravar_env "TEST_MODE" "false"
        ok "Modo produção ligado."
    else
        echo "Cancelado — continua em modo teste."
    fi
}

modo_teste() {
    gravar_env "TEST_MODE" "true"
    ok "Modo teste ligado: nada será gravado no Astrea."
}

# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
menu() {
    while true; do
        titulo "CADASTRO AUTOMÁTICO NO ASTREA"
        "$PY" executar.py status 2>/dev/null | sed -n '1,9p'
        cat <<'MENU'

  1) Ver pendências (abre o relatório)
  2) Verificar a pasta agora
  3) Só analisar, sem tocar no Astrea
  4) Ligar a verificação automática
  5) Desligar a verificação automática
  6) Importar clientes antigos (com confirmação)
  7) Entrar no Astrea (uma vez, sem guardar senha)  ← recomendado
  8) Ligar modo TESTE  /  9) Ligar modo PRODUÇÃO
  c) Calibrar a tela do Astrea
  s) Guardar e-mail e senha do Astrea (para ela entrar sozinha)
  p) Abrir casos de quem pagou a entrada agora  <- confere sozinho no Asaas
  k) Quem já pode receber a marca "01 - OK -" na pasta
  d) Ver dashboard financeiro (atualiza e abre na hora)
  0) Sair
MENU
        read -r -p $'\nO que você quer fazer? ' escolha
        case "$escolha" in
            1) "$PY" executar.py pendencias ;;
            2) "$PY" executar.py rodar ;;
            3) titulo "Análise (nada é gravado)"
               read -r -p "Nome (ou parte) da pasta, ou Enter para todas: " alvo
               if [ -n "$alvo" ]; then "$PY" executar.py analisar "$alvo"
               else "$PY" executar.py analisar; fi ;;
            4) "$PY" executar.py agendador --instalar ;;
            5) "$PY" executar.py agendador --remover ;;
            6) "$PY" executar.py importar ;;
            7) "$PY" executar.py entrar ;;
            8) modo_teste ;;
            9) modo_producao ;;
            c|C) "$PY" executar.py calibrar ;;
            s|S) "$PY" executar.py senha ;;
            p|P) "$PY" executar.py casos ;;
            k|K) "$PY" executar.py prontos ;;
            d|D) "$PY" executar.py dashboard ;;
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
menu
