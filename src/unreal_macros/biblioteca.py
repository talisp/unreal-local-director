"""Biblioteca de blocos (Fase 3 do PLANO_PROXIMA_VERSAO; o B1 da D21): o que já foi MEDIDO, com as condições em que
vale. Puro (sem Unreal).

Fonte da verdade: `biblioteca/*.jsonl` no git, uma linha por registro, com `id` único (gravação ordenada, para o diff
ficar legível). Três tipos:
  blocos  receita que deu nota 0 três vezes com a mesma assinatura e a mesma régua; quem grava é o executor (ou a
          importação de uma rodada antiga), nunca a LLM;
  trocas  fim do clipe A -> início do clipe B: ossos antes e depois, giro, custo por critério, papéis e condições;
  fichas  um clipe: quadros, avanço, papéis em que passou ou reprovou, trocas em que entrou.
Uma medida só vale nas condições em que foi feita (personagem, escala, FPS, root motion, passo da amostragem, régua):
fora delas, a resposta é "medir de novo".
"""
import json
import math
import os
import shutil
import statistics

from . import fila as F

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PASTA = os.path.join(RAIZ, "biblioteca")
TIPOS = ("blocos", "trocas", "fichas", "escolhas")  # escolhas: a variação que o operador escolheu (Fase 8)

# Condições da medida. Obrigatórias: diferente = "medir de novo". Informativas: diferente = só aviso (o executor e o
# toolset mudam por motivos que não alteram a medida; a régua muda o que é medido e por isso é obrigatória).
OBRIGATORIAS = ("personagem", "escala", "fps", "root_motion", "passo_amostragem", "regua")
INFORMATIVAS = ("executor", "toolset")
AJUSTES_TROCA = ("corte_fim_a", "turn_fim_a", "inicio_b")  # Fase 4: mudam a troca; zero = como antes
PERSONAGEM_FILA = "/Game/Characters/SK_YBot.SK_YBot"  # TC.boneco usa M.MALHA_YBOT, sem mudar a escala
ROOT_MOTION_FILA = "padrao_importar_clipe"  # como macros.importar_clipe deixa o clipe (não é ajustado pelo executor)


# ---------- leitura e gravação ----------
def ler_jsonl(caminho: str) -> tuple:
    """(registros, cortadas). Linha que não é JSON de objeto (queda no meio da gravação) é ignorada e contada."""
    regs, cortadas = [], 0
    if not os.path.exists(caminho):
        return regs, 0
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            if not linha.strip():
                continue
            try:
                r = json.loads(linha)
            except ValueError:
                cortadas += 1
                continue
            if isinstance(r, dict):
                regs.append(r)
            else:
                cortadas += 1
    return regs, cortadas


def gravar_jsonl(caminho: str, registros) -> None:
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for r in sorted(registros, key=lambda r: r["id"]):
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, caminho)  # quem lê nunca vê o arquivo pela metade


def carregar(pasta: str = PASTA) -> dict:
    """{tipo: {id: registro}} e {'cortadas': {tipo: n}}."""
    out, cortadas = {}, {}
    for tipo in TIPOS:
        regs, cortadas[tipo] = ler_jsonl(os.path.join(pasta, f"{tipo}.jsonl"))
        out[tipo] = {r["id"]: r for r in regs if "id" in r}
    out["cortadas"] = cortadas
    return out


def mesclar(pasta: str, novos: dict) -> dict:
    """Junta registros novos aos da pasta, pelo `id` (o mesmo id substitui: importar duas vezes não duplica)."""
    atual = carregar(pasta)
    contagem = {}
    for tipo in TIPOS:
        reg = atual[tipo]
        for r in novos.get(tipo, []):
            reg[r["id"]] = r
        gravar_jsonl(os.path.join(pasta, f"{tipo}.jsonl"), reg.values())
        contagem[tipo] = len(reg)
    for destino, origem in (novos.get("arquivos") or {}).items():  # amostras dos blocos
        alvo = os.path.join(pasta, destino)
        os.makedirs(os.path.dirname(alvo), exist_ok=True)
        shutil.copyfile(origem, alvo)
    return contagem


