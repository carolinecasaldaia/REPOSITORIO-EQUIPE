#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ponto de entrada da automação de cadastro no Astrea.

    python3 executar.py rodar         # rodada normal (é o que o agendador chama)
    python3 executar.py ativar        # marca as pastas atuais como histórico
    python3 executar.py importar      # traz pastas antigas (pede confirmação)
    python3 executar.py analisar      # só lê e mostra; não toca no Astrea
    python3 executar.py pendencias    # atualiza e abre o relatório
    python3 executar.py status        # configuração e contagens
    python3 executar.py calibrar      # remapeia a tela do Astrea
    python3 executar.py agendador --instalar | --remover | --ver
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import time
import sys
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

from src.config.settings import get_config, mascarar_cpf          # noqa: E402
from src.database import controle as St                            # noqa: E402
from src.database.controle import Controle                         # noqa: E402
from src.drive import scanner                                      # noqa: E402
from src.extractors import contrato_ho, documentos as D            # noqa: E402
from src.logs.logger import Log                                    # noqa: E402
from src.services import dashboard, orquestrador, relatorio        # noqa: E402
from src.validators import analise                                 # noqa: E402

ROTULO_AGENDADOR = "com.carolinemacedo.cadastro-astrea"


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def cmd_rodar(args):
    config = get_config()
    log = Log.abrir()
    problemas = config.problemas()
    if problemas:
        for problema in problemas:
            log.erro(problema)
        return 2

    log.titulo("Cadastro automático no Astrea — %s"
               % ("MODO TESTE" if config.test_mode else "PRODUÇÃO"))
    resumo = orquestrador.executar(config, log, modo=orquestrador.MODO_NOVOS,
                                   limite=args.limite)
    destino = relatorio.gerar(config)
    log.info("Relatório atualizado: %s" % destino)

    # Não entrou no Astrea = rodada falhou, e quem chamou precisa saber. O
    # agendador usa o código de saída para avisar na tela; devolver 0 aqui foi
    # o que escondeu cinco horas de login recusado (09/09/2026).
    if getattr(resumo, "sem_acesso", ""):
        if getattr(resumo, "motivo_sem_acesso", "") == "senha":
            log.erro("A rodada terminou SEM ENTRAR no Astrea: a senha foi "
                     "recusada. Guarde a nova pelo atalho (opção 's').")
            return 3
        log.erro("A rodada terminou SEM ENTRAR no Astrea, mas não por senha: "
                 "%s. A próxima rodada tenta de novo." % resumo.sem_acesso)
        return 4

    # Depois de cadastrar quem é novo, confere sozinho no Asaas quem já pagou
    # a entrada e abre caso + tarefas — decisão de 22/09/2026, para não
    # depender mais de ninguém escolher cliente a cliente. Falha aqui não
    # derruba o código de saída da rodada: o cadastro (a parte crítica) já
    # terminou bem: isto é um passo a mais, e tenta de novo sozinho na
    # próxima rodada.
    try:
        abertos, falharam, nao_mexidos, sem_chave = abrir_casos_com_entrada_paga(config, log)
        if sem_chave:
            log.alerta("Checagem de entrada no Asaas não rodou: falta "
                      "ASAAS_API_KEY no .env.")
        if abertos:
            nomes = ", ".join(abertos[:3]) + (" e mais %d" % (len(abertos) - 3)
                                              if len(abertos) > 3 else "")
            subprocess.run(["osascript", "-e",
                            'display notification %s with title "Caso aberto automaticamente"'
                            % _aspas_applescript(nomes)], capture_output=True)
        if nao_mexidos:
            # Caso de outra pessoa, entrada paga, tarefa NENHUMA mexida — isto
            # não é erro, mas ninguém pode deixar de ver: é aviso separado do
            # de "caso aberto", com som, igual aos avisos de falha de senha.
            nomes = ", ".join(nao_mexidos[:3]) + (" e mais %d" % (len(nao_mexidos) - 3)
                                                  if len(nao_mexidos) > 3 else "")
            subprocess.run(["osascript", "-e",
                            'display notification %s with title '
                            '"Confira à mão: caso já existia" sound name "Basso"'
                            % _aspas_applescript(nomes)], capture_output=True)
    except Exception as erro:
        log.erro("Checagem de entrada no Asaas falhou: %s" % erro)

    # Dashboard financeiro (decisão dela, 23/09/2026): atualiza sozinho a
    # cada rodada, junto com o resto. Falha aqui é só um aviso — nunca
    # derruba o código de saída da automação principal.
    try:
        destino_dashboard = dashboard.gerar(config, log)
        log.info("Dashboard financeiro atualizado: %s" % destino_dashboard)
    except Exception as erro:
        log.erro("Dashboard financeiro falhou: %s" % erro)

    return 0


def cmd_ativar(args):
    config = get_config()
    log = Log.abrir()
    with Controle(config.banco) as banco:
        if banco.automacao_ativada() and not args.forcar:
            log.alerta("A automação já foi ativada em %s. Use --forcar para "
                       "redefinir a linha de corte." % banco.marco("ativada_em"))
            return 1
        orquestrador.ativar(config, log, banco)
    return 0


def cmd_importar(args):
    """
    Modo importação: processa pastas que já existiam.

    Exige confirmação explícita justamente para não cadastrar 51 clientes de
    uma vez por acidente.
    """
    config = get_config()
    log = Log.abrir()

    pastas = scanner.varrer(config.pasta_clientes,
                            scanner.meses_aceitos(config.meses))
    historicas = []
    with Controle(config.banco) as banco:
        for pasta in pastas:
            registro = banco.buscar(pasta.drive_id)
            if registro is not None and registro["status"] == St.HISTORICO:
                historicas.append(pasta)

    alvo = args.limite or len(historicas)
    print("\nMODO IMPORTAÇÃO")
    print("  Pastas marcadas como histórico: %d" % len(historicas))
    print("  Serão processadas nesta rodada: %d" % min(alvo, len(historicas)))
    print("  Modo atual: %s" % ("TESTE (nada é gravado)" if config.test_mode
                                else "PRODUÇÃO — VAI CADASTRAR NO ASTREA"))

    if not args.sim:
        resposta = input('\nDigite IMPORTAR para confirmar (ou Enter para sair): ')
        if resposta.strip().upper() != "IMPORTAR":
            print("Cancelado. Nada foi feito.")
            return 1

    log.titulo("Importação de clientes já existentes na pasta")
    orquestrador.executar(config, log, modo=orquestrador.MODO_IMPORTACAO,
                          limite=args.limite)
    destino = relatorio.gerar(config)
    log.info("Relatório atualizado: %s" % destino)
    return 0


