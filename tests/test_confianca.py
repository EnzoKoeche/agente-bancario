"""Testes da regra de confiança (src/extraction/confianca.py).
Essa regra é o gatilho de escalação: valor fraco vira None em vez de ser usado."""
from __future__ import annotations

from src.schemas.models import DadosFinanceiros, ValorComFonte, FonteCampo
from src.extraction.confianca import aplicar_regras_de_confianca, LIMIAR_CONFIANCA


def _vcf(valor: float, confianca: float) -> ValorComFonte:
    return ValorComFonte(valor=valor, fonte=FonteCampo(documento="d.pdf", campo="c", confianca=confianca))


def test_confianca_abaixo_do_limiar_descarta():
    dados = DadosFinanceiros(renda_mensal=_vcf(8000, 0.4))
    aplicar_regras_de_confianca(dados)
    assert dados.renda_mensal.valor is None


def test_confianca_no_limiar_mantem():
    # 0.6 == LIMIAR e a regra é '< LIMIAR' (estrita), então 0.6 sobrevive.
    dados = DadosFinanceiros(renda_mensal=_vcf(8000, LIMIAR_CONFIANCA))
    aplicar_regras_de_confianca(dados)
    assert dados.renda_mensal.valor == 8000


def test_confianca_sem_fonte_descarta():
    dados = DadosFinanceiros(renda_mensal=ValorComFonte(valor=8000, fonte=None))
    aplicar_regras_de_confianca(dados)
    assert dados.renda_mensal.valor is None


def test_confianca_valor_ausente_segue_none():
    dados = DadosFinanceiros()  # tudo None
    aplicar_regras_de_confianca(dados)
    assert dados.renda_mensal.valor is None  # sem erro, segue ausente


def test_confianca_preserva_campo_forte_e_descarta_fraco():
    dados = DadosFinanceiros(
        renda_mensal=_vcf(8000, 0.95),   # forte -> mantém
        dividas_mensais=_vcf(2000, 0.3),  # fraco -> descarta
    )
    aplicar_regras_de_confianca(dados)
    assert dados.renda_mensal.valor == 8000
    assert dados.dividas_mensais.valor is None
