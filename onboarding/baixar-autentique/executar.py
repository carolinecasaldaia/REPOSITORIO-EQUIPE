#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Baixa do Autentique os contratos assinados por todas as partes e arquiva na
pasta do cliente em PREPARAÇÃO PARA INGRESSO.

    python3 executar.py rodar          # é o que o agendador chama
    python3 executar.py conferir       # mostra o que faria; não grava nada
    python3 executar.py historico      # traz assinados de antes (pede confirmação)
    python3 executar.py pendencias     # atualiza e abre o relatório
    python3 executar.py status         # configuração e contagens
    python3 executar.py chave          # guarda a chave da API do Autentique
    python3 executar.py testar         # confere se a chave funciona
    python3 executar.py agendador --instalar | --remover | --ver
"""

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

from src import autentique, aviso, relatorio, servico               # noqa: E402
from src.config import (ARQUIVO_ENV, BINARIO_PYTHON_REAL, get_config,  # noqa: E402
                        gravar_no_env, mascarar_token)
from src.estado import Estado, Tranca                               # noqa: E402
from src.log import Log                                             # noqa: E402

ROTULO_AGENDADOR = "com.carolinemacedo.baixar-autentique"


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------

def _preparar(mostrar_na_tela=True):
    config = get_config(recarregar=True)
    config.preparar_pastas()
    log = Log(config.pasta_logs, mostrar_na_tela=mostrar_na_tela)
    return config, log


def _impedimentos(config, log) -> bool:
    problemas = config.problemas()
    for problema in problemas:
        log.erro("[!] " + problema)
    return bool(problemas)


def _abrir(caminho):
    subprocess.run(["open", str(caminho)], check=False)


def _perguntar_em_janela(mensagem, oculto=False, padrao=""):
    """
    Pede um dado numa janela do macOS, não no terminal.

    A chave vai da janela direto para o arquivo: não aparece na tela, não entra
    em log nem no histórico do shell. (Mesmo cuidado do CADASTRO ASTREA.)
    """
    # aviso.aspas, e não json.dumps: acento vira \\uXXXX no json e o AppleScript
    # não entende — a janela nem chega a abrir.
    script = ('activate\n'
              'display dialog %s default answer %s %s with title '
              '"Baixar Contratos Assinados" buttons {"Cancelar", "OK"} '
              'default button "OK"'
              % (aviso.aspas(mensagem), aviso.aspas(padrao),
                 "with hidden answer" if oculto else ""))
    resultado = subprocess.run(["osascript", "-e", script],
                               capture_output=True, text=True)
    if resultado.returncode != 0:
        return None
    saida = resultado.stdout.strip()
    marca = "text returned:"
    return saida.split(marca, 1)[1].strip() if marca in saida else ""


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def cmd_rodar(args):
    config, log = _preparar(mostrar_na_tela=not args.silencioso)
    if _impedimentos(config, log):
        return 2

    conferir = getattr(args, "conferir", False)
    log.titulo("Contratos assinados no Autentique — %s"
               % ("conferência (nada é gravado)" if conferir else "verificação"))

    estado = Estado.carregar(config.arquivo_estado)
    api = autentique.Autentique(config.token, config.api_url, config.timeout_s)

    try:
        with Tranca(config.pasta_dados / "execucao.lock"):
            resumo = servico.rodar(config, estado, log, api, somente_conferir=conferir)
            if not conferir:
                servico.limpar_quarentena(config)
                log.limpar_antigos()
    except RuntimeError as erro:            # tranca
        log.aviso(str(erro))
        return 1
    except autentique.ChaveInvalida as erro:
        log.erro(str(erro))
        return 2
    except autentique.ErroAutentique as erro:
        log.erro(str(erro))
        return 1

    log.info("")
    log.info("Assinados por todas as partes: %d   |   novos nesta rodada: %d"
             % (resumo["prontos"], resumo["novos"]))
    if resumo["baixados"]:
        log.ok("Arquivados na pasta do cliente: %d" % resumo["baixados"])
    if resumo["pendentes"]:
        log.aviso("Esperando você decidir: %d" % resumo["pendentes"])
    if resumo["ignorados"]:
        log.info("Não eram envelope de onboarding: %d" % resumo["ignorados"])
    if resumo["erros"]:
        log.erro("Com erro (a próxima rodada tenta de novo): %d" % resumo["erros"])
    if not resumo["novos"] and not resumo["primeira_vez"]:
        log.info("Nenhum contrato novo assinado desde a última verificação.")

    if not conferir:
        caminho = relatorio.gerar(estado, config, resumo)
        log.info("Relatório: %s" % caminho)
        # A rodada automática não tem janela: o aviso na tela é como ela fica
        # sabendo que chegou contrato sem precisar abrir o relatório.
        aviso.avisar_da_rodada(resumo, config)
        if args.abrir:
            _abrir(caminho)
    return 0


def cmd_historico(args):
    config, log = _preparar()
    if _impedimentos(config, log):
        return 2

    dias = args.dias or config.dias_historico
    log.titulo("Trazer contratos assinados dos últimos %d dias" % dias)
    if not args.sim:
        resposta = input("Isso baixa e arquiva o que já estava assinado. "
                         "Confirma? [s/N] ").strip().lower()
        if not resposta.startswith("s"):
            print("Cancelado.")
            return 0

    estado = Estado.carregar(config.arquivo_estado)
    api = autentique.Autentique(config.token, config.api_url, config.timeout_s)
    try:
        with Tranca(config.pasta_dados / "execucao.lock"):
            resumo = servico.rodar(config, estado, log, api, incluir_historico=True, dias=dias)
    except RuntimeError as erro:
        log.aviso(str(erro))
        return 1
    except autentique.ErroAutentique as erro:
        log.erro(str(erro))
        return 1

    log.info("")
    log.ok("Arquivados: %d   |   pendentes: %d   |   erros: %d"
           % (resumo["baixados"], resumo["pendentes"], resumo["erros"]))
    caminho = relatorio.gerar(estado, config, resumo)
    log.info("Relatório: %s" % caminho)
    _abrir(caminho)
    return 0


def cmd_pendencias(args):
    config, log = _preparar()
    estado = Estado.carregar(config.arquivo_estado)
    caminho = relatorio.gerar(estado, config)
    print("Relatório atualizado: %s" % caminho)
    _abrir(caminho)
    return 0


def cmd_status(args):
    config, _log = _preparar()
    estado = Estado.carregar(config.arquivo_estado)
    contagem = estado.contagem()

    print()
    for chave, valor in config.resumo().items():
        print("  %-24s %s" % (chave + ":", valor))
    print()
    print("  %-24s %s" % ("última verificação:", estado.dados.get("ultima_rodada") or "nunca"))
    print("  %-24s %d baixados | %d pendentes | %d erros | %d histórico"
          % ("documentos:", contagem.get("baixado", 0), contagem.get("pendente", 0),
             contagem.get("erro", 0), contagem.get("historico", 0)))

    plist = Path.home() / "Library/LaunchAgents" / (ROTULO_AGENDADOR + ".plist")
    if plist.exists():
        horas = config.horarios()
        print("  %-24s ligado (%02dh às %02dh, todo dia, no minuto %02d)"
              % ("automático:", horas[0][0], horas[-1][0], config.minuto))
        marca = config.pasta_dados / "ultima-rodada-automatica.txt"
        if marca.exists():
            print("  %-24s %s" % ("última vez sozinha:",
                                  marca.read_text(encoding="utf-8").strip()))
        else:
            print("  %-24s ainda não rodou sozinha" % "última vez sozinha:")
    else:
        print("  %-24s desligado" % "automático:")

    for problema in config.problemas():
        print("\n  [!] " + problema)
    return 0


def cmd_chave(args):
    """Guarda a chave da API do Autentique em ~/.baixar-autentique/.env."""
    print("\nA chave é gerada no painel do Autentique:")
    print("  Configurações → Chaves de API (ou Integrações → API) → gerar chave.")
    print("Ela dá acesso aos documentos do escritório — fica guardada só nesta")
    print("máquina, em ~/.baixar-autentique/.env, fora do Google Drive.\n")

    chave = _perguntar_em_janela("Cole aqui a chave da API do Autentique:", oculto=True)
    if chave is None:
        print("Cancelado.")
        return 1
    chave = (chave or "").strip()
    if not chave:
        print("Nada foi digitado — a chave continua como estava.")
        return 1

    gravar_no_env("AUTENTIQUE_TOKEN", chave)
    print("Chave guardada em %s (só você lê esse arquivo)." % ARQUIVO_ENV)
    print("Conferindo se ela funciona...\n")
    return cmd_testar(args)


def cmd_testar(args):
    config, _log = _preparar()
    if not config.token:
        print("Ainda não há chave configurada. Use a opção de configurar a chave.")
        return 2
    print("Chave: %s" % mascarar_token(config.token))
    api = autentique.Autentique(config.token, config.api_url, config.timeout_s)
    try:
        resultado = api.testar()
    except autentique.ErroAutentique as erro:
        print("\n[!] %s" % erro)
        return 2

    total = resultado.get("total")
    print("Conexão com o Autentique: OK.")
    if isinstance(total, int):
        print("Documentos na conta: %d" % total)
    print("\nAmostra dos mais recentes:")
    for item in resultado["amostra"]:
        resumo = item["resumo"]
        situacao = ("assinado por todos"
                    if item["pronto"] else
                    "falta assinar: " + (", ".join(resumo["faltam"]) or "—"))
        print("  • %-48s %s" % ((item["nome"] or "")[:48], situacao))
    return 0


APLICATIVO = Path.home() / "Applications" / "Baixar Contratos Assinados.app"

INFO_PLIST_APP = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Baixar Contratos Assinados</string>
  <key>CFBundleDisplayName</key><string>Baixar Contratos Assinados</string>
  <key>CFBundleIdentifier</key><string>com.carolinemacedo.baixar-autentique.app</string>
  <key>CFBundleExecutable</key><string>rodar</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>NSDocumentsFolderUsageDescription</key><string>Arquivar os contratos assinados na pasta do cliente, no Google Drive.</string>
  <key>NSDesktopFolderUsageDescription</key><string>Arquivar os contratos assinados na pasta do cliente.</string>
  <key>NSDownloadsFolderUsageDescription</key><string>Ler o PDF assinado baixado do Autentique.</string>
</dict>
</plist>
"""


