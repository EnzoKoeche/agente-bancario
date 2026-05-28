"""Camada de ingestão (RF-01): arquivos -> dict[nome, texto] para o pipeline.

É um front ADITIVO: não toca extração, tools, schemas nem o system prompt.
O texto normalizado que sai daqui é exatamente o que `gerar_pre_parecer` consome.

Dispatch por extensão:
  - .txt / .md  -> leitura direta de texto.
  - .pdf        -> texto via pypdf; sem camada de texto, rasteriza (pypdfium2) e aplica OCR.
  - imagem      -> OCR via backend PLUGÁVEL. Default: pytesseract (requer o binário
    Tesseract instalado no SO). Injete `ocr=` para usar outro backend (ou nos testes).

Imports das libs (pypdf, pytesseract, Pillow) são PREGUIÇOSOS: importar este módulo
não exige nenhuma delas; só falha se você de fato ingerir o formato correspondente
sem a dependência. Assim a eval determinística nunca arrasta essas libs.

O conteúdo extraído é DADO, nunca instrução — a defesa contra injeção vive no extractor.
"""
from __future__ import annotations
from pathlib import Path
from typing import Callable, Iterable

# Backend de OCR: recebe o caminho de uma imagem e devolve o texto reconhecido.
OcrBackend = Callable[[Path], str]

EXT_TEXTO = {".txt", ".md"}
EXT_PDF = {".pdf"}
EXT_IMAGEM = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
EXT_SUPORTADAS = EXT_TEXTO | EXT_PDF | EXT_IMAGEM


class IngestaoError(Exception):
    """Erro base da ingestão."""


class FormatoNaoSuportadoError(IngestaoError):
    """Extensão de arquivo fora do conjunto suportado."""


class PdfSemTextoError(IngestaoError):
    """PDF sem camada de texto (provável escaneado) — exigiria OCR de página."""


class OcrIndisponivelError(IngestaoError):
    """Backend de OCR não configurado para ingerir imagem."""


def _ler_texto(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8", errors="replace")


def _texto_de_pdf(caminho: Path, ocr: OcrBackend | None = None) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:  # dependência opcional, importada sob demanda
        raise IngestaoError("Leitura de PDF requer 'pypdf' (pip install pypdf).") from e

    leitor = PdfReader(str(caminho))
    partes = [(pagina.extract_text() or "").strip() for pagina in leitor.pages]
    texto = "\n".join(p for p in partes if p)
    if texto.strip():
        return texto
    # Sem camada de texto (provável PDF escaneado): rasteriza as páginas e aplica OCR.
    return _ocr_pdf_escaneado(caminho, ocr)


def _ocr_pytesseract(caminho: Path) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:  # dependência opcional + binário Tesseract no SO
        raise OcrIndisponivelError(
            "OCR de imagem requer 'pytesseract' + 'Pillow' (pip install pytesseract Pillow) "
            "e o binário Tesseract instalado no SO. Alternativa: injete um backend via `ocr=`."
        ) from e
    return pytesseract.image_to_string(Image.open(caminho))


def _ocr_pdf_escaneado(caminho: Path, ocr: OcrBackend | None = None) -> str:
    """PDF sem camada de texto: rasteriza cada página (pypdfium2) e aplica o backend de OCR.
    Reusa o mesmo OCR plugável das imagens (default pytesseract; injetável via `ocr=`)."""
    import tempfile
    backend = ocr or _ocr_pytesseract
    try:
        import pypdfium2 as pdfium
    except ImportError as e:  # dependência opcional, importada sob demanda
        raise PdfSemTextoError(
            f"'{caminho.name}' não tem camada de texto; o OCR de PDF escaneado requer "
            "'pypdfium2' (pip install pypdfium2). Alternativa: ingira as páginas como imagem."
        ) from e

    pdf = pdfium.PdfDocument(str(caminho))
    textos: list[str] = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(len(pdf)):
                imagem = pdf[i].render(scale=200 / 72).to_pil()
                destino = Path(tmp) / f"pagina_{i}.png"
                imagem.save(str(destino))
                textos.append(backend(destino).strip())
    finally:
        pdf.close()

    texto = "\n".join(t for t in textos if t)
    if not texto.strip():
        raise PdfSemTextoError(
            f"'{caminho.name}': páginas rasterizadas, mas o OCR não retornou texto."
        )
    return texto


def ingerir_arquivo(caminho: str | Path, ocr: OcrBackend | None = None) -> str:
    """Lê um único arquivo e devolve o texto extraído, escolhendo o leitor pela extensão."""
    caminho = Path(caminho)
    if not caminho.is_file():
        raise IngestaoError(f"Arquivo não encontrado: {caminho}")

    ext = caminho.suffix.lower()
    if ext in EXT_TEXTO:
        return _ler_texto(caminho)
    if ext in EXT_PDF:
        return _texto_de_pdf(caminho, ocr=ocr)
    if ext in EXT_IMAGEM:
        backend = ocr or _ocr_pytesseract
        return backend(caminho)
    raise FormatoNaoSuportadoError(
        f"Extensão não suportada: '{ext}'. Suportadas: {sorted(EXT_SUPORTADAS)}"
    )


def ingerir(origem: str | Path | Iterable[str | Path],
            ocr: OcrBackend | None = None) -> dict[str, str]:
    """Ingere um arquivo, um diretório (todos os formatos suportados nele) ou uma lista
    de caminhos, e devolve {nome_do_arquivo: texto} pronto para `gerar_pre_parecer`.

    Em modo diretório, arquivos de formato não suportado são ignorados; com um caminho
    explícito de formato não suportado, levanta FormatoNaoSuportadoError."""
    if isinstance(origem, (str, Path)):
        p = Path(origem)
        if p.is_dir():
            caminhos = sorted(f for f in p.iterdir()
                              if f.is_file() and f.suffix.lower() in EXT_SUPORTADAS)
        else:
            caminhos = [p]
    else:
        caminhos = [Path(c) for c in origem]

    documentos: dict[str, str] = {}
    for c in caminhos:
        documentos[c.name] = ingerir_arquivo(c, ocr=ocr)
    return documentos
