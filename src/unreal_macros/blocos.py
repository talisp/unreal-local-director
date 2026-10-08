"""v0.0.3 — a "fila de movimentos prontos": receitas de passos verificados que o LLM escolhe e encaixa, em vez de
inventar movimento. Cada receita devolve passos para DirectorTools.seq_build e o efeito previsto (avanço), calculado
com os dados MEDIDOS dos clipes (DirectorTools.clip_info), nunca com números chutados.

Puro (sem Unreal): `info` é um dicionário {clipe: clip_info}. Ver docs/MAPA_LACUNAS_V.md."""

import math

PASTA = "/Game/_AnimLab/Mixamo"


def _recusa(bloco: str, motivos: list, **extra) -> dict:
    return {"bloco": bloco, "recusa": motivos, "passos": [], "avanco_cm": 0.0, **extra}


def caminho(clipe: str) -> str:
    return f"{PASTA}/{clipe}_Anim.{clipe}_Anim"


def andar(distancia_cm: float, info: dict) -> dict:
    """Começar a andar → andar × k → parar, com k escolhido para chegar mais perto da distância pedida.
    A distância é quantizada pelo ciclo de caminhada: o erro previsto volta em `erro_cm` (o chamador decide).
    Zero, negativo, NaN ou infinito: recusa com o motivo (achados K2–K4 da bateria, 08/10)."""
    if not math.isfinite(distancia_cm) or distancia_cm <= 0:
        return _recusa("andar", [f"distância {distancia_cm} cm: precisa ser um número finito maior que zero"])
    ini, ciclo, fim = (info[c]["avanco_cm"] for c in ("Start_Walking", "Walking", "Stop_Walking"))
    k = max(0, round((distancia_cm - ini - fim) / ciclo))
    previsto = ini + k * ciclo + fim
    passos = [{"anim": caminho("Start_Walking")}] + [{"anim": caminho("Walking")}] * k + [{"anim": caminho("Stop_Walking")}]
    return {"bloco": "andar", "passos": passos, "avanco_cm": round(previsto, 1),
            "erro_cm": round(previsto - distancia_cm, 1), "ciclos": k}


def levantar(info: dict) -> dict:
    """Sentado → de pé. Começa com o quadril na altura de sentar; termina de pé, mais à frente."""
    return {"bloco": "levantar", "passos": [{"anim": caminho("Sit_To_Stand")}],
            "avanco_cm": round(info["Sit_To_Stand"]["avanco_cm"], 1), "erro_cm": 0.0}


def compor(*blocos: dict) -> dict:
    """Encadeia blocos na ordem; o avanço previsto é a soma. Uma parte recusada recusa o todo, com os motivos."""
    recusas = [m for b in blocos for m in b.get("recusa", [])]
    if recusas:
        return _recusa("+".join(b["bloco"] for b in blocos), recusas, partes=[b["bloco"] for b in blocos])
    passos = [p for b in blocos for p in b["passos"]]
    return {"bloco": "+".join(b["bloco"] for b in blocos), "passos": passos,
            "avanco_cm": round(sum(b["avanco_cm"] for b in blocos), 1), "partes": [b["bloco"] for b in blocos]}


CLIPES_NECESSARIOS = {"andar": ("Start_Walking", "Walking", "Stop_Walking"), "levantar": ("Sit_To_Stand",)}


def angulos_porta(quadros_ossos: list, dobradica: tuple, frente: tuple, folha_dir: tuple, largura: float = 100.0,
                  folga_graus: float = 4.0) -> dict:
    """Porta "empurrada pelo corpo": em cada quadro, o menor ângulo de abertura para nenhum osso atravessar a folha;
    a porta nunca volta (máximo acumulado). Puro: quadros_ossos = [(quadro, {osso: [x, y, z]})].
    dobradica = (x, y) no plano da porta; frente = sentido em que ela abre; folha_dir = direção da folha fechada
    (da dobradiça para a ponta livre). Devolve [(quadro, graus)] e o osso que empurrou primeiro."""
    hx, hy = dobradica
    angulo, saida, primeiro = 0.0, [], None
    for q, ossos in quadros_ossos:
        precisa = 0.0
        quem = None
        for nome, (x, y, _z) in ossos.items():
            vx, vy = x - hx, y - hy
            s = vx * frente[0] + vy * frente[1]          # quanto já passou do plano da porta
            l = vx * folha_dir[0] + vy * folha_dir[1]    # posição ao longo da folha fechada
            if s > 0 and 0 < l and math.hypot(s, l) <= largura:
                a = math.degrees(math.atan2(s, l)) + folga_graus
                if a > precisa:
                    precisa, quem = a, nome
        if precisa > angulo:
            if primeiro is None and precisa > folga_graus + 1:
                primeiro = {"quadro": q, "osso": quem}
            angulo = min(precisa, 100.0)
        saida.append((q, round(angulo, 2)))
    return {"angulos": saida, "primeiro_toque": primeiro, "final_graus": round(angulo, 2)}


def folha_em(dobradica: tuple, folha_dir: tuple, frente: tuple, graus: float, largura: float = 100.0) -> tuple:
    """Centro (x, y) e direção da folha aberta em `graus` (gira de folha_dir para frente)."""
    t = math.radians(graus)
    dx = folha_dir[0] * math.cos(t) + frente[0] * math.sin(t)
    dy = folha_dir[1] * math.cos(t) + frente[1] * math.sin(t)
    return (dobradica[0] + dx * largura / 2, dobradica[1] + dy * largura / 2), (dx, dy)


# Pré-condições MEDIDAS no Unreal (V03, 06/10): fora delas o clipe atravessa a parede. O bloco recusa com o motivo,
# em vez de gerar uma cena errada; o LLM escolhe outra porta, outro bloco, ou escala a lacuna.
PRECONDICOES = {
    "abrir_porta_empurrando": {"clipe": "Open_Door_Outwards", "vao_min_cm": 150, "dobradica": "esquerda",
                               "abre": "para longe de quem empurra",
                               "evidencia": "V03: vão 100/120 cm -> braço esquerdo 10-15 cm dentro do batente"},
}


def abrir_porta(info: dict, vao_cm: float, dobradica: str) -> dict:
    """Empurrar a porta e passar. `dobradica` relativa a quem empurra ('esquerda'/'direita')."""
    pc = PRECONDICOES["abrir_porta_empurrando"]
    motivos = []
    if not math.isfinite(vao_cm):  # NaN < 150 é falso e inf >= 150: passavam (K1, bateria 08/10)
        motivos.append(f"vão {vao_cm} cm não é um número finito")
    elif vao_cm < pc["vao_min_cm"]:
        motivos.append(f"vão {vao_cm:.0f} cm < {pc['vao_min_cm']} cm exigidos pelo clipe")
    if dobradica != pc["dobradica"]:
        motivos.append(f"dobradiça à {dobradica}; o clipe empurra com a direita e segura com a esquerda")
    if motivos:
        return _recusa("abrir_porta", motivos)
    return {"bloco": "abrir_porta", "passos": [{"anim": caminho(pc["clipe"])}],
            "avanco_cm": round(info[pc["clipe"]]["avanco_cm"], 1), "erro_cm": 0.0}
