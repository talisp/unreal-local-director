"""Regressões L5 da v0.0.6: supervisão, prazo e encerramento (A21 A22 A23 A24 A25 A26 A29 + N1).

Offline: campanhas em pasta temporária, relógio e processos por fixture, trava em arquivo temporário (nunca a real).
Nenhuma sessão do Hermes, nenhum modelo e nenhum Unreal são chamados; não certifica a autonomia do Qwen.
"""
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
import contextlib
import datetime as dt
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
import director_noite as N  # noqa: E402
import fila_executor as X  # noqa: E402
import vigia_dev as V  # noqa: E402
from unreal_macros import campanha as CP, fila as F, processos as P, receita as R  # noqa: E402
from testes_director_noite import plano, SCRATCH  # noqa: E402
from testes_v006_l1 import Mundo, UnrealFalso  # noqa: E402
from testes_v006_l2 import _morto  # noqa: E402


class Campanha(unittest.TestCase):
    MODO = "formal"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=SCRATCH)
        self.addCleanup(self.tmp.cleanup)
        self.c, self.p = self.nova(self.MODO)
        self.r = {"linhagem": "A", "tipo": "exploracao", "hipotese": "fixture, não execução real",
                  "passos": [{"papel": papel, "clipe": "fixture_" + papel} for papel in F.PAPEIS]}

    def nova(self, modo: str = "formal", objetivo: str = "objetivo de fixture") -> tuple:
        pl = plano()
        if modo == "experimental":
            pl["modo"] = "experimental"
        c = N.preparar(objetivo, pl, 1, base=Path(self.tmp.name))
        p = Path(c["pasta"])
        CP.gravar(p, "AUTORIZACAO.json", {"id": c["id"], "integridade": c["integridade"]})
        return c, p

    def linha(self, p=None, **kw):
        d = dict(n=1, tipo_linha="tentativa", linhagem="A", tipo="exploracao", nota=1.0, receita=self.r["passos"],
                 assinatura=R.assinatura(self.r), avaliacao={"valida": True}, cena_ok=True)
        d.update(kw)
        with ((p or self.p) / "tentativas.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(d) + "\n")
        return d

    def foto(self, p=None) -> dict:
        p = p or self.p
        return {str(a.relative_to(p)): a.read_bytes() for a in sorted(p.rglob("*")) if a.is_file()}


class Termino(Campanha):
    def test_a21_ensaio_md_nao_encerra_campanha_experimental(self):
        c, p = self.nova("experimental")
        (p / "ENSAIO.md").write_text("relatório de ensaio", encoding="utf-8")
        self.assertFalse(CP.encerrada(p))
        self.assertFalse(V.ler_rodada(str(p))["terminou"])
        CP.gravar(p, "ENCERRAMENTO.json", {"id": c["id"], "integridade": c["integridade"], "motivo": "prazo",
                                          "justificativa": "x", "quando": dt.datetime.now().isoformat()})
        self.assertTrue(V.ler_rodada(str(p))["terminou"])  # o encerramento válido é reconhecido

    def test_a21_linha_fechamento_ou_ensaio_md_nao_encerram_campanha_formal(self):
        self.linha(tipo_linha="fechamento", n=None)
        (self.p / "ENSAIO.md").write_text("x", encoding="utf-8")
        self.assertFalse(CP.encerrada(self.p))
        self.assertFalse(V.ler_rodada(str(self.p))["terminou"])
        (self.p / "FECHAMENTO.md").write_text("fechamento formal", encoding="utf-8")
        self.assertTrue(V.ler_rodada(str(self.p))["terminou"])

    def test_a21_marcadores_legados_continuam_valendo_fora_de_campanha(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "ENSAIO.md").write_text("x", encoding="utf-8")
            self.assertTrue(V.ler_rodada(d)["terminou"])
        with tempfile.TemporaryDirectory() as d:
            Path(d, "tentativas.jsonl").write_text(json.dumps({"tipo_linha": "fechamento"}) + "\n", encoding="utf-8")
            self.assertTrue(V.ler_rodada(d)["terminou"])


class Decisao(unittest.TestCase):
    def obs(self, melhor=None, tentativas=0, trava="livre", pendente=None, bloqueios=(), motivo="max_iterations (60)"):
        return {"log": {"turno_ativo": False, "motivo_fim": motivo, "sessao": "S1"},
                "rodada": {"terminou": False, "pendente": pendente, "melhor_nota": melhor, "tentativas": tentativas,
                           "inseguro": False, "ultimo_especial": None},
                "saude": {"trava": trava, "trava_motivo": f"fixture: {trava}", "modelo": True, "unreal": True,
                          "sessao_processo": P.MORTO},
                "campanha": {"fim_ts": time.time() + 3600}, "bloqueios_campanha": list(bloqueios), "pausa": False}

    def decidir(self, mem, **kw):
        return V.decidir(self.obs(**kw), mem, time.time(), dict(V.LIM))

    def test_a22_melhora_medida_entre_duas_ocorrencias_da_mesma_causa_nao_obriga_a_mudar(self):
        mem = {"causas": ["limite"], "melhor": 5.0}
        d = self.decidir(mem, melhor=3.0, tentativas=4)  # a nota melhorou depois da 1ª parada por "limite"
        self.assertEqual(d["acoes"], ["relancar"], d)
        self.assertEqual((mem["causas"], mem["melhor"]), ([], 3.0))

    def test_a22_sem_melhora_a_mesma_causa_ainda_manda_mudar(self):
        d = self.decidir({"causas": ["limite"], "melhor": 5.0}, melhor=5.0, tentativas=4)
        self.assertEqual(d["acoes"], ["relancar_mudando"], d)
        # mais linhas sem nota melhor NÃO são progresso
        d = self.decidir({"causas": ["limite"], "melhor": 5.0}, melhor=5.0, tentativas=40)
        self.assertEqual(d["acoes"], ["relancar_mudando"], d)

    def test_a23_trava_orfa_comprovada_e_segura_tem_recuperacao_e_nao_espera_ate_o_prazo(self):
        d = self.decidir({}, trava="morta")
        self.assertEqual((d["estado"], d["acoes"]), ("trava_orfa", ["liberar_trava"]), d)

    def test_a23_dono_vivo_desconhecido_pendencia_ou_inseguranca_nunca_liberam(self):
        for nome, kw in (("viva", {"trava": "viva"}), ("indisponível", {"trava": "indisponivel"}),
                         ("corrompida", {"trava": "corrompida"}), ("execução pendente", {"trava": "morta", "pendente": {"n": 1}}),
                         ("estado parcial", {"trava": "morta", "bloqueios": ["estado_inseguro: fixture"]})):
            with self.subTest(caso=nome):
                d = self.decidir({}, **kw)
                self.assertNotIn("liberar_trava", d["acoes"], d)
                self.assertNotEqual(d["estado"], "parou")
        d = self.decidir({}, trava="corrompida")
        self.assertEqual(d["estado"], "trava_corrompida")  # bloqueio explícito, com motivo: não é espera muda
        self.assertTrue(d["causa"])

    def test_a23_a_liberacao_e_a_da_trava_py_e_so_tira_dono_morto(self):
        with tempfile.TemporaryDirectory() as tmp:
            trava = os.path.join(tmp, "unreal.trava")  # trava TEMPORÁRIA do teste
            args = SimpleNamespace(seco=False, rodada=tmp, pedido="x")
            obs = {"rodada": {"inseguro": False, "ultimo_especial": None}}
            with patch.object(V, "TRAVA", trava), patch.object(V, "PASTA", tmp):
                Path(trava).write_text(json.dumps({"pid": _morto(), "inicio": 1.0, "nonce": "a"}), encoding="utf-8")
                r = V.executar({"acoes": ["liberar_trava"], "causa": None}, obs, {}, args)
                self.assertEqual(r[0]["resultado"], True)
                self.assertFalse(os.path.exists(trava))
                Path(trava).write_text(json.dumps({"pid": os.getppid(), "inicio": None, "nonce": "b"}), encoding="utf-8")
                r = V.executar({"acoes": ["liberar_trava"], "causa": None}, obs, {}, args)
                self.assertEqual(r[0]["resultado"], False)
                self.assertTrue(os.path.exists(trava))


class Retomada(Campanha):
    def _vigia_morta_com_sessao(self, p, cid, pid):
        CP.gravar(p, "LANCAMENTO.json", {"vigia_pid": 999999})
        (p / "vigia").mkdir(exist_ok=True)
        CP.gravar(p / "vigia", "memoria.json", {"campanha": cid, "sessao_pid": pid})

    def test_a24_vigia_morta_com_a_sessao_propria_viva_retoma_so_o_observador(self):
        self._vigia_morta_com_sessao(self.p, self.c["id"], os.getpid())
        with patch.object(N.L2.subprocess, "Popen") as popen, patch.object(N, "ambiente", return_value=[]):
            popen.return_value.pid = 4242
            info = N.iniciar(self.p, autorizado=True, continuar=True)
        self.assertEqual(popen.call_count, 1)                 # um processo só: a vigia
        cmd = popen.call_args.args[0]
        self.assertIn("vigia_dev.py", " ".join(cmd))
        self.assertNotIn("chat", cmd)                          # nenhum Hermes novo
        self.assertEqual(info["vigia_pid"], 4242)
        mem = json.loads((self.p / "vigia/memoria.json").read_text(encoding="utf-8"))
        self.assertEqual(mem["sessao_pid"], os.getpid())       # a memória da sessão viva é preservada
        eventos = (self.p / "eventos.jsonl").read_text(encoding="utf-8")
        self.assertIn("retomada_da_vigia", eventos)

    def test_a24_sessao_de_identidade_desconhecida_ou_de_outra_campanha_continua_bloqueando(self):
        self._vigia_morta_com_sessao(self.p, self.c["id"], os.getpid())
        with patch.object(N.L2, "lancar") as lancar, patch.object(N, "ambiente", return_value=[]):
            with patch.object(P, "estado_processo", side_effect=lambda pid: P.DESCONHECIDO if pid == os.getpid() else P.MORTO):
                with self.assertRaisesRegex(ValueError, "desconhecida"):
                    N.iniciar(self.p, autorizado=True, continuar=True)
            outra_c, outra_p = self.nova(objetivo="outra campanha")
            self._vigia_morta_com_sessao(outra_p, outra_c["id"], os.getpid())
            (self.p / "vigia/memoria.json").unlink()
            with self.assertRaisesRegex(ValueError, "outra campanha"):
                N.iniciar(self.p, autorizado=True, continuar=True)
            self.assertFalse(lancar.called)


class Seco(Campanha):
    def test_a25_modo_seco_so_olha_nao_muda_nenhum_arquivo_da_campanha(self):
        self.linha()
        (self.p / "vigia").mkdir()
        CP.gravar(self.p / "vigia", "memoria.json", {"campanha": self.c["id"], "sessoes": []})
        (self.p / "RELATORIO.md").write_text("relatório oficial anterior", encoding="utf-8")
        antes = self.foto()
        argv = ["vigia_dev.py", "--campanha", self.c["id"], "--rodada", str(self.p), "--pedido", str(self.p / "PEDIDO.md"),
                "--perfil", N.L2.PERFIL, "--seco", "--uma-vez"]
        saude = {"modelo": True, "unreal": True, "trava": "livre", "scripts_da_rodada": 0}
        saida = io.StringIO()
        with patch.object(sys, "argv", argv), patch.object(V, "saude", return_value=saude), \
                patch.object(N, "perfil_local", return_value=True), patch.object(V.subprocess, "Popen") as popen, \
                patch.object(V.subprocess, "run") as run, \
                patch.object(V, "PREFIXO", V.PREFIXO), patch.object(V, "PASTA", V.PASTA), patch.object(V, "PERFIL", V.PERFIL), \
                patch.object(V, "LOG_DEV", str(self.p / "sem-log")), patch.object(V, "LIM", dict(V.LIM)), \
                patch.object(V, "SECO", False, create=True), contextlib.redirect_stdout(saida):
            self.assertEqual(V.main(), 0)
        self.assertEqual(self.foto(), antes)          # nem log, nem resumo, nem relatório, nem memória, nem trava
        self.assertFalse(popen.called or run.called)  # nenhuma chamada externa de execução
        self.assertIn('"estado"', saida.getvalue())   # a observação sai na saída padrão


class Prazo(Campanha):
    def test_a26_campanha_usa_so_o_prazo_absoluto_do_manifesto(self):
        # o relógio legado (HH:MM do CENA.md, contado do início da rodada) já "fechou"; o absoluto ainda não
        CP.gravar(self.p, "estado.json", {"proximo_n": 1, "pendente": None, "fechadas": {},
                                         "inicio_rodada": "2026-10-01T00:00:00"})
        with patch.object(X, "PASTA", str(self.p)), patch.dict(os.environ, {"FILA_CENA": str(self.p / "CENA.md")}):
            self.assertTrue(X.depois_da_hora())  # o legado diria "passou do prazo"
            _, motivos = X.preparar(json.loads(json.dumps(self.r)))
            self.assertFalse(any("prazo" in m for m in motivos), motivos)
            self.assertIs(X.estado_resumo()["depois_do_prazo"], False)
            limite = self.c["prazo_tentativas_ts"]
            with patch.object(time, "time", return_value=limite - 0.001):
                self.assertFalse(any("prazo" in m for m in X.preparar(json.loads(json.dumps(self.r)))[1]))
            with patch.object(time, "time", return_value=limite):  # a fronteira é exatamente a do manifesto
                motivos = X.preparar(json.loads(json.dumps(self.r)))[1]
                self.assertTrue(any("prazo absoluto" in m for m in motivos), motivos)
                self.assertIs(X.estado_resumo()["depois_do_prazo"], True)

    def test_a26_rodada_legada_continua_com_o_prazo_por_horario(self):
        with tempfile.TemporaryDirectory() as d, patch.object(X, "PASTA", d):
            os.environ.pop("FILA_CENA", None)
            X._gravar_estado({"proximo_n": 1, "pendente": None, "fechadas": {}, "inicio_rodada": "2026-10-01T00:00:00"})
            _, motivos = X.preparar({"linhagem": "A", "tipo": "exploracao", "passos": [
                {"clipe": "Sit_To_Stand", "papel": "levantar"}, {"clipe": "Waving", "papel": "acenar"},
                {"clipe": "Start_Walking", "papel": "andar"}, {"clipe": "Stop_Walking_2", "papel": "parar"}]})
            self.assertTrue(any("passou do prazo da rodada" in m for m in motivos), motivos)


class Encerramento(Campanha):
    def test_a29_encerrar_com_tentativa_em_curso_da_relatorio_provisorio_e_o_final_inclui_o_resultado(self):
        self.linha(tipo_linha="tentativa_inicio", n=1, execucao="e1")
        CP.gravar(self.p, "estado.json", {"proximo_n": 2, "fechadas": {},
                                         "pendente": {"n": 1, "pid": os.getpid(), "execucao": "e1"}})
        N.controlar(self.p, "encerrar")
        rel = json.loads((self.p / "RELATORIO.json").read_text(encoding="utf-8"))
        self.assertIs(rel["provisorio"], True)
        self.assertEqual(rel["tentativas"], 0)
        self.assertIn("PROVISÓRIO", (self.p / "RELATORIO.md").read_text(encoding="utf-8"))
        self.assertTrue(any("encerrada" in m for m in CP.guarda(self.p)))  # nenhuma tentativa nova é admitida
        # a tentativa que já estava autorizada termina a limpeza normal e grava o resultado
        self.linha(n=1, execucao="e1", nota=2.0)
        CP.gravar(self.p, "estado.json", {"proximo_n": 2, "fechadas": {}, "pendente": None})
        with patch.object(X, "PASTA", str(self.p)):
            X._relatorio_final_se_encerrada()
        rel = json.loads((self.p / "RELATORIO.json").read_text(encoding="utf-8"))
        self.assertIs(rel["provisorio"], False)
        self.assertEqual((rel["tentativas"], rel["evolucao"][0]["nota"]), (1, 2.0))
        self.assertNotIn("PROVISÓRIO", (self.p / "RELATORIO.md").read_text(encoding="utf-8"))

    def test_a29_o_executor_refaz_o_relatorio_quando_a_campanha_foi_encerrada_durante_a_tentativa(self):
        mundo = Mundo()
        mundo.ganchos["seq_build"] = lambda m: N.controlar(self.p, "encerrar")  # o operador encerra NO MEIO da tentativa
        trava = os.path.join(self.tmp.name, "unreal.trava")
        with patch.object(X, "PASTA", str(self.p)), patch.object(X, "Unreal", lambda: UnrealFalso(mundo, trava)), \
                patch.dict(os.environ, {"FILA_CENA": str(self.p / "CENA.md"), "BIBLIOTECA_PASTA": os.path.join(self.tmp.name, "bib")}):
            cwd = os.getcwd()
            try:
                r = X.executar(json.loads(json.dumps(self.r)), 1)
            finally:
                os.chdir(cwd)
        self.assertIs(r["cena_ok"], True, r)               # a limpeza em curso foi preservada
        rel = json.loads((self.p / "RELATORIO.json").read_text(encoding="utf-8"))
        self.assertIs(rel["provisorio"], False)
        self.assertEqual(rel["tentativas"], 1)              # o relatório final inclui a tentativa que estava em curso
        self.assertIsNone(rel["pendente"])

    def test_a29_campanha_aberta_nao_ganha_relatorio_por_causa_do_executor(self):
        with patch.object(X, "PASTA", str(self.p)):
            X._relatorio_final_se_encerrada()
        self.assertFalse((self.p / "RELATORIO.json").exists())


class Duracao(Campanha):
    MODO = "experimental"

    def test_n1_duracao_decorrida_para_de_contar_no_encerramento(self):
        inicio = dt.datetime.fromisoformat(self.c["inicio"]).timestamp()
        with patch.object(time, "time", return_value=inicio + 50):
            self.assertAlmostEqual(N.estado(self.p)["duracao_decorrida_s"], 50, delta=1)  # aberta: conta até agora
        fim = dt.datetime.fromtimestamp(inicio + 120).astimezone().isoformat()
        CP.gravar(self.p, "ENCERRAMENTO.json", {"id": self.c["id"], "integridade": self.c["integridade"],
                                               "motivo": "prazo", "justificativa": "x", "quando": fim})
        with patch.object(time, "time", return_value=inicio + 12557):  # relatório reemitido horas depois
            self.assertAlmostEqual(N.estado(self.p)["duracao_decorrida_s"], 120, delta=1)


if __name__ == "__main__":
    unittest.main()
