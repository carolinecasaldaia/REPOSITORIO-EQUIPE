#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A rodada: consulta o Autentique, baixa o que já foi assinado por todos e
arquiva na pasta do cliente.

Ordem das decisões (importa):

1. O documento está assinado por TODAS as partes?      -> senão, nem baixa
2. Já foi resolvido numa rodada anterior?              -> senão, baixa
3. O PDF é mesmo um envelope de onboarding?            -> senão, quarentena
4. Qual é a pasta do cliente?                          -> senão, cria ou pendura
5. Grava o envelope e os documentos separados

O passo 3 vem antes do 4 de propósito: enquanto não se sabe que o documento é
do onboarding, nenhuma pasta de cliente é criada. Petição, acordo e qualquer
outro documento assinado no Autentique não bagunçam PREPARAÇÃO PARA INGRESSO.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import (arquivar, autentique, contrato, documentos, multicontrato,
               onboarding, pastas)


def _corte(dias: int):
    if not dias or dias <= 0:
        return None
    return datetime.now(timezone.utc) - timedelta(days=dias)


def _ficou_pronto_depois(documento, corte) -> bool:
    if corte is None:
        return True
    quando = autentique.para_datetime(autentique.quando_ficou_pronto(documento))
    return quando is None or quando >= corte


def _nomes_candidatos(documento, config, nome_no_contrato=""):
    """
    Nomes que podem identificar o cliente, do mais confiável ao menos.

    A ordem não é detalhe: em contrato com corresponsável, quem assina primeiro
    às vezes é o corresponsável — foi medido em dois dos 15 envelopes reais de
    17/08/2026 (Cristiane/Evandro e Maria Nizete/Antonio). Por isso o nome
    escrito no contrato vem na frente do nome do signatário.
    """
    fortes = []
    if nome_no_contrato:
        fortes.append(nome_no_contrato)
    for nome in autentique.signatarios_clientes(documento, config.eh_do_escritorio):
        if nome not in fortes:
            fortes.append(nome)
    fracos = [n for n in pastas.nomes_do_documento(documento.get("name") or "")
              if n not in fortes]
    return fortes, fracos


