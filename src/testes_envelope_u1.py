"""Regressões permanentes U1; envelope real, cliente/trava controlados, sem Unreal."""
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from unreal_macros import macros as M  # noqa: E402


class ClienteFalso:
    def __init__(self):
        self.log = []
        self.prazo = None

    def call(self, toolset, tool, **kwargs):
        self.log.append((tool, 0, True))
        if tool == 'IsPIERunning':
            return False
        if tool == 'GetCameraTransform':
            return {'location': {}, 'rotation': {}}
        return None


class EnvelopeU1(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.tmp = self.stack.enter_context(tempfile.TemporaryDirectory(prefix='v005-envelope-'))
        self.stack.enter_context(patch.dict(os.environ, UNREAL_MACROS_OFFLINE='1'))
        self.stack.enter_context(patch.object(M, 'RAIZ_WORK', self.tmp))
        self.stack.enter_context(patch.object(M, '_pilha', {'n': 0, 'cam': None, 'trava': False}))
        self.stack.enter_context(patch.object(M, '_ambiente', return_value={'teste': True}))
        self.pegar = self.stack.enter_context(patch.object(M, '_pegar_trava'))
        self.soltar = self.stack.enter_context(patch.object(M, '_soltar_trava'))
        self.stack.enter_context(patch.object(M, 'pausa_ativa', return_value=None))

    def conferir_falha_guardada(self, rel, motivo):
        self.assertFalse(rel['ok'])
        self.assertIn(motivo, rel['bloqueio'])
        import json
        saved = json.loads((Path(self.tmp) / 'relatorios' / (rel['id'] + '.json')).read_text(encoding='utf-8'))
        self.assertFalse(saved['ok'])
        self.assertEqual(saved['bloqueio'], rel['bloqueio'])
        self.assertEqual(M._pilha['n'], 0)

    def test_j1_independente_nao_conecta(self):
        def operacao(rel):
            rel['medidas']['executada'] = True
        operacao._usa_unreal = False
        with patch.object(M, 'cliente', side_effect=AssertionError('conexao indevida')) as cliente:
            rel = M.macro(operacao)()
        self.assertTrue(rel['ok'])
        self.assertTrue(rel['medidas']['executada'])
        cliente.assert_not_called()
        self.pegar.assert_not_called()
        self.soltar.assert_not_called()
        self.assertEqual(rel['chamadas'], 0)

    def test_a1_conexao_indisponivel_vira_relatorio(self):
        def operacao(rel):
            self.fail('operacao nao deve executar sem cliente')
        with patch.object(M, 'cliente', side_effect=ConnectionError('cliente indisponivel')):
            rel = M.macro(operacao)()
        self.conferir_falha_guardada(rel, 'cliente indisponivel')

    def test_a1_preparacao_indisponivel_vira_relatorio(self):
        def operacao(rel):
            self.fail('operacao nao deve executar com preparacao falha')
        fake = ClienteFalso()
        with patch.object(M, 'cliente', return_value=fake), patch.object(M, '_ambiente', side_effect=OSError('preparacao indisponivel')):
            rel = M.macro(operacao)()
        self.conferir_falha_guardada(rel, 'preparacao indisponivel')

    def test_dependente_usa_cliente_e_preserva_limpeza(self):
        fake = ClienteFalso()
        def operacao(rel):
            self.assertIsNotNone(fake.prazo)
            rel['medidas']['executada'] = True
        with patch.object(M, 'cliente', return_value=fake) as cliente:
            rel = M.macro(operacao)()
        self.assertTrue(rel['ok'])
        cliente.assert_called()
        self.pegar.assert_called_once_with('operacao')
        self.soltar.assert_called_once_with()
        self.assertIsNone(fake.prazo)
        self.assertEqual(M._pilha, {'n': 0, 'cam': None, 'trava': False})
        self.assertEqual([x[0] for x in fake.log], ['IsPIERunning', 'GetCameraTransform', 'SetCameraTransform'])
        self.assertEqual(rel['chamadas'], 3)

    def test_erro_durante_operacao_guardado_e_limpo(self):
        fake = ClienteFalso()
        def operacao(rel):
            raise ValueError('operacao falhou')
        with patch.object(M, 'cliente', return_value=fake):
            rel = M.macro(operacao)()
        self.conferir_falha_guardada(rel, 'operacao falhou')
        self.soltar.assert_called_once_with()
        self.assertIsNone(fake.prazo)


    def test_serializacao_falha_vira_relatorio_minimo(self):
        def operacao(rel):
            self.fail('preparacao falha nao pode executar')
        operacao._usa_unreal = False
        with patch.object(M, '_serializavel', side_effect=ValueError('serializacao falhou')), patch.object(M, '_guardar_relatorio') as guardar:
            rel = M.macro(operacao)(object())
        self.assertFalse(rel['ok'])
        self.assertIn('serializacao falhou', rel['bloqueio'])
        self.assertEqual(rel['chamada'], {'args': [], 'kwargs': {}})
        guardar.assert_called_once_with(rel)
        self.assertEqual(M._pilha['n'], 0)

    def test_pausa_recusa_antes_de_conectar(self):
        def operacao(rel):
            self.fail('nao pode executar pausada')
        with patch.object(M, 'pausa_ativa', return_value={'motivo': 'teste'}), patch.object(M, 'cliente', side_effect=AssertionError('conexao indevida')) as cliente:
            rel = M.macro(operacao)()
        self.conferir_falha_guardada(rel, 'PAUSADO')
        self.assertEqual(rel['espera']['tipo'], 'pausa')
        cliente.assert_not_called()
        self.pegar.assert_not_called()

    def test_dependente_dentro_de_independente_toma_e_limpa_trava(self):
        fake = ClienteFalso()
        def interna(rel):
            self.assertIsNotNone(fake.prazo)
        executar_interna = M.macro(interna)
        def externa(rel):
            rel['medidas']['interna'] = executar_interna()
        externa._usa_unreal = False
        with patch.object(M, 'cliente', return_value=fake):
            rel = M.macro(externa)()
        self.assertTrue(rel['ok'])
        self.assertTrue(rel['medidas']['interna']['ok'])
        self.pegar.assert_called_once_with('interna')
        self.soltar.assert_called_once_with()
        self.assertIsNone(fake.prazo)
        self.assertEqual(M._pilha, {'n': 0, 'cam': None, 'trava': False})

    def test_logs_independente_incluem_dependente_aninhada(self):
        fake = ClienteFalso()
        fake.log.append(('historico_anterior', 0, True))
        def interna(rel):
            pass
        executar = M.macro(interna)
        def externa(rel):
            rel['medidas']['interna'] = executar()
        externa._usa_unreal = False
        with patch.object(M, '_cliente', fake), patch.object(M, 'cliente', return_value=fake):
            rel = M.macro(externa)()
        self.assertTrue(rel['medidas']['interna']['ok'])
        self.assertEqual(rel['medidas']['interna']['chamadas'], 3)
        self.assertEqual(rel['chamadas'], 3)

    def test_dependente_aninhada_nao_limpa_prazo_do_pai(self):
        fake = ClienteFalso()
        def interna(rel):
            self.assertIsNotNone(fake.prazo)
        executar_interna = M.macro(interna)
        def externa(rel):
            prazo = fake.prazo
            rel['medidas']['interna'] = executar_interna()
            self.assertEqual(fake.prazo, prazo)
        with patch.object(M, 'cliente', return_value=fake):
            rel = M.macro(externa)()
        self.assertTrue(rel['ok'])
        self.assertTrue(rel['medidas']['interna']['ok'])
        self.pegar.assert_called_once_with('externa')
        self.soltar.assert_called_once_with()

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(EnvelopeU1)
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f'envelope_u1: {passed}/{result.testsRun}')
    sys.exit(0 if result.testsRun and result.wasSuccessful() else 1)
