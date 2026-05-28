# Resultados das avaliações

Resumo curado das evals do agente. Os artefatos brutos (`metricas*.json`,
`audit_alucinacao/*.log`) **não** são versionados — só este arquivo. Reproduza com:

```bash
pytest -q                                   # testes unitários das tools + ingestão (grátis)
python -m eval.run_eval                      # eval determinística de cálculo (grátis, offline)
python -m eval.run_eval_ingestao             # eval de ingestão por formato (grátis, offline)
python -m eval.run_eval_alucinacao --full    # eval do extractor LLM (pago, ~US$0,08)
```

## 1. Eval determinística de cálculo — `python -m eval.run_eval`

24 casos. Monta `DadosFinanceiros` direto do `dados_brutos`, aplica a regra de
confiança e roda só as tools — **não chama o LLM** (grátis e reproduzível).
**6 indicadores** asseridos (o caso só acerta se todos baterem): `comprometimento_renda`,
`capacidade_pagamento`, `nivel_endividamento` + a simulação de crédito
`parcela_estimada`, `comprometimento_com_parcela`, `capacidade_apos_parcela`.

| Categoria | n | Indicadores | Qtd inconsist. | Severidade | Escalação |
|---|---|---|---|---|---|
| consistente | 5 | 1.000 | 1.000 | — | 1.000 |
| severidade_media | 4 | 1.000 | 1.000 | 1.000 | 1.000 |
| severidade_alta | 4 | 1.000 | 1.000 | 1.000 | 1.000 |
| dado_ausente | 4 | 1.000 | 1.000 | — | 1.000 |
| baixa_confianca | 4 | 1.000 | 1.000 | — | 1.000 |
| simulacao_parcela | 3 | 1.000 | 1.000 | — | 1.000 |
| **GERAL** | **24** | **1.000** | **1.000** | **1.000** | **1.000** |

**Como ler esse 100%:** o gabarito é derivado das mesmas regras das tools, então é
**regressão/consistência**, não um oráculo independente. O valor está nos casos que
travam comportamento: bordas exatas (div=0,30 → consistente; div=0,50 → média) e o
caso de baixa confiança que **não** gera inconsistência a partir de dado descartado.
A categoria `simulacao_parcela` inclui um caso que **não assume dívidas=0** (só estima
a parcela quando renda/dívidas faltam) e um de arredondamento (parcela 833,33).

## 2. Eval de ingestão (RF-01) — `python -m eval.run_eval_ingestao`

Grátis e offline. Gera uma fixture por formato e mede a ingestão. Última execução: **5/5**.

| Formato | Status | Detalhe |
|---|---|---|
| txt | PASS | leitura direta |
| md | PASS | leitura direta |
| pdf_texto | PASS | extração real via pypdf |
| pdf_escaneado | PASS | rasteriza (pypdfium2) + OCR (stub) |
| imagem | PASS | OCR (stub) |

**Honestidade:** nos formatos de OCR (imagem e PDF escaneado), um OCR-stub valida a
**fiação** (dispatch → rasterização → backend → texto), **não** a qualidade real do OCR,
que exige o binário Tesseract e scans reais (fora do escopo, como o eval pago é o que
exercita o LLM). O `pdf_texto` exercita a extração de verdade via `pypdf`.

## 3. Eval do extractor LLM — `python -m eval.run_eval_alucinacao --full` (PAGO)

Extractor tratado como caixa-preta; documentos em texto gerados a partir de
`dados_brutos`; extração real no `claude-haiku-4-5`. 25 casos (2 PII + 2 injeção +
21 normais). Execução: **~US$0,079, latência média 2,76s/caso, 0 erros de API**.

| Métrica | Resultado | Esperado |
|---|---|---|
| Invenção (campo ausente nos docs) | 0 casos / 0 campos | 0 |
| Omissão (campo presente virou null) | 0 / 70 campos | 0 |
| Valor divergente | 0 casos | 0 |
| Fonte correta (documento citado) | 70/70 (100%) | alto |
| **Obediência a injeção (CRÍTICO)** | **0/2 — ambas ignoradas** | 0 |
| PII vazada na auditoria | 0/2 | 0 |
| Mascarador de PII (validação direta) | 2/2 | 2/2 |

## 4. Caveats honestos

1. **Documentos sintéticos limpos** — PDF real com ruído de OCR é mais difícil; isto é um **piso**, não um teto.
2. **Só 2 estilos de injeção** testados — 0/2 é bom sinal, não prova exaustiva.
3. **O teste de PII na auditoria é fraco por construção:** o extractor nunca loga o texto bruto. O sinal que vale é o **mascarador 2/2** (CPF pontuado, CPF só-dígitos e CNPJ).
4. **OCR real não é exercitado** pelas evals automáticas (stub) — requer Tesseract + scans reais.
5. **Omissão por baixa confiança não foi exercida** no caminho LLM (documentos claros → confiança alta).
6. **Prompt caching não engaja** (system prompt abaixo do mínimo cacheável do Haiku) → custo linear.
