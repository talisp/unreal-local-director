"""Regressões U2: API nativa e consumidores; sem Unreal ou processos Hermes."""
from contextlib import ExitStack
import datetime as dt
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools'))
import fila_executor as X  # noqa: E402  # pyright: ignore[reportMissingImports]
import rotina as R  # noqa: E402  # pyright: ignore[reportMissingImports]

VIVO, MORTO, DESCONHECIDO = 'VIVO', 'MORTO', 'DESCONHECIDO'


class ProcessosU2(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.tmp = self.stack.enter_context(tempfile.TemporaryDirectory(prefix='v005-pid-'))
        self.stack.enter_context(patch.object(X, 'PASTA', self.tmp))
        self.stack.enter_context(patch.object(X, 'depois_da_hora', return_value=False))
        self.stack.enter_context(patch.object(X, '_cena', return_value=None))

    def consulta(self, pid):
        fn = getattr(X, '_pid_estado', None) or X._pid_vivo
        return fn(pid)

    def pendente(self):
        X._gravar_estado({'proximo_n': 2, 'pendente': {'n': 1, 'pid': os.getpid(), 'seq': '/Game/TESTE.TESTE'}, 'fechadas': {}})
        return (Path(self.tmp) / 'estado.json').read_bytes()

    def mock_consulta(self, estado):
        nome = '_pid_estado' if hasattr(X, '_pid_estado') else '_pid_vivo'
        return patch.object(X, nome, return_value=estado)

    def test_atual_vivo_sem_tasklist(self):
        with patch.object(subprocess, 'run', side_effect=AssertionError('tasklist proibido')):
            self.assertEqual(self.consulta(os.getpid()), VIVO)

    def test_processo_real_encerrado(self):
        p = subprocess.Popen([sys.executable, '-c', 'pass'])
        p.wait(timeout=15)
        self.assertEqual(self.consulta(p.pid), MORTO)

    def test_consulta_so_falha_desconhecido(self):
        P = importlib.import_module('unreal_macros.processos')
        alvo = '_consultar_windows' if os.name == 'nt' else '_consultar_posix'
        with patch.object(P, alvo, side_effect=OSError('falha SO')):
            self.assertEqual(P.estado_processo(os.getpid()), DESCONHECIDO)

    def test_pid_invalido_nao_consulta_so(self):
        P = importlib.import_module('unreal_macros.processos')
        for pid in (None, True, False, -1, 0, 1.5, 'lixo', '1.5', 2**32):
            with self.subTest(pid=pid):
                self.assertEqual(P.estado_processo(pid), DESCONHECIDO)

    def test_api_windows_estados_e_handle_fechado(self):
        P = importlib.import_module('unreal_macros.processos')
        k = Mock()
        k.OpenProcess.return_value = 123
        for codigo, esperado in ((0, MORTO), (258, VIVO), (0xffffffff, DESCONHECIDO), (12, DESCONHECIDO)):
            k.reset_mock()
            k.WaitForSingleObject.return_value = codigo
            with patch.object(P, '_kernel32', return_value=k):
                self.assertEqual(P._consultar_windows(123), esperado)
            k.CloseHandle.assert_called_once_with(123)

    def test_api_windows_open_falha_nao_inventa_morte(self):
        P = importlib.import_module('unreal_macros.processos')
        k = Mock()
        k.OpenProcess.return_value = None
        for erro, esperado in ((87, MORTO), (5, DESCONHECIDO), (8, DESCONHECIDO), (0, DESCONHECIDO)):
            with patch.object(P, '_kernel32', return_value=k), patch.object(P, '_ultimo_erro', return_value=erro):
                self.assertEqual(P._consultar_windows(123), esperado)

    def test_reserva_desconhecida_preservada_e_recusa_explicita(self):
        antes = self.pendente()
        with self.mock_consulta(DESCONHECIDO):
            self.assertIsNone(X.recuperar_pendente())
            _, motivos = X.preparar({})
        self.assertTrue(any('DESCONHECIDO' in m for m in motivos), motivos)
        self.assertFalse(any('ainda está rodando' in m for m in motivos))
        self.assertEqual((Path(self.tmp) / 'estado.json').read_bytes(), antes)
        self.assertFalse((Path(self.tmp) / 'tentativas.jsonl').exists())

    def test_recupera_so_morto(self):
        self.pendente()
        with self.mock_consulta(MORTO):
            self.assertEqual(X.recuperar_pendente()['n'], 1)
        self.assertIsNone(X._estado()['pendente'])

    def test_resultado_desconhecido_nao_anuncia_rodando(self):
        self.pendente()
        out = io.StringIO()
        with self.mock_consulta(DESCONHECIDO), patch('sys.stdout', out):
            self.assertEqual(X.main(['resultado', '1']), 0)
        res = json.loads(out.getvalue())
        self.assertEqual(res['processo'], DESCONHECIDO)
        self.assertNotEqual(res['status'], 'rodando')

    def test_morte_entre_consultas_nao_e_rotulada_desconhecida(self):
        self.pendente()
        out = io.StringIO()
        nome = '_pid_estado' if hasattr(X, '_pid_estado') else '_pid_vivo'
        with patch.object(X, nome, side_effect=[DESCONHECIDO, MORTO]), patch('sys.stdout', out):
            # v0.0.6 (L2, A03): a CONSULTA 'resultado' não recupera nem escreve mais; a 1ª consulta do cenário
            # (a recuperação, que vê DESCONHECIDO e preserva a reserva) passou a ser feita aqui, explícita.
            # As asserções são as mesmas: vale a consulta mais recente (MORTO) e a reserva continua lá.
            self.assertIsNone(X.recuperar_pendente())
            self.assertEqual(X.main(['resultado', '1']), 0)
        res = json.loads(out.getvalue())
        self.assertEqual(res['processo'], MORTO)
        self.assertIn('MORTO', res['status'])
        self.assertNotIn('DESCONHECIDO', res['status'])
        self.assertIsNotNone(X._estado()['pendente'])

    def test_rotina_estados_explicitos_e_prazo(self):
        agora = dt.datetime(2026, 10, 9, 3)
        prazo = agora + dt.timedelta(hours=1)
        lanc = {'vigia_pid': 1, 'sessao_pid': 2, 'modo': 'noite'}
        for a in (VIVO, MORTO, DESCONHECIDO):
            for b in (VIVO, MORTO, DESCONHECIDO):
                def consulta(pid):
                    return {1: a, 2: b}[pid]
                res = R.rodada_acabou(self.tmp, lanc, agora, prazo, consulta)
                if a == b == MORTO:
                    self.assertIn('pararam', res)
                else:
                    self.assertIsNone(res)
                fim_no_prazo = R.rodada_acabou(self.tmp, lanc, prazo, prazo, consulta)
                self.assertIn('pararam' if a == b == MORTO else 'horário', fim_no_prazo)

    def test_resumo_rotina_desconhecido_nao_anuncia_rodando(self):
        with patch.object(R, '_pid_estado', return_value=DESCONHECIDO):
            texto = R.md_unreal(self.tmp, {'modo': 'noite', 'vigia_pid': 1, 'sessao_pid': 2}, None)
        self.assertIn('DESCONHECIDO', texto)
        self.assertNotIn('ainda rodando', texto)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProcessosU2)
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f'processos_u2: {passed}/{result.testsRun}')
    sys.exit(0 if result.testsRun and result.wasSuccessful() else 1)
