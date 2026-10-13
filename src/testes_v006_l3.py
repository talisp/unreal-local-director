"""Regressões L3 da v0.0.6: um único significado de sucesso (A08 A09 A10 A11, F02; F09 converge).

Tudo offline: executor com o Unreal falso de testes_v006_l1; campanhas e rodadas em pastas temporárias.
A medida (nota) é preservada; a APROVAÇÃO operacional (passou) só vale com cena segura e sem falha posterior.
"""
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
import director_noite as N  # noqa: E402
import fila_executor as X  # noqa: E402
import rotina as RO  # noqa: E402
from unreal_macros import biblioteca as BIB, campanha as CP, fila as F, receita as R  # noqa: E402
from testes_director_noite import plano, SCRATCH  # noqa: E402
from testes_v006_l1 import BaseExecutor, RECEITA  # noqa: E402

ASSIN = R.assinatura(RECEITA)
VERSOES = {"regua": "r1", "executor": "e1", "toolset": "t1"}


def zero(n: int, **kw) -> dict:
    """Uma linha final como a do executor: medida nota 0, cena restaurada, aprovada."""
    d = {"tipo_linha": "tentativa", "n": n, "execucao": f"exec-{n}", "linhagem": "A", "tipo": "exploracao", "nota": 0.0,
         "passou": True, "cena_ok": True, "classe_erro": None, "receita": RECEITA["passos"], "assinatura": ASSIN,
         "versoes": dict(VERSOES), "fps": 30, "condicoes": dict(X.CONDICOES), "quando": f"2026-10-11T10:0{n}:00",
         "avaliacao": {"valida": True, "nota": 0.0, "duracao_s": 4.0, "intencoes": {p: {"passou": True} for p in F.PAPEIS}},
         "montagem": {"faixas": []}}
    d.update(kw)
    return d


class Sucesso(unittest.TestCase):
    def test_controle_tres_tentativas_distintas_e_compativeis_passam(self):
        ts = [zero(1), zero(2), zero(3)]
        self.assertEqual(F.sucesso(ts), {"assinatura": ASSIN, "vezes": 3})
        self.assertEqual(CP.sucesso_seguro(ts), {"assinatura": ASSIN, "vezes": 3})

    def test_a10_uma_tentativa_triplicada_nao_vale_tres(self):
        ts = [zero(1), zero(1), zero(1)]
        self.assertIsNone(F.sucesso(ts))
        self.assertIsNone(CP.sucesso_seguro(ts))
        self.assertIsNone(F.sucesso([zero(1), zero(1), zero(2)]))  # 2 distintas não são 3

    def test_a10_duplicata_conflitante_invalida_a_apuracao(self):
        ts = [zero(1), zero(1, quando="outro conteúdo, mesmo número"), zero(2), zero(3)]
        self.assertIsNone(F.sucesso(ts))
        self.assertIsNone(CP.sucesso_seguro(ts))

    def test_a09_versao_ou_condicao_divergente_nao_soma(self):
        self.assertIsNone(F.sucesso([zero(1), zero(2), zero(3, versoes=dict(VERSOES, regua="r2"))]))
        self.assertIsNone(F.sucesso([zero(1), zero(2), zero(3, condicoes=dict(X.CONDICOES, escala=1.2))]))
        self.assertIsNone(F.sucesso([zero(1), zero(2), zero(3, fps=24)]))

    def test_a09_restauracao_ou_aprovacao_negada_nao_conta(self):
        for nome, ruim in (("cena", {"cena_ok": False}), ("aprovação", {"passou": False}),
                           ("avaliação", {"avaliacao": {"valida": False}}), ("nota booleana", {"nota": False})):
            with self.subTest(caso=nome):
                self.assertIsNone(F.sucesso([zero(1), zero(2), zero(3, **ruim)]))
                self.assertIsNone(CP.sucesso_seguro([zero(1), zero(2), zero(3, **ruim)]))


