"""Fachada /director-noite: campanhas sobre linha2/vigia_dev/fila_executor, não outro executor."""
# pyright: reportMissingImports=false
import argparse
import datetime as dt
import hashlib
import json
import math
import re
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'src'))
import linha2 as L2  # noqa: E402
from unreal_macros import campanha as CP, cena as C, fila as F, receita as R, teste_versao as TV  # noqa: E402

BASE = RAIZ / 'work/director-noite/campanhas'


def capacidades() -> dict:
    return {'testes_da_versao': TV.ler_lista(),  # o que a versão desta pasta mudou e dá para exercitar ao vivo
            'papeis': list(F.PAPEIS), 'ordem_e_todos_obrigatorios': True,
            'criterios': list(C.CATALOGO), 'limites_medicao': F.LIM, 'regras': F.REGRAS,
            'campos_receita': ['clipe', 'papel', 'turn_deg'] + list(R.LIMITES),
            'variacoes_max': C.VARIACOES_MAX, 'executor': 'tools/fila_executor.py',
            'limitacoes': ['régua de um personagem e sequência específica; não mede diálogo, '
                          'interação entre personagens ou ações fora do catálogo',
                          'sem velocidade/mistura entre clipes']}


def pasta_de(cid: str, base: Path = BASE) -> Path:
    if not re.fullmatch(r'dn-\d{8}-\d{6}-[a-f0-9]{12}', cid):
        raise ValueError('ID inválido; informe a identidade exata da campanha')
    p = base / cid
    if p.is_symlink() or p.resolve().parent != base.resolve():
        raise ValueError('pasta da campanha fora da base')
    return p


