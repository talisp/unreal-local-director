"""Busca na biblioteca Mixamo local (nome, descrição e legenda de movimento do UniML3D) e prévia em quadros."""
import csv
import functools
import os
import re
import subprocess

from .macros import BIBLIOTECA, RAIZ_WORK, _achar_anim, macro

_STOP = {"a", "the", "and", "with", "of", "to", "in", "on", "an", "o", "e", "de", "um", "uma"}


@functools.lru_cache(maxsize=1)
def _indice() -> list:
    estaticos = set()
    try:
        with open(os.path.join(BIBLIOTECA, "static_clips.csv"), encoding="utf-8") as f:
            estaticos = {os.path.basename(r.get("file", "")) for r in csv.DictReader(f)}
    except FileNotFoundError:
        pass
    legenda = {}
    try:
        with open(os.path.join(BIBLIOTECA, "uniml3d_clips.csv"), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("dataset") == "mixamo":
                    legenda[r["clip"]] = r.get("caption", "")
    except FileNotFoundError:
        pass
    itens = []
    with open(os.path.join(BIBLIOTECA, "metadata.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            arq = os.path.basename(r["file"])
            if arq in estaticos:
                continue
            nome = arq[:-4]
            itens.append({"nome": nome, "prompt": r.get("prompt", ""), "descricao": r.get("text", ""),
                          "legenda": legenda.get(nome, ""), "quadros": int(r.get("frames") or 0)})
    return itens


def _tokens(s: str) -> set:
    return {t for t in re.findall(r"[a-z]+", s.lower()) if t not in _STOP and len(t) > 2}


@macro
def buscar_clipe(rel, texto: str, n: int = 10, max_quadros: int = 0):
    """Procura clipes por palavras em inglês (ex.: 'talking standing', 'sit down chair'). max_quadros > 0 filtra clipes longos.
    Pontua nome/descrição (peso 2) e a legenda do movimento do corpo (peso 1)."""
    import math
    q = _tokens(texto)
    if not q:
        raise ValueError("texto vazio; use palavras em inglês")
    idx = _indice()
    df = {t: sum(1 for it in idx if t in _tokens(it["prompt"] + " " + it["descricao"] + " " + it["legenda"])) for t in q}
    idf = {t: math.log((1 + len(idx)) / (1 + df[t])) for t in q}
    res = []
    for it in idx:
        if max_quadros and it["quadros"] > max_quadros:
            continue
        nd = q & _tokens(it["prompt"] + " " + it["descricao"])
        lg = q & _tokens(it["legenda"])
        s = sum(2 * idf[t] for t in nd) + sum(idf[t] for t in lg - nd)
        if _tokens(it["nome"].replace("_", " ")) == q:
            s += 5  # nome exato do clipe
        s = round(s, 2)
        if s:
            res.append((s, it))
    res.sort(key=lambda x: (-x[0], x[1]["quadros"]))
    rel["medidas"]["clipes"] = [dict(it, pontos=s) for s, it in res[:n]]
    if not res:
        rel["avisos"].append("nada encontrado; tente sinônimos em inglês")


@macro
def previa_clipe(rel, nome: str, vista: int = 0):
    """Extrai 3 quadros (início, meio, fim) da prévia em vídeo do clipe e junta numa imagem para conferir com a
    visão ANTES de importar. vista: 0 frente, 1 costas, 2 e 3 lados."""
    import imageio_ffmpeg
    from PIL import Image
    mp4 = os.path.join(BIBLIOTECA, "animation_motion_render", nome, f"v00{vista}.mp4")
    if not os.path.exists(mp4):
        raise FileNotFoundError(f"sem prévia para {nome}")
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    pasta = os.path.join(RAIZ_WORK, "previas")
    os.makedirs(pasta, exist_ok=True)
    quadros = []
    for i, frac in enumerate((0.05, 0.5, 0.95)):
        out = os.path.join(pasta, f"_{nome}_{i}.png")
        dur = subprocess.run([ff, "-i", mp4], capture_output=True, text=True).stderr
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", dur)
        seg = (int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))) if m else 2.0
        subprocess.run([ff, "-y", "-loglevel", "error", "-ss", f"{seg * frac:.2f}", "-i", mp4, "-frames:v", "1", out], check=True)
        quadros.append(Image.open(out).convert("RGB"))
    w, h = quadros[0].size
    folha = Image.new("RGB", (w * 3, h), "white")
    for i, q in enumerate(quadros):
        folha.paste(q, (i * w, 0))
    arq = os.path.join(pasta, f"{nome}_v{vista}.png")
    folha.save(arq)
    rel["evidencias"].append(arq)
    rel["medidas"].update({"quadros": [0.05, 0.5, 0.95], "importado": bool(_achar_anim(nome))})


buscar_clipe.__wrapped__._usa_unreal = False  # não precisa da trava do Unreal
previa_clipe.__wrapped__._usa_unreal = False  # só lê a biblioteca local (achado pelo Hermes, 06/10)
