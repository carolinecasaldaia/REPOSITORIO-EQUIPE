#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuração central da automação.

Tudo que é ajustável vive aqui ou no arquivo .env. Nenhuma credencial fica
escrita no código. O e-mail do Astrea vem do .env; a senha, do Porta-chaves do
macOS (serviço "cadastro-astrea", conta = o e-mail) desde 29/09/2026 — antes
ficava em texto aberto no .env, que ainda é lido se tiver ASTREA_SENHA.

O .env fica FORA do Google Drive, em ~/.cadastro-astrea/.env, com permissão 600.
Isso é proposital: o Drive sincroniza para a nuvem e replica em outras máquinas,
e credencial de sistema jurídico não deve sair da máquina.
"""

import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------

RAIZ_PROJETO = Path(__file__).resolve().parent.parent.parent   # .../CADASTRO ASTREA
PASTA_ONBOARDING = RAIZ_PROJETO.parent                          # .../ONBOARDING
PASTA_COMERCIAL = PASTA_ONBOARDING.parent                       # .../A - COMERCIAL
PASTA_ESCRITORIO = PASTA_COMERCIAL.parent.parent                # .../Documentos Escritório

# Onde o setor comercial cria as pastas dos clientes.
PASTA_CLIENTES_PADRAO = PASTA_COMERCIAL / "PREPARAÇÃO PARA INGRESSO"

# Áreas de destino da cópia automática, depois que o caso é aberto (decisão
# dela, 23/09/2026). "A - COMERCIAL" mora DENTRO de "A - REVISIONAL" — por
# isso o cálculo é a partir dele, e não um irmão de "A - COMERCIAL".
PASTA_REVISIONAL_PADRAO = PASTA_COMERCIAL.parent                 # .../A - REVISIONAL
PASTA_CIVEL_PADRAO = PASTA_ESCRITORIO / "A - CÍVEL"

# Dados operacionais (banco, logs, evidências, .env) ficam fora do Drive.
CASA = Path(os.path.expanduser("~")) / ".cadastro-astrea"
ARQUIVO_ENV = CASA / ".env"
ARQUIVO_ENV_EXEMPLO = RAIZ_PROJETO / ".env.example"

# Relatórios que a Caroline lê ficam DENTRO do Drive, junto do projeto.
PASTA_RELATORIOS = RAIZ_PROJETO / "RELATÓRIOS"


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
        # Valor entre aspas duplas preserva espaços e caracteres especiais —
        # senha pode ter qualquer coisa, inclusive espaço no fim.
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            aspas = valor[0]
            valor = valor[1:-1]
            if aspas == '"':
                valor = valor.replace('\\"', '"').replace("\\\\", "\\")
        valores[chave.strip()] = valor
    return valores


def escapar_para_env(valor: str) -> str:
    """Grava qualquer senha em uma linha do .env sem perder caractere."""
    return '"%s"' % str(valor).replace("\\", "\\\\").replace('"', '\\"')


_ENV_ARQUIVO = _ler_env(ARQUIVO_ENV)


def env(chave: str, padrao: str = "") -> str:
    """Variável de ambiente do sistema tem prioridade sobre o .env."""
    return os.environ.get(chave, _ENV_ARQUIVO.get(chave, padrao))


def _senha_do_astrea(email: str) -> str:
    """
    Variável de ambiente (mesmo vazia, que é como os testes dizem "sem
    senha") > ASTREA_SENHA no .env (formato antigo) > Porta-chaves.
    """
    if "ASTREA_SENHA" in os.environ:
        return os.environ["ASTREA_SENHA"]
    if _ENV_ARQUIVO.get("ASTREA_SENHA"):
        return _ENV_ARQUIVO["ASTREA_SENHA"]
    from src import porta_chaves
    return porta_chaves.ler(porta_chaves.SERVICO_ASTREA, email)


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


# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------

class Config(object):
    """Fotografia das configurações no momento da execução."""

    def __init__(self):
        # --- Segurança do modo de operação -------------------------------
        # Padrão TEST_MODE=true: enquanto ninguém disser o contrário no .env,
        # a automação NÃO grava nada no Astrea.
        self.test_mode = env_bool("TEST_MODE", True)

        # --- Pastas -------------------------------------------------------
        bruto = env("PASTA_CLIENTES", "").strip()
        self.pasta_clientes = Path(bruto) if bruto else PASTA_CLIENTES_PADRAO
        # PASTA_DADOS existe para os testes rodarem isolados do banco real.
        bruto = env("PASTA_DADOS", "").strip()
        self.pasta_dados = Path(bruto) if bruto else CASA
        bruto = env("PASTA_RELATORIOS", "").strip()
        self.pasta_relatorios = Path(bruto) if bruto else PASTA_RELATORIOS
        # Destino da cópia automática da pasta do cliente, depois do caso
        # aberto (decisão dela, 23/09/2026): Busca e Apreensão/Revisional vai
        # para "A - REVISIONAL"; Cível vai para "A - CÍVEL".
        bruto = env("PASTA_REVISIONAL", "").strip()
        self.pasta_revisional = Path(bruto) if bruto else PASTA_REVISIONAL_PADRAO
        bruto = env("PASTA_CIVEL", "").strip()
        self.pasta_civel = Path(bruto) if bruto else PASTA_CIVEL_PADRAO
        # Corte histórico (decisão dela, 23/09/2026, ampliada no mesmo dia):
        # só pasta vista pela primeira vez a partir desta data entra na
        # automação do Asaas inteira — checagem de entrada, abertura de caso,
        # cópia e marcação "OK -". Cliente de antes do corte fica de fora de
        # tudo isso; foi o backlog antigo (46 clientes) que gerou as
        # duplicidades de caso corrigidas em 22 e 23/09/2026.
        self.data_corte_novos_casos = env("DATA_CORTE_NOVOS_CASOS", "2026-09-23").strip()
        self.banco = self.pasta_dados / env("BANCO_ARQUIVO", "controle.sqlite3")
        self.pasta_logs = self.pasta_dados / "logs"
        self.pasta_evidencias = self.pasta_dados / "evidencias"
        self.pasta_perfil_chrome = self.pasta_dados / "chrome-perfil"

        # --- Astrea -------------------------------------------------------
        # adaptador: navegador | planilha | dry-run
        self.astrea_adaptador = env("ASTREA_ADAPTADOR", "navegador").strip().lower()
        self.astrea_url = env("ASTREA_URL", "https://astrea.net.br/#/login/BR").strip()
        self.astrea_email = env("ASTREA_EMAIL", "").strip()
        self.astrea_senha = _senha_do_astrea(self.astrea_email)
        self.astrea_navegador_visivel = env_bool("ASTREA_NAVEGADOR_VISIVEL", False)
        # chrome = o Google Chrome instalado na máquina; chromium = o que o
        # Playwright baixa. Chrome é o padrão por ser o mesmo navegador que a
        # advogada usa — mesmo comportamento, mesma renderização.
        self.astrea_navegador = env("ASTREA_NAVEGADOR", "chrome").strip().lower()
        # Perfil próprio: a sessão do Astrea fica salva num perfil separado do
        # Chrome, criado só para a automação. Com ele, a senha NÃO precisa ser
        # guardada — basta entrar uma vez à mão (executar.py entrar).
        self.astrea_perfil_proprio = env_bool("ASTREA_PERFIL_PROPRIO", True)
        self.astrea_timeout_ms = env_int("ASTREA_TIMEOUT_MS", 30000)
        # Pausa entre clientes: evita rajada de requisições no sistema deles.
        self.astrea_pausa_entre_clientes_s = env_float("ASTREA_PAUSA_ENTRE_CLIENTES_S", 3.0)
        # Desligado por decisão de escopo (13/08/2026): por ora a automação só
        # cadastra o contato. A tela de casos do Astrea ainda não foi calibrada,
        # e o tipo de ação / banco adverso continuam sendo extraídos e mostrados
        # no relatório para abertura manual — o dado não se perde.
        self.astrea_criar_caso = env_bool("ASTREA_CRIAR_CASO", False)

        # --- Regras de negócio -------------------------------------------
        # Campos considerados críticos: abaixo do limiar vão para conferência
        # humana em vez de serem cadastrados.
        self.limiar_confianca = env_float("LIMIAR_CONFIANCA", 0.80)
        # Obrigatórios para permitir o cadastro automático.
        self.campos_obrigatorios = [
            c.strip() for c in env("CAMPOS_OBRIGATORIOS", "nome,cpf").split(",") if c.strip()
        ]
        # Extrai o Cliente Responsável (corresponsável) só para relatório.
        self.extrair_corresponsavel = env_bool("EXTRAIR_CORRESPONSAVEL", True)
        # Cadastrar também o corresponsável no Astrea (decisão: não, por ora).
        self.cadastrar_corresponsavel = env_bool("CADASTRAR_CORRESPONSAVEL", False)

        # --- Vigilância da pasta -----------------------------------------
        # A pasta só é lida depois de ficar parada este tempo, para não pegar
        # o cliente no meio do upload dos documentos.
        self.minutos_estabilidade = env_int("MINUTOS_ESTABILIDADE", 10)
        self.max_tentativas = env_int("MAX_TENTATIVAS", 3)
        # Horários fixos, e não intervalo, por uma limitação do Astrea: ele só
        # aceita UMA sessão por conta. Se a automação rodasse durante o
        # expediente, ela e a advogada ficariam se derrubando o dia inteiro.
        # Então roda cedo e à noite, fora do horário de uso.
        self.horarios = self._ler_horarios(env("HORARIOS", "06:00,21:00"))

        # Quais pastas de mês a automação olha.
        # Vazio = todas; "atual" = só o mês corrente; ou fixo ("AGOSTO 2026").
        # Decisão dela em 18/08/2026: cuidar só do mês corrente — os meses
        # anteriores já tiveram seguimento manual.
        self.meses = env("MESES", "").strip()

        # --- Asaas ----------------------------------------------------------
        # A tentativa de usar a API do Conta Azul para isto (agosto/2026) não
        # foi adiante — o OAuth2 do aplicativo dela nunca chegou a autorizar
        # (ver e-mail enviado ao suporte deles, no projeto). Decisão de
        # 22/09/2026: quem confirma a entrada paga é a API do Asaas, não mais
        # a Caroline escolhendo cliente a cliente. Chave gerada em Asaas >
        # Integrações > Chaves API.
        self.asaas_api_key = env("ASAAS_API_KEY", "").strip()
        # Texto que a cobrança de entrada sempre começa (case-insensitive na
        # comparação). Mensalidade de honorários usa outro texto e nunca bate.
        self.asaas_texto_entrada = env("ASAAS_TEXTO_ENTRADA", "ENTRADA").strip()

        # --- Privacidade / logs ------------------------------------------
        # Estas três estavam por engano DENTRO de _ler_horarios, depois do
        # return: nunca eram atribuídas, e o programa quebrava ao abrir o log
        # ("Config object has no attribute mascarar_cpf_no_log"). O defeito
        # entrou em 17/08/2026 às 15:15 e só apareceu em 18/08, porque entre
        # uma coisa e outra a automação não chegou a rodar.
        # nunca | erro | sempre  — captura de tela do navegador
        self.salvar_evidencia = env("SALVAR_EVIDENCIA", "erro").strip().lower()
        self.mascarar_cpf_no_log = env_bool("MASCARAR_CPF_NO_LOG", True)
        self.dias_retencao_log = env_int("DIAS_RETENCAO_LOG", 180)

    @staticmethod
    def _ler_horarios(bruto):
        """
        Lê HORARIOS do .env. Aceita hora solta e FAIXA de hora em hora.

            06:00,21:00   -> duas rodadas no dia
            08-20:40      -> de hora em hora, das 8h às 20h, sempre aos 40 min

        A faixa existe desde 08/09/2026, quando ela pediu o cadastro de hora em
        hora: o Claude tem login próprio no Astrea, então rodar durante o
        expediente não a derruba mais do sistema.
        """
        horarios = []
        for pedaco in (bruto or "").split(","):
            pedaco = pedaco.strip()
            if not pedaco:
                continue
            faixa = re.match(r"^(\d{1,2})\s*-\s*(\d{1,2})(?::(\d{1,2}))?$", pedaco)
            if faixa:
                inicio, fim = int(faixa.group(1)), int(faixa.group(2))
                minuto = int(faixa.group(3) or 0)
                if 0 <= inicio <= 23 and 0 <= fim <= 23 and 0 <= minuto <= 59:
                    for hora in range(inicio, fim + 1):
                        horarios.append((hora, minuto))
                continue
            partes = pedaco.split(":")
            try:
                hora = int(partes[0])
                minuto = int(partes[1]) if len(partes) > 1 else 0
            except ValueError:
                continue
            if 0 <= hora <= 23 and 0 <= minuto <= 59:
                horarios.append((hora, minuto))
        # Sem repetir horário e em ordem: launchd aceita repetido, mas o menu
        # mostraria "08:40, 08:40" e pareceria defeito.
        vistos, unicos = set(), []
        for horario in horarios:
            if horario not in vistos:
                vistos.add(horario)
                unicos.append(horario)
        return sorted(unicos) or [(6, 0), (21, 0)]

    # -- utilidades ------------------------------------------------------

    def preparar_pastas(self):
        for pasta in (self.pasta_dados, self.pasta_logs, self.pasta_evidencias,
                      self.pasta_relatorios):
            pasta.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(str(self.pasta_dados), 0o700)
        except OSError:
            pass

    def tem_sessao_salva(self) -> bool:
        """O perfil do Chrome da automação já tem sessão do Astrea gravada?"""
        return (self.pasta_perfil_chrome / "Default").exists()

    def tem_acesso_astrea(self) -> bool:
        """
        Dá para entrar no Astrea?

        São dois caminhos independentes: a sessão salva no perfil próprio
        (recomendado) OU e-mail e senha no .env. Confundir isso já custou um
        teste inteiro: a automação caiu em dry-run por não achar senha no .env,
        mesmo com a sessão salva funcionando, e a duplicidade não foi conferida.
        """
        if self.astrea_perfil_proprio and self.tem_sessao_salva():
            return True
        return bool(self.astrea_email and self.astrea_senha)

    def problemas(self):
        """Lista de impedimentos para rodar. Vazia = pode rodar."""
        erros = []
        if not self.pasta_clientes.exists():
            erros.append(
                "A pasta de clientes não foi encontrada:\n    %s\n"
                "  Ajuste PASTA_CLIENTES no .env." % self.pasta_clientes
            )
        if self.astrea_adaptador not in ("navegador", "planilha", "dry-run"):
            erros.append("ASTREA_ADAPTADOR inválido: %r (use navegador, planilha ou dry-run)"
                         % self.astrea_adaptador)
        if not self.test_mode and self.astrea_adaptador == "navegador":
            if not self.tem_acesso_astrea():
                erros.append(
                    "Sem acesso ao Astrea configurado. Rode 'executar.py entrar' "
                    "para entrar uma vez à mão (recomendado, não guarda senha) "
                    "ou preencha ASTREA_EMAIL/ASTREA_SENHA no .env.")
        return erros

    def resumo(self):
        """Resumo legível — nunca inclui senha."""
        return {
            "modo": "TESTE (não grava no Astrea)" if self.test_mode else "PRODUÇÃO",
            "adaptador": self.astrea_adaptador,
            "pasta_clientes": str(self.pasta_clientes),
            "banco": str(self.banco),
            "astrea_email": _mascarar_email(self.astrea_email),
            "senha_configurada": "sim" if self.astrea_senha else "não (será pedida na hora)",
            "criar_caso": self.astrea_criar_caso,
            "limiar_confianca": self.limiar_confianca,
            "campos_obrigatorios": ",".join(self.campos_obrigatorios),
        }


def _mascarar_email(email: str) -> str:
    if not email or "@" not in email:
        return "(não configurado)"
    usuario, _, dominio = email.partition("@")
    if len(usuario) <= 2:
        return "*@" + dominio
    return usuario[0] + "*" * (len(usuario) - 2) + usuario[-1] + "@" + dominio


def mascarar_cpf(cpf: str) -> str:
    """049.123.456-56 -> 049.***.***-56 (para logs e relatórios)."""
    if not cpf:
        return ""
    digitos = re.sub(r"\D", "", cpf)
    if len(digitos) == 11:
        return "%s.***.***-%s" % (digitos[:3], digitos[-2:])
    if len(digitos) == 14:
        return "%s.***.***/****-%s" % (digitos[:2], digitos[-2:])
    return "***"


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
        print("%-22s %s" % (chave + ":", valor))
    for problema in cfg.problemas():
        print("\n[!] " + problema, file=sys.stderr)
