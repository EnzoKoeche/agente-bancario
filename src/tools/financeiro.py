"""Ferramentas determinísticas. O LLM CHAMA estas funções; ele não calcula nada.
Cálculo em código = preciso, testável e auditável. Esse é o coração do padrão
'LLM orquestra, ferramentas calculam'."""
from __future__ import annotations
from typing import Optional
from src.schemas.models import DadosFinanceiros, Indicadores, Inconsistencia


def calcular_comprometimento_renda(renda: float, dividas: float) -> float:
    """% da renda comprometida com dívidas. Determinístico."""
    if renda <= 0:
        raise ValueError("Renda deve ser positiva")
    return round(dividas / renda, 4)


def calcular_capacidade_pagamento(renda: float, dividas: float) -> float:
    """Renda livre após dívidas."""
    return round(renda - dividas, 2)


def calcular_indicadores(dados: DadosFinanceiros) -> Indicadores:
    """Orquestra os cálculos a partir dos dados extraídos.
    Se um insumo necessário estiver ausente, o indicador fica None (não chuta)."""
    ind = Indicadores()
    renda = dados.renda_mensal.valor
    dividas = dados.dividas_mensais.valor

    if renda is not None and dividas is not None and renda > 0:
        ind.comprometimento_renda = calcular_comprometimento_renda(renda, dividas)
        ind.capacidade_pagamento = calcular_capacidade_pagamento(renda, dividas)
        ind.nivel_endividamento = round(dividas / renda, 4)
    return ind


def detectar_inconsistencias(
    dados: DadosFinanceiros, limiar_relativo: float = 0.30
) -> list[Inconsistencia]:
    """Compara campos que deveriam ser coerentes. Determinístico e auditável."""
    achados: list[Inconsistencia] = []
    renda = dados.renda_mensal.valor
    movimentacao = dados.movimentacao_media.valor

    if renda is not None and movimentacao is not None and renda > 0:
        divergencia = abs(renda - movimentacao) / renda
        if divergencia > limiar_relativo:
            achados.append(
                Inconsistencia(
                    tipo="renda_vs_movimentacao",
                    descricao=(
                        f"Renda declarada (R${renda:.2f}) diverge "
                        f"{divergencia*100:.1f}% da movimentação média "
                        f"(R${movimentacao:.2f})."
                    ),
                    valor_a=renda,
                    valor_b=movimentacao,
                    severidade="alta" if divergencia > 0.5 else "media",
                )
            )
    return achados


# Registro de ferramentas exposto ao orquestrador
TOOLS = {
    "calcular_indicadores": calcular_indicadores,
    "detectar_inconsistencias": detectar_inconsistencias,
}
