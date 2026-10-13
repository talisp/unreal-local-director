"""Modo "testar a versão" do /director-noite (13/10): a lista de testes da versão mora com o código
(tools/testes_da_versao.json), quem diz se cada teste foi coberto é o PROGRAMA (lendo os registros da campanha) e
`fechar --motivo esgotamento` é recusado enquanto faltar teste. Também: o executor registra as recusas de admissão e
a vigia, em laboratório, conta experimento novo concluído como progresso.

Tudo offline: campanhas em pasta temporária, Unreal falso de testes_v006_l1. Nenhuma sessão do Hermes é aberta.
"""
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
import contextlib
import io
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
import director_noite as N  # noqa: E402
import fila_executor as X  # noqa: E402
import vigia_dev as V  # noqa: E402
from unreal_macros import campanha as CP, processos as P  # noqa: E402
from testes_director_noite import plano  # noqa: E402
from testes_v006_l1 import BaseExecutor, RECEITA  # noqa: E402
from testes_v006_l3 import zero  # noqa: E402
from testes_v006_l5 import Campanha  # noqa: E402

IDS = ["tentativa_aprovada_completa", "reprovada_guarda_amostras", "repeticao_tres_vezes", "recusa_receita_invalida",
       "segunda_admissao_recusada", "video_completo"]


class Lista(unittest.TestCase):
    def test_a_lista_da_versao_e_legivel_e_o_programa_sabe_conferir_cada_item(self):
        from unreal_macros import teste_versao as TV
        lista = TV.ler_lista()
        self.assertEqual([i["id"] for i in lista["itens"]], IDS)
        self.assertTrue(all(i[k].strip() for i in lista["itens"] for k in ("mudou", "como", "esperado")))
        self.assertEqual(sorted(TV.CONFERIDORES), sorted(IDS))  # item sem conferidor não entra na lista
        self.assertIn("testes_da_versao", N.capacidades())
        self.assertEqual([i["id"] for i in N.capacidades()["testes_da_versao"]["itens"]], IDS)


class CampanhaDeTeste(Campanha):
    MODO = "experimental"

    def nova(self, modo: str = "experimental", objetivo: str = "testar a versão", com_lista: bool = True) -> tuple:
        pl = plano()
        pl["modo"] = modo
        if com_lista:
            pl["testes_da_versao"] = True
        c = N.preparar(objetivo, pl, 1, base=Path(self.tmp.name))
        p = Path(c["pasta"])
        CP.gravar(p, "AUTORIZACAO.json", {"id": c["id"], "integridade": c["integridade"]})
        return c, p

    def arquivo(self, rel: str, texto: str = "[]"):
        alvo = self.p / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(texto, encoding="utf-8")

    def tentativa(self, n: int, **kw):
        """Linha final como a do executor da v0.0.6, com as evidências em disco."""
        d = zero(n, medida={"valida": True, "nota": 0.0, "passou": True}, amostras_completas=True,
                 amostras_arquivo=f"amostras/t{n:03d}.json", cena_alcance={"campos": [], "reduzido": False},
                 cena_fotos=[f"evidencias/t{n:03d}-antes.json", f"evidencias/t{n:03d}-depois.json"])
        d.update(kw)
        for rel in [d.get("amostras_arquivo")] + list(d.get("cena_fotos") or []):
            if rel:
                self.arquivo(rel)
        with (self.p / "tentativas.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(d) + "\n")
        return d

    def recusa(self, motivo: str, **kw):
        with (self.p / "recusas.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(dict({"tipo_linha": "recusa", "comando": "tentar", "motivos": [motivo], "proximo_n_antes": 5,
                                     "proximo_n_depois": 5, "pendente_n": None}, **kw)) + "\n")

    def cobrir_tudo(self, menos: tuple = ()):
        # "menos tentativa_aprovada_completa": as aprovadas existem (a repetição e o vídeo continuam cobertos), mas
        # todas com o alcance da cena REDUZIDO, que é o que esse teste não aceita
        ap = {"cena_alcance": {"campos": [], "reduzido": True}} if "tentativa_aprovada_completa" in menos else {}
        for n in (1, 2) + (() if "repeticao_tres_vezes" in menos else (3,)):
            self.tentativa(n, **ap)
        if "reprovada_guarda_amostras" not in menos:
            self.tentativa(4, nota=2.5, passou=False, classe_erro="encaixe", medida={"valida": True, "nota": 2.5, "passou": False},
                           assinatura="outra")
        if "recusa_receita_invalida" not in menos:
            self.recusa("passo 2: turn_deg entre -180 e 180")
        if "segunda_admissao_recusada" not in menos:
            self.recusa("a tentativa 3 ainda está rodando: espere (resultado 3)", pendente_n=3)
        if "video_completo" not in menos:
            self.arquivo("videos/t005.mp4", "mp4")
            self.tentativa(5, assinatura="com video", video={"arquivo": str(self.p / "videos/t005.mp4"), "completo": True,
                                                              "quadros": 60, "esperados": 60, "faltaram": []}, **ap)

    def faltam(self) -> list:
        return N.estado(self.p)["testes_versao"]["faltam"]


