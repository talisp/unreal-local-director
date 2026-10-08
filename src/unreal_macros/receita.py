"""Campos de passo da Fase 4 (as 3 ferramentas do Sequencer que o Qwen pediu na noite de 07/10), FORA da régua.

A régua (fila.py) não muda: o hash dela é a versão de toda medida da biblioteca. Aqui ficam os campos novos de um
passo de receita, validados à parte; o resto da receita continua passando por fila.validar_receita.
  inicio_q      começa o clipe N quadros adiante (start_frame_offset da seção), 0 a 120
  corte_fim_q   corta N quadros do fim do clipe (end_frame_offset), 0 a 120
  turn_fim_deg  gira a direção DEPOIS do passo (vale para o próximo passo; no último, gira o ator no último quadro)
Sobra do clipe (quadros - inicio_q - corte_fim_q) tem de ser >= 1: corte maior que o clipe é recusado.
Receita sem campo novo tem a MESMA assinatura de antes (os blocos da biblioteca continuam valendo); com campo novo,
a assinatura os inclui (duas receitas diferentes nunca se somam num bloco).
"""
import hashlib
import json

from . import fila as F

LIMITES = {"inicio_q": (0, 120), "corte_fim_q": (0, 120), "turn_fim_deg": (-180.0, 180.0)}
INTEIROS = ("inicio_q", "corte_fim_q")


def tem_extra(receita: dict) -> bool:
    return any(k in p for p in receita.get("passos") or [] if isinstance(p, dict) for k in LIMITES)


def sem_extra(receita: dict) -> dict:
    """A receita como a régua a conhece (sem os campos novos)."""
    passos = [{k: v for k, v in p.items() if k not in LIMITES} if isinstance(p, dict) else p
              for p in receita.get("passos") or []]
    return dict(receita, passos=passos)


def validar(receita: dict, quadros: dict | None = None) -> list:
    """Motivos de recusa (vazio = válida). `quadros` = {clipe: nº de quadros} (ex.: das fichas da biblioteca); clipe
    sem número conhecido só tem os limites conferidos aqui, e o seq_build confere de novo no Unreal."""
    m = F.validar_receita(sem_extra(receita))
    for i, p in enumerate(receita.get("passos") or []):
        if not isinstance(p, dict):
            continue
        for k, (lo, hi) in LIMITES.items():
            if k not in p:
                continue
            v = p[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or (k in INTEIROS and int(v) != v):
                m.append(f"passo {i}: '{k}' tem de ser {'inteiro' if k in INTEIROS else 'número'}")
            elif not lo <= v <= hi:
                m.append(f"passo {i}: '{k}' entre {lo} e {hi}")
        q = (quadros or {}).get(p.get("clipe"))
        sobra = None if q is None else q - int(p.get("inicio_q", 0) or 0) - int(p.get("corte_fim_q", 0) or 0)
        if sobra is not None and sobra < 1:
            m.append(f"passo {i}: {p.get('clipe')} tem {q} quadros; início {p.get('inicio_q', 0)} + corte "
                     f"{p.get('corte_fim_q', 0)} não deixa nenhum quadro")
    return m


def assinatura(receita: dict) -> str:
    if not tem_extra(receita):
        return F.assinatura(receita)  # igual à de antes: os blocos da biblioteca continuam valendo
    s = json.dumps([[p["clipe"], p["papel"], float(p.get("turn_deg", 0)), int(p.get("inicio_q", 0)),
                     int(p.get("corte_fim_q", 0)), float(p.get("turn_fim_deg", 0))] for p in receita["passos"]])
    return hashlib.sha256(s.encode()).hexdigest()[:12]


def passos_para_seq_build(receita: dict, caminho) -> list:
    """Os passos no formato do DirectorTools.seq_build (campos novos só quando presentes)."""
    out = []
    for p in receita["passos"]:
        d = {"anim": caminho(p["clipe"]), "turn_deg": float(p.get("turn_deg", 0))}
        for k in LIMITES:
            if k in p:
                d[k] = p[k]
        out.append(d)
    return out
