#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Senha do Astrea no Porta-chaves do macOS (decisão dela, 29/09/2026).

Até então a senha ficava em texto aberto no ~/.cadastro-astrea/.env. O
Porta-chaves guarda cifrado e só entrega ao usuário logado nesta máquina.

A gravação passa a senha ao `security` pela ENTRADA PADRÃO (`security -i`) e
em hexadecimal (`-X`): nunca vai na linha de comando, que qualquer processo
da máquina consegue listar com `ps`, e não depende de escapar aspas ou `!`.
"""

import subprocess

SERVICO_ASTREA = "cadastro-astrea"


class ErroPortaChaves(Exception):
    pass


def ler(servico: str, conta: str) -> str:
    """
    Segredo guardado, ou "" se não houver (ou se o Porta-chaves recusar).

    Usa `-g` e não `-w`: com `-w`, segredo que tem acento volta em
    hexadecimal sem aviso nenhum, e não dá para distinguir de uma senha que
    por acaso só tenha 0-9a-f. O `-g` marca: `password: 0x<hex>  "..."`
    quando veio em hexadecimal, `password: "..."` quando é texto puro.
    """
    if not conta:
        return ""
    try:
        saida = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", servico,
             "-a", conta, "-g"], capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    if saida.returncode != 0:
        return ""
    for linha in saida.stderr.decode("utf-8", "replace").splitlines():
        if not linha.startswith("password:"):
            continue
        valor = linha[len("password:"):].strip()
        if valor.startswith("0x"):
            return bytes.fromhex(valor[2:].split()[0]).decode("utf-8")
        if len(valor) >= 2 and valor[0] == valor[-1] == '"':
            return valor[1:-1]
        return ""
    return ""


def gravar(servico: str, conta: str, segredo: str):
    """Grava (ou substitui) o segredo. Confere lendo de volta."""
    if not conta or not segredo:
        raise ErroPortaChaves("conta e segredo são obrigatórios")
    comando = 'add-generic-password -U -s "%s" -a "%s" -X %s\n' % (
        servico, conta, segredo.encode("utf-8").hex())
    try:
        saida = subprocess.run(["/usr/bin/security", "-i"], input=comando.encode("ascii"),
                               capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as erro:
        raise ErroPortaChaves("não consegui chamar o Porta-chaves: %s" % erro)
    if saida.returncode != 0 or ler(servico, conta) != segredo:
        raise ErroPortaChaves("o Porta-chaves não confirmou a gravação (%s)"
                              % saida.stderr.decode("utf-8", "ignore").strip()[:200])