class Cobertura(CampanhaDeTeste):
    def test_campanha_preparada_com_a_lista_guarda_os_ids_no_manifesto(self):
        self.assertEqual(self.c["testes_versao"]["ids"], IDS)
        self.assertIn("tools\\testes_da_versao.json", {k.replace("/", "\\") for k in self.c["versoes"]})
        self.assertEqual(self.faltam(), IDS)  # nada feito ainda: falta tudo
        self.assertEqual(CP.ler(self.p)["testes_versao"]["ids"], IDS)  # protegido pela integridade do manifesto

    def test_lista_so_vale_em_laboratorio(self):
        pl = plano()
        pl["testes_da_versao"] = True
        with self.assertRaisesRegex(ValueError, "experimental"):
            N.preparar("formal com lista", pl, 1, base=Path(self.tmp.name))

    def test_cada_item_so_fica_coberto_com_a_evidencia_certa(self):
        self.cobrir_tudo()
        self.assertEqual(self.faltam(), [])
        casos = {
            "tentativa_aprovada_completa": lambda: self.tentativa(9, assinatura="sem foto", cena_fotos=[]),
            "reprovada_guarda_amostras": lambda: self.tentativa(4, nota=2.5, passou=False, amostras_completas=False,
                                                                medida={"valida": True, "nota": 2.5, "passou": False}),
            "recusa_receita_invalida": lambda: self.recusa("passo 2: turn_deg entre -180 e 180", proximo_n_depois=6),
            "segunda_admissao_recusada": lambda: self.recusa("a tentativa 3 ainda está rodando", pendente_n=None),
            "video_completo": lambda: self.tentativa(5, video={"arquivo": None, "completo": False, "quadros": 59,
                                                               "esperados": 60, "faltaram": [4]}),
        }
        for item, evidencia_ruim in casos.items():
            with self.subTest(item=item):
                for f in ("tentativas.jsonl", "recusas.jsonl"):
                    (self.p / f).unlink(missing_ok=True)
                self.cobrir_tudo(menos=(item,))
                evidencia_ruim()  # parecida, mas sem o que o teste exige: não pode contar
                self.assertEqual(self.faltam(), [item])

    def test_repeticao_exige_tres_tentativas_distintas(self):
        self.cobrir_tudo(menos=("repeticao_tres_vezes",))
        self.assertEqual(self.faltam(), ["repeticao_tres_vezes"])
        self.tentativa(2)  # a MESMA linha de novo não é a terceira
        self.assertIn("repeticao_tres_vezes", self.faltam())