# ---------- condições ----------
def condicoes_fila(versoes: dict, fps: int, gravadas: dict | None = None) -> dict:
    """Condições de uma medida do executor da fila. `gravadas` = o que o executor gravou (desde a Fase 3: personagem,
    escala, root motion); sem isso (rodada de 07/10), esses campos saem do código do executor, marcados "deduzido"."""
    g = gravadas or {}
    def o(k, deduzido):
        return "gravado pelo executor" if k in g else deduzido
    return {"personagem": g.get("personagem", PERSONAGEM_FILA), "escala": g.get("escala", 1.0), "fps": fps,
            "root_motion": g.get("root_motion", ROOT_MOTION_FILA), "passo_amostragem": F.PASSO_AMOSTRA,
            "regua": versoes.get("regua"), "executor": versoes.get("executor"), "toolset": versoes.get("toolset"),
            "origem": {"personagem": o("personagem", "deduzido do executor (TC.boneco com MALHA_YBOT)"),
                       "escala": o("escala", "deduzido do executor (o boneco não muda a escala)"),
                       "root_motion": o("root_motion", "deduzido (padrão da importação; o executor não ajusta)"),
                       "passo_amostragem": "régua (fila.PASSO_AMOSTRA)", "fps": "gravado", "regua": "gravado",
                       "executor": "gravado", "toolset": "gravado"}}


def _chave_condicoes(c: dict) -> str:
    return json.dumps([c.get(k) for k in OBRIGATORIAS])


# ---------- importação de uma rodada da fila ----------
def importar_rodada(pasta_rodada: str, fonte: str) -> dict:
    """Lê tentativas.jsonl e encaixes.jsonl de uma rodada da fila e devolve {blocos, trocas, fichas, cortadas}."""
    linhas, cort_t = ler_jsonl(os.path.join(pasta_rodada, "tentativas.jsonl"))
    encaixes, cort_e = ler_jsonl(os.path.join(pasta_rodada, "encaixes.jsonl"))
    tent = {t["n"]: t for t in linhas if t.get("tipo_linha") == "tentativa" and "n" in t}
    trocas = []
    for e in encaixes:
        t = tent.get(e.get("n"))
        if t is None or e.get("valida") is False:
            continue
        passos, i = t["receita"], e["troca"]
        papel_a = passos[i]["papel"] if i < len(passos) and passos[i]["clipe"] == e["clipe_a"] else None
        papel_b = passos[i + 1]["papel"] if i + 1 < len(passos) and passos[i + 1]["clipe"] == e["clipe_b"] else None
        trocas.append({
            "id": f"{fonte}:t{t['n']:03d}:x{i}", "fonte": fonte, "tentativa": t["n"], "troca": i,
            "clipe_a": e["clipe_a"], "clipe_b": e["clipe_b"], "papel_a": papel_a, "papel_b": papel_b,
            "asset_a": e.get("asset_a"), "asset_b": e.get("asset_b"), "turn_deg_b": e.get("turn_deg_b", 0),
            "quadros": e.get("quadros"), "frente": e.get("frente"), "chao_z": e.get("chao_z"),
            "ossos_antes": e["ossos_antes"], "ossos_depois": e["ossos_depois"],
            "medida": {k: e.get(k) for k in ("quadril_cm", "pior_osso", "pior_osso_cm", "virada_deg", "nota")},
            "condicoes": condicoes_fila(e.get("versoes") or t.get("versoes") or {}, e.get("fps") or t.get("fps"),
                                        e.get("condicoes") or t.get("condicoes")),
            "quando": e.get("quando"), **{k: e[k] for k in AJUSTES_TROCA if e.get(k)}})
    blocos, arquivos = _blocos(tent, trocas, fonte, pasta_rodada)
    fichas = _fichas(tent, trocas)
    return {"blocos": blocos, "trocas": trocas, "fichas": fichas, "arquivos": arquivos, "cortadas": cort_t + cort_e}