def cmd_aplicativo(args):
    """
    Cria o aplicativo que o agendador chama.

    Por que existe um aplicativo no meio do caminho: a pasta do Google Drive
    (~/Library/CloudStorage) só é liberada para APLICATIVOS autorizados. O
    Python chamado direto pelo agendador é barrado, mesmo com Acesso Total ao
    Disco — foi medido em 18/08/2026.

    E o executável dele precisa ser um programa compilado, não um roteiro de
    shell: com um script, o macOS atribui a permissão ao /bin/sh e a
    autorização dada ao aplicativo não vale para nada (essa foi a pegadinha
    que segurou tudo por uma manhã).
    """
    if APLICATIVO.exists() and not args.refazer:
        print("O aplicativo já existe: %s" % APLICATIVO)
        print("Não vou mexer nele — refazer troca a assinatura e DERRUBA a")
        print("permissão que você já concedeu. Use --refazer só se precisar.")
        return 0

    fonte = AQUI / "lancador.c"
    if not fonte.exists():
        print("Falta o arquivo lancador.c ao lado do executar.py.")
        return 1

    (APLICATIVO / "Contents" / "MacOS").mkdir(parents=True, exist_ok=True)
    (APLICATIVO / "Contents" / "Info.plist").write_text(INFO_PLIST_APP, encoding="utf-8")
    compilado = subprocess.run(
        ["clang", "-O2", "-o", str(APLICATIVO / "Contents" / "MacOS" / "rodar"), str(fonte)],
        capture_output=True, text=True)
    if compilado.returncode != 0:
        print("Não consegui compilar o lançador: %s" % compilado.stderr.strip()[:300])
        print("Instale as ferramentas de linha de comando:  xcode-select --install")
        return 1
    subprocess.run(["codesign", "--force", "--deep", "-s", "-", str(APLICATIVO)],
                   capture_output=True)
    print("Aplicativo criado: %s" % APLICATIVO)
    print("Agora ele precisa entrar em Acesso Total ao Disco — use a opção 9.")
    return 0


