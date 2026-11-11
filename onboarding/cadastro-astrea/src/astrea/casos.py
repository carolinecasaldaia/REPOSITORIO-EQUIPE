#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Abertura do caso e das tarefas iniciais no Astrea.

Só é chamado depois que a ENTRADA está confirmada como paga — regra do
escritório (18/08/2026). Desde 22/09/2026 a confirmação é automática, pela
API do Asaas (ver `src/asaas.py` e `executar.abrir_casos_com_entrada_paga`) —
ninguém escolhe cliente a cliente mais.

O que foi aprendido na tela e está codificado aqui:

- O caso se abre pelo ADICIONAR da ficha do contato → "Caso". O campo CLIENTE é
  obrigatório e **não vem preenchido**; é um campo de sugestão — só vale se a
  opção for CLICADA.
- PASTA e TÍTULO usam a mesma nomenclatura ("COMERCIAL - REVISIONAL VEICULAR").
- DESCRIÇÃO é a cláusula 1ª do contrato; acesso PÚBLICO (o rádio é invisível,
  precisa de force); o responsável do caso fica "Claude", que é o usuário da
  automação — decisão dela.
- A janela de tarefa é React e **tem um SALVAR próprio dentro dela**; o
  `get_by_role("button", name="SALVAR")` acha o botão da página de trás e
  trava. Por isso tudo aqui é escopado em [data-testid=floating-page].