def cmd_analisar(args):
    """
    Leitura pura: mostra o que seria extraído, sem tocar em banco nem Astrea.

    É o comando para conferir a extração de um cliente específico.
    """
    config = get_config()
    log = Log.abrir()

    pastas = scanner.varrer(config.pasta_clientes,
                            scanner.meses_aceitos(config.meses))
    if args.pasta:
        alvo = args.pasta.strip().lower()
        pastas = [p for p in pastas if alvo in p.nome_pasta.lower()]
    if args.limite:
        pastas = pastas[:args.limite]

    if not pastas:
        print("Nenhuma pasta encontrada com esse filtro.")
        return 1

    contagem = {}
    for pasta in pastas:
        docs = D.inventariar(pasta.caminho)
        documento = D.escolher_contrato(docs)
        resultado = contrato_ho.extrair(documento.caminho) if documento else None
        ficha = analise.montar(pasta.nome_pasta, pasta.caminho, resultado, docs,
                               config.extrair_corresponsavel)
        if ficha.pessoa is not None:
            analise.analisar(ficha, config.campos_obrigatorios,
                             config.limiar_confianca)

        status = ficha.status or "PRONTO PARA CADASTRAR"
        contagem[status] = contagem.get(status, 0) + 1

        print("\n" + "─" * 72)
        print("%s   [%s]" % (pasta.nome_pasta, pasta.mes or "sem mês"))
        print("  ID da pasta no Drive: %s (%s)" % (pasta.drive_id, pasta.origem_id))
        print("  Status: %s" % status)
        if ficha.detalhe:
            print("  Motivo: %s" % ficha.detalhe)
        if ficha.pessoa is not None:
            for rotulo, valor, confianca in ficha.resumo_para_tela():
                mostrado = mascarar_cpf(valor) if rotulo == "CPF" and not args.completo \
                    else valor
                print("    %-18s %-42s conf %.2f" % (rotulo + ":", mostrado, confianca))
            if ficha.tipo_acao.preenchido:
                print("    %-18s %s" % ("Tipo de ação:", ficha.tipo_acao.valor))
            if ficha.banco_adverso.preenchido:
                print("    %-18s %s" % ("Banco adverso:", ficha.banco_adverso.valor))
        for observacao in ficha.observacoes:
            print("  · %s" % observacao)
        for nao_lido in ficha.nao_interpretados:
            print("  ! DOCUMENTO NÃO INTERPRETADO: %s — %s"
                  % (nao_lido["arquivo"], nao_lido["motivo"]))

    print("\n" + "═" * 72)
    for status, quantos in sorted(contagem.items(), key=lambda x: -x[1]):
        print("  %-28s %d" % (status, quantos))
    print("  %-28s %d" % ("TOTAL", len(pastas)))
    log.info("Análise concluída em %d pasta(s), sem gravar nada." % len(pastas))
    return 0


def cmd_pendencias(args):
    config = get_config()
    destino = relatorio.gerar(config)
    print("Relatório: %s" % destino)
    with Controle(config.banco) as banco:
        precisam = banco.listar(status=list(relatorio.PRECISAM_DE_GENTE), limite=200)
        if not precisam:
            print("\nNada pendente.")
        for registro in precisam:
            print("\n%-24s %s" % (registro["status"],
                                  registro["nome_cliente"] or registro["nome_pasta"]))
            print("  pasta : %s" % registro["nome_pasta"])
            print("  cpf   : %s" % mascarar_cpf(registro["cpf_cnpj"] or ""))
            print("  motivo: %s" % (registro["detalhe"] or registro["erro"] or ""))
    if not args.nao_abrir:
        subprocess.run(["open", str(destino)], check=False)
    return 0


def cmd_dashboard(args):
    """
    Atualiza e abre o dashboard financeiro na hora — sem esperar a próxima
    rodada da automação (que já faz isso sozinha, de hora em hora).
    """
    config = get_config()
    log = Log.abrir()
    destino = dashboard.gerar(config, log)
    print("Dashboard: %s" % destino)
    if not args.nao_abrir:
        subprocess.run(["open", str(destino)], check=False)
    return 0


def cmd_status(args):
    config = get_config()
    print("\nCONFIGURAÇÃO")
    for chave, valor in config.resumo().items():
        print("  %-20s %s" % (chave + ":", valor))
    for problema in config.problemas():
        print("\n  [!] %s" % problema)

    with Controle(config.banco) as banco:
        print("\nCONTROLE")
        print("  %-20s %s" % ("ativada em:", banco.marco("ativada_em") or "ainda não"))
        contagens = banco.contagem_por_status()
        if not contagens:
            print("  (nenhum cliente processado ainda)")
        for status, quantos in contagens:
            print("  %-28s %d" % (status, quantos))

    plist = Path.home() / "Library/LaunchAgents" / (ROTULO_AGENDADOR + ".plist")
    print("\nAGENDADOR")
    print("  %-20s %s" % ("instalado:", "sim" if plist.exists() else "não"))
    if plist.exists():
        print("  %-20s %s" % ("horários:",
                              ", ".join("%02d:%02d" % (h, m)
                                        for h, m in config.horarios)))
    return 0


def _gravar_no_env(chave, valor):
    """
    Escreve/atualiza uma chave no ~/.cadastro-astrea/.env, com permissão 600.

    O arquivo fica FORA do Google Drive de propósito: o Drive sincroniza para a
    nuvem e para outras máquinas, e credencial não deve viajar.
    """
    from src.config.settings import ARQUIVO_ENV, escapar_para_env
    ARQUIVO_ENV.parent.mkdir(parents=True, exist_ok=True)
    linhas = []
    if ARQUIVO_ENV.exists():
        linhas = [l for l in ARQUIVO_ENV.read_text(encoding="utf-8").splitlines()
                  if not l.strip().startswith("%s=" % chave)]
    linhas.append("%s=%s" % (chave, escapar_para_env(valor)))
    ARQUIVO_ENV.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    os.chmod(str(ARQUIVO_ENV), 0o600)


def _remover_do_env(chave):
    """Tira uma chave do ~/.cadastro-astrea/.env (se estiver lá)."""
    from src.config.settings import ARQUIVO_ENV
    if not ARQUIVO_ENV.exists():
        return
    linhas = [l for l in ARQUIVO_ENV.read_text(encoding="utf-8").splitlines()
              if not l.strip().startswith("%s=" % chave)]
    ARQUIVO_ENV.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    os.chmod(str(ARQUIVO_ENV), 0o600)


def _aspas_applescript(texto):
    """
    Texto entre aspas do jeito que o AppleScript entende.

    NÃO usar json.dumps: ele escapa acento como \\u00f3, o AppleScript não
    conhece essa notação e o script inteiro morre com erro de sintaxe — a
    janela simplesmente não abre. Foi o que aconteceu com a janela da senha
    ("só nesta máquina"): a do e-mail, sem acento, funcionava, e a da senha
    não aparecia nunca (18/08/2026). Só a barra invertida e a aspa precisam
    de escape; o resto vai como está, em UTF-8.
    """
    return '"%s"' % str(texto or "").replace("\\", "\\\\").replace('"', '\\"')


