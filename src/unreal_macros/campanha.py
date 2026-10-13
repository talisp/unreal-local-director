"""Identidade e barreiras persistentes de campanhas Director (sem conexão Unreal)."""
import hashlib
import json
from pathlib import Path


def sha(arquivo: Path) -> str:
    return hashlib.sha256(arquivo.read_bytes()).hexdigest()


def ler(pasta: str | Path) -> dict:
    p = Path(pasta).resolve()
    c = json.loads((p / 'campanha.json').read_text(encoding='utf-8'))
    if c.get('id') != p.name or c.get('schema') != 1:
        raise ValueError('identidade da campanha inválida')
    for name, digest in c['arquivos'].items():
        if name not in ('OBJETIVO.txt', 'PLANO.json', 'CENA.md', 'PEDIDO.md') or sha(p / name) != digest:
            raise ValueError(f'arquivo imutável divergente: {name}')
    identidade = {k: v for k, v in c.items() if k != 'integridade'}
    if hashlib.sha256(json.dumps(identidade, sort_keys=True, ensure_ascii=False).encode()).hexdigest() != c['integridade']:
        raise ValueError('manifesto da campanha divergente')
    raiz = Path(__file__).resolve().parents[2]
    for nome, digest in c['versoes'].items():
        arquivo = raiz / nome
        if arquivo.resolve().is_relative_to(raiz) and sha(arquivo) == digest:
            continue
        raise ValueError(f'versão mudou durante a campanha: {nome}')
    return c


def historico(pasta: str | Path) -> list:
    p = Path(pasta) / 'tentativas.jsonl'
    if not p.exists():
        return []
    out = []
    for n, linha in enumerate(p.read_text(encoding='utf-8').splitlines(), 1):
        if not linha.strip():
            continue
        d = json.loads(linha)  # campanha não ignora linha cortada por queda
        if not isinstance(d, dict):
            raise ValueError(f'registro inválido na linha {n}')
        out.append(d)
    return out


