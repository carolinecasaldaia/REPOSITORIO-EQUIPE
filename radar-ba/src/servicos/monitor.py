"""Execução do monitoramento: varre, casa, classifica, prioriza e alerta.

Dois modos de varredura, ambos legítimos e testados:

  "nome"      — uma consulta por cliente no DJEN. Simples e barato para
                carteiras pequenas. Custa N requisições por dia.
  "varredura" — baixa todas as comunicações do dia e casa localmente. Custa
                ~300 a 500 requisições por dia independentemente do tamanho da
                carteira, e permite casamento tolerante a erro de grafia.
                Compensa a partir de algumas centenas de clientes.

Deduplicação (item 11): a chave é numeroCNJ + client_id. Processo já visto não
gera alerta de novo — só atualiza a última checagem.
"""
import datetime
import json
import os

from src.config import ajustes
from src.provedores.base import CONFIRMADO, POSSIVEL, REVISAO_MANUAL
from src.servicos import alertas as mod_alertas
from src.servicos import plausibilidade
from src.servicos.casador_nomes import casa, normalizar, tokens
from src.servicos.prioridade import ORDEM, classificar_prioridade
from src.util.http import AUDITORIA
from src.util.log import obter

log = obter("monitor")

VISTOS = ajustes.PASTA_DADOS / "processos_vistos.json"
LIMIAR_VARREDURA = 300      # acima disso, varredura nacional sai mais barata


def _carregar_vistos():
    if not VISTOS.exists():
        return {}
    try:
        return json.loads(VISTOS.read_text(encoding="utf-8"))
    except ValueError:
        log.error("processos_vistos.json ilegível — recomeçando o histórico")
        return {}


def _gravar_vistos(dados):
    VISTOS.parent.mkdir(parents=True, exist_ok=True)
    tmp = VISTOS.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(str(tmp), str(VISTOS))


def _indexar(clientes):
    """Índice por primeiro nome, para não comparar todo cliente com toda parte."""
    idx = {}
    for c in clientes:
        ts = tokens(c.get("nome", ""))
        if ts:
            idx.setdefault(ts[0], []).append(c)
    return idx


class Execucao:
    def __init__(self, modo):
        self.modo = modo
        self.inicio = datetime.datetime.now()
        self.fim = None
        self.clientes_verificados = 0
        self.processos_encontrados = 0
        self.novos = 0
        self.alertas_criticos = 0
        self.tribunais = set()
        self.erros = []
        self.itens = []          # (resultado, cliente, prioridade, motivo)

    def encerrar(self):
        self.fim = datetime.datetime.now()
        return self

    @property
    def duracao_s(self):
        return round(((self.fim or datetime.datetime.now()) - self.inicio).total_seconds(), 1)

    def para_dict(self):
        return {
            "modo": self.modo,
            "inicio": self.inicio.isoformat(timespec="seconds"),
            "fim": (self.fim or datetime.datetime.now()).isoformat(timespec="seconds"),
            "duracao_s": self.duracao_s,
            "clientes_verificados": self.clientes_verificados,
            "processos_encontrados": self.processos_encontrados,
            "novos": self.novos,
            "alertas_criticos": self.alertas_criticos,
            "tribunais": sorted(self.tribunais),
            "erros": self.erros,
            "auditoria": AUDITORIA.resumo(),
        }


