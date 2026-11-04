#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuração da automação de download dos contratos assinados no Autentique.

Tudo que é ajustável vive aqui ou no arquivo .env. A chave da API do Autentique
NUNCA fica no código nem dentro do Google Drive: ela mora em
~/.baixar-autentique/.env, com permissão 600.

Motivo (mesmo do CADASTRO ASTREA): o Drive sincroniza para a nuvem e replica em
outras máquinas — chave de API dá acesso a todos os documentos do escritório.
"""

import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------

RAIZ_PROJETO = Path(__file__).resolve().parent.parent       # .../BAIXAR AUTENTIQUE
PASTA_ONBOARDING = RAIZ_PROJETO.parent                      # .../ONBOARDING
PASTA_COMERCIAL = PASTA_ONBOARDING.parent                   # .../A - COMERCIAL

# Onde o comercial guarda as pastas dos clientes.
PASTA_CLIENTES_PADRAO = PASTA_COMERCIAL / "PREPARAÇÃO PARA INGRESSO"

# O separador já existente é reaproveitado (não há cópia da lógica de corte).
SEPARADOR_PADRAO = PASTA_ONBOARDING / "SEPARADOR AUTENTIQUE" / "separar_autentique.py"

# Idem para o gerador de onboarding, com o ambiente Python próprio dele.
GERADOR_ONBOARDING_PADRAO = PASTA_ONBOARDING / "GERADOR ONBOARDING" / "gerar_onboarding.py"
PYTHON_ONBOARDING_PADRAO = (Path(os.path.expanduser("~")) / ".gerador-onboarding"
                            / "venv" / "bin" / "python")

# Dados operacionais (chave, estado, logs, quarentena) ficam FORA do Drive.
CASA = Path(os.path.expanduser("~")) / ".baixar-autentique"

# O binário de verdade por trás do venv — é ELE que precisa de Acesso Total ao
# Disco para a automação enxergar o Google Drive quando roda sozinha.
try:
    BINARIO_PYTHON_REAL = str(Path(sys.executable).resolve())
except OSError:                                    # pragma: no cover
    BINARIO_PYTHON_REAL = sys.executable
ARQUIVO_ENV = CASA / ".env"
ARQUIVO_ENV_EXEMPLO = RAIZ_PROJETO / ".env.example"

# Relatórios que a Caroline lê ficam DENTRO do Drive, junto do projeto.
PASTA_RELATORIOS_PADRAO = RAIZ_PROJETO / "RELATÓRIOS"

SUBPASTAS_CLIENTE = ("CONTRATO HO", "DOC CLIENTE", "DOC ESCRITÓRIO",
                     "ONBOARDING", "PETIÇÕES")


# ---------------------------------------------------------------------------
# Leitura do .env (sem dependência externa)
# ---------------------------------------------------------------------------

def _ler_env(caminho: Path) -> dict:
    """Lê um .env simples: CHAVE=valor, # comentário, aspas opcionais."""
    valores = {}
    if not caminho.exists():
        return valores
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            aspas = valor[0]
            valor = valor[1:-1]
            if aspas == '"':
                valor = valor.replace('\\"', '"').replace("\\\\", "\\")
        valores[chave.strip()] = valor
    return valores


def escapar_para_env(valor: str) -> str:
    """Grava qualquer valor numa linha do .env sem perder caractere."""
    return '"%s"' % str(valor).replace("\\", "\\\\").replace('"', '\\"')


def gravar_no_env(chave: str, valor: str, caminho: Path = None) -> Path:
    """Escreve/atualiza uma chave no .env, sempre com permissão 600."""
    caminho = caminho or ARQUIVO_ENV
    caminho.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(str(caminho.parent), 0o700)
    except OSError:
        pass
    linhas = []
    if caminho.exists():
        linhas = [l for l in caminho.read_text(encoding="utf-8").splitlines()
                  if not l.strip().startswith("%s=" % chave)]
    linhas.append("%s=%s" % (chave, escapar_para_env(valor)))
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    os.chmod(str(caminho), 0o600)
    return caminho


_ENV_ARQUIVO = _ler_env(ARQUIVO_ENV)


def env(chave: str, padrao: str = "") -> str:
    """Variável de ambiente do sistema tem prioridade sobre o .env."""
    return os.environ.get(chave, _ENV_ARQUIVO.get(chave, padrao))


def env_bool(chave: str, padrao: bool) -> bool:
    bruto = env(chave, "").strip().lower()
    if not bruto:
        return padrao
    return bruto in ("1", "true", "sim", "s", "yes", "y", "on")


def env_int(chave: str, padrao: int) -> int:
    try:
        return int(env(chave, "").strip() or padrao)
    except ValueError:
        return padrao


