"""Regressões L6 da v0.0.6: evidência, diário, biblioteca e vídeo (A17 A19 A20 A27, E4, F03 F04 F10, B1 B6).

Offline. O vídeo é por fixture (capturas e ffmpeg falsos): nenhum quadro real é gravado. A biblioteca usada é uma
pasta temporária, nunca a biblioteca real do repositório.
"""
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
import hashlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
import director_noite as N  # noqa: E402
import fila_executor as X  # noqa: E402
from unreal_macros import biblioteca as BIB, campanha as CP, diario, emperramento as E, fila as F  # noqa: E402
from unreal_macros import supervisor as S  # noqa: E402
from testes_v006_l1 import BaseExecutor  # noqa: E402
from testes_v006_l5 import Campanha  # noqa: E402


class Amostras(BaseExecutor):
    def _carregar(self, rel: str) -> list:
        return [(q, o) for q, o in json.loads(Path(self.pasta, rel).read_text(encoding="utf-8"))]

    def test_a17_tentativa_reprovada_guarda_as_amostras_e_da_para_recalcular_sem_unreal(self):
        r = self.rodar()
        self.assertGreater(r["nota"], 0)  # reprovada (as poses do Unreal falso não cumprem as intenções)
        self.assertEqual((r["amostras_arquivo"], r["amostras_completas"]), ("amostras/t001.json", True))
        am = self._carregar(r["amostras_arquivo"])
        self.assertEqual(len(am), r["amostras"])
        de_novo = F.avaliar(am, r["montagem"]["faixas"], [p["papel"] for p in r["receita"]], r["fps"])
        self.assertEqual(de_novo["nota"], r["nota"])

    def test_a17_excecao_na_avaliacao_nao_perde_as_amostras_ja_coletadas(self):
        def estoura(*a, **k):
            raise RuntimeError("avaliação quebrou")
        with patch.object(F, "avaliar", estoura):
            r = self.rodar()
        self.assertEqual(r["classe_erro"], "infraestrutura")
        self.assertTrue(r["amostras_completas"])
        self.assertGreater(len(self._carregar(r["amostras_arquivo"])), 10)

    def test_a17_conjunto_parcial_nunca_aparece_como_completo(self):
        vezes = {"n": 0}

        def cai_no_meio(m, **k):
            vezes["n"] += 1
            if vezes["n"] > 6:  # as primeiras leituras são do preparo; a queda é no meio da amostragem
                raise RuntimeError("editor parou de responder")
            return {"ossos": {n: [0.0, 0.0, 0.0] for n in k["bones"].split(",")}, "inexistentes": []}
        self.mundo.respostas["bone_world_positions"] = cai_no_meio
        r = self.rodar()
        self.assertIs(r["amostras_completas"], False)
        self.assertEqual(r["amostras_arquivo"], "amostras/t001-parcial.json")
        self.assertFalse(os.path.exists(os.path.join(self.pasta, "amostras", "t001.json")))
        self.assertEqual(len(self._carregar(r["amostras_arquivo"])), 5)


class Video(BaseExecutor):
    def setUp(self):
        super().setUp()
        self.ffmpeg = []
        falso = types.ModuleType("imageio_ffmpeg")
        falso.get_ffmpeg_exe = lambda: "ffmpeg-falso"
        for p in (patch.dict(sys.modules, {"imageio_ffmpeg": falso}),
                  patch.object(X.subprocess, "run", lambda cmd, **k: self.ffmpeg.append(cmd))):
            p.start()
            self.addCleanup(p.stop)

    def test_a27_controle_todas_as_capturas_dao_video_completo_com_a_contagem_esperada(self):
        r = self.rodar(video=True)
        self.assertEqual(len(self.ffmpeg), 1)
        v = r["video"]
        self.assertEqual((v["completo"], v["quadros"], v["esperados"], v["faltaram"]), (True, 60, 60, []))
        self.assertTrue(v["arquivo"].endswith("t001.mp4"))

    def test_a27_captura_intermediaria_que_falha_nao_vira_video_completo(self):
        vezes = {"n": 0}

        def captura(m, **k):
            vezes["n"] += 1
            if vezes["n"] == 3:  # a 3ª captura (quadro 4 da sequência) falha; as outras saem
                return {"ok": False, "erro": "arquivo_nao_gravado"}
            return {"ok": True, "arquivo": os.path.join(k["directory"], k["filename"])}
        self.mundo.respostas["capture_isolated_shot"] = captura
        r = self.rodar(video=True)
        self.assertEqual(self.ffmpeg, [])                      # nenhum mp4 com os quadros renumerados
        v = r["video"]
        self.assertEqual((v["completo"], v["arquivo"], v["faltaram"]), (False, None, [4]))
        self.assertEqual((v["quadros"], v["esperados"]), (59, 60))
        self.assertIs(r["passou"], False)                      # a entrega não está completa: não é aprovação
        self.assertIn("vídeo incompleto", r["motivo"])
        self.assertIs(r["cena_ok"], True)                      # a limpeza seguiu normal


