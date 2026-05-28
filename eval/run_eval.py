"""Avaliação DETERMINÍSTICA do pipeline de cálculo (RF-03/RF-04/RF-06).

Por que determinística: o extractor já é LLM real (claude-haiku-4-5), então
chamar gerar_pre_parecer() aqui custaria dinheiro e o formato `dados_brutos`
não casa com a extração textual. Em vez disso, montamos DadosFinanceiros direto
do `dados_brutos`, aplicamos a MESMA regra de confiança do pipeline (reusada de
src.extraction.confianca — que NÃO importa `anthropic`) e rodamos as tools
determinísticas. Resultado: a eval é grátis, offline e reproduzível.

O que mede (por caso e por categoria):
  - acurácia dos 3 indicadores (comprometimento_renda, capacidade_pagamento,
    nivel_endividamento) — o caso só conta como acerto se os TRÊS baterem
  - acurácia da contagem de inconsistências
  - acurácia de severidade (só nos casos em que se espera inconsistência)
  - escalação correta: um campo que TINHA valor virou None pela regra de confiança

Nota: nivel_endividamento usa a MESMA fórmula de comprometimento_renda na tool
(round(dívidas/renda, 4)), logo são sempre idênticos; são asseridos em separado
apenas como guard contra drift entre as duas linhas de cálculo.

Fora de escopo (vai para um script PAGO, com casos em sintetico_llm.json):
alucinação do extractor, resistência a injeção e mascaramento de PII ponta-a-ponta
— tudo isso só é exercido com o LLM no circuito, que aqui não roda.
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path

from src.schemas.models import DadosFinanceiros, ValorComFonte, FonteCampo
from src.extraction.confianca import aplicar_regras_de_confianca, LIMIAR_CONFIANCA
from src.tools.financeiro import calcular_indicadores, detectar_inconsistencias

DATASET = "eval/datasets/sintetico.json"
SAIDA = "eval/results/metricas.json"

# Indicadores asseridos (todos calculados pelas tools determinísticas).
INDICADORES = ("comprometimento_renda", "capacidade_pagamento", "nivel_endividamento",
               "parcela_estimada", "comprometimento_com_parcela", "capacidade_apos_parcela")


def _aprox(a, b, tol: float = 1e-4) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def construir_dados(brutos: dict) -> DadosFinanceiros:
    """Monta DadosFinanceiros a partir do formato achatado do dataset
    (campo, campo_doc, campo_confianca). Determinístico — NÃO chama o LLM.
    Campo omitido vira ValorComFonte() vazio (ausência != zero)."""
    campos = {}
    for campo in DadosFinanceiros.model_fields:
        if brutos.get(campo) is None:
            continue
        doc = brutos.get(f"{campo}_doc")
        conf = brutos.get(f"{campo}_confianca")
        fonte = None
        if doc is not None and conf is not None:
            fonte = FonteCampo(documento=doc, campo=campo, confianca=conf)
        campos[campo] = ValorComFonte(valor=float(brutos[campo]), fonte=fonte)
    return DadosFinanceiros(**campos)


def avaliar_caso(caso: dict) -> dict:
    gab = caso["gabarito"]
    dados = construir_dados(caso["dados_brutos"])

    # Snapshot ANTES da regra (ela muta o objeto in-place).
    com_valor_antes = {c for c in DadosFinanceiros.model_fields
                       if getattr(dados, c).valor is not None}
    aplicar_regras_de_confianca(dados)
    com_valor_depois = {c for c in DadosFinanceiros.model_fields
                        if getattr(dados, c).valor is not None}
    # Escalação = um campo que TINHA valor foi descartado por confiança (virou None).
    escalou = bool(com_valor_antes - com_valor_depois)

    ind = calcular_indicadores(dados)
    incons = detectar_inconsistencias(dados)
    sev_obtida = incons[0].severidade if incons else None

    erros: list[str] = []

    # Indicadores: o caso só acerta se os TRÊS baterem.
    ok_por_ind: dict[str, bool] = {}
    for nome in INDICADORES:
        obtido = getattr(ind, nome)
        esperado = gab.get(nome)  # ausente no gabarito => espera None (não mascara valor real)
        ok = _aprox(obtido, esperado)
        ok_por_ind[nome] = ok
        if not ok:
            erros.append(f"{nome}: esperado {esperado}, obtido {obtido}")
    ok_ind = all(ok_por_ind.values())

    ok_qtd = len(incons) == gab["qtd_inconsistencias"]
    if not ok_qtd:
        erros.append(f"qtd_inconsistencias: esperado {gab['qtd_inconsistencias']}, "
                     f"obtido {len(incons)}")

    avalia_sev = gab["severidade_esperada"] is not None
    ok_sev = (sev_obtida == gab["severidade_esperada"]) if avalia_sev else None
    if avalia_sev and not ok_sev:
        erros.append(f"severidade: esperado {gab['severidade_esperada']}, obtido {sev_obtida}")

    ok_escal = escalou == gab["escalado_esperado"]
    if not ok_escal:
        erros.append(f"escalacao: esperado {gab['escalado_esperado']}, obtido {escalou}")

    return {
        "id": caso["id"],
        "categoria": caso["categoria"],
        "ok_ind": ok_ind,
        "ok_por_ind": ok_por_ind,
        "ok_qtd": ok_qtd,
        "ok_sev": ok_sev,  # None quando a categoria não espera inconsistência
        "ok_escal": ok_escal,
        "escalado_esperado": gab["escalado_esperado"],
        "escalou": escalou,
        "erros": erros,
    }


def _taxa(num: int, den: int):
    return round(num / den, 3) if den else None


def avaliar(dataset_path: str = DATASET) -> dict:
    casos = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    res = [avaliar_caso(c) for c in casos]
    total = len(res)

    sev_aval = [r for r in res if r["ok_sev"] is not None]
    esperam_escal = [r for r in res if r["escalado_esperado"]]
    geral = {
        "total_casos": total,
        "acuracia_indicadores": _taxa(sum(r["ok_ind"] for r in res), total),
        "acuracia_por_indicador": {
            nome: _taxa(sum(r["ok_por_ind"][nome] for r in res), total)
            for nome in INDICADORES
        },
        "acuracia_qtd_inconsistencias": _taxa(sum(r["ok_qtd"] for r in res), total),
        "acuracia_severidade": _taxa(sum(r["ok_sev"] for r in sev_aval), len(sev_aval)),
        "casos_severidade_avaliados": len(sev_aval),
        "acuracia_escalacao": _taxa(sum(r["ok_escal"] for r in res), total),
        "taxa_escalacao_correta": _taxa(sum(r["escalou"] for r in esperam_escal), len(esperam_escal)),
        "casos_escalacao_esperados": len(esperam_escal),
    }

    por_categoria = {}
    cats: dict[str, list] = defaultdict(list)
    for r in res:
        cats[r["categoria"]].append(r)
    for cat, rs in cats.items():
        sev_rs = [r for r in rs if r["ok_sev"] is not None]
        por_categoria[cat] = {
            "n": len(rs),
            "acuracia_indicadores": _taxa(sum(r["ok_ind"] for r in rs), len(rs)),
            "acuracia_qtd_inconsistencias": _taxa(sum(r["ok_qtd"] for r in rs), len(rs)),
            "acuracia_severidade": _taxa(sum(r["ok_sev"] for r in sev_rs), len(sev_rs)),
            "acuracia_escalacao": _taxa(sum(r["ok_escal"] for r in rs), len(rs)),
        }

    casos_falhos = [{"id": r["id"], "categoria": r["categoria"], "erros": r["erros"]}
                    for r in res if r["erros"]]

    metricas = {
        "limiar_confianca": LIMIAR_CONFIANCA,
        "geral": geral,
        "por_categoria": por_categoria,
        "casos_falhos": casos_falhos,
    }

    Path("eval/results").mkdir(parents=True, exist_ok=True)
    Path(SAIDA).write_text(json.dumps(metricas, ensure_ascii=False, indent=2), encoding="utf-8")
    _imprimir_tabela(metricas)
    return metricas


def _imprimir_tabela(m: dict) -> None:
    def cel(x) -> str:
        return "  —  " if x is None else f"{x:>5.3f}"

    g = m["geral"]
    print("=" * 66)
    print(f"EVAL DETERMINÍSTICA — {g['total_casos']} casos (sem chamada de API)")
    print(f"limiar de confiança = {m['limiar_confianca']}")
    print("=" * 66)
    print(f"{'categoria':<20}{'n':>3}  {'indic':>5} {'qtd':>5} {'sev':>5} {'escal':>5}")
    print("-" * 66)
    for cat, c in m["por_categoria"].items():
        print(f"{cat:<20}{c['n']:>3}  {cel(c['acuracia_indicadores'])} "
              f"{cel(c['acuracia_qtd_inconsistencias'])} {cel(c['acuracia_severidade'])} "
              f"{cel(c['acuracia_escalacao'])}")
    print("-" * 66)
    print(f"{'GERAL':<20}{g['total_casos']:>3}  {cel(g['acuracia_indicadores'])} "
          f"{cel(g['acuracia_qtd_inconsistencias'])} {cel(g['acuracia_severidade'])} "
          f"{cel(g['acuracia_escalacao'])}")
    print("=" * 66)
    print(f"Indicadores (acurácia individual — 'indic' acima exige os {len(INDICADORES)} juntos):")
    for nome in INDICADORES:
        print(f"  - {nome:<22} {cel(g['acuracia_por_indicador'][nome])}")
    print("  (nivel_endividamento == comprometimento_renda: mesma fórmula na tool)")
    print(f"Severidade avaliada em {g['casos_severidade_avaliados']} caso(s) com inconsistência.")
    print(f"Escalação esperada em {g['casos_escalacao_esperados']} caso(s); "
          f"recall = {cel(g['taxa_escalacao_correta'])}.")

    if m["casos_falhos"]:
        print(f"\n{len(m['casos_falhos'])} CASO(S) FALHO(S):")
        for f in m["casos_falhos"]:
            print(f"  - [{f['categoria']}] {f['id']}")
            for e in f["erros"]:
                print(f"      · {e}")
    else:
        print("\nTodos os casos bateram com o gabarito.")


if __name__ == "__main__":
    avaliar()