def env_float(chave: str, padrao: float) -> float:
    try:
        return float((env(chave, "").strip() or str(padrao)).replace(",", "."))
    except ValueError:
        return padrao


def env_lista(chave: str, padrao: str) -> list:
    bruto = env(chave, "").strip() or padrao
    return [p.strip() for p in bruto.split(",") if p.strip()]


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

class Config(object):
    """Fotografia das configurações no momento da execução."""

    def __init__(self):
        # --- Acesso ao Autentique ----------------------------------------
        self.token = env("AUTENTIQUE_TOKEN", "").strip()
        self.api_url = env("AUTENTIQUE_API", "https://api.autentique.com.br/v2/graphql").strip()
        self.timeout_s = env_int("TIMEOUT_S", 60)
        # Quantas páginas da listagem olhar por rodada (60 documentos cada).
        self.itens_por_pagina = env_int("ITENS_POR_PAGINA", 60)
        self.max_paginas = env_int("MAX_PAGINAS", 5)
        # Pasta do Autentique (opcional): em branco = todos os documentos.
        self.pasta_autentique = env("PASTA_AUTENTIQUE_ID", "").strip()
        # Filtro opcional pelo nome do documento (expressão regular).
        self.filtro_nome = env("FILTRO_NOME", "").strip()

        # --- Pastas -------------------------------------------------------
        bruto = env("PASTA_CLIENTES", "").strip()
        self.pasta_clientes = Path(bruto) if bruto else PASTA_CLIENTES_PADRAO
        bruto = env("PASTA_DADOS", "").strip()
        self.pasta_dados = Path(bruto) if bruto else CASA
        bruto = env("PASTA_RELATORIOS", "").strip()
        self.pasta_relatorios = Path(bruto) if bruto else PASTA_RELATORIOS_PADRAO
        bruto = env("SEPARADOR", "").strip()
        self.separador = Path(bruto) if bruto else SEPARADOR_PADRAO
        bruto = env("GERADOR_ONBOARDING", "").strip()
        self.gerador_onboarding = Path(bruto) if bruto else GERADOR_ONBOARDING_PADRAO
        bruto = env("PYTHON_ONBOARDING", "").strip()
        self.python_onboarding = Path(bruto) if bruto else PYTHON_ONBOARDING_PADRAO

        self.arquivo_estado = self.pasta_dados / env("ESTADO_ARQUIVO", "estado.json")
        self.pasta_logs = self.pasta_dados / "logs"
        self.pasta_quarentena = self.pasta_dados / "quarentena"
        self.pasta_temp = self.pasta_dados / "tmp"

        # --- Regras de negócio -------------------------------------------
        # Quem é o escritório: esses signatários não são o cliente.
        self.emails_escritorio = [e.lower() for e in env_lista(
            "EMAILS_ESCRITORIO", "contato@carolinemacedoadv.com")]
        self.dominios_escritorio = [d.lower().lstrip("@") for d in env_lista(
            "DOMINIOS_ESCRITORIO", "carolinemacedoadv.com")]
        # Semelhança mínima entre o nome do signatário e o nome da pasta.
        self.limiar_nome = env_float("LIMIAR_NOME", 0.88)
        # Cliente sem pasta: criar em PREPARAÇÃO PARA INGRESSO/<MÊS ANO>/<NOME>.
        self.criar_pasta = env_bool("CRIAR_PASTA", True)
        # Separar o envelope em contrato / procuração / hipossuficiência.
        self.separar = env_bool("SEPARAR", True)
        # Gerar também o PDF de onboarding do cliente, logo após arquivar.
        self.gerar_onboarding = env_bool("GERAR_ONBOARDING", True)
        # Aviso na tela do Mac quando a rodada automática traz novidade.
        self.avisar_na_tela = env_bool("AVISAR_NA_TELA", True)
        self.timeout_onboarding_s = env_int("TIMEOUT_ONBOARDING_S", 300)
        # Quantos dias para trás o comando 'historico' busca por padrão.
        self.dias_historico = env_int("DIAS_HISTORICO", 30)
        # Lixeira da quarentena: documento sem cliente/sem onboarding fica aqui.
        self.dias_quarentena = env_int("DIAS_QUARENTENA", 60)

        # --- Agendamento ---------------------------------------------------
        self.hora_inicio = env_int("HORA_INICIO", 8)
        self.hora_fim = env_int("HORA_FIM", 20)
        self.minuto = env_int("MINUTO", 10)

    # -- utilidades ------------------------------------------------------

    def preparar_pastas(self):
        for pasta in (self.pasta_dados, self.pasta_logs, self.pasta_quarentena,
                      self.pasta_temp, self.pasta_relatorios):
            pasta.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(str(self.pasta_dados), 0o700)
        except OSError:
            pass

    def horarios(self):
        """Horas cheias em que o agendador roda (8..20 por padrão)."""
        inicio = max(0, min(23, self.hora_inicio))
        fim = max(inicio, min(23, self.hora_fim))
        return [(h, max(0, min(59, self.minuto))) for h in range(inicio, fim + 1)]

    def eh_do_escritorio(self, email: str) -> bool:
        email = (email or "").strip().lower()
        if not email:
            return False
        if email in self.emails_escritorio:
            return True
        dominio = email.rpartition("@")[2]
        return dominio in self.dominios_escritorio

    def regex_filtro(self):
        if not self.filtro_nome:
            return None
        try:
            return re.compile(self.filtro_nome, re.IGNORECASE)
        except re.error:
            return None

    def acesso_a_pasta_clientes(self) -> str:
        """
        "" quando dá para ler a pasta dos clientes; senão, o motivo.

        O caso que importa é o `PermissionError`: o Google Drive fica em
        ~/Library/CloudStorage, que o macOS protege. Rodando pelo atalho o
        acesso é do Terminal (que já tem permissão); rodando pelo agendador,
        quem responde é o binário do Python — e sem Acesso Total ao Disco ele
        não lê nada, nem o próprio programa. Foi exatamente o que derrubou a
        primeira rodada automática, em 17/08/2026, sem deixar rastro no log.
        """
        try:
            os.listdir(str(self.pasta_clientes))
            return ""
        except PermissionError:
            return (
                "O macOS está bloqueando o acesso à pasta do Google Drive.\n"
                "  Isso acontece quando a automação roda sozinha (pelo agendador).\n"
                "  Como resolver, uma vez só:\n"
                "    1. Menu Apple → Ajustes do Sistema → Privacidade e Segurança\n"
                "    2. Acesso Total ao Disco → botão +\n"
                "    3. Aperte Cmd+Shift+G e cole este caminho:\n"
                "       %s\n"
                "    4. Escolha o arquivo python3.9 e ligue a chavinha.\n"
                "  Enquanto isso, pelo atalho (dois cliques) ela funciona normalmente."
                % BINARIO_PYTHON_REAL)
        except FileNotFoundError:
            return ("A pasta de clientes não foi encontrada:\n    %s\n"
                    "  Confira se o Google Drive está aberto, ou ajuste "
                    "PASTA_CLIENTES no .env." % self.pasta_clientes)
        except OSError as erro:
            return "Não consegui abrir a pasta de clientes: %s" % erro

    def problemas(self):
        """Lista de impedimentos para rodar. Vazia = pode rodar."""
        erros = []
        if not self.token:
            erros.append(
                "Falta a chave da API do Autentique.\n"
                "  No painel do Autentique: Configurações → Chaves de API → gerar.\n"
                "  Depois, no atalho 'Baixar Contratos Assinados', use a opção "
                "'Configurar a chave do Autentique'.")
        impedimento = self.acesso_a_pasta_clientes()
        if impedimento:
            erros.append(impedimento)
        if self.separar and not self.separador.exists():
            erros.append("O separador de documentos não foi encontrado:\n    %s\n"
                         "  Ajuste SEPARADOR no .env ou desligue SEPARAR." % self.separador)
        return erros

    def resumo(self):
        """Resumo legível — nunca mostra a chave inteira."""
        return {
            "chave da API": mascarar_token(self.token),
            "pasta dos clientes": str(self.pasta_clientes),
            "separar documentos": "sim" if self.separar else "não",
            "gerar onboarding": "sim" if self.gerar_onboarding else "não",
            "criar pasta do cliente": "sim" if self.criar_pasta else "não",
            "estado": str(self.arquivo_estado),
            "relatórios": str(self.pasta_relatorios),
        }


def mascarar_token(token: str) -> str:
    """Chave nunca aparece inteira em tela, log ou relatório."""
    if not token:
        return "(não configurada)"
    if len(token) <= 8:
        return "*" * len(token)
    return token[:4] + "*" * (len(token) - 8) + token[-4:]


_config = None


def get_config(recarregar: bool = False) -> Config:
    global _config, _ENV_ARQUIVO
    if _config is None or recarregar:
        if recarregar:
            _ENV_ARQUIVO = _ler_env(ARQUIVO_ENV)
        _config = Config()
    return _config


if __name__ == "__main__":
    cfg = get_config()
    for chave, valor in cfg.resumo().items():
        print("%-24s %s" % (chave + ":", valor))
    for problema in cfg.problemas():
        print("\n[!] " + problema)
