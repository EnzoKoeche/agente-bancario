# Resultados das avaliações

Resumo curado das duas evals do agente. Os artefatos brutos (`metricas*.json`,
`audit_alucinacao/*.log`) **não** são versionados — só este arquivo. Reproduza com:

```bash
pytest -q                                  # testes unitários das tools (grátis)
python -m eval.run_eval                     # eval determinística (grátis, offline)
python -m eval.run_eval_alucinacao --full   # eval do extractor LLM (pago, ~US$0,08)
```

## 1. Eval determinística — `python -m eval.run_eval`

21 casos. Monta `DadosFinanceiros` direto do `dados_brutos`, aplica a regra de
confiança e roda só as tools — **não chama o LLM** (grátis e reproduzível).
Indicadores = `comprometimento_renda` + `capacidade_pagamento` + `nivel_endividamento`
(o caso só acerta se os três baterem).

| Categoria | n | Indicadores | Qtd inconsist. | Severidade | Escalação |
|---|---|---|---|---|---|
| consistente | 5 | 1.000 | 1.000 | — | 1.000 |
| severidade_media | 4 | 1.000 | 1.000 | 1.000 | 1.000 |
| severidade_alta | 4 | 1.000 | 1.000 | 1.000 | 1.000 |
| dado_ausente | 4 | 1.000 | 1.000 | — | 1.000 |
| baixa_confianca | 4 | 1.000 | 1.000 | — | 1.000 |
| **GERAL** | **21** | **1.000** | **1.000** | **1.000** | **1.000** |

**Como ler esse 100%:** o gabarito é derivado das mesmas regras das tools, então
isto é um teste de **regressão/consistência**, não um oráculo independente. O valor
está nos casos que travam comportamento: bordas exatas (div=0,30 → consistente;
div=0,50 → média, pelo `>` estrito) e o caso de baixa confiança que **não** gera
inconsistência a partir de dado descartado (evita falso positivo).

## 2. Eval do extractor LLM — `python -m eval.run_eval_alucinacao --full` (PAGO)

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

## 3. Caveats honestos

1. **Documentos sintéticos limpos** — PDF real com ruído de OCR é mais difícil; isto é um **piso**, não um teto.
2. **Só 2 estilos de injeção** testados — 0/2 é bom sinal, não prova exaustiva (faltam injeções ofuscadas/multi-turno).
3. **O teste "PII não vaza na auditoria" é fraco por construção:** o extractor nunca loga o texto bruto, então o CPF não chega ao log. O sinal que vale é o **mascarador 2/2**, que valida a regex sobre CPF pontuado, CPF só-dígitos e CNPJ.
4. **Omissão por baixa confiança não foi exercida** no caminho LLM (documentos claros → confiança alta do modelo).
5. **Prompt caching não engaja** (system prompt abaixo do mínimo cacheável do Haiku) → custo escala linear, sem desconto de cache.