def _perguntar_em_janela(mensagem, oculto=False, padrao=""):
    """
    Pede um dado numa janela do macOS, não no terminal.

    A senha vai da janela direto para o arquivo: não passa por variável de
    ambiente, não aparece na tela, não entra em log nem em histórico de shell.
    """
    # O 'activate' traz a janela para a frente. Sem ele a caixa abre atrás das
    # outras janelas e passa despercebida — na primeira tentativa foi
    # exatamente o que aconteceu.
    script = ('activate\n'
              'display dialog %s default answer %s %s with title '
              '"Cadastro Astrea" buttons {"Cancelar", "OK"} default button "OK"'
              % (_aspas_applescript(mensagem), _aspas_applescript(padrao),
                 "with hidden answer" if oculto else ""))
    resultado = subprocess.run(["osascript", "-e", script],
                               capture_output=True, text=True)
    if resultado.returncode != 0:
        return None                                   # cancelou ou fechou
    saida = resultado.stdout.strip()
    marca = "text returned:"
    if marca not in saida:
        return ""
    valor = saida[saida.find(marca) + len(marca):]
    # A saída vem como "button returned:OK, text returned:xxx" ou o contrário.
    if valor.startswith(", "):
        valor = valor[2:]
    for sufixo in (", button returned:OK", ", button returned:Cancelar"):
        if valor.endswith(sufixo):
            valor = valor[:-len(sufixo)]
    return valor


def cmd_senha(args):
    """
    Guarda e-mail e senha do Astrea para a automação entrar sozinha.

    Necessário porque o Astrea só aceita uma sessão por conta: o uso normal do
    sistema durante o dia derruba a sessão salva, e sem a senha a automação não
    consegue voltar sozinha às 06:00 e às 21:00.
    """
    config = get_config()
    # Já vem preenchido: deixar o campo vazio fazia a janela parecer quebrada
    # (clicar OK sem digitar era lido como desistência).
    sugestao = config.astrea_email or os.environ.get("USER_EMAIL", "") or \
        "contato@carolinemacedoadv.com"
    email = _perguntar_em_janela(
        "E-mail da sua conta no Astrea (confira e clique OK):", padrao=sugestao)
    if email is None:
        print("Cancelado na janela do e-mail. Nada foi gravado.")
        return 1
    if not email.strip():
        print("O campo do e-mail ficou vazio — nada foi gravado. "
              "Rode de novo e digite o e-mail.")
        return 1

    senha = _perguntar_em_janela(
        "Senha do Astrea.\n\nEla fica só nesta máquina, guardada no "
        "Porta-chaves do Mac.", oculto=True)
    if senha is None:
        print("Cancelado na janela da senha. Nada foi gravado.")
        return 1
    if not senha:
        print("O campo da senha ficou vazio — nada foi gravado.")
        return 1

    # Porta-chaves desde 29/09/2026 (decisão dela): a senha não fica mais em
    # texto aberto no .env. Se gravar falhar, nada muda no .env.
    from src import porta_chaves
    try:
        porta_chaves.gravar(porta_chaves.SERVICO_ASTREA, email.strip(), senha)
    except porta_chaves.ErroPortaChaves as erro:
        print("Não consegui guardar no Porta-chaves: %s. Nada foi alterado." % erro)
        return 1
    finally:
        del senha
    _gravar_no_env("ASTREA_EMAIL", email.strip())
    _remover_do_env("ASTREA_SENHA")

    print("Senha guardada no Porta-chaves do Mac (serviço 'cadastro-astrea').")
    print("A senha nunca aparece em log, relatório ou tela.")

    if args.testar:
        print("\nTestando a entrada no Astrea...")
        config = get_config(recarregar=True)
        log = Log.abrir()
        from src.astrea.navegador import AdaptadorNavegador
        adaptador = AdaptadorNavegador(config, log, somente_leitura=True)
        try:
            adaptador.conectar()
            print("\n>>> Entrou. A automação já consegue trabalhar sozinha.")
            return 0
        except Exception as erro:
            print("\n>>> NÃO entrou: %s" % str(erro)[:300])
            print("    Confira e-mail e senha e rode de novo.")
            return 1
        finally:
            adaptador.encerrar()
    return 0


def cmd_entrar(args):
    """
    Abre o Chrome no perfil da automação para você entrar no Astrea uma vez.

    Depois disso a sessão fica salva nesse perfil e as rodadas automáticas a
    reaproveitam — sem senha guardada em arquivo nenhum. Quem digita a senha é
    você, na tela do Astrea; a automação não vê e não grava.
    """
    config = get_config()
    log = Log.abrir()
    config.preparar_pastas()

    from src.astrea.navegador import AdaptadorNavegador
    adaptador = AdaptadorNavegador(config, log, somente_leitura=True)
    try:
        try:
            adaptador.conectar(forcar_visivel=True)
            print("\nA sessão já estava válida — não precisa entrar de novo.")
            return 0
        except Exception:
            pass
        entrou = adaptador.entrar_manualmente(espera_segundos=args.espera)
    finally:
        adaptador.encerrar()

    if entrou:
        print("\nSessão salva no perfil da automação (%s)."
              % config.pasta_perfil_chrome)
        print("As próximas rodadas entram sozinhas, sem senha guardada.")
        return 0
    print("\nNão detectei a entrada no Astrea dentro do tempo. Tente de novo.")
    return 1