class Relatorio(Campanha):
    def test_a19_linha_truncada_bloqueia_mas_nao_apaga_a_parte_legivel_do_relatorio(self):
        self.linha(n=1, nota=3.0)
        self.linha(n=2, nota=2.0)
        with (self.p / "tentativas.jsonl").open("a", encoding="utf-8") as f:
            f.write('{"tipo_linha": "tentativa", "n": 3, "nota": 1.')  # queda no meio da escrita
        antes = (self.p / "tentativas.jsonl").read_bytes()
        self.assertTrue(CP.guarda(self.p)[0].startswith("estado_inseguro"))  # operar continua bloqueado
        s = N.estado(self.p)
        self.assertEqual(s["situacao"], "estado_inseguro")
        self.assertEqual(s["tentativas"], 2)                     # os registros anteriores aparecem
        self.assertEqual(s["melhor"]["n"], 2)
        self.assertEqual(s["historico_corrompido"]["linhas_ilegiveis"], [3])
        self.assertFalse(s["sucesso_medido"])
        rel = json.loads(Path(N.relatorio(self.p)["json"]).read_text(encoding="utf-8"))
        self.assertEqual([t["n"] for t in rel["historico"]], [1, 2])
        self.assertIn("HISTÓRICO CORROMPIDO", (self.p / "RELATORIO.md").read_text(encoding="utf-8"))
        self.assertEqual((self.p / "tentativas.jsonl").read_bytes(), antes)  # o arquivo original é preservado

    def test_a19_historico_integro_nao_ganha_aviso(self):
        self.linha(n=1, nota=3.0)
        self.assertNotIn("historico_corrompido", N.estado(self.p))


class Hipoteses(Campanha):
    MODO = "experimental"
    H = {"id": "H1", "hipotese": "o giro antes do andar reduz o salto", "funcionalidade": "turn_deg",
         "proximo_teste": "turn_deg 15"}

    def test_a20_hipotese_com_tentativa_nao_muda_de_identidade_sob_o_mesmo_id(self):
        N.planejar(self.p, [dict(self.H)])
        N.planejar(self.p, [dict(self.H, hipotese="texto corrigido antes de executar")])  # sem tentativa: pode
        self.linha(n=1, experimento="H1")
        for campo in ("hipotese", "funcionalidade"):
            mudada = dict(self.H, hipotese="texto corrigido antes de executar")
            mudada[campo] = "outra coisa"
            with self.subTest(campo=campo), self.assertRaisesRegex(ValueError, "já tem tentativa"):
                N.planejar(self.p, [mudada])
        lab = N.planejar(self.p, [dict(self.H, hipotese="texto corrigido antes de executar", proximo_teste="turn_deg 30"),
                                  {"id": "H2", "hipotese": "outra", "funcionalidade": "corte_fim_q", "proximo_teste": "x"}])
        self.assertEqual([h["id"] for h in lab["fila"]], ["H1", "H2"])  # próximo teste e hipótese nova: pode
        self.assertEqual(lab["fila"][0]["funcionalidade"], "turn_deg")


def _bloco(videos, **cond) -> dict:
    c = dict(BIB.condicoes_atuais(), **cond)
    return {"id": "abc123", "fonte": "rodada", "receita": [], "tentativas": [1, 2, 3], "amostras": [], "notas": [0, 0, 0],
            "condicoes": c, "videos": list(videos), "quando": "2026-10-11T10:00:00"}