def _avaliacao_zero(amostras, faixas, papeis, fps):
    return {"valida": True, "nota": 0.0, "regua": "fixture", "duracao_s": 4.0,
            "intencoes": {p: {"passou": True} for p in F.PAPEIS},
            "trocas": [{"troca": i, "valida": True, "quadros": [0, 1], "quadril_cm": 0.0, "pior_osso": "Hips",
                        "pior_osso_cm": 0.0, "virada_deg": 0.0, "nota": 0.0, "ossos_antes": {}, "ossos_depois": {}}
                       for i in range(len(faixas) - 1)]}


class Executor(BaseExecutor):
    def setUp(self):
        super().setUp()
        self.biblioteca = []
        for p in (patch.object(F, "avaliar", _avaliacao_zero),
                  patch.object(X, "registrar_na_biblioteca", lambda *a, **k: self.biblioteca.append(1) or {"ok": True}),
                  patch.object(X, "depois_da_hora", lambda *a, **k: False)):
            p.start()
            self.addCleanup(p.stop)

    def test_controle_medida_zero_sem_falha_e_aprovada_e_vai_para_a_biblioteca(self):
        r = self.rodar()
        self.assertEqual((r["nota"], r["passou"], r["classe_erro"], r["cena_ok"]), (0.0, True, None, True))
        self.assertEqual(r["medida"], {"valida": True, "nota": 0.0, "passou": True})
        self.assertEqual(self.biblioteca, [1])

    def test_a08_falha_do_video_depois_da_medida_zero_nao_e_aprovacao(self):
        def estoura(m, **k):
            raise RuntimeError("captura falhou")
        self.mundo.respostas["capture_isolated_setup"] = estoura
        r = self.rodar(video=True)
        self.assertEqual(r["nota"], 0.0)                 # a medida é preservada
        self.assertIs(r["medida"]["passou"], True)
        self.assertIs(r["passou"], False)                # mas não é aprovação operacional
        self.assertEqual(r["classe_erro"], "infraestrutura")
        self.assertNotEqual(r["motivo"], "passou")
        self.assertIn("captura falhou", r["motivo"])
        self.assertEqual(self.biblioteca, [])            # nada encaminhado como sucesso
        self.assertIsNone(F.sucesso([r, dict(r, n=2, execucao="b"), dict(r, n=3, execucao="c")]))

    def test_a08_falha_da_restauracao_depois_da_medida_zero_nao_e_aprovacao(self):
        self.mundo.respostas["capture_isolated_restore"] = {"ok": False, "erros": ["rig"]}
        r = self.rodar()
        self.assertEqual((r["nota"], r["passou"], r["classe_erro"], r["cena_ok"]), (0.0, False, "estado_parcial", False))
        self.assertEqual(self.biblioteca, [])
        self.assertIs(X.curto(r)["passou"], False)

    def _gravar(self, *linhas):
        for t in linhas:
            X._acrescentar("tentativas.jsonl", t)

    def test_a09_resumo_e_admissao_do_executor_usam_a_mesma_politica(self):
        self._gravar(zero(1), zero(2), zero(3, versoes=dict(VERSOES, executor="e2")))
        self.assertIsNone(X.estado_resumo()["sucesso"])
        _, motivos = X.preparar(json.loads(json.dumps(RECEITA)))
        self.assertFalse(any("já conseguiu" in m for m in motivos), motivos)
        self._gravar(zero(4))  # agora há 3 compatíveis (1, 2 e 4)
        self.assertEqual(X.estado_resumo()["sucesso"], {"assinatura": ASSIN, "vezes": 3})
        _, motivos = X.preparar(json.loads(json.dumps(RECEITA)))
        self.assertTrue(any("já conseguiu" in m for m in motivos), motivos)

    def test_f09_biblioteca_nao_promove_tentativa_sem_cena_segura(self):
        self._gravar(zero(1), zero(2), zero(3, cena_ok=False, passou=False, classe_erro="estado_parcial"))
        self.assertEqual(BIB.importar_rodada(self.pasta, "teste")["blocos"], [])
        self._gravar(zero(4))
        blocos = BIB.importar_rodada(self.pasta, "teste")["blocos"]
        self.assertEqual([b["tentativas"] for b in blocos], [[1, 2, 4]])