def cmd_liberar(args):
    """
    Passo a passo do acesso ao Google Drive para a verificação automática.

    Pelo atalho, quem acessa o Drive é o Terminal, que já tem permissão. Pela
    verificação automática, quem acessa é o aplicativo — e ele precisa ser
    autorizado uma vez.
    """
    config, _log = _preparar()
    if not APLICATIVO.exists():
        cmd_aplicativo(argparse.Namespace(refazer=False))

    print("\n  LIBERAR O GOOGLE DRIVE PARA A VERIFICAÇÃO AUTOMÁTICA")
    print("  " + "─" * 62)
    print("  O macOS protege a pasta do Google Drive e só libera para")
    print("  aplicativos autorizados. O aplicativo é este:\n")
    print("    %s\n" % APLICATIVO)
    print("  1. Vou abrir o Finder (com ele selecionado) e os Ajustes")
    print("  2. Nos Ajustes: Privacidade e Segurança → Acesso Total ao Disco")
    print("  3. ARRASTE o aplicativo do Finder para dentro da lista")
    print("     (ou clique em + e escolha ele)")
    print("  4. Destrave com a digital, se pedir, e deixe a chavinha ligada\n")
    print("  Depois volte aqui: o topo do menu mostra 'última vez sozinha'.\n")

    input("  Enter para abrir as janelas... ")
    for endereco in ("x-apple.systempreferences:com.apple.settings.PrivacySecurity"
                     ".extension?Privacy_AllFiles",
                     "x-apple.systempreferences:com.apple.preference.security"
                     "?Privacy_AllFiles"):
        subprocess.run(["open", endereco], check=False, capture_output=True)
    subprocess.run(["open", "-R", str(APLICATIVO)], check=False)

    bloqueio = config.acesso_a_pasta_clientes()
    if bloqueio:
        print("\n  (Pelo atalho o acesso também está bloqueado agora — isso é "
              "incomum; confira se o Google Drive está aberto.)")
    return 0


