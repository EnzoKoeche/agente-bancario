"""Testes da camada de ingestão (src/ingestion/ingestor.py) — RF-01.
Cobrem o dispatch por extensão sem depender do binário Tesseract: o OCR é
injetado, e o caso de PDF sem texto usa um PDF real em branco (via pypdf)."""
from __future__ import annotations
import pytest

from src.ingestion import ingestor
from src.ingestion.ingestor import (
    ingerir,
    ingerir_arquivo,
    FormatoNaoSuportadoError,
    PdfSemTextoError,
    OcrIndisponivelError,
)

try:
    import pypdf  # noqa: F401
    TEM_PYPDF = True
except ImportError:
    TEM_PYPDF = False

try:
    import pytesseract  # noqa: F401
    TEM_TESSERACT = True
except ImportError:
    TEM_TESSERACT = False


def test_txt_leitura_direta(tmp_path):
    f = tmp_path / "contracheque.txt"
    f.write_text("Renda liquida mensal: R$ 8.000,00", encoding="utf-8")
    assert "8.000,00" in ingerir_arquivo(f)


def test_md_suportado(tmp_path):
    f = tmp_path / "nota.md"
    f.write_text("# Doc\nMovimentacao: 7800", encoding="utf-8")
    assert "7800" in ingerir_arquivo(f)


def test_imagem_usa_backend_ocr_injetado(tmp_path):
    # Conteúdo do arquivo é irrelevante: o backend de OCR é injetado.
    img = tmp_path / "scan.png"
    img.write_bytes(b"\x89PNG conteudo-falso")
    texto = ingerir_arquivo(img, ocr=lambda caminho: "Renda: 5000")
    assert texto == "Renda: 5000"


def test_extensao_nao_suportada_levanta(tmp_path):
    f = tmp_path / "planilha.xlsx"
    f.write_bytes(b"x")
    with pytest.raises(FormatoNaoSuportadoError):
        ingerir_arquivo(f)


def test_arquivo_inexistente_levanta(tmp_path):
    with pytest.raises(Exception):
        ingerir_arquivo(tmp_path / "nao_existe.txt")


def test_diretorio_ingere_apenas_suportados(tmp_path):
    (tmp_path / "a.txt").write_text("renda 8000", encoding="utf-8")
    (tmp_path / "b.md").write_text("dividas 2000", encoding="utf-8")
    (tmp_path / "ignorar.xlsx").write_bytes(b"x")  # ignorado em modo diretório
    docs = ingerir(tmp_path)
    assert set(docs) == {"a.txt", "b.md"}
    assert docs["a.txt"] == "renda 8000"


def test_lista_de_caminhos(tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("x", encoding="utf-8")
    b = tmp_path / "b.txt"
    b.write_text("y", encoding="utf-8")
    assert ingerir([a, b]) == {"a.txt": "x", "b.txt": "y"}


def test_pdf_dispatch_para_extrator_de_texto(tmp_path, monkeypatch):
    # Verifica que .pdf é roteado para _texto_de_pdf (sem precisar de um PDF real com texto).
    monkeypatch.setattr(ingestor, "_texto_de_pdf", lambda caminho: "Renda: 9000")
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.4 conteudo-falso")
    assert ingerir_arquivo(f) == "Renda: 9000"


@pytest.mark.skipif(not TEM_PYPDF, reason="pypdf não instalado")
def test_pdf_sem_camada_de_texto_levanta(tmp_path):
    from pypdf import PdfWriter
    escritor = PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    f = tmp_path / "escaneado.pdf"
    with f.open("wb") as fh:
        escritor.write(fh)
    with pytest.raises(PdfSemTextoError):
        ingerir_arquivo(f)


@pytest.mark.skipif(TEM_TESSERACT, reason="pytesseract instalado: backend default disponível")
def test_imagem_sem_backend_nem_pytesseract_da_erro_claro(tmp_path):
    img = tmp_path / "scan.png"
    img.write_bytes(b"x")
    with pytest.raises(OcrIndisponivelError):
        ingerir_arquivo(img)  # sem ocr injetado e sem pytesseract no ambiente
