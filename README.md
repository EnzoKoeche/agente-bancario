# Agente de Análise de Crédito (Underwriting Assistant)

Agente de IA que **assiste** o analista de crédito na fase de pré-análise. **Não decide** crédito — gera um rascunho de pré-parecer com fontes citadas, sempre revisado por um humano.

## Princípios de design
- **LLM orquestra, ferramentas calculam.** Números vêm de código determinístico (`src/tools/`), não do modelo.
- **Saída validada por schema.** Campo ausente é `None`, nunca inventado (`src/schemas/`).
- **Explicabilidade.** Toda afirmação quantitativa cita o documento e o campo de origem.
- **Human-in-the-loop.** A decisão final é sempre humana, por design (invariante no código).
- **Auditabilidade.** Cada passo é logado com versão de prompt/modelo; PII mascarada (`src/audit/`).
- **Segurança.** Conteúdo de documentos é tratado como dado, nunca como instrução.

## Estrutura
```
src/orchestrator/   fluxo do agente
src/extraction/     extração validada (stub -> trocar por LLM)
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
python -m src.orchestrator.agent   # roda um exemplo
python -m eval.run_eval            # gera métricas em eval/results/metricas.json
```

## Avaliação (o diferencial)
O script de eval mede acurácia de indicadores e de detecção de inconsistências sobre dados **sintéticos** (sem dados reais de pessoas). Em produção, acrescente: taxa de alucinação, custo médio por dossiê e latência.

## Próximos passos
1. Trocar o stub do extrator por chamada real ao LLM com structured output.
2. Ampliar o dataset sintético e adicionar métricas de alucinação/custo/latência.
3. Adicionar testes unitários das ferramentas determinísticas.
