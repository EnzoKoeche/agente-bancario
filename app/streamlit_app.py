"""Front (Streamlit) do Assistente de Pré-Análise de Crédito.

Camada FINA e ADITIVA sobre o pipeline (`src/orchestrator/agent.py`): não duplica
regra de negócio nem toca os invariantes. O agente NÃO decide — produz um RASCUNHO
que o analista revisa e aprova (human-in-the-loop).

Rodar:  streamlit run app/streamlit_app.py

Modos:
- Demonstração (sem custo): dossiês de exemplo (dados pré-carregados). Roda as tools
  determinísticas e o rascunho via um extrator-stub injetado — sem chamar o LLM, sem
  API key.
- Real (LLM, pago): upload de documentos (txt/PDF/imagem); extração real no Haiku
  (~US$0,003/análise). Requer ANTHROPIC_API_KEY no .env. OCR de imagem/PDF escaneado
  exige o binário Tesseract.
"""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path

# A raiz do repo precisa estar no sys.path (o Streamlit roda a partir do dir do script).
RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import os
import streamlit as st
from dotenv import load_dotenv

from src.schemas.models import DadosFinanceiros, ValorComFonte, FonteCampo
from src.orchestrator.agent import gerar_pre_parecer, gerar_pre_parecer_de_arquivos
from src.audit.logger import AuditLogger

load_dotenv(RAIZ / ".env")

CAMPOS_ROTULO = {
    "renda_mensal": "Renda mensal",
    "dividas_mensais": "Dívidas mensais",
    "movimentacao_media": "Movimentação média",
    "valor_solicitado": "Valor solicitado",
    "prazo_meses": "Prazo (meses)",
}


def brl(v) -> str:
    if v is None:
        return "—"
    return "R$ " + f"{v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def pct(frac) -> str:
    return "—" if frac is None else f"{frac * 100:.1f}%".replace(".", ",")


def _fmt_valor(campo: str, v) -> str:
    if v is None:
        return "—"
    return f"{int(v)} meses" if campo == "prazo_meses" else brl(v)


def _vcf(valor, doc, campo, conf=0.95) -> ValorComFonte:
    return ValorComFonte(valor=valor, fonte=FonteCampo(documento=doc, campo=campo, confianca=conf))


# Dossiês de exemplo (modo demonstração) — dados já estruturados.
DOSSIES_DEMO = {
    "Cliente consistente": DadosFinanceiros(
        renda_mensal=_vcf(8000, "contracheque.pdf", "Renda líquida mensal"),
        dividas_mensais=_vcf(2000, "serasa.pdf", "Compromissos mensais"),
        movimentacao_media=_vcf(7800, "extrato.pdf", "Movimentação média"),
    ),
    "Inconsistência renda × movimentação": DadosFinanceiros(
        renda_mensal=_vcf(10000, "contracheque.pdf", "Renda líquida mensal"),
        dividas_mensais=_vcf(3000, "serasa.pdf", "Compromissos mensais"),
        movimentacao_media=_vcf(3500, "extrato.pdf", "Movimentação média"),
    ),
    "Com simulação de crédito": DadosFinanceiros(
        renda_mensal=_vcf(8000, "contracheque.pdf", "Renda líquida mensal"),
        dividas_mensais=_vcf(2000, "serasa.pdf", "Compromissos mensais"),
        valor_solicitado=_vcf(12000, "proposta.pdf", "Valor solicitado"),
        prazo_meses=_vcf(24, "proposta.pdf", "Prazo (meses)"),
    ),
}


def _extrator_stub(dados_preset: DadosFinanceiros):
    """Extrator injetável que devolve dados já estruturados (modo demo, sem LLM)."""
    def _stub(documentos, audit):
        audit.registrar("extracao_inicio", {"docs": list(documentos.keys()), "modo": "demonstracao"})
        audit.registrar("extracao_fim", {"dados": dados_preset.model_dump(), "modo": "demonstracao"})
        return dados_preset
    return _stub


def _novo_audit() -> AuditLogger:
    tmp = Path(tempfile.mkdtemp(prefix="parecer_")) / "audit.log"
    return AuditLogger(caminho=str(tmp), versao_prompt="front-v1", versao_modelo="-")


def _analisar_demo(nome: str):
    audit = _novo_audit()
    parecer = gerar_pre_parecer({"dossie_exemplo": nome}, audit,
                                extrator=_extrator_stub(DOSSIES_DEMO[nome]))
    return parecer, audit


def _analisar_real(uploads, audit: AuditLogger):
    pasta = Path(tempfile.mkdtemp(prefix="upload_"))
    for up in uploads:
        (pasta / up.name).write_bytes(up.getbuffer())
    return gerar_pre_parecer_de_arquivos(pasta, audit)


def _render_indicadores(ind) -> None:
    st.subheader("Indicadores")
    c1, c2, c3 = st.columns(3)
    c1.metric("Comprometimento de renda", pct(ind.comprometimento_renda))
    c2.metric("Capacidade de pagamento", brl(ind.capacidade_pagamento))
    c3.metric("Nível de endividamento", pct(ind.nivel_endividamento))

    if ind.parcela_estimada is not None:
        st.caption("Simulação do crédito solicitado")
        d1, d2, d3 = st.columns(3)
        d1.metric("Parcela estimada", brl(ind.parcela_estimada))
        d2.metric("Comprometimento c/ a parcela", pct(ind.comprometimento_com_parcela))
        d3.metric("Capacidade após a parcela", brl(ind.capacidade_apos_parcela))


