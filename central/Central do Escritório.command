#!/bin/zsh
# Central do Escritório — abre em http://127.0.0.1:8500 (só neste Mac).
# Feche esta janela do Terminal para desligar a central.
cd "$HOME/AUTOMACOES/automacoes-claude/central" || exit 1
exec /usr/bin/python3 central.py
