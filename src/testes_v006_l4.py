"""Regressões L4 da v0.0.6: medição fiel, SEM mudar metas (A12 A13 A14 A15 A16, F11).

Os limites (fila.LIM), a quota de exploração e os critérios são os mesmos de antes: `test_limites_intocados`
confere os números. O que muda é a implementação que os aplicava errado. Sequências sintéticas de testes_fila.
"""
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
import fila_executor as X  # noqa: E402
from unreal_macros import fila as F, receita as R  # noqa: E402
from testes_fila import pose, seq_ok, troca_pose  # noqa: E402


class Limites(unittest.TestCase):
    def test_limites_intocados(self):
        self.assertEqual(F.LIM, {"quadril_cm": 10.0, "osso_cm": 15.0, "virada_deg": 10.0, "sentado_max_cm": 70.0,
                                 "de_pe_min_cm": 88.0, "mao_acima_cm": 5.0, "aceno_quadros": 15, "aceno_lateral_cm": 10.0,
                                 "aceno_inversoes": 2, "aceno_passo_cm": 2.0, "andar_cm": 150.0, "pe_apoiado_cm": 3.0,
                                 "pe_no_ar_cm": 8.0, "andar_passos_por_pe": 2, "parar_quadros": 15, "parar_caminho_cm": 3.0,
                                 "dedo_min_cm": -2.0, "dedo_max_cm": 8.0, "duracao_s": 25.0})
        self.assertEqual(F.REGRAS, {"exploracao_min_em_10": 3, "plato_tentativas": 6, "plato_melhora": 0.05,
                                    "linhagens_vivas_max": 3, "linhagens_total_max": 6, "tentativas_max": 80,
                                    "repeticoes_sucesso": 3})
        self.assertEqual(F.PASSO_AMOSTRA, 3)


