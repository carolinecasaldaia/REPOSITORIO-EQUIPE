#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orquestrador: junta varredura, extração, validação, Astrea e controle.

Duas regras estruturam este arquivo:

**Erro de um cliente não derruba a rodada.** Cada cliente é processado dentro do
seu próprio try/except. Cliente B com documento ilegível não impede o cliente C
de ser cadastrado.

**Sem consulta de duplicidade, não cadastra.** Se o Astrea não responder à busca
do CPF, o cliente fica com ERRO NO CADASTRO e espera a próxima rodada. Duplicar
cadastro de cliente é pior do que atrasar.

**Enviado sem confirmação não é erro.** O Astrea leva alguns segundos para
devolver na busca o que acabou de gravar. Nesse intervalo o cliente fica em
CADASTRO A CONFIRMAR, com o id que a própria tela devolveu ao salvar, e a
rodada seguinte **confirma antes de tentar qualquer coisa**. Tratar esse
intervalo como erro foi o que deixou o Wladson com dois contatos (08/09/2026).
"""

from datetime import datetime

from ..astrea.base import (BuscaIndisponivel, ErroAstrea, ErroAutenticacao,
                           ErroSessaoPerdida)
from ..database import controle as St
from ..database.controle import Controle, ExecucaoJaEmAndamento, TravaDeExecucao
from ..drive import scanner
from ..extractors import contrato_ho, documentos as D
from ..astrea.casos import tipo_do_contrato
from ..validators import analise, documentacao, parceiro

MODO_NOVOS = "novos"
MODO_IMPORTACAO = "importacao"


class Resumo(object):
    def __init__(self):
        self.total = 0
        self.cadastrados = 0
        self.ja_existiam = 0
        self.pendentes = 0
        self.divergentes = 0
        self.erros = 0
        self.simulados = 0
        self.aguardando = 0
        self.ignorados = 0
        self.parceiros = 0
        self.linhas = []
        # Rodada que nem conseguiu entrar não é rodada boa. Sem isto, o
        # agendador marcava "ok" enquanto o login falhava de hora em hora —
        # cinco horas sem cadastrar ninguém e sem ninguém saber (09/09/2026).
        self.sem_acesso = ""
        # "senha" quando o Astrea recusou o login; "conexao" para o resto (Chrome
        # ocupado, rede, Astrea fora). O aviso da tela muda conforme o motivo:
        # mandar trocar a senha quando o Chrome só estava ocupado seria errado.
        self.motivo_sem_acesso = ""

    def contagens(self):
        return {"total": self.total, "cadastrados": self.cadastrados,
                "ja_existiam": self.ja_existiam, "pendentes": self.pendentes,
                "divergentes": self.divergentes, "erros": self.erros}

    def como_texto(self):
        return ("%d pasta(s) analisada(s): %d cadastrado(s), %d já existiam, "
                "%d pendente(s), %d divergente(s), %d erro(s), %d simulado(s), "
                "%d aguardando%s." % (self.total, self.cadastrados, self.ja_existiam,
                                    self.pendentes, self.divergentes, self.erros,
                                    self.simulados, self.aguardando,
                                    ", %d do parceiro" % self.parceiros
                                    if self.parceiros else ""))


def _criar_adaptador(config, log):
    if config.astrea_adaptador == "planilha":
        from ..astrea.planilha import AdaptadorPlanilha
        return AdaptadorPlanilha(config, log)
    if config.astrea_adaptador == "dry-run":
        from ..astrea.dry_run import AdaptadorDryRun
        return AdaptadorDryRun(config, log)

    # Navegador sem NENHUM acesso configurado (nem sessão salva no perfil, nem
    # senha no .env) cai para dry-run em vez de falhar — dá para homologar a
    # leitura antes de configurar o acesso.
    #
    # A condição olha os dois caminhos de propósito: checar só a senha do .env
    # fazia a automação cair em dry-run mesmo com a sessão salva válida, e o
    # teste passava sem nunca ter consultado o Astrea.
    if not config.tem_acesso_astrea():
        if config.test_mode:
            log.alerta("Sem acesso ao Astrea configurado — rodando em dry-run "
                       "(lê as pastas, mas NÃO confere duplicidade). Rode "
                       "'executar.py entrar' para conferir de verdade.")
            from ..astrea.dry_run import AdaptadorDryRun
            return AdaptadorDryRun(config, log)

    from ..astrea.navegador import AdaptadorNavegador
    return AdaptadorNavegador(config, log)


# ---------------------------------------------------------------------------
# Ativação (linha de corte do MODO NOVOS)
# ---------------------------------------------------------------------------

def ativar(config, log, banco: Controle):
    """
    Primeira execução: marca todas as pastas que JÁ existem como histórico.

    É o que garante o item 18 do projeto — a automação não sai cadastrando as
    51 pastas antigas de uma vez só porque foi ligada.
    """
    pastas = scanner.varrer(config.pasta_clientes,
                            scanner.meses_aceitos(config.meses))
    quando = banco.ativar()
    for pasta in pastas:
        banco.registrar_visto(pasta.drive_id, pasta.caminho, pasta.nome_pasta,
                              pasta.mes, St.HISTORICO, modo="ativacao",
                              detalhe="Já existia quando a automação foi ativada.")
    log.ok("Automação ativada em %s. %d pasta(s) existentes foram marcadas como "
           "histórico e NÃO serão cadastradas automaticamente."
           % (quando.replace("T", " "), len(pastas)))
    log.info("A partir de agora, só pastas novas entram no fluxo. Para trazer as "
             "antigas, use o modo importação.")
    return len(pastas)


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

def executar(config, log, modo=MODO_NOVOS, apenas=None, limite=None,
             forcar_reprocesso=False):
    """
    Roda uma passada completa.

    modo=novos       → só pastas que apareceram depois da ativação
    modo=importacao  → também as pastas antigas (exige confirmação de quem chama)
    apenas           → lista de nomes de pasta (subconjunto, para teste)
    """
    config.preparar_pastas()
    resumo = Resumo()
    execucao_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    with Controle(config.banco) as banco:
        try:
            trava = TravaDeExecucao(config.pasta_dados / "execucao.lock")
            trava.__enter__()
        except ExecucaoJaEmAndamento as erro:
            log.alerta(str(erro) + " Esta rodada foi ignorada.")
            return resumo

        try:
            banco.destravar_presos(log)

            if not banco.automacao_ativada():
                if modo == MODO_IMPORTACAO:
                    banco.ativar()
                    log.alerta("Automação ainda não tinha sido ativada; ativada "
                               "agora para permitir a importação.")
                else:
                    ativar(config, log, banco)
                    return resumo

            linha_execucao = banco.abrir_execucao(execucao_id, modo, config.test_mode)
            pastas = scanner.varrer(config.pasta_clientes,
                            scanner.meses_aceitos(config.meses))
            log.info("%d pasta(s) de cliente encontradas em %s."
                     % (len(pastas), config.pasta_clientes.name))

            fila = _montar_fila(pastas, banco, modo, apenas, forcar_reprocesso,
                                log, resumo)
            if limite:
                fila = fila[:limite]

            if not fila:
                log.info("Nenhum cliente novo para processar.")
                banco.fechar_execucao(linha_execucao, resumo.contagens())
                return resumo

            log.info("%d cliente(s) na fila desta rodada." % len(fila))
            adaptador = _criar_adaptador(config, log)
            try:
                adaptador.conectar()
                banco.definir_marco("sem_sessao_desde", "")
            except ErroAutenticacao as erro:
                # Caso mais comum no dia a dia: a sessão da automação foi
                # derrubada porque a advogada usou o Astrea (o sistema só
                # aceita uma sessão por conta). Fica registrado para aparecer
                # no relatório — silêncio aqui seria pior que erro.
                if not banco.marco("sem_sessao_desde"):
                    banco.definir_marco(
                        "sem_sessao_desde",
                        datetime.now().isoformat(timespec="seconds"))
                resumo.sem_acesso = str(erro)
                resumo.motivo_sem_acesso = "senha"
                log.erro("A automação não conseguiu entrar no Astrea: %s" % erro)
                log.info("Nenhum cliente foi processado. Abra o atalho e use "
                         "'Entrar no Astrea' — a fila continua intacta.")
                banco.fechar_execucao(linha_execucao, resumo.contagens())
                return resumo
            except ErroAstrea as erro:
                resumo.sem_acesso = str(erro)
                resumo.motivo_sem_acesso = "conexao"
                log.erro("Não foi possível conectar ao Astrea: %s" % erro)
                banco.fechar_execucao(linha_execucao, resumo.contagens())
                return resumo

            try:
                for pasta in fila:
                    try:
                        _processar_com_protecao(pasta, banco, adaptador, config,
                                                log, resumo, modo)
                    except ErroSessaoPerdida as erro:
                        # A sessão caiu no meio. Continuar só produziria uma fila
                        # de erros que não são dos clientes. Devolve este para a
                        # fila e encerra a rodada; a próxima retoma de onde parou.
                        banco.concluir(pasta.drive_id, St.AGUARDANDO,
                                       detalhe="Rodada interrompida: %s" % erro)
                        resumo.aguardando += 1
                        log.erro("RODADA INTERROMPIDA — %s" % erro)
                        log.info("Os clientes que faltaram continuam na fila e "
                                 "entram na próxima rodada. Nada foi perdido.")
                        break
                    if hasattr(adaptador, "pausar"):
                        adaptador.pausar()
            finally:
                adaptador.encerrar()

            banco.fechar_execucao(linha_execucao, resumo.contagens())
            log.titulo("Resultado: " + resumo.como_texto())
            return resumo
        finally:
            trava.__exit__(None, None, None)


def _montar_fila(pastas, banco, modo, apenas, forcar, log, resumo):
    fila = []
    for pasta in pastas:
        if apenas and pasta.nome_pasta not in apenas:
            continue

        registro = banco.buscar(pasta.drive_id)
        if registro is not None and registro["status"] in St.DEFINITIVOS:
            if registro["status"] == St.HISTORICO and modo == MODO_IMPORTACAO:
                banco.reabrir(pasta.drive_id,
                              "Reaberta pelo modo importação (confirmado por quem "
                              "executou).")
            elif forcar and registro["status"] != St.CADASTRADO:
                banco.reabrir(pasta.drive_id, "Reprocessamento forçado.")
            else:
                resumo.ignorados += 1
                continue

        if registro is not None and registro["tentativas"] >= 99:
            resumo.ignorados += 1
            continue

        banco.registrar_visto(pasta.drive_id, pasta.caminho, pasta.nome_pasta,
                              pasta.mes, St.AGUARDANDO, modo=modo)
        fila.append(pasta)
    return fila


def _processar_com_protecao(pasta, banco, adaptador, config, log, resumo, modo):
    """Envolve o processamento de um cliente. Nada aqui pode derrubar a rodada."""
    resumo.total += 1
    log.contexto(pasta=pasta.nome_pasta, cliente=pasta.nome_provavel)

    try:
        minutos = 0 if modo == MODO_IMPORTACAO else config.minutos_estabilidade
        if not pasta.estavel(minutos):
            banco.concluir(pasta.drive_id, St.AGUARDANDO,
                           detalhe="Pasta ainda estava recebendo arquivos "
                                   "(parada há %.0f min, mínimo %d)."
                                   % (pasta.minutos_parada, minutos))
            resumo.aguardando += 1
            log.info("Aguardando: pasta ainda em movimento (%.0f min parada)."
                     % pasta.minutos_parada)
            return

        if not banco.marcar_em_processamento(pasta.drive_id):
            resumo.ignorados += 1
            log.info("Outra execução já está com esta pasta — ignorada nesta rodada.")
            return

        ficha = processar_cliente(pasta, adaptador, config, log, banco, resumo)
        resumo.linhas.append(ficha.como_dict() if ficha else None)

    except ErroSessaoPerdida:
        # A proteção deste bloco é contra erro DE CLIENTE. Sessão caída é da
        # rodada inteira, então passa direto para quem chamou.
        raise
    except Exception as erro:                          # rede, disco, bug: tudo
        resumo.erros += 1
        log.erro("Erro inesperado ao processar este cliente: %s" % erro)
        try:
            banco.concluir(pasta.drive_id, St.ERRO,
                           nome_cliente=pasta.nome_provavel,
                           detalhe="Erro inesperado.", erro=str(erro))
        except Exception:
            pass
    finally:
        log.limpar_contexto()


def processar_cliente(pasta, adaptador, config, log, banco, resumo):
    """Um cliente, do começo ao fim."""
    docs = D.inventariar(pasta.caminho)

    if not docs:
        banco.concluir(pasta.drive_id, St.PENDENTE,
                       nome_cliente=pasta.nome_provavel,
                       detalhe="Pasta sem documentos.")
        resumo.pendentes += 1
        log.registrar_resultado(pasta.nome_pasta, pasta.nome_provavel, "",
                                "Análise da pasta", St.PENDENTE,
                                erro=None)
        log.alerta("PENDENTE DE INFORMAÇÃO — a pasta não tem nenhum documento.")
        return None

    documento_contrato = D.escolher_contrato(docs)
    resultado = None
    if documento_contrato is not None:
        if not scanner.arquivo_disponivel(documento_contrato.caminho):
            banco.concluir(pasta.drive_id, St.AGUARDANDO,
                           nome_cliente=pasta.nome_provavel,
                           detalhe="Contrato ainda não baixado do Google Drive.")
            resumo.aguardando += 1
            log.info("Aguardando: o contrato ainda está só na nuvem.")
            return None
        resultado = contrato_ho.extrair(documento_contrato.caminho)

    ficha = analise.montar(pasta.nome_pasta, pasta.caminho, resultado, docs,
                           config.extrair_corresponsavel)
    if ficha.pessoa is not None:
        analise.analisar(ficha, config.campos_obrigatorios, config.limiar_confianca)

    for nao_lido in ficha.nao_interpretados:
        log.alerta("DOCUMENTO NÃO INTERPRETADO: %s (%s) — %s"
                   % (nao_lido["arquivo"], nao_lido["tipo"], nao_lido["motivo"]))

    log.contexto(pasta=pasta.nome_pasta, cliente=ficha.nome or pasta.nome_provavel,
                 cpf=ficha.cpf)

    # --- assunto do parceiro (decisão dela, 02/10/2026) ------------------
    # "Adicional de insalubridade e reflexos" é do escritório parceiro: não
    # cadastra ninguém no Astrea e, sem cadastro, não há caso nem cópia para
    # o jurídico. Vem ANTES da trava de documentação de propósito — cobrar
    # RG/CNH de um cliente que nem é nosso para cadastrar seria recado errado
    # para o comercial. O status é definitivo: não volta como pendência.
    objeto_do_contrato = (resultado.objeto.valor or "") if resultado else ""
    if parceiro.e_do_parceiro(objeto_do_contrato):
        recado = parceiro.motivo(objeto_do_contrato)
        banco.concluir(pasta.drive_id, St.PARCEIRO, ficha.nome, ficha.cpf,
                       detalhe=recado, confianca=ficha.confianca,
                       dados=ficha.como_dict())
        resumo.parceiros += 1
        log.info("%s  [%s]" % (recado, ficha.nome or pasta.nome_provavel))
        return ficha

    # --- trava de documentação (decisão dela, 25/09/2026) ----------------
    # Sem RG/CNH, comprovante de residência e (em caso de veículo) CRLV na
    # pasta, não cadastra — e, como o caso e a cópia para o jurídico só vêm
    # depois do cadastro, também não andam. Vem antes da
    # checagem de divergência de propósito: o que falta é o primeiro recado
    # para o comercial. PENDENTE é reavaliado toda rodada, então completar a
    # pasta libera sozinho.
    faltando = documentacao.faltantes(
        pasta.caminho, tipo_do_contrato(ficha.tipo_acao.valor))
    # Liberação manual (20/10/2026): o cliente passa mesmo faltando documento,
    # e o que falta vira observação em vez de travar. Ver
    # `documentacao.ler_liberacoes`.
    motivo_liberacao = documentacao.liberado(ficha.nome or "", pasta.nome_pasta)
    if faltando and motivo_liberacao:
        ficha.observacoes.append(
            "LIBERADO MANUALMENTE da trava de documentação (%s). Continua "
            "faltando na pasta: %s." % (motivo_liberacao, ", ".join(faltando)))
        log.alerta("Documentação incompleta, mas liberada por decisão dela "
                   "(%s) — falta: %s" % (motivo_liberacao, ", ".join(faltando)))
        faltando = []
    if faltando:
        aviso = documentacao.mensagem(faltando)
        ficha.pendencias.insert(0, aviso)
        outros = ficha.detalhe if ficha.status else ""
        ficha.status = St.PENDENTE
        ficha.detalhe = aviso + (("; " + outros) if outros else "")

    # --- caminhos que não cadastram -------------------------------------
    if ficha.status == St.PENDENTE:
        banco.concluir(pasta.drive_id, St.PENDENTE, ficha.nome, ficha.cpf,
                       ficha.detalhe, confianca=ficha.confianca,
                       dados=ficha.como_dict())
        resumo.pendentes += 1
        log.alerta("PENDENTE DE INFORMAÇÃO — %s" % ficha.detalhe)
        return ficha

    if ficha.status == St.DIVERGENTE:
        banco.concluir(pasta.drive_id, St.DIVERGENTE, ficha.nome, ficha.cpf,
                       ficha.detalhe, confianca=ficha.confianca,
                       dados=ficha.como_dict())
        resumo.divergentes += 1
        log.alerta("DADOS DIVERGENTES — %s" % ficha.detalhe)
        return ficha

    # --- duplicidade ----------------------------------------------------
    try:
        busca = adaptador.buscar_por_documento(ficha.cpf, ficha.nome)
    except ErroSessaoPerdida:
        # Não é problema deste cliente: sobe para interromper a rodada.
        raise
    except BuscaIndisponivel as erro:
        banco.concluir(pasta.drive_id, St.ERRO, ficha.nome, ficha.cpf,
                       detalhe="Cadastro não tentado: não deu para verificar "
                               "duplicidade.", erro=str(erro),
                       confianca=ficha.confianca, dados=ficha.como_dict())
        resumo.erros += 1
        log.erro("Não foi possível verificar se o CPF já existe no Astrea (%s). "
                 "Por segurança, o cliente NÃO foi cadastrado." % erro)
        return ficha
    except ErroAstrea as erro:
        banco.concluir(pasta.drive_id, St.ERRO, ficha.nome, ficha.cpf,
                       detalhe="Falha na consulta ao Astrea.", erro=str(erro),
                       confianca=ficha.confianca, dados=ficha.como_dict())
        resumo.erros += 1
        log.erro("Falha ao consultar o Astrea: %s" % erro)
        return ficha

    if busca.encontrado:
        banco.concluir(pasta.drive_id, St.JA_CADASTRADO, ficha.nome, ficha.cpf,
                       detalhe=busca.detalhe or "CPF já existe no Astrea.",
                       astrea_contato_id=busca.astrea_id,
                       confianca=ficha.confianca, dados=ficha.como_dict())
        resumo.ja_existiam += 1
        log.registrar_resultado(pasta.nome_pasta, ficha.nome, ficha.cpf,
                                "Consulta de CPF", St.JA_CADASTRADO,
                                astrea_id=busca.astrea_id)
        log.ok("JÁ CADASTRADO NO ASTREA%s — nenhum cadastro novo foi criado."
               % ((" (id %s)" % busca.astrea_id) if busca.astrea_id else ""))
        return ficha

    # Suspeita não é duplicidade confirmada, mas também não é hora de arriscar:
    # se existe alguém de mesmo nome sem o CPF, quem decide é gente.
    if busca.suspeitas:
        ficha.divergencias.extend(busca.suspeitas)
        banco.concluir(pasta.drive_id, St.DIVERGENTE, ficha.nome, ficha.cpf,
                       detalhe="; ".join(busca.suspeitas),
                       confianca=ficha.confianca, dados=ficha.como_dict())
        resumo.divergentes += 1
        log.alerta("DADOS DIVERGENTES — %s" % "; ".join(busca.suspeitas))
        return ficha

    # --- cadastro -------------------------------------------------------
    # Antes de cadastrar: a rodada anterior deixou algo "a confirmar"? Se
    # deixou, o contato já existe (a tela devolveu o id ao salvar) e cadastrar
    # de novo criaria o segundo registro — foi assim que o Wladson duplicou.
    anterior = banco.buscar(pasta.drive_id)
    if (anterior is not None and anterior["status"] == St.A_CONFIRMAR
            and anterior["astrea_contato_id"]):
        banco.concluir(pasta.drive_id, St.JA_CADASTRADO, ficha.nome, ficha.cpf,
                       detalhe="Cadastro da rodada anterior confirmado (id %s)."
                               % anterior["astrea_contato_id"],
                       astrea_contato_id=anterior["astrea_contato_id"],
                       confianca=ficha.confianca, dados=ficha.como_dict())
        resumo.ja_existiam += 1
        log.ok("Cadastro da rodada anterior confirmado — nada foi criado de novo.")
        return ficha

    cadastro = adaptador.cadastrar_contato(ficha)

    if not adaptador.escreve_no_astrea or config.test_mode:
        banco.concluir(pasta.drive_id, St.SIMULADO, ficha.nome, ficha.cpf,
                       detalhe=cadastro.detalhe, confianca=ficha.confianca,
                       dados=ficha.como_dict())
        resumo.simulados += 1
        log.registrar_resultado(pasta.nome_pasta, ficha.nome, ficha.cpf,
                                "Cadastro (simulado)", St.SIMULADO)
        return ficha

    # Enviado mas ainda não confirmado NÃO é erro: o Astrea demora a indexar o
    # que acabou de gravar. Fica marcado para a rodada seguinte conferir pelo
    # CPF — que é o primeiro passo deste mesmo fluxo — antes de qualquer nova
    # tentativa. Tratar isso como erro foi o que duplicou o Wladson.
    if getattr(cadastro, "a_confirmar", False):
        banco.concluir(pasta.drive_id, St.A_CONFIRMAR, ficha.nome, ficha.cpf,
                       detalhe=cadastro.detalhe,
                       astrea_contato_id=cadastro.astrea_id,
                       confianca=ficha.confianca, dados=ficha.como_dict())
        resumo.pendentes += 1
        log.alerta("CADASTRO A CONFIRMAR — %s" % cadastro.detalhe)
        return ficha

    if not cadastro.sucesso:
        banco.concluir(pasta.drive_id, St.ERRO, ficha.nome, ficha.cpf,
                       detalhe=cadastro.detalhe, erro=cadastro.erro,
                       confianca=ficha.confianca, dados=ficha.como_dict())
        resumo.erros += 1
        log.erro("ERRO NO CADASTRO — %s" % (cadastro.erro or cadastro.detalhe))
        return ficha

    # --- caso -----------------------------------------------------------
    status_caso, caso_id = None, None
    if not config.astrea_criar_caso:
        # Escopo atual: só o contato. O que foi extraído para o caso fica
        # registrado para abertura manual, em vez de sumir.
        if ficha.tipo_acao.preenchido:
            status_caso = "CASO NÃO CRIADO (fora do escopo atual) — %s%s" % (
                ficha.tipo_acao.valor,
                (" contra %s" % ficha.banco_adverso.valor)
                if ficha.banco_adverso.preenchido else "")
            log.info("Caso não criado (escopo atual é só o contato). Para abrir "
                     "à mão: %s%s" % (ficha.tipo_acao.valor,
                                      (" — %s" % ficha.banco_adverso.valor)
                                      if ficha.banco_adverso.preenchido else ""))
    elif config.astrea_criar_caso:
        try:
            caso = adaptador.criar_caso(ficha, cadastro.astrea_id)
            if caso.sucesso:
                status_caso, caso_id = "CASO CRIADO", caso.astrea_id
                log.ok("Caso criado no Astrea.")
            else:
                status_caso = "CASO PENDENTE: %s" % (caso.erro or caso.detalhe)
                log.alerta("Contato cadastrado, mas o caso não foi criado: %s"
                           % (caso.erro or caso.detalhe))
        except Exception as erro:
            status_caso = "CASO PENDENTE: %s" % erro
            log.alerta("Contato cadastrado; falha ao criar o caso: %s" % erro)

    banco.concluir(pasta.drive_id, St.CADASTRADO, ficha.nome, ficha.cpf,
                   detalhe=cadastro.detalhe,
                   astrea_contato_id=cadastro.astrea_id,
                   astrea_caso_id=caso_id, status_caso=status_caso,
                   confianca=ficha.confianca, dados=ficha.como_dict())
    resumo.cadastrados += 1
    log.registrar_resultado(pasta.nome_pasta, ficha.nome, ficha.cpf,
                            "Cadastro no Astrea", St.CADASTRADO,
                            astrea_id=cadastro.astrea_id)
    log.ok("CADASTRADO COM SUCESSO%s."
           % ((" (id %s)" % cadastro.astrea_id) if cadastro.astrea_id else ""))
    return ficha