def _render_fontes(dados: DadosFinanceiros) -> None:
    st.subheader("Dados extraídos e suas fontes")
    linhas = []
    for campo in DadosFinanceiros.model_fields:
        vcf = getattr(dados, campo)
        if vcf.valor is None:
            continue
        fonte = vcf.fonte
        linhas.append({
            "Campo": CAMPOS_ROTULO.get(campo, campo),
            "Valor": _fmt_valor(campo, vcf.valor),
            "Documento": fonte.documento if fonte else "—",
            "Campo de origem": fonte.campo if fonte else "—",
            "Confiança": f"{fonte.confianca:.2f}" if fonte else "—",
        })
    if linhas:
        st.dataframe(linhas, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum dado foi extraído com confiança suficiente — escalado para revisão humana.")


def _render_inconsistencias(inconsistencias) -> None:
    st.subheader("Inconsistências")
    if not inconsistencias:
        st.success("Nenhuma inconsistência automática detectada.")
        return
    for inc in inconsistencias:
        div = f" · divergência {pct(inc.divergencia)}" if inc.divergencia is not None else ""
        st.warning(
            f"**[{inc.severidade}] {inc.tipo}**{div}  \n"
            f"valor A = {brl(inc.valor_a)} · valor B = {brl(inc.valor_b)}"
        )


def _render_trilha(audit: AuditLogger) -> None:
    with st.expander("Trilha de auditoria (PII mascarada)"):
        caminho = Path(audit.caminho)
        if caminho.exists():
            st.code(caminho.read_text(encoding="utf-8"), language="json")
        else:
            st.write("Sem registros.")


def _render_acao_humana(audit: AuditLogger) -> None:
    st.subheader("Decisão do analista (human-in-the-loop)")
    st.caption("O agente não decide. A ação abaixo é do analista e fica registrada na auditoria.")
    nota = st.text_input("Observação do analista (opcional)")
    c1, c2 = st.columns(2)
    if c1.button("✅ Aprovar rascunho", use_container_width=True):
        audit.registrar("decisao_humana", {"acao": "aprovado", "observacao": nota})
        st.success("Decisão registrada: rascunho APROVADO pelo analista (gravado na auditoria).")
    if c2.button("✋ Solicitar revisão", use_container_width=True):
        audit.registrar("decisao_humana", {"acao": "revisao_solicitada", "observacao": nota})
        st.info("Decisão registrada: REVISÃO solicitada pelo analista (gravado na auditoria).")


def main() -> None:
    st.set_page_config(page_title="Pré-Análise de Crédito", page_icon="🏦", layout="wide")
    st.title("🏦 Assistente de Pré-Análise de Crédito")
    st.warning("**RASCUNHO assistivo — a decisão é do analista.** O agente não aprova nem recusa crédito.")

    st.sidebar.header("Entrada")
    modo = st.sidebar.radio("Modo", ["Demonstração (sem custo)", "Real (LLM, pago)"])

    if modo.startswith("Demonstração"):
        nome = st.sidebar.selectbox("Dossiê de exemplo", list(DOSSIES_DEMO))
        st.sidebar.caption("Dados pré-carregados; roda as tools sem chamar o LLM.")
        if st.sidebar.button("Gerar pré-parecer", type="primary", use_container_width=True):
            parecer, audit = _analisar_demo(nome)
            st.session_state["res"] = {"parecer": parecer, "audit": audit}
    else:
        tem_chave = bool(os.environ.get("ANTHROPIC_API_KEY"))
        if not tem_chave:
            st.sidebar.error("ANTHROPIC_API_KEY ausente no .env — modo real indisponível.")
        uploads = st.sidebar.file_uploader(
            "Documentos (txt, PDF, imagem)", type=["txt", "md", "pdf", "png", "jpg", "jpeg"],
            accept_multiple_files=True)
        st.sidebar.caption("Extração real no Haiku (~US$0,003/análise). OCR de imagem exige Tesseract.")
        if st.sidebar.button("Gerar pré-parecer", type="primary", use_container_width=True,
                             disabled=not (tem_chave and uploads)):
            audit = _novo_audit()
            try:
                parecer = _analisar_real(uploads, audit)
                st.session_state["res"] = {"parecer": parecer, "audit": audit}
            except Exception as e:  # noqa: BLE001 — superfície de UI: erro amigável
                st.session_state.pop("res", None)
                st.error(f"Falha na análise: {type(e).__name__}: {e}")

    res = st.session_state.get("res")
    if not res:
        st.info("Escolha a entrada na barra lateral e clique em **Gerar pré-parecer**.")
        return

    parecer, audit = res["parecer"], res["audit"]
    _render_indicadores(parecer.indicadores)
    _render_fontes(parecer.dados)
    _render_inconsistencias(parecer.inconsistencias)

    st.subheader("Rascunho do pré-parecer")
    st.code(parecer.rascunho_texto, language="text")

    _render_trilha(audit)
    _render_acao_humana(audit)


if __name__ == "__main__":
    main()
