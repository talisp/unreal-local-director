"""Regressões da integração /director-noite; sem Unreal e sem LLM."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'src'))
import director_noite as N  # noqa: E402  # pyright: ignore[reportMissingImports]
from unreal_macros import fila as F  # noqa: E402

SCRATCH = ROOT / 'work/director-noite/testes'
SCRATCH.mkdir(parents=True, exist_ok=True)


def plano():
    return {'cena': {'descricao': 'objetivo variável', 'papeis': list(F.PAPEIS),
                     'criterios': list(F.PAPEIS) + ['trocas', 'duracao'], 'variacoes': 0,
                     'pode_variar': 'clipes medidos', 'fixo': 'pedido original'},
            'cobertura': [{'requisito': 'requisito de teste', 'essencial': True,
                          'criterios': list(F.PAPEIS), 'ausente': None}]}


class Preparacao(unittest.TestCase):
    def test_preparar_preserva_objetivo_e_isola_sem_unreal(self):
        self.assertIsNotNone(N, 'falta integração de campanha')
        with tempfile.TemporaryDirectory(dir=SCRATCH) as tmp:
            texto = '  pedido livre alfa\naspas " e {campos} intactos  '
            a = N.preparar(texto, plano(), 1, base=Path(tmp))
            b = N.preparar('pedido beta', plano(), 2, base=Path(tmp))
            self.assertNotEqual(a['id'], b['id'])
            pa = Path(a['pasta'])
            self.assertEqual((pa / 'OBJETIVO.txt').read_text(encoding='utf-8'), texto)
            self.assertTrue(a['executavel'], a)
            self.assertNotIn('Sit_To_Stand', (pa / 'PEDIDO.md').read_text(encoding='utf-8'))
            self.assertNotIn('sessao_pid', a)
            self.assertFalse((pa / 'LANCAMENTO.json').exists())
            self.assertNotEqual(a['fim_ts'], b['fim_ts'])
            self.assertTrue((pa / 'campanha.json').exists())

    def test_essencial_ausente_prepara_bloqueada_sem_substituir_objetivo(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as tmp:
            p = plano()
            p['cobertura'].append({'requisito': 'pedido não suportado', 'essencial': True,
                                   'criterios': [], 'ausente': 'sem medição'})
            c = N.preparar('pedido original não suportado', p, 1, base=Path(tmp))
            self.assertFalse(c['executavel'])
            self.assertTrue(any('capacidade_ausente' in x for x in c['bloqueios']))
            self.assertNotIn('tentar', (Path(c['pasta']) / 'PEDIDO.md').read_text())

    def test_objetivo_modificado_e_manifesto_divergente_recusados(self):
        from unreal_macros import campanha as CP
        with tempfile.TemporaryDirectory(dir=SCRATCH) as tmp:
            c = N.preparar('original', plano(), 1, base=Path(tmp))
            p = Path(c['pasta'])
            self.assertEqual(CP.ler(p)['id'], c['id'])
            (p / 'OBJETIVO.txt').write_text('troca silenciosa', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'imutável'):
                CP.ler(p)
            (p / 'OBJETIVO.txt').write_text('original', encoding='utf-8')
            data = json.loads((p / 'campanha.json').read_text())
            data['fim_ts'] += 3600
            (p / 'campanha.json').write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'manifesto'):
                CP.ler(p)

    def test_sem_cobertura_ou_horas_nao_finitas_nao_cria_campanha(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as tmp:
            for horas in (float('nan'), float('inf'), 0, -1, True, 25):
                with self.assertRaises(ValueError):
                    N.preparar('original', plano(), horas, base=Path(tmp))
            for p in ({'cena': {}}, dict(plano(), cobertura=[])):
                with self.assertRaises(ValueError):
                    N.preparar('original', p, 1, base=Path(tmp))
            self.assertEqual(list(Path(tmp).iterdir()), [])


class Seguranca(unittest.TestCase):
    def test_estado_parcial_bloqueia_vigia_mesmo_com_fechamento_e_trava_morta(self):
        import vigia_dev as V  # pyright: ignore[reportMissingImports]
        rd = {'tentativas': 1, 'melhor_nota': 0, 'terminou': True,
              'ultimo_especial': 'estado_parcial', 'pendente': None}
        lg = {'sessao': 'S', 'ultima_atividade': 0, 'fim_turno': 0,
              'inicio_turno': 0, 'turno_ativo': False, 'motivo_fim': 'text_response'}
        sd = {'trava': 'morta', 'modelo': True, 'unreal': True, 'scripts_da_rodada': 0}
        d = V.decidir({'log': lg, 'rodada': rd, 'saude': sd, 'pausa': False}, {}, 10000)
        self.assertEqual(d['estado'], 'estado_inseguro')
        self.assertEqual(d['acoes'], [])
    def test_campanha_pausada_recusa_executor_antes_de_reservar(self):
        from unittest.mock import patch
        import fila_executor as X  # pyright: ignore[reportMissingImports]
        from unreal_macros import campanha as CP
        with tempfile.TemporaryDirectory(dir=SCRATCH) as tmp:
            c = N.preparar('teste', plano(), 1, base=Path(tmp))
            p = Path(c['pasta'])
            (p / 'AUTORIZACAO.json').write_text(json.dumps({'id': c['id'], 'integridade': c['integridade']}))
            (p / 'PAUSA').write_text('pausa')
            boa = {'tipo': 'exploracao', 'linhagem': 'A', 'passos':
                   [{'clipe': 'fixture_' + papel, 'papel': papel} for papel in F.PAPEIS]}
            with patch.object(X, 'PASTA', str(p)), patch.dict(os.environ, {'FILA_CENA': str(p / 'CENA.md')}):
                _, motivos = X.preparar(boa)
                self.assertTrue(any('pausad' in x.lower() for x in motivos), motivos)
                self.assertFalse((p / 'estado.json').exists(), 'recusa não reserva estado')
            self.assertTrue(CP.guarda(p))


class Continuidade(unittest.TestCase):
    def test_pausa_continua_encerramento_e_relatorio_persistem_por_campanha(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as tmp:
            a = N.preparar('objetivo alfa', plano(), 1, base=Path(tmp))
            b = N.preparar('objetivo beta', plano(), 1, base=Path(tmp))
            p, q = Path(a['pasta']), Path(b['pasta'])
            N.controlar(p, 'pausar')
            self.assertTrue((p / 'PAUSA').exists())
            self.assertFalse((q / 'PAUSA').exists())
            self.assertEqual(N.estado(p)['situacao'], 'pausada')
            N.controlar(p, 'encerrar')
            self.assertTrue((p / 'PARAR').exists())
            r = N.relatorio(p)
            data = json.loads(Path(r['json']).read_text(encoding='utf-8'))
            self.assertEqual(data['objetivo'], 'objetivo alfa')
            self.assertFalse(data['sucesso_medido'])
            self.assertIn('Nenhuma', Path(r['markdown']).read_text(encoding='utf-8'))
            self.assertFalse((q / 'RELATORIO.json').exists())
    def test_vigia_campanha_recomeca_sessao_sem_teto_pequeno_mas_respeita_prazo(self):
        import vigia_dev as V  # pyright: ignore[reportMissingImports]
        from unreal_macros import processos as P
        lg = {'sessao': 'S', 'ultima_atividade': 0, 'fim_turno': 1, 'inicio_turno': 0,
              'turno_ativo': False, 'motivo_fim': 'max_iterations_reached'}
        rd = {'tentativas': 0, 'melhor_nota': None, 'terminou': False,
              'ultimo_especial': None, 'pendente': None}
        sd = {'trava': 'livre', 'modelo': True, 'unreal': True, 'scripts_da_rodada': 0,
              'sessao_processo': P.MORTO}
        obs = {'log': lg, 'rodada': rd, 'saude': sd, 'pausa': False,
               'campanha': {'fim_ts': 99999}, 'bloqueios_campanha': []}
        mem = {'relancos': [-10000] * 12, 'causas': ['limite'] * 3}
        d = V.decidir(obs, mem, 10000)
        self.assertIn('relancar_mudando', d['acoes'])
        self.assertNotIn('desistiu', mem)
        obs['campanha']['fim_ts'] = 9999
        self.assertEqual(V.decidir(obs, mem, 10000)['acoes'], [])
        obs['campanha']['fim_ts'] = 99999
        sd['sessao_processo'] = P.VIVO
        self.assertEqual(V.decidir(obs, mem, 10000)['acoes'], [])
        sd['sessao_processo'] = P.MORTO
        sd['trava'] = 'viva'
        self.assertEqual(V.decidir(obs, mem, 10000)['acoes'], [])
    def test_iniciar_exige_autorizacao_e_reusa_lancador_sem_repetir_ativo(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(dir=SCRATCH) as tmp:
            c = N.preparar('pedido', plano(), 1, base=Path(tmp))
            p = Path(c['pasta'])
            with patch.object(N.L2, 'lancar') as lancar, patch.object(N, 'ambiente', return_value=[]):
                with self.assertRaisesRegex(ValueError, 'autoriz'):
                    N.iniciar(p)
                self.assertFalse(lancar.called)
                lancar.return_value = {'vigia_pid': 999999, 'modo': 'noite'}
                N.iniciar(p, autorizado=True)
                self.assertEqual(lancar.call_count, 1)
                self.assertEqual(lancar.call_args.kwargs['campanha'], c['id'])
                self.assertTrue((p / 'AUTORIZACAO.json').exists())
                with patch.object(N, 'processo_vigia', return_value='VIVO'):
                    with self.assertRaisesRegex(ValueError, 'vigia'):
                        N.iniciar(p, autorizado=True)
                self.assertEqual(lancar.call_count, 1)
    def test_voltar_a_receita_segura_nao_desfaz_cena_e_recusa_origem_insegura(self):
        from unreal_macros import campanha as CP, receita as R
        with tempfile.TemporaryDirectory(dir=SCRATCH) as tmp:
            c = N.preparar('pedido', plano(), 1, base=Path(tmp))
            p = Path(c['pasta'])
            passos = [{'clipe': 'fixture_' + papel, 'papel': papel} for papel in F.PAPEIS]
            for n, nota in [(1, 1.0), (2, 4.0)]:
                r = {'linhagem': 'A', 'tipo': 'exploracao', 'passos': passos}
                linha = dict(n=n, tipo_linha='tentativa', receita=passos, nota=nota, cena_ok=True,
                             assinatura=R.assinatura(r), linhagem='A', tipo='exploracao', de=n-1 or None,
                             hipotese='fixture explicitamente sintética', avaliacao={'valida': True})
                with (p / 'tentativas.jsonl').open('a', encoding='utf-8') as f:
                    f.write(json.dumps(linha) + '\n')
            self.assertEqual(N.estado(p)['melhor']['n'], 1)
            out = N.voltar(p, 1, 'B')
            proposta = json.loads(Path(out['receita']).read_text(encoding='utf-8'))
            self.assertEqual(proposta['passos'], passos)
            self.assertEqual(proposta['de'], 1)
            self.assertEqual(proposta['linhagem'], 'B')
            self.assertEqual(len(CP.historico(p)), 2)
            with self.assertRaises(ValueError):
                N.voltar(p, 88, 'C')
            with (p / 'tentativas.jsonl').open('a', encoding='utf-8') as f:
                f.write(json.dumps(dict(linha, n=3, cena_ok=False, classe_erro='estado_parcial')) + '\n')
            with self.assertRaisesRegex(ValueError, 'inseguro'):
                N.voltar(p, 1, 'C')


if __name__ == '__main__':
    unittest.main()
