"""Testes do tools/bateria.py (Fase 2a, S2 a S4). Não usa o Unreal; roda o Ruff e o basedpyright do .venv-ferramentas.

Os defeitos plantados vão numa CÓPIA da pasta de trabalho, fora do repositório. A mesma cópia roda antes sem eles:
é o controle de que a bateria não dá alarme falso no modo --pasta e de que é o defeito plantado que a faz falhar.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
_spec = importlib.util.spec_from_file_location("bateria", os.path.join(RAIZ, "tools", "bateria.py"))
assert _spec and _spec.loader
bateria = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bateria)
PY_FERR = os.path.join(RAIZ, ".venv-ferramentas", "Scripts", "python.exe")

CHAVES = {"ok", "etapas", "duracao_s", "commit", "conhecidos", "marco_aprovado"}
CHAVES_ETAPA = {"nome", "ok", "novos", "detalhe_curto"}
COMMIT_COM_DEFEITOS = "b74658e"  # S4: blocos.py ainda com os defeitos K1–K4 (corrigidos depois)


def confere_formato(r: dict):
    assert set(r) == CHAVES, f"chaves do JSON: {sorted(r)}"
    assert isinstance(r["ok"], bool) and isinstance(r["duracao_s"], (int, float)) and isinstance(r["commit"], str)
    assert isinstance(r["etapas"], list) and r["etapas"]
    for e in r["etapas"]:
        assert set(e) == CHAVES_ETAPA, f"chaves da etapa: {sorted(e)}"
        assert isinstance(e["nome"], str) and isinstance(e["ok"], bool)
        assert isinstance(e["novos"], int) and isinstance(e["detalhe_curto"], str)


def testa_porta_escutando():
    netstat = """
  Proto  Endereço local         Endereço externo       Estado           PID
  TCP    0.0.0.0:7              0.0.0.0:0              LISTENING       6604
  TCP    127.0.0.1:54321        127.0.0.1:8001         ESTABLISHED     111
  TCP    127.0.0.1:8001         127.0.0.1:54321        ESTABLISHED     222