def historico_recuperavel(pasta: str | Path) -> tuple:
    """(registros legíveis, números das linhas ilegíveis). SÓ para apresentação e perícia (A19): quem AUTORIZA uma
    operação usa historico(), que não tolera linha cortada. O arquivo original nunca é alterado."""
    p = Path(pasta) / 'tentativas.jsonl'
    if not p.exists():
        return [], []
    bons, ruins = [], []
    for n, linha in enumerate(p.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
        if not linha.strip():
            continue
        try:
            d = json.loads(linha)
        except ValueError:
            d = None
        if isinstance(d, dict):
            bons.append(d)
        else:
            ruins.append(n)
    return bons, ruins


def conclusao_segura(linhas: list, pendente: dict | None) -> bool:
    """A04: a reserva `pendente` já tem UMA conclusão final segura (cena_ok True) da MESMA execução? Então o que
    sobrou é só a pendência administrativa (o processo caiu entre gravar o resultado e retirar a reserva).
    Sem identidade de execução, com mais de uma conclusão ou sem restauração comprovada: False (segue bloqueado)."""
    if not isinstance(pendente, dict) or not pendente.get('execucao'):
        return False
    finais = [t for t in linhas if t.get('tipo_linha') == 'tentativa' and t.get('execucao') == pendente['execucao']]
    return len(finais) == 1 and finais[0].get('n') == pendente.get('n') and finais[0].get('cena_ok') is True


def inseguranca(pasta: str | Path) -> list:
    from . import processos as P
    p = Path(pasta)
    try:
        linhas = historico(p)
        e = json.loads((p / 'estado.json').read_text(encoding='utf-8')) if (p / 'estado.json').exists() else {}
        if not isinstance(e, dict):
            raise ValueError('estado ilegível')
        memoria = p / 'vigia/memoria.json'
        if memoria.exists():
            m = json.loads(memoria.read_text(encoding='utf-8'))
            if m.get('campanha') != p.name or m.get('lancamento_em_curso'):
                return ['estado_inseguro: identidade da memória/lançamento de sessão não comprovado']
        pend = e.get('pendente')
        # A28: início e fim se correspondem NA ORDEM e um a um. Um fim antigo não fecha um início posterior de
        # mesmo número; número reutilizado ou fim de outra execução é ambiguidade, e ambiguidade bloqueia.
        iniciados, abertos = set(), {}
        for t in linhas:
            tipo, n = t.get('tipo_linha'), t.get('n')
            if t.get('classe_erro') == 'estado_parcial' or tipo in ('estado_parcial', 'tentativa_interrompida'):
                return ['estado_inseguro: operação parcial/interrompida; restauração não comprovada']
            if tipo == 'tentativa' and t.get('cena_ok') is not True:
                return ['estado_inseguro: restauração não comprovada no resultado']
            if tipo == 'tentativa_inicio':
                if n in iniciados:
                    return ['estado_inseguro: número de tentativa reutilizado; início sem correspondência exclusiva']
                iniciados.add(n)
                abertos[n] = t
            elif tipo == 'tentativa' and n in iniciados:  # fim sem início = registro antigo: segue valendo como antes
                inicio = abertos.pop(n, None)
                if inicio is None:
                    return ['estado_inseguro: conclusão repetida para a mesma tentativa']
                if inicio.get('execucao') and t.get('execucao') and inicio['execucao'] != t['execucao']:
                    return ['estado_inseguro: conclusão de outra execução; início sem conclusão comprovada']
        for n in abertos:
            if not pend or pend.get('n') != n or P.estado_processo(pend.get('pid')) != P.VIVO:
                return ['estado_inseguro: execução iniciada sem conclusão comprovada']
        if e.get('runs_para_limpar') or e.get('seqs_para_apagar') or e.get('atores_para_limpar'):
            return ['estado_inseguro: há limpeza pendente de operação interrompida']
        if pend and P.estado_processo(pend.get('pid')) != P.VIVO and not conclusao_segura(linhas, pend):
            return ['estado_inseguro: tentativa pendente sem dono comprovadamente vivo']
        return []
    except (ValueError, OSError, TypeError, AttributeError):
        return ['estado_inseguro: histórico/estado ilegível; não continuar automaticamente']


def laboratorio(pasta: str | Path) -> dict:
    p = Path(pasta)
    c = ler(p)
    arq = p / 'LABORATORIO.json'
    if not arq.exists():
        return {'id': c['id'], 'fila': [], 'experimentos': [], 'scripts': []}
    lab = json.loads(arq.read_text(encoding='utf-8'))
    if not isinstance(lab, dict) or lab.get('id') != c['id'] or any(
            not isinstance(lab.get(k), list) for k in ('fila', 'experimentos', 'scripts')):
        raise ValueError('laboratório ilegível ou de outra campanha')
    if len(lab['fila']) > 5 or any(not isinstance(h, dict) or any(
            not isinstance(h.get(k), str) or not h[k].strip()
            for k in ('id', 'hipotese', 'funcionalidade', 'proximo_teste')) for h in lab['fila']):
        raise ValueError('fila do laboratório malformada')
    if any(not isinstance(e, dict) or not isinstance(e.get('funcionalidade'), str) or
           not isinstance(e.get('tentativas'), list) for e in lab['experimentos']):
        raise ValueError('experimentos do laboratório malformados')
    if any(not isinstance(s, dict) or type(s.get('codigo')) is not int or
           not isinstance(s.get('saida'), str) for s in lab['scripts']):
        raise ValueError('scripts do laboratório malformados')
    return lab


def encerrada(pasta: str | Path) -> bool:
    p = Path(pasta)
    c = ler(p)
    if c.get('modo') != 'experimental':
        return (p / 'FECHAMENTO.md').exists()
    arq = p / 'ENCERRAMENTO.json'
    if not arq.exists():
        return False
    e = json.loads(arq.read_text(encoding='utf-8'))
    if not isinstance(e, dict) or e.get('id') != c['id'] or e.get('integridade') != c['integridade']:
        raise ValueError('encerramento de outra campanha')
    return True


def guarda(pasta: str | Path, agora: float | None = None, admissao: bool = True) -> list:
    import time
    p = Path(pasta)
    try:
        c = ler(p)
    except (ValueError, OSError, KeyError, TypeError):
        return ['estado_inseguro: identidade/arquivos da campanha não conferem']
    motivos = inseguranca(p)
    if motivos:
        return motivos
    if not c['executavel']:
        return list(c['bloqueios'])
    for nome, motivo in [('PARAR', 'campanha encerrada'), ('PAUSA', 'campanha pausada')]:
        if (p / nome).exists():
            return [motivo]
    try:
        laboratorio(p)
        fechada = encerrada(p)
    except (ValueError, OSError, TypeError, KeyError):
        return ['estado_inseguro: laboratório/encerramento ilegível']
    if fechada:
        return ['campanha já tem fechamento']
    limite = c['prazo_tentativas_ts'] if admissao else c['fim_ts']
    if (time.time() if agora is None else agora) >= limite:
        return ['prazo absoluto da campanha encerrado']
    try:
        a = json.loads((p / 'AUTORIZACAO.json').read_text(encoding='utf-8'))
        if a.get('id') != c['id'] or a.get('integridade') != c['integridade']:
            return ['autorização não pertence a esta campanha']
    except (ValueError, OSError, AttributeError):
        return ['campanha não iniciada/autorizada']
    return []


def sucesso_seguro(tentativas: list) -> dict | None:
    """O sucesso da CAMPANHA: a mesma apuração de fila.sucesso (tentativas distintas, mesmas condições/fps/versões),
    exigindo ainda a prova positiva de restauração e de avaliação válida (campo ausente NÃO passa aqui)."""
    from . import fila as F
    return F.sucesso([t for t in tentativas
                      if t.get('cena_ok') is True and (t.get('avaliacao') or {}).get('valida') is True])


def gravar(pasta: Path, nome: str, dados: dict):
    import uuid
    tmp = pasta / (nome + '.' + uuid.uuid4().hex + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.flush()
        import os
        os.fsync(f.fileno())
    tmp.replace(pasta / nome)


def eventos(pasta: Path, evento: str, **dados):
    import datetime as dt
    import os
    with (pasta / 'eventos.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(dict(quando=dt.datetime.now().isoformat(), evento=evento, **dados),
                           ensure_ascii=False, allow_nan=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
