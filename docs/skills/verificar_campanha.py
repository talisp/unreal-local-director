"""Obrigações objetivas do checkpoint Qwen; NÃO prova a verdade da prosa."""
import argparse
import json
import math
from pathlib import Path
import re

VERSION = '0.1.0'


def verificar_checkpoint(checkpoint_path, contexto):
    cp = Path(checkpoint_path)
    result = {'ok_objetivo': False, 'revisao_semantica_pendente': True, 'historico': False,
              'instrument_version': VERSION, 'motivos': []}
    reasons = result['motivos']
    companion = cp.with_suffix('.json')
    if not companion.is_file():
        result['historico'] = True
        reasons.append('checkpoint legado/sem JSON; revisão manual, sem conversão automática')
        return result
    try:
        md = cp.read_text(encoding='utf-8')
        data = json.loads(companion.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        reasons.append('checkpoint ausente/ilegível/truncado')
        return result
    if not isinstance(data, dict) or not isinstance(contexto, dict):
        reasons.append('checkpoint/contexto deve ser objeto')
        return result
    if type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        reasons.append('schema_version desconhecido')
    if data.get('instrument_version') != VERSION:
        reasons.append('instrument_version incompatível')
    for key, pattern in [('skill_version', r'[0-9]+\.[0-9]+\.[0-9]+'),
                         ('skill_sha256', r'[0-9a-f]{64}'), ('director_commit', r'[0-9a-f]{40}')]:
        value = data.get(key)
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            reasons.append(key + ' ausente/inválido')
        if contexto.get(key) is None or value != contexto.get(key):
            reasons.append(key + ' não corresponde ao contexto medido')
    limit = contexto.get('word_limit', 250)
    if type(limit) is not int or limit < 1:
        reasons.append('word_limit inválido')
    elif len(md.split()) > limit:
        reasons.append('limite de palavras excedido')
    result['palavras'] = len(md.split())
    if not isinstance(contexto.get('root'), str) or not isinstance(contexto.get('allowed_refs'), list):
        reasons.append('raiz/lista autorizada ausentes')
        return result
    root = Path(contexto['root']).resolve()
    allowed = contexto['allowed_refs']
    for field in ('evidence_reads', 'evidence_hashes', 'references', 'changed_files'):
        values = data.get(field)
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            reasons.append(field + ' deve ser lista de caminhos')
            continue
        for value in values:
            try:
                path = root / value
                path.resolve().relative_to(root)
            except (ValueError, OSError):
                reasons.append('caminho externo: ' + value)
                continue
            if value not in allowed or not path.is_file():
                reasons.append('referência ausente/não autorizada: ' + value)
            if field == 'evidence_reads' and value not in contexto.get('reads', []):
                reasons.append('leitura sem evento independente: ' + value)
            if field == 'evidence_hashes' and value not in contexto.get('hashes_after', {}):
                reasons.append('hash sem medição independente: ' + value)
            if field == 'changed_files':
                before, after = contexto.get('hashes_before', {}), contexto.get('hashes_after', {})
                if value not in before or value not in after or before[value] == after[value]:
                    reasons.append('mudança sem diferença medida: ' + value)
    for key in ('duration_s', 'budget_s'):
        value = data.get(key)
        if value is None and key == 'duration_s':
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
            reasons.append(key + ' inválido/ausente')
        elif key not in contexto or contexto[key] is None or value != contexto[key]:
            reasons.append(key + ' não corresponde à medição')
    duration, budget = contexto.get('duration_s'), contexto.get('budget_s')
    if isinstance(duration, (int, float)) and isinstance(budget, (int, float)) and duration > budget:
        reasons.append('orçamento medido excedido')
    if not isinstance(data.get('status'), str) or not data['status'].strip():
        reasons.append('status textual obrigatório')
    if not isinstance(data.get('next_step'), str) or not data['next_step'].strip():
        reasons.append('next_step textual obrigatório')
    origin = data.get('source_checkpoint')
    if 'source_checkpoint' not in data or (origin is not None and (not isinstance(origin, str) or origin not in allowed or not (root / origin).is_file())):
        reasons.append('origem ausente/não autorizada')
    result['ok_objetivo'] = not reasons
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--contexto', required=True)
    args = parser.parse_args(argv)
    try:
        context = json.loads(Path(args.contexto).read_text(encoding='utf-8'))
        result = verificar_checkpoint(args.checkpoint, context)
    except (ValueError, OSError) as exc:
        result = {'ok_objetivo': False, 'revisao_semantica_pendente': True, 'motivos': [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok_objetivo'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