def _blocos(tent: dict, trocas: list, fonte: str, pasta_rodada: str) -> tuple:
    """Bloco = mesma assinatura com nota 0 em `repeticoes_sucesso` tentativas válidas, nas MESMAS condições
    obrigatórias (régua, personagem, escala...). Devolve (blocos, arquivos de amostras a copiar)."""
    grupos = {}
    for t in tent.values():
        if t.get("nota") == 0 and (t.get("avaliacao") or {}).get("valida"):
            c = condicoes_fila(t.get("versoes") or {}, t.get("fps"), t.get("condicoes"))
            grupos.setdefault((t["assinatura"], _chave_condicoes(c)), []).append(t)
    out, arquivos = [], {}
    for (assin, _cond), ts in sorted(grupos.items()):
        if len(ts) < F.REGRAS["repeticoes_sucesso"]:
            continue
        ts = sorted(ts, key=lambda t: t["n"])
        ns = [t["n"] for t in ts]
        videos = [f"work/{os.path.basename(pasta_rodada)}/videos/t{n:03d}.mp4" for n in ns
                  if os.path.exists(os.path.join(pasta_rodada, "videos", f"t{n:03d}.mp4"))]
        amostras = []
        for n in ns:  # gravadas pelo executor desde a Fase 3 (a rodada de 07/10 não as tem)
            origem = os.path.join(pasta_rodada, "amostras", f"t{n:03d}.json")
            if os.path.exists(origem):
                destino = f"amostras/{assin}-t{n:03d}.json"
                arquivos[destino] = origem
                amostras.append(destino)
        out.append({
            "id": assin, "fonte": fonte, "receita": ts[0]["receita"], "tentativas": ns, "amostras": amostras,
            "faixas": {str(t["n"]): (t.get("montagem") or {}).get("faixas") for t in ts},
            "notas": [t["nota"] for t in ts], "intencoes": {str(t["n"]): t["avaliacao"]["intencoes"] for t in ts},
            "duracao_s": [t["avaliacao"].get("duracao_s") for t in ts],
            "trocas": [x["id"] for x in trocas if x["tentativa"] in ns],
            "condicoes": condicoes_fila(ts[0].get("versoes") or {}, ts[0].get("fps"), ts[0].get("condicoes")),
            "videos": videos, "quando": ts[-1].get("quando")})
    return out, arquivos


def _fichas(tent: dict, trocas: list) -> list:
    fichas = {}
    for t in sorted(tent.values(), key=lambda t: t["n"]):
        aval = t.get("avaliacao") or {}
        faixas = {f["clipe"]: f for f in (t.get("montagem") or {}).get("faixas", [])}
        for p in t["receita"]:
            c = p["clipe"]
            fi = fichas.setdefault(c, {"id": c, "clipe": c, "quadros": None, "avanco_cm": None, "papeis": {},
                                       "trocas": {"como_a": 0, "como_b": 0}, "aceno": None})
            f = faixas.get(f"{c}_Anim")
            if f and fi["quadros"] is None and not (f.get("inicio_q") or f.get("corte_fim_q")):
                fi["quadros"], fi["avanco_cm"] = f["ate"] - f["de"], f.get("avanco_cm")  # só do clipe inteiro
            if not aval.get("valida") or p["papel"] not in F.PAPEIS:
                continue
            r = aval["intencoes"].get(p["papel"]) or {}
            cont = fi["papeis"].setdefault(p["papel"], {"passou": 0, "reprovou": 0, "tentativas": []})
            cont["passou" if r.get("passou") else "reprovou"] += 1
            cont["tentativas"].append(t["n"])
            if p["papel"] == "acenar" and "amplitude_lateral_cm" in r:
                melhor = fi["aceno"] or {}
                if r["amplitude_lateral_cm"] > melhor.get("amplitude_lateral_cm", -1):
                    fi["aceno"] = {k: r.get(k) for k in ("passou", "mao", "amplitude_lateral_cm", "inversoes")}
    for x in trocas:
        for lado, chave in (("clipe_a", "como_a"), ("clipe_b", "como_b")):
            if x[lado] in fichas:
                fichas[x[lado]]["trocas"][chave] += 1
    return list(fichas.values())


