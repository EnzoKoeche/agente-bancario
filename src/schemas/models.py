"""Schemas de validação. Toda saída do extrator é validada contra estes modelos.
Campos ausentes são None — NUNCA inventados. Isso é o que impede alucinação numérica."""
from __future__ import annotations
from typing import Optional, Literal
from pydantic import BaseModel, Field


class FonteCampo(BaseModel):
    """Rastreia de qual documento e campo veio cada valor. Base da explicabilidade."""
    documento: str = Field(..., description="Nome/ID do documento de origem")
    campo: str = Field(..., description="Campo dentro do documento")
    confianca: float = Field(..., ge=0.0, le=1.0, description="Confiança da extração")


class ValorComFonte(BaseModel):
    valor: Optional[float] = None
    fonte: Optional[FonteCampo] = None


class DadosFinanceiros(BaseModel):
    """Dados extraídos do dossiê. Tudo opcional: ausência != zero."""
    renda_mensal: ValorComFonte = Field(default_factory=ValorComFonte)
    dividas_mensais: ValorComFonte = Field(default_factory=ValorComFonte)
    movimentacao_media: ValorComFonte = Field(default_factory=ValorComFonte)
    valor_solicitado: ValorComFonte = Field(default_factory=ValorComFonte)
    prazo_meses: ValorComFonte = Field(default_factory=ValorComFonte)


class Indicadores(BaseModel):
    """Saída das ferramentas determinísticas (NÃO do LLM)."""
    comprometimento_renda: Optional[float] = None
    nivel_endividamento: Optional[float] = None
    capacidade_pagamento: Optional[float] = None
    # Simulação do crédito solicitado (valor_solicitado + prazo_meses):
    parcela_estimada: Optional[float] = None             # parcela mensal estimada
    comprometimento_com_parcela: Optional[float] = None  # (dívidas + parcela) / renda
    capacidade_apos_parcela: Optional[float] = None      # renda - dívidas - parcela


class Inconsistencia(BaseModel):
    tipo: str
    valor_a: float
    valor_b: float
    divergencia: Optional[float] = None  # divergência relativa calculada pela tool
    severidade: Literal["baixa", "media", "alta"]


class PreParecer(BaseModel):
    """Resultado final. Sempre revisado por humano antes de qualquer decisão."""
    dados: DadosFinanceiros
    indicadores: Indicadores
    inconsistencias: list[Inconsistencia] = Field(default_factory=list)
    rascunho_texto: str = ""
    requer_atencao: bool = False
    escalado_para_humano: bool = True  # SEMPRE True por design
