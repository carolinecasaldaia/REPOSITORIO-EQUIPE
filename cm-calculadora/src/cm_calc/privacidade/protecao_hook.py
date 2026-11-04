#!/usr/bin/env python3
"""CM | Calculadora Judicial Bancária — proteção LOCAL de dados de clientes.

Usado de duas formas:
1. Hook PreToolUse do Claude Code (instalado em ~/.claude/hooks/cm-protecao.py):
   recebe a ação pretendida (JSON no stdin) e NEGA leitura, busca, cópia ou
   envio de áreas protegidas de ~/CM-Calculos-Dados, antes de a ação acontecer.
2. Biblioteca do próprio sistema (``avaliar``, ``liberado``), para verificar
   documentos antes de usá-los.

Áreas protegidas (nunca acessíveis ao modelo):
    casos/<ID>/documentos, extracao, resultados, manifesto.json
    validacao/<ID>/original, anonimizados
    validacao/<ID>/anonimizacao/relatorio-detalhado-*, termos.txt
Áreas condicionais:
    validacao/<ID>/parecer/*, documentos/* -> só se o arquivo estiver no registro
    de liberação (anonimizacao/liberacoes.jsonl) com o MESMO sha256.
Buscas recursivas (Grep/Glob, grep -r, find, tar, cp...) sobre pastas que contêm
áreas protegidas também são negadas.

Ações que não mencionam ~/CM-Calculos-Dados (nem ocorrem dentro dela) são
liberadas sem qualquer efeito — outras automações não são afetadas.

Compatível com Python 3.9 (Python do sistema), sem dependências externas.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime

HOME = os.path.expanduser("~")
NOME_RAIZ = "CM-Calculos-Dados"

PROTEGIDOS = [
    (re.compile(r"^/casos/[^/]+/(documentos|extracao|resultados)(/|$)"), "dados de caso (documentos/extração/resultados)"),
    (re.compile(r"^/casos/[^/]+/manifesto\.json$"), "manifesto do caso"),
    (re.compile(r"^/validacao/[^/]+/(original|anonimizados)(/|$)"), "documento original ou cópia ainda não liberada"),
    (re.compile(r"^/validacao/[^/]+/anonimizacao/(relatorio-detalhado-[^/]*|termos\.txt|originais\.jsonl)$"),
     "registro confidencial de anonimização"),
]
LIBERAVEL = re.compile(r"^/validacao/([^/]+)/(parecer|documentos)/([^/]+)$")
ANCESTRAIS = re.compile(r"^(/?|/casos|/casos/[^/]+|/validacao|/validacao/[^/]+|/validacao/[^/]+/anonimizacao)$")
TOKENS = re.compile(r"(^|[/\s'\"=])(original|anonimizados|documentos|extracao|resultados)(/|\s|$|['\"*])"
                    r"|relatorio-detalhado|termos\.txt|originais\.jsonl|manifesto\.json", re.I)
LEITURA_EM_MASSA = re.compile(r"\b(grep|rg|ag|find|tar|zip|rsync|cp|ditto|scp|cat|xargs|python3?|perl|ruby|node|"
                              r"strings|base64|xxd|od|open|mdfind|less|more|head|tail|sed|awk|curl|uv)\b")
LEITORES = {"Read", "Grep", "Glob", "NotebookRead", "LSP"}
RECURSIVOS = {"Grep", "Glob"}
ESCRITA = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
PERGUNTAR = "PERGUNTAR:"
CHAVES_CAMINHO = ("file_path", "path", "notebook_path", "filePath", "root", "out_dir", "directory", "dir")


def raiz() -> str:
    return os.path.realpath(os.environ.get("CM_PROTECAO_RAIZ") or os.path.join(HOME, NOME_RAIZ))


def _expandir(s: str) -> str:
    return s.replace("${HOME}", HOME).replace("$HOME", HOME).replace("~/", HOME + "/")


def relativo(caminho: str, cwd: str | None = None) -> str | None:
    """Caminho relativo à raiz de dados ('/casos/X/...'), ou None se estiver fora dela."""
    p = _expandir(caminho.strip().strip("'\""))
    if not os.path.isabs(p):
        p = os.path.join(cwd or os.getcwd(), p)
    p = os.path.realpath(os.path.normpath(p))
    r = raiz()
    pl, rl = p.lower(), r.lower()           # sistema de arquivos do macOS não diferencia maiúsculas
    if pl == rl:
        return "/"
    if pl.startswith(rl + "/"):
        return p[len(r):]
    return None


def liberado(caminho_abs: str) -> bool:
    """Arquivo de parecer/ ou documentos/ cujo sha256 consta do registro de liberação da advogada."""
    rel = relativo(caminho_abs)
    m = LIBERAVEL.match(rel or "")
    if not m or not os.path.isfile(caminho_abs):
        return False
    registro = os.path.join(raiz(), "validacao", m.group(1), "anonimizacao", "liberacoes.jsonl")
    try:
        with open(caminho_abs, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
        liberado_ok, revogado = False, False
        with open(registro, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                r = json.loads(linha)
                if r.get("sha256") == h:
                    if r.get("revogado"):
                        revogado = True          # revogação prevalece sobre qualquer liberação
                    else:
                        liberado_ok = True
        return liberado_ok and not revogado
    except (OSError, ValueError):
        return False


def _avaliar_caminho(rel: str, abs_: str, ferramenta: str) -> str | None:
    for padrao, motivo in PROTEGIDOS:
        if padrao.match(rel):
            return motivo
    if ferramenta in LEITORES and LIBERAVEL.match(rel) and os.path.isfile(abs_) and not liberado(abs_):
        return "arquivo não liberado pela advogada (ou alterado depois da liberação)"
    if ferramenta in RECURSIVOS and ANCESTRAIS.match(rel):
        return "busca recursiva em pasta que contém dados protegidos"
    return None


def _textos(v) -> list[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [t for x in v.values() for t in _textos(x)]
    if isinstance(v, list):
        return [t for x in v for t in _textos(x)]
    return []


def avaliar(ferramenta: str, entrada: dict, cwd: str | None = None) -> str | None:
    """Motivo da negação, ou None se a ação é permitida."""
    cwd = cwd or os.getcwd()
    # 1) campos de caminho das ferramentas de arquivo
    for chave in CHAVES_CAMINHO:
        v = entrada.get(chave)
        for s in ([v] if isinstance(v, str) else (v if isinstance(v, list) else [])):
            if not isinstance(s, str) or not s:
                continue
            rel = relativo(s, cwd)
            if rel is not None:
                abs_ = os.path.join(raiz(), rel.lstrip("/"))
                motivo = _avaliar_caminho(rel, abs_, ferramenta)
                if motivo:
                    return motivo
    # escrita fora da pasta de dados: o conteúdo escrito (código, documentação) não é acesso a dados
    if ferramenta in ESCRITA:
        return None
    # Glob/Grep: o padrão também pode apontar para áreas protegidas
    if ferramenta in RECURSIVOS:
        base = entrada.get("path") or cwd
        for k in ("pattern", "glob"):
            pad = entrada.get(k)
            if isinstance(pad, str) and relativo(base, cwd) is not None and TOKENS.search(pad):
                return "padrão de busca alcança área protegida"
    # 2) qualquer outro texto (comandos de shell, conteúdo enviado a serviços, etc.)
    texto = _expandir(" ".join(_textos(entrada)))
    if ferramenta == "Bash" and re.search(r"\bcm-calc\b", texto):
        if not _cli_proprio(texto):
            return "a ferramenta cm-calc só pode ser executada sozinha (sem encadear, redirecionar ou enviar a saída)"
        if not re.search(r"\bcm-calc\s+(validacao|--help|-h)\b", texto):
            return PERGUNTAR + "comando cm-calc que exibe dados de caso — confirme se autoriza"
        if re.search(r"\bcm-calc\s+validacao\s+liberar\b", texto):
            return PERGUNTAR + "liberação de documento é ato da advogada — confirme se autoriza esta liberação"
    dentro = relativo(cwd, cwd) is not None
    menciona = NOME_RAIZ.lower() in texto.lower() or "cm_calc_dados" in texto.lower() or "cm_protecao_raiz" in texto.lower()
    if ferramenta == "Bash":
        motivo = _scripts_executados(texto, cwd)
        if motivo:
            return motivo
    if not (menciona or dentro):
        return None
    for m in re.finditer(r"(/[^\s'\"|;&<>]*" + re.escape(NOME_RAIZ) + r"[^\s'\"|;&<>]*)", texto, re.I):
        rel = relativo(m.group(1).rstrip("*"), cwd)
        if rel is not None:
            for padrao, motivo in PROTEGIDOS:
                if padrao.match(rel.replace("*", "x")) or padrao.match(rel):
                    return motivo
            abs_ = os.path.join(raiz(), rel.lstrip("/"))
            if LIBERAVEL.match(rel) and os.path.isfile(abs_) and not liberado(abs_):
                return "arquivo não liberado pela advogada (ou alterado depois da liberação)"
            if ANCESTRAIS.match(rel) and LEITURA_EM_MASSA.search(texto) and not _cli_proprio(texto):
                return "leitura/cópia em massa de pasta que contém dados protegidos"
    if TOKENS.search(texto) and not _cli_proprio(texto):
        return "menção a área protegida dentro da pasta de dados"
    if dentro and LEITURA_EM_MASSA.search(texto) and not _cli_proprio(texto):
        return "comando de leitura executado dentro da pasta de dados"
    return None


def _scripts_executados(texto: str, cwd: str) -> str | None:
    """Scripts chamados pelo comando (python x.py, bash x.sh...) são lidos: se o conteúdo mirar áreas
    protegidas, a execução é negada (o comando em si não mostraria o caminho). O código do próprio
    sistema (src/ e tests/ do projeto) é exceção: ele aplica as verificações locais."""
    projeto = os.path.join(HOME, "cm-calculadora")
    for m in re.finditer(r"([^\s'\"|;&<>]+\.(?:py|sh|zsh|bash|rb|pl|js|command))\b", texto):
        caminho = _expandir(m.group(1))
        if not os.path.isabs(caminho):
            caminho = os.path.join(cwd, caminho)
        caminho = os.path.realpath(caminho)
        if caminho.startswith((os.path.join(projeto, "src") + "/", os.path.join(projeto, "tests") + "/")) \
                or caminho == os.path.realpath(os.path.join(HOME, ".claude", "hooks", "cm-protecao.py")):
            continue
        try:
            if not (os.path.isfile(caminho) and os.path.getsize(caminho) < 2_000_000):
                continue
            with open(caminho, encoding="utf-8", errors="ignore") as f:
                conteudo = f.read()
        except OSError:
            continue
        baixo = conteudo.lower()
        if (NOME_RAIZ.lower() in baixo or "cm_calc_dados" in baixo or "raiz_dados" in baixo) and TOKENS.search(conteudo):
            return "script executado faz referência a área protegida da pasta de dados"
    return None


def _cli_proprio(texto: str) -> bool:
    """Comando que é só a ferramenta local cm-calc (ela não exibe dados pessoais)."""
    partes = [p.strip() for p in re.split(r"&&|;|\|\|", texto) if p.strip()]
    return bool(partes) and all(re.match(r"^(cd\s+\S+|(uv\s+run\s+)?cm-calc\s.*|ls(\s+-\w+)*(\s+\S+)?)$", p) for p in partes) \
        and "|" not in texto and ">" not in texto


def _registrar(ferramenta: str, motivo: str) -> None:
    try:
        log = os.path.join(HOME, ".claude", "hooks", "cm-protecao.log")
        with open(log, "a", encoding="utf-8") as f:   # sem caminhos nem conteúdo: só ferramenta e motivo
            f.write(f"{datetime.now().isoformat(timespec='seconds')}\tNEGADO\t{ferramenta}\t{motivo}\n")
    except OSError:
        pass


def main() -> int:
    bruto = sys.stdin.read()
    try:
        dados = json.loads(bruto)
        ferramenta = dados.get("tool_name", "")
        motivo = avaliar(ferramenta, dados.get("tool_input") or {}, dados.get("cwd"))
    except Exception:  # noqa: BLE001 — falha interna: só bloqueia se a ação envolver a pasta de dados
        ferramenta = "?"
        motivo = "verificação de proteção falhou" if NOME_RAIZ.lower() in bruto.lower() else None
    if motivo is None:
        return 0
    if motivo.startswith(PERGUNTAR):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                          "permissionDecisionReason": "CM | Proteção de dados: " + motivo[len(PERGUNTAR):]}},
                         ensure_ascii=False))
        return 0
    _registrar(ferramenta, motivo)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": f"CM | Proteção de dados: acesso negado — {motivo}. "
                                    "Use apenas arquivos liberados pela advogada (cm-calc validacao liberar)."}},
        ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