# ---------- recálculo com a régua (B2) ----------
# A fórmula da troca é a de fila.avaliar, COPIADA de propósito: mudar fila.py muda o hash da régua e marcaria toda
# medida antiga como "régua diferente". testes_biblioteca prova que a cópia dá os mesmos números nas 138 trocas.
def medir_troca(antes: dict, depois: dict, lim: dict | None = None) -> dict:
    lim = lim or F.LIM
    saltos = {n: math.dist(antes[n], depois[n]) for n in F.OSSOS}
    pior = max(saltos, key=lambda k: saltos[k])
    q, p = round(saltos["Hips"], 2), round(saltos[pior], 2)
    v = round(abs(F._dif(F.ang_quadril(antes), F.ang_quadril(depois))), 2)
    nota = round(max(0, q - lim["quadril_cm"]) / lim["quadril_cm"] + max(0, p - lim["osso_cm"]) / lim["osso_cm"]
                 + max(0, v - lim["virada_deg"]) / lim["virada_deg"], 3)
    return {"quadril_cm": q, "pior_osso": pior, "pior_osso_cm": p, "virada_deg": v, "nota": nota}


def recalcular_bloco(bloco: dict, trocas: dict, lim: dict | None = None, regua: str | None = None) -> dict:
    """Nota de cada tentativa do bloco com a régua de agora: trocas RECALCULADAS dos ossos gravados; intenções e
    duração vêm do que foi gravado (a série de quadros não foi guardada em 07/10). Régua diferente da do bloco fica
    marcada: a parte das intenções precisa ser medida de novo."""
    lim, regua = lim or F.LIM, regua or F.hash_regua()
    por_tent = {}
    for tid in bloco["trocas"]:
        t = trocas[tid]
        por_tent.setdefault(t["tentativa"], []).append(medir_troca(t["ossos_antes"], t["ossos_depois"], lim))
    notas = {}
    for i, n in enumerate(bloco["tentativas"]):
        intencoes = bloco["intencoes"][str(n)]
        dur = bloco["duracao_s"][i]
        nota = sum(x["nota"] for x in por_tent.get(n, [])) + sum(1 for r in intencoes.values() if not r.get("passou"))
        nota += dur is not None and dur > lim["duracao_s"]
        notas[n] = round(nota, 3)
    diferente = bloco["condicoes"].get("regua") != regua
    return {"notas": notas, "trocas": por_tent, "regua_do_bloco": bloco["condicoes"].get("regua"), "regua_agora": regua,
            "regua_diferente": diferente,
            "intencoes": "gravadas; régua diferente: medir de novo" if diferente else "gravadas (mesma régua)"}


def recalcular_bloco_completo(bloco: dict, pasta: str = PASTA) -> dict:
    """Régua de AGORA inteira (fila.avaliar: trocas, intenções e duração) sobre as amostras gravadas do bloco.
    Só para blocos gravados pelo executor desde a Fase 3; sem amostras, devolve 'sem_amostras'."""
    if not bloco.get("amostras"):
        return {"status": "sem_amostras", "motivo": "bloco anterior à Fase 3: só as trocas são recalculáveis"}
    papeis = [p["papel"] for p in bloco["receita"]]
    notas = {}
    for rel in bloco["amostras"]:
        n = int(rel.rsplit("-t", 1)[1].split(".")[0])
        amostras = [(q, ossos) for q, ossos in json.load(open(os.path.join(pasta, rel), encoding="utf-8"))]
        av = F.avaliar(amostras, bloco["faixas"][str(n)], papeis, bloco["condicoes"]["fps"])
        notas[n] = av.get("nota") if av.get("valida") else None
    return {"status": "ok", "notas": notas, "regua": F.hash_regua(),
            "regua_diferente": bloco["condicoes"].get("regua") != F.hash_regua()}


