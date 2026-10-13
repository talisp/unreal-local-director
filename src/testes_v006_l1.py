"""Regressões L1 da v0.0.6 (A05, A06, A07, A18): executar() de ponta a ponta com um Unreal FALSO.

Nada aqui conecta ao Unreal, pega a trava real ou chama LLM: o mundo é um dicionário em memória e a trava é um
arquivo temporário. O que se prova é o comportamento do executor; a prova no Unreal real é um ensaio à parte.
"""
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
import fila_executor as X  # noqa: E402

RECEITA = {"linhagem": "A", "tipo": "exploracao", "hipotese": "teste", "passos": [
    {"clipe": "Sit_To_Stand", "papel": "levantar"}, {"clipe": "Waving", "papel": "acenar"},
    {"clipe": "Start_Walking", "papel": "andar"}, {"clipe": "Stop_Walking_2", "papel": "parar"}]}
SEQ = "/Game/_AnimLab/Experimentos/SEQ_TESTE_1.SEQ_TESTE_1"
MOVEL = {"rotulo": "Mesa", "classe": "StaticMeshActor", "xyz": [1.0, 2.0, 3.0], "rotacao": [0.0, 0.0, 0.0],
         "escala": [1.0, 1.0, 1.0]}


class Mundo:
    """A cena falsa: {caminho: {rotulo, classe, xyz, rotacao, escala}} e as sequências de teste."""

    def __init__(self, atores: dict | None = None, antigo: bool = False):
        self.atores = {c: dict(a) for c, a in (atores or {"/L.L:P.Mesa_1": MOVEL}).items()}
        self.seqs, self.k, self.antigo = set(), 100, antigo
        self.respostas: dict = {}   # ferramenta -> valor ou função(mundo, **k) que substitui a resposta normal
        self.ganchos: dict = {}     # ferramenta -> função(mundo) chamada ANTES da resposta normal
        self.chamadas: list = []

    def criar(self, rotulo: str, classe: str = "StaticMeshActor") -> dict:
        self.k += 1
        caminho = f"/L.L:P.{classe}_{self.k}"
        self.atores[caminho] = {"rotulo": rotulo, "classe": classe, "xyz": [20000.0, 0.0, 0.0],
                                "rotacao": [0.0, 0.0, 0.0], "escala": [1.0, 1.0, 1.0]}
        return {"refPath": caminho}

    def rotulos(self) -> list:
        return sorted(a["rotulo"] for a in self.atores.values())


class UnrealFalso(X.Unreal):
    def __init__(self, mundo: Mundo, trava: str):  # não chama o __init__ real (ele importa o cliente do Unreal)
        self.mundo = mundo
        cli = SimpleNamespace(call=self._call)
        self.M = SimpleNamespace(TRAVA=trava, _pilha={"n": 0}, RUN="777", cliente=lambda: cli,
                                 importar_clipe=lambda c: {"ok": True},
                                 aplicar_clipe=lambda *a, **k: mundo.criar("TESTE_ESTUDIO_777_PISO") and {"ok": True},
                                 limpar_estudio=self._limpar_estudio)
        tc = SimpleNamespace(ACTOR="actor", boneco=lambda rot, x, y: self._gancho("boneco") or mundo.criar(rot, "SkeletalMeshActor"),
                             teste_actors=lambda: [{"refPath": c} for c, a in mundo.atores.items()
                                                   if a["rotulo"].startswith("TESTE_")])
        self.V = SimpleNamespace(TC=tc, caixa=lambda rot, *a: self._gancho("caixa") or mundo.criar(rot))
        self.ASSET, self.SCENE, self.SEQ, self._nome = "asset", "scene", "seq", "DirectorTools"

    def _gancho(self, nome: str):
        g = self.mundo.ganchos.get(nome)
        if g:
            g(self.mundo)

    def _limpar_estudio(self):
        self._gancho("limpar_estudio")
        if "limpar_estudio" in self.mundo.respostas:
            return self.mundo.respostas["limpar_estudio"]
        for c in [c for c, a in self.mundo.atores.items() if a["rotulo"].startswith("TESTE_ESTUDIO_777_")]:
            del self.mundo.atores[c]
        return None  # contrato real: macros.limpar_estudio não devolve nada

    def _call(self, toolset: str, tool: str, **k):
        m = self.mundo
        m.chamadas.append(tool)
        self._gancho(tool)
        if tool in m.respostas:
            r = m.respostas[tool]
            return r(m, **k) if callable(r) else r
        if tool == "get_label":
            return m.atores[k["actor"]["refPath"]]["rotulo"]
        if tool == "remove_from_scene":
            m.atores.pop(k["actor"]["refPath"], None)
            return True
        if tool == "find_assets":
            return [s for s in m.seqs if k["name"] in s]
        return None

    def dt(self, f, **k):
        m = self.mundo
        m.chamadas.append(f)
        self._gancho(f)
        if f in m.respostas:
            r = m.respostas[f]
            return r(m, **k) if callable(r) else r
        if f == "list_actors":
            fora = ("rotacao", "escala") if m.antigo else ()
            itens = [dict({x: v for x, v in a.items() if x not in fora}, caminho=c) for c, a in m.atores.items()
                     if a["rotulo"].startswith(k.get("label_prefix", ""))]
            return {"ok": True, "total": len(itens), "atores": itens}
        if f == "bone_world_positions":
            return {"ossos": {n: [0.0, 0.0, 0.0] for n in k["bones"].split(",")}, "inexistentes": []}
        if f == "seq_build":
            m.seqs.add(SEQ)
            faixas = [{"clipe": f"c{i}", "de": i * 30, "ate": (i + 1) * 30, "avanco_cm": 0.0} for i in range(4)]
            return {"ok": True, "sequencia": SEQ, "faixas": faixas, "quadros": 120}
        if f == "seq_close_delete":
            m.seqs.discard(k["sequence_path"])
            return {"ok": True, "apagou": True}
        if f == "capture_isolated_restore":
            return {"ok": True, "restaurado": False, "motivo": "nada_ativo"}
        if f == "capture_isolated_shot":
            return {"ok": True, "arquivo": os.path.join(k["directory"], k["filename"])}
        return {"ok": True}


