"""Validação pericial (Fase 5): reconstrução independente e comparação com o parecer.

Separação rigorosa:
- ENTRADAS do cálculo vêm da ficha do caso (contrato e título), nunca dos
  resultados da perita;
- RESULTADOS da perita (AP01, AP02, AP03) entram só como objeto de comparação.
O motor não é alterado para reproduzir o parecer: cenários alternativos são
executados apenas para diagnosticar a origem das divergências.
"""
