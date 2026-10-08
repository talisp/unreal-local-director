"""Executor ÚNICO da rodada da fila de movimentos (07/10). O Qwen só escreve a receita (JSON); este programa valida,
pega a trava, monta no Sequencer, amostra os ossos, dá a nota pela régua fixa (src/unreal_macros/fila.py), registra
e limpa. Feito pelo Claude depois do parecer do Astra: a LLM não constrói a régua, não limpa a cena e não guarda o
estado de cabeça.

Comandos (na raiz do repositório, Python do venv):
  tentar ARQ_RECEITA [--video]   valida e roda em SEGUNDO PLANO; responde na hora com o número (o terminal do
                                 Hermes corta em 180 s; uma tentativa leva minutos)
  resultado N                    veredito da tentativa N (ou "rodando")
  estado                         campeãs, linhagens, regras, tentativa pendente, sucesso
  fechar-linhagem NOME MOTIVO    fecha uma linhagem (platô, beco)
  rodar-agora ARQ [--video]      o mesmo que tentar, mas no primeiro plano (uso do Claude nos ensaios)

Registro (tudo em work/fila_2026-10-07/, ou FILA_PASTA): tentativas.jsonl (uma linha 'tentativa_inicio' ANTES de
tocar na cena e uma 'tentativa' no fim), encaixes.jsonl (uma linha por troca, com as coordenadas antes/depois de
todos os ossos), estado.json (gravado de forma atômica), videos/. Linha JSON cortada por queda é ignorada na leitura.
Segurança: trava a cada tentativa; atores só TESTE_FILA_* em x=20000; nada salvo; a cena final é comparada ator
por ator (caminho e posição) com a do início; cada passo da limpeza é protegido sozinho."""
# pyright: reportMissingImports=false
# (src/ e tools/ entram no sys.path na hora de rodar; o verificador não enxerga)
import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import traceback
import uuid

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
sys.path.insert(0, os.path.join(RAIZ, "tools"))
PASTA = os.path.abspath(os.environ.get("FILA_PASTA", os.path.join(RAIZ, "work", "fila_2026-10-07")))
PY = os.path.join(RAIZ, "venv", "Scripts", "python.exe")
FPS = 30
ZX, ZY = 20000.0, 0.0
ATOR, PISO = "TESTE_FILA_BONECO", "TESTE_FILA_PISO"
PREFIXO = "TESTE_FILA_"
HORA_FECHAR = (7, 30)
# Condições da medida (Fase 3, D25): TC.boneco cria o SK_YBot sem mudar a escala; o root motion fica como a
# importação (macros.importar_clipe) deixa. Vão em toda tentativa e troca; a biblioteca as compara antes de reaproveitar.
CONDICOES = {"personagem": "/Game/Characters/SK_YBot.SK_YBot", "escala": 1.0, "root_motion": "padrao_importar_clipe"}


# ---------- arquivos (sem Unreal) ----------
def _ler_jsonl(nome: str) -> list:
    arq = os.path.join(PASTA, nome)
    out = []
    if os.path.exists(arq):
        with open(arq, encoding="utf-8", errors="replace") as f:
            for ln in f:
                try:
                    out.append(json.loads(ln))
                except ValueError:
                    pass  # linha cortada por queda: ignorada
    return out


