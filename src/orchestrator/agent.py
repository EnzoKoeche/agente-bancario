"""Orquestrador. Controla o fluxo: extrair -> calcular -> detectar -> redigir -> escalar.
O LLM raciocina e redige; os números vêm SEMPRE das ferramentas. Decisão final = humano."""
from __future__ import annotations
from typing import Any
from src.schemas.models import PreParecer
from src.extraction.extractor import extrair_dados
from src.tools.financeiro import calcular_indicadores, detectar_inconsistencias
from src.audit.logger import AuditLogger


def gerar_pre_parecer(documentos: dict[str, Any],
                      audit: AuditLogger | None = None) -> PreParecer:
    audit = audit or AuditLogger()

    # 1. Extração (validada por schema)
    dados = extrair_dados(documentos, audit)

    # 2. Cálculo determinístico (ferramentas, não LLM)
    indicadores = calcular_indicadores(dados)
    audit.registrar("indicadores", {"indicadores": indicadores.model_dump()})

    # 3. Detecção de inconsistências (determinística)
    inconsistencias = detectar_inconsistencias(dados)
    audit.registrar("inconsistencias", {"qtd": len(inconsistencias)})

    # 4. Rascunho textual (aqui entraria o LLM, citando as fontes de cada número)
    rascunho = _montar_rascunho(dados, indicadores, inconsistencias)

    parecer = PreParecer(
        dados=dados,
        indicadores=indicadores,
        inconsistencias=inconsistencias,
        rascunho_texto=rascunho,
        requer_atencao=len(inconsistencias) > 0,
        escalado_para_humano=True,  # invariante de design
    )
    audit.registrar("pre_parecer", {"requer_atencao": parecer.requer_atencao})
    return parecer


def _montar_rascunho(dados, indicadores, inconsistencias) -> str:
    """Placeholder textual. Em produção, substituído por geração via LLM
    com instrução de citar a fonte de cada valor (ver prompts/system_prompt.md)."""
    linhas = ["RASCUNHO DE PRÉ-PARECER (revisão humana obrigatória)\n"]
    if indicadores.comprometimento_renda is not None:
        linhas.append(f"- Comprometimento de renda: {indicadores.comprometimento_renda*100:.1f}%")
    if inconsistencias:
        linhas.append(f"- ATENÇÃO: {len(inconsistencias)} inconsistência(s) detectada(s).")
    else:
        linhas.append("- Nenhuma inconsistência automática detectada.")
    return "\n".join(linhas)


if __name__ == "__main__":
    exemplo = {
        "contracheque.pdf": (
            "DEMONSTRATIVO DE PAGAMENTO\n"
            "Funcionário: (dados mascarados)\n"
            "Salário base: R$ 7.200,00\n"
            "Renda líquida mensal: R$ 8.000,00\n"
        ),
        "serasa.pdf": (
            "RELATÓRIO DE CRÉDITO\n"
            "Compromissos mensais (parcelas/financiamentos): R$ 2.500,00\n"
        ),
        "extrato.pdf": (
            "EXTRATO BANCÁRIO — últimos 6 meses\n"
            "Movimentação média mensal de créditos: R$ 3.000,00\n"
        ),
    }
    p = gerar_pre_parecer(exemplo)
    print(p.rascunho_texto)