class Biblioteca(unittest.TestCase):
    def test_e4_reimportar_o_bloco_sem_video_nao_apaga_o_link_ja_gravado(self):
        with tempfile.TemporaryDirectory() as bib:
            BIB.mesclar(bib, {"blocos": [_bloco(["work/r/videos/t001.mp4"])]})
            BIB.mesclar(bib, {"blocos": [_bloco([])]})  # a mesma rodada reimportada, agora sem os mp4 no disco
            self.assertEqual(BIB.carregar(bib)["blocos"]["abc123"]["videos"], ["work/r/videos/t001.mp4"])
            BIB.mesclar(bib, {"blocos": [_bloco(["work/r/videos/t002.mp4"])]})
            self.assertEqual(BIB.carregar(bib)["blocos"]["abc123"]["videos"],
                             ["work/r/videos/t001.mp4", "work/r/videos/t002.mp4"])
            self.assertEqual(len(BIB.carregar(bib)["blocos"]), 1)  # idempotente: continua um bloco só

    def test_e4_bloco_medido_em_outras_condicoes_nao_herda_a_prova_antiga(self):
        with tempfile.TemporaryDirectory() as bib:
            BIB.mesclar(bib, {"blocos": [_bloco(["work/r/videos/t001.mp4"])]})
            BIB.mesclar(bib, {"blocos": [_bloco([], escala=1.2)]})
            self.assertEqual(BIB.carregar(bib)["blocos"]["abc123"]["videos"], [])


REL_DOIS = {"ok": False, "id": "20261011-100000-abc", "segundos": 9.0, "chamadas": 30, "bloqueio": "nenhum clipe passou para B",
            "medidas": {"atores": [
                {"ator": "A", "clipe": "Talking", "tentativas": [{"gates": [{"nome": "deriva_xy", "resultado": "PASS", "valor": 3.0}]}]},
                {"ator": "B", "clipe": None, "tentativas": [{"gates": [{"nome": "deriva_xy", "resultado": "FAIL", "valor": 22.0}]}]}]}}


class Diario(unittest.TestCase):
    def test_f04_os_gates_sao_os_do_ator_nomeado_e_nao_os_do_primeiro(self):
        a = diario.linha_do_relatorio(REL_DOIS, macro="plateia_em_loop", ator="A")
        b = diario.linha_do_relatorio(REL_DOIS, macro="plateia_em_loop", ator="B")
        self.assertEqual(a["gates"], {"deriva_xy": "PASS (3.0)"})
        self.assertEqual(b["gates"], {"deriva_xy": "FAIL (22.0)"})  # B não herda os gates de A
        c = diario.linha_do_relatorio(REL_DOIS, macro="plateia_em_loop", ator="C")
        self.assertNotIn("gates", c)
        self.assertEqual(c["aviso"], "ator 'C' não está no relatório: gates não registrados")

    def test_f03_extra_nao_substitui_os_campos_que_vem_do_relatorio(self):
        linha = diario.linha_do_relatorio(REL_DOIS, macro="plateia_em_loop", ator="A", fonte="colado",
                                          extra={"ok": True, "relatorio_id": "outro", "fonte": "relatorio_id", "gates": {},
                                                 "observacao": "campo inocente"})
        self.assertIs(linha["ok"], False)
        self.assertEqual((linha["relatorio_id"], linha["fonte"]), ("20261011-100000-abc", "colado"))
        self.assertEqual(linha["gates"], {"deriva_xy": "PASS (3.0)"})
        self.assertEqual(linha["observacao"], "campo inocente")  # extra que não colide passa
        self.assertEqual(linha["extra_recusado"], ["fonte", "gates", "ok", "relatorio_id"])

    def test_f10_linha_corrompida_no_indice_nao_esconde_o_relatorio_valido_e_fica_sinalizada(self):
        with tempfile.TemporaryDirectory() as tmp:
            arquivo = Path(tmp, "relatorios_arquivo")
            arquivo.mkdir()
            for rid in ("20261011-100000-aaa", "20261011-100500-bbb"):
                (arquivo / f"{rid}.json").write_text(json.dumps({"id": rid, "ok": True}), encoding="utf-8")
            (arquivo / "indice.jsonl").write_text(
                json.dumps({"id": "20261011-100000-aaa", "arquivo": "20261011-100000-aaa.json"}) + "\n"
                + '{"id": "20261011-1002' + "\n"  # linha cortada no meio
                + json.dumps({"id": "20261011-100500-bbb", "arquivo": "20261011-100500-bbb.json"}) + "\n", encoding="utf-8")
            with patch.object(diario, "PASTA_RELATORIOS", os.path.join(tmp, "relatorios")):
                self.assertEqual(diario.carregar_relatorio("20261011-100000-aaa")["id"], "20261011-100000-aaa")
                depois = diario.carregar_relatorio("20261011-100500-bbb")  # está DEPOIS da linha ruim
                self.assertEqual(depois["id"], "20261011-100500-bbb")
                self.assertIn("1 linha", depois["aviso_indice"])
                with self.assertRaisesRegex(FileNotFoundError, "ilegíve"):
                    diario.carregar_relatorio("20261011-109999-zzz")