def processar(documento, config, estado, log, api, candidatas,
              somente_conferir: bool = False) -> dict:
    """Trata um documento. Devolve o registro do que aconteceu."""
    doc_id = documento.get("id") or ""
    nome_doc = documento.get("name") or "(sem nome)"
    resumo = autentique.resumo_assinaturas(documento)
    registro = {
        "nome": nome_doc,
        "assinado_em": autentique.quando_ficou_pronto(documento),
        "partes": resumo["total"],
        "signatarios": resumo["assinaram"],
        "cliente": "",
        "pasta": "",
        "arquivos": [],
        "situacao": "erro",
        "motivo": "",
    }

    url = (documento.get("files") or {}).get("signed")
    temporario = Path(config.pasta_temp) / ("%s.pdf" % (doc_id or "documento"))
    temporario.parent.mkdir(parents=True, exist_ok=True)

    try:
        api.baixar_pdf(url, temporario)

        # --- 3. é envelope de onboarding? --------------------------------
        reader, secoes, relatorio, tipos = arquivar.analisar_envelope(
            temporario, config.separador)
        if not arquivar.eh_envelope_de_onboarding(tipos):
            registro["situacao"] = "ignorado"
            registro["motivo"] = ("Não é envelope de onboarding (não achei contrato, "
                                  "procuração nem declaração de hipossuficiência no PDF).")
            if not somente_conferir:
                guardado = arquivar.guardar_na_quarentena(
                    temporario, config.pasta_quarentena, nome_doc)
                registro["arquivos"] = [str(guardado)]
            log.info("• %s — ignorado: não é envelope de onboarding." % nome_doc)
            return registro

        registro["documentos_no_pdf"] = sorted(tipos)

        # --- 4. de quem é? ------------------------------------------------
        # O nome vale mais vindo do contrato do que do cadastro do Autentique,
        # que traz nome abreviado com frequência ("Telma Cristiane E").
        texto = contrato.texto_inicial(reader)
        nome_no_contrato = contrato.nome_do_contratante(texto)
        corresponsavel = contrato.nome_do_responsavel(texto)
        if corresponsavel:
            registro["corresponsavel"] = corresponsavel
        fortes, fracos = _nomes_candidatos(documento, config, nome_no_contrato)
        registro["cliente"] = fortes[0] if fortes else (fracos[0] if fracos else "")
        resultado = pastas.localizar(candidatas, fortes, config.limiar_nome)
        if not resultado.achou and fracos:
            # Só o primeiro nome no título do envelope: exige casamento quase
            # exato, senão dá pasta trocada.
            tentativa = pastas.localizar(candidatas, fracos, max(0.95, config.limiar_nome))
            if tentativa.achou:
                resultado = tentativa

        pasta_cliente = None
        if resultado.achou:
            pasta_cliente = resultado.pasta.caminho
            registro["motivo"] = resultado.motivo
        elif resultado.situacao == "ambiguo" or not fortes:
            registro["situacao"] = "pendente"
            registro["motivo"] = resultado.motivo + (
                " Opções: " + "; ".join(resultado.alternativas) if resultado.alternativas else "")
            if not somente_conferir:
                guardado = arquivar.guardar_na_quarentena(
                    temporario, config.pasta_quarentena, nome_doc)
                registro["arquivos"] = [str(guardado)]
            log.aviso("• %s — pendente: %s" % (nome_doc, registro["motivo"]))
            return registro
        elif config.criar_pasta:
            if somente_conferir:
                registro["situacao"] = "pendente"
                registro["motivo"] = ("Cliente novo: seria criada a pasta \"%s\" em %s."
                                      % (fortes[0].upper(), pastas.nome_do_mes()))
                log.info("• %s — %s" % (nome_doc, registro["motivo"]))
                return registro
            quando = autentique.para_datetime(registro["assinado_em"])
            pasta_cliente = pastas.criar_pasta_cliente(
                config.pasta_clientes, fortes[0],
                quando.astimezone() if quando else None)
            candidatas.append(pastas.PastaCliente(pasta_cliente, pasta_cliente.parent.name))
            registro["motivo"] = "Cliente novo — pasta criada agora."
            log.ok("• %s — pasta criada: %s" % (nome_doc, pasta_cliente))
        else:
            registro["situacao"] = "pendente"
            registro["motivo"] = resultado.motivo + " (criação de pasta desligada)"
            if not somente_conferir:
                guardado = arquivar.guardar_na_quarentena(
                    temporario, config.pasta_quarentena, nome_doc)
                registro["arquivos"] = [str(guardado)]
            log.aviso("• %s — pendente: %s" % (nome_doc, registro["motivo"]))
            return registro

        registro["pasta"] = str(pasta_cliente)

        # --- 5. arquivar ---------------------------------------------------
        if somente_conferir:
            registro["situacao"] = "pendente"
            registro["motivo"] = "Só conferência: nada foi gravado. %s" % registro["motivo"]
            log.info("• %s — iria para %s" % (nome_doc, pasta_cliente))
            return registro

        feito = arquivar.arquivar(temporario, pasta_cliente, nome_doc, config.separador,
                                  separar=config.separar, reader=reader,
                                  secoes=secoes, relatorio=relatorio)
        # Documento de cliente solto na raiz vai para DOC CLIENTE — decisão
        # dela em 18/08/2026. Na dúvida o arquivo fica onde está.
        arrumados = documentos.arrumar(pasta_cliente, arquivar.carregar_separador(config.separador))
        if arrumados:
            registro["arquivos"] += [str(destino) for _n, _t, destino in arrumados]
            registro["motivo"] += (" %d documento(s) do cliente foram para DOC CLIENTE (%s)."
                                   % (len(arrumados), ", ".join(sorted({t for _n, t, _d in arrumados}))))
            log.info("  ↳ %d documento(s) arrumados em DOC CLIENTE." % len(arrumados))

        # Envelope com mais de um contrato de honorários: o onboarding e o caso
        # sairiam só do primeiro, e o segundo sumiria calado (Sofia, 01/09/2026).
        varios = multicontrato.conferir(reader)
        pastas_do_cliente = [pasta_cliente]
        if varios:
            registro["multicontrato"] = varios
            registro["motivo"] += " " + multicontrato.recado(varios, registro["cliente"])
            log.aviso("  ↳ %s" % multicontrato.recado(varios, registro["cliente"]))
            contrato_pdf = next((c for _r, c in feito["documentos"]
                                 if "CONTRATO HO" in str(c).upper()), None)
            separadas = multicontrato.separar(
                pasta_cliente, contrato_pdf, feito["envelope"],
                arquivar.carregar_separador(config.separador)) if contrato_pdf else []
            if separadas:
                pastas_do_cliente = separadas
                registro["pasta"] = str(separadas[0])
                registro["pastas"] = [str(p) for p in separadas]
                registro["motivo"] += (" Separei em %d pastas: %s. Os nomes são "
                                       "provisórios — renomeie para o que cada caso é."
                                       % (len(separadas),
                                          ", ".join(p.name for p in separadas)))
                log.ok("  ↳ separado em %d pastas (CONTRATO 1..%d)."
                       % (len(separadas), len(separadas)))

        if corresponsavel:
            registro["motivo"] += " Corresponsável no contrato: %s." % corresponsavel
        registro["situacao"] = "baixado"
        registro["arquivos"] = [str(feito["envelope"])] + [str(c) for _r, c in feito["documentos"]]
        if feito["ja_existia"]:
            registro["motivo"] = ("Já estava arquivado em %s — nada foi duplicado."
                                  % feito["envelope"].name)
            log.info("• %s — já estava na pasta do cliente." % nome_doc)
        else:
            gerados = ", ".join(r for r, _c in feito["documentos"]) or "envelope"
            registro["motivo"] = "%s Documentos gravados: %s." % (registro["motivo"], gerados)
            log.ok("• %s — arquivado em %s" % (nome_doc, pasta_cliente.name))

        # --- 6. onboarding do cliente --------------------------------------
        # Vem depois do arquivamento porque o gerador lê justamente o contrato
        # que acabou de ser gravado em CONTRATO HO. Falha aqui não desfaz nada:
        # o contrato continua arquivado e o recado vai para o relatório.
        if config.gerar_onboarding:
            # Uma por pasta: envelope com dois contratos vira dois onboardings.
            for pasta in pastas_do_cliente:
                feito_onb = onboarding.gerar(pasta, config, config.timeout_onboarding_s)
                registro["onboarding"] = feito_onb["situacao"]
                registro["motivo"] += " " + feito_onb["motivo"]
                if feito_onb["arquivo"]:
                    registro["arquivos"].append(str(feito_onb["arquivo"]))
                if feito_onb["situacao"] == "gerado":
                    log.ok("  ↳ onboarding gerado%s."
                           % (" (%s)" % pasta.name if len(pastas_do_cliente) > 1 else ""))
                elif feito_onb["situacao"] != "ja_existia":
                    log.aviso("  ↳ %s" % feito_onb["motivo"])
        return registro

    except (autentique.ErroAutentique, arquivar.ErroArquivamento) as erro:
        registro["situacao"] = "erro"
        registro["motivo"] = str(erro)
        log.erro("• %s — %s" % (nome_doc, erro))
        return registro
    except OSError as erro:
        registro["situacao"] = "erro"
        registro["motivo"] = "Problema de arquivo/pasta: %s" % erro
        log.erro("• %s — %s" % (nome_doc, erro))
        return registro
    finally:
        try:
            temporario.unlink(missing_ok=True)
        except OSError:
            pass


