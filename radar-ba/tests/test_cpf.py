"""Validação, mascaramento, hash e criptografia de CPF (item 9)."""
import pytest

from src.seguranca import cpf as C

VALIDOS = ["111.444.777-35", "11144477735", "529.982.247-25"]
INVALIDOS = ["123.456.789-12", "111.111.111-11", "000.000.000-00", "123", "", None]


@pytest.mark.parametrize("v", VALIDOS)
def test_aceita_cpf_valido(v):
    assert C.validar(v)


@pytest.mark.parametrize("v", INVALIDOS)
def test_recusa_cpf_invalido(v):
    assert not C.validar(v)


def test_mascara_esconde_tudo_menos_os_dois_ultimos():
    assert C.mascarar("111.444.777-35") == "***.***.***-35"
    assert C.mascarar("11144477735") == "***.***.***-35"
    assert "444" not in C.mascarar("111.444.777-35")


def test_mascara_de_valor_invalido_nao_vaza_nada():
    assert C.mascarar("123") == "***.***.***-**"


def test_hash_e_deterministico_e_independe_de_pontuacao():
    assert C.hash_deterministico("111.444.777-35") == C.hash_deterministico("11144477735")


def test_hash_difere_entre_cpfs():
    assert C.hash_deterministico("11144477735") != C.hash_deterministico("52998224725")


def test_hash_nao_contem_o_cpf():
    assert "11144477735" not in C.hash_deterministico("11144477735")


def test_cifra_e_decifra_ida_e_volta():
    assert C.decifrar(C.cifrar("111.444.777-35")) == "11144477735"


def test_cifragem_nao_e_deterministica():
    """Nonce novo a cada cifragem: dois cifrados iguais não podem existir."""
    assert C.cifrar("11144477735") != C.cifrar("11144477735")


def test_cifrado_nao_contem_o_cpf_em_claro():
    assert "11144477735" not in C.cifrar("11144477735")


def test_recusa_cifrar_cpf_invalido():
    with pytest.raises(ValueError):
        C.cifrar("123")


def test_falha_fechado_sem_chave(monkeypatch):
    """Sem chave configurada o sistema recusa — nunca grava em texto puro."""
    from src.config import ajustes
    monkeypatch.setattr(ajustes, "CPF_CHAVE", "")
    with pytest.raises(C.ChaveAusente):
        C.cifrar("11144477735")
