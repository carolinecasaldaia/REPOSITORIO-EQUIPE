"""Controle de duplicidade: cada exclusão, restituição ou crédito é usado uma vez.

Exemplo do risco: uma tarifa financiada excluída do AP02 já é devolvida
pela redução das parcelas; se também entrar como indébito avulso, ou se um
crédito do consumidor for compensado na compensação geral e de novo na
apuração da venda do veículo, o cálculo conta o mesmo valor duas vezes.
"""

from __future__ import annotations


class DuplicidadeError(ValueError):
    pass


class ControleUtilizacao:
    def __init__(self) -> None:
        self._usos: dict[str, str] = {}

    def usar(self, identificador: str | None, finalidade: str) -> None:
        if not identificador:
            raise ValueError(f"item sem identificador não pode ser controlado ({finalidade})")
        if identificador in self._usos:
            raise DuplicidadeError(
                f"'{identificador}' já utilizado em '{self._usos[identificador]}'; "
                f"uso duplicado em '{finalidade}' recusado"
            )
        self._usos[identificador] = finalidade

    def finalidade(self, identificador: str) -> str | None:
        return self._usos.get(identificador)

    @property
    def usos(self) -> dict[str, str]:
        return dict(self._usos)