class Fechamento(CampanhaDeTeste):
    def _fila_vazia_com_historico(self):
        N.planejar(self.p, [{"id": "H1", "hipotese": "h", "funcionalidade": "f", "proximo_teste": "t"}])
        self.arquivo("nota.md", "evidência")
        N.concluir(self.p, {"id": "H1", "classe": "descartada", "descoberta": "nada", "evidencias": ["nota.md"]})

    def test_esgotamento_e_recusado_enquanto_faltar_teste_da_versao(self):
        self.cobrir_tudo(menos=("video_completo", "segunda_admissao_recusada"))
        self._fila_vazia_com_historico()
        with self.assertRaisesRegex(ValueError, "faltam testes da versão.*segunda_admissao_recusada.*video_completo"):
            N.fechar(self.p, "esgotamento", "fila vazia")
        self.assertFalse((self.p / "ENCERRAMENTO.json").exists())
        self.assertFalse(CP.encerrada(self.p))

    def test_esgotamento_e_aceito_com_a_lista_coberta(self):
        self.cobrir_tudo()
        self._fila_vazia_com_historico()
        N.fechar(self.p, "esgotamento", "lista coberta e fila vazia")
        self.assertTrue(CP.encerrada(self.p))

    def test_teste_que_achou_defeito_conta_como_resolvido_se_foi_registrado_com_evidencia(self):
        self.cobrir_tudo(menos=("video_completo",))
        N.planejar(self.p, [{"id": "HV", "hipotese": "o vídeo sai completo", "funcionalidade": "video", "proximo_teste": "t",
                             "teste": "video_completo"}])
        self.arquivo("achado.md", "o vídeo saiu incompleto 2 vezes")
        N.concluir(self.p, {"id": "HV", "classe": "suspeita", "descoberta": "vídeo incompleto 2 vezes",
                            "evidencias": ["achado.md"], "teste": "video_completo"})
        s = N.estado(self.p)["testes_versao"]
        self.assertEqual(s["faltam"], [])
        self.assertEqual([i["situacao"] for i in s["itens"] if i["id"] == "video_completo"], ["achado_registrado"])
        N.fechar(self.p, "esgotamento", "lista resolvida: 5 cobertos e 1 achado registrado")
        self.assertTrue(CP.encerrada(self.p))

    def test_teste_desconhecido_e_recusado_no_planejamento(self):
        with self.assertRaisesRegex(ValueError, "teste desconhecido"):
            N.planejar(self.p, [{"id": "HX", "hipotese": "h", "funcionalidade": "f", "proximo_teste": "t", "teste": "inventado"}])

    def test_controle_campanha_sem_a_lista_fecha_por_esgotamento_como_antes(self):
        self.c, self.p = self.nova(com_lista=False)
        self.assertNotIn("testes_versao", N.estado(self.p))
        self._fila_vazia_com_historico()
        N.fechar(self.p, "esgotamento", "fila vazia")
        self.assertTrue(CP.encerrada(self.p))

    def test_prazo_continua_fechando_mesmo_com_teste_faltando(self):
        with patch.object(time, "time", return_value=self.c["prazo_tentativas_ts"] + 1):
            N.fechar(self.p, "prazo", "acabou o tempo")
        rel = json.loads((self.p / "RELATORIO.json").read_text(encoding="utf-8"))
        self.assertEqual(rel["testes_versao"]["faltam"], IDS)  # o relatório diz o que ficou sem testar
        self.assertIn("Testes da versão", (self.p / "RELATORIO.md").read_text(encoding="utf-8"))


