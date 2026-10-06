"""Rotação de work/relatorios/ (v0.0.2, bloco 4). ARQUIVA, nunca apaga.

Política de retenção (explícita e testada). Um relatório fica ATIVO se qualquer regra abaixo vale:
  1. tem menos de DIAS_ATIVOS dias;
  2. não houve progresso medido DEPOIS dele na mesma linha OU na visão de sessão (o detector ainda precisa dele:
     antes de um progresso a escada já foi zerada, então o passado não muda o estado atual);
  3. é citado por corrida de experimento ABERTO;
  4. está na janela de uma aplicação de lição ainda sem voto (mesma linha, depois da aplicação).
Os demais vão para work/relatorios_arquivo/AAAA-MM/<id>.json, com uma linha em indice.jsonl (macro, chamada, ok,
versão do código) — a regressão e a auditoria continuam vendo; diario.carregar_relatorio lê do arquivo também.
"""
import datetime as dt
import glob
import json
import os

from . import emperramento as E
from .macros import RAIZ_WORK

DIAS_ATIVOS = 7


def _ultimo_progresso(est):
    p = [m["quando"] for m in est["marcos"] if m["tipo"] == "progresso"]
    return max(p) if p else None


def _add(prot: dict, rid: str, motivo: str):
    prot.setdefault(rid, [])
    if motivo not in prot[rid]:
        prot[rid].append(motivo)


def protegidos(itens: list, pasta_exp: str, pasta_licoes: str, agora: float, dias: float) -> dict:
    """{id_relatorio: [motivos]} dos relatórios que precisam ficar ativos (todos os motivos, não só o primeiro)."""
    prot = {}
    rels = [t for t in itens if t["fonte"] == "relatorio" and t.get("ref")]
    for t in rels:
        if agora - t["quando"] < dias * 86400:
            _add(prot, t["ref"], "recente")
    ses = _ultimo_progresso(E.avaliar_sessao(itens))
    for linha in {t.get("linha") for t in rels}:
        lim = _ultimo_progresso(E.avaliar(itens, linha))
        for t in rels:
            if t.get("linha") != linha:
                continue
            if lim is None or t["quando"] >= lim:
                _add(prot, t["ref"], "janela do detector (linha)")
            elif ses is None or t["quando"] >= ses:
                _add(prot, t["ref"], "janela do detector (sessão)")
    for arq in glob.glob(os.path.join(pasta_exp, "*.json")):
        e = json.load(open(arq, encoding="utf-8"))
        if e.get("estado") == "aberto":
            for c in e.get("corridas", []):
                for rid in c.get("relatorio_ids", []):
                    _add(prot, rid, f"experimento aberto {e['nome']}")
    arq_ap = os.path.join(pasta_licoes, "aplicacoes.jsonl")
    if os.path.exists(arq_ap):
        votos = json.load(open(os.path.join(pasta_licoes, "votos.json"), encoding="utf-8")) \
            if os.path.exists(os.path.join(pasta_licoes, "votos.json")) else {}
        resolvidas = set(votos.get("_resolvidas", []))
        for linha in open(arq_ap, encoding="utf-8"):
            if not linha.strip():
                continue
            ap = json.loads(linha)
            if ap["aplicacao"] not in resolvidas:
                for t in rels:
                    if t.get("linha") == ap["linha"] and t["quando"] >= ap["quando"]:
                        _add(prot, t["ref"], f"lição sem voto {ap['licao']}")
    return prot


def arquivar(agora: float, dias: float = DIAS_ATIVOS, pasta_rel: str = None, pasta_exp: str = None,
             pasta_arquivo: str = None, pasta_licoes: str = None) -> dict:
    from . import experimentos as X
    from . import resolver as RS
    pasta_rel = pasta_rel or os.path.join(RAIZ_WORK, "relatorios")
    pasta_exp = pasta_exp or X.PASTA
    pasta_arquivo = pasta_arquivo or os.path.join(RAIZ_WORK, "relatorios_arquivo")
    pasta_licoes = pasta_licoes or RS.PASTA_LICOES
    itens = E.carregar_historico(pasta_rel, pasta_exp)
    prot = protegidos(itens, pasta_exp, pasta_licoes, agora, dias)
    arquivados = []
    os.makedirs(pasta_arquivo, exist_ok=True)
    indice = os.path.join(pasta_arquivo, "indice.jsonl")
    for arq in sorted(glob.glob(os.path.join(pasta_rel, "*.json"))):
        rid = os.path.basename(arq)[:-5]
        if rid in prot:
            continue
        try:
            rel = json.load(open(arq, encoding="utf-8"))
        except (OSError, ValueError):
            continue  # ilegível: fica onde está (não some em silêncio)
        mes = rid[:6] if rid[:6].isdigit() else "sem-data"
        destino_dir = os.path.join(pasta_arquivo, f"{mes[:4]}-{mes[4:6]}" if mes != "sem-data" else mes)
        os.makedirs(destino_dir, exist_ok=True)
        destino = os.path.join(destino_dir, os.path.basename(arq))
        with open(indice, "a", encoding="utf-8") as f:  # índice ANTES de mover: nunca há relatório sem rastro
            f.write(json.dumps({"id": rid, "macro": rel.get("macro"), "chamada": rel.get("chamada"), "ok": rel.get("ok"),
                                "bloqueio": rel.get("bloqueio"), "ambiente": {"versao_codigo": (rel.get("ambiente") or {}).get("versao_codigo")},
                                "arquivo": os.path.relpath(destino, pasta_arquivo),
                                "arquivado_em": dt.datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False) + "\n")
        os.replace(arq, destino)
        arquivados.append(rid)
    return {"arquivados": arquivados, "protegidos": prot, "dias_ativos": dias}
