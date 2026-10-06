"""Workflows: processos limitados que encadeiam macros e gates e devolvem relatório (política, camada 3)."""
import time

from . import catalogo, gates
from . import macros as M


def _centro_pernas_cm(s: dict, px_por_cm: float) -> float:
    """Centro x (cm relativo à base) da REGIÃO DAS PERNAS (a mesma máscara abaixo de 80 cm do pes_plantados).
    Sway de tronco/braço não move as pernas plantadas; caminhar move. (exp2, Hermes 06/10: Talking_2, o controle
    canônico de conversa parada, reprovava em deriva_xy 21,0 porque o centro da silhueta inteira acompanha os braços.)"""
    import numpy as np
    m = s.get("_pernas")
    if m is None or not s.get("medido"):
        raise ValueError("amostra sem máscara de pernas")
    xs = np.nonzero(m.any(axis=0))[0]
    if not len(xs):
        raise ValueError("máscara de pernas vazia")
    return float((xs.mean() - s["_rx_mean_px"]) / px_por_cm)


def _gate_deriva(a: dict, tol: float) -> dict:
    """Uma cópia no estúdio tocando o loop, fotografada de lado e de frente em 4 instantes: um clipe que anda
    'passeia' na horizontal (ou sai do quadro, o que também reprova). A deriva mede o centro da REGIÃO DAS PERNAS
    (abaixo de 80 cm), não da silhueta inteira: gesticular de pé não anda (exp2)."""
    lat = M._amostrar_estudio(a, vista="lateral", n=4, intervalo=0.6)
    fr = M._amostrar_estudio(a, vista="frontal", n=4, intervalo=0.6)
    if any(not s.get("medido") for s in lat + fr):
        return [gates.g("deriva_xy", False, "saiu da janela de medida", f"<= {tol} cm")]
    try:
        # lateral vê o deslocamento para frente/trás; frontal vê o deslocamento para os lados (A07)
        pares = [(_centro_pernas_cm(s, s["px_por_cm"]), _centro_pernas_cm(f, f["px_por_cm"])) for s, f in zip(lat, fr)]
    except ValueError as e:
        return [gates.g("deriva_xy", False, f"pernas não mensuráveis: {e}", f"<= {tol} cm")]
    return [gates.deriva_xy(pares, tol), gates.pes_plantados(lat)]


@M.macro
def plateia_em_loop(rel, atores: list, texto: str = "idle talking conversation", candidatos: list | None = None,
                    max_quadros: int = 400, tentativas_por_ator: int = 4, deriva_max_cm: float = 15.0,
                    distancia_minima_cm: float = 45.0):
    """Dá a cada personagem da lista um loop discreto (conversa/idle), UM POR VEZ, sem mover ninguém.
    Para cada um: tenta clipes candidatos até um passar em tudo (de pé, pés no piso, ator parado, sem deriva,
    sem vizinho colado). Se nenhum passar, desfaz aquele personagem e PARA (não segue para o próximo).
    candidatos: nomes de clipes da biblioteca; se vazio, usa buscar_clipe(texto)."""
    if not candidatos:
        b = catalogo.buscar_clipe(texto, n=12, max_quadros=max_quadros)
        candidatos = [c["nome"] for c in b["medidas"].get("clipes", [])]
    if not candidatos:
        raise ValueError("sem clipes candidatos")
    resultado = []
    for i, ator in enumerate(atores):
        a = M.resolver_ator(ator)
        estado = M._props(a)
        ordem = candidatos[i % len(candidatos):] + candidatos[:i % len(candidatos)]  # varia o clipe entre vizinhos
        feito = None
        tentativas = []
        for clipe in ordem[:tentativas_por_ator]:
            ri = M.importar_clipe(clipe)
            if not ri["ok"]:
                tentativas.append({"clipe": clipe, "falha": ri["bloqueio"]})
                continue
            ra = M.aplicar_clipe(ator, clipe, loop=True, checar_movimento=False)  # o workflow mede deriva abaixo
            gs = list(ra["medidas"].get("gates", []))
            try:
                if ra["ok"]:
                    gs.extend(_gate_deriva(a, deriva_max_cm))
                    viz = M._vizinhos_bases(a)
                    perto = [v for v in viz if v["dist_cm"] < distancia_minima_cm]
                    gs.append(gates.g("distancia_vizinhos", not perto, viz[:2], f">= {distancia_minima_cm} cm"))
            except Exception as e:
                gs.append(gates.g("medicao_extra", False, f"{type(e).__name__}: {str(e)[:200]}", "sem erro"))
            passou = ra["ok"] and all(g["resultado"] == "PASS" for g in gs)
            tentativas.append({"clipe": clipe, "passou": passou, "gates": gs, "bloqueio": ra["bloqueio"],
                               "ajuste_z": ra["medidas"].get("silhueta", {}).get("ajuste_z_cm")})
            if passou:
                feito = clipe
                break
            if ra["ok"] or ra["medidas"].get("restaurado") is False:  # passou na macro mas não no workflow, ou restauração falhou
                if not M._restaurar(a, estado):
                    rel["medidas"]["atores"] = resultado + [{"ator": ator, "clipe": None, "tentativas": tentativas}]
                    raise RuntimeError(f"ESTADO PARCIAL em {ator}: restauração não conferiu; parei")
        resultado.append({"ator": ator, "clipe": feito, "tentativas": tentativas})
        if not feito:
            rel["bloqueio"] = f"nenhum clipe passou para {ator}; parei (os anteriores ficaram feitos, este foi restaurado)"
            break
    M.limpar_estudio()
    rel["medidas"]["atores"] = resultado
    rel["medidas"]["feitos"] = sum(1 for r in resultado if r["clipe"])