"""

import json
import os
import re
import time
import unicodedata

MINUSCULAS = ("de", "da", "do", "das", "dos", "e")

# Nomenclatura de PASTA/TÍTULO e da tarefa inicial, por tipo de ação.
TIPOS = {
    "REVISIONAL VEICULAR": "PETICIONAR INICIAL - REVISIONAL VEICULAR",
    "REVISIONAL EMPRÉSTIMO": "PETICIONAR INICIAL - REVISIONAL EMPRÉSTIMO",
    "REVISIONAL CARTÃO DE CRÉDITO": "PETICIONAR INICIAL - REVISIONAL CARTÃO DE CRÉDITO",
    "BUSCA E APREENSÃO": "PETICIONAR DEFESA - BUSCA E APREENSÃO",
    "CÍVEL": "PETICIONAR INICIAL - CÍVEL",
}

# Responsável de cada tipo (nomes como aparecem no Astrea). Quem manda é o
# arquivo "RESPONSÁVEIS DAS TAREFAS.txt" na pasta do projeto, que ela edita
# quando a equipe muda; esta tabela só vale se o arquivo sumir ou vier vazio.
ARQUIVO_RESPONSAVEIS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "RESPONSÁVEIS DAS TAREFAS.txt")

RESPONSAVEIS_PADRAO = {
    "REVISIONAL VEICULAR": "Emerson Medeiros",      # era Pablo Cabral até 22/09/2026
    "REVISIONAL EMPRÉSTIMO": "Emerson Medeiros",
    "REVISIONAL CARTÃO DE CRÉDITO": "Emerson Medeiros",
    "BUSCA E APREENSÃO": "Ana Carolina",
    "CÍVEL": "Samantha",
    "NEGOCIAR EXTRAJUDICIAL": "Luysa",
}


def ler_responsaveis(caminho=ARQUIVO_RESPONSAVEIS) -> dict:
    """Tabela padrão, sobrescrita pelo que o arquivo de responsáveis disser."""
    tabela = dict(RESPONSAVEIS_PADRAO)
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            linhas = arquivo.read().splitlines()
    except OSError:
        return tabela
    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        tipo, nome = (parte.strip() for parte in linha.split("=", 1))
        if tipo and nome:
            tabela[tipo.upper()] = nome
    return tabela


RESPONSAVEIS = ler_responsaveis()

# Correção manual do tipo, por cliente. O contrato de honorários nem sempre
# descreve o caso que será aberto: o da Dione (19/10/2026) fala em Ação
# Revisional de Empréstimo com garantia de veículo, e o caso é defesa em
# busca e apreensão. Em vez de adivinhar pelo valor ou pela descrição da
# cobrança, ela escreve o tipo certo no arquivo e a automação obedece.
ARQUIVO_CORRECOES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "TIPO DE AÇÃO - CORREÇÕES.txt")


def _sem_acento(texto: str) -> str:
    cru = unicodedata.normalize("NFD", (texto or "").strip().upper())
    return "".join(c for c in cru if unicodedata.category(c) != "Mn")


def ler_correcoes_de_tipo(caminho=ARQUIVO_CORRECOES) -> dict:
    """{nome normalizado: TIPO} lido do arquivo de correções."""
    correcoes = {}
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            linhas = arquivo.read().splitlines()
    except OSError:
        return correcoes
    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        quem, tipo = (parte.strip() for parte in linha.split("=", 1))
        tipo_limpo = _sem_acento(tipo)
        casa = [t for t in TIPOS if _sem_acento(t) == tipo_limpo]
        if quem and casa:
            correcoes[_sem_acento(quem)] = casa[0]
    return correcoes


# Autorização de matéria nova. Cliente que já tem processo/caso no Astrea não
# recebe caso automático (ver `_contar_processos_e_casos`): pode ser a mesma
# matéria de sempre. Quando ela confirma que é matéria nova — o Daniel Cedrim
# tinha um Superendividamento ativo e contratou uma busca e apreensão em
# 20/10/2026 —, o nome entra neste arquivo e o caso é aberto normalmente.
ARQUIVO_MATERIA_NOVA = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "MATÉRIA NOVA - AUTORIZAÇÕES.txt")


def ler_materias_novas(caminho=ARQUIVO_MATERIA_NOVA) -> dict:
    """{nome normalizado: motivo} dos clientes com matéria nova autorizada."""
    autorizados = {}
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            linhas = arquivo.read().splitlines()
    except OSError:
        return autorizados
    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        quem, motivo = (parte.strip() for parte in linha.split("=", 1))
        if quem:
            autorizados[_sem_acento(quem)] = motivo or "autorizado por ela"
    return autorizados


def materia_nova(*nomes, autorizacoes=None) -> str:
    """Motivo autorizado para este cliente, ou "" se ele não está na lista."""
    tabela = ler_materias_novas() if autorizacoes is None else autorizacoes
    for nome in nomes:
        motivo = tabela.get(_sem_acento(nome))
        if motivo:
            return motivo
    return ""


def tipo_corrigido(tipo, *nomes, correcoes=None) -> str:
    """
    O tipo que vale para este cliente: o do arquivo de correções, se houver.

    `nomes` são as formas de chamar o mesmo cliente (nome do cadastro, nome
    da pasta) — basta uma bater.
    """
    tabela = ler_correcoes_de_tipo() if correcoes is None else correcoes
    for nome in nomes:
        achado = tabela.get(_sem_acento(nome))
        if achado:
            return achado
    return tipo

# Tarefas que acompanham todo caso, sempre em CAIXA ALTA.
TAREFAS_COMUNS = ("ENVIAR ONBOARDING", "PROTOCOLAR INICIAL",
                  "INFORMAR PROTOCOLO", "INCLUIR NA PLANILHA")

# Veículo apreendido acrescenta o agravo (regra do documento de nomenclatura).
TAREFA_AGRAVO = "PETICIONAR AGRAVO DE INSTRUMENTO"

# Usuário do Astrea com que a automação está logada. Serve para diferenciar
# "caso que a própria automação criou" (pode completar tarefa que faltou,
# ex.: Eber, 18/09/2026) de "caso que já existia por conta de uma pessoa"
# (nunca mexer — foi mexer nisso que gerou o retrabalho de 22/09/2026).
USUARIO_AUTOMACAO = "Claude"


def tipo_do_contrato(tipo_acao: str) -> str:
    """Traduz o que o contrato diz para a nomenclatura do escritório."""
    alvo = (tipo_acao or "").lower()
    if "busca" in alvo:
        return "BUSCA E APREENSÃO"
    if "obriga" in alvo or "dano" in alvo or "cível" in alvo or "civel" in alvo:
        return "CÍVEL"
    if "empr" in alvo:
        return "REVISIONAL EMPRÉSTIMO"
    if "cart" in alvo:
        return "REVISIONAL CARTÃO DE CRÉDITO"
    if "revisional" in alvo:
        return "REVISIONAL VEICULAR"
    return ""


def nome_no_padrao(nome: str) -> str:
    partes = (nome or "").strip().lower().split()
    return " ".join(p if (p in MINUSCULAS and i > 0) else p.capitalize()
                    for i, p in enumerate(partes))


def _limpar_campo(pagina):
    pagina.keyboard.press("Meta+A")
    pagina.keyboard.press("Backspace")
    time.sleep(0.3)


def padrao_tolerante(alvo):
    """
    Padrão que casa o nome mesmo que as partículas não batam.

    O contrato escreve "DANIEL CEDRIM OLIVEIRA" e o contato no Astrea é
    "Daniel Cedrim de Oliveira" (20/10/2026). São a mesma pessoa, mas a
    comparação literal não achava a sugestão e o caso não abria. Aqui as
    partículas (de, da, do, e) passam a ser opcionais ENTRE os nomes; os
    nomes em si continuam todos obrigatórios e na mesma ordem, para não
    clicar em outro cliente.
    """
    partes = [re.escape(p) for p in (alvo or "").split()
              if p.lower() not in MINUSCULAS]
    if not partes:
        return None
    meio = r"\s+(?:(?:%s)\s+)*" % "|".join(MINUSCULAS)
    return re.compile(meio.join(partes), re.I)


def _esperar_sugestao(pagina, alvo, segundos=25):
    """
    Espera a opção aparecer e devolve o elemento clicável (ou None).

    Procura primeiro o texto exato; só depois aceita a diferença de
    partículas (ver `padrao_tolerante`). A ordem importa: havendo a opção
    exata, é nela que se clica.
    """
    tolerante = padrao_tolerante(alvo)
    fim = time.time() + segundos
    while time.time() < fim:
        for procura in [alvo] + ([tolerante] if tolerante is not None else []):
            opcao = pagina.locator("li,a").filter(has_text=procura)
            try:
                if opcao.count() > 0 and opcao.last.is_visible():
                    return opcao.last
            except Exception:
                pass
        pagina.wait_for_timeout(400)
    return None


# O Astrea às vezes abre um "guia de primeiro acesso" por cima de tudo. Ele não
# é um painel qualquer: cobre a tela inteira e **engole todos os cliques** —
# o Playwright diz "subtree intercepts pointer events" e desiste. Derrubou o
# cadastro do Wladson duas vezes em 08/09/2026, e não some sozinho.
GUIA_INICIAL = "first-xp-module-react, [class*=first-xp], [data-testid=first-xp-module]"


class SessaoCaiu(RuntimeError):
    """A tela é a de login: não adianta procurar botão nenhum."""


# Marcas da tela de login do Astrea. A automação faz login a cada execução, mas
# a sessão pode cair no meio — e aí TODO clique falha por "tempo esgotado",
# mensagem que não diz o que houve. Em 09/09/2026 isso me custou duas rodadas
# consertando o que não estava quebrado.
SINAIS_DE_LOGIN = ("ESQUECEU SUA SENHA", "AINDA NÃO TEM CONTA NO ASTREA")


def conferir_sessao(pagina):
    """Levanta SessaoCaiu quando o Astrea devolveu a tela de login."""
    try:
        texto = (pagina.evaluate("() => document.body.innerText") or "").upper()
    except Exception:
        return
    if any(sinal in texto for sinal in SINAIS_DE_LOGIN):
        raise SessaoCaiu(
            "A sessão do Astrea caiu — a tela mostrada é a de login. Entre de "
            "novo (o adaptador faz isso) antes de abrir caso ou tarefa.")


def fechar_guia_inicial(pagina) -> bool:
    """Fecha o guia de primeiro acesso do Astrea. Devolve True se havia um."""
    try:
        guia = pagina.locator(GUIA_INICIAL)
        if not guia.count():
            return False
        for rotulo in ("Fechar", "Pular", "Entendi", "Começar", "×"):
            botao = guia.first.get_by_text(rotulo, exact=False)
            try:
                if botao.count() and botao.first.is_visible():
                    botao.first.click(timeout=5000)
                    pagina.wait_for_timeout(1200)
                    if not pagina.locator(GUIA_INICIAL).count():
                        return True
            except Exception:
                pass
        # Sem botão que funcione, tira da frente pelo DOM: o guia é enfeite,
        # e ficar preso nele custa a rodada inteira.
        pagina.evaluate("""(seletor) => {
            document.querySelectorAll(seletor).forEach(el => el.remove());
        }""", GUIA_INICIAL)
        pagina.wait_for_timeout(600)
        return True
    except Exception:
        return False


def fechar_paineis(pagina):
    """
    Fecha painel de tarefa que tenha ficado aberto.

    Não é zelo excessivo: em 18/08/2026 uma tarefa falhou no meio, o painel
    (`floating-page`) continuou aberto e passou a **interceptar todos os
    cliques** — os seis clientes seguintes falharam em sequência por causa
    disso, sem relação com os dados deles.
    """
    fechar_guia_inicial(pagina)
    try:
        painel = pagina.locator("[data-testid=floating-page]")
        if painel.count() and painel.first.is_visible():
            cancelar = painel.first.get_by_text("CANCELAR", exact=False)
            if cancelar.count():
                cancelar.last.click()
            else:
                pagina.keyboard.press("Escape")
            pagina.wait_for_timeout(1500)
    except Exception:
        pass


def _sugerir(pagina, texto, alvo, pausa=0.3, preferir_completo=False):
    """
    Campo de sugestão do Astrea: digitar, ESPERAR a opção e CLICAR nela.

    Duas lições que custaram uma rodada inteira (18/08/2026):

    1. **Digitar duas palavras não devolve nada.** "Jhonatas Macedo" volta
       vazio; "Jhonatas" traz a sugestão em ~4 s. Por isso a busca começa pela
       primeira palavra e só depois tenta mais.
    2. Tempo fixo de espera não serve — às vezes leva 4 s, às vezes mais. A
       espera é ativa, até 14 s por tentativa.

    O texto digitado é só para procurar; quem manda no clique é `alvo`, que é o
    nome completo.
    """
    # Cada campo tem seu jeito, medido na tela em 18/08/2026:
    #   cliente do caso  -> a PRIMEIRA palavra é o que traz sugestão
    #   vínculo da tarefa -> só o nome COMPLETO devolve o caso certo
    #                        ("COMERCIAL" traz casos de outros clientes)
    palavras = (texto or "").split()
    tentativas = [texto] if preferir_completo else []
    if palavras:
        tentativas.append(palavras[0])
        if len(palavras) > 1:
            tentativas.append(" ".join(palavras[:2]))
        # Primeiro nome comum derruba a busca: "Juliana" traz outras Julianas do
        # escritório e a lista de sugestões, que é curta, corta justamente o caso
        # que queríamos (01/09/2026 — as 5 tarefas dela falharam por isso). Então
        # tenta também os outros nomes, do mais longo para o mais curto, que é
        # uma aposta razoável de qual é o mais raro.
        outros = [p for p in palavras[1:] if p.lower() not in MINUSCULAS]
        tentativas.extend(sorted(outros, key=len, reverse=True))
    if texto not in tentativas:
        tentativas.append(texto)
    vistos, unicas = set(), []
    for tentativa in tentativas:
        if tentativa not in vistos:
            vistos.add(tentativa)
            unicas.append(tentativa)
    tentativas = unicas

    for tentativa in tentativas:
        if not tentativa.strip():
            continue
        _limpar_campo(pagina)
        for letra in tentativa:
            pagina.keyboard.type(letra)
            time.sleep(pausa)
        opcao = _esperar_sugestao(pagina, alvo)
        if opcao is not None:
            opcao.click()
            time.sleep(1.5)
            return True
    raise RuntimeError("O Astrea não sugeriu %r (digitei %r)" % (alvo, tentativas))


# Quanto esperar o Astrea indexar o caso recém-salvo, e quantas vezes insistir
# numa tarefa que não achou o caso. Ver ESPERA_APOS_SALVAR / abrir_lote.
ESPERA_APOS_SALVAR = 30
TENTATIVAS_DA_TAREFA = 3
ESPERA_ENTRE_TENTATIVAS = 40


def abrir_caso(pagina, contato_id, cliente, tipo, descricao, observacao="",
               espera=ESPERA_APOS_SALVAR, tentativas=2, materia_nova=""):
    """
    Cria o caso e devolve (título, criado, resumo_bloqueio).

    `criado` é True (criou agora), False (já existia com este título) ou
    None (recusou criar — cliente já tem processo/caso anterior sob outro
    título; `resumo_bloqueio` traz o que já existe, para conferência manual).

    Insiste quando o Astrea trava no meio — instabilidade dele, que aconteceu
    duas vezes em dois dias. **Repetir é seguro** porque a primeira coisa que
    a função faz é olhar se o caso já está na ficha: se estiver, devolve sem
    criar nada. Sem essa conferência, insistir duplicaria caso.
    """
    ultimo = None
    for numero in range(1, max(1, tentativas) + 1):
        try:
            return _abrir_caso(pagina, contato_id, cliente, tipo, descricao,
                               observacao, espera, materia_nova)
        except SessaoCaiu:
            raise                       # insistir com a sessão caída é só perder tempo
        except Exception as erro:
            ultimo = erro
            fechar_paineis(pagina)
            if numero < tentativas:
                time.sleep(ESPERA_ENTRE_TENTATIVAS)
    raise ultimo


def _contar_processos_e_casos(pagina) -> int:
    """
    Quantos processos/casos a ficha do cliente já lista, ANTES de a
    automação criar qualquer coisa. Cliente realmente novo tem zero.

    Número maior que zero é sinal de que o cliente já tem matéria em
    andamento rastreada de outro jeito — um "Processo" (não um "Caso") de
    antes desta automação existir, por exemplo. Foi exatamente isso que
    aconteceu com o Bruno Helder Gomes Teofilo em 22/09/2026: cliente antigo,
    defesa já protocolada num Processo de 2025, e a automação abriu um "Caso
    COMERCIAL" do zero — com o kit inteiro de tarefas de início — para uma
    matéria que já estava em andamento.
    """
    texto = pagina.evaluate("() => document.body.innerText") or ""
    m = re.search(r"(\d+)\s+de\s+\d+\s+processos?\s+e\s+casos?", texto, re.I)
    return int(m.group(1)) if m else 0


def _resumo_processos_e_casos(pagina) -> str:
    """
    Texto bruto da lista "Processos e casos" da ficha do cliente, para quem
    for decidir se é a MESMA matéria (mesmo contrato, mesmo veículo) ou uma
    NOVA (cliente que voltou a comprar do escritório).

    Decisão dela (23/09/2026): a automação nunca decide isso sozinha — só
    junta a informação (título, ação/foro, data de cada item já existente)
    e devolve para conferência manual. O formato da tela não é estável o
    bastante para recortar título/ação com segurança; melhor entregar o
    trecho bruto do que arriscar cortar errado e esconder informação.
    """
    texto = pagina.evaluate("() => document.body.innerText") or ""
    m = re.search(r"\d+\s+de\s+\d+\s+processos?\s+e\s+casos?", texto, re.I)
    inicio = m.start() if m else texto.lower().find("processos e casos")
    if inicio < 0:
        return ""
    linhas = [l.strip() for l in texto[inicio:].splitlines() if l.strip()]
    return "\n".join(linhas[:50])


def _abrir_caso(pagina, contato_id, cliente, tipo, descricao, observacao="",
                espera=ESPERA_APOS_SALVAR, materia_nova=""):
    fechar_paineis(pagina)
    titulo = "COMERCIAL - " + tipo
    pagina.goto("https://astrea.net.br/#/main/contacts/detail/%s/folders" % contato_id,
                wait_until="domcontentloaded", timeout=60000)
    time.sleep(8)
    conferir_sessao(pagina)
    # O guia de primeiro acesso reaparece DEPOIS da navegação, não antes.
    fechar_guia_inicial(pagina)
    if titulo in pagina.evaluate("() => document.body.innerText"):
        return titulo, False, None                  # já existia; não duplica

    if _contar_processos_e_casos(pagina) > 0 and not materia_nova:
        # Cliente já tem processo/caso anterior sob outro título — não é
        # necessariamente matéria nova (pode ser cliente que voltou a
        # comprar), mas também pode ser a mesma matéria de sempre. A
        # automação NUNCA decide isso sozinha — regra dela, 23/09/2026:
        # "se houver dúvidas, sempre questionar". `criado=None` é o terceiro
        # estado: nem criou, nem achou o mesmo caso — só recusou, com o
        # resumo do que já existe, para conferência manual (ver `abrir_lote`).
        return titulo, None, _resumo_processos_e_casos(pagina)

    pagina.get_by_role("button", name="ADICIONAR", exact=False).first.click()
    time.sleep(3)
    pagina.get_by_text("Caso", exact=True).first.click()
    time.sleep(7)

    campo = pagina.locator("[ng-model='customer.name']").first
    campo.click()
    _sugerir(pagina, " ".join(cliente.split()[:2]), cliente)

    for chave, valor in (("case.file", titulo), ("case.title", titulo),
                         ("case.description", descricao), ("case.observation", observacao)):
        if not valor:
            continue
        alvo = pagina.locator("[ng-model='%s']" % chave).first
        alvo.click()
        alvo.fill(valor)
        time.sleep(0.4)

    pagina.locator("#casePublicPermission").first.check(force=True)
    pagina.get_by_role("button", name="SALVAR", exact=False).first.click()
    # O Astrea demora para indexar o que acabou de salvar: sem esta pausa, a
    # busca do vínculo da tarefa não encontra o caso e a tarefa falha (medido
    # em 4 clientes, 18/08/2026). Em lote, `abrir_lote` passa uma espera curta:
    # quem dá o tempo ali é a fila de casos que roda antes das tarefas.
    time.sleep(espera)
    return titulo, True, None


def abrir_tarefa(pagina, url_caso, titulo_caso, cliente, tarefa, responsavel, data,
                 tentativas=TENTATIVAS_DA_TAREFA):
    """
    Cria a tarefa, insistindo enquanto o Astrea ainda não indexou o caso.

    A falha é sempre a mesma — "não sugeriu 'COMERCIAL - ...'" — e some sozinha
    depois de algumas dezenas de segundos. Insistir aqui é o que impede que a
    primeira tarefa de cada caso novo caia (aconteceu com o Djacy e com o
    Adeson, 24/08 e 01/09/2026).
    """
    ultimo = None
    for numero in range(1, max(1, tentativas) + 1):
        try:
            return _abrir_tarefa(pagina, url_caso, titulo_caso, cliente, tarefa,
                                 responsavel, data)
        except SessaoCaiu:
            raise                       # insistir com a sessão caída é só perder tempo
        except Exception as erro:
            ultimo = erro
            fechar_paineis(pagina)          # senão o painel preso derruba o resto
            if numero < tentativas:
                time.sleep(ESPERA_ENTRE_TENTATIVAS)
    raise ultimo


# --- Tarefa pela API interna do Astrea (11/11/2026)
#
# Até 04/11/2026 a tarefa era criada pela TELA: o campo de vínculo era
# preenchido digitando o nome do cliente e clicando na primeira sugestão com o
# título "COMERCIAL - REVISIONAL VEICULAR". Esse título é o mesmo para todos
# os clientes, e o caso recém-criado ainda não aparecia na busca: as 3
# primeiras tarefas do Daniel Oliveira da Silva foram parar no caso do Carlos
# Daniel da Silva, e as do Felipe da Silva Ribeiro no da Priscila Ribeiro de
# Oliveira — e o log disse "5 tarefas, 0 falhas", porque nada conferia.
# Agora a tarefa é gravada direto no caso pelo NÚMERO dele (o mesmo que está
# na URL da pasta), e só conta como criada depois de relida no próprio caso.
APP = "https://app.astrea.net.br"
ENDP = APP + "/_ah/api"
USUARIO_ASTREA = "5487223873241088"     # conta Claude
TENANT = "6406437268422656"
_CREDENCIAIS = {}


def caso_id_da_url(url_caso: str) -> str:
    m = re.search(r"/folders/detail/(\d+)", url_caso or "")
    if not m:
        raise RuntimeError("não achei o número do caso na URL %r" % url_caso)
    return m.group(1)


def _credencial(pagina) -> str:
    """O token da sessão, pego de uma requisição que o próprio site faz."""
    chave = id(pagina)
    if _CREDENCIAIS.get(chave):
        return _CREDENCIAIS[chave]

    def ao_pedir(req):
        if req.url.startswith(APP + "/") and "authorization" in req.headers:
            _CREDENCIAIS[chave] = req.headers["authorization"]
    pagina.on("request", ao_pedir)
    for rota in ("#/main/workspace", "#/main/contacts"):
        pagina.goto("https://astrea.net.br/" + rota, wait_until="domcontentloaded", timeout=60000)
        conferir_sessao(pagina)
        for _ in range(25):
            if _CREDENCIAIS.get(chave):
                return _CREDENCIAIS[chave]
            pagina.wait_for_timeout(1000)
    raise RuntimeError("não consegui a credencial da sessão do Astrea")


def _api(pagina, caminho, corpo=None):
    cab = {"authorization": _credencial(pagina), "content-type": "application/json"}
    url = ENDP + caminho
    if corpo is None:
        r = pagina.request.get(url, headers=cab, timeout=120000)
    else:
        r = pagina.request.post(url, headers=cab, data=json.dumps(corpo), timeout=120000)
    if r.status not in (200, 204):
        if r.status in (401, 403):
            _CREDENCIAIS.pop(id(pagina), None)
        raise RuntimeError("Astrea respondeu %s em %s: %s"
                           % (r.status, caminho.split("?")[0], r.text()[:200]))
    try:
        return r.json()
    except Exception:
        return {}


def _tarefas_no_caso(pagina, caso_id) -> list:
    r = _api(pagina, "/workspace/v1/getTasksByCase?caseId=%s&userId=%s"
             % (caso_id, USUARIO_ASTREA), {})
    return [((t.get("description") or "").strip().upper(), aberta)
            for chave, aberta in (("activeTasks", True), ("inactiveTasks", False))
            for t in (r.get(chave) or [])]


def _id_do_responsavel(pagina, nome) -> str:
    r = _api(pagina, "/users/v1/getAllUsers?tenantId=%s" % TENANT, {})
    alvo = _sem_acento(nome)
    achados = [u for u in r.get("users", []) if u.get("status") == "ACTIVE"
               and alvo in _sem_acento((u.get("name") or "").strip())]
    if len(achados) != 1:
        raise RuntimeError("responsável %r: %s no Astrea" % (
            nome, "não encontrado" if not achados else "ambíguo"))
    return str(achados[0]["id"])


def _abrir_tarefa(pagina, url_caso, titulo_caso, cliente, tarefa, responsavel, data):
    """Cria a tarefa NO caso (pelo número dele) e confere relendo o caso."""
    caso_id = caso_id_da_url(url_caso)
    alvo = tarefa.strip().upper()
    # Não duplica: se a tentativa anterior gravou mas a conferência falhou,
    # a tarefa já está lá.
    if any(t == alvo and aberta for t, aberta in _tarefas_no_caso(pagina, caso_id)):
        return
    dia, mes, ano = data.split("/")
    itens = (_api(pagina, "/workspace/v1/listTaskListsByUser?userId=%s" % USUARIO_ASTREA)
             .get("items") or [])
    lista = ([i for i in itens if i.get("current")] or itens or [{}])[0].get("id")
    if not lista:
        raise RuntimeError("conta Claude sem lista de tarefas no Astrea")
    quem = _id_do_responsavel(pagina, responsavel)
    salva = _api(pagina, "/workspace/v1/saveTaskWithList", {
        "userId": USUARIO_ASTREA, "idUser": USUARIO_ASTREA, "idCurrentTaskList": lista,
        "responsibleId": quem, "rootCaseId": caso_id,
        "taskInfoDTO": {"caseId": caso_id, "description": tarefa,
                        "dueDate": "%s-%s-%s" % (ano, mes, dia), "responsibleId": quem,
                        "ownerId": USUARIO_ASTREA, "priority": 2, "involved": [],
                        "tagIds": [], "taskListIds": [lista], "done": False}})
    if not salva.get("id"):
        raise RuntimeError("o Astrea não devolveu o número da tarefa %s" % tarefa)
    if not any(titulo == alvo for titulo, _ in _tarefas_no_caso(pagina, caso_id)):
        raise RuntimeError("tarefa %s gravada mas não aparece no caso %s" % (tarefa, caso_id))


def tarefas_existentes(pagina, url_caso, tarefas) -> set:
    """
    Quais das `tarefas` o caso JÁ tem, lidas da aba Atividades.

    A aba Atividades é a única lista completa: o painel "Próximas atividades"
    mostra no máximo cinco, e foi lendo ele que o João Roberto ficou com
    INFORMAR PROTOCOLO duplicada (18/08/2026). Desde 11/11/2026 lê primeiro
    pela API, no próprio caso; a tela fica só de reserva.
    """
    try:
        no_caso = {titulo for titulo, _ in _tarefas_no_caso(pagina, caso_id_da_url(url_caso))}
        return {tarefa for tarefa in tarefas if tarefa.strip().upper() in no_caso}
    except SessaoCaiu:
        raise
    except Exception:
        pass
    pagina.goto(url_caso, wait_until="domcontentloaded", timeout=60000)
    time.sleep(7)
    conferir_sessao(pagina)
    fechar_guia_inicial(pagina)
    aba = pagina.get_by_text("Atividades", exact=False)
    try:
        if aba.count():
            aba.first.click()
            time.sleep(7)
    except Exception:
        pass
    corpo = (pagina.evaluate("() => document.body.innerText") or "").upper()
    return {tarefa for tarefa in tarefas if tarefa.upper() in corpo}


def tarefas_do_caso(tipo: str, apreendido=None) -> list:
    tarefas = [TIPOS.get(tipo, "")]
    if apreendido:
        tarefas.append(TAREFA_AGRAVO)
    return [t for t in tarefas if t] + list(TAREFAS_COMUNS)


def numero_cnj(processo: str) -> str:
    """
    "00356759220268160001" -> "0035675-92.2026.8.16.0001".

    O contrato às vezes traz o número com os 20 dígitos colados (João Paulo,
    21/09/2026). Número que não tem 20 dígitos volta como veio — não se inventa
    formatação para o que não é número CNJ.
    """
    digitos = "".join(c for c in (processo or "") if c.isdigit())
    if len(digitos) != 20:
        return (processo or "").strip()
    return "%s-%s.%s.%s.%s.%s" % (digitos[:7], digitos[7:9], digitos[9:13],
                                  digitos[13], digitos[14:16], digitos[16:])


def observacao_de_apreensao(estado: str, data: str, processo: str = "") -> str:
    """Formato pedido no documento de nomenclatura do escritório."""
    numero = numero_cnj(processo) if processo else "(não informado no contrato)"
    texto = ("Veículo apreendido no dia %s - Processo sob o nº %s - %s."
             % (data, numero, (estado or "").upper()))
    if not processo:
        texto += " Solicitar o número do processo ao setor comercial."
    return texto


def quem_criou_o_caso(pagina) -> str:
    """
    Lê "Criado por: <nome>" do cabeçalho da página do caso já aberta.

    Esse campo é o único jeito confiável de saber se foi a automação quem
    criou o caso (usuário `USUARIO_AUTOMACAO`) ou se já existia por conta de
    alguém da equipe — o nome da pasta e o "já existia" sozinhos não dizem
    isso.
    """
    texto = pagina.evaluate("() => document.body.innerText") or ""
    m = re.search(r"Criado por:\s*\n*\s*([^\n]+)", texto)
    return (m.group(1) or "").strip() if m else ""


def abrir_lote(pagina, itens, data, avisar=None):
    """
    Abre caso e tarefas de vários clientes, em duas voltas.

    Primeiro cria TODOS os casos; só depois volta para abrir as tarefas. O
    Astrea leva algumas dezenas de segundos para indexar um caso novo, e na
    ordem antiga — caso, tarefas, próximo cliente — quem pagava a espera era
    sempre a primeira tarefa de cada cliente, que falhava. Fazendo os casos
    primeiro, o tempo de abrir os outros clientes já serve de espera.

    `itens` é uma lista de dicionários com: id, cliente, tipo e, opcionais,
    descricao, observacao e apreendido. `avisar(texto)` recebe o andamento.

    Só mexe em tarefa de caso que JÁ EXISTIA se foi a própria automação quem
    o criou (usuário `USUARIO_AUTOMACAO`, ver `quem_criou_o_caso`) — sinal de
    que sobrou tarefa de uma rodada anterior que caiu no meio (Eber,
    18/09/2026). Caso que já existia por conta de uma pessoa da equipe nunca
    recebe tarefa daqui: pode estar em qualquer fase, e completar um "kit de
    início" nele foi o que gerou retrabalho e transtorno para a equipe em
    22/09/2026 — esses casos voltam como `nao_mexido: True`, para conferência
    manual.

    Também não cria caso NENHUM (`criado=None`, ver `_contar_processos_e_casos`)
    para cliente que já tem processo/caso anterior sob outro título — sinal
    de matéria antiga, não nova. Foi isso que aconteceu com o Bruno Helder
    Gomes Teofilo em 22/09/2026: cliente com defesa já protocolada num
    Processo de 2025, sem "Caso COMERCIAL" ainda, e a automação abriu um do
    zero. Esses também voltam como `nao_mexido: True`.

    Devolve [{cliente, titulo, criado, tarefas: [...], falhas: [(tarefa, erro)],
    nao_mexido?, criado_por?, bloqueado_historico?}]. Erro em um cliente não
    derruba os outros.
    """
    def conta(texto):
        if avisar:
            avisar(texto)

    autorizadas = ler_materias_novas()
    abertos = []
    for item in itens:
        try:
            # Matéria nova autorizada por ela: o cliente tem processo/caso
            # anterior, mas esta contratação é outra causa. Ver
            # `ler_materias_novas`.
            liberacao = materia_nova(item["cliente"],
                                     item.get("nome_cliente_bruto", ""),
                                     autorizacoes=autorizadas)
            if liberacao:
                conta("matéria nova autorizada (%s): %s"
                      % (liberacao, item["cliente"]))
            titulo, criado, resumo_bloqueio = abrir_caso(
                pagina, item["id"], item["cliente"], item["tipo"],
                item.get("descricao", ""), item.get("observacao", ""), espera=3,
                materia_nova=liberacao)
            abertos.append({"item": item, "titulo": titulo, "criado": criado,
                            "erro": None, "resumo_bloqueio": resumo_bloqueio})
            if criado is None:
                conta("caso NÃO aberto (cliente já tem processo/caso anterior): %s"
                     % item["cliente"])
            else:
                conta("caso %s: %s" % ("aberto" if criado else "já existia", item["cliente"]))
        except Exception as erro:
            fechar_paineis(pagina)
            abertos.append({"item": item, "titulo": "", "criado": False, "erro": erro,
                            "resumo_bloqueio": None})
            conta("caso NÃO aberto: %s — %s" % (item["cliente"], str(erro)[:70]))

    resultados = []
    for aberto in abertos:
        item, titulo = aberto["item"], aberto["titulo"]
        linha = {"cliente": item["cliente"], "titulo": titulo, "criado": aberto["criado"],
                 "tarefas": [], "falhas": []}
        if aberto["erro"] is not None:
            linha["falhas"].append(("(caso)", str(aberto["erro"])))
            resultados.append(linha)
            continue
        if aberto["criado"] is None:
            # Não criou nada de propósito: cliente já tem processo/caso
            # anterior (ver `_contar_processos_e_casos`). Não há caso nenhum
            # para entrar aqui.
            linha["nao_mexido"] = True
            linha["bloqueado_historico"] = True
            linha["processos_e_casos_anteriores"] = aberto.get("resumo_bloqueio") or ""
            resultados.append(linha)
            continue
        try:
            url_caso = _entrar_no_caso(pagina, item["id"], titulo)
        except Exception as erro:
            fechar_paineis(pagina)
            linha["falhas"].append(("(entrar no caso)", str(erro)))
            resultados.append(linha)
            conta("não consegui entrar no caso de %s" % item["cliente"])
            continue

        if not aberto["criado"]:
            criador = quem_criou_o_caso(pagina)
            linha["criado_por"] = criador
            if criador != USUARIO_AUTOMACAO:
                linha["nao_mexido"] = True
                conta("caso já existia (criado por %s) — tarefas não mexidas: %s"
                      % (criador or "?", item["cliente"]))
                resultados.append(linha)
                continue

        previstas = tarefas_do_caso(item["tipo"], item.get("apreendido"))
        # Caso que já existia pode já ter tarefas: cliente de mês anterior
        # (Eber, 18/09/2026) ou lote refeito depois de uma queda. Criar só o
        # que falta — o Astrea não impede tarefa repetida.
        try:
            ja_tem = tarefas_existentes(pagina, url_caso, previstas)
        except SessaoCaiu:
            raise
        except Exception:
            ja_tem = set()
        linha["ja_tinha"] = sorted(ja_tem)
        for tarefa in [t for t in previstas if t not in ja_tem]:
            try:
                abrir_tarefa(pagina, url_caso, titulo, item["cliente"], tarefa,
                             RESPONSAVEIS.get(item["tipo"], "Claude"), data)
                linha["tarefas"].append(tarefa)
            except Exception as erro:
                fechar_paineis(pagina)
                linha["falhas"].append((tarefa, str(erro)))
        conta("%s: %d tarefa(s), %d falha(s)"
              % (item["cliente"], len(linha["tarefas"]), len(linha["falhas"])))
        resultados.append(linha)
    return resultados


def _entrar_no_caso(pagina, contato_id, titulo, tentativas=TENTATIVAS_DA_TAREFA):
    """
    Abre a pasta do caso na ficha do contato e devolve a URL dele.

    Insiste pelo mesmo motivo das tarefas: o caso recém-salvo demora a aparecer.
    Com um cliente só no lote não há fila nenhuma para dar esse tempo, e a
    entrada falhava logo na primeira olhada (Wladson, 08/09/2026).
    """
    ultimo = None
    for numero in range(1, max(1, tentativas) + 1):
        try:
            fechar_guia_inicial(pagina)
            pagina.goto("https://astrea.net.br/#/main/contacts/detail/%s/folders" % contato_id,
                        wait_until="domcontentloaded", timeout=60000)
            time.sleep(8)
            conferir_sessao(pagina)
            fechar_guia_inicial(pagina)
            # Ir pelo LINK do caso, não pelo texto: o título aparece dentro de
            # uma célula de tabela que nem sempre aceita clique — o caso do
            # Wladson existia, estava na tela, e o clique no texto dava tempo
            # esgotado (08/09/2026).
            link = pagina.locator("a[href*='/main/folders/detail/']").first
            if link.count():
                destino = link.get_attribute("href") or ""
                if destino:
                    pagina.goto("https://astrea.net.br/" + destino.lstrip("/"),
                                wait_until="domcontentloaded", timeout=60000)
                    time.sleep(8)
                    return pagina.url
            pagina.get_by_text(titulo, exact=False).first.click(timeout=15000)
            time.sleep(8)
            return pagina.url
        except Exception as erro:
            ultimo = erro
            if numero < tentativas:
                time.sleep(ESPERA_ENTRE_TENTATIVAS)
    raise ultimo
