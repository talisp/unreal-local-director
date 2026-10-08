"""Confere o RELATO.json do Qwen contra os RESUMO.json da bateria, campo a campo (Fase 2a, S5).

Uso: .venv-ferramentas\\Scripts\\python.exe tools\\conferir_relato_bateria.py <pasta do s5> <RESUMO do commit> <linhas aceitas>
Ex.: ... work/bateria/s5 work/bateria/087aa03xxxxx/RESUMO.json 91,103

Confere: commit, ok, marco_aprovado, número de conhecidos e cada etapa (ok, novos) dos dois RESUMOs; o defeito da
cópia aponta src/unreal_macros/blocos.py numa das linhas aceitas; e o comando dado REPRODUZ a falha (sai != 0),
rodado na cópia com UNREAL_MACROS_OFFLINE=1. Imprime um JSON {ok, erros}; sai 0 só se tudo bater.
"""
import json
import os
import shutil
import subprocess
import sys


def _resumo_esperado(resumo: dict) -> dict:
    return {"commit": resumo["commit"], "ok": resumo["ok"], "marco_aprovado": resumo["marco_aprovado"],
            "conhecidos": len(resumo["conhecidos"]),
            "etapas": {e["nome"]: {"ok": e["ok"], "novos": e["novos"]} for e in resumo["etapas"]}}


def comparar(lado: str, relato: dict, resumo: dict) -> list:
    erros, esperado = [], _resumo_esperado(resumo)
    for campo in ("commit", "ok", "marco_aprovado", "conhecidos"):
        if relato.get(campo) != esperado[campo]:
            erros.append(f"{lado}.{campo}: relato {relato.get(campo)!r} x RESUMO {esperado[campo]!r}")
    etapas = relato.get("etapas") or {}
    if set(etapas) != set(esperado["etapas"]):
        erros.append(f"{lado}.etapas: nomes diferentes {sorted(set(etapas) ^ set(esperado['etapas']))}")
    for nome, e in esperado["etapas"].items():
        r = etapas.get(nome) or {}
        if (r.get("ok"), r.get("novos")) != (e["ok"], e["novos"]):
            erros.append(f"{lado}.etapas.{nome}: relato {r} x RESUMO {e}")
    return erros


def conferir_defeito(d: dict, copia: str, linhas: set) -> list:
    erros = []
    arq, _, lin = str(d.get("arquivo_linha", "")).rpartition(":")
    if not arq.replace("\\", "/").endswith("src/unreal_macros/blocos.py") or not lin.isdigit() or int(lin) not in linhas:
        erros.append(f"defeito no lugar errado: {d.get('arquivo_linha')!r} (aceitas: blocos.py:{sorted(linhas)})")
    cmd = str(d.get("comando", ""))
    if not cmd:
        return erros + ["defeito sem comando"]
    env = dict(os.environ, UNREAL_MACROS_OFFLINE="1")
    # Caminho exato: "bash" sozinho no subprocess do Windows abre o bash do WSL (System32), que sai 1 para tudo e
    # fazia qualquer comando parecer "reproduz" (08/10). shutil.which acha o mesmo bash do terminal do Hermes.
    bash = shutil.which("bash")
    if not bash:
        return erros + ["bash não encontrado para rodar o comando"]
    r = subprocess.run([bash, "-c", cmd], cwd=copia, env=env, capture_output=True, timeout=300)
    if r.returncode == 0:
        erros.append(f"o comando não reproduz a falha (saiu 0): {cmd}")
    return erros


def main(argv) -> int:
    pasta, resumo_commit, linhas = argv[0], argv[1], {int(x) for x in argv[2].split(",")}
    erros = []
    try:
        relato = json.load(open(os.path.join(pasta, "RELATO.json"), encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(json.dumps({"ok": False, "erros": [f"RELATO.json ilegível: {e}"]}, ensure_ascii=False))
        return 1
    erros += comparar("commit", relato.get("commit") or {}, json.load(open(resumo_commit, encoding="utf-8")))
    resumo_copia = json.load(open(os.path.join(pasta, "saida_copia", "RESUMO.json"), encoding="utf-8"))
    erros += comparar("copia", relato.get("copia") or {}, resumo_copia)
    defeitos = (relato.get("copia") or {}).get("defeitos") or []
    if not defeitos:
        erros.append("nenhum defeito relatado na cópia")
    for d in defeitos:
        erros += conferir_defeito(d, os.path.join(pasta, "copia"), linhas)
    print(json.dumps({"ok": not erros, "erros": erros}, ensure_ascii=False, indent=1))
    return 0 if not erros else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