def consistencia_trocas(trocas) -> dict:
    """Hipótese: a mesma troca (clipe_a -> clipe_b com o mesmo giro) dá o mesmo custo em receitas diferentes?
    Devolve, por grupo com 2+ medidas, a variação (máx - mín) de cada critério, e o resumo."""
    grupos = {}
    for t in trocas:
        grupos.setdefault((t["clipe_a"], t["clipe_b"], float(t.get("turn_deg_b") or 0))
                          + tuple(t.get(k, 0) for k in AJUSTES_TROCA), []).append(t["medida"])
    detalhe = []
    for (a, b, g, *aj), ms in sorted(grupos.items()):
        if len(ms) < 2:
            continue
        var = {k: round(max(m[k] for m in ms) - min(m[k] for m in ms), 2)
               for k in ("quadril_cm", "pior_osso_cm", "virada_deg", "nota")}
        detalhe.append({"clipe_a": a, "clipe_b": b, "giro": g, "medidas": len(ms), "variacao": var,
                        **{k: v for k, v in zip(AJUSTES_TROCA, aj) if v}})
    resumo: dict = {"grupos_com_repeticao": len(detalhe), "trocas_nesses_grupos": sum(d["medidas"] for d in detalhe)}
    for k in ("quadril_cm", "pior_osso_cm", "virada_deg", "nota"):
        vs = [d["variacao"][k] for d in detalhe]
        resumo[k] = {"variacao_max": max(vs) if vs else None,
                     "variacao_mediana": round(statistics.median(vs), 2) if vs else None}
    return {"resumo": resumo, "grupos": detalhe}


# ---------- condições e consulta (B3) ----------
FRASE_VALIDO = "validado nestas condições; fora delas, meça de novo"


