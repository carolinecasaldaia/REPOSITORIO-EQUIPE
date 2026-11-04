"""Armazenamento de casos em ~/CM-Calculos-Dados/casos/<id>/ (fora do código).

- Identificador interno sem nome/CPF (validado).
- Documentos importados ficam somente leitura (0400) e registrados com SHA-256.
- Diretórios com permissão 0700.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from .documentos.leitura import ler_arquivo, sha256
from .documentos.modelos import Documento


def raiz_dados() -> Path:
    """Pasta de dados: variável CM_CALC_DADOS (testes) ou ~/CM-Calculos-Dados."""
    return Path(os.environ.get("CM_CALC_DADOS", Path.home() / "CM-Calculos-Dados"))


RE_ID = re.compile(r"^[A-Z0-9][A-Z0-9\-]{2,39}$")


class Caso:
    def __init__(self, caso_id: str, raiz: Path | None = None):
        if not RE_ID.match(caso_id):
            raise ValueError("identificador do caso: 3–40 caracteres, MAIÚSCULAS, dígitos e hífen (sem nome/CPF)")
        if re.search(r"\d{11}|\d{3}\.\d{3}\.\d{3}", caso_id):
            raise ValueError("identificador do caso parece conter CPF")
        self.id = caso_id
        self.pasta = (raiz or raiz_dados()) / "casos" / caso_id

    @property
    def docs(self) -> Path:
        return self.pasta / "documentos"

    @property
    def manifesto(self) -> Path:
        return self.pasta / "manifesto.json"

    @property
    def arquivo_quadro(self) -> Path:
        return self.pasta / "extracao" / "quadro.json"

    def criar(self) -> None:
        for p in (self.pasta, self.docs, self.pasta / "extracao", self.pasta / "claude", self.pasta / "resultados"):
            p.mkdir(parents=True, exist_ok=True)
            os.chmod(p, 0o700)
        if not self.manifesto.exists():
            self._gravar_manifesto({"caso": self.id, "criado_em": datetime.now().isoformat(timespec="seconds"),
                                    "documentos": []})

    def _ler_manifesto(self) -> dict:
        return json.loads(self.manifesto.read_text(encoding="utf-8"))

    def _gravar_manifesto(self, m: dict) -> None:
        self.manifesto.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(self.manifesto, 0o600)

    def importar(self, origem: Path) -> str:
        return self.importar_bytes(origem.name, origem.read_bytes())

    def importar_bytes(self, nome: str, dados: bytes) -> str:
        """Importa conteúdo recebido pela interface (sem gravar cópia temporária fora do caso)."""
        nome = Path(nome).name
        if Path(nome).suffix.lower() not in (".pdf", ".csv", ".xlsx", ".txt"):
            raise ValueError(f"{nome}: formato não suportado (aceitos: PDF, CSV, XLSX, TXT)")
        self.criar()
        h = sha256(dados)
        m = self._ler_manifesto()
        if any(d["sha256"] == h for d in m["documentos"]):
            return f"{nome}: já importado (mesmo conteúdo)"
        destino = self.docs / f"{len(m['documentos']) + 1:03d}-{nome}"
        destino.write_bytes(dados)
        os.chmod(destino, 0o400)
        m["documentos"].append({"arquivo": destino.name, "original": nome, "sha256": h,
                                "importado_em": datetime.now().isoformat(timespec="seconds")})
        self._gravar_manifesto(m)
        return f"{nome}: importado como {destino.name}"

    def verificar_integridade(self) -> list[str]:
        problemas = []
        for d in self._ler_manifesto()["documentos"]:
            arq = self.docs / d["arquivo"]
            if not arq.exists():
                problemas.append(f"{d['arquivo']}: ausente")
            elif sha256(arq.read_bytes()) != d["sha256"]:
                problemas.append(f"{d['arquivo']}: conteúdo alterado após a importação")
        return problemas

    def ler_documentos(self) -> tuple[list[Documento], list[str]]:
        docs, avisos = [], []
        for d in self._ler_manifesto()["documentos"]:
            r = ler_arquivo(self.docs / d["arquivo"])
            docs += r.documentos
            avisos += r.avisos
        return docs, avisos

    def documentos_importados(self) -> list[dict]:
        return self._ler_manifesto()["documentos"] if self.manifesto.exists() else []

    @property
    def pasta_resultados(self) -> Path:
        return self.pasta / "resultados"


def listar_casos(raiz: Path | None = None) -> list[str]:
    pasta = (raiz or raiz_dados()) / "casos"
    return sorted(p.name for p in pasta.iterdir() if p.is_dir() and RE_ID.match(p.name)) if pasta.exists() else []
