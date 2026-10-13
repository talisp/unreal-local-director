"""Regressões L2 da v0.0.6: reservas e recuperação consistentes (A01 A02 A03 A04 A28, F05, F06, F07).

Tudo offline. As travas são arquivos TEMPORÁRIOS criados pelo teste: nenhuma falha é plantada na trava real
(work/unreal.trava). O executor roda com o Unreal falso de testes_v006_l1.
"""
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
import fila_executor as X  # noqa: E402
from unreal_macros import campanha as CP, processos as P  # noqa: E402
from testes_v006_l1 import BaseExecutor, RECEITA  # noqa: E402

if os.environ.get("V006_TRAVA_CONTROLE"):  # controle negativo: os MESMOS testes contra a trava.py de antes do L2
    _spec = importlib.util.spec_from_file_location("trava_controle", os.environ["V006_TRAVA_CONTROLE"])
    assert _spec and _spec.loader
    T = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(T)
else:
    from unreal_macros import trava as T  # noqa: E402


def _morto() -> int:
    """Um pid que comprovadamente não existe mais (processo que já terminou)."""
    import subprocess
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


class Trava(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="v006_trava_")
        self.p = os.path.join(self.tmp, "teste.trava")
        self.log = os.path.join(self.tmp, "trava.log")

    def escrever(self, **info):
        Path(self.p).write_text(json.dumps(info), encoding="utf-8")

    def test_controle_pegar_soltar_e_orfa_morta(self):
        T.pegar(self.p, "teste")
        self.assertEqual(T.estado(self.p)["estado"], "propria")
        T.soltar(self.p)
        self.assertFalse(os.path.exists(self.p))
        self.escrever(pid=_morto(), inicio=1.0, nonce="antigo")
        self.assertEqual(T.estado(self.p)["estado"], "morta")
        self.assertTrue(T.liberar_orfa(self.p, self.log)["liberada"])
        self.assertFalse(os.path.exists(self.p))
        self.escrever(pid=_morto(), inicio=1.0, nonce="antigo")
        T.pegar(self.p, "assume a órfã")  # dono comprovadamente morto: assume
        self.assertEqual(T.estado(self.p)["estado"], "propria")
        T.soltar(self.p)

    def test_f07_soltar_nao_remove_aquisicao_alheia_com_o_mesmo_pid(self):
        T.pegar(self.p, "teste")
        d = json.loads(Path(self.p).read_text(encoding="utf-8"))
        self.escrever(**dict(d, nonce="outra-aquisicao"))
        T.soltar(self.p)
        self.assertTrue(os.path.exists(self.p), "pid igual não é propriedade da aquisição")

    def test_f07_soltar_sem_ter_pegado_nao_remove(self):
        self.escrever(pid=os.getpid(), inicio=T._criacao_processo(os.getpid()), nonce="de-outro-modulo")
        T.soltar(self.p)
        self.assertTrue(os.path.exists(self.p))

    def test_f07_pid_reaproveitado_por_este_processo_nao_e_propria(self):
        self.escrever(pid=os.getpid(), inicio=1.0, nonce="dono-antigo")  # mesmo pid, criado em outro horário
        self.assertEqual(T.estado(self.p)["estado"], "morta")

    def _troca_de_dono_durante_a_leitura(self, novo: dict):
        nome = "_observar" if hasattr(T, "_observar") else "estado"  # "estado" = a trava.py de antes do L2 (controle)
        real = getattr(T, nome)

        def observar(caminho):
            visto = real(caminho)
            Path(caminho).write_text(json.dumps(novo), encoding="utf-8")  # outro processo assume ENTRE ler e remover
            return visto
        return patch.object(T, nome, observar)

    def test_f06_liberar_orfa_nao_remove_dono_substituido(self):
        self.escrever(pid=_morto(), inicio=1.0, nonce="antigo")
        novo = {"pid": os.getppid(), "inicio": None, "nonce": "novo", "macro": "outro operador"}
        with self._troca_de_dono_durante_a_leitura(novo):
            r = T.liberar_orfa(self.p, self.log)
        self.assertFalse(r["liberada"])
        self.assertEqual(json.loads(Path(self.p).read_text(encoding="utf-8")), novo)

    def test_f06_pegar_nao_apaga_a_trava_de_quem_assumiu_no_meio(self):
        self.escrever(pid=_morto(), inicio=1.0, nonce="antigo")
        novo = {"pid": os.getppid(), "inicio": None, "nonce": "novo", "macro": "outro operador"}
        with self._troca_de_dono_durante_a_leitura(novo), self.assertRaises((T.TravaOcupada, RuntimeError)):
            T.pegar(self.p, "atrasado", log=self.log)
        self.assertEqual(json.loads(Path(self.p).read_text(encoding="utf-8")), novo)

    def test_f06_vivo_ou_desconhecido_nunca_e_liberado(self):
        self.escrever(pid=os.getppid(), inicio=None, nonce="vivo")
        self.assertFalse(T.liberar_orfa(self.p, self.log)["liberada"])
        Path(self.p).write_text("{corrompida", encoding="utf-8")
        self.assertFalse(T.liberar_orfa(self.p, self.log)["liberada"])
        self.assertTrue(os.path.exists(self.p))

    def test_exclusiva_espera_e_nao_e_reentrante(self):
        ordem, dentro = [], threading.Event()

        def segundo():
            with T.exclusiva(self.p, "b", prazo_s=5):
                ordem.append("b")
        with T.exclusiva(self.p, "a", prazo_s=5):
            t = threading.Thread(target=segundo)
            t.start()
            dentro.wait(0.2)
            ordem.append("a")
            with self.assertRaises(T.TravaOcupada):  # mesmo processo, outra entrada: espera, não atravessa
                with T.exclusiva(self.p, "c", prazo_s=0.1):
                    ordem.append("c")
        t.join(5)
        self.assertEqual(ordem, ["a", "b"])
        self.assertFalse(os.path.exists(self.p))


