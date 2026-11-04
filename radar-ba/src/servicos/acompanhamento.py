"""Acompanhamento dos processos de Busca e Apreensão já conhecidos.

Enquanto o radar por CPF/nome pergunta "surgiu processo novo?", este módulo
pergunta "o que andou no processo que já conhecemos?" — e procura os dois
eventos que mudam a urgência do caso:

    LIMINAR DEFERIDA   o juiz autorizou a apreensão
    MANDADO EXPEDIDO   o oficial já pode buscar o veículo

A fonte é o DJEN consultado por NÚMERO DO PROCESSO. Esse caminho não sofre o
cego estrutural da busca por nome: a publicação é encontrada pelo número mesmo
quando a intimação foi dirigida só ao advogado do banco — que é justamente o
caso das primeiras decisões de uma busca e apreensão.

Custo: uma requisição por processo, por execução.
"""
import datetime
import json
import os

from src.config import ajustes
from src.servicos.classificador_movimentos import classificar_texto
from src.util.http import FalhaConsulta
from src.util.log import obter
from src.util import cnj

log = obter("acompanhamento")

EVENTOS_VISTOS = ajustes.PASTA_DADOS / "eventos_vistos.json"


def _carregar():
    if not EVENTOS_VISTOS.exists():
        return {}
    try:
        return json.loads(EVENTOS_VISTOS.read_text(encoding="utf-8"))
    except ValueError:
        log.error("eventos_vistos.json ilegível — recomeçando o histórico")
        return {}


def _gravar(dados):
    EVENTOS_VISTOS.parent.mkdir(parents=True, exist_ok=True)
    tmp = EVENTOS_VISTOS.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(str(tmp), str(EVENTOS_VISTOS))


def processos_a_acompanhar(clientes):
    """Devolve [(numero, cliente)] sem repetir número."""
    vistos = set()
    lista = []
    for c in clientes:
        for numero in (c.get("processos_busca") or []):
            chave = cnj.digitos(numero)
            if not chave or chave in vistos:
                continue
            vistos.add(chave)
            lista.append((numero, c))
    return lista


def acompanhar(clientes, djen, dias=7, hoje=None, ao_detectar=None):
    """Consulta cada processo conhecido e devolve os eventos NOVOS.

    `ao_detectar(evento, resultado, cliente)` é chamado para cada novidade.
    """
    hoje = hoje or datetime.date.today()
    inicio = (hoje - datetime.timedelta(days=max(0, dias))).isoformat()
    historico = _carregar()
    novidades = []
    erros = []

    for numero, cliente in processos_a_acompanhar(clientes):
        try:
            dados = djen._consultar(
                numeroProcesso=cnj.digitos(numero),
                dataDisponibilizacaoInicio=inicio,
                dataDisponibilizacaoFim=hoje.isoformat(),
                itensPorPagina=100,
            )
        except FalhaConsulta as e:
            erros.append("%s: %s" % (numero, e))
            log.warning("falha ao acompanhar %s: %s", numero, e)
            continue

        for item in (dados.get("items") or []):
            texto = item.get("texto") or ""
            leitura = classificar_texto(texto, fonte="DJEN")
            for evento in leitura.eventos:
                base = "%s|%s" % (cnj.digitos(numero), evento.tipo)
                chave = "%s|%s" % (base, item.get("data_disponibilizacao"))
                if chave in historico:
                    continue
                # "Liminar deferida" é um fato, não um evento por publicação:
                # ele é mencionado de novo em cada despacho seguinte. O
                # histórico guarda cada menção, mas só a PRIMEIRA vira aviso —
                # senão um processo antigo dispara o mesmo alerta cinco vezes.
                ja_avisado = any(k.startswith(base + "|") for k in historico)
                historico[chave] = {
                    "processo": numero,
                    "tribunal": item.get("siglaTribunal"),
                    "evento": evento.tipo,
                    "data": item.get("data_disponibilizacao"),
                    "cliente_id": cliente.get("id"),
                    "confianca": evento.confianca,
                    "detectado_em": hoje.isoformat(),
                }
                if ja_avisado:
                    continue
                registro = dict(historico[chave])
                registro["trecho"] = evento.trecho
                registro["orgao"] = item.get("nomeOrgao", "")
                registro["urgente"] = evento.urgente
                novidades.append((registro, cliente))
                if ao_detectar:
                    ao_detectar(registro, cliente)

    _gravar(historico)
    return novidades, erros
