"""registrar_tentativa (exp4, Hermes 06/10): a linha do diário sai do relatório REAL da macro.

Preferência: o relatório é lido do disco pelo `id` que a própria macro gravou (work/relatorios/<id>.json), então
nenhum número passa pelo LLM. Aceita também o JSON colado pelo agente, mas a linha fica marcada fonte="colado".
O agente só fornece o que o relatório não tem: rodada, tema, caso, ator, previsão, restauração e lição.
"""
import datetime
import json
import os
import re

from .macros import RAIZ_WORK

PASTA_RELATORIOS = os.path.join(RAIZ_WORK, "relatorios")
PASTA_DIARIO = os.path.join(RAIZ_WORK, "bancada_hermes")


def carregar_relatorio(rel_id: str) -> dict:
    if not re.fullmatch(r"[0-9A-Za-z_-]{6,80}", rel_id or ""):
        raise ValueError(f"id de relatório inválido: {rel_id!r}")
    caminho = os.path.join(PASTA_RELATORIOS, rel_id + ".json")
    if os.path.exists(caminho):
        return json.load(open(caminho, encoding="utf-8"))
    arquivo = os.path.join(os.path.dirname(PASTA_RELATORIOS), "relatorios_arquivo")  # rotação (bloco 4)
    indice = os.path.join(arquivo, "indice.jsonl")
    if os.path.exists(indice):
        for linha in open(indice, encoding="utf-8"):
            if linha.strip() and json.loads(linha)["id"] == rel_id:
                return json.load(open(os.path.join(arquivo, json.loads(linha)["arquivo"]), encoding="utf-8"))
    raise FileNotFoundError(f"relatório {rel_id} não existe (use o campo 'id' devolvido pela macro)")


def _gate_resumo(g: dict) -> str:
    v = g.get("valor")
    if isinstance(v, dict):
        v = "/".join(str(x) for x in v.values())
    elif isinstance(v, list):
        v = str([x if not isinstance(x, dict) else x.get("dist_cm", x) for x in v])[:60]
    return f"{g.get('resultado')} ({v})"


def linha_do_relatorio(rel: dict, *, macro: str, ator: str = "", clipe: str = "", rodada: int | None = None,
                       tema: str = "", caso: str = "", previsao: str = "", restaurado=None,
                       restauracao: str = "", licao: str = "", tipo: str = "tentativa", fonte: str = "",
                       extra: dict | None = None) -> dict:
    """Monta a linha do diário a partir do relatório devolvido pela macro (dict, como ela voltou)."""
    gates = {}
    tent = (rel.get("medidas", {}).get("atores") or [{}])[0].get("tentativas") if macro == "plateia_em_loop" else None
    if tent:  # workflow: gates da última tentativa registrada por ator
        for g in (tent[-1].get("gates") or []):
            gates[g["nome"]] = _gate_resumo(g)
    else:
        for g in rel.get("medidas", {}).get("gates", []):
            gates[g["nome"]] = _gate_resumo(g)
    linha = {
        "tipo": tipo, "rodada": rodada,
        "hora": datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S"),
        "tema": tema, "caso": caso, "ator": ator, "clipe": clipe, "previsao": previsao, "macro": macro,
        "ok": rel.get("ok"), "gates": gates, "bloqueio": rel.get("bloqueio"),
        "segundos": rel.get("segundos"), "chamadas": rel.get("chamadas"),
        "relatorio_id": rel.get("id"), "fonte": fonte,
        "restaurado": restaurado, "restauracao": restauracao, "licao": licao,
    }
    if extra:
        linha.update(extra)
    return {k: v for k, v in linha.items() if v not in (None, "", {}, [])}


def registrar(rel: dict, diretorio: str | None = None, **kw) -> dict:
    """Igual a linha_do_relatorio e acrescenta no diario.jsonl. O diretório é fixo pelo servidor (não vem do agente)."""
    linha = linha_do_relatorio(rel, **kw)
    diretorio = diretorio or PASTA_DIARIO
    os.makedirs(diretorio, exist_ok=True)
    caminho = os.path.join(diretorio, "diario.jsonl")
    with open(caminho, "a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    return {"ok": True, "arquivo": caminho, "linha": linha}