def rodar(config, estado, log, api, somente_conferir: bool = False,
          incluir_historico: bool = False, dias: int = 0) -> dict:
    """
    Uma rodada completa.

    `incluir_historico=True` reprocessa também o que foi marcado como histórico
    (comando 'historico'), limitado a `dias` para trás.
    """
    resultado = {"prontos": 0, "novos": 0, "baixados": 0, "pendentes": 0,
                 "ignorados": 0, "erros": 0, "primeira_vez": False, "eventos": []}

    documentos = api.prontos(max_paginas=config.max_paginas,
                             limite=config.itens_por_pagina,
                             pasta=config.pasta_autentique)
    resultado["prontos"] = len(documentos)
    log.info("Documentos assinados por todas as partes no Autentique: %d" % len(documentos))

    filtro = config.regex_filtro()
    if filtro is not None:
        documentos = [d for d in documentos if filtro.search(d.get("name") or "")]
        log.info("Depois do filtro pelo nome: %d" % len(documentos))

    # Primeira vez: o que já estava assinado vira histórico, senão a automação
    # baixaria de novo anos de contrato na primeira rodada.
    if estado.vazio() and not incluir_historico:
        resultado["primeira_vez"] = True
        if somente_conferir:
            # Conferir não pode ATIVAR a automação sem querer: nada é gravado,
            # e ela vê o que a primeira rodada de verdade vai fazer.
            log.aviso("Ainda não foi ligada. A primeira verificação de verdade vai "
                      "marcar %d documentos já assinados como histórico (sem baixar "
                      "nenhum) e só depois passa a baixar os novos." % len(documentos))
            return resultado
        for documento in documentos:
            estado.anotar(documento["id"], nome=documento.get("name") or "",
                          situacao="historico",
                          assinado_em=autentique.quando_ficou_pronto(documento),
                          motivo="Já estava assinado quando a automação foi ligada.")
        estado.marcar_ligada()
        estado.marcar_rodada()
        estado.salvar()
        log.aviso("Primeira rodada: %d documentos já assinados foram marcados como "
                  "histórico. A partir de agora, só os novos são baixados "
                  "(o menu tem a opção de trazer os antigos)." % len(documentos))
        return resultado

    corte = _corte(dias) if incluir_historico else None
    candidatas = pastas.varrer(config.pasta_clientes)
    log.info("Pastas de cliente encontradas em PREPARAÇÃO PARA INGRESSO: %d" % len(candidatas))

    for documento in documentos:
        doc_id = documento.get("id") or ""
        if not doc_id:
            continue
        situacao = estado.situacao(doc_id)
        if incluir_historico:
            if situacao == "baixado" or not _ficou_pronto_depois(documento, corte):
                continue
        elif estado.conhecido(doc_id):
            continue

        resultado["novos"] += 1
        registro = processar(documento, config, estado, log, api, candidatas,
                             somente_conferir=somente_conferir)
        if not somente_conferir:
            estado.anotar(doc_id, **registro)
        registro["id"] = doc_id
        resultado["eventos"].append(registro)
        chave = {"baixado": "baixados", "pendente": "pendentes",
                 "ignorado": "ignorados", "erro": "erros"}.get(registro["situacao"])
        if chave:
            resultado[chave] += 1

    # Onboardings que ficaram esperando o banco: tenta de novo a cada rodada.
    # Decisão dela em 18/09/2026 — os documentos da Gisleine chegaram dois dias
    # depois do contrato, e nada tentava outra vez.
    resultado["onboardings_retomados"] = retomar_onboardings(
        config, estado, log, candidatas, somente_conferir=somente_conferir)

    if not somente_conferir:
        estado.marcar_ligada()
        estado.marcar_rodada()
        estado.salvar()
    return resultado


