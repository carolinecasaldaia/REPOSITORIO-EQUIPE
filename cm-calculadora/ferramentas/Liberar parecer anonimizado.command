#!/bin/zsh
# CM | Calculadora Judicial Bancária — LIBERAÇÃO do parecer anonimizado para a validação.
# Use somente DEPOIS de conferir a cópia anonimizada.
# - Mostra apenas cópias com verificação APROVADA (nomes genéricos).
# - Pede o seu nome e a confirmação expressa: é preciso DIGITAR "AUTORIZO".
#   Enter, Esc ou "Cancelar" em qualquer janela encerram SEM liberar.
# - A liberação é registrada (nome, data/hora, arquivo e impressão digital SHA-256);
#   qualquer alteração posterior do arquivo invalida a liberação automaticamente.
# - Diário das etapas (sem conteúdo de documentos): ~/Library/Logs/CM-Calculadora/liberacao.log

ID="${CM_VALIDACAO_ID:-VAL-001}"
PROJETO="$HOME/cm-calculadora"
DIARIO="$HOME/Library/Logs/CM-Calculadora/liberacao.log"
mkdir -p "${DIARIO:h}"

cm() { /opt/homebrew/bin/uv run --quiet --project "$PROJETO" cm-calc validacao "$@"; }
diario() { print -r -- "$(date '+%Y-%m-%d %H:%M:%S')  $ID  $*" >> "$DIARIO"; }
janela() {   # janela na frente de todas; devolve o texto/botão; código != 0 se cancelada
  osascript -e 'activate' -e "$1" 2>>"$DIARIO"
}
avisar() {
  janela "display dialog \"$1\" with title \"CM | Liberação\" buttons {\"OK\"} default button \"OK\" with icon $2" >/dev/null
}
encerrar() { diario "ENCERRADO SEM LIBERAR: $1"; echo; echo "Encerrado sem liberar: $1"; exit ${2:-0}; }

echo "CM | Liberação do parecer anonimizado — validação $ID"
echo
diario "início"

LISTA=$(cm listar-anonimizados "$ID" 2>>"$DIARIO" | awk -F'\t' '$2 == "APROVADA" {print $1}')
if [ -z "$LISTA" ]; then
  avisar "Não há cópia anonimizada APROVADA para liberar no caso $ID.\n\nRode antes o atalho 'CM - 1 Anonimizar parecer'." stop
  encerrar "nenhuma cópia aprovada" 1
fi
diario "cópias aprovadas: $(echo $LISTA | tr '\n' ' ')"

# 1) escolha da cópia
ITENS=$(echo "$LISTA" | awk '{printf "%s\"%s\"", (NR>1?", ":""), $0}')
ARQ=$(janela "choose from list {$ITENS} with prompt \"Qual cópia anonimizada você CONFERIU e quer liberar para a validação?\" with title \"CM | Liberação\" OK button name \"Continuar\" cancel button name \"Cancelar\"")
[ $? -ne 0 ] || [ -z "$ARQ" ] || [ "$ARQ" = "false" ] && encerrar "nenhuma cópia escolhida"
echo "$LISTA" | grep -qxF -- "$ARQ" || encerrar "cópia escolhida não está entre as aprovadas" 1
diario "cópia escolhida: $ARQ"

# 2) nome da responsável (pergunta de novo se vier vazio)
NOME=""
for tentativa in 1 2 3; do
  NOME=$(janela "text returned of (display dialog \"Seu nome completo (responsável pela conferência e pela autorização):\" default answer \"\" with title \"CM | Liberação\" buttons {\"Cancelar\", \"Continuar\"} default button \"Continuar\" cancel button \"Cancelar\")") \
    || encerrar "cancelado na janela do nome"
  NOME="${NOME## }"; NOME="${NOME%% }"; NOME="${NOME//\"/\'}"     # aspas quebrariam as janelas
  [ -n "${NOME// /}" ] && break
  avisar "O nome não pode ficar em branco." caution
done
[ -n "${NOME// /}" ] || encerrar "nome não informado" 1
diario "responsável informada"

# 3) confirmação expressa: digitar AUTORIZO
RESP=$(janela "text returned of (display dialog \"Confirme a liberação da cópia:\n\n   $ARQ\n\nDeclaro que CONFERI a cópia anonimizada (busca de nomes com e sem acento, CPF, processo, contrato, assinaturas e metadados) e AUTORIZO seu uso na validação matemática.\n\nPara confirmar, digite AUTORIZO e clique em Liberar.\" default answer \"\" with title \"CM | Liberação\" buttons {\"Cancelar\", \"Liberar\"} default button \"Cancelar\" cancel button \"Cancelar\" with icon caution)") \
  || encerrar "cancelado na confirmação"
[ "${RESP:u}" = "AUTORIZO" ] || { avisar "Confirmação não reconhecida (é preciso digitar AUTORIZO). Nada foi liberado." caution; encerrar "confirmação não digitada"; }
diario "confirmação expressa recebida"

# 4) liberação registrada
SAIDA=$(cm liberar "$ID" "$ARQ" --como parecer --por "$NOME" --confirmo-conferencia 2>&1)
RES=$?
echo "$SAIDA"
diario "liberar: código $RES"
if [ $RES -eq 0 ]; then
  avisar "Cópia LIBERADA e registrada:\n\n$ARQ\nResponsável: $NOME\n\nAvise o Claude que o parecer está liberado para a análise." note
  diario "LIBERADO: $ARQ"
  echo; echo "Liberado. Pode fechar esta janela."
else
  avisar "A liberação NÃO foi concluída. Veja a mensagem na janela do Terminal." stop
  encerrar "erro na liberação" 1
fi
exit 0
