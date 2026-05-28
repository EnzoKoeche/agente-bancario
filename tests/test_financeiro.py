"""Testes das ferramentas determinísticas (src/tools/financeiro.py).
São o coração do invariante 'LLM orquestra, ferramentas calculam' — então
travamos o comportamento numérico, incluindo bordas e casos degenerados."""
from __future__ import annotations
import pytest

from src.schemas.models import DadosFinanceiros, ValorComFonte, FonteCampo
from src.tools.financeiro import (
    calcular_comprometimento_renda,
    calcular_capacidade_pagamento,
    calcular_parcela,
    calcular_indicadores,
    detectar_inconsistencias,
)


def _vcf(valor: float, confianca: float = 0.9) -> ValorComFonte:
    """ValorComFonte com fonte confiável (não é descartado pela regra de confiança)."""
    return ValorComFonte(valor=valor, fonte=FonteCampo(documento="doc.pdf", campo="c", confianca=confianca))


# --- calcular_comprometimento_renda --------------------------------------

def test_comprometimento_valor_normal():
    assert calcular_comprometimento_renda(8000, 2000) == 0.25


def test_comprometimento_renda_zero_levanta_valueerror():
    with pytest.raises(ValueError):
        calcular_comprometimento_renda(0, 1000)


def test_comprometimento_divida_maior_que_renda_passa_de_1():
    valor = calcular_comprometimento_renda(8000, 10000)
    assert valor > 1.0
    assert valor == 1.25


# --- calcular_capacidade_pagamento ----------------------------------------

def test_capacidade_normal():
    assert calcular_capacidade_pagamento(8000, 2000) == 6000.0


def test_capacidade_negativa_quando_divida_maior():
    assert calcular_capacidade_pagamento(8000, 10000) == -2000.0


def test_capacidade_com_centavos():
    assert calcular_capacidade_pagamento(7000, 1500.50) == 5499.5


# --- calcular_indicadores -------------------------------------------------

def test_indicadores_campos_ausentes_viram_none_nao_zero():
    ind = calcular_indicadores(DadosFinanceiros())
    assert ind.comprometimento_renda is None
    assert ind.capacidade_pagamento is None
    assert ind.nivel_endividamento is None


def test_indicadores_renda_zero_tudo_none_sem_levantar():
    # renda=0 NÃO levanta aqui: o guard `renda > 0` impede a chamada que levantaria.
    dados = DadosFinanceiros(renda_mensal=_vcf(0), dividas_mensais=_vcf(2000))
    ind = calcular_indicadores(dados)
    assert ind.comprometimento_renda is None
    assert ind.capacidade_pagamento is None
    assert ind.nivel_endividamento is None


def test_indicadores_caso_feliz_os_tres():
    dados = DadosFinanceiros(renda_mensal=_vcf(8000), dividas_mensais=_vcf(2000))
    ind = calcular_indicadores(dados)
    assert ind.comprometimento_renda == 0.25
    assert ind.capacidade_pagamento == 6000.0
    assert ind.nivel_endividamento == 0.25
    # Documenta a redundância real: nivel_endividamento usa a MESMA fórmula
    # de comprometimento_renda na tool (round(dividas/renda, 4)).
    assert ind.nivel_endividamento == ind.comprometimento_renda


# --- detectar_inconsistencias (bordas EXATAS) -----------------------------

def test_inconsistencia_borda_030_nenhuma():
    # |10000-7000|/10000 = 0.30; limiar é '> 0.30' (estrito) -> nenhuma.
    dados = DadosFinanceiros(renda_mensal=_vcf(10000), movimentacao_media=_vcf(7000))
    assert detectar_inconsistencias(dados) == []


def test_inconsistencia_borda_050_media():
    # |10000-5000|/10000 = 0.50; 'alta' só se > 0.5 -> media.
    dados = DadosFinanceiros(renda_mensal=_vcf(10000), movimentacao_media=_vcf(5000))
    incons = detectar_inconsistencias(dados)
    assert len(incons) == 1
    assert incons[0].severidade == "media"
    assert incons[0].divergencia == 0.5


def test_inconsistencia_acima_050_alta():
    # |10000-3500|/10000 = 0.65 -> alta.
    dados = DadosFinanceiros(renda_mensal=_vcf(10000), movimentacao_media=_vcf(3500))
    incons = detectar_inconsistencias(dados)
    assert len(incons) == 1
    assert incons[0].severidade == "alta"
    assert incons[0].divergencia == 0.65


def test_inconsistencia_sem_movimentacao_lista_vazia():
    # Insumo ausente -> não detecta (não chuta).
    dados = DadosFinanceiros(renda_mensal=_vcf(10000))
    assert detectar_inconsistencias(dados) == []


# --- calcular_parcela + simulação de impacto ------------------------------

def test_parcela_sem_juros():
    assert calcular_parcela(12000, 24) == 500.0  # 12000 / 24


def test_parcela_prazo_invalido_levanta():
    with pytest.raises(ValueError):
        calcular_parcela(12000, 0)


def test_parcela_com_juros_price():
    # Price: PV=10000, i=2% a.m., n=12 -> PMT ~ R$ 945,60
    assert abs(calcular_parcela(10000, 12, taxa_mensal=0.02) - 945.60) < 0.5


def test_indicadores_parcela_impacto_completo():
    dados = DadosFinanceiros(
        renda_mensal=_vcf(8000), dividas_mensais=_vcf(2000),
        valor_solicitado=_vcf(12000), prazo_meses=_vcf(24),
    )
    ind = calcular_indicadores(dados)
    assert ind.parcela_estimada == 500.0
    assert ind.comprometimento_com_parcela == 0.3125   # (2000 + 500) / 8000
    assert ind.capacidade_apos_parcela == 5500.0       # 8000 - 2000 - 500


def test_indicadores_parcela_sem_renda_nao_assume_zero():
    # valor + prazo presentes, mas renda/dívidas ausentes: estima a parcela,
    # mas NÃO calcula o impacto (ausência != zero).
    dados = DadosFinanceiros(valor_solicitado=_vcf(12000), prazo_meses=_vcf(24))
    ind = calcular_indicadores(dados)
    assert ind.parcela_estimada == 500.0
    assert ind.comprometimento_com_parcela is None
    assert ind.capacidade_apos_parcela is None


def test_indicadores_sem_credito_solicitado_parcela_none():
    dados = DadosFinanceiros(renda_mensal=_vcf(8000), dividas_mensais=_vcf(2000))
    ind = calcular_indicadores(dados)
    assert ind.parcela_estimada is None
