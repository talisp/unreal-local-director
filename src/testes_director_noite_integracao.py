"""Ataques permanentes à campanha: fixtures explícitas; nenhuma inferência/conexão Unreal."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'src'))
import director_noite as N  # noqa: E402  # pyright: ignore[reportMissingImports]
import fila_executor as X  # noqa: E402  # pyright: ignore[reportMissingImports]
import vigia_dev as V  # noqa: E402  # pyright: ignore[reportMissingImports]
from unreal_macros import campanha as CP, fila as F, processos as P, receita as R  # noqa: E402
from testes_director_noite import plano, SCRATCH  # noqa: E402


class Ataques(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=SCRATCH)
        self.addCleanup(self.tmp.cleanup)
        self.c = N.preparar('objetivo literal para fixture', plano(), 1, base=Path(self.tmp.name))
        self.p = Path(self.c['pasta'])
        CP.gravar(self.p, 'AUTORIZACAO.json', {'id': self.c['id'], 'integridade': self.c['integridade']})
        self.r = {'linhagem': 'A', 'tipo': 'exploracao', 'hipotese': 'fixture, não execução real',
                  'passos': [{'papel': papel, 'clipe': 'fixture_' + papel} for papel in F.PAPEIS]}

    def linha(self, **kw):
        d = dict(n=1, tipo_linha='tentativa', linhagem='A', tipo='exploracao', nota=1.0,
                 receita=self.r['passos'], assinatura=R.assinatura(self.r),
                 avaliacao={'valida': True}, cena_ok=True)
        d.update(kw)
        with (self.p / 'tentativas.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(d) + '\n')
        return d

    def test_controle_positivo_e_falha_parcial_nao_somem_com_resultado_posterior(self):
        self.assertEqual(CP.guarda(self.p), [])
        self.linha(cena_ok=False, classe_erro='estado_parcial')
        self.linha(n=2, nota=0)
        (self.p / 'FECHAMENTO.md').write_text('não autoriza limpar', encoding='utf-8')
        self.assertTrue(CP.guarda(self.p)[0].startswith('estado_inseguro'))
        self.assertFalse(N.estado(self.p)['sucesso_medido'])
        self.assertTrue(V.ler_rodada(str(self.p))['inseguro'])

    def test_restauracao_ausente_interrupcao_e_linha_cortada_bloqueiam(self):
        for linha in [{'tipo_linha': 'tentativa', 'cena_ok': None},
                      {'tipo_linha': 'tentativa_interrompida'},
                      {'tipo_linha': 'tentativa_inicio', 'n': 1}]:
            with (self.p / 'tentativas.jsonl').open('w', encoding='utf-8') as f:
                f.write(json.dumps(linha) + '\n')
            self.assertTrue(CP.guarda(self.p)[0].startswith('estado_inseguro'), linha)
        (self.p / 'tentativas.jsonl').write_text('{"tipo_linha":', encoding='utf-8')
        self.assertTrue(CP.guarda(self.p)[0].startswith('estado_inseguro'))
        self.assertEqual(N.estado(self.p)['situacao'], 'estado_inseguro')

    def test_pendente_vivo_espera_morto_ou_desconhecido_nao_recupera(self):
        self.linha(tipo_linha='tentativa_inicio')
        CP.gravar(self.p, 'estado.json', {'pendente': {'n': 1, 'pid': os.getpid()}})
        self.assertEqual(CP.inseguranca(self.p), [])
        with patch.object(X, 'PASTA', str(self.p)):
            for status in (P.MORTO, P.DESCONHECIDO):
                with patch.object(P, 'estado_processo', return_value=status):
                    self.assertTrue(CP.inseguranca(self.p))
                    self.assertIsNone(X.recuperar_pendente())
                    self.assertIsNotNone(X._estado()['pendente'])

    def test_filho_nao_atravessa_pausa_nem_consumindo_autorizacao_anterior(self):
        CP.gravar(self.p, 'estado.json', {'autorizado': {'n': 1, 'nonce': 'fixture'}})
        proposta = self.p / 'proposta.json'
        proposta.write_text(json.dumps(self.r), encoding='utf-8')
        (self.p / 'PAUSA').write_text('pausa', encoding='utf-8')
        with patch.object(X, 'PASTA', str(self.p)), patch.dict(os.environ, {'FILA_CENA': str(self.p / 'CENA.md')}), \
             patch.object(X, 'Unreal') as unreal, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(X.main(['_filho', str(proposta), '1', 'fixture']), 1)
            self.assertFalse(unreal.called)
            self.assertEqual(X._estado()['autorizado']['nonce'], 'fixture')
            self.assertIn('recusada', X.executar(self.r, 1))
            self.assertFalse(unreal.called)

    def test_cena_e_autorizacao_de_outra_campanha_recusadas(self):
        outra = N.preparar('outro objetivo', plano(), 1, base=Path(self.tmp.name))
        with patch.object(X, 'PASTA', str(self.p)), patch.dict(os.environ, {'FILA_CENA': str(Path(outra['pasta']) / 'CENA.md')}):
            self.assertTrue(any('FILA_CENA' in m for m in X.guarda_campanha()))
        CP.gravar(self.p, 'AUTORIZACAO.json', {'id': outra['id'], 'integridade': outra['integridade']})
        self.assertTrue(any('autorização' in m for m in CP.guarda(self.p)))

    def test_prazo_igual_ao_limite_recusa_sem_reabrir_dia_seguinte(self):
        self.assertEqual(CP.guarda(self.p, agora=self.c['prazo_tentativas_ts'] - 1), [])
        self.assertTrue(CP.guarda(self.p, agora=self.c['prazo_tentativas_ts']))
        self.assertTrue(CP.guarda(self.p, agora=self.c['fim_ts'] + 86400))

    def test_logs_so_adotam_prefixo_desta_campanha(self):
        a, b = self.c['id'], 'outra-campanha'
        linhas = [f"2026-10-10 01:00:00,123 INFO [S1] conversation turn: msg='[director-noite:{b}] continue'",
                  f"2026-10-10 01:00:01,123 INFO [S2] conversation turn: msg='[director-noite:{a}] continue'"]
        with patch.object(V, 'PREFIXO', f'[director-noite:{a}]'):
            lg = V.ler_log(linhas, set())
            self.assertEqual(lg['novas'], ['S2'])
            self.assertEqual(lg['sessao'], 'S2')

    def test_rechecagem_vigia_nao_age_sobre_decisao_antiga_apos_pausa(self):
        args = SimpleNamespace(campanha=self.c['id'], rodada=str(self.p), pedido=str(self.p / 'PEDIDO.md'), seco=False)
        (self.p / 'PAUSA').write_text('pausa', encoding='utf-8')
        obs = {'rodada': {'inseguro': False, 'ultimo_especial': None}}
        with patch.object(V, 'relancar') as relancar:
            self.assertEqual(V.executar({'acoes': ['relancar'], 'causa': 'limite'}, obs, {}, args), [])
            self.assertFalse(relancar.called)

    def test_lancador_cria_apenas_vigia_com_identidade_propria(self):
        with patch.object(N.L2.subprocess, 'Popen') as popen:
            popen.return_value.pid = 12345
            info = N.L2.lancar(str(self.p / 'PEDIDO.md'), str(self.p), self.c['cena'], 'noite', campanha=self.c['id'])
            self.assertEqual(popen.call_count, 1)
            cmd = popen.call_args.args[0]
            self.assertIn('vigia_dev.py', ' '.join(cmd))
            self.assertIn('--campanha', cmd)
            self.assertIn(self.c['id'], cmd)
            self.assertIn('--sessao', cmd)
            self.assertNotIn('chat', cmd)
            self.assertEqual(info['vigia_pid'], 12345)

    def test_continuar_vigia_viva_remove_so_pausa_e_nao_lanca_segundo_operador(self):
        (self.p / 'PAUSA').write_text('pausa', encoding='utf-8')
        with patch.object(N, 'processo_vigia', return_value=P.VIVO), patch.object(N.L2, 'lancar') as lancar:
            s = N.iniciar(self.p, autorizado=True, continuar=True)
            self.assertFalse(lancar.called)
            self.assertFalse((self.p / 'PAUSA').exists())
            self.assertEqual(s['situacao'], 'ativa')
        N.controlar(self.p, 'encerrar')
        with self.assertRaisesRegex(ValueError, 'encerrada'):
            N.iniciar(self.p, autorizado=True, continuar=True)

    def test_relatorio_guarda_linhagem_hipoteses_videos_versoes_sem_inventar_sucesso(self):
        self.linha(hipotese='hipótese fixture', video={'arquivo': 'fixture.mp4'}, de=None)
        resultado = N.relatorio(self.p)
        data = json.loads(Path(resultado['json']).read_text(encoding='utf-8'))
        self.assertEqual(data['historico'][0]['hipotese'], 'hipótese fixture')
        self.assertEqual(data['historico'][0]['video']['arquivo'], 'fixture.mp4')
        self.assertEqual(data['versoes'], self.c['versoes'])
        self.assertFalse(data['sucesso_medido'])
        self.assertFalse(data['autonomia_oito_horas_validada'])
        self.assertEqual(data['evolucao'][0]['nota'], 1)

    def test_sucesso_exige_tres_medicoes_seguras_e_variacoes_completas(self):
        self.linha(n=1, nota=0)
        self.linha(n=2, nota=0)
        self.assertFalse(N.estado(self.p)['sucesso_medido'])
        self.linha(n=3, nota=0)
        self.assertTrue(N.estado(self.p)['sucesso_medido'])
        self.linha(n=4, nota=0, cena_ok=False)
        self.assertFalse(N.estado(self.p)['sucesso_medido'])
    def test_variacoes_pendentes_impedem_sucesso_global(self):
        p = plano()
        p['cena']['variacoes'] = 1
        c = N.preparar('pedido com variação', p, 1, base=Path(self.tmp.name))
        self.p = Path(c['pasta'])
        for n in (1, 2, 3):
            self.linha(n=n, nota=0)
        self.assertFalse(N.estado(self.p)['sucesso_medido'])
        self.assertEqual(N.estado(self.p)['variacoes']['faltam'], 1)
        passos = [dict(x) for x in self.r['passos']]
        passos[0]['clipe'] += '_alternativa'
        self.linha(n=4, nota=0, receita=passos, variacao=True,
                   assinatura=R.assinatura(dict(self.r, passos=passos)))
        self.assertTrue(N.estado(self.p)['sucesso_medido'])
    def test_manifesto_ausente_nao_transforma_campanha_em_executor_legado(self):
        (self.p / 'campanha.json').rename(self.p / 'campanha-backup.json')
        with patch.object(X, 'PASTA', str(self.p)), patch.dict(os.environ, {'FILA_CENA': str(self.p / 'CENA.md')}):
            _, motivos = X.preparar(self.r)
            self.assertTrue(any('estado_inseguro' in m for m in motivos), motivos)
    def test_laco_real_vigia_reusa_memoria_local_sem_lancar_modelo(self):
        # Apenas as bordas rede/processo são fixtures. Parser, decisão, prompt, memória e relatório são reais.
        argv = ['vigia_dev.py', '--campanha', self.c['id'], '--rodada', str(self.p),
                '--pedido', str(self.p / 'PEDIDO.md'), '--perfil', N.L2.PERFIL, '--uma-vez']
        saude = {'modelo': True, 'unreal': True, 'trava': 'livre', 'scripts_da_rodada': 0}
        with patch.object(sys, 'argv', argv), patch.object(V, 'saude', return_value=saude), \
             patch.object(N, 'perfil_local', return_value=True), patch.object(V.subprocess, 'Popen') as popen, \
             patch.object(V, 'PREFIXO', V.PREFIXO), patch.object(V, 'PASTA', V.PASTA), \
             patch.object(V, 'PERFIL', V.PERFIL), patch.object(V, 'LOG_DEV', str(self.p / 'sem-log')), \
             patch.object(V, 'LIM', dict(V.LIM)), contextlib.redirect_stdout(io.StringIO()):
            popen.return_value.pid = 999999
            self.assertEqual(V.main(), 0)
            self.assertEqual(popen.call_count, 1)
            cmd = popen.call_args.args[0]
            self.assertIn('--query-file', cmd)
            self.assertIn(N.L2.PERFIL, cmd)
            prompt = Path(cmd[cmd.index('--query-file') + 1]).read_text(encoding='utf-8')
            self.assertIn(self.c['id'], prompt)
            self.assertNotIn('07:30', prompt)
        mem = json.loads((self.p / 'vigia/memoria.json').read_text(encoding='utf-8'))
        self.assertEqual(mem['campanha'], self.c['id'])
        self.assertEqual(mem['sessoes'], [])
        self.assertEqual(mem['sessao_pid'], 999999)
        self.assertTrue((self.p / 'RELATORIO.md').exists())
        self.assertFalse((self.p / 'vigia/operador.trava').exists())
    def test_estado_classifica_progresso_repeticao_e_infra_sem_inventar_causa(self):
        self.linha(n=1, nota=4)
        self.assertEqual(N.estado(self.p)['diagnostico'], 'primeira_medicao')
        self.linha(n=2, nota=2)
        self.assertEqual(N.estado(self.p)['diagnostico'], 'progresso_medido')
        self.linha(n=3, nota=3)
        self.assertEqual(N.estado(self.p)['diagnostico'], 'sem_avanco_medido')
        self.linha(n=4, nota=None, classe_erro='infraestrutura', avaliacao={})
        self.assertEqual(N.estado(self.p)['diagnostico'], 'falha_infraestrutura')
        self.linha(n=5, nota=None, classe_erro='dependencia', avaliacao={})
        self.assertEqual(N.estado(self.p)['diagnostico'], 'falha_ferramenta_ou_dependencia')
    def test_duas_campanhas_nao_lancam_escritores_concorrentes_no_mesmo_perfil(self):
        outra = N.preparar('pedido beta', plano(), 1, base=Path(self.tmp.name))
        q = Path(outra['pasta'])
        CP.gravar(self.p, 'LANCAMENTO.json', {'vigia_pid': os.getpid()})  # fixture de processo vivo real
        with patch.object(N.L2, 'lancar', return_value={'vigia_pid': 999999}) as lancar, \
             patch.object(N, 'ambiente', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'outra campanha'):
                N.iniciar(q, autorizado=True)
            self.assertFalse(lancar.called)
        self.assertFalse((q / 'AUTORIZACAO.json').exists())
    def test_vigia_morta_nao_permite_duplicar_sessao_ainda_viva(self):
        CP.gravar(self.p, 'LANCAMENTO.json', {'vigia_pid': 999999})
        (self.p / 'vigia').mkdir()
        CP.gravar(self.p / 'vigia', 'memoria.json', {'campanha': self.c['id'], 'sessao_pid': os.getpid()})
        # v0.0.6 (L5, A24): a regra mudou DE PROPÓSITO. Antes a retomada era recusada e a sessão viva ficava sem
        # supervisão até morrer. Agora, com a sessão comprovadamente DESTA campanha viva, recria-se só o observador:
        # L2.lancar em campanha cria apenas a vigia (teste test_lancador_cria_apenas_vigia_com_identidade_propria)
        # e a vigia não relança enquanto a sessão registrada vive. Continua proibido duplicar a sessão: identidade
        # desconhecida ou sessão de outra campanha seguem bloqueando (src/testes_v006_l5.py, Retomada).
        with patch.object(N.L2, 'lancar', return_value={'vigia_pid': 999999}) as lancar, \
             patch.object(N, 'ambiente', return_value=[]):
            N.iniciar(self.p, autorizado=True, continuar=True)
            self.assertEqual(lancar.call_count, 1)
            self.assertEqual(lancar.call_args.kwargs.get('campanha'), self.c['id'])
        memoria = json.loads((self.p / 'vigia/memoria.json').read_text(encoding='utf-8'))
        self.assertEqual(memoria['sessao_pid'], os.getpid())  # a sessão viva não foi trocada nem duplicada
    def test_vigia_soltar_trava_propria_se_observacao_falhar(self):
        argv = ['vigia_dev.py', '--campanha', self.c['id'], '--rodada', str(self.p),
                '--pedido', str(self.p / 'PEDIDO.md'), '--perfil', N.L2.PERFIL, '--uma-vez']
        with patch.object(sys, 'argv', argv), patch.object(V, 'observar', side_effect=ValueError('fixture queda')), \
             patch.object(V, 'PREFIXO', V.PREFIXO), patch.object(V, 'PASTA', V.PASTA), \
             patch.object(V, 'PERFIL', V.PERFIL), patch.object(V, 'LOG_DEV', V.LOG_DEV), \
             patch.object(V, 'LIM', dict(V.LIM)):
            with self.assertRaisesRegex(ValueError, 'fixture queda'):
                V.main()
        self.assertFalse((self.p / 'vigia/operador.trava').exists())
        self.assertFalse((self.p.parent / 'operador.trava').exists())
    def test_relancar_persiste_pid_antes_de_devolver_ao_laco(self):
        mem = {'campanha': self.c['id'], 'sessoes': []}
        vigia = self.p / 'vigia'
        vigia.mkdir()
        with patch.object(V, 'PASTA', str(vigia)), patch.object(N, 'perfil_local', return_value=True), \
             patch.object(V.subprocess, 'Popen') as popen:
            popen.return_value.pid = 999999
            V.relancar('fixture de prompt; nenhuma LLM executada', mem, False)
        self.assertTrue((vigia / 'memoria.json').exists())
        persistida = json.loads((vigia / 'memoria.json').read_text(encoding='utf-8'))
        self.assertEqual(persistida['sessao_pid'], 999999)
        self.assertFalse(persistida['lancamento_em_curso'])
    def test_retorno_recusa_receita_que_nao_corresponde_a_assinatura_medida(self):
        self.linha(assinatura='assinatura divergente de fixture')
        with self.assertRaisesRegex(ValueError, 'assinatura'):
            N.voltar(self.p, 1, 'B')
        self.assertEqual(list(self.p.glob('proposta-retorno-*.json')), [])
    def test_lancamento_inconclusivo_e_perfil_nao_local_nao_relancam(self):
        vigia = self.p / 'vigia'
        vigia.mkdir()
        CP.gravar(vigia, 'memoria.json', {'campanha': self.c['id'], 'lancamento_em_curso': True})
        self.assertTrue(CP.guarda(self.p)[0].startswith('estado_inseguro'))
        with patch.object(N.L2, 'lancar') as lancar:
            with self.assertRaisesRegex(ValueError, 'estado_inseguro'):
                N.iniciar(self.p, autorizado=True)
            self.assertFalse(lancar.called)
        with patch.object(V, 'PASTA', str(vigia)), patch.object(N, 'perfil_local', return_value=False), \
             patch.object(V.subprocess, 'Popen') as popen:
            self.assertIn('bloqueio', V.relancar('fixture', {'campanha': self.c['id']}, False))
            self.assertFalse(popen.called)

    def test_cli_controles_por_id_e_recusa_sem_autorizacao(self):
        def chamar(args):
            with patch.object(N, 'pasta_de', return_value=self.p), contextlib.redirect_stdout(io.StringIO()) as out:
                code = N.main(args)
            return code, json.loads(out.getvalue())
        code, data = chamar(['estado', self.c['id']])
        self.assertEqual(code, 0)
        self.assertEqual(data['id'], self.c['id'])
        code, data = chamar(['pausar', self.c['id']])
        self.assertEqual(data['situacao'], 'pausada')
        code, data = chamar(['continuar', self.c['id']])
        self.assertEqual(code, 1)
        self.assertIn('autorização', data['erro'])
        self.assertTrue((self.p / 'PAUSA').exists())
        code, data = chamar(['relatorio', self.c['id']])
        self.assertEqual(code, 0)
        self.assertTrue(Path(data['markdown']).exists())
        code, data = chamar(['encerrar', self.c['id']])
        self.assertEqual(data['situacao'], 'encerrada')


if __name__ == '__main__':
    unittest.main()