def executar(clientes, djen, dias=1, modo=None, canal=None, esaj_por_tribunal=None,
             hoje=None, usar_prefixo=True):
    """Roda um ciclo de monitoramento e devolve a Execucao."""
    hoje = hoje or datetime.date.today()
    modo = modo or ("varredura" if len(clientes) > LIMIAR_VARREDURA else "nome")
    canal = canal or mod_alertas.CanalConsole()
    execucao = Execucao(modo)
    vistos = _carregar_vistos()

    brutos = []
    if modo == "nome":
        for c in clientes:
            execucao.clientes_verificados += 1
            try:
                for r in djen.buscar_por_nome(c.get("nome", ""), dias=dias,
                                              cliente_id=c.get("id"),
                                              usar_prefixo=usar_prefixo):
                    brutos.append((r, c))
            except Exception as e:
                execucao.erros.append("cliente %s: %s" % (c.get("id"), e))
                log.warning("falha ao consultar cliente %s: %s", c.get("id"), e)
    else:
        execucao.clientes_verificados = len(clientes)
        idx = _indexar(clientes)
        inicio = (hoje - datetime.timedelta(days=max(0, dias))).isoformat()
        for item in djen.varrer(inicio, hoje.isoformat()):
            passivos = [d.get("nome", "") for d in (item.get("destinatarios") or [])
                        if d.get("polo") == "P"]
            for nome_parte in passivos:
                ts = tokens(nome_parte)
                if not ts:
                    continue
                for c in idx.get(ts[0], []):
                    ok, _, _ = casa(c.get("nome", ""), nome_parte)
                    if not ok:
                        continue
                    r = djen.converter(item, nome_cliente=c.get("nome"),
                                       cliente_id=c.get("id"))
                    if r is not None:
                        brutos.append((r, c))

    # Quantos processos cada cliente puxou: nome comum espalhado pelo país é
    # o retrato do homônimo, e isso precisa pesar na confiança de cada um.
    achados_por_cliente = {}
    for r, c in brutos:
        cid = c.get("id")
        achados_por_cliente[cid] = achados_por_cliente.get(cid, 0) + 1

    # --- deduplicação, prioridade e alerta ------------------------------
    for r, c in brutos:
        execucao.processos_encontrados += 1
        if r.tribunal:
            execucao.tribunais.add(r.tribunal)

        # confirmação por CPF, quando o tribunal permite e o escritório autorizou
        provedor_esaj = (esaj_por_tribunal or {}).get(r.tribunal)
        if provedor_esaj is not None and ajustes.ESAJ_HABILITADO:
            r = _confirmar_por_cpf(r, c, provedor_esaj)

        # plausibilidade: estado, nome pouco distintivo, muitos achados
        fator, observacao = plausibilidade.avaliar(
            r.numero_processo, c.get("ufs"), c.get("nome", ""),
            achados_por_cliente.get(c.get("id"), 1))
        if fator < 1.0:
            r.confianca = round(r.confianca * fator, 3)
        if observacao:
            r.motivo += " Plausibilidade: %s." % observacao

        chave = r.chave
        ja_visto = chave in vistos
        vistos[chave] = {
            "processo": r.numero_processo,
            "tribunal": r.tribunal,
            "cliente_id": c.get("id"),
            "primeiro_detectado_em": vistos.get(chave, {}).get(
                "primeiro_detectado_em", hoje.isoformat()),
            "ultima_checagem": hoje.isoformat(),
            "ultima_movimentacao": r.ultima_movimentacao,
            "status": r.status_casamento,
            "confianca": r.confianca,
            "uf": r.uf,
            "ano": r.ano_ajuizamento,
        }
        if ja_visto:
            log.debug("processo %s já conhecido — só atualiza", r.numero_processo)
            continue

        execucao.novos += 1
        prioridade, motivo = classificar_prioridade(
            data_distribuicao=r.data_distribuicao,
            data_publicacao=r.data_publicacao, hoje=hoje,
            ano_ajuizamento=r.ano_ajuizamento)
        if prioridade == "CRÍTICO":
            execucao.alertas_criticos += 1
        execucao.itens.append((r, c, prioridade, motivo))

    execucao.itens.sort(key=lambda t: (ORDEM.get(t[2], 9), t[0].tribunal))
    for r, c, prioridade, motivo in execucao.itens:
        canal.enviar(mod_alertas.montar_texto(r, c, prioridade, motivo), r)

    _gravar_vistos(vistos)
    return execucao.encerrar()


def _confirmar_por_cpf(resultado, cliente, provedor_esaj):
    """Sobe POSSIBLE_MATCH para CONFIRMED_MATCH quando o CPF bate na origem."""
    from src.seguranca.cpf import decifrar
    try:
        cpf = decifrar(cliente["cpf_cifrado"])
    except Exception as e:
        log.warning("não foi possível decifrar o CPF do cliente %s: %s",
                    cliente.get("id"), e)
        return resultado
    try:
        achados = provedor_esaj.buscar_por_cpf(cpf, cliente_id=cliente.get("id"))
    except Exception as e:
        log.warning("confirmação por CPF falhou: %s", e)
        return resultado
    from src.provedores.base import so_digitos
    alvo = so_digitos(resultado.numero_processo)
    for a in achados:
        if so_digitos(a.numero_processo) == alvo and a.status_casamento == CONFIRMADO:
            resultado.status_casamento = CONFIRMADO
            resultado.confianca = max(resultado.confianca, 0.99)
            resultado.motivo += " Identidade confirmada por CPF no e-SAJ %s." % resultado.tribunal
            return resultado
    return resultado
