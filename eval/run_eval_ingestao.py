"""Eval de ingestão (RF-01) — grátis e offline.

Mede a camada `src/ingestion` sobre fixtures geradas em tempo de execução, um formato
por vez, e grava um placar por formato. NÃO chama API nem requer o binário Tesseract.

Honestidade sobre OCR: nos formatos baseados em OCR (imagem e PDF escaneado) injeta-se
um OCR-stub determinístico. Isso valida a FIAÇÃO (dispatch -> rasterização do PDF via
pypdfium2 -> backend de OCR -> texto), NÃO a qualidade real do OCR — que exige Tesseract
e documentos reais (fora do escopo, assim como o eval pago é o que exercita o LLM).
O formato `pdf_texto` usa fpdf2 para gerar um PDF real e exercita a extração de verdade
(pypdf), sem stub.
"""
from __future__ import annotations
import json
import tempfile
from pathlib import Path

from src.ingestion.ingestor import ingerir_arquivo

SAIDA = Path(__file__).resolve().parents[1] / "eval" / "results" / "metricas_ingestao.json"

MARCA_OCR = "RENDA-OCR 8000"  # marcador retornado pelo OCR-stub para checar a fiação


def _ocr_stub(caminho: Path) -> str:
    return MARCA_OCR


def _res(formato: str, ok, detalhe: str) -> dict:
    return {"formato": formato, "ok": ok, "detalhe": detalhe}


def _check_txt(d: Path) -> dict:
    f = d / "dossie.txt"
    f.write_text("Renda liquida mensal: 8000", encoding="utf-8")
    return _res("txt", "8000" in ingerir_arquivo(f), "leitura direta")


def _check_md(d: Path) -> dict:
    f = d / "nota.md"
    f.write_text("# Documento\nMovimentacao media: 7800", encoding="utf-8")
    return _res("md", "7800" in ingerir_arquivo(f), "leitura direta")


def _check_pdf_texto(d: Path) -> dict:
    try:
        from fpdf import FPDF
    except ImportError:
        return _res("pdf_texto", None, "pulado: fpdf2 ausente (gera a fixture)")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, "Renda liquida mensal: 8000")
    f = d / "contracheque.pdf"
    f.write_bytes(bytes(pdf.output()))
    return _res("pdf_texto", "8000" in ingerir_arquivo(f), "extracao real via pypdf")


def _check_pdf_escaneado(d: Path) -> dict:
    try:
        import pypdfium2  # noqa: F401
        from pypdf import PdfWriter
    except ImportError:
        return _res("pdf_escaneado", None, "pulado: requer pypdf + pypdfium2")
    escritor = PdfWriter()
    escritor.add_blank_page(width=300, height=300)
    f = d / "escaneado.pdf"
    with f.open("wb") as fh:
        escritor.write(fh)
    texto = ingerir_arquivo(f, ocr=_ocr_stub)  # rasteriza (pypdfium2) -> OCR-stub
    return _res("pdf_escaneado", MARCA_OCR in texto, "rasteriza + OCR (stub)")


def _check_imagem(d: Path) -> dict:
    f = d / "holerite.png"
    f.write_bytes(b"\x89PNG conteudo-irrelevante")
    return _res("imagem", MARCA_OCR in ingerir_arquivo(f, ocr=_ocr_stub), "OCR (stub)")


def avaliar() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        checagens = [_check_txt(d), _check_md(d), _check_pdf_texto(d),
                     _check_pdf_escaneado(d), _check_imagem(d)]

    rodados = [c for c in checagens if c["ok"] is not None]
    pulados = [c["formato"] for c in checagens if c["ok"] is None]
    metricas = {
        "formatos_ok": sum(1 for c in rodados if c["ok"]),
        "formatos_rodados": len(rodados),
        "formatos_pulados": pulados,
        "detalhe": checagens,
        "observacao": ("OCR injetado (stub) em imagem e pdf_escaneado valida a fiacao "
                       "rasterizar->OCR, nao a qualidade real do OCR (que exige Tesseract)."),
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(metricas, ensure_ascii=False, indent=2), encoding="utf-8")
    _imprimir(metricas)
    return metricas


def _imprimir(m: dict) -> None:
    print("=" * 62)
    print("EVAL DE INGESTAO (RF-01) — gratis, sem API nem Tesseract")
    print("=" * 62)
    print(f"{'formato':<16}{'status':>7}  detalhe")
    print("-" * 62)
    for c in m["detalhe"]:
        status = "—" if c["ok"] is None else ("PASS" if c["ok"] else "FAIL")
        print(f"{c['formato']:<16}{status:>7}  {c['detalhe']}")
    print("-" * 62)
    pulados = ", ".join(m["formatos_pulados"]) or "nenhum"
    print(f"OK: {m['formatos_ok']}/{m['formatos_rodados']} rodados | pulados: {pulados}")
    print(m["observacao"])


if __name__ == "__main__":
    avaliar()