class Supervisor(unittest.TestCase):
    EV = [{"experimento": "x1", "evento": "iniciado", "quando": "2026-10-11T10:00:00"},
          {"experimento": "x1", "evento": "corrida", "n": 1, "script": "a.py", "codigo_saida": 1, "quando": "2026-10-11T10:01:00"}]

    def _pastas(self, tmp: str) -> tuple:
        rel, exp = os.path.join(tmp, "relatorios"), os.path.join(tmp, "exp")
        os.makedirs(rel)
        os.makedirs(exp)
        Path(exp, "eventos.jsonl").write_text(json.dumps(self.EV[0]) + "\n" + '{"experimento": "x1", "even' + "\n"
                                              + json.dumps(self.EV[1]) + "\n", encoding="utf-8")
        return rel, exp

    def test_b1_linha_truncada_avisa_e_mostra_a_parte_integra(self):
        with tempfile.TemporaryDirectory() as tmp:
            rel, exp = self._pastas(tmp)
            itens = E.carregar_historico(rel, exp)
            self.assertEqual([t["tipo"] for t in itens if t["tipo"] != "incompleta"], ["iniciado", "tentativa"])
            ruins = [t for t in itens if t["tipo"] == "incompleta"]
            self.assertEqual((len(ruins), ruins[0]["falta"]), (1, ["json"]))
            r = S.avaliar(1_800_000_000.0, pasta_rel=rel, pasta_exp=exp, trava_path=os.path.join(tmp, "sem.trava"),
                          pasta_sup=os.path.join(tmp, "sup"))
            corrompido = [a for a in r["alarmes"] if a["tipo"] == "registro_corrompido"]
            self.assertEqual(len(corrompido), 1)  # o supervisor não cai e não finge que está tudo certo
            self.assertIn("eventos.jsonl", corrompido[0]["evidencia"][0])
            Path(tmp, "sup", "alarmes.jsonl").open("a", encoding="utf-8").write('{"chave": "cort')
            S.avaliar(1_800_000_000.0, pasta_rel=rel, pasta_exp=exp, trava_path=os.path.join(tmp, "sem.trava"),
                      pasta_sup=os.path.join(tmp, "sup"))  # registro de alarmes truncado também não derruba

    def _producao(self, tmp: str) -> tuple:
        base = os.path.join(tmp, "producao")
        os.makedirs(os.path.join(base, "src"))
        Path(base, "src", "a.py").write_bytes(b"print('a')\n")
        Path(base, "b.txt").write_bytes(b"b\n")
        hashes = os.path.join(tmp, "hashes.sha256")
        Path(hashes).write_text("".join(f"{hashlib.sha256(Path(base, p).read_bytes()).hexdigest()}  {p}\n"
                                        for p in ("src/a.py", "b.txt")), encoding="utf-8")
        return base, hashes

    def test_b6_alarme_de_producao_alterada_nao_depende_do_sha256sum_no_path(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PATH": tmp}):  # PATH sem sha256sum
            base, hashes = self._producao(tmp)
            self.assertEqual(S._violacoes([], hashes, base, None, None), [])  # hash correto: sem alarme
            Path(base, "src", "a.py").write_bytes(b"print('alterado')\n")
            v = S._violacoes([], hashes, base, None, None)
            self.assertEqual([x["tipo"] for x in v], ["producao_alterada"])
            self.assertIn("src/a.py", v[0]["evidencia"][0])
            os.remove(os.path.join(base, "b.txt"))  # arquivo que sumiu também é alteração
            self.assertEqual(len(S._violacoes([], hashes, base, None, None)[0]["evidencia"]), 2)


if __name__ == "__main__":
    unittest.main()