# ---------------------------------------------------------------------------
# Agendador (launchd)
# ---------------------------------------------------------------------------

# O agendador chama este roteiro, e não o Python direto. Ele mora FORA do Google
# Drive de propósito: quando o macOS bloqueia o Drive (o Python precisa de Acesso
# Total ao Disco para ler lá), o Python nem consegue abrir o próprio programa e
# morre sem escrever no log — foi o que aconteceu na primeira rodada automática,
# em 17/08/2026. Daqui, o aviso sai de qualquer jeito.
MODELO_RODAR = """#!/bin/sh
# Gerado por 'executar.py agendador --instalar'. Não precisa editar à mão.
PY={python}
PROGRAMA={script}
CASA="$HOME/.baixar-autentique"
LOG="$CASA/logs/agendador.err"
MARCA="$CASA/ultima-rodada-automatica.txt"
ERRO_TEMP="$CASA/logs/.saida-agendador"

"$PY" "$PROGRAMA" rodar --silencioso 2> "$ERRO_TEMP"
CODIGO=$?
QUANDO=$(date "+%d/%m/%Y %H:%M")

if [ "$CODIGO" -eq 0 ]; then
    printf '%s  ok\\n' "$QUANDO" > "$MARCA"
    rm -f "$ERRO_TEMP"
    exit 0
fi

cat "$ERRO_TEMP" >> "$LOG"
if grep -q "Operation not permitted" "$ERRO_TEMP" 2>/dev/null; then
    MOTIVO="o macOS bloqueou o acesso ao Google Drive"
    osascript -e 'display notification "Abra o atalho Baixar Contratos Assinados: ele mostra como liberar, em 4 passos." with title "A verificação automática está bloqueada" sound name "Basso"' >/dev/null 2>&1
else
    MOTIVO="erro na verificação (código $CODIGO)"
    osascript -e 'display notification "Abra o atalho Baixar Contratos Assinados e veja o status." with title "A verificação automática falhou" sound name "Basso"' >/dev/null 2>&1
fi
printf '%s  FALHOU: %s\\n' "$QUANDO" "$MOTIVO" > "$MARCA"
rm -f "$ERRO_TEMP"
exit "$CODIGO"
"""

MODELO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{rotulo}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/open</string>
    <string>-gj</string>
    <string>-a</string>
    <string>{aplicativo}</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
{horarios}  </array>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>{saida}</string>
  <key>StandardErrorPath</key><string>{erro}</string>
  <key>WorkingDirectory</key><string>{pasta}</string>
