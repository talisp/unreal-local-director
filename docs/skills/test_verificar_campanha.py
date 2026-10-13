"""Regressões objetivas de checkpoint; não certificam interpretação."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('cp', Path(__file__).with_name('verificar_campanha.py'))
assert SPEC and SPEC.loader


class Checkpoint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cp = self.root / 'CHECKPOINT-001.md'
        self.cp.write_text('Checkpoint curto. Leitura e hash são operações diferentes.', encoding='utf-8')
        (self.root / 'pedido.md').write_text('entrada', encoding='utf-8')
        self.ctx = {'root': str(self.root), 'allowed_refs': ['pedido.md'], 'reads': ['pedido.md'],
                    'hashes_only': [], 'hashes_before': {'pedido.md': 'abc'}, 'hashes_after': {'pedido.md': 'abc'},
                    'duration_s': 12.0, 'budget_s': 20, 'word_limit': 250,
                    'skill_version': '0.4.0', 'skill_sha256': 'a'*64, 'director_commit': 'b'*40}
        self.data = {'schema_version': 1, 'skill_version': '0.4.0', 'skill_sha256': 'a'*64,
                     'director_commit': 'b'*40, 'instrument_version': '0.1.0',
                     'evidence_reads': ['pedido.md'], 'evidence_hashes': [], 'references': ['pedido.md'],
                     'changed_files': [], 'duration_s': 12.0, 'budget_s': 20, 'source_checkpoint': None,
                     'status': 'PAUSADO', 'next_step': 'Retomar lote separado.'}
        spec = SPEC
        assert spec and spec.loader
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def verify(self):
        self.cp.with_suffix('.json').write_text(json.dumps(self.data), encoding='utf-8')
        return self.module.verificar_checkpoint(self.cp, self.ctx)

    def test_controle_objetivo_nao_autoaprova_prosa(self):
        r = self.verify()
        self.assertTrue(r['ok_objetivo'], r)
        self.assertTrue(r['revisao_semantica_pendente'])

    def test_mudanca_alegada_sem_diferenca_recusada(self):
        self.data['changed_files'] = ['pedido.md']
        self.assertFalse(self.verify()['ok_objetivo'])

    def test_mudanca_medida_aceita(self):
        self.ctx['hashes_after']['pedido.md'] = 'def'
        self.data['changed_files'] = ['pedido.md']
        self.assertTrue(self.verify()['ok_objetivo'])

    def test_hash_nao_e_leitura(self):
        self.ctx['reads'] = []
        self.ctx['hashes_only'] = ['pedido.md']
        self.assertFalse(self.verify()['ok_objetivo'])

    def test_referencia_inventada(self):
        self.data['references'] = ['checkpoint-contract.md']
        self.assertFalse(self.verify()['ok_objetivo'])

    def test_fora_da_raiz(self):
        self.data['references'] = ['../fora.md']
        self.assertFalse(self.verify()['ok_objetivo'])

    def test_limite_palavras(self):
        self.cp.write_text(' '.join(['p']*251), encoding='utf-8')
        self.assertFalse(self.verify()['ok_objetivo'])

    def test_orcamento_estourado(self):
        self.ctx['duration_s'] = 21
        self.data['duration_s'] = 21
        self.assertFalse(self.verify()['ok_objetivo'])

    def test_duracao_inventada(self):
        self.data['duration_s'] = 10
        self.assertFalse(self.verify()['ok_objetivo'])

    def test_duracao_desconhecida_permitida_sem_afirmacao(self):
        self.data['duration_s'] = None
        self.assertTrue(self.verify()['ok_objetivo'])

    def test_identidade_divergente(self):
        self.data['skill_sha256'] = 'c'*64
        self.assertFalse(self.verify()['ok_objetivo'])

    def test_legacy_sem_json_historico(self):
        r = self.module.verificar_checkpoint(self.cp, self.ctx)
        self.assertFalse(r['ok_objetivo'])
        self.assertTrue(r['historico'])

    def test_tipos_invalidos_sem_excecao(self):
        for key,value in [('schema_version', True),('references',17),('evidence_reads',[1]),('duration_s',True),('duration_s',float('nan'))]:
            original = self.data[key]
            self.data[key] = value
            self.assertFalse(self.verify()['ok_objetivo'], key)
            self.data[key] = original

    def test_json_truncado(self):
        self.cp.with_suffix('.json').write_text('{',encoding='utf-8')
        self.assertFalse(self.module.verificar_checkpoint(self.cp,self.ctx)['ok_objetivo'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
