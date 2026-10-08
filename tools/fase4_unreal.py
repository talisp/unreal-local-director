"""Prova ao vivo da Fase 4 (pontual e rápida): início adiantado, corte do fim e giro no fim no seq_build.

Uso: venv\\Scripts\\python.exe tools\\fase4_unreal.py     (com a trava; Unreal aberto; grava work/fase4/prova.json)
Monta 3 sequências do clipe Victory num boneco de teste (zona x=10000), mede ossos e apaga tudo:
  A = clipe inteiro; B = inicio_q=10, corte_fim_q=20; C = turn_fim_deg=90 (último passo).
Provas:
  1. início: B no quadro k = A no quadro 10+k (todos os ossos, k = 0 e 5), diferença <= 0,5 cm;
  2. corte: B tem exatamente 30 quadros a menos que A, e o último quadro de B = A no quadro (último - 20);
  3. giro no fim: no último quadro de C o quadril fica onde estava em A (<= 3 cm) e o corpo gira 90 graus (+-3);
  4. cena: no fim, os mesmos atores nas mesmas posições.
"""
import json
import math
import os
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
sys.path.insert(0, os.path.join(RAIZ, "tools"))
import fila_executor as X  # noqa: E402  # pyright: ignore[reportMissingImports]
from unreal_macros import blocos as B  # noqa: E402  # pyright: ignore[reportMissingImports]
from unreal_macros import fila as F  # noqa: E402  # pyright: ignore[reportMissingImports]
from unreal_macros import trava  # noqa: E402  # pyright: ignore[reportMissingImports]

OSSOS = ",".join(F.OSSOS)
CLIPE = "Victory"


def _dmax(a: dict, b: dict) -> float:
    return max(math.dist(a[n], b[n]) for n in F.OSSOS)


def main() -> int:
    t0 = time.time()
    res = {"provas": {}, "erros": []}
    u = X.Unreal()
    trava.pegar(u.M.TRAVA, "claude-fase4", log=os.path.join(os.path.dirname(u.M.TRAVA), "trava.log"))
    u.M._pilha["n"] += 1
    seqs, antes = [], None
    try:
        antes = u.cena()
        res["reload"] = u.dt("reload_toolset")
        u._nome = None  # o nome do toolset muda depois do reload
        u.V.TC.boneco(X.ATOR, 10000.0, 600.0)
        for c in (CLIPE, "Walking"):
            r = u.M.importar_clipe(c)
            if isinstance(r, dict) and not r.get("ok", False):
                raise RuntimeError(f"importar {c}: {r.get('bloqueio')}")
        # a mesma preparação do executor da fila (sem ela o boneco fica deitado e o quadril longe da raiz)
        u.M.aplicar_clipe(X.ATOR, "Walking", loop=True, manter_se_falhar=True, checar_movimento=False)
        u.dt("set_pose_eval", actor_label=X.ATOR, on=True)
        anim = B.caminho(CLIPE)

        def montar(passo):
            s = u.dt("seq_build", actor_label=X.ATOR, steps_json=json.dumps([passo]), dir_x=1.0, dir_y=0.0, fps=X.FPS)
            if not s.get("ok"):
                raise RuntimeError(f"seq_build {passo}: {s}")
            seqs.append(s["sequencia"])
            return s

        A = montar({"anim": anim})
        Bq = montar({"anim": anim, "inicio_q": 10, "corte_fim_q": 20})
        C = montar({"anim": anim, "turn_fim_deg": 90})
        na, nb = A["quadros"], Bq["quadros"]
        o = lambda s, q: u.ossos(s["sequencia"], q, OSSOS)["ossos"]  # noqa: E731
        d0, d5 = _dmax(o(Bq, 0), o(A, 10)), _dmax(o(Bq, 5), o(A, 15))
        res["provas"]["inicio"] = {"ok": d0 <= 0.5 and d5 <= 0.5, "dif_q0_cm": round(d0, 3), "dif_q5_cm": round(d5, 3)}
        dfim = _dmax(o(Bq, nb - 1), o(A, na - 21))
        res["provas"]["corte"] = {"ok": nb == na - 30 and dfim <= 0.5, "quadros_A": na, "quadros_B": nb,
                                  "dif_ultimo_cm": round(dfim, 3)}
        oa, oc = o(A, na - 1), o(C, C["quadros"] - 1)
        quadril = math.dist(oa["Hips"][:2], oc["Hips"][:2])
        giro = abs(F._dif(F.ang_quadril(oa), F.ang_quadril(oc)))
        res["provas"]["giro_fim"] = {"ok": quadril <= 3.0 and abs(giro - 90) <= 3.0, "quadril_moveu_cm": round(quadril, 2),
                                     "giro_deg": round(giro, 2)}
        diag = {}  # onde estão o quadril e a raiz no penúltimo e no último quadro, com e sem o giro
        for nome, s, q in (("A_ultimo", A, na - 1), ("C_penultimo", C, C["quadros"] - 2), ("C_ultimo", C, C["quadros"] - 1)):
            r = u.ossos(s["sequencia"], q, "Hips,root,Root")
            diag[nome] = {k: [round(v, 1) for v in xyz] for k, xyz in r["ossos"].items()}
        diag["faixas_C"] = C.get("faixas")
        res["diagnostico_giro"] = diag
    except Exception as ex:  # noqa: BLE001
        res["erros"].append(f"{type(ex).__name__}: {str(ex)[:400]}")
    finally:
        for s in seqs:
            try:
                res.setdefault("apagou", []).append(u.dt("seq_close_delete", sequence_path=s).get("apagou"))
            except Exception as ex:  # noqa: BLE001
                res["erros"].append(f"apagar {s}: {ex}")
        try:
            u.M.limpar_estudio()  # o aplicar_clipe cria o estúdio de medida (TESTE_ESTUDIO_<pid>_*): é nosso
            for a in u.V.TC.teste_actors():
                if u.M.cliente().call(u.V.TC.ACTOR, "get_label", actor=a) == X.ATOR:
                    u.M.cliente().call(u.SCENE, "remove_from_scene", actor=a)
            depois = u.cena()
            iguais = antes is not None and {k: v["xyz"] for k, v in antes.items()} == {k: v["xyz"] for k, v in depois.items()}
            res["provas"]["cena"] = {"ok": iguais, "atores_antes": len(antes or {}), "atores_depois": len(depois)}
        except Exception as ex:  # noqa: BLE001
            res["erros"].append(f"limpeza: {ex}")
        u.M._pilha["n"] -= 1
        trava.soltar(u.M.TRAVA)
    res["ok"] = not res["erros"] and all(p.get("ok") for p in res["provas"].values()) and len(res["provas"]) == 4
    res["segundos"] = round(time.time() - t0, 1)
    os.makedirs(os.path.join(RAIZ, "work", "fase4"), exist_ok=True)
    json.dump(res, open(os.path.join(RAIZ, "work", "fase4", "prova.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