</dict>
</plist>
"""

ITEM_HORARIO = ("    <dict><key>Hour</key><integer>%d</integer>"
                "<key>Minute</key><integer>%d</integer></dict>\n")


def cmd_agendador(args):
    config, _log = _preparar()
    pasta_agentes = Path.home() / "Library/LaunchAgents"
    plist = pasta_agentes / (ROTULO_AGENDADOR + ".plist")

    if args.remover:
        subprocess.run(["launchctl", "unload", str(plist)], check=False, capture_output=True)
        if plist.exists():
            plist.unlink()
        print("Automático desligado. A busca só acontece quando você clicar no atalho.")
        return 0

    if args.ver:
        saida = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
        linhas = [l for l in saida.stdout.splitlines() if ROTULO_AGENDADOR in l]
        print("\n".join(linhas) if linhas else "O automático não está carregado.")
        return 0

    pasta_agentes.mkdir(parents=True, exist_ok=True)

    # O roteiro fica junto dos dados, fora do Drive (ver comentário no modelo).
    roteiro = config.pasta_dados / "rodar.sh"
    # shlex.quote, e não json.dumps: o caminho tem acento e espaço, e json
    # escaparia o acento como \u0301 — o shell tomaria isso ao pé da letra e
    # não acharia o arquivo. (Mesma pegadinha do AppleScript, em src/aviso.py.)
    roteiro.write_text(MODELO_RODAR.format(
        python=shlex.quote(sys.executable),
        script=shlex.quote(str(AQUI / "executar.py")),
    ), encoding="utf-8")
    os.chmod(str(roteiro), 0o700)

    aplicativo = Path.home() / "Applications" / "Baixar Contratos Assinados.app"
    if not aplicativo.exists():
        print("O aplicativo da verificação automática não existe ainda.")
        print("Rode:  python3 executar.py aplicativo")
        return 1

    horarios = "".join(ITEM_HORARIO % (h, m) for h, m in config.horarios())
    plist.write_text(MODELO_PLIST.format(
        rotulo=ROTULO_AGENDADOR,
        aplicativo=str(aplicativo),
        horarios=horarios,
        saida=str(config.pasta_logs / "agendador.out"),
        erro=str(config.pasta_logs / "agendador.err"),
        pasta=str(config.pasta_dados),
    ), encoding="utf-8")

    subprocess.run(["launchctl", "unload", str(plist)], check=False, capture_output=True)
    carga = subprocess.run(["launchctl", "load", str(plist)], capture_output=True, text=True)
    if carga.returncode != 0:
        print("Não consegui ligar o automático: %s" % (carga.stderr.strip() or "erro desconhecido"))
        return 1

    horas = config.horarios()
    print("Automático ligado: de %02dh às %02dh, de hora em hora (minuto %02d)."
          % (horas[0][0], horas[-1][0], config.minuto))
    print("Contrato assinado por todas as partes cai na pasta do cliente em até 1 hora.")
    return 0


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="comando")

    p = sub.add_parser("rodar", help="verifica o Autentique e arquiva o que estiver pronto")
    p.add_argument("--silencioso", action="store_true", help="sem saída na tela (agendador)")
    p.add_argument("--abrir", action="store_true", help="abre o relatório ao terminar")
    p.set_defaults(func=cmd_rodar, conferir=False)

    p = sub.add_parser("conferir", help="mostra o que seria feito, sem gravar nada")
    p.add_argument("--silencioso", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_rodar, conferir=True, abrir=False)

    p = sub.add_parser("historico", help="traz contratos assinados de antes da automação")
    p.add_argument("--dias", type=int, default=0, help="quantos dias para trás")
    p.add_argument("--sim", action="store_true", help="não perguntar a confirmação")
    p.set_defaults(func=cmd_historico)

    p = sub.add_parser("pendencias", help="atualiza e abre o relatório")
    p.set_defaults(func=cmd_pendencias)

    p = sub.add_parser("status", help="configuração e contagens")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("chave", help="guarda a chave da API do Autentique")
    p.set_defaults(func=cmd_chave)

    p = sub.add_parser("testar", help="confere se a chave funciona")
    p.set_defaults(func=cmd_testar)

    p = sub.add_parser("liberar", help="passo a passo do acesso ao Google Drive")
    p.set_defaults(func=cmd_liberar)

    p = sub.add_parser("aplicativo", help="cria o aplicativo que o agendador chama")
    p.add_argument("--refazer", action="store_true",
                   help="recria mesmo já existindo (derruba a permissão concedida)")
    p.set_defaults(func=cmd_aplicativo)

    p = sub.add_parser("agendador", help="liga/desliga a verificação automática")
    p.add_argument("--instalar", action="store_true")
    p.add_argument("--remover", action="store_true")
    p.add_argument("--ver", action="store_true")
    p.set_defaults(func=cmd_agendador)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        ap.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
