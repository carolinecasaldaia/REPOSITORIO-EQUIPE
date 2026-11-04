#!/bin/bash
# ---------------------------------------------------------------------------
# Painel do RADAR B&A — Caroline Macedo Advocacia.
#
# Monitora a carteira de clientes e avisa quando aparece uma nova
# Busca e Apreensão ou Execução contra alguém do escritório.
#
# Instala tudo sozinho na primeira execução, num ambiente isolado em
# ~/.radar-ba/venv — não mexe no Python do sistema.
# ---------------------------------------------------------------------------

set -uo pipefail
cd "$(dirname "$0")" || exit 1

PROJETO="$(pwd)"
CASA="$HOME/.radar-ba"
VENV="$CASA/venv"
PY="$VENV/bin/python3"
ENVFILE="$CASA/.env"

titulo() { printf "\n\033[1m%s\033[0m\n" "$1"; printf '%.0s─' {1..66}; echo; }
aviso()  { printf "\033[33m%s\033[0m\n" "$1"; }
erro()   { printf "\033[31m%s\033[0m\n" "$1"; }
ok()     { printf "\033[32m%s\033[0m\n" "$1"; }

preparar() {
  mkdir -p "$CASA/dados"
  if [ ! -x "$PY" ]; then
    titulo "Primeira execução — preparando o ambiente"
    echo "Isso acontece só uma vez e leva cerca de um minuto."
    python3 -m venv "$VENV" || { erro "não foi possível criar o ambiente"; return 1; }
    "$VENV/bin/pip" install -q --upgrade pip
    "$VENV/bin/pip" install -q -r "$PROJETO/requirements.txt" || {
      erro "falha ao instalar as dependências"; return 1; }
    ok "Ambiente pronto."
  fi
  if [ ! -f "$ENVFILE" ]; then
    titulo "Configuração inicial"
    cp "$PROJETO/.env.exemplo" "$ENVFILE"
    chmod 600 "$ENVFILE"
    # gera os segredos locais
    "$PY" - <<'PYGEN' >> "$ENVFILE"
import base64, os
print("")
print("CPF_PEPPER=" + base64.b64encode(os.urandom(24)).decode())
print("CPF_CHAVE=" + base64.b64encode(os.urandom(32)).decode())
PYGEN
    aviso "Criei $ENVFILE com chaves novas."
    aviso "Falta colar a chave pública do DataJud em DATAJUD_API_KEY."
    aviso "Ela é divulgada pelo CNJ em datajud-wiki.cnj.jus.br/api-publica/acesso"
    echo
    read -r -p "Abrir o arquivo de configuração agora? [S/n] " abrir
    [[ "${abrir:-S}" =~ ^[Ss]?$ ]] && open -t "$ENVFILE"
  fi
}

menu() {
  titulo "RADAR B&A — Caroline Macedo Advocacia"
  cat <<'MENU'
  1) Rodar o monitoramento agora (último dia)
  2) Rodar buscando os últimos 7 dias
  3) Ver a carteira monitorada
  4) Importar carteira de clientes (CSV ou XLSX)
  5) Verificar se as fontes estão no ar
  6) Abrir a pasta de relatórios
  7) Abrir a configuração
  8) Rodar os testes
  0) Sair
MENU
  echo
  read -r -p "Escolha: " opcao
  case "$opcao" in
    1) "$PY" executar.py monitorar --dias 1 ;;
    2) "$PY" executar.py monitorar --dias 7 ;;
    3) "$PY" executar.py clientes ;;
    4) echo; read -r -p "Arraste o arquivo para cá e tecle Enter: " arq
       arq="${arq%\"}"; arq="${arq#\"}"; arq="$(echo "$arq" | xargs)"
       [ -f "$arq" ] && "$PY" executar.py importar "$arq" || erro "arquivo não encontrado" ;;
    5) "$PY" executar.py saude ;;
    6) open "$PROJETO/RELATÓRIOS" ;;
    7) open -t "$ENVFILE" ;;
    8) "$PY" -m pytest tests/ -q ;;
    0) exit 0 ;;
    *) aviso "Opção inválida." ;;
  esac
  echo; read -r -p "Tecle Enter para voltar ao menu..." _
  menu
}

preparar || { echo; read -r -p "Tecle Enter para fechar..." _; exit 1; }
menu
