#!/bin/bash
set -e

CASA="$HOME/.cadastro-astrea"
PLIST="$HOME/Library/LaunchAgents/com.carolinemacedo.manter-acordado.plist"
SCRIPT_ACORDAR="$CASA/manter-acordado.sh"

desfazer() {
    echo "Desfazendo o agendamento de energia..."
    osascript -e 'do shell script "pmset repeat cancel" with administrator privileges with prompt "Autorize remover o agendamento de acordar/dormir do Mac"' || true
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST" "$SCRIPT_ACORDAR"
    echo
    echo "Pronto. O Mac voltou a dormir/acordar do jeito de antes (sem agendamento fixo)."
    echo "A automação do Cadastro Astrea continua normal, só que agora depende do Mac"
    echo "estar ligado e acordado na hora certa."
    read -p "Pressione ENTER para fechar..." _
    exit 0
}

if [ "$1" = "--desfazer" ]; then
    desfazer
fi

clear
echo "======================================================================"
echo " MANTER O MAC ACORDADO PARA O CADASTRO ASTREA RODAR SOZINHO"
echo "======================================================================"
echo
echo "O Cadastro Astrea roda de hora em hora, das 08:40 às 20:40. Hoje isso só"
echo "acontece se o Mac já estiver ligado e acordado nesses horários."
echo
echo "Este instalador vai configurar o Mac mini para:"
echo
echo "   1) Acordar/ligar sozinho às 08:35, todos os dias"
echo "   2) Ficar acordado até por volta das 20:42 (cobre as 13 rodadas)"
echo "   3) Voltar a dormir sozinho às 20:50, se ninguém estiver usando"
echo
echo "Isso é uma configuração do macOS (não da automação em si) e por isso vai"
echo "pedir a SENHA DO SEU MAC numa janela própria do sistema, uma única vez."
echo
echo "Para desfazer depois, clique com o botão direito neste mesmo arquivo,"
echo "escolha Abrir, e quando pedir rode com --desfazer (ou peça ao Claude)."
echo
read -p "Pressione ENTER para continuar, ou feche esta janela para cancelar..." _

echo
echo "Aplicando o agendamento de energia (vai pedir sua senha)..."
osascript -e 'do shell script "pmset repeat wakeorpoweron MTWRFSU 08:35:00 sleep MTWRFSU 20:50:00" with administrator privileges with prompt "Autorize o Mac a acordar às 08:35 e dormir às 20:50, todos os dias"'

mkdir -p "$CASA/logs"

cat > "$SCRIPT_ACORDAR" <<'EOF'
#!/bin/sh
# Mantém o Mac acordado durante a janela do Cadastro Astrea (08:40-20:40).
# Gerado por "Manter Mac Acordado (Cadastro Astrea).command". Não precisa editar à mão.
exec /usr/bin/caffeinate -s -i -t 43560
EOF
chmod +x "$SCRIPT_ACORDAR"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.carolinemacedo.manter-acordado</string>
  <key>ProgramArguments</key>
  <array>
    <string>$SCRIPT_ACORDAR</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>36</integer></dict>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>$CASA/logs/manter-acordado.out</string>
  <key>StandardErrorPath</key><string>$CASA/logs/manter-acordado.err</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo
echo "======================================================================"
echo " PRONTO"
echo "======================================================================"
echo
echo "A partir de amanhã:"
echo "  - O Mac acorda/liga sozinho às 08:35"
echo "  - Fica acordado até por volta das 20:42 (cobre as 13 rodadas do Cadastro Astrea)"
echo "  - Volta a dormir às 20:50, se ninguém estiver usando"
echo
echo "Conferir a qualquer momento com: pmset -g sched"
echo
read -p "Pressione ENTER para fechar..." _