"""
    assert bateria.porta_escutando(netstat) is False  # conexões abertas com a 8001 não são "escutando"
    assert bateria.porta_escutando(netstat + "  TCP    127.0.0.1:8001         0.0.0.0:0              ESCUTANDO       64444\n")
    assert bateria.porta_escutando("  TCP    127.0.0.1:18001        0.0.0.0:0   LISTENING  1\n") is False


def testa_comparar():
    base = {"a.py|E741": 2, "b.py|F401": 1}
    e = bateria.comparar("ruff", __import__("collections").Counter({"a.py|E741": 2, "b.py|F401": 1}), base)
    assert e["ok"] and e["novos"] == 0
    e = bateria.comparar("ruff", __import__("collections").Counter({"a.py|E741": 1, "c.py|E702": 1}), base)
    assert not e["ok"] and e["novos"] == 1 and "c.py|E702 +1" in e["detalhe_curto"]  # sumir um antigo não compensa


def testa_avaliar_suite():
    assert bateria.avaliar_suite("s", 0, "OK a\nOK b\nbloco2: 21/21\n")["ok"]
    e = bateria.avaliar_suite("s", 0, "diario: 0/0\n")  # rodada vazia sai com 0 e mesmo assim é falha
    assert not e["ok"] and e["novos"] == 1 and "0 casos" in e["detalhe_curto"], e
    e = bateria.avaliar_suite("s", 1, "OK a\nFALHA b | x\nbloco2: 20/21\n")
    assert not e["ok"] and e["novos"] == 1 and "20/21" in e["detalhe_curto"], e
    e = bateria.avaliar_suite("s", 0, "bloco2: 20/21\n")  # contagem incompleta reprova mesmo com saída 0
    assert not e["ok"], e
    e = bateria.avaliar_suite("s", 1, "Traceback ...\nAssertionError: plantado\n")
    assert not e["ok"] and "sem contagem" in e["detalhe_curto"], e
    assert bateria.avaliar_suite("s", 0, "")["ok"] is False


def _rodar_na_copia(copia: str, saida: str, extra: dict | None = None):
    env = dict(os.environ)
    env.update(extra or {})
    p = subprocess.run([PY_FERR, os.path.join(RAIZ, "tools", "bateria.py"), "--pasta", copia, "--saida", saida],
                       capture_output=True, timeout=300, env=env)
    r = json.load(open(os.path.join(saida, "RESUMO.json"), encoding="utf-8"))
    return p.returncode, r


def _copia(tmp: str) -> str:
    """Cópia da PASTA DE TRABALHO (arquivos do git + novos não ignorados), fora do repositório: testa o que ainda
    não foi commitado. (Até o S3 era `git archive HEAD`.)"""
    copia = os.path.join(tmp, "copia")
    nomes = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=RAIZ, check=True,
                           capture_output=True, timeout=60).stdout.decode("utf-8").split("\0")
    for nome in filter(None, nomes):
        origem = os.path.join(RAIZ, nome)
        if os.path.isfile(origem):
            os.makedirs(os.path.dirname(os.path.join(copia, nome)), exist_ok=True)
            shutil.copy2(origem, os.path.join(copia, nome))
    return copia


def _n_conhecidos(copia: str) -> int:
    return len(json.load(open(os.path.join(copia, "tools", "bateria_conhecidos.json"), encoding="utf-8")))


def testa_aviso_plantado_numa_copia():
    with tempfile.TemporaryDirectory(prefix="bateria_teste_") as tmp:
        tmp = os.path.realpath(tmp)
        copia = _copia(tmp)

        codigo, r = _rodar_na_copia(copia, os.path.join(tmp, "limpa"))  # controle: sem o aviso
        confere_formato(r)
        etapas = {e["nome"]: e for e in r["etapas"]}
        assert codigo == 0 and r["ok"], f"cópia limpa falhou: {r}"
        assert etapas["ruff"]["novos"] == 0 and etapas["basedpyright"]["novos"] == 0
        assert etapas["propriedades"]["novos"] == 0 and len(r["conhecidos"]) == _n_conhecidos(copia), r["conhecidos"]
        pendentes = [c for c in r["conhecidos"] if c["decisao_talis"] == "pendente"]
        assert r["marco_aprovado"] is (not pendentes), r["marco_aprovado"]

        with open(os.path.join(copia, "src", "plantado_bateria.py"), "w", encoding="utf-8") as f:
            f.write("a = 1; b = 2\n")  # E702: um aviso de Ruff, nenhum do basedpyright
        codigo, r = _rodar_na_copia(copia, os.path.join(tmp, "plantada"))
        confere_formato(r)
        etapas = {e["nome"]: e for e in r["etapas"]}
        assert codigo == 1 and r["ok"] is False, f"esperava sair com 1: {codigo} {r}"
        assert etapas["ruff"]["novos"] == 1 and not etapas["ruff"]["ok"], etapas["ruff"]
        assert "src/plantado_bateria.py|E702" in etapas["ruff"]["detalhe_curto"], etapas["ruff"]
        assert etapas["basedpyright"]["novos"] == 0, etapas["basedpyright"]
        nomes = [e["nome"] for e in r["etapas"]]
        assert all(f"suite:{s}" in nomes for s in bateria.SUITES), nomes
        assert "venv_runtime" in nomes and "worktree" not in nomes, nomes  # --pasta não cria worktree

        # S3: suíte forçada a falhar (raise no 1º caso do testes_diario), sem o aviso de Ruff
        os.remove(os.path.join(copia, "src", "plantado_bateria.py"))
        caminho = os.path.join(copia, "src", "testes_diario.py")
        texto = open(caminho, encoding="utf-8").read()
        assert "def testa_pass(tmp):" in texto
        open(caminho, "w", encoding="utf-8").write(
            texto.replace("def testa_pass(tmp):", "def testa_pass(tmp):\n    raise AssertionError('plantado pela bateria')", 1))
        codigo, r = _rodar_na_copia(copia, os.path.join(tmp, "suite_quebrada"))
        confere_formato(r)
        etapas = {e["nome"]: e for e in r["etapas"]}
        assert codigo == 1 and r["ok"] is False, f"esperava sair com 1: {codigo} {r}"
        assert not etapas["suite:testes_diario"]["ok"], etapas["suite:testes_diario"]
        assert etapas["ruff"]["novos"] == 0, etapas["ruff"]


def _contraexemplos(saida: str) -> list:
    return json.load(open(os.path.join(saida, "contraexemplos.json"), encoding="utf-8"))


def testa_propriedades_acham_defeitos_sozinhas():
    # S4: sem a lista de conhecidos, as propriedades acham os defeitos de blocos.py SEM ninguém dizer onde estão;
    # duas rodadas dão o mesmo resultado; um defeito novo plantado (porta aceitando 120 cm) faz sair com 1.
    with tempfile.TemporaryDirectory(prefix="bateria_teste_") as tmp:
        tmp = os.path.realpath(tmp)
        copia = _copia(tmp)
        vazia = os.path.join(tmp, "vazia.json")
        open(vazia, "w", encoding="utf-8").write("[]")

        # Os defeitos reais de 08/10 foram corrigidos depois do S4; para a prova continuar valendo, a cópia recebe o
        # blocos.py do commit do S4 (b74658e), que ainda os tinha.
        alvo = os.path.join(copia, "src", "unreal_macros", "blocos.py")
        atual = open(alvo, encoding="utf-8").read()
        antigo = subprocess.run(["git", "show", f"{COMMIT_COM_DEFEITOS}:src/unreal_macros/blocos.py"], cwd=RAIZ,
                                check=True, capture_output=True, timeout=60).stdout.decode("utf-8")
        open(alvo, "w", encoding="utf-8").write(antigo)
        resultados = []
        for i in (1, 2):
            codigo, r = _rodar_na_copia(copia, os.path.join(tmp, f"sem_lista_{i}"), {"BATERIA_CONHECIDOS": vazia})
            confere_formato(r)
            resultados.append((codigo, _contraexemplos(os.path.join(tmp, f"sem_lista_{i}"))))
        (codigo, ces), (_, ces2) = resultados
        assert ces == ces2, f"duas rodadas diferentes:\n{ces}\n{ces2}"
        assert codigo == 1, codigo
        textos = " | ".join(c["mensagem"] for c in ces)
        for esperado in ("abrir_porta(nan", "abrir_porta(inf", "andar(nan", "andar(inf", "andar(-", "andar(0.0"):
            assert esperado in textos, f"não achou {esperado}: {textos}"
        open(alvo, "w", encoding="utf-8").write(atual)

        texto = atual
        assert '"vao_min_cm": 150' in texto
        open(alvo, "w", encoding="utf-8").write(texto.replace('"vao_min_cm": 150', '"vao_min_cm": 120', 1))
        saida = os.path.join(tmp, "porta_120")
        codigo, r = _rodar_na_copia(copia, saida)
        etapas = {e["nome"]: e for e in r["etapas"]}
        assert codigo == 1 and etapas["propriedades"]["novos"] == 1, (codigo, etapas["propriedades"])
        assert [c["propriedade"] for c in _contraexemplos(saida)] == ["test_abrir_porta[abaixo_do_minimo]"], \
            _contraexemplos(saida)


if __name__ == "__main__":
    testes = (testa_porta_escutando, testa_comparar, testa_avaliar_suite, testa_aviso_plantado_numa_copia,
              testa_propriedades_acham_defeitos_sozinhas)
    passou = 0
    for fn in testes:
        try:
            fn()
            passou += 1
            print("OK", fn.__name__)
        except AssertionError as e:
            print("FALHOU", fn.__name__, "-", e)
    print(f"bateria: {passou}/{len(testes)}")
    sys.exit(0 if testes and passou == len(testes) else 1)
