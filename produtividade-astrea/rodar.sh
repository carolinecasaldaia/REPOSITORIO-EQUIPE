#!/bin/sh
# Chamado pelo app "Produtividade Astrea" (agendador: 12:10 e 20:10).
# Coleta no Astrea os prazos/tarefas concluídos e regera o dashboard.
PY=/Users/carolinemacedo/.cadastro-astrea/venv/bin/python3
PROGRAMA='/Users/carolinemacedo/Library/CloudStorage/GoogleDrive-contato@carolinemacedoadv.com/Meu Drive/Documentos Escritório /EMPRESA/CLAUDE/PRODUTIVIDADE - PRAZOS ASTREA/coletar.py'
CASA="$HOME/.produtividade-astrea"
mkdir -p "$CASA/logs"
cd "$(dirname "$PROGRAMA")" || exit 1
"$PY" "$PROGRAMA" >> "$CASA/logs/agendador.out" 2>> "$CASA/logs/agendador.err"
CODIGO=$?
# Ranking do Escritório (05/11/2026): ano inteiro, todas as pessoas. Regrava
# RELATÓRIOS/atividades_escritorio_AAAA.csv e ranking-escritorio-dados.json
# (lido pela página no claude.ai). Falha aqui não muda o resultado acima.
"$PY" "$(dirname "$PROGRAMA")/ranking_escritorio.py" >> "$CASA/logs/agendador.out" 2>> "$CASA/logs/agendador.err" || \
    osascript -e 'display notification "Veja ~/.produtividade-astrea/logs" with title "Ranking do escritório não atualizou" sound name "Basso"' >/dev/null 2>&1
QUANDO=$(date "+%d/%m/%Y %H:%M")
if [ "$CODIGO" -eq 0 ]; then
    printf '%s  ok\n' "$QUANDO" > "$CASA/ultima-rodada.txt"
else
    printf '%s  falhou (codigo %s)\n' "$QUANDO" "$CODIGO" > "$CASA/ultima-rodada.txt"
    osascript -e 'display notification "Veja ~/.produtividade-astrea/logs" with title "Dashboard de prazos não atualizou" sound name "Basso"' >/dev/null 2>&1
fi
exit "$CODIGO"
