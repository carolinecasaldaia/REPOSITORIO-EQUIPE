"""Montagem do alerta para o escritório (item 13).

O texto é montado aqui e entregue por um "canal". Na FASE 2 existe só o canal
de console/arquivo. WhatsApp, Slack, e-mail, Astrea e webhook entram depois:
a arquitetura já está pronta para eles, mas nenhuma integração externa é
ativada sem credencial e autorização expressa.
"""
import abc

from src.seguranca.cpf import mascarar
from src.servicos.prioridade import EMOJI


def montar_texto(resultado, cliente=None, prioridade="ATENÇÃO", motivo_prioridade=""):
    cliente = cliente or {}
    # já vem mascarado do cadastro; nunca decifra CPF só para exibir
    mascara = cliente.get("cpf_mascara") or (mascarar(cliente["cpf"]) if cliente.get("cpf") else "")
    linhas = [
        "%s NOVA BUSCA E APREENSÃO LOCALIZADA" % EMOJI.get(prioridade, ""),
        "",
        "Cliente:            %s" % (cliente.get("nome") or resultado.reu or "—"),
        "CPF:                %s" % (mascara or "—"),
        "Banco:              %s" % (resultado.banco_normalizado or resultado.autor or "—"),
        "Processo:           %s" % (resultado.numero_processo or "—"),
        "Tribunal:           %s" % (resultado.tribunal or "—"),
        "Comarca:            %s" % (resultado.comarca or "—"),
        "Vara:               %s" % (resultado.orgao_julgador or "—"),
        "Distribuição:       %s" % (resultado.data_distribuicao or "não informada pela fonte"),
        "Publicação (DJEN):  %s" % (resultado.data_publicacao or "—"),
        "Classe:             %s" % (resultado.classe_nome or "—"),
        "Última movimentação:%s" % (" " + resultado.ultima_movimentacao if resultado.ultima_movimentacao else " —"),
        "Prioridade:         %s — %s" % (prioridade, motivo_prioridade),
        "Situação:           %s (confiança %.0f%%)" % (resultado.status_casamento, resultado.confianca * 100),
        "Fonte:              %s" % (resultado.fonte or "—"),
        "",
        "Motivo: %s" % resultado.motivo,
    ]
    if resultado.status_casamento != "CONFIRMED_MATCH":
        linhas += ["", "⚠️  IDENTIDADE NÃO CONFIRMADA POR CPF — confira antes de agir."]
    return "\n".join(linhas)


class Canal(abc.ABC):
    """Contrato de qualquer canal de entrega de alerta."""
    nome = "canal"

    @abc.abstractmethod
    def enviar(self, texto, resultado=None):
        """True se entregou."""


class CanalConsole(Canal):
    nome = "console"

    def __init__(self, saida=None):
        self.entregues = []
        self._saida = saida

    def enviar(self, texto, resultado=None):
        self.entregues.append(texto)
        if self._saida is not None:
            self._saida.write(texto + "\n\n")
        else:
            print("\n" + texto + "\n")
        return True
