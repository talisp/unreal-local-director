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
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    arquivo = os.path.join(os.path.dirname(PASTA_RELATORIOS), "relatorios_arquivo")  # rotação (bloco 4)
    indice = os.path.join(arquivo, "indice.jsonl")
    ilegiveis = 0  # F10: uma linha cortada no índice não pode esconder os relatórios válidos que vêm depois dela
    if os.path.exists(indice):
        with open(indice, encoding="utf-8", errors="replace") as f:
            linhas = f.readlines()
        for linha in linhas:
            if not linha.strip():
                continue
            try:
                item = json.loads(linha)
                achou = item["id"] == rel_id
            except (ValueError, KeyError, TypeError):
                ilegiveis += 1
                continue
            if achou:
                with open(os.path.join(arquivo, item["arquivo"]), encoding="utf-8") as f:
                    rel = json.load(f)
                if ilegiveis and isinstance(rel, dict):  # a consulta vale, e a corrupção fica sinalizada
                    rel["aviso_indice"] = f"{ilegiveis} linha(s) ilegível(is) no índice do arquivo de relatórios"
                return rel
    sinal = f"; o índice do arquivo tem {ilegiveis} linha(s) ilegível(is), o relatório pode estar numa delas" if ilegiveis else ""
    raise FileNotFoundError(f"relatório {rel_id} não existe (use o campo 'id' devolvido pela macro){sinal}")


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
    gates, aviso = {}, None
    atores = (rel.get("medidas", {}).get("atores") or []) if macro == "plateia_em_loop" else []
    if atores:  # workflow: gates da última tentativa registrada DO ATOR NOMEADO
        # F04: antes valia sempre o 1º ator do relatório; a linha do ator B saía com os gates do ator A
        do_ator = [a for a in atores if isinstance(a, dict) and a.get("ator") == ator] if ator else atores[:1]
        if not do_ator:
            aviso = f"ator {ator!r} não está no relatório: gates não registrados"
        for g in ((do_ator[0].get("tentativas") or [{}])[-1].get("gates") or []) if do_ator else []:
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
        "restaurado": restaurado, "restauracao": restauracao, "licao": licao, "aviso": aviso,
    }
    if extra:
        # F03: `extra` só ACRESCENTA. Os campos da linha vêm do relatório e dos argumentos; um extra de mesmo nome
        # (ok, relatorio_id, fonte, gates...) não os substitui e fica anotado.
        recusados = sorted(k for k in extra if k in linha or k == "extra_recusado")
        linha.update({k: v for k, v in extra.items() if k not in recusados})
        if recusados:
            linha["extra_recusado"] = recusados
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
