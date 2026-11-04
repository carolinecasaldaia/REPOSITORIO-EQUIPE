#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cópia da pasta do cliente para a área do escritório, depois do caso aberto.

Decisão dela (23/09/2026): depois que a entrada é confirmada no Asaas, o
contato é cadastrado e o caso é aberto no Astrea, a pasta do cliente (que
está em PREPARAÇÃO PARA INGRESSO) é COPIADA — o original continua lá — para
a área que vai de fato trabalhar o caso: "A - REVISIONAL" (Busca e Apreensão
e qualquer Revisional) ou "A - CÍVEL" (Cível).

É cópia, não mudança de lugar: a pasta de origem continua em PREPARAÇÃO PARA
INGRESSO, que é domínio do comercial — esta automação nunca apaga, move ou
altera o CONTEÚDO de nada lá (ver README, "O que a automação nunca faz").
A única mudança permitida ali é renomear (ver `marcar_pasta_ok`), acrescentando
"OK -" para avisar que o caso já foi aberto e a cópia já foi feita.

Só entra pasta vista pela primeira vez a partir de 23/09/2026 — decisão dela:
cliente de antes dessa data não faz parte desta automação nova, nem para
cópia nem para a marcação.
"""

import re
import shutil
from pathlib import Path

from src.astrea import prontos as _prontos
from src.validators import documentacao as _documentacao

TIPOS_REVISIONAL = ("BUSCA E APREENSÃO", "REVISIONAL VEICULAR",
                    "REVISIONAL EMPRÉSTIMO", "REVISIONAL CARTÃO DE CRÉDITO")
TIPOS_CIVEL = ("CÍVEL",)

# "1 - OK - FULANO DE TAL" -> "FULANO DE TAL". A pasta de origem carrega um
# prefixo numérico e de status que não existe na nomenclatura das áreas — lá
# as pastas de cliente têm só o nome.
_PREFIXO_PASTA = re.compile(r"^\s*\d+\s*-\s*(OK\s*-\s*)?", re.I)

# "15 - FULANO" -> grupo 1 = "15 - ", grupo 2 = "FULANO". Usado só para saber
# onde encaixar o "OK -" em `marcar_pasta_ok`, sem mexer no número que o
# comercial já usa para ordenar a fila.
_PREFIXO_NUMERICO = re.compile(r"^(\s*\d+\s*-\s*)(.*)$")


def pasta_destino(config, tipo: str):
    """
    Área de destino (A - REVISIONAL / A - CÍVEL) para o tipo de ação, ou
    None se o tipo não tiver destino definido — não copia às cegas para um
    tipo que não foi mapeado.
    """
    if tipo in TIPOS_REVISIONAL:
        return config.pasta_revisional
    if tipo in TIPOS_CIVEL:
        return config.pasta_civel
    return None


def nome_da_copia(nome_pasta_origem: str, nome_cliente: str) -> str:
    """
    Nome da pasta na área de destino: o nome do cliente, sem o prefixo
    numérico/status da pasta de PREPARAÇÃO PARA INGRESSO — é assim que as
    pastas já existentes em "A - REVISIONAL"/"A - CÍVEL" são nomeadas.
    """
    limpo = _PREFIXO_PASTA.sub("", nome_pasta_origem or "").strip()
    return limpo or (nome_cliente or "").strip()


def copiar_para_area(origem, nome_pasta_origem: str, nome_cliente: str,
                     tipo: str, config, log) -> bool:
    """
    Copia a pasta do cliente para a área certa (Revisional/Cível), sem mexer
    no original. Devolve True se copiou, False se não copiou por algum
    motivo (tipo sem área definida, pasta de origem sumiu, pasta já existe
    no destino, erro de E/S) — nunca derruba quem chamou.
    """
    destino_area = pasta_destino(config, tipo)
    if destino_area is None:
        log.alerta("Não copiei a pasta de %s: tipo %r não tem área de destino "
                  "definida." % (nome_cliente, tipo))
        return False

    origem = Path(origem)
    if not origem.exists():
        log.alerta("Não copiei a pasta de %s: a pasta de origem não existe mais "
                  "(%s)." % (nome_cliente, origem))
        return False

    # Trava de documentação (decisão dela, 25/09/2026). Quem chama já barra
    # antes de abrir o caso (`executar._barrar_documentacao_incompleta`);
    # repetir aqui garante que nenhum outro caminho copie pasta incompleta.
    faltando = _documentacao.faltantes(origem, tipo)
    # A liberação manual vale aqui também (20/10/2026): se ela liberou o
    # cliente, o caso está aberto e a equipe já está trabalhando — segurar a
    # pasta do jurídico só esconderia o processo de quem precisa dele. O que
    # falta continua no relatório de pendências.
    motivo_liberacao = _documentacao.liberado(nome_cliente, nome_pasta_origem)
    if faltando and motivo_liberacao:
        log.alerta("Pasta de %s copiada com documentação incompleta, por "
                  "decisão dela (%s) — falta: %s"
                  % (nome_cliente, motivo_liberacao, ", ".join(faltando)))
        faltando = []
    if faltando:
        log.alerta("Não copiei a pasta de %s para %s: %s"
                  % (nome_cliente, destino_area.name,
                     _documentacao.mensagem(faltando)))
        return False

    destino = destino_area / nome_da_copia(nome_pasta_origem, nome_cliente)
    if destino.exists():
        # Não sobrescreve: pode ser a cópia de uma rodada anterior (nada a
        # fazer) ou o cliente voltando a comprar do escritório, com o nome
        # batendo por coincidência — decidir isso sozinha não é seguro. Regra
        # dela, 23/09/2026: na dúvida, questionar.
        log.alerta("Pasta de %s já existe em %s — não sobrescrevi. Confira se é "
                  "a mesma cópia de antes ou se precisa de um nome diferente."
                  % (nome_cliente, destino_area.name))
        return False

    try:
        shutil.copytree(origem, destino)
    except OSError as erro:
        log.alerta("Falha ao copiar a pasta de %s para %s: %s"
                  % (nome_cliente, destino_area.name, erro))
        return False

    log.ok("Pasta de %s copiada para %s." % (nome_cliente, destino_area.name))
    return True


def marcar_pasta_ok(pasta_origem):
    """
    Renomeia a pasta em PREPARAÇÃO PARA INGRESSO acrescentando "OK -": sinal
    de que o caso já foi aberto e a pasta já foi copiada para a área do
    jurídico (decisão dela, 23/09/2026).

    Diferente do `src/astrea/prontos.py`, que é outro critério (mais amplo:
    subpastas, contrato, onboarding) e continua manual por decisão de
    21/08/2026 — esta marcação é só para este evento específico (caso aberto
    + pasta copiada), e é automática porque o próprio evento já é a
    confirmação.

    Usa `prontos.ja_marcada` para não marcar duas vezes (ex.: rodada que
    repete por algum motivo). Renomear é seguro: a chave de controle é o ID
    da pasta no Drive, não o nome (ver README, "Identificação das pastas").
    Devolve o caminho novo, ou o mesmo caminho se não mexeu (já marcada, ou
    já existe uma pasta com o nome de destino).
    """
    pasta_origem = Path(pasta_origem)
    nome = pasta_origem.name
    if _prontos.ja_marcada(nome):
        return pasta_origem
    m = _PREFIXO_NUMERICO.match(nome)
    novo_nome = ("%sOK - %s" % (m.group(1), m.group(2))) if m else ("01 - OK - " + nome)
    novo_caminho = pasta_origem.with_name(novo_nome)
    if novo_caminho.exists():
        return pasta_origem
    pasta_origem.rename(novo_caminho)
    return novo_caminho