def preparar(objetivo: str, plano: dict, horas: float = 8, base: Path = BASE) -> dict:
    if not isinstance(objetivo, str) or not objetivo.strip():
        raise ValueError('objetivo original vazio')
    if isinstance(horas, bool) or not math.isfinite(horas) or not 0 < horas <= 24:
        raise ValueError('horas deve ser finito, maior que zero e no máximo 24')
    if not isinstance(plano, dict) or not isinstance(plano.get('cena'), dict):
        raise ValueError('plano exige cena e cobertura explícita')
    if plano.get('modo', 'formal') not in ('formal', 'experimental'):
        raise ValueError('modo deve ser formal ou experimental')
    if plano.get('testes_da_versao') not in (None, False, True):
        raise ValueError('testes_da_versao: true ou false')
    if plano.get('testes_da_versao') and plano.get('modo') != 'experimental':
        raise ValueError('testes_da_versao só vale em modo experimental (laboratório)')
    inicio = dt.datetime.now().astimezone()
    fim = inicio + dt.timedelta(hours=horas)
    prazo = fim - dt.timedelta(seconds=min(1800, horas * 3600 / 10))
    cid = f'dn-{inicio:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:12]}'
    pasta = pasta_de(cid, base)
    cena = dict(plano['cena'], nome=cid, descricao='Objetivo literal em OBJETIVO.txt; cobertura em PLANO.json.',
                ate=fim.strftime('%H:%M'), prazo_tentativas=prazo.strftime('%H:%M'))
    # Campos legados são linhas únicas; objetivo literal fica fora desse formato.
    for k in ('pode_variar', 'fixo', 'personagem'):
        if not isinstance(cena.get(k, ''), str) or '\n' in cena.get(k, '') or '\r' in cena.get(k, ''):
            raise ValueError(f'{k}: texto em uma linha')
    for k in ('papeis', 'criterios'):
        if not isinstance(cena.get(k), list) or not all(isinstance(x, str) for x in cena[k]):
            raise ValueError(f'{k}: lista de nomes')
    if type(cena.get('variacoes')) is not int:
        raise ValueError('variacoes: inteiro')
    validacao = C.validar_cena(cena)
    motivos = list(validacao['motivos'])
    if not set(cena['papeis']).issubset(cena['criterios']):
        motivos.append('todos os papéis precisam dos próprios critérios de medição')
    cobertura = plano.get('cobertura')
    if not isinstance(cobertura, list) or not cobertura:
        raise ValueError('cobertura explícita de cada requisito é obrigatória')
    lacunas = []
    for item in cobertura:
        if not isinstance(item, dict) or not isinstance(item.get('requisito'), str) or not item['requisito'].strip():
            raise ValueError('requisito de cobertura inválido')
        if type(item.get('essencial')) is not bool or not isinstance(item.get('criterios'), list):
            raise ValueError('cobertura exige essencial booleano e criterios em lista')
        if not all(isinstance(x, str) for x in item['criterios']):
            raise ValueError('critério de cobertura inválido')
        if item.get('ausente') is not None and not isinstance(item['ausente'], str):
            raise ValueError('ausente deve ser texto ou null')
        faltas = set(item['criterios']) - set(cena['criterios'])
        if faltas:
            motivos.append(f'critério não vinculado à cena: {sorted(faltas)}')
        if item.get('ausente') or not item['criterios']:
            lacunas.append(dict(item))
        if item['essencial'] and (item.get('ausente') or not item['criterios']) and plano.get('modo') != 'experimental':
            motivos.append(f"capacidade_ausente: {item['requisito']}: {item.get('ausente') or 'sem critério medível'}")
    pasta.mkdir(parents=True, exist_ok=False)
    (pasta / 'OBJETIVO.txt').write_text(objetivo, encoding='utf-8', newline='')
    CP.gravar(pasta, 'PLANO.json', plano)
    texto_cena = '# Cena da campanha\n' + '\n'.join(
        f"- {k}: {', '.join(v) if isinstance(v, list) else v}" for k, v in cena.items()) + '\n'
    (pasta / 'CENA.md').write_text(texto_cena, encoding='utf-8')
    if motivos:
        pedido = f'# Campanha {cid} bloqueada\nLeia OBJETIVO.txt e PLANO.json. Não executar Unreal.\n' + '\n'.join(motivos)
    else:
        pedido = L2.gerar_pedido(cena, (pasta / 'CENA.md').as_posix(), pasta.as_posix(), 'noite',
                                str(RAIZ / 'docs/rotinas/L2_DIRECTOR_NOITE.md'))
    (pasta / 'PEDIDO.md').write_text(pedido, encoding='utf-8')
    (pasta / 'LICOES.md').write_text('# Hipóteses, aprendizado e próxima ação\nNenhuma tentativa ainda.\n', encoding='utf-8')
    c = {'schema': 1, 'modo': plano.get('modo', 'formal'), 'id': cid, 'inicio': inicio.isoformat(), 'fim_ts': fim.timestamp(),
         'prazo_tentativas_ts': prazo.timestamp(), 'horas': horas, 'perfil': L2.PERFIL,
         'executavel': not motivos, 'bloqueios': motivos, 'lacunas': lacunas, 'cena': cena,
         'versoes': {str(p.relative_to(RAIZ)): CP.sha(p) for p in
                     [RAIZ / 'tools/linha2.py', Path(__file__), RAIZ / 'tools/vigia_dev.py',
                      RAIZ / 'tools/fila_executor.py', RAIZ / 'src/unreal_macros/fila.py',
                      RAIZ / 'src/unreal_macros/campanha.py', RAIZ / 'src/unreal_macros/cena.py',
                      RAIZ / 'src/unreal_macros/receita.py', RAIZ / 'src/unreal_macros/macros.py',
                      RAIZ / 'src/unreal_macros/biblioteca.py', RAIZ / 'src/unreal_macros/python_auxiliar.py',
                      RAIZ / 'src/unreal_macros/teste_versao.py', TV.LISTA,
                      RAIZ / 'docs/rotinas/L2_DIRECTOR_NOITE.md']},
         'arquivos': {n: CP.sha(pasta / n) for n in ('OBJETIVO.txt', 'PLANO.json', 'CENA.md', 'PEDIDO.md')}}
    if plano.get('testes_da_versao'):
        # A lista entra no manifesto (protegida pela integridade): a campanha testa ESTA versão, com ESTES testes,
        # e não fecha por esgotamento enquanto o programa não achar a evidência de cada um (ver fechar).
        lista = TV.ler_lista()
        c['testes_versao'] = {'versao': lista.get('versao'), 'ids': [i['id'] for i in lista['itens']]}
    c['integridade'] = hashlib.sha256(json.dumps(c, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    CP.gravar(pasta, 'campanha.json', c)
    CP.eventos(pasta, 'preparacao', executavel=c['executavel'], bloqueios=motivos)
    return dict(c, pasta=str(pasta))


def _carimbo_fechamento(pasta: Path) -> float | None:
    """Quando a campanha acabou, lido do REGISTRO: ENCERRAMENTO.json (`quando`) e PARAR (hora escrita dentro);
    FECHAMENTO.md (fluxo formal, escrito pela sessão) não tem hora própria: último recurso é o mtime."""
    ts = []
    try:
        q = json.loads((pasta / 'ENCERRAMENTO.json').read_text(encoding='utf-8')).get('quando')
        ts.append(dt.datetime.fromisoformat(q).timestamp())
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    parar = pasta / 'PARAR'
    if parar.exists():
        try:
            ts.append(dt.datetime.fromisoformat(parar.read_text(encoding='utf-8').strip()).timestamp())
        except (OSError, ValueError):
            ts.append(parar.stat().st_mtime)
    if (pasta / 'FECHAMENTO.md').exists():
        ts.append((pasta / 'FECHAMENTO.md').stat().st_mtime)
    return max(ts) if ts else None


def tempo_decorrido(pasta: Path, c: dict) -> float:
    """N1 (achado do qwen-junior, 11/10): depois do encerramento a duração da campanha é um fato do passado. Reler
    `estado`/`relatorio` horas depois não pode continuar contando o relógio (um relatório reemitido marcou 12.557 s
    numa campanha de 2.031 s)."""
    import time
    fim = _carimbo_fechamento(pasta)
    agora = time.time()
    return max(0, (agora if fim is None else min(fim, agora)) - dt.datetime.fromisoformat(c['inicio']).timestamp())


def estado(pasta: Path) -> dict:
    import time
    from unreal_macros import processos as P
    c = CP.ler(pasta)
    bloqueios = CP.guarda(pasta)
    # A19: histórico corrompido bloqueia a OPERAÇÃO (a guarda acima já o faz), mas a apresentação mostra a parte
    # legível e diz o que está corrompido, em vez de apresentar tudo como vazio.
    linhas, ilegiveis = CP.historico_recuperavel(pasta)
    tent = [t for t in linhas if t.get('tipo_linha') == 'tentativa']
    seguras = [t for t in tent if t.get('cena_ok') is True and (t.get('avaliacao') or {}).get('valida') is True
               and type(t.get('nota')) in (int, float) and math.isfinite(t['nota'])]
    melhor = min(seguras, key=lambda t: t['nota']) if seguras else None
    arq = pasta / 'estado.json'
    try:
        e = json.loads(arq.read_text(encoding='utf-8')) if arq.exists() else {}
        pendente = e.get('pendente')
    except (ValueError, AttributeError):
        e, pendente = {}, None
    try:
        lab = CP.laboratorio(pasta)
    except (ValueError, OSError, TypeError, KeyError):
        lab = {'fila': [], 'experimentos': [], 'scripts': []}
    situacao = ('estado_inseguro' if any(x.startswith('estado_inseguro') for x in bloqueios) else
                'encerrada' if (pasta / 'PARAR').exists() or CP.encerrada(pasta) else
                'pausada' if (pasta / 'PAUSA').exists() else 'bloqueada' if bloqueios else 'ativa')
    cmd = (f'cd "{RAIZ.as_posix()}" && FILA_PASTA="{pasta.as_posix()}" '
           f'FILA_CENA="{(pasta / "CENA.md").as_posix()}" '
           f'"{(RAIZ / "venv/Scripts/python.exe").as_posix()}" tools/fila_executor.py')
    variacoes = C.estado_variacoes(seguras, c['cena']['variacoes'])
    ultimo = tent[-1] if tent else {}
    nota = ultimo.get('nota')
    anteriores = [t['nota'] for t in seguras if t is not ultimo]
    recorte = bool(CP.sucesso_seguro(seguras))
    lacunas = c.get('lacunas', [])
    # A11: o texto e o booleano saem da MESMA condição final; recorte aprovado com variação faltando não é sucesso
    sucesso_final = (situacao != 'estado_inseguro' and recorte and c['executavel']
                     and not any(x['essencial'] for x in lacunas) and variacoes['faltam'] == 0)
    diagnostico = ('estado_inseguro' if situacao == 'estado_inseguro' else
                   'capacidade_ausente' if not c['executavel'] else
                   'falha_infraestrutura' if ultimo.get('classe_erro') == 'infraestrutura' else
                   'falha_ferramenta_ou_dependencia' if ultimo.get('classe_erro') == 'dependencia' else
                   'recorte_medido_com_lacunas' if recorte and any(x['essencial'] for x in lacunas) else
                   'sucesso_medido' if sucesso_final else
                   'recorte_medido_variacoes_pendentes' if recorte else
                   'sem_medicao' if not isinstance(nota, (int, float)) or isinstance(nota, bool) or not math.isfinite(nota) else
                   'primeira_medicao' if not anteriores else
                   'progresso_medido' if nota < min(anteriores) else 'sem_avanco_medido')
    video_opcional = c.get('modo') == 'experimental'
    duracoes = []
    for t in tent:
        try:
            segundos = (dt.datetime.fromisoformat(t['quando']) - dt.datetime.fromisoformat(t['quando_inicio'])).total_seconds()
            if segundos >= 0:
                duracoes.append(segundos)
        except (ValueError, KeyError, TypeError):
            pass  # Ausência de relógio não é zero segundos de execução comprovada.
    corrompido = ({'historico_corrompido': {'linhas_ilegiveis': ilegiveis, 'arquivo': 'tentativas.jsonl',
                                           'efeito': 'operação bloqueada; os registros legíveis são evidência parcial'}}
                  if ilegiveis else {})
    if c.get('testes_versao'):  # cobertura calculada pelo programa, a partir dos registros da campanha
        corrompido['testes_versao'] = dict(TV.conferir(pasta, c['testes_versao']['ids'], lab['experimentos']),
                                           versao=c['testes_versao'].get('versao'))
    return {**corrompido, 'tentativas': len(tent), 'aprovadas': sum(t['nota'] == 0 for t in seguras),
            'reprovadas': sum(t['nota'] > 0 for t in seguras),
            'sem_medicao': len(tent) - len(seguras), 'video_opcional': video_opcional,
            'tempo_execucao_medido_s': sum(duracoes), 'duracoes_ausentes': len(tent) - len(duracoes),
            'id': c['id'], 'pasta': str(pasta), 'situacao': situacao, 'bloqueios': bloqueios,
            'diagnostico': diagnostico,
            'fila_hipoteses': lab['fila'], 'experimentos': lab['experimentos'], 'scripts': lab['scripts'],
            'experimentos_distintos': len(lab['experimentos']),
            'receitas_distintas': len({json.dumps([t.get('assinatura'), t.get('condicoes')], sort_keys=True) for t in tent}),
            'funcionalidades_testadas': sorted({x['funcionalidade'] for x in lab['experimentos'] if x['tentativas']}),
            'repeticoes_sem_novidade': len(tent) - len({json.dumps([t.get('assinatura'), t.get('condicoes')], sort_keys=True) for t in tent}),
            'tempo_restante_s': max(0, c['prazo_tentativas_ts'] - time.time()),
            'fim_ts': c['fim_ts'], 'prazo_tentativas_ts': c['prazo_tentativas_ts'],
            'duracao_decorrida_s': tempo_decorrido(pasta, c),
            'pendente': pendente,
            'pendente_processo': P.estado_processo(pendente.get('pid')) if pendente else None,
            'melhor': melhor, 'linhagens': F.estado_linhagens(seguras, e.get('fechadas', {})),
            'recorte_medido': situacao != 'estado_inseguro' and recorte,
            'lacunas': lacunas, 'modo': c.get('modo', 'formal'),
            'sucesso_medido': sucesso_final,
            'variacoes': variacoes,
            'criterios': c['cena']['criterios'], 'comando_executor': cmd,
            'ultimas': [{k: t.get(k) for k in ('n', 'nota', 'classe_erro', 'cena_ok', 'hipotese', 'de')}
                        for t in tent[-5:]]}


def editar_laboratorio(pasta: Path, mudar, registro: bool = False) -> dict:
    from unreal_macros import trava as T
    lock = str(pasta / 'laboratorio.trava')
    T.pegar(lock, 'laboratorio:' + pasta.name)
    try:
        motivos = CP.guarda(pasta)
        if registro:
            # Arquivar resultado já produzido não é admissão de outra operação.
            motivos = [m for m in motivos if m not in ('prazo absoluto da campanha encerrado',
                        'campanha encerrada', 'campanha pausada', 'campanha já tem fechamento')]
        if motivos:
            raise ValueError('; '.join(motivos))
        lab = CP.laboratorio(pasta)
        if CP.ler(pasta).get('modo') != 'experimental':
            raise ValueError('laboratório somente em modo experimental')
        mudar(lab)
        CP.gravar(pasta, 'LABORATORIO.json', lab)
        return lab
    finally:
        T.soltar(lock)


def planejar(pasta: Path, fila: list) -> dict:
    if not isinstance(fila, list) or len(fila) > 5:
        raise ValueError('fila deve ter até cinco hipóteses')
    ids = set()
    for h in fila:
        if not isinstance(h, dict) or any(not isinstance(h.get(k), str) or not h[k].strip()
                                         for k in ('id', 'hipotese', 'funcionalidade', 'proximo_teste')):
            raise ValueError('hipótese exige id, hipotese, funcionalidade e proximo_teste')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', h['id']) or h['id'] in ids:
            raise ValueError('id de hipótese inválido/duplicado')
        if 'teste' in h and h['teste'] not in TV.CONFERIDORES:
            raise ValueError(f"teste desconhecido: {h['teste']!r}; os testes da versão são {sorted(TV.CONFERIDORES)}")
        ids.add(h['id'])
    # A20: hipótese que já tem tentativa não muda de identidade sob o mesmo ID (a medida ficaria atribuída a outra
    # coisa). Corrigir o texto ou a funcionalidade ANTES de qualquer tentativa continua permitido; depois, ID novo.
    com_tentativa = {t.get('experimento') for t in CP.historico(pasta)
                     if t.get('tipo_linha') in ('tentativa', 'tentativa_inicio') and t.get('experimento')}

    def mudar(lab):
        antigas = {h['id'] for h in lab['fila']}
        if antigas - ids:
            raise ValueError('conclua/descarte hipóteses com evidência antes de removê-las')
        atuais = {h['id']: h for h in lab['fila']}
        for h in fila:
            antes = atuais.get(h['id'])
            if antes and h['id'] in com_tentativa and any(h[k] != antes[k] for k in ('hipotese', 'funcionalidade')):
                raise ValueError(f"hipótese {h['id']} já tem tentativa: hipótese e funcionalidade não mudam; "
                                 'use um ID novo para outra hipótese')
        if ids & {x['id'] for x in lab['experimentos']}:
            raise ValueError('id já concluído; use hipótese nova')
        lab['fila'] = fila
    lab = editar_laboratorio(pasta, mudar)
    CP.eventos(pasta, 'planejamento', fila=fila)
    return lab


def concluir(pasta: Path, resultado: dict) -> dict:
    if not isinstance(resultado, dict) or resultado.get('classe') not in ('medido', 'lacuna', 'descartada', 'suspeita', 'proposta'):
        raise ValueError('classe de resultado inválida')
    if not isinstance(resultado.get('descoberta'), str) or not resultado['descoberta'].strip():
        raise ValueError('descoberta/justificativa obrigatória')
    if 'teste' in resultado and resultado['teste'] not in TV.CONFERIDORES:
        raise ValueError(f"teste desconhecido: {resultado['teste']!r}; os testes da versão são {sorted(TV.CONFERIDORES)}")
    ns = resultado.get('tentativas', [])
    if not isinstance(ns, list) or any(type(n) is not int for n in ns) or len(set(ns)) != len(ns):
        raise ValueError('tentativas deve ser lista de números únicos')
    if resultado['classe'] == 'medido' and not ns:
        raise ValueError('medido exige tentativa real no histórico, não texto da LLM')
    if resultado['classe'] == 'medido' and (not isinstance(resultado.get('reproducao'), str) or not resultado['reproducao'].strip()):
        raise ValueError('resultado medido exige reprodução descrita')
    evidencias = resultado.get('evidencias', [])
    if not isinstance(evidencias, list) or not evidencias:
        raise ValueError('evidências locais obrigatórias')
    for nome in evidencias:
        if not isinstance(nome, str) or not (pasta / nome).resolve().is_relative_to(pasta.resolve()) or not (pasta / nome).is_file():
            raise ValueError('evidência inexistente/fora da campanha')
    tent = {t.get('n'): t for t in CP.historico(pasta) if t.get('tipo_linha') == 'tentativa'}
    if any(n not in tent or tent[n].get('experimento') != resultado.get('id') for n in ns):
        raise ValueError('tentativa não pertence ao experimento')
    if resultado['classe'] == 'medido' and any(tent[n].get('cena_ok') is not True or
                                              (tent[n].get('avaliacao') or {}).get('valida') is not True for n in ns):
        raise ValueError('medição/restauração não comprovada')
    def mudar(lab):
        h = next((h for h in lab['fila'] if h['id'] == resultado.get('id')), None)
        if h is None:
            raise ValueError('hipótese não está na fila')
        if any(k in resultado and resultado[k] != h[k] for k in ('hipotese', 'funcionalidade', 'proximo_teste')):
            raise ValueError('resultado não pode alterar metadados da hipótese')
        lab['experimentos'].append({**h, **resultado, 'tentativas': ns, 'quando': dt.datetime.now().isoformat()})
        lab['fila'].remove(h)
    lab = editar_laboratorio(pasta, mudar, registro=True)
    CP.eventos(pasta, 'experimento_concluido', resultado=resultado)
    return lab


def python_auxiliar(pasta: Path, script: Path, dados: Path) -> dict:
    import os
    import subprocess
    import time
    from unreal_macros import python_auxiliar as A
    c = CP.ler(pasta)
    if c.get('modo') != 'experimental':
        raise ValueError('Python auxiliar somente em modo experimental')
    motivos = CP.guarda(pasta)
    if motivos:
        raise ValueError('; '.join(motivos))
    for p in (script, dados):
        if not p.resolve().is_relative_to(pasta.resolve()) or not p.is_file() or p.stat().st_size > 10_000_000:
            raise ValueError('script/dados devem ser arquivos pequenos exclusivos da campanha')
    texto = script.read_text(encoding='utf-8')
    A.validar(texto)
    entrada = json.loads(dados.read_text(encoding='utf-8'))
    destino = (pasta / 'scripts' / ('exec-' + uuid.uuid4().hex[:12])).resolve()
    if not destino.is_relative_to(pasta.resolve()):
        raise ValueError('diretório scripts fora da campanha')
    destino.mkdir(parents=True, exist_ok=False)
    copia = destino / 'script.py'
    copia.write_text(texto, encoding='utf-8')
    CP.gravar(destino, 'dados.json', entrada)
    codigo = ('import sys,json; from pathlib import Path; sys.path.insert(0,sys.argv[1]); '
              'from unreal_macros.python_auxiliar import executar; '
              'executar(Path(sys.argv[2]).read_text(encoding="utf-8"),json.loads(Path(sys.argv[3]).read_text(encoding="utf-8")))')
    inicio = time.monotonic()
    saida = destino / 'saida.txt'
    with saida.open('wb') as f:
        try:
            proc = subprocess.run([sys.executable, '-I', '-c', codigo, str(RAIZ / 'src'), str(copia), str(destino / 'dados.json')],
                                  cwd=destino, env=dict(os.environ, UNREAL_MACROS_OFFLINE='1', PYTHONUTF8='1'),
                                  stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT,
                                  timeout=min(30, max(0.1, c['prazo_tentativas_ts'] - time.time())))
            retorno = proc.returncode
        except subprocess.TimeoutExpired:
            retorno = 124
    r = {'script': str(copia.relative_to(pasta)), 'sha256': CP.sha(copia), 'dados_sha256': CP.sha(destino / 'dados.json'),
         'saida': str(saida.relative_to(pasta)), 'codigo': retorno, 'duracao_s': time.monotonic() - inicio,
         'categoria': 'calculo_offline_auxiliar_nao_prova_unreal'}
    CP.gravar(destino, 'resultado.json', r)  # Preservado mesmo se registro central for bloqueado.
    def mudar(lab):
        lab['scripts'].append(r)
    editar_laboratorio(pasta, mudar, registro=True)
    CP.eventos(pasta, 'python_auxiliar', **r)
    return r


def fechar(pasta: Path, motivo: str, justificativa: str) -> dict:
    import time
    c = CP.ler(pasta)
    s = estado(pasta)
    if c.get('modo') != 'experimental':
        raise ValueError('fechamento de laboratório somente em modo experimental')
    if s['pendente']:
        raise ValueError('tentativa pendente: espere a limpeza')
    if motivo not in ('prazo', 'seguranca', 'esgotamento') or not justificativa.strip():
        raise ValueError('fim exige motivo permitido e justificativa')
    if motivo == 'prazo' and time.time() < c['prazo_tentativas_ts']:
        raise ValueError('prazo ainda não terminou')
    if motivo == 'seguranca' and not CP.inseguranca(pasta):
        raise ValueError('impedimento de segurança não comprovado')
    if motivo == 'esgotamento' and (s['fila_hipoteses'] or not s['experimentos']):
        raise ValueError('há hipóteses úteis ou falta histórico que fundamente o esgotamento')
    faltam = (s.get('testes_versao') or {}).get('faltam') or []
    if motivo == 'esgotamento' and faltam:
        # Campanha de teste da versão: "esgotei as ideias" não vale enquanto o programa não achar a evidência de
        # cada teste (ou o registro do defeito que impediu o teste). Prazo e segurança continuam fechando.
        raise ValueError(f"faltam testes da versão: {', '.join(faltam)}. Faça cada um (director_noite.py capacidades "
                         "mostra como) ou, se um deles não funciona, registre o achado com concluir "
                         "(classe suspeita, campo teste com o id e a evidência). Sem isso, só fecha por prazo ou segurança")
    CP.gravar(pasta, 'ENCERRAMENTO.json', {'id': c['id'], 'integridade': c['integridade'],
                                        'motivo': motivo, 'justificativa': justificativa,
                                        'quando': dt.datetime.now().isoformat()})
    CP.eventos(pasta, 'fechamento', motivo=motivo, justificativa=justificativa)
    return relatorio(pasta)


def controlar(pasta: Path, comando: str) -> dict:
    CP.ler(pasta)
    if comando not in ('pausar', 'encerrar'):
        raise ValueError('controle desconhecido')
    (pasta / ('PAUSA' if comando == 'pausar' else 'PARAR')).write_text(dt.datetime.now().isoformat(), encoding='utf-8')
    CP.eventos(pasta, comando, efeito='não admite novas operações; execução em curso limpa normalmente')
    if comando == 'encerrar':
        relatorio(pasta)
    return estado(pasta)


def relatorio(pasta: Path) -> dict:
    c = CP.ler(pasta)
    s = estado(pasta)
    linhas, ilegiveis = CP.historico_recuperavel(pasta)  # A19: a parte legível continua no relatório
    tent = [t for t in linhas if t.get('tipo_linha') == 'tentativa']
    # A29: com tentativa em curso o relatório é PROVISÓRIO (o resultado dela ainda não existe). O executor refaz o
    # relatório quando essa tentativa termina (fila_executor._relatorio_final_se_encerrada).
    provisorio = bool(s['pendente'])
    data = dict(s, provisorio=provisorio, objetivo=(pasta / 'OBJETIVO.txt').read_text(encoding='utf-8'),
                plano=json.loads((pasta / 'PLANO.json').read_text(encoding='utf-8')),
                inicio=c['inicio'], versoes=c['versoes'], historico=linhas,
                hipoteses=(pasta / 'LICOES.md').read_text(encoding='utf-8'),
                evolucao=[{'n': t.get('n'), 'nota': t.get('nota'), 'cena_ok': t.get('cena_ok')} for t in tent],
                evidencias=[str(p.relative_to(pasta)) for p in pasta.rglob('*') if p.is_file()
                            and p.name not in ('RELATORIO.json', 'RELATORIO.md')],
                autonomia_oito_horas_validada=False)
    json_path, md_path = pasta / 'RELATORIO.json', pasta / 'RELATORIO.md'
    CP.gravar(pasta, 'RELATORIO.json', data)
    melhor = s['melhor']
    aviso = ("> **RELATÓRIO PROVISÓRIO:** há uma tentativa em curso; o resultado dela ainda não está aqui. "
             "Este arquivo é refeito quando ela terminar.\n\n" if provisorio else "")
    if ilegiveis:
        aviso += (f"> **HISTÓRICO CORROMPIDO:** {len(ilegiveis)} linha(s) ilegível(is) em tentativas.jsonl (linha "
                  f"{', '.join(str(n) for n in ilegiveis[:10])}). A campanha fica bloqueada; o que aparece abaixo é só a "
                  "parte legível (evidência parcial) e o arquivo original não foi alterado.\n\n")
    txt = (f"# Campanha {c['id']}\n\n{aviso}## Objetivo original\n{data['objetivo']}\n\n"
           f"## Resultado\n- Situação: {s['situacao']}.\n- Sucesso medido: {'sim' if s['sucesso_medido'] else 'não'}.\n"
           f"- Tentativas registradas: {s['tentativas']}.\n- Duração decorrida: {s['duracao_decorrida_s']:.1f} s.\n"
           f"- Tempo efetivo das execuções com relógio: {s['tempo_execucao_medido_s']:.1f} s; durações ausentes: {s['duracoes_ausentes']}.\n"
           f"- Melhor: {('tentativa ' + str(melhor['n']) + ', nota ' + str(melhor['nota'])) if melhor else 'Nenhuma medição segura'}.\n"
           f"- Bloqueios: {s['bloqueios']}.\n- Execução pendente: {s['pendente']}.\n"
           f"- Experimentos concluídos: {s['experimentos_distintos']}; receitas/condições distintas: {s['receitas_distintas']}.\n"
           f"- Aprovações de tentativas: {s['aprovadas']}; reprovações: {s['reprovadas']}; sem medição: {s['sem_medicao']}.\n"
           f"- Tempo restante para novas tentativas: {s['tempo_restante_s']:.1f} s; repetições sem novidade de receita: {s['repeticoes_sem_novidade']}.\n"
           f"- Funções com tentativas: {s['funcionalidades_testadas']}; lacunas originais: {s['lacunas']}.\n"
           "- Limites de contrato não provam impossibilidade. Oito horas reais não certificadas.\n\n"
           f"## Critérios\n{c['cena']['criterios']}\n\n## Hipóteses e próxima ação\n{data['hipoteses']}\n\n"
           "## Experimentos, descobertas e reprodução\n" + json.dumps(s['experimentos'], ensure_ascii=False, indent=2) +
           "\n\n## Hipóteses pendentes\n" + json.dumps(s['fila_hipoteses'], ensure_ascii=False, indent=2) +
           "\n\n## Python auxiliar (não aprovação formal)\n" + json.dumps(s['scripts'], ensure_ascii=False, indent=2) +
           (("\n\n## Testes da versão " + str(s['testes_versao'].get('versao')) + " (conferidos pelo programa)\n"
             + '\n'.join(f"- {i['id']}: {i['situacao']}" + (f" ({i['falta']})" if i.get('falta') else '')
                         for i in s['testes_versao']['itens'])) if s.get('testes_versao') else '') +
           "\n\n## Evidências\n" + '\n'.join('- ' + p for p in data['evidencias']) + '\n')
    md_path.write_text(txt, encoding='utf-8')
    return {'id': c['id'], 'json': str(json_path), 'markdown': str(md_path), 'situacao': s['situacao'],
            'provisorio': provisorio}


def perfil_local() -> bool:
    """Usa o parser do Hermes instalado, sem dependência nova no venv Runtime e sem exibir config/segredos."""
    import os
    import subprocess
    home = Path(os.environ.get('LOCALAPPDATA', '')) / 'hermes'
    py = home / 'hermes-agent/venv/Scripts/python.exe'
    config = home / 'profiles' / L2.PERFIL / 'config.yaml'
    codigo = ("import sys,yaml; from pathlib import Path; "
              "c=yaml.safe_load(Path(sys.argv[1]).read_text(encoding='utf-8')); m=c.get('model',{}); "
              "sys.exit(0 if isinstance(m,dict) and str(m.get('default','')).lower().startswith('qwen') "
              "and m.get('base_url')=='http://127.0.0.1:8080/v1' and m.get('provider')=='qwen-l40s' else 1)")
    return subprocess.run([str(py), '-c', codigo, str(config)], capture_output=True, timeout=30).returncode == 0


def ambiente() -> list:
    import subprocess
    if not perfil_local():
        return ['perfil não comprovado como Qwen local; não lançar outro modelo']
    net = subprocess.run(['netstat', '-ano', '-p', 'TCP'], capture_output=True, timeout=30).stdout.decode('utf-8', 'replace')
    return L2.checar_ambiente(net, (RAIZ / 'work/unreal.trava').exists())


def processo_vigia(pasta: Path) -> str:
    from unreal_macros import processos as P
    lan = pasta / 'LANCAMENTO.json'
    if not lan.exists():
        return P.MORTO
    try:
        return P.estado_processo(json.loads(lan.read_text(encoding='utf-8')).get('vigia_pid'))
    except (OSError, ValueError, AttributeError):
        return P.DESCONHECIDO


def iniciar(pasta: Path, autorizado: bool = False, continuar: bool = False) -> dict:
    from unreal_macros import processos as P, trava as T
    if not autorizado:
        raise ValueError('iniciar/continuar exige autorização do usuário')
    c = CP.ler(pasta)
    if (pasta / 'PARAR').exists():
        raise ValueError('campanha encerrada; não reabrir identidade antiga')
    if CP.inseguranca(pasta):
        raise ValueError('; '.join(CP.inseguranca(pasta)))
    if not c['executavel']:
        raise ValueError('; '.join(c['bloqueios']))
    import time
    if time.time() >= c['prazo_tentativas_ts']:
        raise ValueError('prazo absoluto encerrado; não prolongar campanha')
    if (pasta / 'PAUSA').exists() and not continuar:
        raise ValueError('campanha pausada; use continuar')
    lock = str(pasta.parent / 'inicio.trava')  # serializa arranque entre campanhas do perfil
    T.pegar(lock, 'director-noite:' + c['id'])
    try:
        processo = processo_vigia(pasta)
        if processo != P.MORTO:
            if continuar and processo == P.VIVO:
                (pasta / 'PAUSA').unlink(missing_ok=True)
                CP.eventos(pasta, 'continuar', vigia_existente=True)
                return estado(pasta)
            raise ValueError('vigia viva ou desconhecida; não lançar outra')
        st = T.estado(str(pasta.parent / 'operador.trava'))
        if st['estado'] not in ('livre', 'morta'):
            raise ValueError('vigia de outra campanha possui o operador: ' + st['estado'])
        # A vigia pode ter caído enquanto a sessão Hermes ainda trabalha.
        # PID desconhecido é bloqueio, não autorização para criar outro escritor.
        # A24: se a sessão viva é a DESTA campanha (memória com a identidade dela, PID comprovadamente VIVO), o que
        # falta é só o observador: o lançamento abaixo cria apenas a vigia, e a vigia não relança enquanto a sessão
        # registrada estiver viva. Sessão de outra campanha, ou de identidade desconhecida, continua bloqueando.
        sessao_propria = None
        for outra in pasta.parent.glob('dn-*'):
            if not outra.is_dir():
                continue
            if outra != pasta and processo_vigia(outra) != P.MORTO:
                raise ValueError('outra campanha tem vigia viva/desconhecida: ' + outra.name)
            memoria = outra / 'vigia/memoria.json'
            if memoria.exists():
                try:
                    m = json.loads(memoria.read_text(encoding='utf-8'))
                    if m.get('campanha') != outra.name or m.get('lancamento_em_curso'):
                        raise ValueError('lançamento ou identidade da memória não comprovados')
                    pid = m.get('sessao_pid')
                except (ValueError, OSError, AttributeError) as ex:
                    raise ValueError('estado_inseguro: memória ilegível da campanha ' + outra.name) from ex
                processo_sessao = P.estado_processo(pid) if pid else P.MORTO
                if outra == pasta and processo_sessao == P.VIVO:
                    sessao_propria = pid
                elif processo_sessao == P.VIVO:
                    raise ValueError('sessão viva de outra campanha: ' + outra.name)
                elif processo_sessao != P.MORTO:
                    raise ValueError('sessão de identidade desconhecida (processo não verificável): ' + outra.name)
        motivos = ambiente()
        if motivos:
            CP.eventos(pasta, 'infraestrutura_indisponivel', motivos=motivos)
            raise ValueError('; '.join(motivos))
        CP.gravar(pasta, 'AUTORIZACAO.json', {'id': c['id'], 'integridade': c['integridade'],
                                            'quando': dt.datetime.now().isoformat()})
        if continuar:
            (pasta / 'PAUSA').unlink(missing_ok=True)
        motivos = CP.guarda(pasta)
        if motivos:
            raise ValueError('; '.join(motivos))
        # Somente a vigia cria a primeira sessão, evitando dois Productores no arranque.
        info = L2.lancar(str(pasta / 'PEDIDO.md'), str(pasta), c['cena'], 'noite', campanha=c['id'])
        CP.gravar(pasta, 'LANCAMENTO.json', info)
        if sessao_propria:
            CP.eventos(pasta, 'retomada_da_vigia', sessao_pid=sessao_propria, lancamento=info,
                       efeito='só o observador foi recriado; a sessão viva da campanha continua a mesma')
        CP.eventos(pasta, 'continuar' if continuar else 'iniciar', lancamento=info)
        return dict(info, id=c['id'], pasta=str(pasta))
    finally:
        T.soltar(lock)


def voltar(pasta: Path, n: int, linhagem: str) -> dict:
    CP.ler(pasta)
    motivos = CP.inseguranca(pasta)
    if motivos:
        raise ValueError('; '.join(motivos))
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', linhagem):
        raise ValueError('linhagem: nome curto, sem caminho')
    s = estado(pasta)
    if linhagem in s['linhagens']:
        raise ValueError('retorno exige linhagem nova para alternativa experimental')
    linhas = CP.historico(pasta)
    origens = [t for t in linhas if t.get('tipo_linha') == 'tentativa' and t.get('n') == n
               and t.get('cena_ok') is True and (t.get('avaliacao') or {}).get('valida') is True
               and type(t.get('nota')) in (int, float) and math.isfinite(t['nota'])]
    if len(origens) != 1:
        raise ValueError('origem não é uma tentativa única medida e segura desta campanha')
    t = origens[0]
    proposta = {'linhagem': linhagem, 'tipo': 'exploracao', 'de': n, 'passos': t['receita'],
                'hipotese': f'Retorno à receita medida da tentativa {n}; escrever hipótese alternativa antes de tentar.'}
    motivos = R.validar(proposta)
    if motivos:
        raise ValueError('; '.join(motivos))
    if R.assinatura(proposta) != t.get('assinatura'):
        raise ValueError('assinatura da receita diverge da medição de origem')
    arquivo = pasta / f'proposta-retorno-t{n:03d}-{uuid.uuid4().hex[:12]}.json'
    CP.gravar(pasta, arquivo.name, proposta)
    CP.eventos(pasta, 'retorno_receita', de=n, linhagem=linhagem, nota_origem=t['nota'], receita=arquivo.name)
    return {'receita': str(arquivo), 'de': n, 'nota_origem': t['nota'], 'unreal_alterado': False}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('capacidades')
    p = sub.add_parser('preparar')
    p.add_argument('--objetivo-arquivo', required=True)
    p.add_argument('--plano', required=True)
    p.add_argument('--horas', type=float, default=8)
    for nome in ('estado', 'relatorio', 'pausar', 'encerrar', 'iniciar', 'continuar', 'voltar',
                 'planejar', 'concluir', 'python', 'fechar'):
        q = sub.add_parser(nome)
        q.add_argument('id')
        if nome in ('iniciar', 'continuar'):
            q.add_argument('--autorizado', action='store_true')
        if nome in ('planejar', 'concluir'):
            q.add_argument('--arquivo', required=True)
        if nome == 'python':
            q.add_argument('--script', required=True)
            q.add_argument('--dados', required=True)
        if nome == 'fechar':
            q.add_argument('--motivo', choices=['prazo', 'seguranca', 'esgotamento'], required=True)
            q.add_argument('--justificativa', required=True)
        if nome == 'voltar':
            q.add_argument('--tentativa', type=int, required=True)
            q.add_argument('--linhagem', required=True)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore[attr-defined]
    try:
        if a.cmd == 'capacidades':
            out = capacidades()
        elif a.cmd == 'preparar':
            with Path(a.objetivo_arquivo).open(encoding='utf-8', newline='') as f:
                objetivo = f.read()
            out = preparar(objetivo, json.loads(Path(a.plano).read_text(encoding='utf-8')), a.horas)
        else:
            pasta = pasta_de(a.id)
            if a.cmd == 'estado':
                out = estado(pasta)
            elif a.cmd == 'relatorio':
                out = relatorio(pasta)
            elif a.cmd in ('pausar', 'encerrar'):
                out = controlar(pasta, a.cmd)
            elif a.cmd in ('iniciar', 'continuar'):
                out = iniciar(pasta, a.autorizado, a.cmd == 'continuar')
            elif a.cmd == 'planejar':
                out = planejar(pasta, json.loads(Path(a.arquivo).read_text(encoding='utf-8')))
            elif a.cmd == 'concluir':
                out = concluir(pasta, json.loads(Path(a.arquivo).read_text(encoding='utf-8')))
            elif a.cmd == 'python':
                out = python_auxiliar(pasta, Path(a.script), Path(a.dados))
            elif a.cmd == 'fechar':
                out = fechar(pasta, a.motivo, a.justificativa)
            else:
                out = voltar(pasta, a.tentativa, a.linhagem)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as ex:
        print(json.dumps({'erro': str(ex)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(main())
