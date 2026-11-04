#!/usr/bin/env python3
"""RADAR B&A — painel de linha de comando.

Use o atalho "RADAR B&A.command" no dia a dia. Este arquivo é o motor.

    python3 executar.py saude
    python3 executar.py gerar-chaves
    python3 executar.py importar carteira.csv
    python3 executar.py clientes
    python3 executar.py monitorar --dias 1
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import ajustes                                    # noqa: E402
from src.provedores.datajud.cliente import ProvedorDataJud        # noqa: E402
from src.provedores.djen.cliente import ProvedorDJEN              # noqa: E402
from src.provedores.esaj.cliente import DOMINIOS, ProvedorESAJ    # noqa: E402
from src.seguranca import cpf as scpf                             # noqa: E402
from src.servicos import carteira, monitor, relatorio             # noqa: E402
from src.servicos import importador_rodagem                       # noqa: E402
from src.servicos import acompanhamento                           # noqa: E402
from src.servicos import varredura_esaj                           # noqa: E402
from src.servicos.classificador_movimentos import URGENTES        # noqa: E402
from src.util.log import obter                                    # noqa: E402

log = obter("cli")


def cmd_saude(args):
    print("Verificando as fontes...\n")
    djen = ProvedorDJEN()
    ok_djen = djen.verificar_saude()
    print("  DJEN (detecção, nacional)        %s" % ("OK" if ok_djen else "INDISPONÍVEL"))
    dj = ProvedorDataJud()
    ok_dj = dj.verificar_saude()
    print("  DataJud (enriquecimento)         %s" % ("OK" if ok_dj else "INDISPONÍVEL"))
    print("  e-SAJ (confirmação por CPF)      %s" %
          ("LIGADO" if ajustes.ESAJ_HABILITADO else "desligado por padrão"))
    if ajustes.ESAJ_HABILITADO:
        for tj in DOMINIOS:
            print("     %-6s %s" % (tj, "OK" if ProvedorESAJ(tj).verificar_saude() else "INDISPONÍVEL"))
    print("\n  Segredos configurados: pepper=%s chave=%s" % (
        "sim" if ajustes.CPF_PEPPER else "NÃO", "sim" if ajustes.CPF_CHAVE else "NÃO"))
    return 0 if (ok_djen and ok_dj) else 1


def cmd_gerar_chaves(args):
    print("Cole estas linhas no arquivo ~/.radar-ba/.env:\n")
    print("CPF_PEPPER=%s" % scpf.gerar_chave()[:32])
    print("CPF_CHAVE=%s" % scpf.gerar_chave())
    print("\nATENÇÃO: se o CPF_PEPPER mudar, todos os hashes já gravados mudam.")
    return 0


def cmd_importar(args):
    novos, problemas = carteira.importar(args.arquivo)
    print("Aceitos: %d" % len(novos))
    for c in novos[:20]:
        print("   + %s" % c["nome"])
    if len(novos) > 20:
        print("   ... e mais %d" % (len(novos) - 20))
    if problemas:
        print("\nRecusados: %d" % len(problemas))
        for p in problemas[:20]:
            print("   - %s" % p)
    if novos and not args.simular:
        total = carteira.acrescentar(novos)
        print("\nCarteira agora com %d cliente(s)." % total)
    elif args.simular:
        print("\n(simulação — nada foi gravado)")
    return 0


def cmd_importar_rodagem(args):
    """Importa a carteira real da planilha RODAGEM PROCESSUAL."""
    print("Lendo %s ...\n" % args.arquivo)
    clientes, problemas, resumo = importador_rodagem.importar_planilha(args.arquivo)

    print("%-24s %-24s %7s %8s %9s" % ("ABA", "SITUAÇÃO", "LINHAS", "ACEITOS", "RECUSADOS"))
    for r in resumo:
        print("%-24s %-24s %7d %8d %9d" % (r["aba"][:23], r["situacao"][:23],
                                           r["linhas"], r["aceitos"], r["recusados"]))
    com_busca = sum(1 for c in clientes if c["tem_busca_na_planilha"])
    print("\nClientes únicos por CPF : %d" % len(clientes))
    print("Já com busca na planilha: %d" % com_busca)
    print("Linhas recusadas        : %d" % len(problemas))
    if problemas and args.detalhar:
        for p in problemas:
            print("   - %s" % p)
    elif problemas:
        for p in problemas[:8]:
            print("   - %s" % p)
        if len(problemas) > 8:
            print("   ... e mais %d (use --detalhar)" % (len(problemas) - 8))

    if args.simular:
        print("\n(simulação — nada foi gravado)")
        return 0
    carteira.gravar(clientes)
    print("\nCarteira gravada com %d cliente(s)." % len(clientes))
    return 0


def cmd_acompanhar(args):
    """Vê o que andou nos processos de Busca e Apreensão já conhecidos."""
    clientes = carteira.ativos()
    processos = acompanhamento.processos_a_acompanhar(clientes)
    if not processos:
        print("Nenhum processo de Busca e Apreensão cadastrado para acompanhar.")
        print("Importe a RODAGEM: python3 executar.py importar-rodagem <arquivo>")
        return 1
    if args.limite:
        # Recorta de verdade: monta clientes só com os processos escolhidos,
        # senão o total consultado não bate com o que é anunciado.
        processos = processos[:args.limite]
        recorte = []
        for numero, c in processos:
            copia = dict(c)
            copia["processos_busca"] = [numero]
            recorte.append(copia)
        clientes = recorte
    djen = ProvedorDJEN()
    if not djen.verificar_saude():
        print("DJEN indisponível agora.")
        return 1

    print("Acompanhando %d processo(s), janela de %d dias.\n"
          "A %d consultas por minuto isso leva cerca de %d minuto(s).\n"
          % (len(processos), args.dias, ajustes.DJEN_RPM,
             max(1, len(processos) // max(ajustes.DJEN_RPM, 1))))

    urgentes = []

    def avisar(registro, cliente):
        marca = "🚨" if registro["urgente"] else "  "
        print("%s %-20s %-26s %-7s %s" % (
            marca, registro["evento"], registro["processo"],
            registro["tribunal"] or "-", (cliente.get("nome") or "")[:30]))
        if registro["urgente"]:
            urgentes.append((registro, cliente))

    novidades, erros = acompanhamento.acompanhar(clientes, djen, dias=args.dias,
                                                 ao_detectar=avisar)
    print("\n" + "=" * 66)
    print("ACOMPANHAMENTO DE BUSCA E APREENSÃO")
    print("=" * 66)
    print("Processos consultados : %d" % len(processos))
    print("Eventos novos         : %d" % len(novidades))
    print("Eventos URGENTES      : %d" % len(urgentes))
    print("Erros                 : %d" % len(erros))
    if urgentes:
        print("\nURGENTES — exigem ação hoje:")
        for r, c in urgentes:
            print("\n  %s · %s" % (r["evento"], r["data"]))
            print("  Cliente : %s (%s)" % (c.get("nome"), c.get("cpf_mascara", "")))
            print("  Processo: %s  %s" % (r["processo"], r["tribunal"] or ""))
            print("  Vara    : %s" % r.get("orgao", ""))
            print("  Trecho  : ...%s..." % r["trecho"][:180])
    for e in erros[:5]:
        print("  erro: %s" % e)
    return 0


def cmd_varrer_esaj(args):
    """Objetivo A: procura busca e apreensão nova por CPF/CNPJ no e-SAJ."""
    if not ajustes.ESAJ_HABILITADO:
        print("A varredura por CPF está DESLIGADA (ESAJ_HABILITADO=false).")
        print("Ligue em ~/.radar-ba/.env apenas após analisar os Termos de Uso.")
        return 1
    clientes = carteira.ativos()
    pares = varredura_esaj.alcancaveis(clientes)
    if args.limite:
        pares = pares[:args.limite]
        clientes = [c for c, _ in pares]
    print("Consultando %d cliente(s) por documento, a 1 a cada %ds "
          "(cerca de %d minuto(s)).\n" % (len(pares), ajustes.ESAJ_INTERVALO_S,
                                          max(1, len(pares) * ajustes.ESAJ_INTERVALO_S // 60)))

    def avisar(registro, cliente, resultado):
        print("✅ %-26s %-7s %-28s %s" % (
            registro["processo"], registro["tribunal"],
            (registro["banco"] or "-")[:26], (cliente.get("nome") or "")[:28]))

    novos, conhecidos, erros = varredura_esaj.varrer(clientes, ao_achar=avisar)
    print("\n" + "=" * 66)
    print("VARREDURA POR CPF/CNPJ NO e-SAJ")
    print("=" * 66)
    print("Clientes consultados : %d" % len(pares))
    print("Processos novos      : %d" % len(novos))
    print("Já conhecidos        : %d" % len(conhecidos))
    print("Erros                : %d" % len(erros))
    for e in erros[:6]:
        print("   %s" % e)
    return 0


def cmd_clientes(args):
    todos = carteira.carregar()
    print("Carteira: %d cliente(s), %d em monitoramento\n" %
          (len(todos), len(carteira.ativos())))
    for c in todos:
        print("  %-16s %-38s %s" % (c["id"], c["nome"][:37],
                                    c.get("banco") or "—"))
    return 0


def cmd_monitorar(args):
    clientes = carteira.ativos()
    if not clientes:
        print("Nenhum cliente em monitoramento. Use: python3 executar.py importar <arquivo>")
        return 1
    djen = ProvedorDJEN()
    indisponiveis = []
    if not djen.verificar_saude():
        print("DJEN indisponível agora — nada a fazer.")
        return 1
    esaj = {}
    if ajustes.ESAJ_HABILITADO:
        for tj in DOMINIOS:
            try:
                esaj[tj] = ProvedorESAJ(tj)
            except ValueError:
                pass
    canal = None
    if getattr(args, "sem_alerta", False):
        import io
        from src.servicos.alertas import CanalConsole
        canal = CanalConsole(saida=io.StringIO())
        print("Carga inicial: registrando o que já existe, sem despejar alerta.\n")
    execucao = monitor.executar(clientes, djen, dias=args.dias, modo=args.modo,
                                esaj_por_tribunal=esaj, canal=canal,
                                usar_prefixo=not getattr(args, "so_nome_completo", False))
    print("\n" + relatorio.montar_texto(execucao, indisponiveis))
    txt, js = relatorio.salvar(execucao, indisponiveis)
    print("\nRelatório salvo em %s" % txt.parent)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="radar", description="RADAR B&A — Caroline Macedo Advocacia")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("saude", help="verifica se as fontes estão respondendo").set_defaults(f=cmd_saude)
    sub.add_parser("gerar-chaves", help="gera pepper e chave de criptografia").set_defaults(f=cmd_gerar_chaves)

    imp = sub.add_parser("importar", help="importa carteira de CSV ou XLSX")
    imp.add_argument("arquivo")
    imp.add_argument("--simular", action="store_true", help="só mostra, não grava")
    imp.set_defaults(f=cmd_importar)

    rod = sub.add_parser("importar-rodagem",
                         help="importa a carteira da planilha RODAGEM PROCESSUAL")
    rod.add_argument("arquivo")
    rod.add_argument("--simular", action="store_true", help="só mostra, não grava")
    rod.add_argument("--detalhar", action="store_true", help="lista todas as recusas")
    rod.set_defaults(f=cmd_importar_rodagem)

    aco = sub.add_parser("acompanhar",
                         help="vê liminar deferida / mandado expedido nos processos conhecidos")
    aco.add_argument("--dias", type=int, default=7, help="janela em dias (padrão 7)")
    aco.add_argument("--limite", type=int, default=0, help="só os N primeiros (teste)")
    aco.set_defaults(f=cmd_acompanhar)

    ves = sub.add_parser("varrer-esaj",
                         help="procura B&A nova por CPF/CNPJ no e-SAJ")
    ves.add_argument("--limite", type=int, default=0, help="só os N primeiros (teste)")
    ves.set_defaults(f=cmd_varrer_esaj)

    sub.add_parser("clientes", help="lista a carteira").set_defaults(f=cmd_clientes)

    mon = sub.add_parser("monitorar", help="roda um ciclo de monitoramento")
    mon.add_argument("--dias", type=int, default=1, help="janela em dias (padrão 1)")
    mon.add_argument("--modo", choices=["nome", "varredura"], default=None)
    mon.add_argument("--so-nome-completo", action="store_true",
                     help="não consulta o prefixo do nome; metade das requisições")
    mon.add_argument("--sem-alerta", action="store_true",
                     help="carga inicial: registra o que existe sem despejar alerta")
    mon.set_defaults(f=cmd_monitorar)

    args = p.parse_args(argv)
    if not getattr(args, "f", None):
        p.print_help()
        return 0
    return args.f(args)


if __name__ == "__main__":
    sys.exit(main())