def _pasta_atual(registro, candidatas):
    """
    Onde a pasta do cliente está HOJE.

    O caminho guardado envelhece: ela põe "01 - OK -" no nome quando manda
    para o jurídico, move de mês, e às vezes divide em duas (Sofia). Primeiro
    o caminho guardado; se sumiu, procura pelo nome do cliente — e, havendo
    duas parecidas, não escolhe (mesma regra do arquivamento).
    """
    guardado = Path(registro.get("pasta") or "")
    if str(guardado) not in ("", ".") and guardado.is_dir():
        return guardado
    nome = registro.get("cliente") or ""
    if not nome:
        return None
    achado = pastas.localizar(candidatas, [nome])
    return achado.pasta.caminho if achado.achou else None


def retomar_onboardings(config, estado, log, candidatas, somente_conferir=False) -> list:
    """
    Tenta de novo os onboardings pendentes. Devolve os nomes dos que saíram.

    Nunca gera um segundo onboarding: se a pasta já tem um (feito à mão, por
    exemplo), só atualiza o histórico para parar de tentar.
    """
    if not getattr(config, "gerar_onboarding", True):
        return []
    gerados = []
    for doc_id, registro in list(estado.documentos.items()):
        if registro.get("onboarding") != "pendente":
            continue
        pasta = _pasta_atual(registro, candidatas)
        if pasta is None:
            continue                       # sumiu ou ficou ambígua: não chuta
        existente = onboarding.ja_tem_onboarding(pasta)
        if existente is not None:
            if not somente_conferir:
                estado.anotar(doc_id, onboarding="ja_existia", pasta=str(pasta))
            continue
        if somente_conferir:
            log.info("• %s — onboarding pendente seria tentado de novo."
                     % (registro.get("cliente") or pasta.name))
            continue
        feito = onboarding.gerar(pasta, config, config.timeout_onboarding_s)
        if feito["situacao"] == "gerado":
            estado.anotar(doc_id, onboarding="gerado", pasta=str(pasta),
                          motivo=(registro.get("motivo") or "") + " " + feito["motivo"])
            gerados.append(registro.get("cliente") or pasta.name)
            log.ok("• %s — onboarding gerado agora (%s)"
                   % (registro.get("cliente") or pasta.name, feito["motivo"][:90]))
    return gerados


def limpar_quarentena(config, dias: int = None) -> int:
    """Apaga da quarentena o que já passou do prazo. Devolve quantos saíram."""
    dias = config.dias_quarentena if dias is None else dias
    if dias <= 0:
        return 0
    pasta = Path(config.pasta_quarentena)
    if not pasta.exists():
        return 0
    limite = datetime.now().timestamp() - dias * 86400
    apagados = 0
    for arquivo in pasta.glob("*.pdf"):
        try:
            if arquivo.stat().st_mtime < limite:
                arquivo.unlink()
                apagados += 1
        except OSError:
            continue
    return apagados