class Reservas(BaseExecutor):
    def _saida(self, *argv) -> tuple:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            codigo = X.main(list(argv))
        return codigo, self._ultimo_json(buf.getvalue())

    @staticmethod
    def _ultimo_json(texto: str) -> dict:
        try:
            return json.loads(texto)  # o comando 'estado' imprime um JSON só, em várias linhas
        except ValueError:
            linhas = [json.loads(x) for x in texto.splitlines() if x.strip().startswith("{")]
            return linhas[-1] if linhas else {}

    def _receita(self, nome="r.json", **extra) -> str:
        arq = os.path.join(self.tmp, nome)
        Path(arq).write_text(json.dumps(dict(RECEITA, **extra)), encoding="utf-8")
        return arq

    def setUp(self):
        super().setUp()
        p = patch.object(X, "depois_da_hora", lambda *a, **k: False)
        p.start()
        self.addCleanup(p.stop)
        self.lancados = []

    def _popen_falso(self, barreira=None):
        def popen(cmd, **k):
            if barreira:
                barreira.wait(2)
            self.lancados.append(cmd)
            return type("Proc", (), {"pid": os.getpid()})()
        return popen

    def test_a01_duas_admissoes_ao_mesmo_tempo_dao_um_lancamento_e_uma_reserva(self):
        arq = self._receita()
        res, entrou = [], threading.Barrier(2)
        real = X.preparar

        def preparar(receita):
            try:
                entrou.wait(0.5)  # as duas passariam juntas pelo preparar, se a admissão não fosse exclusiva
            except threading.BrokenBarrierError:
                pass
            return real(receita)

        porta = threading.local()  # cada thread guarda o que ELA imprimiu (redirect_stdout é do processo inteiro)

        def imprimir(*a, **k):
            porta.texto = getattr(porta, "texto", "") + " ".join(str(x) for x in a) + "\n"

        def tentar():
            codigo = X.main(["tentar", arq])
            res.append((codigo, self._ultimo_json(getattr(porta, "texto", ""))))
        with patch.object(X, "preparar", preparar), patch.object(X.subprocess, "Popen", self._popen_falso()), \
                patch.object(X, "print", imprimir, create=True):
            ts = [threading.Thread(target=tentar) for _ in range(2)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(20)
        self.assertEqual(len(self.lancados), 1, res)
        self.assertEqual(sorted(c for c, _ in res), [0, 1])
        recusada = next(d for c, d in res if c == 1)
        self.assertIn("ainda está rodando", " ".join(recusada["recusada"]))
        e = X._estado()
        self.assertEqual((e["pendente"]["n"], e["proximo_n"]), (1, 2))
        self.assertEqual(sorted(os.listdir(os.path.join(self.pasta, "receitas"))), ["t001.json", "t001_saida.txt"])

    def test_a01_reserva_existe_antes_de_anunciar_rodando_e_erro_no_lancamento_a_libera(self):
        arq = self._receita()
        visto = {}

        def popen(cmd, **k):
            visto["pendente"] = dict(X._estado()["pendente"])
            raise OSError("não deu para criar o processo")
        with patch.object(X.subprocess, "Popen", popen):
            codigo, d = self._saida("tentar", arq)
        self.assertEqual(codigo, 1)
        self.assertEqual(visto["pendente"]["n"], 1)  # número e dono reservados ANTES do filho
        e = X._estado()
        self.assertIsNone(e["pendente"])  # a reserva própria foi liberada
        self.assertNotIn("autorizado", e)
        self.assertEqual(e["proximo_n"], 2)  # o número não é reutilizado

    def test_a01_execucao_nao_limpa_a_reserva_de_outra(self):
        X._gravar_estado({"proximo_n": 6, "fechadas": {}, "pendente": {"n": 5, "pid": os.getpid(), "desde": "x",
                                                                    "execucao": "de-outra"}})
        r = self.rodar(6)
        self.assertIn("recusada", r)
        self.assertEqual(X._estado()["pendente"]["execucao"], "de-outra")
        self.assertEqual(len(self.mundo.atores), 1)

    def _autorizar(self, arq_original: str) -> tuple:
        with patch.object(X.subprocess, "Popen", self._popen_falso()):
            codigo, d = self._saida("tentar", arq_original)
        self.assertEqual(codigo, 0, d)
        cmd = self.lancados[-1]
        return cmd[cmd.index("_filho") + 1], cmd[cmd.index("_filho") + 2], cmd[cmd.index("_filho") + 3]

    def test_a02_receita_trocada_depois_da_validacao_e_recusada_sem_tocar_no_unreal(self):
        copia, n, nonce = self._autorizar(self._receita())
        Path(copia).write_text(json.dumps(dict(RECEITA, hipotese="outra receita, não validada")), encoding="utf-8")
        codigo, d = self._saida("_filho", copia, n, nonce)
        self.assertEqual(codigo, 1)
        self.assertIn("não é a que foi validada", " ".join(d["recusada"]))
        self.assertEqual(self.mundo.chamadas, [])  # nenhuma chamada ao adaptador do Unreal
        self.assertEqual(X.tentativas_validas(), [])
        self.assertIsNone(X._estado()["pendente"])  # nada começou: a reserva desta autorização é liberada

    def test_a02_receita_intacta_e_consumida_uma_unica_vez(self):
        copia, n, nonce = self._autorizar(self._receita())
        codigo, _ = self._saida("_filho", copia, n, nonce)
        self.assertEqual(codigo, 0)
        self.assertEqual(len(X.tentativas_validas()), 1)
        chamadas = len(self.mundo.chamadas)
        codigo, d = self._saida("_filho", copia, n, nonce)  # repetir a mesma autorização
        self.assertEqual(codigo, 1)
        self.assertEqual(len(self.mundo.chamadas), chamadas)
        self.assertEqual(len(X.tentativas_validas()), 1)

    def _linha(self, **kw):
        X._acrescentar("tentativas.jsonl", dict({"tipo_linha": "tentativa", "n": 1, "linhagem": "A", "tipo": "exploracao",
                                                "nota": 2.0, "assinatura": "x", "receita": RECEITA["passos"],
                                                "cena_ok": True, "quando": "2026-10-11T10:00:00"}, **kw))

    def _fotografia(self) -> dict:
        return {f: Path(self.pasta, f).read_bytes() for f in sorted(os.listdir(self.pasta))
                if os.path.isfile(os.path.join(self.pasta, f))}

    def test_a03_estado_ausente_com_historico_nao_reinicia_o_contador_e_a_consulta_nao_escreve(self):
        for n in (1, 2, 3):
            self._linha(n=n)
        X._acrescentar("tentativas.jsonl", {"tipo_linha": "linhagem_fechada", "linhagem": "B", "motivo": "platô"})
        antes = self._fotografia()
        codigo, d = self._saida("estado")
        self.assertEqual(codigo, 0)
        self.assertEqual((d["tentativas"], d["proximo_n"]), (3, 4))
        self.assertEqual(self._fotografia(), antes)  # consultar não cria nem muda arquivo
        n, motivos = X.preparar(json.loads(json.dumps(RECEITA)))
        self.assertEqual((n, motivos), (4, []))  # contador e fechamentos reconciliados pelo histórico
        self.assertEqual(X._estado()["fechadas"], {"B": "platô"})

    def test_a03_estado_ausente_com_inicio_sem_conclusao_bloqueia(self):
        self._linha(n=1)
        X._acrescentar("tentativas.jsonl", {"tipo_linha": "tentativa_inicio", "n": 2})
        codigo, d = self._saida("tentar", self._receita())
        self.assertEqual(codigo, 1)
        self.assertIn("estado.json", " ".join(d["recusada"]))
        self.assertFalse(os.path.exists(os.path.join(self.pasta, "estado.json")))

    def test_a03_estado_truncado_bloqueia_e_o_arquivo_defeituoso_e_preservado(self):
        self._linha(n=1)
        Path(self.pasta, "estado.json").write_text('{"proximo_n": 2, "pend', encoding="utf-8")
        antes = self._fotografia()
        codigo, d = self._saida("estado")
        self.assertEqual(codigo, 0)
        self.assertIn("ilegível", d["estado_ilegivel"])
        self.assertEqual(d["tentativas"], 1)
        codigo, d = self._saida("tentar", self._receita())
        self.assertEqual(codigo, 1)
        self.assertIn("ilegível", " ".join(d["recusada"]))
        self.assertIn("recusada", self.rodar(2))
        self.assertEqual(self._fotografia(), antes)
        self.assertEqual(self.mundo.chamadas, [])

    def test_a03_pasta_nova_continua_inicializavel(self):
        self.assertEqual(X.preparar(json.loads(json.dumps(RECEITA))), (1, []))
        self.assertIs(self.rodar(1)["cena_ok"], True)

    def _queda_entre_resultado_e_limpeza_da_pendencia(self, **final):
        r = self.rodar(1)
        self.assertIs(r["cena_ok"], True)
        linhas = X._ler_jsonl("tentativas.jsonl")
        os.remove(os.path.join(self.pasta, "tentativas.jsonl"))
        for t in linhas:
            X._acrescentar("tentativas.jsonl", dict(t, **final) if t["tipo_linha"] == "tentativa" else t)
        e = X._estado()
        e["pendente"] = {"n": 1, "pid": _morto(), "desde": "x", "seq": None, "execucao": r["execucao"]}
        X._gravar_estado(e)

    def test_a04_queda_depois_do_resultado_seguro_reconcilia_so_a_pendencia(self):
        self._queda_entre_resultado_e_limpeza_da_pendencia()
        chamadas = len(self.mundo.chamadas)
        self.assertEqual(CP.inseguranca(self.pasta), [])  # a campanha não fica presa por uma pendência administrativa
        codigo, _ = self._saida("estado")
        self.assertIsNotNone(X._estado()["pendente"])  # consulta não escreve
        codigo, d = self._saida("resultado", "1")
        self.assertEqual(d["n"], 1)
        n, motivos = X.preparar(json.loads(json.dumps(RECEITA)))
        self.assertEqual(motivos, [])
        with X._admissao():
            self.assertEqual(X.reconciliar_pendente()["n"], 1)
        self.assertIsNone(X._estado()["pendente"])
        self.assertEqual(len(self.mundo.chamadas), chamadas)  # sem acessar o Unreal
        self.assertEqual(len(X.tentativas_validas()), 1)  # histórico preservado

    def test_a04_sem_conclusao_segura_inequivoca_o_bloqueio_continua(self):
        for nome, final in (("cena não comprovada", {"cena_ok": None}), ("de outra execução", {"execucao": "outra"})):
            with self.subTest(caso=nome):
                for f in ("tentativas.jsonl", "estado.json"):
                    if os.path.exists(os.path.join(self.pasta, f)):
                        os.remove(os.path.join(self.pasta, f))
                self._queda_entre_resultado_e_limpeza_da_pendencia(**final)
                self.assertTrue(CP.inseguranca(self.pasta))
                with X._admissao():
                    self.assertIsNone(X.reconciliar_pendente())
                self.assertIsNotNone(X._estado()["pendente"])


class Guarda(unittest.TestCase):
    def setUp(self):
        self.p = Path(tempfile.mkdtemp(prefix="v006_guarda_"))

    def linhas(self, *ls):
        (self.p / "tentativas.jsonl").write_text("".join(json.dumps(x) + "\n" for x in ls), encoding="utf-8")

    def test_a28_inicio_repetido_sem_novo_fim_bloqueia(self):
        ini, fim = {"tipo_linha": "tentativa_inicio", "n": 1}, {"tipo_linha": "tentativa", "n": 1, "cena_ok": True}
        self.linhas(ini, fim)
        self.assertEqual(CP.inseguranca(self.p), [])  # controle: um início e um fim seguro
        self.linhas(ini, fim, ini)
        self.assertTrue(CP.inseguranca(self.p)[0].startswith("estado_inseguro"))
        self.linhas(ini, fim, ini, fim)  # número reutilizado: a correspondência deixou de ser exclusiva
        self.assertTrue(CP.inseguranca(self.p))
        self.linhas(ini, fim, fim)
        self.assertTrue(CP.inseguranca(self.p))

    def test_a28_fim_de_outra_execucao_nao_fecha_o_inicio(self):
        self.linhas({"tipo_linha": "tentativa_inicio", "n": 1, "execucao": "a"},
                    {"tipo_linha": "tentativa", "n": 1, "cena_ok": True, "execucao": "b"})
        self.assertTrue(CP.inseguranca(self.p))

    def test_a28_inicio_em_curso_com_dono_vivo_continua_seguro(self):
        self.linhas({"tipo_linha": "tentativa_inicio", "n": 1})
        (self.p / "estado.json").write_text(json.dumps({"pendente": {"n": 1, "pid": os.getpid()}}), encoding="utf-8")
        self.assertEqual(CP.inseguranca(self.p), [])
        with patch.object(P, "estado_processo", return_value=P.DESCONHECIDO):
            self.assertTrue(CP.inseguranca(self.p))


class Painel(unittest.TestCase):
    def test_f05_dois_cliques_ao_mesmo_tempo_dao_um_lancamento(self):
        import painel as PN
        lancados, juntos = [], threading.Barrier(2)

        class Proc:
            def poll(self):
                return None

        def popen(cmd, **k):
            lancados.append(cmd)
            return Proc()

        def ocupadas(*a, **k):
            r = sorted(x for x, p in PN.LANCADOS.items() if p.poll() is None)
            try:
                juntos.wait(0.5)  # os dois cliques veriam "livre" ao mesmo tempo, se checar e lançar não fosse uma coisa só
            except threading.BrokenBarrierError:
                pass
            return r
        res = []
        with patch.object(PN, "LANCADOS", {}), patch.object(PN, "ocupadas", ocupadas), \
                patch.object(PN, "dados_unreal", lambda *a: None), patch.object(PN, "vigia_agora", lambda: None), \
                patch.object(PN, "rodada_atual", lambda: None), patch.object(PN.subprocess, "Popen", popen):
            ts = [threading.Thread(target=lambda: res.append(PN.rodar_rotina("bateria"))) for _ in range(2)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(10)
        self.assertEqual(len(lancados), 1, res)
        self.assertEqual(sorted(r["ok"] for r in res), [False, True])

    def test_f05_erro_no_lancamento_nao_deixa_a_rotina_presa(self):
        import painel as PN

        def popen(cmd, **k):
            raise OSError("falhou")
        with patch.object(PN, "LANCADOS", {}), patch.object(PN, "dados_unreal", lambda *a: None), \
                patch.object(PN, "vigia_agora", lambda: None), patch.object(PN, "rodada_atual", lambda: None), \
                patch.object(PN, "ocupadas", lambda *a, **k: sorted(PN.LANCADOS)), patch.object(PN.subprocess, "Popen", popen):
            r = PN.rodar_rotina("bateria")
            self.assertFalse(r["ok"])
            self.assertEqual(PN.LANCADOS, {})


if __name__ == "__main__":
    unittest.main()
