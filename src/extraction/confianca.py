"""Regra de confiança da extração, isolada do SDK do LLM.

Vive em módulo próprio (não dentro de extractor.py) para poder ser reusada por
código determinístico — como a eval — SEM arrastar a dependência `anthropic`.
É a regra única do pipeline: valor sem fonte ou com confiança abaixo do limiar
vira None (ausência), em vez de ser usado como dado fraco. Ausência != zero, e
descartar um valor que existia é o gatilho de escalação para revisão humana."""
from __future__ import annotations
from src.schemas.models import DadosFinanceiros, ValorComFonte

LIMIAR_CONFIANCA = 0.6  # abaixo disso, o campo é descartado (vira None)


def aplicar_regras_de_confianca(dados: DadosFinanceiros) -> DadosFinanceiros:
    """Valor sem fonte ou com confiança abaixo do limiar vira None (escala para humano).
    Muta `dados` in-place e o devolve por conveniência."""
    for campo in DadosFinanceiros.model_fields:
        vcf: ValorComFonte = getattr(dados, campo)
        if vcf.valor is None:
            continue
        if vcf.fonte is None or vcf.fonte.confianca < LIMIAR_CONFIANCA:
            setattr(dados, campo, ValorComFonte())
    return dados