class Recusas(BaseExecutor):
    def setUp(self):
        super().setUp()
        p = patch.object(X, "depois_da_hora", lambda *a, **k: False)
        p.start()
        self.addCleanup(p.stop)

    def _tentar(self, receita: dict) -> tuple:
        arq = os.path.join(self.tmp, "r.json")
        Path(arq).write_text(json.dumps(receita), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            return X.main(["tentar", arq])

    def test_recusa_de_admissao_fica_registrada_com_o_motivo_e_sem_gastar_numero(self):
        passos = [dict(p) for p in RECEITA["passos"]]
        passos[2]["turn_deg"] = True
        self.assertEqual(self._tentar(dict(RECEITA, passos=passos)), 1)
        linhas = X._ler_jsonl("recusas.jsonl")
        self.assertEqual(len(linhas), 1)
        self.assertTrue(any("turn_deg" in m for m in linhas[0]["motivos"]))
        self.assertEqual((linhas[0]["proximo_n_antes"], linhas[0]["proximo_n_depois"], linhas[0]["pendente_n"]), (1, 1, None))
        self.assertEqual(X.tentativas_validas(), [])
        self.assertEqual(self.mundo.chamadas, [])

    def test_segunda_admissao_com_uma_tentativa_rodando_registra_quem_estava_rodando(self):
        with patch.object(X.subprocess, "Popen", lambda cmd, **k: type("Proc", (), {"pid": os.getpid()})()):
            self.assertEqual(self._tentar(RECEITA), 0)   # aceita: fica "rodando" (filho falso, pid vivo)
            self.assertEqual(self._tentar(RECEITA), 1)   # a segunda, com a primeira ainda rodando
        linhas = X._ler_jsonl("recusas.jsonl")
        self.assertEqual(len(linhas), 1)
        self.assertIn("ainda está rodando", " ".join(linhas[0]["motivos"]))
        self.assertEqual((linhas[0]["pendente_n"], linhas[0]["proximo_n_antes"], linhas[0]["proximo_n_depois"]), (1, 2, 2))


class VigiaLaboratorio(unittest.TestCase):
    def obs(self, experimentos, melhor=0.0):
        return {"log": {"turno_ativo": False, "motivo_fim": "text_response(finish_reason=stop)", "sessao": "S1"},
                "rodada": {"terminou": False, "pendente": None, "melhor_nota": melhor, "tentativas": 9, "inseguro": False,
                           "ultimo_especial": None, "experimentos_medidos": experimentos},
                "saude": {"trava": "livre", "modelo": True, "unreal": True, "sessao_processo": P.MORTO},
                "campanha": {"fim_ts": time.time() + 3600}, "bloqueios_campanha": [], "pausa": False}

    def test_experimento_novo_concluido_conta_como_progresso_depois_da_primeira_nota_zero(self):
        mem = {"causas": ["falou_e_parou"], "melhor": 0.0, "experimentos_medidos": 4}
        d = V.decidir(self.obs(experimentos=7), mem, time.time(), dict(V.LIM))  # 3 experimentos medidos desde a última parada
        self.assertEqual(d["acoes"], ["relancar"], d)
        self.assertEqual((mem["causas"], mem["experimentos_medidos"]), ([], 7))

    def test_mesma_causa_sem_experimento_novo_ainda_manda_mudar(self):
        mem = {"causas": ["falou_e_parou"], "melhor": 0.0, "experimentos_medidos": 4}
        d = V.decidir(self.obs(experimentos=4), mem, time.time(), dict(V.LIM))
        self.assertEqual(d["acoes"], ["relancar_mudando"], d)

    def test_ler_rodada_conta_so_experimentos_medidos_da_campanha(self):
        import tempfile
        from testes_director_noite import SCRATCH
        with tempfile.TemporaryDirectory(dir=SCRATCH) as tmp:
            pl = plano()
            pl["modo"] = "experimental"
            c = N.preparar("objetivo", pl, 1, base=Path(tmp))
            p = Path(c["pasta"])
            CP.gravar(p, "LABORATORIO.json", {"id": c["id"], "fila": [], "scripts": [], "experimentos": [
                {"id": "a", "funcionalidade": "f", "tentativas": [1], "classe": "medido"},
                {"id": "b", "funcionalidade": "f", "tentativas": [], "classe": "descartada"},
                {"id": "c", "funcionalidade": "f", "tentativas": [2], "classe": "medido"}]})
            self.assertEqual(V.ler_rodada(str(p))["experimentos_medidos"], 2)
        with tempfile.TemporaryDirectory() as legado:
            self.assertIsNone(V.ler_rodada(legado)["experimentos_medidos"])


if __name__ == "__main__":
    unittest.main()