class Coordenadas(unittest.TestCase):
    def test_a12_coordenada_nao_finita_ou_de_tipo_errado_invalida_a_medida(self):
        am, fx, pp = seq_ok()
        self.assertEqual(F.avaliar(am, fx, pp, 30)["nota"], 0)  # controle: a medição original passa
        q = am[7][0]
        for nome, ruim in (("NaN", [0.0, float("nan"), 125.0]), ("infinito", [0.0, float("inf"), 125.0]),
                           ("texto", [0.0, "1", 125.0]), ("booleano", [0.0, True, 125.0]), ("2 dimensões", [0.0, 125.0]),
                           ("não é lista", 5.0)):
            with self.subTest(caso=nome):
                o = dict(am[7][1], Spine2=ruim)
                r = F.avaliar(troca_pose(am, q, o), fx, pp, 30)
                self.assertIs(r["valida"], False, r)
                self.assertIsNone(r["nota"])
                self.assertIn("Spine2", r["motivo"])

    def test_a12_o_registro_nunca_grava_nan_ou_infinito_em_silencio(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(X, "PASTA", tmp):
            X._acrescentar("tentativas.jsonl", {"tipo_linha": "tentativa", "n": 1, "nota": float("nan"),
                                              "trocas": [{"quadril_cm": float("inf")}]})
            texto = Path(tmp, "tentativas.jsonl").read_text(encoding="utf-8")

            def recusa(x):
                raise ValueError(x)
            d = json.loads(texto, parse_constant=recusa)  # JSON estrito: NaN/Infinity quebrariam aqui
            self.assertIsNone(d["nota"])
            self.assertIsNone(d["trocas"][0]["quadril_cm"])
            self.assertEqual(d["nao_finitos"], ["nota", "trocas[0].quadril_cm"])


class Arredondamento(unittest.TestCase):
    def _com_salto(self, osso: str, eixo: int, cm: float) -> dict:
        am, fx, pp = seq_ok()
        o = {k: list(v) for k, v in am[[q for q, _ in am].index(89)][1].items()}
        o[osso][eixo] += cm
        return F.avaliar(troca_pose(am, 90, o), fx, pp, 30)

    def test_a13_exatamente_no_limite_passa_e_imediatamente_acima_reprova(self):
        for nome, osso, eixo, limite in (("quadril", "Hips", 2, 10.0), ("osso", "RightHand", 2, 15.0)):
            with self.subTest(caso=nome):
                no_limite = self._com_salto(osso, eixo, limite)["trocas"][1]
                self.assertEqual((no_limite["nota"], no_limite["excede"]), (0.0, []), no_limite)
                acima = self._com_salto(osso, eixo, limite + 0.004)
                t = acima["trocas"][1]
                self.assertEqual(t["pior_osso_cm"], limite)      # o texto exibido se arredonda para o limite...
                self.assertGreater(t["nota"], 0)                  # ...mas a troca NÃO passa
                self.assertTrue(t["excede"])
                self.assertGreater(acima["nota"], 0)

    def test_a13_virada_imediatamente_acima_do_limite_reprova(self):
        am, fx, pp = seq_ok()
        for graus, passa in ((10.0, True), (10.004, False)):
            r = F.avaliar(troca_pose(am, 90, pose(f=90.0 + graus)), fx, pp, 30)
            t = r["trocas"][1]
            self.assertEqual(t["virada_deg"], 10.0)
            self.assertEqual(t["nota"] == 0, passa, (graus, t["nota"], t["excede"]))

    def test_a13_a_copia_da_biblioteca_decide_igual_a_regua(self):
        from unreal_macros import biblioteca as BIB
        am, fx, pp = seq_ok()
        o = {k: list(v) for k, v in am[[q for q, _ in am].index(89)][1].items()}
        o["Hips"][2] += 10.004
        t = F.avaliar(troca_pose(am, 90, o), fx, pp, 30)["trocas"][1]
        copia = BIB.medir_troca(t["ossos_antes"], t["ossos_depois"])
        self.assertEqual(copia["nota"], t["nota"])
        self.assertGreater(copia["nota"], 0)


class Andar(unittest.TestCase):
    def _andar(self, alturas: list) -> dict:
        """Cada pé com as alturas dadas (cm acima do seu mínimo); o quadril anda 160 cm."""
        n = len(alturas)
        return F._andar([(i * 3, pose(hy=160.0 * i / (n - 1), pe=(a, a))) for i, a in enumerate(alturas)])

    def test_a14_pe_que_comeca_no_ar_nao_conta_como_saida_do_chao(self):
        r = self._andar([8.0, 0.0, 8.0])
        self.assertEqual(r["pe_saiu_do_chao"], {"LeftFoot": 1, "RightFoot": 1})  # uma transição observada, não duas
        self.assertFalse(r["passou"])
        self.assertGreaterEqual(r["deslocamento_cm"], 150)

    def test_a14_duas_saidas_observadas_contam_duas(self):
        r = self._andar([0.0, 8.0, 0.0, 8.0])
        self.assertEqual(r["pe_saiu_do_chao"], {"LeftFoot": 2, "RightFoot": 2})
        self.assertTrue(r["passou"])


class Acenar(unittest.TestCase):
    @staticmethod
    def _mao(q: int) -> tuple:
        return ("R", 25 + 12 * math.sin(q / 2.0), 15)  # alta e indo e voltando de lado

    def _medir(self, faixas, papeis, acenando) -> dict:
        """Mão alta e alternando só nos quadros de `acenando`; no resto (pontes, espera) a mão fica baixa."""
        base, _, _ = seq_ok()
        am = []
        for q in F.quadros_a_amostrar(faixas):
            papel = papeis[F._faixa_de(q, faixas)]
            if papel == "levantar":
                o = pose(hz=50 + q * 1.5)
            elif papel in ("acenar", "ponte"):
                o = pose(mao=self._mao(q)) if acenando(q) else pose()
            elif papel == "andar":
                o = dict(base)[90 + min(87, 3 * ((q - faixas[-2]["de"]) // 3))]
            else:
                o = pose(hy=180.0)
            am.append((q, o))
        return F.avaliar(am, faixas, papeis, 30)["intencoes"]["acenar"]

    def test_a15_trechos_curtos_separados_por_pontes_nao_somam_continuidade(self):
        # 3 acenos de 8 quadros (< 15) separados por pontes de 12 quadros com a mão BAIXA
        cortes = [0, 30, 38, 50, 58, 70, 78, 168, 198]
        faixas = [{"de": a, "ate": b} for a, b in zip(cortes, cortes[1:])]
        papeis = ["levantar", "acenar", "ponte", "acenar", "ponte", "acenar", "andar", "parar"]
        r = self._medir(faixas, papeis, lambda q: any(a <= q < b for a, b in ((30, 38), (50, 58), (70, 78))))
        self.assertFalse(r["passou"], r)

    def test_a15_aceno_continuo_equivalente_passa(self):
        cortes = [0, 30, 78, 168, 198]
        faixas = [{"de": a, "ate": b} for a, b in zip(cortes, cortes[1:])]
        papeis = ["levantar", "acenar", "andar", "parar"]
        r = self._medir(faixas, papeis, lambda q: 30 <= q < 78)
        self.assertTrue(r["passou"], r)

    def test_a15_faixas_de_aceno_vizinhas_continuam_um_trecho_so(self):
        cortes = [0, 30, 54, 78, 168, 198]  # dois clipes de aceno em seguida, sem ponte no meio
        faixas = [{"de": a, "ate": b} for a, b in zip(cortes, cortes[1:])]
        papeis = ["levantar", "acenar", "acenar", "andar", "parar"]
        r = self._medir(faixas, papeis, lambda q: 30 <= q < 78)
        self.assertTrue(r["passou"], r)


class Exploracao(unittest.TestCase):
    @staticmethod
    def _hist(tipos) -> list:
        # sem nota: não entra em platô nem em regra de dois; só a regra de exploração está em jogo
        return [{"n": i + 1, "nota": None, "linhagem": "A", "tipo": t, "classe_erro": "infraestrutura", "assinatura": "x"}
                for i, t in enumerate(tipos)]

    def _pode(self, tipos, proximo: str) -> bool:
        return F.checar_regras({"linhagem": "A", "tipo": proximo}, self._hist(tipos), {}) == []

    def test_a16_toda_sequencia_admitida_tem_continuacao_e_nenhuma_janela_fica_abaixo_da_quota(self):
        admitidas, becos, janelas_ruins = [()], [], []
        for _ in range(13):
            proximas = []
            for seq in admitidas:
                filhos = [seq + (t,) for t in ("ajuste", "exploracao") if self._pode(seq, t)]
                if not filhos:
                    becos.append(seq)
                proximas += filhos
            admitidas = proximas
            for seq in admitidas:
                if len(seq) >= 10 and seq[-10:].count("exploracao") < F.REGRAS["exploracao_min_em_10"]:
                    janelas_ruins.append(seq)
        self.assertEqual(becos[:3], [])            # nenhuma sequência admitida fica sem próxima tentativa válida
        self.assertEqual(janelas_ruins[:3], [])    # e a regra de 3 em 10 continua valendo em toda janela completa
        self.assertGreater(len(admitidas), 100)    # o teste percorreu de fato muitas sequências (13 tentativas)

    def test_a16_a_obrigacao_e_antecipada_so_quando_as_vagas_restantes_sao_necessarias(self):
        self.assertTrue(self._pode(["ajuste"] * 7, "exploracao"))
        self.assertFalse(self._pode(["ajuste"] * 7, "ajuste"))   # 8ª: sobram 2 vagas, faltam 3 explorações
        self.assertTrue(self._pode(["ajuste"] * 6, "ajuste"))    # 7ª: ainda cabem 3 explorações depois
        self.assertTrue(self._pode(["exploracao"] * 3 + ["ajuste"] * 6, "ajuste"))

    def test_a16_historico_antigo_ja_sem_quota_aceita_a_exploracao_que_o_repara(self):
        nove = ["ajuste"] * 9  # situação que o código antigo admitia e depois não deixava sair
        self.assertFalse(self._pode(nove, "ajuste"))
        self.assertTrue(self._pode(nove, "exploracao"))


class Giro(unittest.TestCase):
    BASE = {"linhagem": "A", "tipo": "exploracao", "passos": [
        {"clipe": "Sit_To_Stand", "papel": "levantar"}, {"clipe": "Waving", "papel": "acenar"},
        {"clipe": "Start_Walking", "papel": "andar"}, {"clipe": "Stop_Walking_2", "papel": "parar"}]}

    def _com(self, valor) -> dict:
        passos = [dict(p) for p in self.BASE["passos"]]
        passos[2]["turn_deg"] = valor
        return dict(self.BASE, passos=passos)

    def test_f11_turn_deg_booleano_nan_infinito_ou_texto_e_recusado(self):
        for ruim in (True, False, float("nan"), float("inf"), float("-inf"), "90", None, [90]):
            with self.subTest(valor=ruim):
                self.assertTrue(any("turn_deg" in m for m in F.validar_receita(self._com(ruim))), ruim)
                self.assertTrue(any("turn_deg" in m for m in R.validar(self._com(ruim))), ruim)

    def test_f11_angulo_finito_valido_e_aceito(self):
        for bom in (0, 90, -180, 180.0, 12.5):
            with self.subTest(valor=bom):
                self.assertEqual(F.validar_receita(self._com(bom)), [])
        self.assertTrue(any("turn_deg" in m for m in F.validar_receita(self._com(180.5))))


if __name__ == "__main__":
    os.environ.setdefault("UNREAL_MACROS_OFFLINE", "1")
    unittest.main()
