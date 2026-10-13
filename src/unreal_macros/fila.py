"""Fila de movimentos (rodada de 07/10): a RÉGUA fixa e as regras da rodada, puras (sem Unreal). O executor
(tools/fila_executor.py) monta, amostra e chama daqui; o Qwen só propõe a receita. Escrito e testado pelo Claude
ANTES da rodada (parecer do Astra, 07/10: a LLM não constrói a régua que julga o próprio trabalho).

Amostras = [(quadro, {osso: [x, y, z]})] em cm no mundo, ordenadas por quadro. Chão = z 0 (piso de teste).
Toda medida é feita só nos quadros amostrados; a resolução está declarada em cada critério."""
import hashlib
import json
import math

PAPEIS = ("levantar", "acenar", "andar", "parar")  # ordem fixa da tarefa; "ponte" pode entrar entre quaisquer passos
OSSOS = ("Hips", "Spine2", "Head", "LeftArm", "RightArm", "LeftForeArm", "RightForeArm", "LeftHand", "RightHand",
         "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg", "LeftFoot", "RightFoot", "LeftToeBase", "RightToeBase")
LIM = {"quadril_cm": 10.0, "osso_cm": 15.0, "virada_deg": 10.0, "sentado_max_cm": 70.0, "de_pe_min_cm": 88.0,
       "mao_acima_cm": 5.0, "aceno_quadros": 15, "aceno_lateral_cm": 10.0, "aceno_inversoes": 2, "aceno_passo_cm": 2.0,
       "andar_cm": 150.0, "pe_apoiado_cm": 3.0, "pe_no_ar_cm": 8.0, "andar_passos_por_pe": 2,
       "parar_quadros": 15, "parar_caminho_cm": 3.0, "dedo_min_cm": -2.0, "dedo_max_cm": 8.0, "duracao_s": 25.0}
PASSO_AMOSTRA = 3  # a cada 3 quadros; nos últimos `parar_quadros` e nas trocas, todo quadro


