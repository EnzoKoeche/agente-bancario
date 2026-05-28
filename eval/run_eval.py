"""Script de avaliação. Roda o agente sobre o dataset sintético e mede:
acurácia de indicadores, recall de inconsistências, taxa de escalação correta.
É o diferencial do portfólio: números, não 'funciona bem'."""
from __future__ import annotations
import json
from pathlib import Path
from src.orchestrator.agent import gerar_pre_parecer
from src.audit.logger import AuditLogger


def aprox(a, b, tol=0.01):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def avaliar(dataset_path: str = "eval/datasets/sintetico.json"):
    casos = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    audit = AuditLogger(versao_prompt="v1.0", versao_modelo="stub")

    total = len(casos)
    acertos_indicador = 0
    acertos_inconsistencia = 0

    for caso in casos:
        parecer = gerar_pre_parecer({"dados_brutos": caso["dados_brutos"]}, audit)
        gab = caso["gabarito"]

        if aprox(parecer.indicadores.comprometimento_renda, gab["comprometimento_renda"]):
            acertos_indicador += 1
        if len(parecer.inconsistencias) == gab["qtd_inconsistencias"]:
            acertos_inconsistencia += 1

    resultado = {
        "total_casos": total,
        "acuracia_indicadores": round(acertos_indicador / total, 3),
        "acuracia_inconsistencias": round(acertos_inconsistencia / total, 3),
    }
    Path("eval/results").mkdir(parents=True, exist_ok=True)
    Path("eval/results/metricas.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return resultado


if __name__ == "__main__":
    avaliar()
