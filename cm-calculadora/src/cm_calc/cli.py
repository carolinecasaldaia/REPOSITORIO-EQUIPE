"""Linha de comando: cm-calc <comando> ...

  importar  CASO ARQ...         copia documentos para a pasta do caso (somente leitura + hash)
  extrair   CASO                lê, classifica, extrai e grava o quadro de parâmetros
  quadro    CASO                imprime o quadro em Markdown
  confirmar CASO PARAM --por NOME [--valor V] [--detalhe chave=valor ...]
  rejeitar  CASO PARAM --por NOME --motivo TEXTO
  pagamentos CASO --por NOME     confirma a lista de pagamentos
  ciencia   CASO OCORRENCIA --por NOME
  status    CASO                pendências que bloqueiam o cálculo
  pacote    CASO --por NOME --finalidade TEXTO --itens ID [ID...]
                                grava pacote pseudonimizado para leitura autorizada pelo Claude
  validacao preparar|verificar|executar ID [--anonimizacao-confirmada-por NOME]
                                validação pericial (Fase 5)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .casos import Caso
from .extracao import aprovacao as ap
from .extracao.quadro import montar_quadro
from .extracao.relatorio import quadro_markdown
from .privacidade.pacote import Autorizacao, gravar_pacote, montar_pacote


def main(argv: list[str] | None = None) -> int:
    pr = argparse.ArgumentParser(prog="cm-calc", description="CM | Calculadora Judicial Bancária")
    sub = pr.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("importar"); s.add_argument("caso"); s.add_argument("arquivos", nargs="+", type=Path)
    s = sub.add_parser("extrair"); s.add_argument("caso")
    s = sub.add_parser("quadro"); s.add_argument("caso")
    s = sub.add_parser("confirmar"); s.add_argument("caso"); s.add_argument("param"); s.add_argument("--por", required=True)
    s.add_argument("--valor"); s.add_argument("--detalhe", action="append", default=[]); s.add_argument("--obs")
    s = sub.add_parser("rejeitar"); s.add_argument("caso"); s.add_argument("param"); s.add_argument("--por", required=True)
    s.add_argument("--motivo", required=True)
    s = sub.add_parser("pagamentos"); s.add_argument("caso"); s.add_argument("--por", required=True)
    s = sub.add_parser("ciencia"); s.add_argument("caso"); s.add_argument("ocorrencia"); s.add_argument("--por", required=True)
    s = sub.add_parser("status"); s.add_argument("caso")
    s = sub.add_parser("pacote"); s.add_argument("caso"); s.add_argument("--por", required=True)
    s.add_argument("--finalidade", required=True); s.add_argument("--itens", nargs="+", required=True)
    s = sub.add_parser("validacao")
    s.add_argument("acao", choices=["preparar", "ficticio", "importar-original", "termos", "anonimizar",
                                    "abrir-conferencia", "listar-anonimizados", "liberar", "revogar", "verificar", "executar",
                                    "diagnosticar-imagens"])
    s.add_argument("--sha256"); s.add_argument("--motivo")
    s.add_argument("caso", metavar="ID"); s.add_argument("arquivo", nargs="?")
    s.add_argument("--anonimizacao-confirmada-por"); s.add_argument("--como", choices=["parecer", "documento"])
    s.add_argument("--por"); s.add_argument("--apesar-de")
    s.add_argument("--adicionar", help="termos a remover, separados por ponto e vírgula")
    s.add_argument("--remover-imagens-grandes", action="store_true",
                   help="remove também imagens grandes (possíveis gráficos/tabelas) — só após conferi-las")
    s.add_argument("--confirmo-conferencia", action="store_true",
                   help="declaração expressa de que a cópia foi conferida (exigida para liberar)")
    a = pr.parse_args(argv)

    if a.cmd == "validacao":
        try:
            return _validacao(a)
        except (PermissionError, FileNotFoundError, ValueError) as e:
            print(f"Recusado: {e}", file=sys.stderr)
            return 2
    caso = Caso(a.caso)
    if a.cmd == "importar":
        for arq in a.arquivos:
            print(caso.importar(arq))
        return 0
    if a.cmd == "extrair":
        problemas = caso.verificar_integridade()
        if problemas:
            print("Integridade comprometida:\n- " + "\n- ".join(problemas), file=sys.stderr)
            return 2
        docs, avisos = caso.ler_documentos()
        q = montar_quadro(caso.id, docs, avisos)
        ap.salvar(q, caso.arquivo_quadro)
        print(f"{len(docs)} documento(s); {len(q.parametros)} parâmetro(s); {len(q.ocorrencias)} ocorrência(s).")
        print(f"Quadro: {caso.arquivo_quadro}")
        return 0

    q = ap.carregar(caso.arquivo_quadro)
    if a.cmd == "quadro":
        print(quadro_markdown(q))
        return 0
    if a.cmd == "status":
        pend = ap.bloqueios(q)
        print("Pronto para o cálculo." if not pend else "Pendências:\n- " + "\n- ".join(pend))
        return 0 if not pend else 1
    if a.cmd == "pacote":
        pacote, _ = montar_pacote(q, Autorizacao(responsavel=a.por, finalidade=a.finalidade, escopo=a.itens))
        print(f"Pacote gravado (pseudonimizado): {gravar_pacote(pacote, caso.pasta)}")
        return 0
    if a.cmd == "confirmar":
        det = dict(d.split("=", 1) for d in a.detalhe) or None
        ap.confirmar(q, a.param, a.por, a.valor, det, a.obs)
    elif a.cmd == "rejeitar":
        ap.rejeitar(q, a.param, a.por, a.motivo)
    elif a.cmd == "pagamentos":
        ap.confirmar_pagamentos(q, a.por)
    elif a.cmd == "ciencia":
        ap.dar_ciencia(q, a.ocorrencia, a.por)
    ap.salvar(q, caso.arquivo_quadro)
    print("Registrado.")
    return 0


def _motivos_reprovacao(ver: dict) -> list[str]:
    """Motivos da reprovação, sem dados pessoais."""
    m = []
    if ver.get("original_intacto") is False:
        m.append("o arquivo original foi alterado durante o processo")
    if ver.get("textos_removidos_reaparecendo"):
        m.append(f"{ver['textos_removidos_reaparecendo']} texto(s) removido(s) ainda aparecem na cópia "
                 f"(por tipo: {ver.get('reaparecendo_por_tipo') or 'não informado'})")
    if ver.get("residuos_por_tipo"):
        m.append(f"identificador(es) pessoal(is) ainda presente(s) na cópia (por tipo: {ver['residuos_por_tipo']}) — "
                 "acrescente o termo na lista ou avise a equipe técnica")
    for img in ver.get("imagens_restantes_detalhe") or []:
        m.append(f"imagem restante na pág. {img['pagina']} ({img['origem']}, {img['pixels']} px, {img['zona']}, "
                 f"{img['area_pct_pagina']}% da página) — função provável: {img['funcao_provavel']}")
    for chave, rotulo in (("imagens_restantes", "imagem(ns) restante(s)"), ("anotacoes_restantes", "anotação(ões) restante(s)"),
                          ("anexos_restantes", "anexo(s) restante(s)"), ("marcadores_restantes", "marcador(es) restante(s)")):
        if ver.get(chave):
            m.append(f"{ver[chave]} {rotulo}")
    if ver.get("residuos_em_estruturas_internas"):
        m.append(f"dado(s) pessoal(is) em estruturas internas do PDF (por tipo: {ver['residuos_em_estruturas_internas']}) "
                 "— revisão manual obrigatória")
    if ver.get("desenhos_vetoriais_restantes"):
        m.append(f"{ver['desenhos_vetoriais_restantes']} desenho(s) vetorial(is) com aparência de rubrica/assinatura restante(s)")
    if ver.get("estruturas_internas_restantes"):
        m.append(f"{ver['estruturas_internas_restantes']} estrutura(s) interna(s) (formulário, assinatura digital, "
                 "árvore de estrutura etc.) não removida(s)")
    if (ver.get("revisoes_no_arquivo") or 1) > 1:
        m.append("o arquivo guarda revisões anteriores (gravação incremental)")
    if ver.get("metadados_vazios") is False:
        m.append("metadados não puderam ser apagados")
    if ver.get("dados_financeiros_ausentes"):
        m.append(f"{ver['dados_financeiros_ausentes']} dado(s) financeiro(s) ausente(s) na cópia — integridade não garantida")
    if ver.get("tabelas_identicas") is False:
        m.append("as tabelas dos apêndices mudaram na cópia — integridade não garantida")
    if ver.get("paginas_digitalizadas"):
        m.append(f"página(s) digitalizada(s) {ver['paginas_digitalizadas']}: o conteúdo em imagem não pode ser anonimizado "
                 "nem conferido com segurança — use o PDF digital (não escaneado)")
    if ver.get("termos_nao_localizados_no_pdf"):
        m.append(f"{ver['termos_nao_localizados_no_pdf']} identificador(es) detectado(s) mas não localizado(s) para tarja "
                 f"(por tipo: {ver.get('nao_localizados_por_tipo') or 'não informado'})")
    if ver.get("observacao"):
        m.append(ver["observacao"])
    return m or ["verificação automática não aprovada"]


def _validacao(a) -> int:
    from .validacao.modelos import Classe
    from .validacao.pasta import Validacao

    v = Validacao(a.caso)
    if a.acao == "preparar":
        print(f"Pasta preparada: {v.preparar()}\nLeia {v.pasta / 'LEIA-ME.txt'}")
        return 0
    if a.acao == "ficticio":
        if not a.caso.startswith(("TESTE-", "DEMO-")):
            print("material fictício só em validações cujo ID começa com TESTE- ou DEMO-", file=sys.stderr)
            return 2
        from .demonstracao.parecer_ficticio import gerar_pdf_com_dados_ficticios
        v.preparar()
        gerar_pdf_com_dados_ficticios(v.pasta / "original" / "parecer-ficticio.pdf")
        (v.pasta / "anonimizacao" / "termos.txt").write_text("# termos fictícios\nFulana Perita Teste\n", encoding="utf-8")
        print(f"Material FICTÍCIO criado em {v.pasta} (original/parecer-ficticio.pdf e termos.txt)")
        return 0
    if a.acao == "importar-original":
        if not a.arquivo:
            print("uso: cm-calc validacao importar-original ID ARQUIVO", file=sys.stderr)
            return 2
        print(f"Original copiado como {v.importar_original(Path(a.arquivo).expanduser())} (o arquivo de origem não foi alterado)")
        return 0
    if a.acao == "termos":
        n = v.adicionar_termos((a.adicionar or "").split(";"))
        print(f"{n} termo(s) acrescentado(s) à lista de remoção.")
        return 0
    if a.acao == "abrir-conferencia":
        v.abrir_conferencia()
        return 0
    if a.acao == "listar-anonimizados":
        # só nomes genéricos e a situação da verificação (sem dados pessoais)
        import json as _json
        arq_ver = v.pasta / "anonimizacao" / "verificacao.json"
        ver = {r.get("arquivo_anonimizado"): r for r in _json.loads(arq_ver.read_text(encoding="utf-8"))} if arq_ver.exists() else {}
        for p in sorted((v.pasta / "anonimizados").glob("documento-*")):
            ok = ver.get(p.name, {}).get("verificacao", {}).get("aprovada")
            print(f"{p.name}\t{'APROVADA' if ok else 'REPROVADA'}")
        return 0
    if a.acao == "anonimizar":
        reprovados = 0
        for r in v.anonimizar(remover_imagens_grandes=a.remover_imagens_grandes):
            ver = r.get("verificacao", {})
            ok = bool(ver.get("aprovada"))
            reprovados += not ok
            print(f"{r['arquivo_original']} -> {r.get('arquivo_anonimizado') or '(não processado)'}: "
                  f"{'APROVADA' if ok else 'REPROVADA'}; remoções {r.get('remocoes_por_tipo', {})}")
            if not ok:
                for motivo in _motivos_reprovacao(ver):
                    print(f"   motivo: {motivo}")
        print(f"Verificação (sem dados pessoais): {v.pasta / 'anonimizacao' / 'verificacao.md'}")
        print(f"Relatório detalhado (CONFIDENCIAL): {v.pasta / 'anonimizacao'}/relatorio-detalhado-*.md")
        if reprovados:
            print("PROCEDIMENTO INTERROMPIDO: há verificação reprovada. Não libere o documento.")
            return 3
        return 0
    if a.acao == "liberar":
        faltam = [n for n, v in (("ARQUIVO", a.arquivo), ("--como", a.como), ("--por NOME", (a.por or "").strip()),
                                  ("--confirmo-conferencia", a.confirmo_conferencia)) if not v]
        if faltam:
            print(f"Liberação NÃO realizada — falta: {', '.join(faltam)}.\n"
                  "uso: cm-calc validacao liberar ID ARQUIVO --como parecer|documento --por NOME --confirmo-conferencia",
                  file=sys.stderr)
            return 2
        print(f"Liberado: {v.liberar(a.arquivo, a.como, a.por, a.apesar_de)}")
        return 0
    if a.acao == "diagnosticar-imagens":
        # só METADADOS técnicos das imagens que restaram nas cópias anonimizadas — nenhum pixel, nenhum texto
        import json as _json
        import pymupdf
        from .privacidade.anonimizacao import inventario_imagens
        for arq in sorted((v.pasta / "anonimizados").glob("*.pdf")):
            with pymupdf.open(arq) as d:
                inv = inventario_imagens(d)
            print(f"{arq.name}: {len(inv)} imagem(ns)")
            for i in inv:
                print("  " + _json.dumps(i, ensure_ascii=False))
        return 0
    if a.acao == "revogar":
        if not (a.sha256 and a.motivo and a.por):
            print("uso: cm-calc validacao revogar ID --sha256 HASH --motivo TEXTO --por NOME", file=sys.stderr)
            return 2
        v.revogar(a.sha256, a.motivo, a.por)
        print(f"Versão {a.sha256[:12]}… revogada e registrada.")
        return 0
    if a.acao == "verificar":
        for arq, achados in v.verificar_anonimizacao().items():
            print(f"{arq}: " + ("sem indícios de dados pessoais" if not achados else "ATENÇÃO — " + ", ".join(achados)))
        parecer = v.ler_parecer()
        for ap, t in sorted(parecer.tabelas.items()):
            print(f"{ap}: {len(t.linhas)} linhas, colunas {', '.join(t.colunas)}" + (f" — {'; '.join(t.avisos)}" if t.avisos else ""))
        for av in parecer.avisos:
            print(f"aviso: {av}")
        temas = sorted({m.tema for m in parecer.metodologia})
        print("Metodologia citada no parecer: " + (", ".join(temas) or "nenhum indício localizado"))
        try:
            pend = v.pendencias(parecer, v.ficha(), v.series())
        except ValueError as e:
            pend = [str(e)]
        print("Pronto para executar." if not pend else "Pendências:\n- " + "\n- ".join(pend))
        return 0 if not pend else 1
    rv, md, xlsx = v.executar(a.anonimizacao_confirmada_por)
    div = sum(c.classe is Classe.DIVERGENTE for c in rv.comparacoes)
    print(f"{len(rv.comparacoes)} valores comparados; {div} divergente(s); "
          f"{len(rv.inconsistencias)} inconsistência(s) interna(s) no parecer.\nRelatório: {md}\nPlanilha: {xlsx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