def hash_regua() -> str:
    """Versão da régua: sha256 deste arquivo (vai em toda linha do registro)."""
    with open(__file__, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def _dif(a: float, b: float) -> float:
    d = (b - a + 180) % 360 - 180
    return 180.0 if d == -180 else d


def ang_quadril(o: dict) -> float:
    """Para onde o quadril olha: linha das coxas girada 90°, graus no mundo."""
    lx, ly = o["RightUpLeg"][0] - o["LeftUpLeg"][0], o["RightUpLeg"][1] - o["LeftUpLeg"][1]
    return math.degrees(math.atan2(-lx, ly))


# ---------- receita ----------
def validar_receita(receita: dict) -> list:
    """Motivos de recusa (vazio = válida). A receita só escolhe clipes, ordem, pontes e giros; não mexe na régua."""
    m = []
    passos = receita.get("passos")
    if not isinstance(passos, list) or not passos:
        return ["receita sem 'passos'"]
    for i, p in enumerate(passos):
        if not isinstance(p, dict):
            m.append(f"passo {i}: falta 'clipe' (nome da biblioteca, ex. Sit_To_Stand)")
            continue
        if not str(p.get("clipe", "")).strip():
            m.append(f"passo {i}: falta 'clipe' (nome da biblioteca, ex. Sit_To_Stand)")
        if p.get("papel") not in PAPEIS + ("ponte",):
            m.append(f"passo {i}: 'papel' tem de ser um de {PAPEIS + ('ponte',)}")
        extra = set(p) - {"clipe", "papel", "turn_deg"}
        if extra:
            m.append(f"passo {i}: campos não aceitos {sorted(extra)} (só clipe, papel, turn_deg)")
        giro = p.get("turn_deg", 0)  # F11: True e NaN passavam (bool é int; abs(nan) > 180 é falso)
        if isinstance(giro, bool) or not isinstance(giro, (int, float)) or not math.isfinite(giro) or abs(giro) > 180:
            m.append(f"passo {i}: turn_deg entre -180 e 180")
    ordem = [PAPEIS.index(p["papel"]) for p in passos if isinstance(p, dict) and p.get("papel") in PAPEIS]
    if ordem != sorted(ordem):
        m.append("ordem das intenções tem de ser levantar → acenar → andar → parar (pontes podem entrar no meio)")
    faltam = [x for x in PAPEIS if x not in {p.get("papel") for p in passos if isinstance(p, dict)}]
    if faltam:
        m.append(f"faltam intenções: {faltam}")
    if passos and isinstance(passos[-1], dict) and passos[-1].get("papel") != "parar":
        m.append("o último passo tem de ser 'parar'")
    if receita.get("tipo") not in ("ajuste", "exploracao"):
        m.append("'tipo' tem de ser 'ajuste' ou 'exploracao'")
    if not str(receita.get("linhagem", "")).strip():
        m.append("falta 'linhagem' (nome curto, ex. A)")
    return m


def assinatura(receita: dict) -> str:
    """Mesma receita = mesma assinatura (para contar repetições 3/3)."""
    s = json.dumps([[p["clipe"], p["papel"], float(p.get("turn_deg", 0))] for p in receita["passos"]])
    return hashlib.sha256(s.encode()).hexdigest()[:12]


# ---------- amostragem ----------
def quadros_a_amostrar(faixas: list) -> list:
    total = faixas[-1]["ate"]
    q = set(range(0, total, PASSO_AMOSTRA)) | set(range(max(0, total - LIM["parar_quadros"]), total))
    for a, b in zip(faixas, faixas[1:]):
        q |= {a["ate"] - 1, b["de"]}
    return sorted(x for x in q if 0 <= x < total)


# ---------- régua ----------
def _faixa_de(q: int, faixas: list) -> int:
    for i, f in enumerate(faixas):
        if f["de"] <= q < f["ate"]:
            return i
    return len(faixas) - 1


def _trocas(am: dict, faixas: list) -> list:
    out = []
    for i, (a, b) in enumerate(zip(faixas, faixas[1:])):
        oa, ob = am.get(a["ate"] - 1), am.get(b["de"])
        if oa is None or ob is None:
            out.append({"troca": i, "valida": False, "motivo": "quadro da troca não amostrado"})
            continue
        saltos = {n: math.dist(oa[n], ob[n]) for n in OSSOS}
        pior = max(saltos, key=lambda k: saltos[k])
        virada = abs(_dif(ang_quadril(oa), ang_quadril(ob)))
        # A13: quem decide se a troca passou são os valores COMPLETOS contra os limites; o arredondamento é só para
        # mostrar (10,004 cm aparece como 10,0, mas está acima de 10).
        excede = [k for k, v in (("quadril_cm", saltos["Hips"]), ("osso_cm", saltos[pior]), ("virada_deg", virada))
                  if v > LIM[k]]
        out.append({"troca": i, "valida": True, "quadros": [a["ate"] - 1, b["de"]],
                    "quadril_cm": round(saltos["Hips"], 2), "pior_osso": pior, "pior_osso_cm": round(saltos[pior], 2),
                    "virada_deg": round(virada, 2), "excede": excede,
                    "ossos_antes": oa, "ossos_depois": ob})
    return out


def _levantar(seq: list) -> dict:
    if not seq:
        return {"passou": False, "motivo": "nenhuma amostra no levantar"}
    z0, zmax = seq[0][1]["Hips"][2], max(o["Hips"][2] for _, o in seq)
    ok = z0 < LIM["sentado_max_cm"] and zmax >= LIM["de_pe_min_cm"]
    return {"passou": ok, "quadril_inicio_cm": round(z0, 1), "quadril_max_cm": round(zmax, 1)}


def _acenar(seq: list) -> dict:
    """Mão acima da cabeça por ≥ 15 quadros (medidos nas amostras: do 1º ao último quadro do trecho) E, nesse trecho,
    a mão vai e volta de lado (no eixo direita do corpo, pelas coxas): amplitude ≥ 10 cm e ≥ 2 inversões de ≥ 2 cm.
    Braço levantado parado NÃO é aceno."""
    diag = {}  # diagnóstico (não muda a nota): quanto a mão chegou acima da cabeça e do ombro, e quanto foi de lado
    for mao, ombro in (("LeftHand", "LeftArm"), ("RightHand", "RightArm")):
        if seq:
            diag[mao] = {"max_acima_cabeca_cm": round(max(o[mao][2] - o["Head"][2] for _, o in seq), 1),
                         "max_acima_ombro_cm": round(max(o[mao][2] - o[ombro][2] for _, o in seq), 1)}
    melhor = {"passou": False, "motivo": "mão nunca acima da cabeça por 15 quadros", "diagnostico": diag}
    for mao in ("LeftHand", "RightHand"):
        trecho = []
        for q, o in seq + [(None, None)]:
            if o is not None and o[mao][2] > o["Head"][2] + LIM["mao_acima_cm"]:
                trecho.append((q, o))
                continue
            if len(trecho) >= 2 and trecho[-1][0] - trecho[0][0] + 1 >= LIM["aceno_quadros"]:
                lat = []
                for _, x in trecho:
                    rx, ry = x["RightUpLeg"][0] - x["LeftUpLeg"][0], x["RightUpLeg"][1] - x["LeftUpLeg"][1]
                    n = math.hypot(rx, ry) or 1.0
                    lat.append(((x[mao][0] - x["Head"][0]) * rx + (x[mao][1] - x["Head"][1]) * ry) / n)
                amp, inv, sentido, ancora = max(lat) - min(lat), 0, 0, lat[0]
                for v in lat[1:]:
                    d = v - ancora
                    if abs(d) >= LIM["aceno_passo_cm"]:
                        s = 1 if d > 0 else -1
                        inv += sentido != 0 and s != sentido
                        sentido, ancora = s, v
                r = {"passou": amp >= LIM["aceno_lateral_cm"] and inv >= LIM["aceno_inversoes"], "mao": mao,
                     "quadros": [trecho[0][0], trecho[-1][0]], "amplitude_lateral_cm": round(amp, 1), "inversoes": inv}
                if r["passou"] or not melhor.get("mao") or amp > melhor.get("amplitude_lateral_cm", 0):
                    melhor = r
                if r["passou"]:
                    return r
            trecho = []
    return melhor


def _andar(seq: list) -> dict:
    """Quadril anda ≥ 150 cm no plano E cada pé sai do chão ≥ 2 vezes (tornozelo de ≤ 3 cm para ≥ 8 cm acima do seu
    mínimo no trecho): deslizar não conta como andar."""
    if len(seq) < 2:
        return {"passou": False, "motivo": "amostras insuficientes no andar"}
    h0, h1 = seq[0][1]["Hips"], seq[-1][1]["Hips"]
    desloc = math.hypot(h1[0] - h0[0], h1[1] - h0[1])
    passos = {}
    for pe in ("LeftFoot", "RightFoot"):
        # A14: o apoio só vale depois de OBSERVADO (uma amostra a ≤ 3 cm). Pé que começa o trecho no ar não conta
        # como "saiu do chão": a saída anterior não está nas amostras.
        zmin, n, apoiado = min(o[pe][2] for _, o in seq), 0, False
        for _, o in seq:
            z = o[pe][2] - zmin
            if z <= LIM["pe_apoiado_cm"]:
                apoiado = True
            elif apoiado and z >= LIM["pe_no_ar_cm"]:
                n, apoiado = n + 1, False
        passos[pe] = n
    ok = desloc >= LIM["andar_cm"] and min(passos.values()) >= LIM["andar_passos_por_pe"]
    return {"passou": ok, "deslocamento_cm": round(desloc, 1), "pe_saiu_do_chao": passos}


def _parar(seq: list, total: int) -> dict:
    """Nos últimos 15 quadros (todos amostrados): caminho TOTAL do quadril (soma dos trechos) < 3 cm e os dois dedos
    entre -2 e 8 cm do chão em todos esses quadros."""
    janela = [(q, o) for q, o in seq if q >= total - LIM["parar_quadros"]]
    if len(janela) < LIM["parar_quadros"]:
        return {"passou": False, "motivo": f"só {len(janela)} de {LIM['parar_quadros']} quadros finais amostrados"}
    caminho = sum(math.dist(a["Hips"], b["Hips"]) for (_, a), (_, b) in zip(janela, janela[1:]))
    dedos = [o[d][2] for _, o in janela for d in ("LeftToeBase", "RightToeBase")]
    ok = caminho < LIM["parar_caminho_cm"] and LIM["dedo_min_cm"] <= min(dedos) and max(dedos) <= LIM["dedo_max_cm"]
    return {"passou": ok, "caminho_quadril_cm": round(caminho, 2), "dedo_min_cm": round(min(dedos), 1),
            "dedo_max_cm": round(max(dedos), 1)}


def _vetor_finito(v) -> bool:
    return (isinstance(v, (list, tuple)) and len(v) == 3
            and all(not isinstance(x, bool) and isinstance(x, (int, float)) and math.isfinite(x) for x in v))


def _acenar_por_trecho(amostras: list, faixas: list, papeis: list) -> dict:
    """A15: o aceno é medido dentro de cada trecho CONTÍNUO de faixas 'acenar'. Faixas de aceno vizinhas formam um
    trecho só; uma ponte (ou outro papel) no meio separa. Antes, as amostras de todos os acenos eram juntadas numa
    lista e o intervalo da ponte, que nem estava nela, contava como continuidade."""
    trechos, atual = [], []
    for i, papel in enumerate(papeis):
        if papel == "acenar":
            atual += [(q, o) for q, o in amostras if _faixa_de(q, faixas) == i]
        elif atual:
            trechos.append(atual)
            atual = []
    if atual:
        trechos.append(atual)
    melhor = None
    for trecho in trechos:
        r = _acenar(trecho)
        if r["passou"]:
            return r
        if melhor is None or r.get("amplitude_lateral_cm", -1) > melhor.get("amplitude_lateral_cm", -1):
            melhor = r
    return melhor or _acenar([])


def avaliar(amostras: list, faixas: list, papeis: list, fps: int) -> dict:
    """Nota (menor é melhor; 0 = passou tudo). Medição incompleta (osso faltando) NÃO vira nota: valida=False."""
    faltando = sorted({(q, n) for q, o in amostras for n in OSSOS if n not in o or o[n] is None})
    if faltando:
        return {"valida": False, "nota": None, "motivo": f"ossos faltando em {len(faltando)} leituras, ex. {faltando[:3]}"}
    # A12: coordenada tem de ser [x, y, z] de números finitos ANTES de qualquer conta (NaN passava por max e dist)
    ruins = sorted({(q, n) for q, o in amostras for n in OSSOS if not _vetor_finito(o[n])})
    if ruins:
        return {"valida": False, "nota": None,
                "motivo": f"coordenadas inválidas (não são [x, y, z] finitos) em {len(ruins)} leituras, ex. {ruins[:3]}"}
    am = dict(amostras)
    trocas = _trocas(am, faixas)
    if any(not t["valida"] for t in trocas):
        return {"valida": False, "nota": None, "motivo": "troca sem amostra", "trocas": trocas}
    por = {p: [(q, o) for q, o in amostras if papeis[_faixa_de(q, faixas)] == p] for p in PAPEIS}
    total = faixas[-1]["ate"]
    intencoes = {"levantar": _levantar(por["levantar"]), "acenar": _acenar_por_trecho(amostras, faixas, papeis),
                 "andar": _andar(por["andar"]), "parar": _parar(amostras, total)}
    duracao = total / fps
    nota = 0.0
    for t in trocas:
        t["nota"] = round(max(0, t["quadril_cm"] - LIM["quadril_cm"]) / LIM["quadril_cm"]
                          + max(0, t["pior_osso_cm"] - LIM["osso_cm"]) / LIM["osso_cm"]
                          + max(0, t["virada_deg"] - LIM["virada_deg"]) / LIM["virada_deg"], 3)
        if t["excede"] and t["nota"] == 0:
            t["nota"] = 0.001  # A13: passou do limite por menos do que o arredondamento mostra; não é nota 0
        nota += t["nota"]
    nota += sum(1 for r in intencoes.values() if not r["passou"]) + (duracao > LIM["duracao_s"])
    return {"valida": True, "nota": round(nota, 3), "trocas": trocas, "intencoes": intencoes,
            "duracao_s": round(duracao, 2), "regua": hash_regua()}


# ---------- regras da rodada (o executor recusa o que as viola) ----------
REGRAS = {"exploracao_min_em_10": 3, "plato_tentativas": 6, "plato_melhora": 0.05, "linhagens_vivas_max": 3,
          "linhagens_total_max": 6, "tentativas_max": 80, "repeticoes_sucesso": 3}


def estado_linhagens(tentativas: list, fechadas: dict) -> dict:
    """De todas as tentativas válidas: campeã, platô e regra de dois por linhagem."""
    lin = {}
    for t in tentativas:
        L = lin.setdefault(t["linhagem"], {"campea_n": None, "campea_nota": None, "sem_melhora": 0, "classes": [],
                                          "tentativas": 0, "fechada": t["linhagem"] in fechadas,
                                          "motivo_fechada": fechadas.get(t["linhagem"]), "_ref": None})
        L["tentativas"] += 1
        nota = t.get("nota")
        if nota is None:
            continue  # sem nota (infraestrutura, dependência, medição): não conta para platô nem regra de dois
        L["classes"].append((tuple(t.get("falhas") or [t.get("classe_erro")]), nota))
        if L["campea_nota"] is None or nota < L["campea_nota"]:
            L["campea_n"], L["campea_nota"] = t["n"], nota  # campeã = menor nota
        # platô: só uma melhora de >= 5% sobre a referência zera o contador
        if L["_ref"] is None or nota <= L["_ref"] * (1 - REGRAS["plato_melhora"]):
            L["_ref"], L["sem_melhora"] = nota, 0
        else:
            L["sem_melhora"] += 1
    for L in lin.values():
        L["plato"] = L["sem_melhora"] >= REGRAS["plato_tentativas"]
        c = L["classes"]  # regra de dois: os MESMOS critérios falhando 2 vezes seguidas, sem a nota melhorar
        L["regra_de_dois"] = len(c) >= 2 and c[-1][0] == c[-2][0] and c[-1][1] >= c[-2][1] and c[-1][1] > 0
        del L["classes"], L["_ref"]
    return lin


def checar_regras(receita: dict, tentativas: list, fechadas: dict) -> list:
    """Motivos para recusar a tentativa nova pelas regras da rodada (vazio = pode)."""
    m = []
    if len(tentativas) >= REGRAS["tentativas_max"]:
        m.append(f"limite de {REGRAS['tentativas_max']} tentativas atingido: escreva o FECHAMENTO")
    lin = estado_linhagens(tentativas, fechadas)
    nome = receita.get("linhagem")
    if nome in fechadas:
        m.append(f"linhagem {nome} está fechada ({fechadas[nome]}): use outra")
    L = lin.get(nome)
    if L and L["plato"] and nome not in fechadas:
        m.append(f"linhagem {nome} em platô ({L['sem_melhora']} tentativas sem melhorar 5%): feche-a com "
                 "fechar-linhagem e abra outra a partir de um ponto diferente")
    if L and L["regra_de_dois"] and receita.get("tipo") != "exploracao":
        m.append(f"regra de dois: a linhagem {nome} teve a mesma classe de erro 2 vezes seguidas; a próxima tem de ser "
                 "'exploracao'")
    vivas = {n for n, x in lin.items() if n not in fechadas}
    if nome not in lin and len(vivas) >= REGRAS["linhagens_vivas_max"]:
        m.append(f"já há {len(vivas)} linhagens vivas (máx. {REGRAS['linhagens_vivas_max']}): feche uma antes de abrir {nome}")
    if nome not in lin and len(lin) >= REGRAS["linhagens_total_max"]:
        m.append(f"já houve {len(lin)} linhagens (máx. {REGRAS['linhagens_total_max']}): escreva o FECHAMENTO")
    # A16: a quota é a mesma (3 explorações em cada 10). A obrigação é ANTECIPADA quando as vagas que sobram na
    # janela já não bastam para completá-la (antes só se conferia na 10ª, e nove ajustes seguidos deixavam a rodada
    # sem nenhuma próxima tentativa válida). Uma exploração nunca é recusada por esta regra: é ela que repara a janela.
    ult = tentativas[-9:]
    vagas_depois = 9 - len(ult)  # tentativas que ainda cabem na janela de 10 depois desta
    if receita.get("tipo") != "exploracao" and \
            sum(t.get("tipo") == "exploracao" for t in ult) + vagas_depois < REGRAS["exploracao_min_em_10"]:
        m.append(f"menos de {REGRAS['exploracao_min_em_10']} explorações nas últimas 10: esta tem de ser 'exploracao'")
    return m


def elegivel(t: dict) -> bool:
    """A tentativa conta como repetição de sucesso? Medida com nota 0 (número, não booleano) E nada que negue a
    aprovação: avaliação inválida, cena não restaurada (cena_ok False) ou tentativa não aprovada (passou False: houve
    falha depois da medida). Campo ausente não nega: registros antigos não tinham esses campos."""
    nota = t.get("nota")
    return (type(nota) in (int, float) and nota == 0 and t.get("passou") is not False
            and t.get("cena_ok") is not False and (t.get("avaliacao") or {}).get("valida") is not False)


def sucesso(tentativas: list) -> dict | None:
    """Conseguiu = a mesma receita (assinatura) com nota 0 em 3 tentativas válidas: DISTINTAS (a mesma linha repetida
    não vale três), elegíveis (ver elegivel) e medidas nas MESMAS condições, fps e versões. O mesmo número de
    tentativa com conteúdos diferentes invalida a apuração daquela receita. É a única definição de sucesso: executor,
    campanha, biblioteca, painel e rotina chamam esta função."""
    grupos = {}
    for i, t in enumerate(tentativas):
        if not elegivel(t):
            continue
        chave = (t["assinatura"], json.dumps([t.get("condicoes"), t.get("fps"), t.get("versoes")], sort_keys=True, default=str))
        quem = (t.get("n"), t.get("execucao")) if t.get("n") is not None else ("sem número", i)
        grupos.setdefault(chave, {}).setdefault(quem, []).append(t)
    for (a, _), g in grupos.items():
        if any(x != v[0] for v in g.values() for x in v[1:]):
            continue  # duplicata conflitante: não dá para saber qual é a medida
        if len(g) >= REGRAS["repeticoes_sucesso"]:
            return {"assinatura": a, "vezes": len(g)}
    return None
