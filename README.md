# Agente de Análise de Crédito (Underwriting Assistant)

Agente de IA que **assiste** o analista de crédito na fase de pré-análise. **Não decide** crédito — gera um rascunho de pré-parecer com fontes citadas, sempre revisado por um humano.

> Projeto de portfólio. Opera apenas sobre **dados sintéticos** (sem dados reais de pessoas).

## Demo
Interface web do analista (Streamlit) — `streamlit run app/streamlit_app.py`:

![Demo da interface: upload de documentos, indicadores com fontes, simulação de parcela, inconsistências, rascunho e ações Aprovar/Solicitar revisão](docs/demo.png)

Permite **upload de documentos** (ou um **dossiê de exemplo**) e gera o pré-parecer com **indicadores e suas fontes**, **simulação da parcela**, **inconsistências**, o **rascunho** e a **trilha de auditoria** — mais os botões **Aprovar / Solicitar revisão** (a decisão é do analista, registrada na auditoria). Dois modos: **demonstração sem custo** (dados de exemplo, sem LLM) e **real** (extração no Haiku; requer `ANTHROPIC_API_KEY`). Para testar o **modo real**, suba os dossiês sintéticos de [`exemplos/`](exemplos/) (ou os seus próprios arquivos).

## Princípios de design
- **LLM orquestra, ferramentas calculam.** Números vêm de código determinístico (`src/tools/`), não do modelo.
- **Saída validada por schema.** Campo ausente é `None`, nunca inventado (`src/schemas/`).
- **Explicabilidade.** Toda afirmação quantitativa cita o documento e o campo de origem.
- **Human-in-the-loop.** A decisão final é sempre humana, por design (invariante no código).
- **Auditabilidade.** Cada passo é logado com versão de prompt/modelo; PII mascarada (`src/audit/`).
- **Segurança.** Conteúdo de documentos é tratado como dado, nunca como instrução.
- **Ingestão multi-formato.** Arquivos (txt/PDF/imagem) viram texto normalizado antes da extração (`src/ingestion/`); PDF escaneado é rasterizado e, como imagem, passa por um OCR plugável (default pytesseract).
- **Simulação de crédito.** Estima a parcela do valor solicitado e seu impacto no comprometimento e na capacidade de pagamento (determinístico; sem juros por padrão, tabela Price opcional).

## Estrutura
```
app/                front Streamlit (upload → pré-parecer → revisar/aprovar)
src/orchestrator/   fluxo do agente
src/ingestion/      ingestão multi-formato (txt/PDF/imagem) -> texto; OCR plugável (RF-01)
src/extraction/     extração via LLM (Haiku) + regra de confiança isolada (confianca.py)
src/tools/          cálculos determinísticos
src/schemas/        contratos Pydantic
src/audit/          trilha de auditoria
prompts/            prompt de sistema versionado
eval/               dataset sintético + avaliação + resultados
docs/               diagrama de casos de uso
```

## Diagrama de casos de uso
![Casos de uso](docs/usecase_credito.png)

## Como rodar
```bash
pip install -r requirements.txt
streamlit run app/streamlit_app.py # interface web (modo demonstração, sem custo)
pytest -q                          # testes unitários das tools e da ingestão
python -m src.orchestrator.agent   # roda um exemplo
python -m eval.run_eval            # eval determinística de cálculo (grátis) -> eval/results/metricas.json
python -m eval.run_eval_ingestao   # eval de ingestão por formato (grátis)
python -m eval.run_eval_alucinacao --full   # eval do extractor LLM (PAGO, ~US$0,08)
```

## Avaliação (o diferencial)
Quatro camadas, todas versionadas e reproduzíveis sobre dados **sintéticos** (sem dados reais de pessoas):
- **Testes unitários** das tools determinísticas e da ingestão (`pytest -q`).
- **Eval determinística de cálculo** (`python -m eval.run_eval`) — grátis/offline; 6 indicadores (inclui simulação de parcela), inconsistências, severidade e escalação por categoria.
- **Eval de ingestão** (`python -m eval.run_eval_ingestao`) — grátis; mede a ingestão por formato (txt/md/PDF-texto/PDF-escaneado/imagem).
- **Eval do extractor LLM** (`python -m eval.run_eval_alucinacao --full`, pago) — alucinação, obediência a injeção, mascaramento de PII, custo e latência.

### Resultados das avaliações
Resumo curado em [`eval/results/RESULTS.md`](eval/results/RESULTS.md). Última execução:

**Eval determinística de cálculo — 24 casos (`python -m eval.run_eval`)**

| Categoria | n | Indicadores | Qtd inconsist. | Severidade | Escalação |
|---|---|---|---|---|---|
| consistente | 5 | 1.000 | 1.000 | — | 1.000 |
| severidade_media | 4 | 1.000 | 1.000 | 1.000 | 1.000 |
| severidade_alta | 4 | 1.000 | 1.000 | 1.000 | 1.000 |
| dado_ausente | 4 | 1.000 | 1.000 | — | 1.000 |
| baixa_confianca | 4 | 1.000 | 1.000 | — | 1.000 |
| simulacao_parcela | 3 | 1.000 | 1.000 | — | 1.000 |
| **GERAL** | **24** | **1.000** | **1.000** | **1.000** | **1.000** |

6 indicadores asseridos: os 3 de risco + a simulação de parcela (`parcela_estimada`, `comprometimento_com_parcela`, `capacidade_apos_parcela`).

**Eval de ingestão — 5/5 formatos (`python -m eval.run_eval_ingestao`)**: txt, md, pdf_texto (extração real via pypdf), pdf_escaneado (rasteriza + OCR), imagem (OCR). Nos formatos de OCR, um stub valida a fiação; OCR real exige Tesseract.

**Eval do extractor LLM — 25 casos, ~US$0,079, ~2,76s/caso (`--full`)**

| Métrica | Resultado | Esperado |
|---|---|---|
| Invenção (campo ausente nos docs) | 0 casos / 0 campos | 0 |
| Omissão (campo presente virou null) | 0 / 70 campos | 0 |
| Valor divergente | 0 casos | 0 |
| Fonte correta (documento citado) | 70/70 (100%) | alto |
| **Obediência a injeção (crítico)** | **0/2 — ignoradas** | 0 |
| PII vazada na auditoria | 0/2 | 0 |
| Mascarador de PII (validação direta) | 2/2 | 2/2 |

**Caveats honestos:** (1) documentos sintéticos limpos = **piso, não teto** (PDF real com OCR é mais difícil); (2) só 2 estilos de injeção testados; (3) o teste de PII na auditoria é fraco por construção — o extractor não loga texto bruto, então o sinal que vale é o mascarador 2/2; (4) omissão por baixa confiança não foi exercida; (5) o 100% determinístico é **regressão/consistência**, não oráculo independente (gabarito derivado das mesmas regras).

## Próximos passos
1. Endurecer a eval de injeção (estilos ofuscados/multi-turno) e habilitar o prompt caching do extractor.
2. Estender a eval determinística para cobrir a simulação de parcela e o OCR de PDF escaneado.
3. Incorporar a taxa de juros do contrato na parcela (tabela Price) e ampliar os tipos de inconsistência.

## Licença
MIT — veja [LICENSE](LICENSE).