class BaseExecutor(unittest.TestCase):
    """Pasta da rodada, trava e biblioteca temporárias; X.Unreal trocado pelo falso."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="v006_")
        self.pasta = os.path.join(self.tmp, "rodada")
        os.makedirs(self.pasta)
        self.mundo = Mundo()
        trava = os.path.join(self.tmp, "unreal.trava")
        cwd = os.getcwd()
        for p in (patch.object(X, "PASTA", self.pasta), patch.object(X, "Unreal", lambda: UnrealFalso(self.mundo, trava)),
                  patch.dict(os.environ, {"BIBLIOTECA_PASTA": os.path.join(self.tmp, "bib")})):
            p.start()
            self.addCleanup(p.stop)
        os.environ.pop("FILA_CENA", None)
        self.addCleanup(os.chdir, cwd)
        self.trava = trava

    def rodar(self, n: int = 1, **k) -> dict:
        return X.executar(json.loads(json.dumps(RECEITA)), n, **k)

    def foto(self, n: int, fase: str) -> dict:
        return json.loads(Path(self.pasta, "evidencias", f"t{n:03d}-{fase}.json").read_text(encoding="utf-8"))


class L1Cena(BaseExecutor):
    def test_controle_cena_limpa_restaura_e_declara_alcance(self):
        r = self.rodar()
        self.assertIs(r["cena_ok"], True, r)
        self.assertEqual(self.mundo.rotulos(), ["Mesa"])  # só o que já existia; nada de TESTE_* sobrando
        self.assertFalse(self.mundo.seqs)
        self.assertEqual(r["cena_alcance"]["campos"], ["classe", "escala", "rotacao", "rotulo", "xyz"])
        self.assertFalse(r["cena_alcance"]["reduzido"])
        self.assertFalse(os.path.exists(self.trava))  # a trava (temporária) foi solta
        self.assertIsNone(X._estado()["pendente"])

    def test_a05_ator_antigo_de_mesmo_prefixo_e_preservado_e_a_execucao_recusada(self):
        self.mundo.atores["/L.L:P.Antigo_9"] = dict(MOVEL, rotulo=X.ATOR)
        self.mundo.atores["/L.L:P.Antigo_8"] = dict(MOVEL, rotulo="TESTE_FILA_OUTRA_COISA")
        r = self.rodar()
        self.assertIn("/L.L:P.Antigo_9", self.mundo.atores)  # preservado: prefixo não prova propriedade
        self.assertIn("/L.L:P.Antigo_8", self.mundo.atores)
        self.assertNotIn("remove_from_scene", self.mundo.chamadas)
        self.assertNotIn("seq_build", self.mundo.chamadas)   # recusou ANTES de montar qualquer coisa
        self.assertIs(r["cena_ok"], False)
        self.assertEqual(r["classe_erro"], "estado_parcial")
        self.assertIn("sem dono comprovado", r["motivo"])
        self.assertFalse(r["passou"])

    def test_a05_sobra_registrada_da_propria_queda_e_limpa_sem_redefinir_a_referencia(self):
        # modo legado: a tentativa 1 caiu depois de registrar o que criou; a 2 limpa SÓ o registrado
        self.mundo.atores["/L.L:P.Boneco_7"] = dict(MOVEL, rotulo=X.ATOR)
        self.mundo.atores["/L.L:P.Estudio_6"] = dict(MOVEL, rotulo="TESTE_ESTUDIO_4242_PISO")
        self.mundo.atores["/L.L:P.Estudio_5"] = dict(MOVEL, rotulo="TESTE_ESTUDIO_9999_PISO")  # de outra execução: não é nosso
        self.mundo.seqs.add("/Game/_AnimLab/Experimentos/SEQ_TESTE_9.SEQ_TESTE_9")
        X._gravar_estado({"proximo_n": 2, "fechadas": {}, "pendente": {
            "n": 1, "pid": 999999, "desde": "x", "run": "4242", "atores": ["/L.L:P.Boneco_7"],
            "seq": "/Game/_AnimLab/Experimentos/SEQ_TESTE_9.SEQ_TESTE_9"}})
        self.assertEqual(X.recuperar_pendente()["n"], 1)
        r = self.rodar(2)
        self.assertIs(r["cena_ok"], True, r)
        self.assertEqual(self.mundo.rotulos(), ["Mesa", "TESTE_ESTUDIO_9999_PISO"])
        # o boneco registrado e o estúdio do run registrado (4242); o estúdio 9999 não é desta rodada
        self.assertEqual(r["limpou_sobra_propria"]["atores"], ["/L.L:P.Boneco_7", "/L.L:P.Estudio_6"])
        self.assertIn("/L.L:P.Boneco_7", self.foto(2, "antes"))  # a fotografia inicial é a ORIGINAL, com a sobra
        e = X._estado()
        self.assertEqual((e["atores_para_limpar"], e["runs_para_limpar"], e["seqs_para_apagar"]), ([], [], []))

    def test_a05_sobra_registrada_mais_ator_alheio_bloqueia_sem_remover_nada(self):
        self.mundo.atores["/L.L:P.Boneco_7"] = dict(MOVEL, rotulo=X.ATOR)
        self.mundo.atores["/L.L:P.Alheio_3"] = dict(MOVEL, rotulo=X.PISO)
        X._gravar_estado({"proximo_n": 2, "fechadas": {}, "pendente": None, "atores_para_limpar": ["/L.L:P.Boneco_7"],
                          "runs_para_limpar": ["4242"], "seqs_para_apagar": []})
        r = self.rodar(2)
        self.assertIs(r["cena_ok"], False)
        self.assertEqual(len(self.mundo.atores), 3)
        self.assertEqual(X._estado()["atores_para_limpar"], ["/L.L:P.Boneco_7"])  # nada zerado sem limpeza confirmada

    def test_a06_rotulo_rotacao_ou_escala_alterados_reprovam_cena_ok(self):
        for campo, valor in (("rotulo", "Mesa_renomeada"), ("rotacao", [0.0, 90.0, 0.0]), ("escala", [1.0, 2.0, 1.0]),
                             ("xyz", [9.0, 2.0, 3.0])):
            with self.subTest(campo=campo):
                self.mundo = Mundo()
                self.mundo.ganchos["seq_build"] = lambda m, c=campo, v=valor: m.atores["/L.L:P.Mesa_1"].__setitem__(c, v)
                r = self.rodar(1)
                self.assertIs(r["cena_ok"], False, campo)
                self.assertEqual(r["cena_diferencas"]["alteraram"], ["/L.L:P.Mesa_1"])
                self.assertEqual(r["classe_erro"], "estado_parcial")
                self.assertEqual(self.foto(1, "antes")["/L.L:P.Mesa_1"][campo], MOVEL[campo])
                self.assertEqual(self.foto(1, "depois")["/L.L:P.Mesa_1"][campo], valor)  # A18: os valores ficam guardados
                for f in os.listdir(self.pasta):
                    p = os.path.join(self.pasta, f)
                    if os.path.isfile(p):
                        os.remove(p)

    def test_a06_toolset_antigo_sem_rotacao_roda_com_alcance_reduzido_declarado(self):
        self.mundo = Mundo(antigo=True)
        r = self.rodar()
        self.assertIs(r["cena_ok"], True, r)
        self.assertEqual(r["cena_alcance"]["campos"], ["classe", "rotulo", "xyz"])
        self.assertTrue(r["cena_alcance"]["reduzido"])
        self.assertIn("reload_toolset", r["cena_alcance"]["aviso"])

    def test_a07_retorno_negativo_ou_desconhecido_da_limpeza_nao_vira_limpeza_confirmada(self):
        casos = {"captura negativa": ("capture_isolated_restore", {"ok": False, "erros": ["rig: falhou"]}),
                 "captura com erros": ("capture_isolated_restore", {"ok": True, "erros": ["tick: x"]}),
                 "captura desconhecida": ("capture_isolated_restore", "qualquer texto"),
                 "remocao negativa": ("remove_from_scene", False),
                 "estudio nao limpou": ("limpar_estudio", None)}
        for nome, (ferramenta, resposta) in casos.items():
            with self.subTest(caso=nome):
                self.mundo = Mundo()
                self.mundo.respostas[ferramenta] = resposta
                r = self.rodar(1)
                self.assertIs(r["cena_ok"], False, nome)
                self.assertTrue(any(not p["ok"] for p in r["limpeza"]), r["limpeza"])
                self.assertEqual(r["classe_erro"], "estado_parcial")
                os.remove(os.path.join(self.pasta, "estado.json"))
                os.remove(os.path.join(self.pasta, "tentativas.jsonl"))

    def test_a07_excecao_na_limpeza_nao_impede_os_outros_passos(self):
        def estoura(m, **k):
            raise RuntimeError("editor não respondeu")
        self.mundo.respostas["capture_isolated_restore"] = estoura
        r = self.rodar()
        self.assertIs(r["cena_ok"], False)
        self.assertEqual([p["passo"] for p in r["limpeza"]], ["captura", "sequencia", "atores", "estudio"])
        self.assertEqual(self.mundo.rotulos(), ["Mesa"])  # os passos seguintes limparam o que era desta execução

    def test_a18_fotografia_inicial_gravada_antes_de_qualquer_mutacao(self):
        visto = {}
        self.mundo.ganchos["caixa"] = lambda m: visto.setdefault(
            "antes", os.path.exists(os.path.join(self.pasta, "evidencias", "t001-antes.json")))
        r = self.rodar()
        self.assertTrue(visto["antes"])
        self.assertEqual(sorted(self.foto(1, "antes")), ["/L.L:P.Mesa_1"])
        self.assertEqual(self.foto(1, "depois"), self.foto(1, "antes"))
        self.assertEqual(r["cena_fotos"], ["evidencias/t001-antes.json", "evidencias/t001-depois.json"])

    def test_a18_queda_depois_do_inicio_preserva_a_referencia_e_o_que_foi_criado(self):
        def cai(m):
            raise KeyboardInterrupt  # o processo morre depois de criar o piso e o boneco
        self.mundo.ganchos["set_pose_eval"] = cai
        with self.assertRaises(KeyboardInterrupt):
            self.rodar()
        self.assertEqual(sorted(self.foto(1, "antes")), ["/L.L:P.Mesa_1"])
        pend = X._estado()["pendente"]
        self.assertEqual(len(pend["atores"]), 2)  # piso e boneco registrados ANTES de seguir: a próxima sabe o que é dela

    def test_inventario_nao_confirmado_nao_toca_na_cena(self):
        self.mundo.respostas["list_actors"] = {"ok": False, "erro": "x"}
        r = self.rodar()
        self.assertIsNone(r["cena_ok"])
        self.assertEqual(r["classe_erro"], "infraestrutura")
        self.assertIn("inventário", r["motivo"])
        self.assertEqual(len(self.mundo.atores), 1)

    def test_sem_baseline_aceito_meus_atores_e_vazio(self):
        u = UnrealFalso(self.mundo, self.trava)
        self.mundo.criar(X.ATOR)
        self.assertEqual(u.meus_atores(), [])  # propriedade não comprovada: nada a remover


if __name__ == "__main__":
    unittest.main()
