"""Quanto é plausível que este processo seja mesmo do nosso cliente.

Nome igual não é prova. Na carga real de 18/08/2026, consultar 358 clientes
devolveu 362 processos — e **272 deles (75%) estavam em estado diferente do
cadastro do cliente**. Um único "Marcos Antônio da Silva" puxou 24 processos
espalhados pelo país. São homônimos, não clientes.

Este módulo não descarta nada sozinho: ele pontua, explica e deixa a decisão
para a régua de prioridade e para a conferência humana. Descartar por conta
própria arriscaria perder o processo de um cliente que simplesmente se mudou.
"""
from src.util import cnj

# Nomes com poucos tokens distintivos casam com muita gente.
_SOBRENOMES_COMUNS = {
    "SILVA", "SANTOS", "SOUZA", "SOUSA", "OLIVEIRA", "PEREIRA", "LIMA",
    "COSTA", "FERREIRA", "RODRIGUES", "ALVES", "NASCIMENTO", "CARVALHO",
    "GOMES", "MARTINS", "ARAUJO", "MELO", "BARBOSA", "RIBEIRO", "JESUS",
}


def avaliar(numero_processo, ufs_do_cliente, nome_cliente="", achados_do_cliente=1):
    """Devolve (fator, observacao).

    `fator` multiplica a confiança: 1.0 mantém, valores menores rebaixam.
    `achados_do_cliente` é quantos processos aquele mesmo nome trouxe — muitos
    achados espalhados é o retrato do homônimo.
    """
    observacoes = []
    fator = 1.0

    if not cnj.eh_estadual(numero_processo):
        return 0.35, "processo fora da Justiça Estadual — provavelmente não é do cliente"

    uf_processo = cnj.uf(numero_processo)
    ufs = [u for u in (ufs_do_cliente or []) if u]
    if uf_processo and ufs:
        if uf_processo not in ufs:
            fator *= 0.45
            observacoes.append("processo em %s, cliente cadastrado em %s"
                               % (uf_processo, "/".join(ufs)))
        else:
            observacoes.append("mesmo estado do cadastro (%s)" % uf_processo)

    # Nome pouco distintivo: só nomes muito comuns, sem sobrenome raro.
    tokens = [t for t in str(nome_cliente or "").upper().split() if len(t) > 2]
    distintivos = [t for t in tokens if t not in _SOBRENOMES_COMUNS]
    if len(tokens) >= 2 and len(distintivos) <= 1:
        fator *= 0.75
        observacoes.append("nome pouco distintivo")

    if achados_do_cliente >= 8:
        fator *= 0.5
        observacoes.append("mesmo nome apareceu em %d processos — forte indício de homônimo"
                           % achados_do_cliente)
    elif achados_do_cliente >= 4:
        fator *= 0.75
        observacoes.append("mesmo nome apareceu em %d processos" % achados_do_cliente)

    return round(max(0.1, fator), 3), "; ".join(observacoes)


def ano_do_processo(numero_processo):
    return cnj.ano(numero_processo)
