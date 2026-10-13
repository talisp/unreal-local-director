"""Testes offline do pipeline novo do tools/astra.py (fase A rigorosa). NENHUM teste chama o Codex, o Hermes, o
Unreal ou a rede: o envio usa um Popen falso (ou, no teste de timeout, um script Python local que faz o papel do
codex). Tudo grava só no diretório temporário (TMPDIR) e usa um repositório git descartável.

Rodar:  python -m unittest docs/skills/test_astra_pipeline.py   (ou: python docs/skills/test_astra_pipeline.py)
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REAL = os.path.dirname(os.path.dirname(AQUI))
_spec = importlib.util.spec_from_file_location("astra_novo", os.path.join(RAIZ_REAL, "tools", "astra.py"))
assert _spec and _spec.loader
A = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A)


def _tmp_base() -> str:
    t = os.environ.get("TMPDIR")
    return t if t and os.path.isdir(t) else tempfile.gettempdir()


def _rm(p):
    def _w(f, path, _e):
        os.chmod(path, 0o700)
        f(path)
    shutil.rmtree(p, onerror=_w)


def _git(raiz, *a):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=raiz, check=True, capture_output=True)


def _escreve(raiz, rel, texto):
    p = os.path.join(raiz, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(texto.encode("utf-8"))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="astra-t-", dir=_tmp_base())
        self.addCleanup(_rm, self.tmp)
        self.raiz = os.path.join(self.tmp, "repo")
        self.copias = os.path.join(self.tmp, "copias")
        os.makedirs(self.raiz)
        _git(self.raiz, "init", "-q")
        _escreve(self.raiz, "docs/TALIS.md", "# Ordens do operador\nlinha 2\n")
        _escreve(self.raiz, "src/a.py", "a = 1\nb = 2\nc = 3\n")
        _escreve(self.raiz, "src/b.py", "x = 1\n")
        _escreve(self.raiz, "docs/HANDOFF.md", "handoff secreto\n")
        _git(self.raiz, "add", "-A")
        _git(self.raiz, "commit", "-q", "-m", "base")
        self.addCleanup(setattr, A, "RAIZ", A.RAIZ)
        setattr(A, "RAIZ", self.raiz)

    def prep(self, arquivos=("src/a.py", "src/b.py"), **kw):
        return A.preparar("tema x", "A régua tem furo?", list(arquivos), copias_base=self.copias, **kw)

    def resposta_boa(self, n=1, extra=None, pergunta="A régua tem furo?"):
        achados = [{"achado": f"problema {i}", "gravidade": "media", "prova": "src/a.py:2",
                    "correcao": f"corrigir {i}", "verificado": True} for i in range(1, n + 1)]
        d = {"pergunta": pergunta, "achados": achados, "resumo": "resumo curto"}
        d.update(extra or {})
        return "Olhei o código.\n```json\n" + json.dumps(d, ensure_ascii=False) + "\n```\n"


# ---------------------------------------------------------------- conferir_resposta
class ConferirResposta(Base):
    def conf(self, texto, **kw):
        kw.setdefault("raiz", self.raiz)
        return A.conferir_resposta(texto, **kw)

    def test_linha_zero_recusada(self):
        t = self.resposta_boa().replace("src/a.py:2", "src/a.py:0")
        r = self.conf(t)
        self.assertFalse(r["ok"], r)

    def test_linha_alem_do_fim_e_negativa(self):
        for ln in ("src/a.py:4", "src/a.py:-1"):
            self.assertFalse(self.conf(self.resposta_boa().replace("src/a.py:2", ln))["ok"], ln)

    def test_sem_pergunta_ou_resumo(self):
        for campo in ("pergunta", "resumo"):
            d = json.loads(self.resposta_boa().split("```json\n")[1].split("\n```")[0])
            del d[campo]
            r = self.conf("```json\n" + json.dumps(d) + "\n```")
            self.assertFalse(r["ok"], campo)
            self.assertTrue(any(campo in m for m in r["motivos"]), r["motivos"])

    def test_achados_tipo_errado_nao_lanca(self):
        for achados in ([1], ["x"], [None], [[]], "texto", {"a": 1}):
            txt = "```json\n" + json.dumps({"pergunta": "p", "achados": achados, "resumo": "r"}) + "\n```"
            r = self.conf(txt)
            self.assertFalse(r["ok"], achados)

    def test_campos_tipos(self):
        base = self.resposta_boa()
        for velho, novo in (('"verificado": true', '"verificado": "sim"'), ('"verificado": true', '"verificado": 1'),
                            ('"media"', '"enorme"'), ('"achado": "problema 1"', '"achado": ""'),
                            ('"achado": "problema 1"', '"achado": 5'), ('"correcao": "corrigir 1"', '"correcao": "  "'),
                            ('"correcao": "corrigir 1"', '"correcao": null')):
            self.assertFalse(self.conf(base.replace(velho, novo))["ok"], (velho, novo))

    def test_resposta_boa_passa_e_formato_dos_itens(self):
        r = self.conf(self.resposta_boa(2))
        self.assertTrue(r["ok"], r)
        for k in ("ok", "motivos", "achados", "pergunta", "resumo"):
            self.assertIn(k, r)
        for k in ("n", "gravidade", "achado", "prova"):
            self.assertIn(k, r["achados"][0])
        self.assertEqual([a["n"] for a in r["achados"]], [1, 2])

    def test_seis_achados_distintos_sem_teto_de_cinco(self):
        r = self.conf(self.resposta_boa(6), pergunta_esperada="A régua tem furo?", permitidos=["src/a.py"])
        self.assertTrue(r["ok"], r)
        self.assertEqual(len(r["achados"]), 6)
        self.assertEqual(len({a["achado"] for a in r["achados"]}), 6)

    def test_pergunta_esperada_exata(self):
        self.assertTrue(self.conf(self.resposta_boa(), pergunta_esperada="A régua tem furo?")["ok"])
        self.assertFalse(self.conf(self.resposta_boa(), pergunta_esperada="Outra pergunta?")["ok"])
        self.assertFalse(self.conf(self.resposta_boa(pergunta="a régua tem furo?"), pergunta_esperada="A régua tem furo?")["ok"])

    def test_caminhos_perigosos(self):
        outro = os.path.join(self.tmp, "fora.py")
        Path(outro).write_text("1\n2\n", encoding="utf-8")
        for prova in ("../fora.py:1", "/etc/passwd:1", outro.replace("\\", "/") + ":1", "C:/Windows/win.ini:1",
                      "src/../src/a.py:1", "./src/a.py:1", "src//a.py:1", "src\\a.py:1", "src/a.py.bak:1", "src/a.p:1"):
            r = self.conf(self.resposta_boa().replace("src/a.py:2", prova.replace("\\", "\\\\")), permitidos=["src/a.py"])
            self.assertFalse(r["ok"], prova)

    def test_lista_permitida_exata(self):
        self.assertTrue(self.conf(self.resposta_boa(), permitidos=["src/a.py", "src/b.py"])["ok"])
        r = self.conf(self.resposta_boa(), permitidos=["src/b.py"])
        self.assertFalse(r["ok"])

    def test_dentro_nao_usa_prefixo(self):
        self.assertTrue(A._dentro("/x/raiz", "/x/raiz/f"))
        self.assertFalse(A._dentro("/x/raiz", "/x/raiz-evil/f"))
        self.assertFalse(A._dentro("/x/raiz", "/x/outro"))

    def test_symlink_para_fora_recusado(self):
        fora = os.path.join(self.tmp, "fora.py")
        Path(fora).write_text("1\n2\n3\n", encoding="utf-8")
        try:
            os.symlink(fora, os.path.join(self.raiz, "src", "link.py"))
        except (OSError, NotImplementedError):
            self.skipTest("sem permissão para criar symlink neste Windows")
        r = self.conf(self.resposta_boa().replace("src/a.py:2", "src/link.py:1"))
        self.assertFalse(r["ok"], r)

    def test_provas_lista_toda_validada(self):
        ok = self.resposta_boa(extra=None)
        d = json.loads(ok.split("```json\n")[1].split("\n```")[0])
        d["achados"][0]["provas"] = ["src/a.py:1", "src/b.py:1"]
        self.assertTrue(self.conf("```json\n" + json.dumps(d) + "\n```")["ok"])
        d["achados"][0]["provas"] = ["src/a.py:1", "src/b.py:99"]
        self.assertFalse(self.conf("```json\n" + json.dumps(d) + "\n```")["ok"])
        d["achados"][0]["provas"] = "src/a.py:1"
        self.assertFalse(self.conf("```json\n" + json.dumps(d) + "\n```")["ok"])

    def test_sem_bloco_preserva_diagnostico_historico(self):
        r = self.conf("texto sem json")
        self.assertFalse(r["ok"])
        self.assertTrue(any("sem bloco" in m for m in r["motivos"]))

    def test_json_unico_e_terminal_no_modo_estrito(self):
        b = self.resposta_boa()
        self.assertFalse(self.conf(b + "texto depois", pergunta_esperada="A régua tem furo?")["ok"])
        self.assertFalse(self.conf(b + b, pergunta_esperada="A régua tem furo?")["ok"])
        self.assertTrue(self.conf(b, pergunta_esperada="A régua tem furo?")["ok"])

    def test_modo_historico_explicito_e_incompleto(self):
        r = self.conf(self.resposta_boa())
        self.assertEqual(r["modo"], "historico")
        self.assertTrue(r["incompleto"])
        self.assertFalse(r.get("validado", False))
        e = self.conf(self.resposta_boa(), pergunta_esperada="A régua tem furo?")
        self.assertEqual(e["modo"], "estrito")
        self.assertFalse(e["incompleto"])

    def test_limite_palavras_600_prosa_mais_resumo(self):
        prosa = " ".join(["p"] * 590)
        d = json.loads(self.resposta_boa().split("```json\n")[1].split("\n```")[0])
        d["resumo"] = " ".join(["r"] * 10)
        ok = prosa + "\n```json\n" + json.dumps(d) + "\n```"
        self.assertTrue(self.conf(ok, pergunta_esperada="A régua tem furo?")["ok"])
        d["resumo"] = " ".join(["r"] * 11)
        estoura = prosa + "\n```json\n" + json.dumps(d) + "\n```"
        r = self.conf(estoura, pergunta_esperada="A régua tem furo?")
        self.assertFalse(r["ok"])
        self.assertTrue(any("palavras" in m for m in r["motivos"]))

    def test_limite_bytes_do_json_proprio(self):
        with mock.patch.object(A, "ACHADOS_JSON_MAX_BYTES", 200):
            r = self.conf(self.resposta_boa(3), pergunta_esperada="A régua tem furo?")
        self.assertFalse(r["ok"])
        self.assertTrue(any("bytes" in m for m in r["motivos"]))

    def test_prioridades(self):
        pergunta = "A régua tem furo?"
        r = self.conf(self.resposta_boa(7, {"prioridades": [1, 2, 3]}), pergunta_esperada=pergunta)
        self.assertTrue(r["ok"], r)
        for ruim in ([9], [1, 1], [1, 2, 3, 4, 5, 6], ["1"], [True], "1", [0]):
            self.assertFalse(self.conf(self.resposta_boa(7, {"prioridades": ruim}), pergunta_esperada=pergunta)["ok"], ruim)

    def test_manifesto_arquivo_mudou_desde_o_snapshot(self):
        pasta = self.prep()
        man = A.carregar_manifesto(pasta)
        copia = man["copia"]
        self.assertTrue(self.conf(self.resposta_boa(), raiz=copia, manifesto=man, pergunta_esperada=man["pergunta"])["ok"])
        with open(os.path.join(copia, "src", "a.py"), "ab") as f:
            f.write(b"d = 4\n")
        r = self.conf(self.resposta_boa(), raiz=copia, manifesto=man, pergunta_esperada=man["pergunta"])
        self.assertFalse(r["ok"], r)


# ---------------------------------------------------------------- preparar / pedido
class Preparar(Base):
    def test_manifesto_snapshot_com_head_completo_e_dirty(self):
        _escreve(self.raiz, "src/a.py", "a = 1\nb = 2\nc = 3\nd = 4\n")  # sujo
        pasta = self.prep()
        man = A.carregar_manifesto(pasta)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.raiz, capture_output=True, text=True).stdout.strip()
        self.assertEqual(man["head"], head)
        self.assertEqual(len(man["head"]), 40)
        self.assertTrue(man["dirty"])
        self.assertIn("src/a.py", man["dirty_arquivos"])
        porcam = {x["path"]: x for x in man["arquivos"]}
        self.assertEqual(porcam["src/a.py"]["linhas"], 4)
        self.assertEqual(porcam["src/a.py"]["bytes"], len(b"a = 1\nb = 2\nc = 3\nd = 4\n"))
        self.assertEqual(len(porcam["src/a.py"]["sha256"]), 64)
        self.assertEqual(porcam["src/b.py"]["linhas"], 1)
        pedido = Path(os.path.join(pasta, "pedido.md")).read_text(encoding="utf-8")
        self.assertIn(head, pedido)
        self.assertIn(porcam["src/a.py"]["sha256"], pedido)
        self.assertIn("sujo", pedido.lower())
        self.assertNotIn("cego absoluto", man["escopo"].lower().replace("não alega cegueira absoluta", ""))
        self.assertIn("seleção", man["escopo"].lower())

    def test_pedido_sem_bateria_handoff_registro_pendencias_achados(self):
        pasta = self.prep()
        pedido = Path(os.path.join(pasta, "pedido.md")).read_text(encoding="utf-8")
        for proibido in ("HANDOFF", "REGISTRO", "Pendências abertas", "Bateria neste commit", "relatosjunior", "handoff secreto"):
            self.assertNotIn(proibido, pedido)
        self.assertLessEqual(len(pedido), A.PEDIDO_MAX)
        self.assertIn("A régua tem furo?", pedido)

    def test_arquivos_negados(self):
        _escreve(self.raiz, "AGENTS.md", "x\n")
        _escreve(self.raiz, "CLAUDE.md", "x\n")
        _escreve(self.raiz, "docs/REGISTRO.md", "x\n")
        _escreve(self.raiz, ".hermes/plans/p.md", "x\n")
        _escreve(self.raiz, "relatosjunior/q.md", "achado do qwen\n")
        for ruim in ("AGENTS.md", "CLAUDE.md", "docs/HANDOFF.md", "docs/REGISTRO.md", ".hermes/plans/p.md",
                     "relatosjunior/q.md", "../fora.py", "/abs/x.py", "src/nao_existe.py", "src", "src\\a.py", "src/../src/a.py"):
            with self.assertRaises(ValueError, msg=ruim):
                self.prep(arquivos=("src/a.py", ruim))
        self.assertFalse(os.path.isdir(os.path.join(self.raiz, "work", "astra")) and os.listdir(os.path.join(self.raiz, "work", "astra")))

    def test_sem_arquivos_ou_pergunta_vazia(self):
        with self.assertRaises(ValueError):
            A.preparar("t", "p?", [], copias_base=self.copias)
        with self.assertRaises(ValueError):
            A.preparar("t", "  ", ["src/a.py"], copias_base=self.copias)

    def test_final_14000_erro_sem_truncar_e_sem_residuo(self):
        with self.assertRaises(ValueError) as cm:
            A.preparar("t", "X" * 14000, ["src/a.py"], copias_base=self.copias)
        self.assertIn("14000", str(cm.exception))
        base = os.path.join(self.raiz, "work", "astra")
        self.assertFalse(os.path.isdir(base) and os.listdir(base))
        self.assertFalse(os.path.isdir(self.copias) and os.listdir(self.copias))
        with self.assertRaises(ValueError):
            A.montar_pedido("X" * 14000)  # caminho legado também não corta em silêncio

    def test_cabe_exatamente_no_limite(self):
        base = len(Path(os.path.join(self.prep(), "pedido.md")).read_text(encoding="utf-8"))
        vazio = base - len("A régua tem furo?")
        pergunta = "Z" * (A.PEDIDO_MAX - vazio)
        pasta = A.preparar("t2", pergunta, ["src/a.py", "src/b.py"], copias_base=self.copias)
        self.assertEqual(len(Path(os.path.join(pasta, "pedido.md")).read_text(encoding="utf-8")), A.PEDIDO_MAX)
        with self.assertRaises(ValueError):
            A.preparar("t3", pergunta + "Z", ["src/a.py", "src/b.py"], copias_base=self.copias)

    def test_copia_de_auditoria_fora_do_repo(self):
        pasta = self.prep()
        man = A.carregar_manifesto(pasta)
        copia = man["copia"]
        self.assertFalse(A._dentro(self.raiz, copia))
        self.assertTrue(A._dentro(self.copias, copia))
        agents = Path(os.path.join(copia, "AGENTS.md")).read_text(encoding="utf-8")
        self.assertIn("somente leitura", agents.lower())
        self.assertEqual(Path(os.path.join(copia, "docs", "TALIS.md")).read_bytes(), Path(os.path.join(self.raiz, "docs", "TALIS.md")).read_bytes())
        self.assertEqual(Path(os.path.join(copia, "src", "a.py")).read_bytes(), Path(os.path.join(self.raiz, "src", "a.py")).read_bytes())
        self.assertFalse(os.path.exists(os.path.join(copia, "docs", "HANDOFF.md")))
        self.assertFalse(os.path.exists(os.path.join(copia, "docs", "REGISTRO.md")))
        with self.assertRaises(ValueError):
            A.preparar("t", "p?", ["src/a.py"], copias_base=os.path.join(self.raiz, "dentro"))

    def test_pasta_exclusiva_sem_reuso(self):
        p1, p2 = self.prep(), self.prep()
        self.assertNotEqual(p1, p2)
        self.assertEqual(A.estado(p1), "PREPARADO")
        self.assertIn("tema-x", os.path.basename(p1))
        pasta_ruim = A.preparar("../../Fora/..\\x", "p?", ["src/a.py"], copias_base=self.copias)
        self.assertTrue(A._dentro(os.path.join(self.raiz, "work", "astra"), pasta_ruim))

    def test_exclusividade_concorrente_com_barreira(self):
        barreira = threading.Barrier(2, timeout=30)
        usados = []
        trava = threading.Lock()

        def gerar():
            with trava:
                n = len(usados)
                usados.append(n)
            if n < 2:  # as duas primeiras tentativas colidem de propósito (mesmo sufixo)
                barreira.wait()
                return "mesmo"
            return f"outro{n}"

        saida, erros = [], []

        def tarefa():
            try:
                saida.append(A.preparar("c", "p?", ["src/a.py"], copias_base=self.copias, gerar_sufixo=gerar))
            except BaseException as e:  # noqa: BLE001
                erros.append(e)

        ts = [threading.Thread(target=tarefa) for _ in range(2)]
        [t.start() for t in ts]
        [t.join(60) for t in ts]
        self.assertEqual(erros, [])
        self.assertEqual(len(set(saida)), 2, saida)
        self.assertEqual(sum(1 for p in saida if p.endswith("-mesmo")), 1)

    def test_eventos_numerados_exclusivos_em_concorrencia(self):
        pasta = self.prep()
        barreira = threading.Barrier(8, timeout=30)
        numeros = []

        def t():
            barreira.wait()
            numeros.append(A._evento(pasta, "FALHOU", motivo="x"))

        ts = [threading.Thread(target=t) for _ in range(8)]
        [x.start() for x in ts]
        [x.join(60) for x in ts]
        self.assertEqual(len(set(numeros)), 8, numeros)
        self.assertEqual(sorted(e["n"] for e in A.eventos(pasta)), list(range(1, 10)))


# ---------------------------------------------------------------- envio
class FakePopen:
    chamadas = []
    rc = 0
    escreve = True
    modelo_header: str | None = "gpt-6-astra"
    resposta: str | None = None

    def __init__(self, cmd, **kw):
        type(self).chamadas.append({"cmd": list(cmd), "kw": kw})
        self.cmd, self.kw = list(cmd), kw
        self.pid = 4242
        self.returncode = None
        self.entrada = None

    def communicate(self, input=None, timeout=None):
        self.entrada = input
        type(self).chamadas[-1]["input"] = input
        if self.modelo_header is not None:
            self.kw["stderr"].write(f"OpenAI Codex\nmodel: {self.modelo_header}\nsandbox: read-only\n".encode())
        self.kw["stdout"].write(b"saida\n")
        if self.escreve:
            saida = self.cmd[self.cmd.index("-o") + 1]
            with open(saida, "w", encoding="utf-8") as f:
                f.write(type(self).resposta or "")
        self.returncode = type(self).rc
        return (None, None)

    def kill(self):
        pass


def fake_popen(rc=0, escreve=True, modelo: str | None = "gpt-6-astra", resposta=""):
    FakePopen.chamadas = []
    FakePopen.rc, FakePopen.escreve, FakePopen.modelo_header, FakePopen.resposta = rc, escreve, modelo, resposta
    return FakePopen


class Envio(Base):
    def enviar(self, pasta, popen, **kw):
        kw.setdefault("login_ok", lambda: True)
        kw.setdefault("comando", ["codex"])
        return A.enviar(pasta, confirmo_cota=kw.pop("confirmo_cota", True), popen=popen, **kw)

    def test_cota_negativa_nao_cria_processo(self):
        pasta = self.prep()
        with mock.patch.object(subprocess, "Popen") as p, mock.patch.object(subprocess, "run") as r:
            res = A.enviar(pasta, confirmo_cota=False)
        self.assertEqual(res["codigo"], 2)
        p.assert_not_called()
        r.assert_not_called()
        self.assertEqual(A.estado(pasta), "PREPARADO")
        # pelo main: --enviar sem --confirmo-cota
        with mock.patch.object(A, "enviar") as e:
            self.assertEqual(A.main(["--tema", "t", "--pergunta", "p?", "--arquivos", "src/a.py", "--enviar"]), 2)
            e.assert_not_called()

    def test_um_envio_comando_modelo_readonly_e_estados(self):
        pasta = self.prep(modelo="modelo-x")
        popen = fake_popen(modelo="modelo-x", resposta=self.resposta_boa(2))
        res = self.enviar(pasta, popen)
        self.assertEqual(res["codigo"], 0, res)
        self.assertEqual(len(popen.chamadas), 1)
        cmd = popen.chamadas[0]["cmd"]
        man = A.carregar_manifesto(pasta)
        self.assertEqual(cmd[:2], ["codex", "exec"])
        self.assertEqual(cmd[cmd.index("-m") + 1], "modelo-x")
        self.assertEqual(cmd[cmd.index("-s") + 1], "read-only")
        self.assertEqual(cmd[cmd.index("-C") + 1], man["copia"])
        self.assertEqual(cmd[-1], "-")
        self.assertTrue(cmd[cmd.index("-o") + 1].startswith(pasta))
        self.assertNotIn("hermes", os.path.basename(cmd[0]).lower())  # executável, não diretório de scratch
        self.assertEqual(popen.chamadas[0]["input"], Path(os.path.join(pasta, "pedido.md")).read_bytes())
        self.assertEqual([e["estado"] for e in A.eventos(pasta)], ["PREPARADO", "EXECUTANDO", "PARECER_SALVO"])
        ev = A.eventos(pasta)[-1]
        self.assertEqual(ev["modelo_solicitado"], "modelo-x")
        self.assertEqual(ev["modelo_observado"], "modelo-x")  # identidade consistente; divergência testada separadamente
        self.assertEqual(res["estado"], "PARECER_SALVO")
        self.assertTrue(os.path.isfile(os.path.join(pasta, "parecer-A.md")))

    def test_modelo_divergente_nao_e_sucesso(self):
        pasta = self.prep(modelo="gpt-6-astra")
        res = self.enviar(pasta, fake_popen(modelo="outro-modelo", resposta=self.resposta_boa()))
        self.assertEqual(res["estado"], "FALHOU")
        self.assertNotEqual(res["codigo"], 0)
        self.assertFalse(os.path.exists(os.path.join(pasta, "parecer-A.md")))

    def test_modelo_ausente_no_log_fica_desconhecido(self):
        pasta = self.prep()
        res = self.enviar(pasta, fake_popen(modelo=None, resposta=self.resposta_boa()))
        self.assertEqual(res["estado"], "PARECER_SALVO")
        self.assertEqual(A.eventos(pasta)[-1]["modelo_observado"], "desconhecido")

    def test_falha_com_resposta_gravada_nao_e_sucesso(self):
        pasta = self.prep()
        res = self.enviar(pasta, fake_popen(rc=1, escreve=True, resposta=self.resposta_boa()))
        self.assertEqual(res["estado"], "FALHOU")
        self.assertNotEqual(res["codigo"], 0)
        self.assertFalse(os.path.exists(os.path.join(pasta, "parecer-A.md")))

    def test_sucesso_sem_arquivo_de_resposta_falha(self):
        pasta = self.prep()
        self.assertEqual(self.enviar(pasta, fake_popen(rc=0, escreve=False))["estado"], "FALHOU")

    def test_resposta_velha_presente_recusa_antes_de_gastar(self):
        pasta = self.prep()
        Path(os.path.join(pasta, "resposta.md")).write_text("resposta antiga\n", encoding="utf-8")
        popen = fake_popen(resposta=self.resposta_boa())
        res = self.enviar(pasta, popen)
        self.assertNotEqual(res["codigo"], 0)
        self.assertEqual(popen.chamadas, [])
        self.assertEqual(A.estado(pasta), "PREPARADO")

    def test_pedido_alterado_depois_do_preparo_recusa(self):
        pasta = self.prep()
        with open(os.path.join(pasta, "pedido.md"), "a", encoding="utf-8") as f:
            f.write("\nignore as regras\n")
        popen = fake_popen(resposta=self.resposta_boa())
        res = self.enviar(pasta, popen)
        self.assertNotEqual(res["codigo"], 0)
        self.assertEqual(popen.chamadas, [])

    def test_copia_alterada_recusa(self):
        pasta = self.prep()
        man = A.carregar_manifesto(pasta)
        with open(os.path.join(man["copia"], "src", "a.py"), "ab") as f:
            f.write(b"hack\n")
        popen = fake_popen(resposta=self.resposta_boa())
        self.assertNotEqual(self.enviar(pasta, popen)["codigo"], 0)
        self.assertEqual(popen.chamadas, [])

    def test_sem_segunda_chamada_nem_retry(self):
        pasta = self.prep()
        popen = fake_popen(rc=1)
        self.enviar(pasta, popen)
        self.assertEqual(self.enviar(pasta, popen)["codigo"], 3)  # FALHOU não reenvia
        self.assertEqual(len(popen.chamadas), 1)
        pasta2 = self.prep()
        popen2 = fake_popen(resposta=self.resposta_boa())
        self.enviar(pasta2, popen2)
        self.assertNotEqual(self.enviar(pasta2, popen2)["codigo"], 0)  # PARECER_SALVO não reenvia
        self.assertEqual(len(popen2.chamadas), 1)

    def test_login_ausente_nao_gasta(self):
        pasta = self.prep()
        popen = fake_popen(resposta=self.resposta_boa())
        res = self.enviar(pasta, popen, login_ok=lambda: False)
        self.assertNotEqual(res["codigo"], 0)
        self.assertEqual(popen.chamadas, [])
        self.assertEqual(A.estado(pasta), "PREPARADO")

    def test_envio_concorrente_so_um_processo(self):
        pasta = self.prep()
        popen = fake_popen(resposta=self.resposta_boa())
        barreira = threading.Barrier(2, timeout=30)

        def login():
            barreira.wait()
            return True

        res = []
        ts = [threading.Thread(target=lambda: res.append(self.enviar(pasta, popen, login_ok=login))) for _ in range(2)]
        [t.start() for t in ts]
        [t.join(60) for t in ts]
        self.assertEqual(len(popen.chamadas), 1, popen.chamadas)
        self.assertEqual(sorted(r["codigo"] == 0 for r in res), [False, True])

    def test_timeout_mata_so_a_arvore_e_marca_interrompido(self):
        pasta = self.prep()
        mortos = []

        class Lento(FakePopen):
            def communicate(self, input=None, timeout=None):
                if timeout is not None and not mortos:
                    raise subprocess.TimeoutExpired(self.cmd, timeout)
                return (None, None)

        FakePopen.chamadas = []
        res = self.enviar(pasta, Lento, timeout_s=1, matar=lambda p: mortos.append(p.pid))
        self.assertEqual(mortos, [4242])
        self.assertEqual(res["estado"], "INTERROMPIDO")
        self.assertFalse(os.path.exists(os.path.join(pasta, "parecer-A.md")))

    def test_timeout_real_encerra_neto_do_processo(self):
        pasta = self.prep()
        script = os.path.join(self.tmp, "falso_codex.py")
        pidfile = os.path.join(self.tmp, "neto.pid")
        with open(script, "w") as f:
            f.write("import subprocess, sys, time, os\n"
                    "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
                    f"open({pidfile!r}, 'w').write(str(p.pid))\n"
                    "time.sleep(120)\n")
        res = self.enviar(pasta, subprocess.Popen, comando=[sys.executable, script], timeout_s=5)
        self.assertEqual(res["estado"], "INTERROMPIDO", res)
        neto = int(Path(pidfile).read_text(encoding="utf-8"))
        self.addCleanup(lambda: A._matar_pid(neto))
        self.assertFalse(A._vivo(neto), "o neto do processo continuou vivo depois do timeout")


# ---------------------------------------------------------------- retomada / conferência / comparação
class Retomada(Base):
    def salvo(self, n=2):
        pasta = self.prep()
        res = A.enviar(pasta, confirmo_cota=True, popen=fake_popen(resposta=self.resposta_boa(n)),
                       login_ok=lambda: True, comando=["codex"])
        self.assertEqual(res["estado"], "PARECER_SALVO", res)
        return pasta

    def test_interrupcao_e_retomada_sem_segunda_chamada(self):
        pasta = self.prep()

        class Quebra(FakePopen):
            def communicate(self, input=None, timeout=None):
                raise KeyboardInterrupt

        FakePopen.chamadas = []
        with self.assertRaises(KeyboardInterrupt):
            A.enviar(pasta, confirmo_cota=True, popen=Quebra, login_ok=lambda: True, comando=["codex"], matar=lambda p: None)
        self.assertEqual(A.estado(pasta), "INTERROMPIDO")
        popen = fake_popen(resposta=self.resposta_boa())
        r = A.retomar(pasta)
        self.assertFalse(r["reenviar"])
        again = self.enviar_de_novo(pasta, popen)
        self.assertNotEqual(again["codigo"], 0)
        self.assertEqual(popen.chamadas, [])

    def enviar_de_novo(self, pasta, popen):
        return A.enviar(pasta, confirmo_cota=True, popen=popen, login_ok=lambda: True, comando=["codex"])

    def test_executando_ambiguo_vira_interrompido_sem_reenviar(self):
        pasta = self.prep()
        A._evento(pasta, "EXECUTANDO", modelo_solicitado="x")  # processo caiu antes de qualquer desfecho
        with open(os.path.join(pasta, "resposta.md"), "w") as f:
            f.write("meio escrita")
        r = A.retomar(pasta)
        self.assertEqual(r["estado"], "INTERROMPIDO")
        self.assertTrue(r["ambiguo"])
        self.assertFalse(r["reenviar"])
        popen = fake_popen(resposta=self.resposta_boa())
        self.assertNotEqual(self.enviar_de_novo(pasta, popen)["codigo"], 0)
        self.assertEqual(popen.chamadas, [])

    def test_retomada_de_parecer_salvo_le_artefatos_e_nao_reenvia(self):
        pasta = self.salvo()
        r = A.retomar(pasta)
        self.assertEqual(r["estado"], "PARECER_SALVO")
        self.assertFalse(r["reenviar"])
        self.assertIn("conferir", r["proximo"])

    def test_conferir_usa_snapshot_nao_head_atual(self):
        pasta = self.salvo()
        _escreve(self.raiz, "src/a.py", "mudou\n")  # a árvore principal muda depois do envio
        _git(self.raiz, "add", "-A")
        _git(self.raiz, "commit", "-q", "-m", "novo head")
        conf = A.conferir_campanha(pasta)
        self.assertTrue(conf["ok"], conf)
        self.assertEqual(conf["modo"], "estrito")

    def test_conferir_detecta_parecer_adulterado(self):
        pasta = self.salvo()
        with open(os.path.join(pasta, "parecer-A.md"), "a", encoding="utf-8") as f:
            f.write("\nadulterado\n")
        with self.assertRaises(ValueError):
            A.conferir_campanha(pasta)

    def test_conferir_antes_do_parecer_recusa(self):
        with self.assertRaises(ValueError):
            A.conferir_campanha(self.prep())

    def test_comparar_so_depois_de_a_salvo_e_preserva_a(self):
        rel = os.path.join(self.tmp, "relatosjunior")
        os.makedirs(rel)
        qwen = os.path.join(rel, "q1.md")
        Path(qwen).write_text("achei algo em src/a.py:2 e em src/b.py:1\n", encoding="utf-8")
        pasta = self.prep()
        with mock.patch.object(A, "_ler_relatorio") as lendo:
            with self.assertRaises(ValueError):
                A.comparar_campanha(pasta, [qwen])
            lendo.assert_not_called()  # nem abriu o relatório do Qwen
        pasta = self.salvo()
        antes = Path(os.path.join(pasta, "parecer-A.md")).read_bytes()
        r = A.comparar_campanha(pasta, [qwen])
        self.assertEqual(Path(os.path.join(pasta, "parecer-A.md")).read_bytes(), antes)
        self.assertEqual(A.estado(pasta), "COMPARADO")
        self.assertIn("src/a.py:2", r["em_ambos"])
        self.assertIn("src/b.py:1", r["so_qwen"])
        self.assertEqual(r["so_a"], [])
        self.assertTrue(r["relatorios"][0]["sha256"])
        self.assertTrue(os.path.isfile(os.path.join(pasta, "comparacao.json")))
        ordem = [e["estado"] for e in A.eventos(pasta)]
        self.assertEqual(ordem, ["PREPARADO", "EXECUTANDO", "PARECER_SALVO", "COMPARADO"])

    def test_preparo_e_envio_nunca_abrem_relatosjunior(self):
        lidos = []
        real = open

        def espia(f, *a, **k):
            lidos.append(str(f))
            return real(f, *a, **k)

        with mock.patch("builtins.open", espia):
            pasta = self.prep()
            A.enviar(pasta, confirmo_cota=True, popen=fake_popen(resposta=self.resposta_boa()), login_ok=lambda: True, comando=["codex"])
        self.assertFalse([p for p in lidos if "relatosjunior" in p.lower()])


# ---------------------------------------------------------------- CLI legada
class CliLegada(Base):
    def test_portas_legadas_sem_arquivos_recusam_antes_de_gastar(self):
        with mock.patch.object(A, "enviar") as e, mock.patch.object(subprocess, "Popen") as p:
            self.assertEqual(A.main(["--tema", "t", "--pergunta", "p?", "--enviar", "--confirmo-cota"]), 2)
            self.assertEqual(A.main(["--tema", "t", "--pergunta", "p?"]), 2)
            e.assert_not_called()
            p.assert_not_called()
        self.assertFalse(os.path.isdir(os.path.join(self.raiz, "work", "astra")))

    def test_fases_preparar_conferir_e_enviar_exige_flags(self):
        self.assertEqual(A.main(["--tema", "t", "--pergunta", "A régua tem furo?", "--arquivos", "src/a.py,src/b.py", "--fase", "preparar"]), 0)
        base = os.path.join(self.raiz, "work", "astra")
        pasta = os.path.join(base, os.listdir(base)[0])
        with mock.patch.object(A, "enviar") as e:
            self.assertEqual(A.main(["--fase", "enviar", "--campanha", pasta]), 2)
            self.assertEqual(A.main(["--fase", "enviar", "--campanha", pasta, "--enviar"]), 2)
            e.assert_not_called()

    def test_conferir_legado_de_arquivo_e_historico(self):
        resp = os.path.join(self.tmp, "r.md")
        Path(resp).write_text(self.resposta_boa(), encoding="utf-8")
        self.assertEqual(A.main(["--tema", "t", "--conferir", resp]), 0)
        self.assertTrue(os.path.isfile(os.path.join(self.raiz, "escaladas", f"{A.dt.date.today().isoformat()}-ASTRA-t.md")))


if __name__ == "__main__":
    unittest.main()