class Diagnostico(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=SCRATCH)
        self.addCleanup(self.tmp.cleanup)
        p = plano()
        p["cena"]["variacoes"] = 1
        self.c = N.preparar("objetivo com uma variação", p, 1, base=Path(self.tmp.name))
        self.p = Path(self.c["pasta"])
        self.assertTrue(self.c["executavel"], self.c["bloqueios"])
        CP.gravar(self.p, "AUTORIZACAO.json", {"id": self.c["id"], "integridade": self.c["integridade"]})

    def linha(self, t):
        with (self.p / "tentativas.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(t) + "\n")

    def test_a11_recorte_aprovado_com_variacao_faltando_nao_e_sucesso_no_diagnostico(self):
        for n in (1, 2, 3):
            self.linha(zero(n))
        s = N.estado(self.p)
        self.assertTrue(s["recorte_medido"])
        self.assertEqual(s["variacoes"]["faltam"], 1)
        self.assertFalse(s["sucesso_medido"])
        self.assertEqual(s["diagnostico"], "recorte_medido_variacoes_pendentes")
        outra = [dict(p) for p in RECEITA["passos"]]
        outra[1]["clipe"] = "Victory"
        self.linha(zero(4, variacao=True, receita=outra, assinatura=R.assinatura({"passos": outra})))
        s = N.estado(self.p)
        self.assertEqual(s["variacoes"]["faltam"], 0)
        self.assertTrue(s["sucesso_medido"])  # ao completar a variação, texto e booleano concordam
        self.assertEqual(s["diagnostico"], "sucesso_medido")


class Ensaio(unittest.TestCase):
    def rodada(self, *linhas, arquivos=("ENSAIO.md",)) -> str:
        d = tempfile.mkdtemp(prefix="v006_ensaio_")
        Path(d, "tentativas.jsonl").write_text("".join(json.dumps(t) + "\n" for t in linhas), encoding="utf-8")
        for a in arquivos:
            Path(d, a).write_text("escrito pelo Productor", encoding="utf-8")
        return d

    def medida(self, n, nota, **kw):
        return zero(n, nota=nota, passou=nota == 0, avaliacao={"valida": True, "nota": nota}, **kw)

    def test_f02_ensaio_valido_nao_e_julgado_pelo_contrato_da_noite(self):
        d = self.rodada(self.medida(1, 2.5), self.medida(2, 2.5))  # tentativa válida + reprodução com a MESMA nota
        ensaio = RO.md_unreal(d, {"modo": "ensaio"}, "o Productor escreveu o relatório do ensaio", 0)
        self.assertIn("✅ ensaio válido", ensaio)
        self.assertNotIn("não conseguiu", ensaio)
        noite = RO.md_unreal(d, {"modo": "noite"}, "passou do horário-limite", 0)  # os MESMOS dados não bastam para a noite
        self.assertIn("❌ não conseguiu", noite)

    def test_f02_ensaio_md_sozinho_nao_prova_o_ensaio(self):
        casos = {"sem tentativa medida": [],
                 "uma só, sem reprodução": [self.medida(1, 2.5)],
                 "reprodução com nota diferente": [self.medida(1, 2.5), self.medida(2, 4.0)],
                 "cena não restaurada": [self.medida(1, 2.5), self.medida(2, 2.5, cena_ok=False)]}
        for nome, linhas in casos.items():
            with self.subTest(caso=nome):
                m = RO.md_unreal(self.rodada(*linhas), {"modo": "ensaio"}, "o Productor escreveu o relatório do ensaio", 0)
                self.assertIn("❌ ensaio não cumprido", m)


if __name__ == "__main__":
    unittest.main()
