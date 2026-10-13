"""Laboratório Director: fixtures offline declaradas, nunca prova Unreal."""
# pyright: reportMissingImports=false
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'src'))
import director_noite as N  # noqa: E402
import fila_executor as X  # noqa: E402
import vigia_dev as V  # noqa: E402
from unreal_macros import campanha as CP, fila as F, receita as R  # noqa: E402
from testes_director_noite import plano, SCRATCH  # noqa: E402


class Laboratorio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=SCRATCH)
        self.addCleanup(self.tmp.cleanup)
        self.plano: dict = dict(plano(), modo='experimental')
        self.c = N.preparar('objetivo literal de laboratório', self.plano, 1, base=Path(self.tmp.name))
        self.p = Path(self.c['pasta'])
        CP.gravar(self.p, 'AUTORIZACAO.json', {'id': self.c['id'], 'integridade': self.c['integridade']})
        self.r: dict = {'linhagem': 'A', 'tipo': 'exploracao', 'hipotese': 'fixture offline',
                  'passos': [{'papel': papel, 'clipe': 'fixture_' + papel} for papel in F.PAPEIS]}

    def linha(self, **kw):
        t = dict(tipo_linha='tentativa', n=1, linhagem='A', tipo='exploracao', nota=0,
                 assinatura=R.assinatura(self.r), receita=self.r['passos'],
                 avaliacao={'valida': True}, cena_ok=True, condicoes=dict(X.CONDICOES))
        t.update(kw)
        with (self.p / 'tentativas.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(t) + '\n')
        return t

    def test_tres_zeros_admitem_nova_hipotese_sem_mudar_regua(self):
        for n in (1, 2, 3):
            self.linha(n=n)
        alternativa: dict = dict(self.r, linhagem='B', passos=[dict(x) for x in self.r['passos']])
        alternativa['passos'][1]['clipe'] += '_alternativa'
        with patch.object(X, 'PASTA', str(self.p)), patch.dict(os.environ, {'FILA_CENA': str(self.p / 'CENA.md')}):
            _, motivos = X.preparar(alternativa)
        self.assertEqual(motivos, [], motivos)
        self.assertTrue(N.estado(self.p)['sucesso_medido'])
        self.assertEqual(N.estado(self.p)['diagnostico'], 'sucesso_medido')

    def test_vigia_fechada_nao_fica_bloqueada_e_inseguranca_prevalece(self):
        obs = {'log': {}, 'saude': {}, 'rodada': {'terminou': True}, 'pausa': False,
               'campanha': self.c, 'bloqueios_campanha': ['campanha já tem fechamento']}
        d = V.decidir_campanha(obs, {}, 0, V.LIM)
        self.assertEqual(d['estado'], 'terminou')
        obs['bloqueios_campanha'] = ['estado_inseguro: restauração não comprovada']
        self.assertEqual(V.decidir_campanha(obs, {}, 0, V.LIM)['estado'], 'estado_inseguro')

    def test_lacuna_essencial_nao_bloqueia_recorte_mas_nunca_aprova_objetivo(self):
        p = dict(self.plano, cobertura=self.plano['cobertura'] + [
            {'requisito': 'colisão com porta', 'essencial': True, 'criterios': [], 'ausente': 'sem sensor'}])
        c = N.preparar('andar sem colidir com porta', p, 1, base=Path(self.tmp.name))
        self.assertTrue(c['executavel'], c)
        self.p = Path(c['pasta'])
        for n in (1, 2, 3):
            self.linha(n=n)
        s = N.estado(self.p)
        self.assertTrue(s['recorte_medido'])
        self.assertFalse(s['sucesso_medido'])
        self.assertEqual(len(s['lacunas']), 1)
        formal = N.preparar('mesmo pedido', dict(p, modo='formal'), 1, base=Path(self.tmp.name))
        self.assertFalse(formal['executavel'])

    def test_personagem_nao_suportado_recusa_antes_de_unreal(self):
        p = dict(self.plano, cena=dict(self.plano['cena'], personagem='PC_03_Marcos'))
        c = N.preparar('Marcos levanta', p, 1, base=Path(self.tmp.name))
        q = Path(c['pasta'])
        CP.gravar(q, 'AUTORIZACAO.json', {'id': c['id'], 'integridade': c['integridade']})
        with patch.object(X, 'PASTA', str(q)), patch.dict(os.environ, {'FILA_CENA': str(q / 'CENA.md')}), \
             patch.object(X, 'Unreal') as unreal:
            _, motivos = X.preparar(self.r)
            self.assertTrue(any('personagem' in m for m in motivos), motivos)
            self.assertIn('recusada', X.executar(self.r, 1))
            self.assertFalse(unreal.called)

    def test_repeticoes_de_personagens_distintos_nao_somam_sucesso(self):
        self.linha(n=1)
        self.linha(n=2, condicoes=dict(X.CONDICOES, personagem='PC_03_Marcos'))
        self.linha(n=3)
        self.assertFalse(N.estado(self.p)['sucesso_medido'])

    def test_fila_retomada_relatorio_e_fechamento_com_progresso(self):
        fila = [{'id': 'h1', 'hipotese': 'novo giro evita salto', 'funcionalidade': 'turn_deg',
                 'proximo_teste': 'comparar 0 e 10 graus'}]
        N.planejar(self.p, fila)
        self.assertEqual(N.estado(self.p)['fila_hipoteses'], fila)
        (self.p / 'FECHAMENTO.md').write_text('três zeros não encerram laboratório', encoding='utf-8')
        self.assertEqual(CP.guarda(self.p), [])
        with self.assertRaisesRegex(ValueError, 'hipóteses'):
            N.fechar(self.p, 'esgotamento', 'ainda há teste útil')
        self.linha(experimento='h1')
        N.concluir(self.p, {'id': 'h1', 'classe': 'medido', 'tentativas': [1],
                          'descoberta': 'fixture passou', 'reproducao': 'receita fixture', 'evidencias': ['tentativas.jsonl']})
        with patch.object(N, 'pasta_de', return_value=self.p):
            s = N.estado(N.pasta_de(self.c['id']))
        self.assertEqual(s['fila_hipoteses'], [])
        self.assertEqual(s['experimentos_distintos'], 1)
        self.assertEqual(s['funcionalidades_testadas'], ['turn_deg'])
        self.assertGreater(s['tempo_restante_s'], 0)
        out = N.relatorio(self.p)
        data = json.loads(Path(out['json']).read_text(encoding='utf-8'))
        self.assertEqual(data['experimentos'][0]['reproducao'], 'receita fixture')
        N.fechar(self.p, 'esgotamento', 'alternativas relevantes descartadas; evidências no laboratório')
        self.assertIn('fechamento', ' '.join(CP.guarda(self.p)))

    def test_fila_maior_que_cinco_e_resultado_sem_evidencia_recusados(self):
        with self.assertRaises(ValueError):
            N.planejar(self.p, [{'id': str(i), 'hipotese': 'h', 'funcionalidade': 'f', 'proximo_teste': 't'} for i in range(6)])
        N.planejar(self.p, [{'id': 'h1', 'hipotese': 'h', 'funcionalidade': 'f', 'proximo_teste': 't'}])
        with self.assertRaises(ValueError):
            N.concluir(self.p, {'id': 'h1', 'classe': 'medido', 'tentativas': [], 'descoberta': 'inventada'})

    def test_python_auxiliar_real_guarda_saida_e_nao_altera_director(self):
        script = self.p / 'scripts/calcular.py'
        script.parent.mkdir()
        script.write_text('print(json.dumps({"media": statistics.mean(dados["valores"])}))', encoding='utf-8')
        CP.gravar(self.p, 'dados.json', {'valores': [2, 4, 6]})
        antes = CP.sha(ROOT / 'tools/fila_executor.py')
        r = N.python_auxiliar(self.p, script, self.p / 'dados.json')
        self.assertEqual(r['codigo'], 0)
        saida = json.loads((self.p / r['saida']).read_text(encoding='utf-8'))
        self.assertEqual(saida['media'], 4)
        self.assertEqual(CP.sha(ROOT / 'tools/fila_executor.py'), antes)
        script.write_text('import socket\nsocket.socket()', encoding='utf-8')
        with self.assertRaises(ValueError):
            N.python_auxiliar(self.p, script, self.p / 'dados.json')
        with self.assertRaises(ValueError):
            N.python_auxiliar(self.p, ROOT / 'tools/fila_executor.py', self.p / 'dados.json')

    def test_personagem_em_fixo_e_script_perigoso_nao_sao_contornados(self):
        p = dict(self.plano, cena=dict(self.plano['cena'], fixo='personagem PC_03_Marcos'))
        c = N.preparar('Marcos', p, 1, base=Path(self.tmp.name))
        q = Path(c['pasta'])
        CP.gravar(q, 'AUTORIZACAO.json', {'id': c['id'], 'integridade': c['integridade']})
        with patch.object(X, 'PASTA', str(q)), patch.dict(os.environ, {'FILA_CENA': str(q / 'CENA.md')}):
            self.assertTrue(X.guarda_personagem())
        from unreal_macros import python_auxiliar as A
        for texto in ['open("fora.txt", "w")', 'dados.__class__', 'getattr(json, "loads")',
                      'import os', '__import__("socket")', 'eval("1+1")', 'while True: pass']:
            with self.subTest(texto=texto), self.assertRaises(ValueError):
                A.validar(texto)

    def test_fechamento_precoce_nao_para_vigia_e_controles_ainda_bloqueiam(self):
        (self.p / 'FECHAMENTO.md').write_text('sucesso inicial', encoding='utf-8')
        self.assertFalse(V.ler_rodada(str(self.p))['terminou'])
        (self.p / 'PAUSA').write_text('usuário', encoding='utf-8')
        self.assertTrue(any('pausada' in x for x in CP.guarda(self.p)))
        self.linha(cena_ok=False, classe_erro='estado_parcial')
        self.assertTrue(CP.guarda(self.p)[0].startswith('estado_inseguro'))


    def test_tempo_efetivo_nao_confunde_prazo_com_execucao(self):
        self.linha(quando_inicio='2026-10-10T00:00:00', quando='2026-10-10T00:00:12')
        self.linha(n=2)
        s = N.estado(self.p)
        self.assertEqual(s['tempo_execucao_medido_s'], 12)
        self.assertEqual(s['duracoes_ausentes'], 1)

    def test_personagem_fixo_nao_e_sobrescrito_pela_receita(self):
        with patch.dict(os.environ, {'FILA_CENA': str(self.p / 'CENA.md')}):
            self.assertEqual(X.guarda_personagem(dict(self.r, personagem=X.CONDICOES['personagem'])), [])
        p = dict(self.plano, cena=dict(self.plano['cena'], personagem='PC_03_Marcos'))
        c = N.preparar('Marcos', p, 1, base=Path(self.tmp.name))
        q = Path(c['pasta'])
        CP.gravar(q, 'AUTORIZACAO.json', {'id': c['id'], 'integridade': c['integridade']})
        with patch.object(X, 'PASTA', str(q)), patch.dict(os.environ, {'FILA_CENA': str(q / 'CENA.md')}):
            self.assertTrue(X.guarda_personagem(dict(self.r, personagem='SK_YBot')))
        p = dict(self.plano, cena=dict(self.plano['cena'], fixo='PC_03_Marcos', personagem='SK_YBot'))
        c = N.preparar('Marcos', p, 1, base=Path(self.tmp.name))
        with patch.dict(os.environ, {'FILA_CENA': str(Path(c['pasta']) / 'CENA.md')}):
            self.assertTrue(X.guarda_personagem(self.r))

    def test_laboratorio_nao_muda_modo_formal_e_relatorio_contem_reproducao(self):
        c = N.preparar('formal', dict(self.plano, modo='formal'), 1, base=Path(self.tmp.name))
        q = Path(c['pasta'])
        CP.gravar(q, 'AUTORIZACAO.json', {'id': c['id'], 'integridade': c['integridade']})
        with self.assertRaisesRegex(ValueError, 'experimental'):
            N.planejar(q, [])
        with self.assertRaisesRegex(ValueError, 'experimental'):
            N.fechar(q, 'esgotamento', 'não misturar')
        r = N.relatorio(self.p)
        texto = Path(r['markdown']).read_text(encoding='utf-8')
        self.assertIn('Experimentos, descobertas e reprodução', texto)
        self.assertIn('Python auxiliar', texto)

    def test_retomada_em_processo_novo_preserva_objetivo_prazo_e_fila(self):
        import subprocess
        fila = [{'id': 'h1', 'hipotese': 'comparar giro', 'funcionalidade': 'turn_deg', 'proximo_teste': 'medir giro'}]
        N.planejar(self.p, fila)
        codigo = ('import sys,json; from pathlib import Path; sys.path.insert(0,sys.argv[1]); '
                  'import director_noite as N; p=Path(sys.argv[2]); '
                  'print(json.dumps(dict(estado=N.estado(p),objetivo=(p/"OBJETIVO.txt").read_text(encoding="utf-8"))))')
        proc = subprocess.run([sys.executable, '-I', '-c', codigo, str(ROOT / 'tools'), str(self.p)],
                              capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        r = json.loads(proc.stdout)
        self.assertEqual(r['objetivo'], 'objetivo literal de laboratório')
        self.assertEqual(r['estado']['fim_ts'], self.c['fim_ts'])
        self.assertEqual(r['estado']['fila_hipoteses'], fila)
        self.assertEqual(r['estado']['bloqueios'], [])

    def test_resultado_medido_exige_reproducao_e_preserva_funcionalidade_planejada(self):
        N.planejar(self.p, [{'id': 'h1', 'hipotese': 'h', 'funcionalidade': 'turn_deg', 'proximo_teste': 't'}])
        self.linha(experimento='h1')
        r = {'id': 'h1', 'classe': 'medido', 'tentativas': [1], 'descoberta': 'd', 'evidencias': ['tentativas.jsonl']}
        with self.assertRaisesRegex(ValueError, 'reprodução'):
            N.concluir(self.p, r)
        r.update(reproducao='receita fixture', funcionalidade='inventada')
        with self.assertRaisesRegex(ValueError, 'metadados'):
            N.concluir(self.p, r)

    def test_memoria_malformada_bloqueia_e_nao_apaga_evidencias(self):
        CP.gravar(self.p, 'LABORATORIO.json', {'id': self.c['id'], 'fila': ['inválida'], 'experimentos': [], 'scripts': []})
        self.assertTrue(CP.guarda(self.p)[0].startswith('estado_inseguro'))
        self.assertEqual(N.estado(self.p)['diagnostico'], 'estado_inseguro')
        CP.gravar(self.p, 'LABORATORIO.json', {'id': self.c['id'], 'fila': [], 'experimentos': [], 'scripts': []})
        (self.p / 'ENCERRAMENTO.json').write_text('[]', encoding='utf-8')
        self.assertTrue(CP.guarda(self.p)[0].startswith('estado_inseguro'))
        self.assertEqual(N.estado(self.p)['diagnostico'], 'estado_inseguro')

    def test_python_registra_timeout_mesmo_se_prazo_terminar(self):
        import subprocess
        script = self.p / 'scripts/calcular.py'
        script.parent.mkdir()
        script.write_text('print(dados)', encoding='utf-8')
        CP.gravar(self.p, 'dados.json', {})
        import time
        real = time.time
        expirado = [False]
        def expirar(*args, **kw):
            expirado[0] = True
            raise subprocess.TimeoutExpired(args[0], 30)
        with patch('subprocess.run', side_effect=expirar), patch('time.time', side_effect=lambda: self.c['fim_ts'] + 1 if expirado[0] else real()):
            r = N.python_auxiliar(self.p, script, self.p / 'dados.json')
        self.assertEqual(r['codigo'], 124)
        self.assertEqual(CP.laboratorio(self.p)['scripts'][0]['codigo'], 124)


if __name__ == '__main__':
    unittest.main()
