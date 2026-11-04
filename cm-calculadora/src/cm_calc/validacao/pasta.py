"""Pasta de trabalho da validação: ~/CM-Calculos-Dados/validacao/<ID>/

    original/      documentos ORIGINAIS (nunca alterados; lidos só pela rotina local de anonimização)
    anonimizados/  cópias anonimizadas aguardando a conferência da advogada
    anonimizacao/  termos.txt (nomes e números a remover), relatório detalhado (confidencial) e verificação
    parecer/   parecer anonimizado e LIBERADO (PDF) e, se houver, planilhas da perita (XLSX ou AP01.csv...)
    documentos/    contrato, sentença etc. anonimizados e LIBERADOS (base da ficha)
    ficha.xlsx parâmetros de ENTRADA do caso (modelo gerado automaticamente)
    indices/   séries oficiais: <NOME>.csv + <NOME>.fonte.txt (órgão, tabela/série, data da consulta)
    saida/     relatório (validacao.md, validacao.xlsx) e registro (comparativo.json)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from ..casos import raiz_dados
from ..motor.atualizacao import SerieMensal
from ..servicos.indices import serie_de_csv
from .comparacao import ResultadoValidacao, validar
from .ficha import FichaCaso, carregar_ficha, gerar_modelo, pendencias_ficha
from .leitura_parecer import ler_parecer_csv, ler_parecer_pdf, ler_parecer_xlsx, texto_pdf, verificar_anonimizacao
from .modelos import Parecer
from .relatorio import markdown, planilha

RE_ID = re.compile(r"^[A-Z0-9][A-Z0-9\-]{2,39}$")

TERMOS = """# Um termo por linha: nomes completos, apelidos, números de contrato/processo, placas,
# nome da perita, do advogado, da empresa empregadora etc. — tudo o que deve ser removido.
# Linhas iniciadas por # são ignoradas. Este arquivo é confidencial (não é lido pelo Claude).
"""

LEIA_ME = """VALIDAÇÃO PERICIAL — {id}

0. ANONIMIZAÇÃO LOCAL (recomendado):
   - coloque os ORIGINAIS em original/ (parecer, contrato, sentença...) — nunca são alterados;
   - liste em anonimizacao/termos.txt os nomes e números a remover;
   - rode:  uv run cm-calc validacao anonimizar {id}
   - confira as cópias em anonimizados/ e o relatório anonimizacao/relatorio-detalhado-*.md;
   - libere:  uv run cm-calc validacao liberar {id} ARQUIVO --como parecer|documento --por "NOME"
1. parecer/  : recebe o parecer ANONIMIZADO e liberado (PDF com texto pesquisável).
               Se a perita forneceu planilhas, coloque também (XLSX com abas AP01/AP02/AP03,
               ou arquivos AP01.csv, AP02.csv, AP03.csv).
2. ficha.xlsx: parâmetros de ENTRADA (contrato e título). Não copie resultados da perita.
3. indices/  : séries oficiais usadas na atualização, uma por arquivo:
               INPC.csv (competência;variação %) + INPC.fonte.txt (órgão, série/tabela, data da consulta).
4. Rode:  uv run cm-calc validacao verificar {id}
          uv run cm-calc validacao executar {id}