def _sha16(caminho: str) -> str | None:
    import hashlib
    try:
        with open(caminho, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except OSError:
        return None


def condicoes_atuais(fps: int = 30) -> dict:
    """As condições em que o executor da fila mediria AGORA (mesmos hashes que fila_executor.versoes())."""
    versoes = {"regua": F.hash_regua(), "executor": _sha16(os.path.join(RAIZ, "tools", "fila_executor.py")),
               "toolset": _sha16(os.path.join(RAIZ, "editor_python", "director_tools", "toolset.py"))}
    c = condicoes_fila(versoes, fps)
    c.pop("origem")
    return c


def comparar_condicoes(gravadas: dict, pedidas: dict) -> tuple:
    """(motivos, avisos). Motivo = condição obrigatória diferente ou não informada -> medir de novo."""
    motivos, avisos = [], []
    for k in OBRIGATORIAS:
        if k not in pedidas or pedidas[k] is None:
            motivos.append(f"{k}: não informado no pedido; sem ele não dá para garantir a medida")
            continue
        g, p = gravadas.get(k), pedidas[k]
        igual = abs(float(g) - float(p)) < 1e-6 if isinstance(g, (int, float)) and isinstance(p, (int, float)) else g == p
        if not igual:
            motivos.append(f"{k}: medido com {g!r}, pedido {p!r}")
    for k in INFORMATIVAS:
        if k in pedidas and pedidas[k] != gravadas.get(k):
            avisos.append(f"{k}: medido com {gravadas.get(k)!r}, agora {pedidas[k]!r} (não muda a medida; confirme no "
                          "próximo uso)")
    return motivos, avisos


def consultar_bloco(bib: dict, bloco_id: str, condicoes: dict) -> dict:
    """O bloco nas condições pedidas: 'validado' (com a receita pronta para o executor) ou 'medir_de_novo' (com os
    motivos, SEM a receita: medida de outras condições não é garantia)."""
    b = bib["blocos"].get(bloco_id)
    if b is None:
        return {"status": "nao_existe", "motivo": f"bloco {bloco_id!r} não está na biblioteca",
                "blocos": sorted(bib["blocos"])}
    motivos, avisos = comparar_condicoes(b["condicoes"], condicoes)
    if motivos:
        return {"status": "medir_de_novo", "bloco": bloco_id, "motivos": motivos, "avisos": avisos}
    return {"status": "validado", "frase": FRASE_VALIDO, "bloco": bloco_id, "avisos": avisos,
            "receita": {"linhagem": f"bloco-{bloco_id}", "tipo": "ajuste",
                        "hipotese": f"reaproveitar o bloco {bloco_id}, validado em {b['tentativas']}",
                        "passos": [dict(p) for p in b["receita"]]},
            "condicoes": {k: b["condicoes"].get(k) for k in OBRIGATORIAS + INFORMATIVAS},
            "medida": {"tentativas": b["tentativas"], "notas": b["notas"], "videos": b.get("videos", [])}}


# ---------- consultas para o Qwen (B4; só leitura) ----------
def _sugestoes(nome: str, opcoes) -> list:
    import difflib
    return difflib.get_close_matches(nome, sorted(opcoes), n=5, cutoff=0.4)


def listar_blocos(bib: dict, condicoes: dict | None = None) -> dict:
    out = []
    for b in sorted(bib["blocos"].values(), key=lambda b: b["id"]):
        item = {"bloco": b["id"], "papeis": [p["papel"] for p in b["receita"]],
                "clipes": [p["clipe"] for p in b["receita"]], "tentativas": b["tentativas"], "notas": b["notas"]}
        if condicoes is not None:
            motivos, _ = comparar_condicoes(b["condicoes"], condicoes)
            item["status"] = "medir_de_novo" if motivos else "validado"
            if motivos:
                item["motivos"] = motivos
        out.append(item)
    return {"blocos": out, "total": len(out)}


def historico_bloco(bib: dict, bloco_id: str) -> dict:
    b = bib["blocos"].get(bloco_id)
    if b is None:
        return {"status": "nao_existe", "motivo": f"bloco {bloco_id!r} não está na biblioteca",
                "blocos": sorted(bib["blocos"])}
    trocas = [{"troca": t["troca"], "tentativa": t["tentativa"], "de": t["clipe_a"], "para": t["clipe_b"],
               "giro": t.get("turn_deg_b", 0), **t["medida"]}
              for t in (bib["trocas"][i] for i in b["trocas"] if i in bib["trocas"])]
    return {"status": "ok", "bloco": b["id"], "receita": b["receita"], "tentativas": b["tentativas"],
            "notas": b["notas"], "duracao_s": b["duracao_s"], "intencoes": b["intencoes"], "trocas": trocas,
            "condicoes": b["condicoes"], "videos": b.get("videos", []), "fonte": b.get("fonte")}


def consultar_trocas(bib: dict, clipe_de: str, papel_para: str, condicoes: dict | None = None) -> dict:
    """Trocas JÁ MEDIDAS que saem de `clipe_de` para um clipe que fez o papel `papel_para`, da melhor para a pior.
    A mesma troca custa o mesmo em receitas diferentes (B2): repetições viram uma linha, com quantas vezes foi medida."""
    clipes = {t["clipe_a"] for t in bib["trocas"].values()}
    if papel_para not in F.PAPEIS + ("ponte",):
        return {"status": "recusado", "motivo": f"papel {papel_para!r} não existe; use um de {list(F.PAPEIS)}"}
    if clipe_de not in clipes:
        return {"status": "sem_medida", "motivo": f"nenhuma troca medida saindo de {clipe_de!r}",
                "parecidos": _sugestoes(clipe_de, clipes)}
    grupos = {}
    for t in bib["trocas"].values():
        if t["clipe_a"] == clipe_de and t["papel_b"] == papel_para:
            grupos.setdefault((t["clipe_b"], float(t.get("turn_deg_b") or 0))
                              + tuple(t.get(k, 0) for k in AJUSTES_TROCA), []).append(t)
    linhas = []
    for (clipe_b, giro, *aj), ts in grupos.items():
        m = ts[0]["medida"]
        linha = {"para": clipe_b, "giro": giro, "medida": m, "vezes_medida": len(ts),
                 "exemplo": ts[0]["id"], "passa_na_regua": m["nota"] == 0,
                 **{k: v for k, v in zip(AJUSTES_TROCA, aj) if v}}
        if condicoes is not None:
            motivos, _ = comparar_condicoes(ts[0]["condicoes"], condicoes)
            linha["status"] = "medir_de_novo" if motivos else "validado"
            if motivos:
                linha["motivos"] = motivos
        linhas.append(linha)
    linhas.sort(key=lambda x: (x["medida"]["nota"], x["medida"]["pior_osso_cm"]))
    return {"status": "ok", "de": clipe_de, "papel_para": papel_para, "trocas": linhas, "total": len(linhas)}


def ficha_clipe(bib: dict, nome: str) -> dict:
    f = bib["fichas"].get(nome)
    if f is None:
        return {"status": "nao_existe", "motivo": f"clipe {nome!r} sem ficha (nunca usado numa rodada)",
                "parecidos": _sugestoes(nome, bib["fichas"])}
    return dict(f, status="ok")
