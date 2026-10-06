"""Gates numéricos: cada um devolve {nome, resultado PASS|FAIL|NOT_EVALUATED, valor, limite}."""


def g(nome: str, passou, valor, limite) -> dict:
    res = "NOT_EVALUATED" if passou is None else ("PASS" if passou else "FAIL")
    return {"nome": nome, "resultado": res, "valor": valor, "limite": limite}


def pes_no_chao(m: dict, tol: float = 3.0) -> dict:
    gap = m.get("gap_chao")
    return g("pes_no_chao", None if gap is None else abs(gap) <= tol, gap, f"|gap| <= {tol} cm")


def nao_deitado(m: dict) -> dict:
    return g("nao_deitado", not m.get("deitado"), {"altura": m.get("altura"), "largura": m.get("largura_max")},
             "altura >= 110 ou largura <= 120")


def sem_sobreposicao(m: dict) -> dict:
    sob = m.get("sobreposicoes")
    return g("sem_sobreposicao", None if sob is None else len(sob) == 0, sob, "nenhuma caixa de outro personagem invadida > 2 cm")


def ator_parado(antes: dict, depois: dict, tol: float = 0.5, ajuste_z: float = 0.0, ajuste_roll: float = 0.0) -> dict:
    """O ator não pode ter saído do lugar que o operador definiu (política, regra 7). Só se aceita o ajuste
    vertical que a própria macro mediu e declarou (compensação da raiz do clipe)."""
    dz = depois["location"]["z"] - antes["location"]["z"]
    dl = max([abs(antes["location"][k] - depois["location"][k]) for k in "xy"] + [abs(dz - ajuste_z) if abs(dz) > tol else 0.0])
    dr_roll = depois["rotation"]["roll"] - antes["rotation"]["roll"]
    dr = max([abs(antes["rotation"][k] - depois["rotation"][k]) for k in ("pitch", "yaw")] +
             [abs(dr_roll - ajuste_roll) if abs(dr_roll) > tol else 0.0])
    return g("ator_parado", dl <= tol and dr <= tol, {"desloc_cm": round(dl, 2), "rot_graus": round(dr, 2), "ajuste_z_declarado": round(ajuste_z, 1)}, f"<= {tol}")


def deriva_xy(amostras: list, tol: float = 15.0) -> dict:
    """Num loop, o centro do corpo não pode passear (ex.: clipes que andam ou giram)."""
    if len(amostras) < 2:
        return g("deriva_xy", None, None, f"<= {tol} cm")
    xs = [a[0] for a in amostras]
    ys = [a[1] for a in amostras]
    d = max(max(xs) - min(xs), max(ys) - min(ys))
    return g("deriva_xy", d <= tol, round(d, 1), f"<= {tol} cm")


def silhueta_de_pe(s: dict, altura=(160, 210)) -> dict:  # 06/10: 150 aceitava ajoelhado ereto (156,9)
    """Pose de pé medida pela silhueta na imagem (altura estimada em cm e não deitado)."""
    if not s.get("medido"):
        return g("silhueta_de_pe", None, s.get("pixels"), "silhueta mensurável")
    ok = altura[0] <= s["altura_cm"] <= altura[1] and not s["deitado"]
    return g("silhueta_de_pe", ok, {"altura_cm": s["altura_cm"], "largura_cm": s["largura_cm"]},
             f"altura {altura[0]}-{altura[1]} cm, não deitado")


def pes_plantados(amostras: list, iou_min: float = 0.55) -> dict:  # calibrado 05/10: Walking 0.00, conversas 0.69-0.82
    """Plateia/conversa: as pernas quase não mudam entre instantes do loop. IoU mínimo da região das pernas
    (abaixo de 80 cm) entre a 1a amostra e as demais. Caminhar no lugar derruba o IoU."""
    import numpy as np
    ms = [s.get("_pernas") for s in amostras if s.get("_pernas") is not None]
    if len(ms) < 2:
        return g("pes_plantados", None, None, f"IoU >= {iou_min}")
    h = min(m.shape[0] for m in ms)
    base = ms[0][:h]
    ious = []
    for m in ms[1:]:
        m = m[:h]
        uni = np.logical_or(base, m).sum()
        ious.append(float(np.logical_and(base, m).sum() / uni) if uni else 1.0)
    v = round(min(ious), 3)
    return g("pes_plantados", v >= iou_min, v, f"IoU pernas >= {iou_min}")


def pose_em_todo_clipe(amostras: list, altura=(160, 210), contato_cm: float = 10.0) -> dict:
    """A pose de pé vale no clipe INTEIRO (4 instantes), não num quadro sorteado: queda, ajoelhar ou sentar no meio
    do clipe reprovam (06/10, bancada do Hermes: 'roleta de quadro')."""
    if not amostras or any(not s.get("medido") for s in amostras):  # vazio NÃO é PASS (Astra: all([]) = True)
        return g("pose_em_todo_clipe", None, [s.get("motivo") for s in amostras], "todos os instantes mensuráveis")
    alt = [s["altura_cm"] for s in amostras]
    gap = [s["gap_pes_cm"] for s in amostras]
    ok = all(altura[0] <= h <= altura[1] for h in alt) and not any(s["deitado"] for s in amostras) \
        and all(abs(x) <= contato_cm for x in gap)
    return g("pose_em_todo_clipe", ok, {"altura_cm": alt, "gap_pes_cm": gap},
             f"altura {altura[0]}-{altura[1]} cm e pés a <= {contato_cm} cm do piso em todos os instantes")