"""


class Validacao:
    def __init__(self, vid: str, raiz: Path | None = None):
        if not RE_ID.match(vid):
            raise ValueError("identificador: MAIÚSCULAS, dígitos e hífen (sem nome/CPF)")
        self.id = vid
        self.pasta = (raiz or raiz_dados()) / "validacao" / vid

    def preparar(self) -> Path:
        for sub in ("", "original", "anonimizados", "anonimizacao", "parecer", "documentos", "indices", "saida"):
            p = self.pasta / sub
            p.mkdir(parents=True, exist_ok=True)
            os.chmod(p, 0o700)
        if not (self.pasta / "ficha.xlsx").exists():
            gerar_modelo(self.pasta / "ficha.xlsx")
        termos = self.pasta / "anonimizacao" / "termos.txt"
        if not termos.exists():
            termos.write_text(TERMOS, encoding="utf-8")
            os.chmod(termos, 0o600)
        (self.pasta / "LEIA-ME.txt").write_text(LEIA_ME.format(id=self.id), encoding="utf-8")
        return self.pasta

    # --- anonimização local -----------------------------------------------------------------
    def termos(self) -> list[str]:
        arq = self.pasta / "anonimizacao" / "termos.txt"
        if not arq.exists():
            return []
        return [l.strip() for l in arq.read_text(encoding="utf-8").splitlines() if l.strip() and not l.lstrip().startswith("#")]

    def importar_original(self, arquivo: Path) -> str:
        """Copia o documento ORIGINAL para original/ com nome genérico (o nome do arquivo pode conter
        dado pessoal). O arquivo de origem não é alterado. Devolve só o nome genérico."""
        self.preparar()
        ext = arquivo.suffix.lower()
        if ext not in (".pdf", ".xlsx", ".csv"):
            raise ValueError(f"formato {ext or '(sem extensão)'} não suportado: use PDF, XLSX ou CSV")
        dados = arquivo.read_bytes()
        h = hashlib.sha256(dados).hexdigest()
        existentes = sorted(p for p in (self.pasta / "original").iterdir() if p.is_file() and not p.name.startswith("."))
        for p in existentes:
            if hashlib.sha256(p.read_bytes()).hexdigest() == h:
                return f"{p.name} (já importado)"
        destino = self.pasta / "original" / f"documento-{len(existentes) + 1:02d}{ext}"
        destino.write_bytes(dados)
        os.chmod(destino, 0o400)
        with (self.pasta / "anonimizacao" / "originais.jsonl").open("a", encoding="utf-8") as f:   # confidencial
            f.write(json.dumps({"generico": destino.name, "nome_original": arquivo.name, "sha256": h,
                                "importado_em": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False) + "\n")
        os.chmod(self.pasta / "anonimizacao" / "originais.jsonl", 0o600)
        return destino.name

    def adicionar_termos(self, termos: list[str]) -> int:
        self.preparar()
        novos = [t.strip() for t in termos if t.strip()]
        with (self.pasta / "anonimizacao" / "termos.txt").open("a", encoding="utf-8") as f:
            for t in novos:
                f.write(t + "\n")
        return len(novos)

    def abrir_conferencia(self) -> None:
        """Abre no Mac (localmente) o original, a cópia anonimizada e os relatórios, para conferência."""
        import subprocess
        pdfs = sorted((self.pasta / "anonimizados").glob("*.pdf")) + sorted((self.pasta / "original").glob("*.pdf"))
        if pdfs:
            subprocess.run(["open", "-a", "Preview", *map(str, pdfs)], check=False)
        relatorios = [self.pasta / "anonimizacao" / "verificacao.md",
                      *sorted((self.pasta / "anonimizacao").glob("relatorio-detalhado-*.md"))]
        subprocess.run(["open", "-e", *[str(r) for r in relatorios if r.exists()]], check=False)

    def anonimizar(self, remover_imagens_grandes: bool = False) -> list[dict]:
        """Anonimiza cada arquivo de original/ em anonimizados/. Devolve resumos SEM dados pessoais.
        Imagens grandes (possíveis gráficos/tabelas) ficam retidas e exportadas para anonimizados/revisao-imagens/
        (pasta protegida) até a conferência da advogada; só com `remover_imagens_grandes` são removidas."""
        from ..privacidade.anonimizacao import (anonimizar_csv, anonimizar_pdf, anonimizar_xlsx, relatorio_detalhado,
                                                relatorio_verificacao)
        origem = self.pasta / "original"
        arquivos = sorted(p for p in origem.iterdir() if p.is_file() and not p.name.startswith("."))
        if not arquivos:
            raise FileNotFoundError(f"nenhum arquivo em {origem}")
        termos, resumos = self.termos(), []
        for i, arq in enumerate(arquivos, start=1):
            ext = arq.suffix.lower()
            # nomes genéricos: o nome do arquivo original pode conter dado pessoal
            generico = arq.stem if re.fullmatch(r"documento-\d+", arq.stem) else f"documento-{i:02d}"
            destino = self.pasta / "anonimizados" / f"{generico}-anonimizado{ext}"
            if ext == ".pdf":
                r = anonimizar_pdf(arq, destino, termos, remover_imagens_grandes=remover_imagens_grandes,
                                   pasta_revisao=self.pasta / "anonimizados" / "revisao-imagens" / generico)
                resumo, remocoes, ver = r.resumo(), r.remocoes, r.verificacao
                resumo["arquivo_original"] = f"{generico}{ext} (original)"
            elif ext in (".xlsx", ".csv"):
                h0 = hashlib.sha256(arq.read_bytes()).hexdigest()
                remocoes, faltam = (anonimizar_xlsx if ext == ".xlsx" else anonimizar_csv)(arq, destino, termos)
                intacto = hashlib.sha256(arq.read_bytes()).hexdigest() == h0
                resumo = {"arquivo_original": f"{generico}{ext} (original)", "arquivo_anonimizado": destino.name,
                          "remocoes_por_tipo": dict(Counter(x.tipo for x in remocoes)),
                          "verificacao": {"aprovada": intacto and faltam == 0, "original_intacto": intacto,
                                          "dados_financeiros_ausentes": faltam,
                                          "observacao": "planilha: comentários, imagens e propriedades removidos; "
                                                        "conferir abas ocultas e nomes de abas"}}
                ver = None
            else:
                resumos.append({"arquivo_original": f"{generico}{ext} (original)", "arquivo_anonimizado": "",
                                "verificacao": {"aprovada": False, "observacao": f"formato {ext} não suportado: converta para PDF"}})
                continue
            det = self.pasta / "anonimizacao" / f"relatorio-detalhado-{generico}.md"
            det.write_text(relatorio_detalhado(f"{arq.name} -> {destino.name}", remocoes, ver), encoding="utf-8")
            os.chmod(det, 0o600)
            resumos.append(resumo)
        (self.pasta / "anonimizacao" / "verificacao.json").write_text(json.dumps(resumos, ensure_ascii=False, indent=1),
                                                                     encoding="utf-8")
        (self.pasta / "anonimizacao" / "verificacao.md").write_text(relatorio_verificacao(resumos), encoding="utf-8")
        return resumos

    def liberar(self, arquivo: str, como: str, responsavel: str, apesar_de: str | None = None) -> Path:
        """Libera uma cópia anonimizada para uso na validação (registro da autorização da advogada)."""
        if como not in ("parecer", "documento"):
            raise ValueError("como: parecer | documento")
        if not responsavel.strip():
            raise ValueError("informe a responsável pela autorização")
        origem = self.pasta / "anonimizados" / Path(arquivo).name
        if not origem.exists():
            raise FileNotFoundError(f"{origem.name} não está em anonimizados/")
        ver = json.loads((self.pasta / "anonimizacao" / "verificacao.json").read_text(encoding="utf-8"))
        resumo = next((r for r in ver if r.get("arquivo_anonimizado") == origem.name), None)
        aprovada = bool(resumo and resumo["verificacao"].get("aprovada"))
        if not aprovada and not (apesar_de and apesar_de.strip()):
            raise PermissionError(f"{origem.name}: verificação automática não aprovada; corrija ou justifique (--apesar-de)")
        destino = self.pasta / ("parecer" if como == "parecer" else "documentos") / origem.name
        destino.write_bytes(origem.read_bytes())
        with (self.pasta / "anonimizacao" / "liberacoes.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"arquivo": origem.name, "como": como, "responsavel": responsavel.strip(),
                                "verificacao_aprovada": aprovada, "justificativa": apesar_de,
                                "sha256": hashlib.sha256(destino.read_bytes()).hexdigest(),
                                "liberado_em": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False) + "\n")
        return destino

    def arquivos_parecer(self) -> list[Path]:
        return sorted(p for p in (self.pasta / "parecer").iterdir() if p.suffix.lower() in (".pdf", ".xlsx", ".csv"))

    def verificar_anonimizacao(self) -> dict[str, list[str]]:
        out = {}
        for arq in self.arquivos_parecer():
            dados = arq.read_bytes()
            if arq.suffix.lower() == ".pdf":
                texto = texto_pdf(dados)
            elif arq.suffix.lower() == ".csv":
                texto = dados.decode("utf-8-sig", errors="replace")
            else:
                from openpyxl import load_workbook
                import io
                wb = load_workbook(io.BytesIO(dados), read_only=True, data_only=True)
                texto = "\n".join(" ".join(str(c) for c in r if c is not None) for ws in wb.worksheets for r in ws.iter_rows(values_only=True))
            out[arq.name] = verificar_anonimizacao(texto)
        return out

    def exigir_liberado(self, arq: Path) -> None:
        """Verificação local antes do uso: o arquivo precisa constar do registro de liberação da
        advogada com o MESMO conteúdo (sha256). Arquivo copiado à mão ou alterado é recusado."""
        h = hashlib.sha256(arq.read_bytes()).hexdigest()
        liberados, revogados = self.estado_liberacoes()
        if h in revogados:
            raise PermissionError(f"{arq.name}: versão REVOGADA ({revogados[h]}) — gere e libere nova cópia")
        if h not in liberados:
            raise PermissionError(f"{arq.name}: não liberado pela advogada (ou alterado após a liberação) — "
                                  "use 'cm-calc validacao liberar'")

    def estado_liberacoes(self) -> tuple[set[str], dict[str, str]]:
        """(hashes liberados, {hash revogado: motivo}). Revogação prevalece sobre liberação."""
        registro = self.pasta / "anonimizacao" / "liberacoes.jsonl"
        liberados: set[str] = set()
        revogados: dict[str, str] = {}
        if registro.exists():
            for linha in registro.read_text(encoding="utf-8").splitlines():
                if not linha.strip():
                    continue
                r = json.loads(linha)
                if r.get("revogado"):
                    revogados[r["sha256"]] = r.get("motivo", "")
                elif r.get("sha256"):
                    liberados.add(r["sha256"])
        return liberados, revogados

    def revogar(self, sha256: str, motivo: str, responsavel: str) -> None:
        """Revoga uma versão liberada (registro de auditoria só com hash, motivo e responsável)."""
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError("informe o SHA-256 completo (64 caracteres hexadecimais)")
        if not motivo.strip() or not responsavel.strip():
            raise ValueError("revogação exige motivo e responsável")
        liberados, revogados = self.estado_liberacoes()
        if sha256 not in liberados:
            raise ValueError("este SHA-256 não consta como liberado")
        if sha256 in revogados:
            return
        with (self.pasta / "anonimizacao" / "liberacoes.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"revogado": True, "sha256": sha256, "motivo": motivo.strip(), "por": responsavel.strip(),
                                "revogado_em": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False) + "\n")

    def ler_parecer(self) -> Parecer:
        for arq in self.arquivos_parecer():
            self.exigir_liberado(arq)
        pdfs = [a for a in self.arquivos_parecer() if a.suffix.lower() == ".pdf"]
        if not pdfs and not self.arquivos_parecer():
            raise FileNotFoundError(f"nenhum arquivo em {self.pasta / 'parecer'}")
        parecer = ler_parecer_pdf(pdfs[0].read_bytes(), pdfs[0].name) if pdfs else \
            Parecer(arquivo="(somente planilhas)", sha256="", tabelas={}, metodologia=[])
        # planilhas da perita têm prioridade sobre a leitura do PDF (sem risco de erro de extração)
        for arq in self.arquivos_parecer():
            if arq.suffix.lower() == ".xlsx":
                for ap, t in ler_parecer_xlsx(arq.read_bytes(), arq.name).items():
                    parecer.tabelas[ap] = t
            elif arq.suffix.lower() == ".csv":
                t = ler_parecer_csv(arq.read_bytes(), arq.name)
                parecer.tabelas[t.apendice] = t
        return parecer

    def ficha(self) -> FichaCaso:
        return carregar_ficha((self.pasta / "ficha.xlsx").read_bytes())

    def series(self) -> dict[str, SerieMensal]:
        out = {}
        for csv in sorted((self.pasta / "indices").glob("*.csv")):
            fonte = csv.with_suffix(".fonte.txt")
            if not fonte.exists():
                raise ValueError(f"{csv.name}: falta {fonte.name} com a fonte oficial da série")
            s = serie_de_csv(csv.stem.upper(), csv.read_bytes(), fonte.read_text(encoding="utf-8").strip(),
                             embute_correcao=csv.stem.upper().startswith("SELIC"))
            out[s.nome] = s
        return out

    def pendencias(self, parecer: Parecer, ficha: FichaCaso, series: dict[str, SerieMensal]) -> list[str]:
        pend = pendencias_ficha(ficha, set(parecer.tabelas))
        if not parecer.tabelas:
            pend.append("nenhuma tabela de apêndice reconhecida no parecer")
        idx = ficha.texto("indice_correcao")
        if "AP03" in parecer.tabelas and idx and idx.upper() not in series:
            pend.append(f"série {idx} não encontrada em indices/ (CSV + .fonte.txt)")
        return pend

    def executar(self, responsavel_anonimizacao: str | None = None) -> tuple[ResultadoValidacao, Path, Path]:
        restos = {k: v for k, v in self.verificar_anonimizacao().items() if v}
        if restos and not responsavel_anonimizacao:
            raise PermissionError("possíveis dados pessoais no parecer: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in restos.items())
                                  + " — anonimize ou confirme expressamente que são falsos positivos")
        parecer, ficha, series = self.ler_parecer(), self.ficha(), self.series()
        if ficha.texto("indice_correcao"):
            ficha.parametros["indice_correcao"] = ficha.texto("indice_correcao").upper()
        pend = self.pendencias(parecer, ficha, series)
        if pend:
            raise ValueError("validação bloqueada:\n- " + "\n- ".join(pend))
        rv = validar(ficha, parecer, series)
        saida = self.pasta / "saida"
        md = saida / "validacao.md"
        md.write_text(markdown(rv, parecer, self.id), encoding="utf-8")
        xlsx = planilha(rv, saida / "validacao.xlsx")
        registro = {"validacao": self.id, "executado_em": datetime.now().isoformat(timespec="seconds"),
                    "parecer_sha256": parecer.sha256, "anonimizacao_confirmada_por": responsavel_anonimizacao,
                    "reconstrucao": rv.principal.descricao,
                    "comparacoes": [c.model_dump(mode="json") for c in rv.comparacoes],
                    "inconsistencias": [i.model_dump() for i in rv.inconsistencias],
                    "cenarios": {k: [c.model_dump(mode="json") for c in v] for k, v in rv.cenarios.items()}}
        (saida / "comparativo.json").write_text(json.dumps(registro, ensure_ascii=False, indent=1), encoding="utf-8")
        return rv, md, xlsx
