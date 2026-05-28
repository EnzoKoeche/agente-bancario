"""Trilha de auditoria (RF-07). Registra cada passo: entrada, ferramenta chamada,
saída, versão de prompt/modelo. PII é mascarada antes de gravar."""
from __future__ import annotations
import json
import re
import time
from pathlib import Path
from typing import Any

_PII_PATTERNS = [
    (re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}"), "[CPF_MASCARADO]"),
    (re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}"), "[CNPJ_MASCARADO]"),
]


def mascarar_pii(texto: str) -> str:
    for pattern, repl in _PII_PATTERNS:
        texto = pattern.sub(repl, texto)
    return texto


class AuditLogger:
    def __init__(self, caminho: str = "eval/results/audit.log",
                 versao_prompt: str = "v1.0", versao_modelo: str = "desconhecido"):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.versao_prompt = versao_prompt
        self.versao_modelo = versao_modelo

    def registrar(self, etapa: str, payload: dict[str, Any]) -> None:
        entrada = {
            "ts": time.time(),
            "etapa": etapa,
            "versao_prompt": self.versao_prompt,
            "versao_modelo": self.versao_modelo,
            "payload": json.loads(mascarar_pii(json.dumps(payload, ensure_ascii=False, default=str))),
        }
        with self.caminho.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
