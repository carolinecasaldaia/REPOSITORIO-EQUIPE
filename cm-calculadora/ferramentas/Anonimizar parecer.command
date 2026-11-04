#!/bin/zsh
# CM | Calculadora Judicial Bancária — ANONIMIZAÇÃO LOCAL de parecer.
# - Tudo acontece neste Mac: nada é enviado à internet nem ao Claude.
# - O arquivo original escolhido NÃO é alterado (o sistema trabalha com uma cópia).
# - O documento anonimizado NÃO é liberado aqui: a liberação é um passo separado
#   ("CM - Liberar parecer anonimizado"), depois da sua conferência.

ID="${CM_VALIDACAO_ID:-VAL-001}"
PROJETO="$HOME/cm-calculadora"
cm() { /opt/homebrew/bin/uv run --quiet --project "$PROJETO" cm-calc validacao "$@"; }
aviso() {
  [ -n "$CM_SEM_DIALOGOS" ] && return 0
  osascript -e "display dialog \"$1\" with title \"CM | Anonimização\" buttons {\"OK\"} default button 1 with icon $2" >/dev/null
}

echo "CM | Anonimização local — validação $ID"
echo

if [ -n "$CM_TESTE_ARQUIVO" ]; then
  ARQ="$CM_TESTE_ARQUIVO"
else
  ARQ=$(osascript -e 'POSIX path of (choose file with prompt "Selecione o PDF ORIGINAL do parecer (ele não será alterado):" of type {"com.adobe.pdf"})' 2>/dev/null) \
    || { echo "Cancelado."; exit 0; }
fi

if [ -n "${CM_TESTE_TERMOS+x}" ]; then
  TERMOS="$CM_TESTE_TERMOS"
else
  TERMOS=$(osascript -e 'text returned of (display dialog "Digite os nomes e números que aparecem no parecer e devem ser removidos, separados por ponto e vírgula (;).

Exemplo: nome da autora; nome da perita; nome do advogado; nº do contrato; placa

(O sistema também procura CPF, processo, endereço, telefone, e-mail etc. automaticamente.)" default answer "" with title "CM | Anonimização")' 2>/dev/null) \
    || { echo "Cancelado."; exit 0; }
fi

cm preparar "$ID" >/dev/null || { aviso "Não foi possível preparar a pasta de validação." stop; exit 1; }
cm importar-original "$ID" "$ARQ" || { aviso "Não foi possível copiar o arquivo escolhido." stop; exit 1; }
if [ -n "$TERMOS" ]; then
  cm termos "$ID" --adicionar "$TERMOS"
fi

echo
cm anonimizar "$ID"
RES=$?
echo

if [ $RES -eq 0 ]; then
  aviso "Verificação automática APROVADA.

Agora confira com calma:
• vão abrir o ORIGINAL e a CÓPIA ANONIMIZADA (Pré-Visualização);
• e os relatórios (TextEdit) — o 'detalhado' é confidencial.

O documento NÃO foi liberado. Depois de conferir, use 'CM - Liberar parecer anonimizado'." note
else
  aviso "PROCEDIMENTO INTERROMPIDO: a verificação foi REPROVADA.

Os motivos estão nesta janela do Terminal. Não libere o documento — avise a equipe técnica." stop
fi

[ -n "$CM_SEM_DIALOGOS" ] || cm abrir-conferencia "$ID"
echo "Pode fechar esta janela."
exit $RES