def _acrescentar(nome: str, d: dict):
    os.makedirs(PASTA, exist_ok=True)
    with open(os.path.join(PASTA, nome), "a", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _estado() -> dict:
    arq = os.path.join(PASTA, "estado.json")
    try:
        return json.load(open(arq, encoding="utf-8"))
    except (OSError, ValueError):
        return {"proximo_n": 1, "pendente": None, "fechadas": {}}


def _gravar_estado(e: dict):
    os.makedirs(PASTA, exist_ok=True)
    tmp = os.path.join(PASTA, "estado.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(e, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, os.path.join(PASTA, "estado.json"))


def _agora() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _sha(caminho: str) -> str:
    with open(caminho, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def versoes() -> dict:
    return {"regua": _sha(os.path.join(RAIZ, "src", "unreal_macros", "fila.py")), "executor": _sha(__file__),
            "toolset": _sha(os.path.join(RAIZ, "editor_python", "director_tools", "toolset.py"))}


def tentativas_validas() -> list:
    return [t for t in _ler_jsonl("tentativas.jsonl") if t.get("tipo_linha") == "tentativa"]


def _pid_vivo(pid) -> bool:
    try:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"], capture_output=True, text=True, timeout=30)
        return str(int(pid)) in r.stdout
    except Exception:  # noqa: BLE001
        return True  # na dúvida, vivo (não assume)


def _cena() -> dict | None:
    """A cena da linha 2 (Fase 8), se FILA_CENA aponta para uma (cenas/<nome>.md). Sem ela: a rodada de 07/10."""
    arq = os.environ.get("FILA_CENA")
    if not arq:
        return None
    from unreal_macros import cena as C
    return C.ler_cena(arq if os.path.isabs(arq) else os.path.join(RAIZ, arq))


def prazo_de(inicio: dt.datetime, fechar: tuple) -> dt.datetime:
    """O primeiro `fechar` (HH, MM) DEPOIS do início da rodada. Astra, 08/10: a regra antiga ('antes do meio-dia e
    depois das 07:30') reabria a rodada à tarde."""
    p = inicio.replace(hour=fechar[0], minute=fechar[1], second=0, microsecond=0)
    return p if p > inicio else p + dt.timedelta(days=1)


def _fechar() -> tuple:
    c = _cena()
    return tuple(int(x) for x in c["prazo_tentativas"].split(":")) if c and c.get("prazo_tentativas") else HORA_FECHAR


def depois_da_hora() -> bool:
    e = _estado()
    if not e.get("inicio_rodada"):  # a 1ª pergunta da rodada marca o início (vale para a rodada inteira)
        e["inicio_rodada"] = _agora()
        _gravar_estado(e)
    return dt.datetime.now() >= prazo_de(dt.datetime.fromisoformat(e["inicio_rodada"]), _fechar())


# ---------- preparação da receita (sem Unreal) ----------
def preparar(receita: dict) -> tuple:
    """(n reservado, motivos de recusa). Recusa ANTES de tocar no Unreal: receita inválida, regras, hora, pendente."""
    from unreal_macros import fila as F
    from unreal_macros import receita as R
    motivos = R.validar(receita, _quadros_conhecidos())  # régua + campos da Fase 4 (início, corte, giro no fim)
    e = _estado()
    if e.get("pendente"):
        p = e["pendente"]
        if _pid_vivo(p.get("pid")):
            motivos.append(f"a tentativa {p['n']} ainda está rodando: espere (resultado {p['n']})")
    tent = tentativas_validas()
    if not motivos:
        motivos += F.checar_regras(receita, tent, e.get("fechadas", {}))
    if depois_da_hora():
        motivos.append("passou do prazo da rodada: não comece tentativas novas; escreva o FECHAMENTO.md")
    c = _cena()
    if c:  # Astra, 08/10: a cena é validada aqui também, não só no lançador
        from unreal_macros import cena as C
        motivos += [f"cena inválida: {m}" for m in C.validar_cena(c)["motivos"]]
    if c and c.get("variacoes", 0) > 0:  # linha 2 (Fase 8): depois do sucesso, K variações diferentes de verdade
        from unreal_macros import cena as C
        motivos += C.checar_variacao(receita, tent, c["variacoes"])
    elif receita.get("variacao"):
        motivos.append("esta rodada não tem fase de variações (sem FILA_CENA com 'variacoes')")
    elif F.sucesso(tent):
        motivos.append(f"já conseguiu ({F.sucesso(tent)}): use o tempo para medir outras trocas com tipo 'exploracao' "
                       "numa linhagem nova, ou escreva o FECHAMENTO")
    return e.get("proximo_n", 1), motivos


def _quadros_conhecidos() -> dict:
    """{clipe: quadros} das fichas da biblioteca, para recusar corte maior que o clipe antes do Unreal."""
    try:
        from unreal_macros import biblioteca as BIB
        return {c: f["quadros"] for c, f in BIB.carregar()["fichas"].items() if f.get("quadros")}
    except Exception:  # noqa: BLE001 - sem biblioteca, o seq_build ainda confere no Unreal
        return {}


# ---------- Unreal ----------
class Unreal:
    def __init__(self):
        import bloco2_v as V  # muda o cwd para src e configura a trava
        from unreal_macros import macros as M
        from unreal_macros.mcp_client import ASSET, SCENE, SEQ
        self.V, self.M, self.ASSET, self.SCENE, self.SEQ = V, M, ASSET, SCENE, SEQ
        self._nome = None

    def dt(self, f, **k):
        if self._nome is None:
            self._nome = max(re.findall(r"[\w.]*DirectorTools\w*", self.M.cliente().list_toolsets()), key=len)
        r = self.M.cliente().call(self._nome, f, **k)
        r = r.get("returnValue", r) if isinstance(r, dict) else r
        return json.loads(r)

    def cena(self) -> dict:
        r = self.dt("list_actors", class_name="", label_prefix="")
        return {a["caminho"]: {"rotulo": a["rotulo"], "xyz": a["xyz"]} for a in r["atores"]}

    def ossos(self, seq: str, q: int, nomes: str) -> dict:
        self.dt("seq_eval_frame", sequence_path=seq, frame=q)
        self.M.cliente().call(self.SEQ, "set_playhead_frame", frame=q)
        self.M.cliente().call(self.SEQ, "force_evaluate")
        r = self.dt("bone_world_positions", actor_label=ATOR, bones=nomes)  # leitura em OUTRA chamada
        return {"ossos": r.get("ossos", {}), "inexistentes": r.get("inexistentes", [])}

    def meus_atores(self, extras: tuple = ()) -> list:
        """Atores da rodada (TESTE_FILA_*) e, se pedido, o estúdio de uma execução que caiu (TESTE_ESTUDIO_<pid>_*)."""
        out = []
        for a in self.V.TC.teste_actors():
            rot = self.M.cliente().call(self.V.TC.ACTOR, "get_label", actor=a)
            if str(rot).startswith((PREFIXO,) + tuple(extras)):
                out.append(a)
        return out


def _video(u, seq: str, quadros: int, n: int, frente) -> dict:
    pasta = os.path.join(PASTA, "videos", f"t{n:03d}_quadros")
    os.makedirs(pasta, exist_ok=True)
    k = 0
    for q in range(0, quadros, 2):
        u.ossos(seq, q, "Hips")
        u.dt("capture_isolated_setup", actor_label=ATOR, yaw_deg=180.0 if frente[1] else 270.0, pitch_deg=6.0,
             distance_cm=420.0, width=640, height=360, also_show=PISO, center_bone="Hips")
        if u.dt("capture_isolated_shot", directory=pasta, filename=f"q{k:04d}.png").get("ok"):
            k += 1
    import imageio_ffmpeg
    mp4 = os.path.join(PASTA, "videos", f"t{n:03d}.mp4")  # nome único por tentativa: nada é sobrescrito
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-n", "-loglevel", "error", "-framerate", str(FPS // 2), "-i",
                    os.path.join(pasta, "q%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", mp4], check=True)
    return {"arquivo": mp4, "quadros": k}


def _limpar(u, seq, passos_limpeza: list):
    """Cada passo protegido sozinho: um erro não impede os seguintes."""
    def tenta(nome, fn):
        try:
            passos_limpeza.append({"passo": nome, "ok": True, "r": fn()})
        except Exception as e:  # noqa: BLE001
            passos_limpeza.append({"passo": nome, "ok": False, "erro": f"{type(e).__name__}: {str(e)[:200]}"})
    tenta("captura", lambda: u.dt("capture_isolated_restore"))
    if seq:
        def fecha():
            r = u.dt("seq_close_delete", sequence_path=seq)
            sobrou = [p for p in (u.M.cliente().call(u.ASSET, "find_assets", folder_path="/Game/_AnimLab/Experimentos",
                                                     name=seq.split("/")[-1].split(".")[0]) or [])]
            if not r.get("apagou") or sobrou:
                raise RuntimeError(f"sequência não apagada: {r}, ainda existe {sobrou}")
            return r
        tenta("sequencia", fecha)
    tenta("atores", lambda: [u.M.cliente().call(u.SCENE, "remove_from_scene", actor=a) for a in u.meus_atores()] and "ok")
    tenta("estudio", lambda: u.M.limpar_estudio() or "ok")  # TESTE_ESTUDIO_<pid desta execução>_* (aplicar_clipe cria)


def executar(receita: dict, n: int, video: bool = False) -> dict:
    """Uma tentativa completa. Grava 'tentativa_inicio' antes de tocar na cena e 'tentativa' no fim, sempre."""
    from unreal_macros import blocos as B
    from unreal_macros import fila as F
    from unreal_macros import receita as R
    from unreal_macros import trava
    e = _estado()
    e["pendente"] = {"n": n, "pid": os.getpid(), "desde": _agora(), "seq": None}
    e["proximo_n"] = n + 1
    _gravar_estado(e)
    base: dict = {"n": n, "linhagem": receita["linhagem"], "tipo": receita["tipo"], "de": receita.get("de"),
            "hipotese": receita.get("hipotese"), "observacao": receita.get("observacao"), "receita": receita["passos"],
            "variacao": bool(receita.get("variacao")),
            "assinatura": R.assinatura(receita), "versoes": versoes(), "fps": FPS, "condicoes": dict(CONDICOES)}
    _acrescentar("tentativas.jsonl", dict(base, tipo_linha="tentativa_inicio", quando=_agora()))
    res: dict = dict(base, tipo_linha="tentativa", quando_inicio=e["pendente"]["desde"], passou=False, nota=None,
               classe_erro=None, motivo=None, video=None, cena_ok=None)
    u = seq = antes = None
    limpeza = []
    try:
        u = Unreal()
        os.chdir(RAIZ)
        trava.pegar(u.M.TRAVA, f"fila-t{n}", log=os.path.join(os.path.dirname(u.M.TRAVA), "trava.log"))
        u.M._pilha["n"] += 1
        try:
            antes = u.cena()
            caidos = tuple(f"TESTE_ESTUDIO_{r}_" for r in _estado().get("runs_para_limpar", []))
            sujos = [a for a, v in antes.items() if v["rotulo"].startswith((PREFIXO,) + caidos)]
            if sujos:  # sobra de uma tentativa que caiu: é nossa (prefixo da rodada, estúdio do pid dela); limpa e registra
                for a in u.meus_atores(caidos):
                    u.M.cliente().call(u.SCENE, "remove_from_scene", actor=a)
                res["limpou_sobra_anterior"] = [antes[a]["rotulo"] for a in sujos]
                antes = u.cena()
            e = _estado()
            for sq in e.get("seqs_para_apagar", []):  # sequência de tentativa que caiu
                try:
                    res.setdefault("apagou_seq_anterior", []).append(u.dt("seq_close_delete", sequence_path=sq))
                except Exception as ex:  # noqa: BLE001
                    res.setdefault("apagou_seq_anterior", []).append({"seq": sq, "erro": str(ex)[:200]})
            e["runs_para_limpar"], e["seqs_para_apagar"] = [], []
            e["pendente"]["run"] = u.M.RUN
            _gravar_estado(e)
            try:
                u.V.caixa(PISO, ZX, ZY + 300, -100, 8, 14, 1)
                u.V.TC.boneco(ATOR, ZX, ZY)
                clipes = sorted({p["clipe"] for p in receita["passos"]} | {"Walking"})
                for c in clipes:
                    r = u.M.importar_clipe(c)  # macro: erro volta no relatório (ok=False), não como exceção
                    if isinstance(r, dict) and not r.get("ok", False):
                        raise LookupError(f"clipe {c}: {r.get('bloqueio') or r.get('erro') or r}")
                u.M.aplicar_clipe(ATOR, "Walking", loop=True, manter_se_falhar=True, checar_movimento=False)  # roll
                u.dt("set_pose_eval", actor_label=ATOR, on=True)
                o = u.dt("bone_world_positions", actor_label=ATOR, bones="LeftFoot,RightFoot,LeftToeBase,RightToeBase")["ossos"]
                fx = sum(o[f"{lado}ToeBase"][0] - o[f"{lado}Foot"][0] for lado in ("Left", "Right"))
                fy = sum(o[f"{lado}ToeBase"][1] - o[f"{lado}Foot"][1] for lado in ("Left", "Right"))
                frente = (0.0, math.copysign(1.0, fy)) if abs(fy) >= abs(fx) else (math.copysign(1.0, fx), 0.0)
                passos = R.passos_para_seq_build(receita, B.caminho)
                s = u.dt("seq_build", actor_label=ATOR, steps_json=json.dumps(passos), dir_x=frente[0], dir_y=frente[1], fps=FPS)
                if not s.get("ok"):
                    raise LookupError(f"seq_build: {s}")
                seq = s["sequencia"]
                e = _estado()
                e["pendente"]["seq"] = seq
                _gravar_estado(e)
                faixas = s["faixas"]
                res["montagem"] = {"faixas": faixas, "quadros": s["quadros"], "frente": frente,
                                   "assets": [p["anim"] for p in passos]}
                amostras, faltas = [], set()
                for q in F.quadros_a_amostrar(faixas):
                    r = u.ossos(seq, q, ",".join(F.OSSOS))
                    faltas |= set(r["inexistentes"])
                    amostras.append((q, r["ossos"]))
                av = F.avaliar(amostras, faixas, [p["papel"] for p in receita["passos"]], FPS)
                if faltas:
                    av = {"valida": False, "nota": None, "motivo": f"ossos inexistentes: {sorted(faltas)}"}
                res.update(nota=av.get("nota"), avaliacao={k: v for k, v in av.items() if k != "trocas"},
                           amostras=len(amostras))
                for t in av.get("trocas", []):
                    a, b = receita["passos"][t["troca"]], receita["passos"][t["troca"] + 1]
                    _acrescentar("encaixes.jsonl", dict(t, n=n, clipe_a=a["clipe"], clipe_b=b["clipe"],
                                                        asset_a=passos[t["troca"]]["anim"], asset_b=passos[t["troca"] + 1]["anim"],
                                                        turn_deg_b=b.get("turn_deg", 0), fps=FPS, versoes=base["versoes"],
                                                        condicoes=base["condicoes"], frente=frente, chao_z=0.0,
                                                        quando=_agora(), **_ajustes_da_troca(a, b)))
                if av.get("valida") and av.get("nota") == 0:  # a biblioteca guarda as amostras dos blocos (Fase 3)
                    _gravar_amostras(n, amostras)
                res["trocas"] = [{k: t[k] for k in ("troca", "quadril_cm", "pior_osso", "pior_osso_cm", "virada_deg", "nota")}
                                 for t in av.get("trocas", [])]
                if not av.get("valida"):
                    res["classe_erro"], res["motivo"] = "medida_instavel", av.get("motivo")
                else:
                    res["passou"] = av["nota"] == 0
                    falhas = [k for k, v in av["intencoes"].items() if not v["passou"]] + \
                             [f"troca {t['troca']} ({t['pior_osso']} {t['pior_osso_cm']} cm, quadril {t['quadril_cm']}, "
                              f"virada {t['virada_deg']}°)" for t in av["trocas"] if t["nota"] > 0]
                    res["classe_erro"] = None if res["passou"] else "encaixe"
                    res["falhas"] = sorted([k for k, v in av["intencoes"].items() if not v["passou"]] +
                                           [f"troca{t['troca']}" for t in av["trocas"] if t["nota"] > 0])
                    res["motivo"] = "passou" if res["passou"] else "; ".join(falhas)
                if video:
                    res["video"] = _video(u, seq, s["quadros"], n, frente)
            except LookupError as ex:
                res["classe_erro"], res["motivo"] = "dependencia", str(ex)[:400]
            finally:
                _limpar(u, seq, limpeza)
                depois = u.cena() if antes is not None else {}
                dif = {"sumiram": sorted(set(antes) - set(depois)), "sobraram": sorted(set(depois) - set(antes)),
                       "moveram": sorted(c for c in set(antes) & set(depois) if antes[c]["xyz"] != depois[c]["xyz"])}
                res["cena_ok"] = not any(dif.values()) and all(p["ok"] for p in limpeza)
                res["cena_diferencas"] = dif
        finally:
            u.M._pilha["n"] -= 1
            trava.soltar(u.M.TRAVA)
    except Exception as ex:  # noqa: BLE001
        res["classe_erro"] = res["classe_erro"] or "infraestrutura"
        res["motivo"] = res["motivo"] or f"{type(ex).__name__}: {str(ex)[:300]}"
        res["erro_original"] = traceback.format_exc()[-1500:]
    res["limpeza"] = limpeza
    res["quando"] = _agora()
    if res["cena_ok"] is False:
        res["classe_erro"] = "estado_parcial"
        res["motivo"] = f"CENA DIFERENTE DO INÍCIO: {res.get('cena_diferencas')} / limpeza {limpeza}"
    _acrescentar("tentativas.jsonl", res)
    e = _estado()
    e["pendente"] = None
    _gravar_estado(e)
    if res.get("nota") == 0:
        registrar_na_biblioteca()
    return res


def _ajustes_da_troca(a: dict, b: dict) -> dict:
    """Campos da Fase 4 que mudam a troca A -> B (só os que não são zero: as trocas antigas ficam iguais)."""
    d = {"corte_fim_a": a.get("corte_fim_q", 0), "turn_fim_a": a.get("turn_fim_deg", 0), "inicio_b": b.get("inicio_q", 0)}
    return {k: v for k, v in d.items() if v}


def _gravar_amostras(n: int, amostras: list):
    pasta = os.path.join(PASTA, "amostras")
    os.makedirs(pasta, exist_ok=True)
    tmp = os.path.join(pasta, f"t{n:03d}.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump([[q, o] for q, o in amostras], f)
    os.replace(tmp, os.path.join(pasta, f"t{n:03d}.json"))


def registrar_na_biblioteca(pasta_bib: str | None = None) -> dict:
    """Depois de uma nota 0: reimporta a rodada para a biblioteca (idempotente). O bloco só nasce com 3 notas 0 da
    mesma assinatura nas mesmas condições (biblioteca._blocos). Falha aqui NUNCA derruba a tentativa: fica registrada
    em biblioteca.jsonl da rodada. A pasta da biblioteca pode vir de BIBLIOTECA_PASTA (testes)."""
    from unreal_macros import biblioteca as BIB
    destino = pasta_bib or os.environ.get("BIBLIOTECA_PASTA") or BIB.PASTA
    try:
        r = BIB.importar_rodada(PASTA, os.path.basename(PASTA))
        total = BIB.mesclar(destino, r)
        linha = {"ok": True, "blocos": [b["id"] for b in r["blocos"]], "na_biblioteca": total}
    except Exception as ex:  # noqa: BLE001
        linha = {"ok": False, "erro": f"{type(ex).__name__}: {str(ex)[:300]}"}
    linha["quando"] = _agora()
    _acrescentar("biblioteca.jsonl", linha)
    return linha


def curto(res: dict) -> dict:
    """O que o Qwen precisa ler (resposta curta)."""
    return {k: res.get(k) for k in ("n", "linhagem", "tipo", "passou", "nota", "classe_erro", "motivo", "trocas",
                                    "cena_ok", "video")} | {"intencoes": {k: v.get("passou") for k, v in
                                                                          (res.get("avaliacao") or {}).get("intencoes", {}).items()}}


def recuperar_pendente() -> dict | None:
    """Tentativa que caiu (dono morto): registra como interrompida. A limpeza da cena acontece na próxima tentativa
    (os atores TESTE_FILA_* são da rodada) e a sequência fica anotada para conferência."""
    e = _estado()
    p = e.get("pendente")
    if not p or _pid_vivo(p.get("pid")):
        return None
    _acrescentar("tentativas.jsonl", {"tipo_linha": "tentativa_interrompida", "n": p["n"], "pendente": p, "quando": _agora()})
    e["pendente"] = None
    e.setdefault("runs_para_limpar", []).append(p.get("run") or str(p.get("pid")))  # o estúdio dela tem o pid no nome
    if p.get("seq"):
        e.setdefault("seqs_para_apagar", []).append(p["seq"])
    _gravar_estado(e)
    return p


def estado_resumo() -> dict:
    from unreal_macros import fila as F
    e = _estado()
    tent = tentativas_validas()
    lin = F.estado_linhagens(tent, e.get("fechadas", {}))
    return {"tentativas": len(tent), "pendente": e.get("pendente"), "proximo_n": e.get("proximo_n", 1),
            "linhagens": lin, "fechadas": e.get("fechadas", {}), "sucesso": F.sucesso(tent),
            "ultimas": [curto(t) | {"receita": [p["clipe"] for p in t["receita"]]} for t in tent[-5:]],
            "exploracoes_nas_ultimas_10": sum(t.get("tipo") == "exploracao" for t in tent[-10:]),
            "depois_do_prazo": depois_da_hora(), "versoes": versoes(), **_resumo_variacoes(tent)}


def _resumo_variacoes(tent: list) -> dict:
    c = _cena()
    if not c or c.get("variacoes", 0) <= 0:
        return {}
    from unreal_macros import cena as C
    ev = C.estado_variacoes(tent, c["variacoes"])
    return {"cena": c.get("nome"), "variacoes": {k: v for k, v in ev.items() if k != "referencias"}}


def main(argv: list) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd = argv[0]
    rec = recuperar_pendente()
    if rec:
        print(json.dumps({"aviso": f"a tentativa {rec['n']} tinha caído; registrada como interrompida"}, ensure_ascii=False))
    if cmd in ("tentar", "rodar-agora", "_filho"):
        arq = argv[1]
        try:
            receita = json.load(open(arq, encoding="utf-8"))
        except (OSError, ValueError) as ex:
            print(json.dumps({"recusada": [f"receita ilegível: {ex}"]}, ensure_ascii=False))
            return 1
        video = "--video" in argv or bool(receita.get("variacao"))  # toda variação sai com vídeo (Fase 8)
        if cmd == "_filho":  # só com a autorização de uso único que o 'tentar' grava depois do preparar (Astra, 08/10)
            e = _estado()
            aut = e.pop("autorizado", None) or {}
            if aut.get("n") != int(argv[2]) or aut.get("nonce") != (argv[3] if len(argv) > 3 else None):
                print(json.dumps({"recusada": ["_filho é interno: use 'tentar' (passa pelas regras antes do Unreal)"]},
                                 ensure_ascii=False))
                return 1
            _gravar_estado(e)
            executar(receita, int(argv[2]), video)
            return 0
        n, motivos = preparar(receita)
        if motivos:
            print(json.dumps({"recusada": motivos}, ensure_ascii=False))
            return 1
        if cmd == "rodar-agora":
            print(json.dumps(curto(executar(receita, n, video)), ensure_ascii=False, default=str))
            return 0
        os.makedirs(os.path.join(PASTA, "receitas"), exist_ok=True)
        copia = os.path.join(PASTA, "receitas", f"t{n:03d}.json")
        json.dump(receita, open(copia, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        saida = open(os.path.join(PASTA, "receitas", f"t{n:03d}_saida.txt"), "w", encoding="utf-8")
        e = _estado()
        e["autorizado"] = {"n": n, "nonce": uuid.uuid4().hex}
        _gravar_estado(e)
        subprocess.Popen([PY, os.path.abspath(__file__), "_filho", copia, str(n), e["autorizado"]["nonce"]]
                         + (["--video"] if video else []),
                         cwd=RAIZ, stdout=saida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         creationflags=0x00000008 | 0x00000200)
        print(json.dumps({"n": n, "status": "rodando", "dica": f"em 3 a 15 min: resultado {n}"}, ensure_ascii=False))
        return 0
    if cmd == "resultado":
        n = int(argv[1])
        fim = [t for t in _ler_jsonl("tentativas.jsonl") if t.get("n") == n and t.get("tipo_linha") in
               ("tentativa", "tentativa_interrompida")]
        if fim:
            print(json.dumps(curto(fim[-1]) if fim[-1]["tipo_linha"] == "tentativa" else fim[-1], ensure_ascii=False, default=str))
        else:
            p = _estado().get("pendente") or {}
            print(json.dumps({"n": n, "status": "rodando" if p.get("n") == n else "não encontrada"}, ensure_ascii=False))
        return 0
    if cmd == "estado":
        print(json.dumps(estado_resumo(), ensure_ascii=False, default=str, indent=1))
        return 0
    if cmd == "fechar-linhagem":
        e = _estado()
        e.setdefault("fechadas", {})[argv[1]] = " ".join(argv[2:]) or "sem motivo"
        _gravar_estado(e)
        _acrescentar("tentativas.jsonl", {"tipo_linha": "linhagem_fechada", "linhagem": argv[1], "motivo": e["fechadas"][argv[1]],
                                          "quando": _agora()})
        print(json.dumps({"fechada": argv[1]}, ensure_ascii=False))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