def cmd_calibrar(args):
    """Remapeia a tela do Astrea. Abre o navegador visível; não cadastra nada."""
    import json
    config = get_config()
    log = Log.abrir()

    from src.astrea.navegador import AdaptadorNavegador
    adaptador = AdaptadorNavegador(config, log, somente_leitura=True)
    try:
        try:
            adaptador.conectar(forcar_visivel=True)
        except Exception as erro:
            print("\nNão consegui entrar no Astrea: %s" % erro)
            print("Rode antes: python3 executar.py entrar")
            return 2
        mapa = adaptador.calibrar()
    finally:
        adaptador.encerrar()

    # Parênteses obrigatórios: sem eles o "/" acontece antes do "%", e o
    # Python tenta formatar um Path — TypeError.
    destino = config.pasta_dados / (
        "calibracao-%s.json" % datetime.now().strftime("%Y%m%d-%H%M"))
    destino.write_text(json.dumps(mapa, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    print("\nMapa da tela salvo em: %s" % destino)
    for tela, conteudo in mapa.items():
        print("\n== %s" % tela)
        if isinstance(conteudo, dict) and conteudo.get("erro"):
            print("   erro: %s" % conteudo["erro"])
            continue
        for campo in (conteudo.get("campos") or [])[:40]:
            print("   campo  rotulo=%-24s placeholder=%-20s name=%s"
                  % (campo.get("rotulo", "")[:24],
                     campo.get("placeholder", "")[:20], campo.get("name", "")))
        for botao in (conteudo.get("botoes") or [])[:20]:
            print("   botão  %s" % botao.get("texto", ""))
    print("\nEnvie este arquivo para quem der manutenção, ou edite "
          "~/.cadastro-astrea/seletores.json com os nomes corretos.")
    return 0


def cmd_prontos(args):
    """
    Lista quem já pode receber a marca "01 - OK -" na pasta.

    Ela pediu (21/08/2026) para ser AVISADA, não para a automação renomear:
    a marca quer dizer "conferido e enviado ao jurídico", e quem confere é ela.
    """
    from src.astrea import prontos as P
    from src.database.controle import Controle
    from src.drive import scanner
    config = get_config(recarregar=True)
    banco = Controle(config.banco)
    registros = P.registros_por_pasta(banco)

    candidatos = []
    for pasta in scanner.varrer(config.pasta_clientes, scanner.meses_aceitos(config.meses)):
        if P.ja_marcada(pasta.nome_pasta):
            continue
        candidatos.append((pasta, registros.get(str(pasta.caminho))))

    if not candidatos:
        print("Nenhuma pasta sem a marca — está tudo em dia.")
        return 0

    # O caso só dá para saber consultando o Astrea; por isso é opcional.
    casos = {}
    if not args.rapido:
        from src.astrea.navegador import AdaptadorNavegador
        log = Log.abrir()
        adaptador = AdaptadorNavegador(config, log, somente_leitura=True)
        try:
            adaptador.conectar()
            for pasta, registro in candidatos:
                contato = (registro or {}).get("astrea_contato_id")
                if not contato:
                    casos[str(pasta.caminho)] = False
                    continue
                adaptador.pagina.goto(
                    "https://astrea.net.br/#/main/contacts/detail/%s/folders" % contato,
                    wait_until="domcontentloaded", timeout=60000)
                adaptador.pagina.wait_for_timeout(6000)
                texto = adaptador.pagina.evaluate("() => document.body.innerText")
                casos[str(pasta.caminho)] = "COMERCIAL - " in texto
        finally:
            adaptador.encerrar()

    prontos, pendentes = [], []
    for pasta, registro in candidatos:
        avaliacao = P.avaliar(pasta.caminho, registro, casos.get(str(pasta.caminho)))
        (prontos if avaliacao["pronto"] else pendentes).append((pasta, avaliacao))

    print("\n  PRONTOS PARA MARCAR \"01 - OK -\" (%d)" % len(prontos))
    print("  " + "-" * 62)
    for pasta, _a in prontos:
        print("   • %s" % pasta.nome_pasta)
    if pendentes:
        print("\n  AINDA FALTA ALGO (%d)" % len(pendentes))
        print("  " + "-" * 62)
        for pasta, avaliacao in pendentes:
            print("   • %-40s falta: %s" % (pasta.nome_pasta[:40], ", ".join(avaliacao["faltas"])))
    print()

    if prontos:
        nomes = ", ".join(p.nome_pasta[:28] for p, _a in prontos[:3])
        if len(prontos) > 3:
            nomes += " e mais %d" % (len(prontos) - 3)
        subprocess.run(["osascript", "-e",
                        'display notification %s with title "Prontos para marcar 01 - OK -"'
                        % _aspas_applescript(nomes)], capture_output=True)
    return 0


def _clientes_aguardando_caso(config, mes_filtro=None):
    """
    Clientes já cadastrados no Astrea cujo caso ainda não foi marcado como
    aberto por esta automação. Não filtra por mês por padrão: a entrada pode
    ser paga muito depois do cadastro, e travar num mês faria cliente antigo
    nunca entrar na checagem.

    Filtra por `config.data_corte_novos_casos` (decisão dela, 23/09/2026):
    só pasta vista pela primeira vez a partir dessa data entra nesta
    automação — nenhum cliente do backlog antigo (46 em 23/09/2026) chega
    até aqui, nem para checar entrada, nem para abrir caso.
    """
    import json as _json
    from src.astrea import casos as C
    from src.database.controle import Controle

    banco = Controle(config.banco)
    try:
        if mes_filtro:
            linhas = banco._conn.execute(
                "select drive_item_id, nome_cliente, nome_pasta, cpf_cnpj,"
                " astrea_contato_id, dados_json, caminho, visto_em from processamentos"
                " where mes_pasta like ? and astrea_contato_id <> '' and visto_em >= ?"
                "   and (status like 'CADASTRADO%' or status like 'JÁ CADASTRADO%')"
                "   and (status_caso is null or status_caso not like 'CASO ABERTO%')"
                " order by nome_cliente",
                (mes_filtro, config.data_corte_novos_casos)).fetchall()
        else:
            linhas = banco._conn.execute(
                "select drive_item_id, nome_cliente, nome_pasta, cpf_cnpj,"
                " astrea_contato_id, dados_json, caminho, visto_em from processamentos"
                " where astrea_contato_id <> '' and visto_em >= ?"
                "   and (status like 'CADASTRADO%' or status like 'JÁ CADASTRADO%')"
                "   and (status_caso is null or status_caso not like 'CASO ABERTO%')"
                " order by nome_cliente",
                (config.data_corte_novos_casos,)).fetchall()
    finally:
        banco.fechar()

    correcoes = C.ler_correcoes_de_tipo()
    pendentes = []
    for l in linhas:
        dados = _json.loads(l["dados_json"] or "{}")
        bruto = dados.get("tipo_acao")
        tipo = C.tipo_do_contrato(bruto.get("valor") if isinstance(bruto, dict) else bruto)
        # Correção manual do tipo (19/10/2026): o contrato de honorários nem
        # sempre descreve o caso que será aberto. Vale mesmo quando o contrato
        # não deu tipo nenhum — é o único jeito de um cliente assim entrar na
        # fila de casos. Ver `casos.ler_correcoes_de_tipo`.
        tipo = C.tipo_corrigido(tipo, l["nome_cliente"], l["nome_pasta"],
                                correcoes=correcoes)
        if not tipo:
            continue
        responsavel = dados.get("corresponsavel") or {}
        cpf_resp = ((responsavel.get("cpf") or {}).get("valor") or "") \
            if (responsavel.get("cpf") or {}).get("valido", True) else ""
        pendentes.append({"drive_item_id": l["drive_item_id"],
                          "cpf_responsavel": cpf_resp,
                          "nome_responsavel": (responsavel.get("nome") or {}).get("valor") or "",
                          "cliente": C.nome_no_padrao(l["nome_cliente"]),
                          "nome_cliente_bruto": l["nome_cliente"],
                          "nome_pasta": l["nome_pasta"],
                          "visto_em": l["visto_em"] or "",
                          "cpf_cnpj": l["cpf_cnpj"],
                          "id": l["astrea_contato_id"], "tipo": tipo,
                          "pasta": l["caminho"]})
    return pendentes


def _so_digitos(texto):
    return "".join(c for c in (texto or "") if c.isdigit())


def _cpfs_de_contratantes(config):
    """CPF/CNPJ de todo contratante que a automação já viu (qualquer mês)."""
    from src.database.controle import Controle
    banco = Controle(config.banco)
    try:
        linhas = banco._conn.execute(
            "select cpf_cnpj from processamentos where coalesce(cpf_cnpj,'') <> ''").fetchall()
    finally:
        banco.fechar()
    return {_so_digitos(l["cpf_cnpj"]) for l in linhas}


def _total_do_contrato(pasta):
    """Valor total dos honorários lido do contrato assinado (0 se não der)."""
    from src.extractors import contrato_ho
    if not pasta:
        return 0.0
    try:
        pdfs = list(Path(pasta).rglob("Contrato HO Assinado.pdf"))
        if not pdfs:
            return 0.0
        return float(contrato_ho.extrair(pdfs[0]).valor_total_honorarios.valor or 0)
    except Exception:
        return 0.0


def _cobranca_paga(cpf, item, config, log):
    """
    Entrada paga; na falta dela, pagamento à vista que quite o contrato.

    A descrição "ENTRADA" continua sendo o caminho normal. O à vista entra só
    depois, e exige o valor total do contrato para comparar — ver
    `asaas.pagamento_quitado`.
    """
    from src import asaas
    cobranca = asaas.entrada_paga(cpf, config.asaas_api_key,
                                  config.asaas_texto_entrada)
    if cobranca:
        return cobranca
    total = _total_do_contrato(item.get("pasta"))
    if not total:
        return None
    cobranca = asaas.pagamento_quitado(cpf, config.asaas_api_key, total)
    if cobranca:
        log.info("Pagamento à vista de %s: R$ %s quitando contrato de R$ %.2f "
                 "(cobrança '%s')."
                 % (item["cliente"], cobranca.get("value"), total,
                    (cobranca.get("description") or "")[:60]))
    return cobranca


ARQUIVO_OUTRO_CADASTRO = Path(__file__).resolve().parent / \
    "PAGAMENTO EM OUTRO CADASTRO DO ASAAS.txt"


def _cadastro_asaas_indicado(item):
    """
    Id do cadastro do Asaas (cus_...) onde a entrada deste cliente foi
    cobrada, quando ela indicou na lista. "" se o cliente não está na lista.
    Mesmo formato da lista de liberações: NOME = cus_... # observação.
    """
    from src.validators.documentacao import _normal
    try:
        linhas = ARQUIVO_OUTRO_CADASTRO.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    nomes = {_normal(n) for n in (item.get("cliente"), item.get("nome_pasta"),
                                  item.get("nome_cliente_bruto")) if n}
    for linha in linhas:
        linha = linha.split("#", 1)[0].strip()
        if "=" not in linha:
            continue
        quem, cadastro = (parte.strip() for parte in linha.split("=", 1))
        if _normal(quem) in nomes and cadastro.startswith("cus_"):
            return cadastro
    return ""


def _entrada_do_cliente(item, config, log, cpfs_de_clientes):
    """
    Cobrança de ENTRADA paga do cliente: primeiro pelo CPF do contratante;
    se não achar, pelo CPF do cliente responsável do contrato.

    Decisão dela (29/09/2026), depois do Adonias: o comercial cadastrou no
    Asaas "ADONIAS ESTEVAM DA SILVA" com o CPF do responsável (Jeremias),
    que é quem paga — a entrada estava paga desde 23/09 e o caso não abria.

    O CPF do responsável só vale se ele NÃO for contratante de outra pasta:
    senão a entrada que ele pagou pelo próprio caso abriria o caso de outra
    pessoa. Nesse caso não decide sozinha — avisa para conferir à mão.
    """
    from src import asaas
    cobranca = _cobranca_paga(item["cpf_cnpj"], item, config, log)
    if cobranca:
        return cobranca

    # Entrada cobrada em outro cadastro do Asaas, indicado por ela na lista
    # (26/10/2026: Izabel, cobrada num cadastro com o CPF do irmão Jair).
    cadastro = _cadastro_asaas_indicado(item)
    if cadastro:
        cobranca = asaas.entrada_paga(cadastro, config.asaas_api_key,
                                      config.asaas_texto_entrada)
        if cobranca:
            log.info("Entrada de %s encontrada no cadastro do Asaas indicado na "
                     "lista (%s)." % (item["cliente"], cadastro))
            return cobranca

    cpf_resp = _so_digitos(item.get("cpf_responsavel"))
    if not cpf_resp or cpf_resp == _so_digitos(item["cpf_cnpj"]):
        return None
    if cpf_resp in cpfs_de_clientes:
        cobranca_resp = _cobranca_paga(cpf_resp, item, config, log)
        if cobranca_resp:
            log.alerta("Entrada paga no CPF do responsável %s, mas ele também é "
                       "contratante de outra pasta — NÃO abri o caso de %s. Confira "
                       "a quem é essa entrada (%s)."
                       % (item.get("nome_responsavel") or "?", item["cliente"],
                          (cobranca_resp.get("description") or "")[:120]))
        return None

    cobranca = _cobranca_paga(cpf_resp, item, config, log)
    if cobranca:
        log.info("Entrada de %s encontrada no CPF do responsável do contrato (%s)."
                 % (item["cliente"], item.get("nome_responsavel") or "?"))
    return cobranca


def _barrar_documentacao_incompleta(pendentes, config, log):
    """
    Trava de documentação (decisão dela, 25/09/2026) antes do caso e da
    cópia para o jurídico: cliente cadastrado cuja pasta ainda não tem RG/CNH,
    comprovante de residência e (veículo) CRLV não tem caso
    aberto nem pasta copiada, mesmo com a entrada paga.

    Tem que ser aqui, e não só na cópia: a cópia acontece na mesma volta em
    que o caso é aberto, e caso aberto sai da fila — travar só a cópia faria
    a pasta nunca mais ser copiada. Barrando antes, o cliente continua na
    fila e a rodada seguinte (com a pasta completa) faz tudo de uma vez.
    """
    from src.database.controle import Controle
    from src.validators import documentacao

    liberacoes = documentacao.ler_liberacoes()
    liberados, barrados = [], []
    for item in pendentes:
        faltando = documentacao.faltantes(item["pasta"], item["tipo"])
        motivo = documentacao.liberado(item.get("nome_cliente_bruto", ""),
                                       item["cliente"],
                                       item.get("nome_pasta", ""),
                                       liberacoes=liberacoes)
        if faltando and motivo:
            log.alerta("Caso de %s aberto com documentação incompleta, por "
                       "decisão dela (%s) — falta: %s"
                       % (item["cliente"], motivo, ", ".join(faltando)))
            faltando = []
        if faltando:
            barrados.append((item, faltando))
        else:
            liberados.append(item)
    if not barrados:
        return liberados

    banco = Controle(config.banco)
    try:
        for item, faltando in barrados:
            banco.atualizar_status_caso(
                item["drive_item_id"],
                "CASO NÃO ABERTO — DOCUMENTAÇÃO INCOMPLETA (falta: %s)"
                % ", ".join(faltando))
            log.alerta("Caso NÃO aberto e pasta NÃO copiada para o jurídico: %s — %s"
                       % (item["cliente"], documentacao.mensagem(faltando)))
    finally:
        banco.fechar()
    return liberados


def abrir_casos_com_entrada_paga(config, log, mes_filtro=None, avisar=None):
    """
    Mesma trava de execução do cadastro (execucao.lock). Até 29/09/2026 esta
    etapa rodava fora dela: um roteiro avulso (ex.: abrir caso de quem pagou
    pelo Conta Azul) podia usar o mesmo perfil do Chrome ao mesmo tempo que a
    rodada das :40. Com a trava ocupada, a etapa desta hora é pulada — o
    cliente continua na fila e a rodada seguinte confere de novo.
    """
    from src.database.controle import ExecucaoJaEmAndamento, TravaDeExecucao
    try:
        trava = TravaDeExecucao(config.pasta_dados / "execucao.lock")
        trava.__enter__()
    except ExecucaoJaEmAndamento as erro:
        log.alerta("Abertura de casos pulada nesta rodada: %s A próxima rodada "
                   "confere de novo." % erro)
        return [], [], [], False
    try:
        return _abrir_casos_com_entrada_paga(config, log, mes_filtro, avisar)
    finally:
        trava.__exit__(None, None, None)


def _abrir_casos_com_entrada_paga(config, log, mes_filtro=None, avisar=None):
    """
    Confere no Asaas, por CPF/CNPJ, quem já pagou a ENTRADA e abre caso +
    tarefas no Astrea sozinho — sem perguntar nada (decisão do escritório,
    22/09/2026). Substitui a escolha manual que existia antes.

    Devolve (abertos, falharam, nao_mexidos, sem_chave). `sem_chave` True
    significa que ASAAS_API_KEY não está configurada — impedimento, não
    "ninguém pagou". `nao_mexidos` são casos que já existiam por conta de
    alguém da equipe (não da automação): a entrada foi confirmada, mas
    NENHUMA tarefa foi tocada — ver `src/astrea/casos.abrir_lote`. Precisam
    de conferência manual.
    """
    from src import asaas
    from src.astrea import casos as C
    from src.extractors import contrato_ho
    from src.database.controle import Controle

    def conta(texto):
        if avisar:
            avisar(texto)
        log.info(texto)

    if not config.asaas_api_key:
        log.erro("ASAAS_API_KEY não configurada — não dá para conferir a "
                 "entrada automaticamente.")
        return [], [], [], True

    pendentes = _clientes_aguardando_caso(config, mes_filtro)
    pendentes = _barrar_documentacao_incompleta(pendentes, config, log)
    if not pendentes:
        conta("Nenhum cliente aguardando abertura de caso.")
        return [], [], [], False

    cpfs_de_clientes = _cpfs_de_contratantes(config)
    pagos = []
    for item in pendentes:
        try:
            cobranca = _entrada_do_cliente(item, config, log, cpfs_de_clientes)
        except asaas.ErroAsaas as erro:
            # Falha ao falar com o Asaas é sistêmica (chave errada, rede fora)
            # — não dá para saber quem pagou, então não abre caso nenhum nesta
            # rodada em vez de arriscar decidir errado. A próxima rodada tenta
            # de novo sozinha.
            log.erro("Não consegui consultar o Asaas: %s" % erro)
            return [], [], [], False
        if cobranca:
            item["cobranca_id"] = cobranca.get("id", "")
            pagos.append(item)

    if not pagos:
        conta("Nenhuma entrada nova confirmada no Asaas.")
        return [], [], [], False

    conta("Entrada confirmada no Asaas para: %s"
         % ", ".join(p["cliente"] for p in pagos))

    if config.test_mode:
        # Mesma trava de TEST_MODE do cadastro de contato: com ele ligado, a
        # automação PODE consultar o Asaas de verdade (é só leitura), mas
        # NUNCA abre o navegador nem grava status_caso — senão ligar
        # TEST_MODE pra testar outra coisa abriria caso de verdade no Astrea.
        conta("[TEST MODE] CASO SERIA ABERTO para: %s"
             % ", ".join(p["cliente"] for p in pagos))
        return [], [], [], False

    banco = Controle(config.banco)
    hoje = datetime.now().strftime("%d/%m/%Y")
    from src.validators import parceiro
    do_parceiro = []
    for item in pagos:
        pdfs = list(Path(item["pasta"]).rglob("Contrato HO Assinado.pdf"))
        if not pdfs:
            continue
        resultado = contrato_ho.extrair(pdfs[0])
        item["descricao"] = resultado.objeto.valor or ""
        # Segunda trava do assunto do parceiro (02/10/2026). A primeira está
        # no cadastro, que nem chega aqui; esta pega quem já estava cadastrado
        # ANTES da regra existir — caso contrário a entrada paga abriria o
        # caso de um cliente que é do parceiro.
        if parceiro.e_do_parceiro(item["descricao"]):
            do_parceiro.append(item)
            banco.atualizar_status_caso(item["drive_item_id"],
                                        parceiro.motivo(item["descricao"]))
            conta("Caso NÃO aberto (assunto do parceiro): %s" % item["cliente"])
            continue
        if resultado.apreensao:
            item["apreendido"] = True
            item["observacao"] = C.observacao_de_apreensao(
                resultado.apreensao["estado"], resultado.apreensao["data"],
                resultado.apreensao["processo"])

    pagos = [item for item in pagos if item not in do_parceiro]
    if not pagos:
        banco.fechar()
        return [], [], [], False

    from src.astrea.navegador import AdaptadorNavegador
    adaptador = AdaptadorNavegador(config, log, somente_leitura=False)
    adaptador.conectar()
    abertos, falharam, nao_mexidos = [], [], []
    try:
        # Duas voltas: todos os casos primeiro, tarefas depois. Ver abrir_lote.
        resultados = C.abrir_lote(adaptador.pagina, pagos, hoje, avisar=conta)
        for item, linha in zip(pagos, resultados):
            if linha.get("bloqueado_historico"):
                nao_mexidos.append(item["cliente"])
                banco.atualizar_status_caso(
                    item["drive_item_id"],
                    "CASO NÃO ABERTO (cliente já tem processo/caso anterior) — "
                    "CONFERIR MANUALMENTE")
                # A automação não decide sozinha se é a mesma matéria (mesmo
                # contrato, mesmo veículo) ou o cliente voltando a comprar do
                # escritório — regra dela, 23/09/2026: "se houver dúvidas,
                # sempre questionar". O alerta traz os dois lados (contrato
                # novo x o que já existe) para a decisão ser manual, rápida
                # e sem precisar abrir o Astrea antes.
                log.alerta(
                    "NÃO abri caso para %s: já tem processo/caso anterior no Astrea. "
                    "Confira se é a MESMA matéria (mesmo contrato/veículo) ou se o "
                    "cliente voltou a comprar do escritório.\n"
                    "  Contrato de hoje: %s\n"
                    "  Já existe no Astrea:\n%s"
                    % (linha["cliente"], item.get("descricao", "(sem descrição extraída)"),
                       linha.get("processos_e_casos_anteriores", "") or "(não consegui ler)"))
            elif linha.get("nao_mexido"):
                nao_mexidos.append(item["cliente"])
                criador = linha.get("criado_por", "?")
                banco.atualizar_status_caso(
                    item["drive_item_id"],
                    "CASO JÁ EXISTIA (criado por %s) — CONFERIR MANUALMENTE" % criador)
                log.alerta("Caso de %s já existia, criado por %s (não é a automação) — "
                           "NÃO mexi em tarefa nenhuma. Confira manualmente se falta "
                           "abrir algo." % (linha["cliente"], criador))
            elif linha["falhas"]:
                falharam.append(item["cliente"])
                banco.atualizar_status_caso(
                    item["drive_item_id"],
                    "CASO PENDENTE: %s" % ", ".join(t for t, _ in linha["falhas"]))
                log.alerta("Caso de %s: %d tarefa(s) aberta(s), pendente(s): %s"
                           % (linha["cliente"], len(linha["tarefas"]),
                              ", ".join(t for t, _ in linha["falhas"])))
            else:
                abertos.append(item["cliente"])
                banco.atualizar_status_caso(item["drive_item_id"], "CASO ABERTO (via Asaas)")
                log.ok("Caso e tarefas abertos: %s (%d tarefas)"
                       % (linha["cliente"], len(linha["tarefas"])))
                # Entrada paga, contato cadastrado, caso aberto: última etapa
                # da esteira (decisão dela, 23/09/2026) é copiar a pasta do
                # cliente para a área que vai trabalhar o caso de fato, e
                # marcar a pasta de origem como "OK -". `item` só chega até
                # aqui se já passou pelo corte de data em
                # `_clientes_aguardando_caso` — não precisa checar de novo.
                try:
                    from src.services import copia
                    copiou = copia.copiar_para_area(
                        item["pasta"], item.get("nome_pasta", ""),
                        item.get("nome_cliente_bruto", item["cliente"]),
                        item["tipo"], config, log)
                    if copiou:
                        novo = copia.marcar_pasta_ok(item["pasta"])
                        if str(novo) != str(item["pasta"]):
                            log.ok("Pasta de %s marcada como OK em "
                                  "PREPARAÇÃO PARA INGRESSO." % linha["cliente"])
                except Exception as erro:
                    log.alerta("Falha ao copiar/marcar a pasta de %s: %s"
                              % (linha["cliente"], erro))
    finally:
        adaptador.encerrar()
        banco.fechar()
    return abertos, falharam, nao_mexidos, False


def cmd_casos(args):
    """
    Abre caso + tarefas no Astrea de quem teve a ENTRADA paga.

    A confirmação de pagamento vem da API do Asaas (chave em
    ~/.cadastro-astrea/.env), não mais de escolha manual — é a mesma checagem
    que já roda sozinha dentro de 'executar.py rodar'. Este comando existe
    para rodar na hora, sem esperar o próximo horário agendado.
    """
    config = get_config(recarregar=True)
    log = Log.abrir()
    abertos, falharam, nao_mexidos, sem_chave = abrir_casos_com_entrada_paga(
        config, log, mes_filtro=args.mes, avisar=print)
    if sem_chave:
        return 2
    if nao_mexidos:
        print("\n  ATENÇÃO — caso(s) que já existiam, criados por outra pessoa,")
        print("  entrada confirmada mas NENHUMA tarefa mexida (confira à mão):")
        for nome in nao_mexidos:
            print("   • %s" % nome)
    return 1 if falharam else 0


# ---------------------------------------------------------------------------
# Aplicativo que o agendador chama
# ---------------------------------------------------------------------------

APLICATIVO = Path.home() / "Applications" / "Cadastrar Clientes no Astrea.app"

INFO_PLIST_APP = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Cadastrar Clientes no Astrea</string>
  <key>CFBundleDisplayName</key><string>Cadastrar Clientes no Astrea</string>
  <key>CFBundleIdentifier</key><string>com.carolinemacedo.cadastro-astrea.app</string>
  <key>CFBundleExecutable</key><string>rodar</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSBackgroundOnly</key><true/>
  <key>NSDocumentsFolderUsageDescription</key><string>Ler os contratos assinados na pasta do cliente, no Google Drive.</string>
  <key>NSDesktopFolderUsageDescription</key><string>Ler as pastas de clientes.</string>
</dict>
</plist>
"""

MODELO_RODAR = """#!/bin/sh
# Gerado por 'executar.py agendador --instalar'. Não precisa editar à mão.
PY={python}
PROGRAMA={script}
CASA="$HOME/.cadastro-astrea"
LOG="$CASA/logs/agendador.err"
MARCA="$CASA/ultima-rodada-automatica.txt"
ERRO_TEMP="$CASA/logs/.saida-agendador"

mkdir -p "$CASA/logs"
"$PY" "$PROGRAMA" rodar 2> "$ERRO_TEMP"
CODIGO=$?

# Painel Comercial Contratos (23/10/2026): pega carona nesta rodada, que já
# tem permissão de ler o Drive, e regrava painel-comercial-dados.json. Falha
# aqui não muda o resultado do cadastro.
PAINEL='/Users/carolinemacedo/Library/CloudStorage/GoogleDrive-contato@carolinemacedoadv.com/Meu Drive/Documentos Escritório /EMPRESA/FINANCEIRO/PAINEL COMERCIAL/gerar_dados_painel.py'
"$PY" "$PAINEL" >> "$CASA/logs/painel-comercial.log" 2>&1 || \\
    printf '%s  painel falhou\\n' "$(date '+%d/%m/%Y %H:%M')" >> "$CASA/logs/painel-comercial.log"
QUANDO=$(date "+%d/%m/%Y %H:%M")

if [ "$CODIGO" -eq 0 ]; then
    printf '%s  ok\\n' "$QUANDO" > "$MARCA"
    rm -f "$ERRO_TEMP"
    exit 0
fi

cat "$ERRO_TEMP" >> "$LOG"
if grep -q "Operation not permitted" "$ERRO_TEMP" 2>/dev/null; then
    osascript -e 'display notification "Abra o atalho Cadastrar Clientes: a opção 9 mostra como liberar." with title "O cadastro automático está bloqueado" sound name "Basso"' >/dev/null 2>&1
else
    osascript -e 'display notification "Abra o atalho Cadastrar Clientes e veja o status." with title "O cadastro automático falhou" sound name "Basso"' >/dev/null 2>&1
fi
printf '%s  falhou (codigo %s)\\n' "$QUANDO" "$CODIGO" > "$MARCA"
exit "$CODIGO"
"""


def cmd_aplicativo(args):
    """
    Cria o aplicativo que o agendador chama.

    A pasta do Google Drive (~/Library/CloudStorage) só é liberada para
    APLICATIVOS autorizados: o Python chamado direto pelo agendador é barrado
    mesmo com Acesso Total ao Disco. E o executável do aplicativo precisa ser
    compilado — com um roteiro de shell a permissão vai para o /bin/sh e a
    autorização não vale nada. As duas coisas foram medidas em 18/08/2026, no
    projeto BAIXAR AUTENTIQUE, e valem igual aqui.
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
    print("Agora ele precisa entrar em Acesso Total ao Disco.")
    return 0


# ---------------------------------------------------------------------------
# Agendador (launchd)
# ---------------------------------------------------------------------------

PLIST = """<?xml version="1.0" encoding="UTF-8"?>
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
    config = get_config()
    pasta_agentes = Path.home() / "Library/LaunchAgents"
    plist = pasta_agentes / (ROTULO_AGENDADOR + ".plist")

    if args.remover:
        subprocess.run(["launchctl", "unload", str(plist)], check=False,
                       capture_output=True)
        if plist.exists():
            plist.unlink()
        print("Agendador removido. A automação não roda mais sozinha.")
        return 0

    if args.ver:
        saida = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
        linhas = [l for l in saida.stdout.splitlines() if ROTULO_AGENDADOR in l]
        print("\n".join(linhas) if linhas else "Agendador não está carregado.")
        return 0

    pasta_agentes.mkdir(parents=True, exist_ok=True)
    config.preparar_pastas()

    # O agendador chama o APLICATIVO, nunca o python direto: python lançado
    # pelo launchd não enxerga o Google Drive, por mais permissão que tenha.
    if not APLICATIVO.exists():
        class _Args(object):
            refazer = False
        if cmd_aplicativo(_Args()) != 0:
            return 1

    roteiro = Path.home() / ".cadastro-astrea" / "rodar.sh"
    roteiro.parent.mkdir(parents=True, exist_ok=True)
    roteiro.write_text(MODELO_RODAR.format(
        python=shlex.quote(sys.executable),
        script=shlex.quote(str(AQUI / "executar.py"))), encoding="utf-8")
    roteiro.chmod(0o755)

    conteudo = PLIST.format(
        rotulo=ROTULO_AGENDADOR,
        aplicativo=str(APLICATIVO),
        horarios="".join(ITEM_HORARIO % (h, m) for h, m in config.horarios),
        saida=str(config.pasta_logs / "agendador.out"),
        erro=str(config.pasta_logs / "agendador.err"),
        pasta=str(AQUI))
    plist.write_text(conteudo, encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(plist)], check=False,
                   capture_output=True)
    resultado = subprocess.run(["launchctl", "load", str(plist)],
                               capture_output=True, text=True)
    if resultado.returncode != 0:
        print("Não foi possível carregar o agendador: %s" % resultado.stderr.strip())
        return 1
    horas = ", ".join("%02d:%02d" % (h, m) for h, m in config.horarios)
    print("Agendador instalado. A automação vai verificar a pasta sozinha às "
          "%s." % horas)
    # O aviso de "não rode durante o expediente" valia enquanto a automação
    # entrava com a conta DELA. Desde 08/09/2026 o Claude tem login próprio no
    # Astrea, então rodar de hora em hora não derruba mais a sessão dela.
    print("O Claude usa o login próprio dele no Astrea — rodar durante o "
          "expediente não derruba a sua sessão.")
    print("")
    print("FALTA UM PASSO, e sem ele o agendador não enxerga o Google Drive:")
    print("  Ajustes do Sistema > Privacidade e Segurança > Acesso Total ao Disco")
    print("  e adicione:  %s" % APLICATIVO)
    print("Depois de autorizar, NÃO refaça o aplicativo: a assinatura muda e a")
    print("permissão cai junto.")
    print("Para desligar: python3 executar.py agendador --remover")
    return 0


# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Cadastro automático de clientes no Astrea.")
    sub = parser.add_subparsers(dest="comando")

    p = sub.add_parser("rodar", help="rodada normal (só clientes novos)")
    p.add_argument("--limite", type=int, default=None)
    p.set_defaults(func=cmd_rodar)

    p = sub.add_parser("ativar", help="marca as pastas atuais como histórico")
    p.add_argument("--forcar", action="store_true")
    p.set_defaults(func=cmd_ativar)

    p = sub.add_parser("importar", help="processa pastas antigas (com confirmação)")
    p.add_argument("--limite", type=int, default=None)
    p.add_argument("--sim", action="store_true", help="pula a confirmação")
    p.set_defaults(func=cmd_importar)

    p = sub.add_parser("analisar", help="só lê e mostra; não grava nada")
    p.add_argument("pasta", nargs="?", default=None,
                   help="parte do nome da pasta do cliente")
    p.add_argument("--limite", type=int, default=None)
    p.add_argument("--completo", action="store_true",
                   help="mostra o CPF inteiro (padrão é mascarado)")
    p.set_defaults(func=cmd_analisar)

    p = sub.add_parser("pendencias", help="atualiza e abre o relatório")
    p.add_argument("--nao-abrir", action="store_true")
    p.set_defaults(func=cmd_pendencias)

    p = sub.add_parser("dashboard", help="atualiza e abre o dashboard financeiro")
    p.add_argument("--nao-abrir", action="store_true")
    p.set_defaults(func=cmd_dashboard)

    p = sub.add_parser("status", help="configuração e contagens")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("senha", help="guardar e-mail e senha do Astrea (janela)")
    p.add_argument("--testar", action="store_true", default=True)
    p.add_argument("--sem-testar", dest="testar", action="store_false")
    p.set_defaults(func=cmd_senha)

    p = sub.add_parser("entrar", help="entrar no Astrea uma vez, à mão (sem "
                                      "guardar senha)")
    p.add_argument("--espera", type=int, default=300,
                   help="segundos de espera pela sua entrada (padrão 300)")
    p.set_defaults(func=cmd_entrar)

    p = sub.add_parser("calibrar", help="remapeia a tela do Astrea")
    p.set_defaults(func=cmd_calibrar)

    p = sub.add_parser("aplicativo",
                       help="cria o aplicativo que o agendador chama")
    p.add_argument("--refazer", action="store_true",
                   help="refaz do zero (CUIDADO: derruba a permissão já dada)")
    p.set_defaults(func=cmd_aplicativo)

    p = sub.add_parser("prontos", help="quem já pode receber a marca 01 - OK - na pasta")
    p.add_argument("--rapido", action="store_true",
                   help="não consulta o Astrea (não confere se o caso foi aberto)")
    p.set_defaults(func=cmd_prontos)

    p = sub.add_parser("casos", help="confere entrada no Asaas e abre caso/tarefas de quem pagou")
    p.add_argument("--mes", help="filtro do mês da pasta (padrão: todos os meses)")
    p.set_defaults(func=cmd_casos)

    p = sub.add_parser("agendador", help="liga/desliga a execução automática")
    p.add_argument("--instalar", action="store_true")
    p.add_argument("--remover", action="store_true")
    p.add_argument("--ver", action="store_true")
    p.set_defaults(func=cmd_agendador)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrompido.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
