#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aviso na tela do Mac quando a rodada automática traz alguma coisa.

A automação roda sem janela nenhuma: sem isso, a única forma de saber que um
contrato chegou seria abrir o relatório de tempos em tempos. O aviso aparece
como notificação do macOS, com o nome do cliente.

Só avisa quando há o que contar — contrato arquivado ou documento esperando
por ela. Rodada sem novidade não interrompe ninguém.
"""

import subprocess


def aspas(texto: str) -> str:
    """
    Texto entre aspas do jeito que o AppleScript entende.

    Não dá para usar json.dumps aqui: ele escapa acento como \\u00c1, e o
    AppleScript não conhece essa notação — o script morre com erro de sintaxe.
    Como quase todo nome de cliente tem acento, isso derrubaria o aviso
    justamente nos casos reais. Só a barra invertida e a aspa precisam de
    escape; o resto vai como está, em UTF-8.
    """
    return '"%s"' % str(texto or "").replace("\\", "\\\\").replace('"', '\\"')


def _texto_dos_clientes(eventos, situacao, limite=3):
    nomes = [(e.get("cliente") or e.get("nome") or "").strip()
             for e in eventos if e.get("situacao") == situacao]
    nomes = [n for n in nomes if n]
    if not nomes:
        return ""
    if len(nomes) <= limite:
        return ", ".join(nomes)
    return "%s e mais %d" % (", ".join(nomes[:limite]), len(nomes) - limite)


def montar(resumo) -> tuple:
    """Devolve (título, mensagem) do aviso, ou (None, None) se não há o que dizer."""
    baixados = resumo.get("baixados", 0)
    pendentes = resumo.get("pendentes", 0) + resumo.get("erros", 0)
    retomados = resumo.get("onboardings_retomados") or []
    if not baixados and not pendentes:
        if retomados:
            # Documento que chegou depois destravou um onboarding antigo.
            return ("Onboarding pronto",
                    "%s — o documento que faltava chegou" % ", ".join(retomados))
        return None, None

    eventos = resumo.get("eventos") or []
    partes = []
    if baixados:
        quem = _texto_dos_clientes(eventos, "baixado")
        titulo = ("Contrato assinado arquivado" if baixados == 1
                  else "%d contratos assinados arquivados" % baixados)
        partes.append(quem or "pasta do cliente atualizada")
        onboarding = sum(1 for e in eventos if e.get("onboarding") == "gerado")
        se_falta = sum(1 for e in eventos if e.get("onboarding") == "pendente")
        if onboarding:
            partes.append("onboarding gerado" if onboarding == 1
                          else "%d onboardings gerados" % onboarding)
        if se_falta:
            partes.append("%d onboarding(s) esperando o banco adverso" % se_falta)
    else:
        titulo = "Documento assinado esperando você"

    if pendentes:
        quem = _texto_dos_clientes(eventos, "pendente")
        partes.append("%d documento(s) precisam de você%s"
                      % (pendentes, (": " + quem) if quem else ""))

    # Envelope com dois contratos é raro e caro de passar batido: some do
    # relatório se não for dito aqui, e o segundo caso não existe para ninguém.
    varios = [e for e in eventos if e.get("multicontrato")]
    if varios:
        nomes = ", ".join(sorted({(e.get("cliente") or "cliente") for e in varios}))
        partes.append("ATENÇÃO: envelope com mais de um contrato (%s) — "
                      "separe em uma pasta por contrato" % nomes)
        titulo = "Envelope com mais de um contrato"
    return titulo, " · ".join(partes)


def notificar(titulo: str, mensagem: str, som: str = "Glass") -> bool:
    """Notificação do macOS. Falha em silêncio: aviso nunca derruba a rodada."""
    if not titulo:
        return False
    script = ('display notification %s with title %s%s'
              % (aspas(mensagem), aspas(titulo),
                 (" sound name %s" % aspas(som)) if som else ""))
    try:
        return subprocess.run(["osascript", "-e", script],
                              capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def avisar_da_rodada(resumo, config) -> bool:
    if not getattr(config, "avisar_na_tela", True):
        return False
    titulo, mensagem = montar(resumo)
    return notificar(titulo, mensagem) if titulo else False
