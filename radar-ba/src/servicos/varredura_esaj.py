"""Varredura da carteira por CPF/CNPJ no e-SAJ.

Responde ao objetivo A do escritório: *houve distribuição de busca e apreensão
nova contra este cliente?* — perguntando pelo documento, não pelo nome.

É o único caminho testado que confirma identidade. E, diferente do DJEN por
nome, não depende de ter havido publicação: o processo aparece assim que é
distribuído, mesmo que a única intimação até agora tenha sido dirigida ao
advogado do banco.

Alcance (medido em 18/08/2026): TJAL, TJAC, TJAM, TJCE — e TJSP apenas para o
acervo anterior à migração para o eproc.
"""
import datetime
import json
import os

from src.config import ajustes
from src.provedores.esaj.cliente import UF_PARA_TRIBUNAL, ProvedorESAJ
from src.seguranca import documento as sdoc
from src.util import cnj
from src.util.log import obter

log = obter("varredura-esaj")

ACHADOS = ajustes.PASTA_DADOS / "esaj_achados.json"


def _carregar():
    if not ACHADOS.exists():
        return {}
    try:
        return json.loads(ACHADOS.read_text(encoding="utf-8"))
    except ValueError:
        log.error("esaj_achados.json ilegível — recomeçando")
        return {}


def _gravar(dados):
    ACHADOS.parent.mkdir(parents=True, exist_ok=True)
    tmp = ACHADOS.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(str(tmp), str(ACHADOS))


def alcancaveis(clientes):
    """[(cliente, tribunal)] — só quem está em estado com e-SAJ por documento."""
    pares = []
    for c in clientes:
        for uf in (c.get("ufs") or []):
            tribunal = UF_PARA_TRIBUNAL.get(uf)
            if tribunal:
                pares.append((c, tribunal))
    return pares


def varrer(clientes, hoje=None, ao_achar=None, provedores=None):
    """Consulta cada cliente no e-SAJ do seu estado.

    Devolve (achados_novos, ja_conhecidos, erros).
    """
    hoje = hoje or datetime.date.today()
    historico = _carregar()
    provedores = provedores or {}
    novos, conhecidos, erros = [], [], []

    for cliente, tribunal in alcancaveis(clientes):
        provedor = provedores.get(tribunal)
        if provedor is None:
            try:
                provedor = ProvedorESAJ(tribunal)
            except ValueError:
                continue
            provedores[tribunal] = provedor
        try:
            documento = sdoc.decifrar(cliente["cpf_cifrado"])
        except Exception as e:
            erros.append("cliente %s: não foi possível decifrar o documento (%s)"
                         % (cliente.get("id"), e))
            continue
        try:
            resultados = provedor.buscar_por_cpf(documento, cliente_id=cliente.get("id"),
                                                 nome_cliente=cliente.get("nome"))
        except Exception as e:
            erros.append("cliente %s em %s: %s" % (cliente.get("id"), tribunal, e))
            continue

        for r in resultados:
            if r.status_casamento != "CONFIRMED_MATCH" or not r.numero_processo:
                if r.motivo:
                    erros.append("%s: %s" % (tribunal, r.motivo))
                continue
            chave = "%s|%s" % (cnj.digitos(r.numero_processo), cliente.get("id"))
            registro = {
                "processo": r.numero_processo,
                "tribunal": r.tribunal,
                "classe": r.classe_nome,
                "banco": r.banco_normalizado,
                "orgao": r.orgao_julgador,
                "distribuicao": r.data_distribuicao,
                "cliente_id": cliente.get("id"),
                "ano": cnj.ano(r.numero_processo),
                "confianca": r.confianca,
            }
            if chave in historico:
                conhecidos.append((registro, cliente))
                continue
            registro["detectado_em"] = hoje.isoformat()
            historico[chave] = registro
            novos.append((registro, cliente))
            if ao_achar:
                ao_achar(registro, cliente, r)

    _gravar(historico)
    return novos, conhecidos, erros
