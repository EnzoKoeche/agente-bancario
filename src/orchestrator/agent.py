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


def gerar_pre_parecer_de_arquivos(origem, audit: AuditLogger | None = None, ocr=None) -> PreParecer:
    """Conveniência RF-01: ingere arquivos (txt/pdf/imagem) e gera o pré-parecer.
    `origem` pode ser um arquivo, um diretório ou uma lista de caminhos.
    Import preguiçoso da ingestão para não arrastar pypdf/Pillow ao resto do pipeline."""
    from src.ingestion.ingestor import ingerir
    documentos = ingerir(origem, ocr=ocr)
    return gerar_pre_parecer(documentos, audit)


def _montar_rascunho(dados, indicadores, inconsistencias) -> str:
    """Redige o rascunho de forma DETERMINÍSTICA: cada afirmação quantitativa
    imprime a fonte (documento + campo) dos seus insumos, lida do ValorComFonte.
    Insumo ausente (None) é declarado como 'dado ausente', nunca omitido."""

    def brl(v: float) -> str:
        # Formata em padrão BR: R$8.000,00 (milhar com ponto, decimal com vírgula).
        return "R$" + f"{v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")

    def pct(frac: float) -> str:
        return f"{frac * 100:.1f}%".replace(".", ",")

    def cite(rotulo, vcf) -> str:
        if vcf.valor is None:
            return f"{rotulo} dado ausente"
        if vcf.fonte is None:
            return f"{rotulo} {brl(vcf.valor)} — fonte ausente"
        return f'{rotulo} {brl(vcf.valor)} — {vcf.fonte.documento}, campo "{vcf.fonte.campo}"'

    def fonte_de_valor(v: float) -> str:
        # Recupera a fonte de um valor usado numa inconsistência, casando-o com o
        # campo de origem em `dados` (determinístico; sem chamar o LLM).
        for nome in dados.__class__.model_fields:
            vcf = getattr(dados, nome)
            if vcf.valor is not None and abs(vcf.valor - v) < 0.005:
                if vcf.fonte is None:
                    return f"{brl(v)} — fonte ausente"
                return f'{brl(v)} — {vcf.fonte.documento}, campo "{vcf.fonte.campo}"'
        return f"{brl(v)} — fonte ausente"

    linhas = ["RASCUNHO DE PRÉ-PARECER (revisão humana obrigatória)\n"]

    cit_renda = cite("renda", dados.renda_mensal)
    cit_dividas = cite("dívidas", dados.dividas_mensais)
    if indicadores.comprometimento_renda is not None:
        linhas.append(
            f"- Comprometimento de renda: {pct(indicadores.comprometimento_renda)} "
            f"({cit_renda}; {cit_dividas})"
        )
    else:
        linhas.append(
            f"- Comprometimento de renda: não calculável ({cit_renda}; {cit_dividas})"
        )

    if inconsistencias:
        linhas.append(f"- ATENÇÃO: {len(inconsistencias)} inconsistência(s) detectada(s):")
        for inc in inconsistencias:
            div = f" (divergência de {pct(inc.divergencia)})" if inc.divergencia is not None else ""
            linhas.append(f'    • Inconsistência [{inc.severidade}] — {inc.tipo}: valor A diverge de valor B{div}.')
            linhas.append(f"        - valor A: {fonte_de_valor(inc.valor_a)}")
            linhas.append(f"        - valor B: {fonte_de_valor(inc.valor_b)}")
    else:
        linhas.append("- Nenhuma inconsistência automática detectada.")

    return "\n".join(linhas)


if __name__ == "__main__":
    from pathlib import Path
    from dotenv import load_dotenv
    # Carrega ANTHROPIC_API_KEY do .env (não versionado) para o ambiente do processo.
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")

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
