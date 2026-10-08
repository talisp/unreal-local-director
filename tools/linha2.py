"""Linha 2, cena completa com variações (Fase 8), num comando: cena -> pedido gerado -> Productor + vigia.

Uso (na raiz; quem lança o ensaio e a noite é o TALIS, nunca o Claude):
  venv\\Scripts\\python.exe tools\\linha2.py --cena cenas\\fila.md --seco     valida a cena e gera o pedido (não lança)
  venv\\Scripts\\python.exe tools\\linha2.py --cena cenas\\fila.md --ensaio   ensaio curto: tentativa válida, recusada,
                                                                         reprodução e um relançamento da vigia
  venv\\Scripts\\python.exe tools\\linha2.py --cena cenas\\fila.md --noite    a rodada longa (até a hora 'ate' da cena)
O Qwen roda pelo Hermes, no perfil codex-unreal-economico (D27, D28). Cena com papel ou critério que a régua de hoje
não mede = critério_ausente: nada é lançado. Grava work/<cena>_<data>[_ensaio]/ e escaladas/<data>-RODADA-<cena>[-ensaio].md.
Acompanhar: venv\\Scripts\\python.exe tools\\vigia_dev.py --resumo   ·   Parar a vigia: criar o arquivo work\\vigia\\PARAR
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
from unreal_macros import cena as C  # noqa: E402  # pyright: ignore[reportMissingImports]
from unreal_macros import fila as F  # noqa: E402  # pyright: ignore[reportMissingImports]
from unreal_macros import receita as R  # noqa: E402  # pyright: ignore[reportMissingImports]

PROTOCOLO = os.path.join(RAIZ, "docs", "rotinas", "L2_CENA.md")
HERMES = os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes", "bin", "hermes.cmd")
PY = os.path.join(RAIZ, "venv", "Scripts", "python.exe")
PERFIL = "codex-unreal-economico"
LIMITES_MODO = {"ensaio": {"max_turns": 25, "run_budget": 2400}, "noite": {"max_turns": 200, "run_budget": 5400}}
RAIZ_BASH = RAIZ.replace("\\", "/")

EXEMPLO = {"linhagem": "A", "tipo": "exploracao", "de": None, "hipotese": "o que espero e por quê",
           "passos": [{"clipe": "Sit_To_Stand", "papel": "levantar"}, {"clipe": "Waving", "papel": "acenar"},
                      {"clipe": "Idle_16", "papel": "ponte"}, {"clipe": "Start_Walking", "papel": "andar"},
                      {"clipe": "Walking", "papel": "andar"},
                      {"clipe": "Stop_Walking_2", "papel": "parar", "inicio_q": 2, "turn_deg": 0}]}


def criterios_texto(nomes: list) -> str:
    L = F.LIM
    desc = {
        "levantar": f"o quadril começa abaixo de {L['sentado_max_cm']:g} cm e chega a {L['de_pe_min_cm']:g} cm",
        "acenar": (f"a mão fica acima da cabeça (+{L['mao_acima_cm']:g} cm) por {L['aceno_quadros']} quadros ou mais, indo "
                   f"e voltando de lado {L['aceno_lateral_cm']:g} cm ou mais, com {L['aceno_inversoes']} inversões ou mais"),
        "andar": (f"o quadril anda {L['andar_cm']:g} cm ou mais e cada pé sai do chão {L['andar_passos_por_pe']} vezes ou "
                  "mais (deslizar não conta)"),
        "parar": (f"nos últimos {L['parar_quadros']} quadros o quadril anda menos de {L['parar_caminho_cm']:g} cm e os dedos "
                  f"ficam entre {L['dedo_min_cm']:g} e {L['dedo_max_cm']:g} cm do chão"),
        "trocas": (f"em cada troca, o quadril salta até {L['quadril_cm']:g} cm, qualquer osso até {L['osso_cm']:g} cm e a "
                   f"virada fica em até {L['virada_deg']:g}°"),
        "duracao": f"a cena inteira dura até {L['duracao_s']:g} s"}
    return "\n".join(f"  - **{n}:** {desc[n]};" for n in nomes)


def ferramentas_texto() -> str:
    campos = {"inicio_q": "começar o clipe N quadros adiante", "corte_fim_q": "cortar N quadros do fim",
              "turn_fim_deg": "girar depois do passo (no último passo, gira no lugar, em volta do quadril)"}
    linhas = ["- **Campos de um passo:** `clipe`, `papel` (os da cena ou `ponte`), `turn_deg` (giro instantâneo antes do "
              "passo, -180 a 180) e, opcionais:"]
    for k, (lo, hi) in R.LIMITES.items():
        linhas.append(f"  - `{k}`: {campos[k]}, de {lo:g} a {hi:g};")
    linhas.append("  - corte maior que o clipe é recusado antes do Unreal.")
    linhas.append("- **Consultas da biblioteca** (MCP `florentia-macros`, só leitura): `listar_blocos`, `consultar_bloco`, "
                  "`historico_bloco`, `consultar_trocas(clipe_de, papel_para)` e `ficha_clipe`.")
    linhas.append("- **Comandos do executor:** `estado`, `tentar <receita.json> [--video]`, `resultado N`, "
                  "`fechar-linhagem <L> \"motivo\"`.")
    linhas.append("- **Não existe:** velocidade e mistura entre clipes. Se precisar, registre `capacidade_ausente` no "
                  "LICOES.md, com o número que mostra que ajudaria.")
    return "\n".join(linhas)


def ensaio_texto(pasta: str) -> str:
    return (f"\n## Ensaio (esta rodada é curta: faça SÓ isto, nesta ordem)\n"
            "1. **Tentativa válida:** use `listar_blocos` e `consultar_bloco`. Se houver bloco validado desta cena, tente "
            "a receita dele: deve dar nota 0. Se não houver, uma receita sua.\n"
            "2. **Recusa de propósito:** uma receita com `corte_fim_q` maior que o clipe. O executor tem de recusar antes "
            "do Unreal.\n"
            "3. **Reprodução:** repita a tentativa 1 sem mudar nada. A nota tem de ser igual.\n"
            "4. **Relançamento:** esta sessão tem poucas ações de propósito. Quando ela parar, a vigia abre outra; "
            "continue pelo `estado`.\n"
            f"5. Escreva `{pasta}/ENSAIO.md`: o N, a nota e o `cena_ok` das 3 tentativas, e se você foi relançado. "
            "Pare (sem variações no ensaio).\n")


def gerar_pedido(cena: dict, arq_cena_rel: str, pasta_rel: str, modo: str) -> str:
    modelo = open(PROTOCOLO, encoding="utf-8").read().split("\n---\n", 1)[1].strip()
    cmd = (f'cd "{RAIZ_BASH}" && FILA_PASTA="{pasta_rel}" FILA_CENA="{arq_cena_rel}" '
           f'"{RAIZ_BASH}/venv/Scripts/python.exe" tools/fila_executor.py')
    escolha = (f'cd "{RAIZ_BASH}" && "{RAIZ_BASH}/venv/Scripts/python.exe" tools/escolha.py gerar {pasta_rel} '
               f'--cena {arq_cena_rel}')
    campos = {"nome": cena["nome"], "modo": " (ENSAIO)" if modo == "ensaio" else "", "descricao": cena.get("descricao", ""),
              "ate": cena["ate"], "prazo": cena["prazo_tentativas"], "cmd": cmd, "papeis": " → ".join(cena["papeis"]),
              "pode_variar": cena.get("pode_variar", ""), "fixo": cena.get("fixo", ""),
              "criterios": criterios_texto(cena["criterios"]), "ferramentas": ferramentas_texto(), "pasta": pasta_rel,
              "receita_exemplo": json.dumps(EXEMPLO, ensure_ascii=False), "variacoes": str(cena["variacoes"]),
              "ensaio": ensaio_texto(pasta_rel) if modo == "ensaio" else "", "escolha": escolha}
    for k, v in campos.items():
        modelo = modelo.replace("{" + k + "}", v)
    return modelo


def checar_ambiente(netstat: str, trava_existe: bool) -> list:
    """Motivos para NÃO lançar: Unreal fechado, modelo fora do ar ou trava ocupada."""
    def escutando(porta):
        return any(len(p) >= 3 and p[0].upper() == "TCP" and p[1].endswith(f":{porta}") and p[2].endswith(":0")
                   for p in (ln.split() for ln in netstat.splitlines()))
    m = []
    if not escutando(8001):
        m.append("o Unreal não está aberto (porta 8001 fechada)")
    if not escutando(8080):
        m.append("o modelo local não responde (porta 8080 fechada)")
    if trava_existe:
        m.append("a trava do Unreal está ocupada (work/unreal.trava): outro operador está trabalhando")
    return m


def lancar(pedido_abs: str, pasta_abs: str, cena: dict, modo: str) -> dict:
    lim = LIMITES_MODO[modo]
    flags = 0x00000008 | 0x00000200  # processo solto: continua se o terminal fechar
    sessao = subprocess.Popen(["cmd", "/c", HERMES, "-p", PERFIL, "chat", "--query-file", pedido_abs, "-Q",
                               "--max-turns", str(lim["max_turns"]), "--run-budget", str(lim["run_budget"])],
                              stdout=open(os.path.join(pasta_abs, "sessao_inicial.txt"), "w", encoding="utf-8"),
                              stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags)
    vigia = subprocess.Popen([PY, os.path.join(RAIZ, "tools", "vigia_dev.py"), "--perfil", PERFIL,
                              "--rodada", os.path.relpath(pasta_abs, RAIZ), "--pedido", os.path.relpath(pedido_abs, RAIZ),
                              "--ate", cena["ate"], "--max-turns", str(lim["max_turns"]),
                              "--run-budget", str(lim["run_budget"])],
                             cwd=RAIZ, stdout=open(os.path.join(pasta_abs, "vigia_saida.txt"), "w", encoding="utf-8"),
                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags)
    return {"sessao_pid": sessao.pid, "vigia_pid": vigia.pid, "modo": modo, "limites": lim,
            "quando": dt.datetime.now().isoformat(timespec="seconds")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="linha 2: cena com variações")
    ap.add_argument("--cena", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--seco", action="store_true")
    g.add_argument("--ensaio", action="store_true")
    g.add_argument("--noite", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    arq_cena = os.path.abspath(a.cena)
    cena = C.ler_cena(arq_cena)
    v = C.validar_cena(cena)
    if not v["ok"]:
        print("linha 2: a cena não pode rodar hoje:")
        for m in v["motivos"]:
            print(f"  ! {m}")
        if v["ausentes"]:
            print("  → registre em docs/PENDENCIAS.md como critério_ausente (trabalho do Claude: régua nova, com teste)")
        return 1
    modo = "ensaio" if a.ensaio else "noite" if a.noite else "seco"
    data = dt.date.today().isoformat()
    sufixo = "_ensaio" if modo == "ensaio" else ""
    pasta_rel = f"work/{cena['nome']}_{data}{sufixo}"
    pasta_abs = os.path.join(RAIZ, pasta_rel)
    os.makedirs(pasta_abs, exist_ok=True)
    pedido = gerar_pedido(cena, os.path.relpath(arq_cena, RAIZ).replace("\\", "/"), pasta_rel,
                          "ensaio" if modo == "ensaio" else "noite")
    pedido_rel = f"escaladas/{data}-RODADA-{cena['nome']}{'-ensaio' if modo == 'ensaio' else ''}.md"
    pedido_abs = os.path.join(RAIZ, pedido_rel)
    open(pedido_abs, "w", encoding="utf-8", newline="\n").write(pedido)
    if modo == "seco":
        print(f"linha 2 (seco): cena '{cena['nome']}' ok · pedido {pedido_rel} ({len(pedido)} caracteres) · rodada {pasta_rel}")
        return 0
    net = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, timeout=30).stdout.decode("utf-8", "replace")
    motivos = checar_ambiente(net, os.path.exists(os.path.join(RAIZ, "work", "unreal.trava")))
    if motivos:
        print("linha 2: não lancei:")
        for m in motivos:
            print(f"  ! {m}")
        return 1
    info = lancar(pedido_abs, pasta_abs, cena, modo)
    json.dump(dict(info, pedido=pedido_rel, rodada=pasta_rel, cena=cena["nome"]),
              open(os.path.join(pasta_abs, "LANCAMENTO.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"linha 2: {modo} lançado · Productor pid {info['sessao_pid']} · vigia pid {info['vigia_pid']} · rodada {pasta_rel}")
    print("  acompanhar: venv\\Scripts\\python.exe tools\\vigia_dev.py --resumo")
    print("  parar a vigia: criar o arquivo work\\vigia\\PARAR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
