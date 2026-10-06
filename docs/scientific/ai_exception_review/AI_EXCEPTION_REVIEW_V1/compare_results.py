#!/usr/bin/env python3
"""AI_EXCEPTION_REVIEW_V1 coordinator utility. Standard library only; no network.

Checks form, exact evidence/claim agreement and routes exceptions. It does NOT
authenticate external evidence, score POS/KVS, authorize distribution or run
human reliability. Run without arguments for usage. Frozen inputs are read-only.
"""
import argparse
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROLES = ('EXPERT_A_CHATGPT_PRO', 'EXPERT_B_CHATGPT_PRO', 'EXPERT_C_CLAUDE_FABLE_5_1')
CUTOFF = '2011-12-15T23:59:59Z'
DIMENSIONS = ('actor_attribution', 'group_coverage', 'reference_coverage',
              'time_coverage', 'chain_support', 'context_sufficiency')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(value):
    return hashlib.sha256(value).hexdigest()


def read(path):
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError('Non-finite JSON number: ' + value)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'),
                      object_pairs_hook=no_duplicates, parse_constant=invalid_constant)


def utc(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('UTC/timezone required')
    return parsed.astimezone(timezone.utc)


def check_schema(value, schema, path='$'):
    """Validate the closed subset used in RESPONSE_SCHEMA.json, no dependencies."""
    types = schema.get('type')
    if types:
        types = types if isinstance(types, list) else [types]
        matches = {'null': value is None, 'object': isinstance(value, dict),
                   'array': isinstance(value, list), 'string': isinstance(value, str),
                   'boolean': isinstance(value, bool),
                   'number': type(value) in (int, float), 'integer': type(value) is int}
        if not any(matches[t] for t in types):
            raise ValueError(path + ': wrong type')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(path + ': value outside enum')
    if isinstance(value, dict):
        props = schema.get('properties', {})
        if set(schema.get('required', [])) - value.keys():
            raise ValueError(path + ': missing required keys')
        if schema.get('additionalProperties') is False and value.keys() - props.keys():
            raise ValueError(path + ': unexpected keys')
        for key in value.keys() & props.keys():
            check_schema(value[key], props[key], path + '.' + key)
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0):
            raise ValueError(path + ': insufficient items')
        if schema.get('uniqueItems') and len({canonical(v) for v in value}) != len(value):
            raise ValueError(path + ': duplicate items')
        for index, entry in enumerate(value):
            check_schema(entry, schema.get('items', {}), f'{path}[{index}]')
    if isinstance(value, str):
        if len(value.strip()) < schema.get('minLength', 0):
            raise ValueError(path + ': empty text')
        if 'pattern' in schema and not re.fullmatch(schema['pattern'], value):
            raise ValueError(path + ': pattern mismatch')
    if type(value) in (float, int):
        if value < schema.get('minimum', float('-inf')) or value > schema.get('maximum', float('inf')):
            raise ValueError(path + ': number out of range')


def proof_key(evidence):
    # URL equality alone never counts as proof. Same bytes, passage, preservation
    # time, locator, target and explicit scope are required. Different URLs for
    # the same preserved payload can be equivalent. No semantic synonym guessing.
    return canonical({key: sorted(evidence[key]) if key == 'fragment_ids' else evidence[key]
                      for key in ('evidence_kind', 'target_id', 'fragment_ids',
                                  'preserved_at_utc', 'payload_sha256', 'quote_sha256',
                                  'locator', 'claim_scope')})


def agreement_key(row):
    proof = sorted(proof_key(e) for e in row['evidence'] if e['decisive'])
    finding = {k: v for k, v in row['finding'].items() if k != 'language_explanation'}
    return canonical({'finding': finding, 'proof': proof})


def route(rows):
    if any(r['status'] == 'NEED_HUMAN' for r in rows):
        return 'HUMAN_EXCEPTION_QUEUE', 'AT_LEAST_ONE_NEED_HUMAN'
    if any(r['material_issues'] for r in rows):
        return 'HUMAN_EXCEPTION_QUEUE', 'EXPLICIT_MATERIAL_ISSUE'
    resolved = [r for r in rows if r['status'] == 'RESOLVED']
    if len(resolved) >= 2 and len({agreement_key(r) for r in resolved}) != 1:
        return 'HUMAN_EXCEPTION_QUEUE', 'EVIDENCE_OR_SCOPE_OR_TRANSLATION_DIFFERENCE_REQUIRES_REVIEW'
    if len(resolved) == 3:
        return 'AI_TRIAGE_RESOLVED', 'THREE_RESOLVED_WITH_IDENTICAL_STRUCTURED_CLAIM_AND_PROOF'
    if len(resolved) == 2:
        third = next(r for r in rows if r['status'] != 'RESOLVED')
        # A contradictory typed finding overrides a two-vote majority.
        if any(v == 'CONTRADICTED' for v in third['finding']['mapping_dimensions'].values()):
            return 'HUMAN_EXCEPTION_QUEUE', 'CONTRADICTORY_FINDING'
        if third['finding'].get('translation_ru') is not None and third['finding']['translation_ru'] != resolved[0]['finding'].get('translation_ru'):
            return 'HUMAN_EXCEPTION_QUEUE', 'THIRD_TRANSLATION_DIFFERENCE_REQUIRES_REVIEW'
        return 'AI_TRIAGE_CANDIDATE', 'TWO_MATCHING_RESOLVED_ONE_NOT_RESOLVED_SEPARATE_CHECK_REQUIRED'
    return 'HUMAN_EXCEPTION_QUEUE', 'ZERO_OR_ONE_RESOLVED_REMAINS_OPEN'


def validate_response(response, role, registry, schema):
    check_schema(response, schema)
    packet = registry['packets'][role]
    if response['review_id'] != registry['review_id'] or response['expert_id'] != role:
        raise ValueError('Wrong review or expert identity')
    if response['material_sha256'] != registry['material_sha256']:
        raise ValueError('Different factual material')
    if utc(response['completed_at_utc']) > datetime.now(timezone.utc):
        raise ValueError('Completion timestamp is in the future')
    att = response['attestation']
    if not all(att[k] for k in ('fresh_isolated_session', 'no_other_expert_answers',
                               'no_prior_review_decisions', 'no_outcome_used',
                               'no_factor_or_human_coding')):
        raise ValueError('Independence/scope attestation failed')
    units = {u['unit_id']: u for u in registry['units']}
    expected = packet['local_to_unit']
    rows = response['answers']
    if len(rows) != len(expected) or len({r['local_id'] for r in rows}) != len(rows):
        raise ValueError('Missing or duplicate units')
    if {r['local_id'] for r in rows} != set(expected):
        raise ValueError('Wrong packet local IDs')
    output = {}
    for row in rows:
        unit = units[expected[row['local_id']]]
        if row['target_id'] != unit['target_id']:
            raise ValueError(row['local_id'] + ': target mismatch')
        finding = row['finding']
        if finding['kind'] != unit['kind']:
            raise ValueError(row['local_id'] + ': review kind mismatch')
        if unit['kind'] == 'AVAILABILITY' and finding['availability'] is None:
            raise ValueError('Availability finding must explicitly retain NOT_PROVEN when unproved')
        if row['status'] != 'RESOLVED' and not row['remaining_unknowns']:
            raise ValueError(row['local_id'] + ': unresolved requires exact unknowns')
        if row['status'] == 'RESOLVED' and (row['remaining_unknowns'] or row['material_issues']):
            raise ValueError(row['local_id'] + ': RESOLVED with residual gap/dispute')
        relevant = set(unit['fragment_ids'])
        decisive = [e for e in row['evidence'] if e['decisive']]
        for evidence in row['evidence']:
            if evidence['target_id'] != unit['target_id']:
                raise ValueError(row['local_id'] + ': evidence targets another unit')
            if not set(evidence['fragment_ids']) <= relevant:
                raise ValueError(row['local_id'] + ': evidence references another fragment')
            if evidence['quote_sha256'] != sha(evidence['exact_quote'].encode('utf-8')):
                raise ValueError(row['local_id'] + ': quote hash mismatch')
            if evidence['evidence_kind'] == 'PRESERVATION_WITNESS':
                if not evidence['preserved_at_utc'] or not evidence['payload_sha256']:
                    raise ValueError(row['local_id'] + ': witness lacks time/bytes hash')
                if utc(evidence['preserved_at_utc']) > utc(CUTOFF):
                    if evidence['decisive']:
                        raise ValueError(row['local_id'] + ': post-cutoff evidence cannot be decisive')
            if evidence['decisive'] and unit['kind'] != 'TRANSLATION':
                if evidence['evidence_kind'] != 'PRESERVATION_WITNESS':
                    raise ValueError(row['local_id'] + ': current copy/publication date is not proof')
        if row['status'] == 'RESOLVED':
            if not decisive:
                raise ValueError(row['local_id'] + ': RESOLVED requires decisive evidence')
            if unit['kind'] == 'AVAILABILITY':
                if finding['availability'] not in ('PROVEN_PRE_CUTOFF', 'PROVEN_FRAGMENT_PRE_CUTOFF'):
                    raise ValueError('Availability remains unproved')
                for fid in relevant:
                    text = registry['fragment_texts'][fid]
                    if not any(fid in e['fragment_ids'] and text in e['exact_quote'] for e in decisive):
                        raise ValueError('Every selected exact fragment requires decisive literal proof')
                if finding['availability'] == 'PROVEN_PRE_CUTOFF':
                    if not finding['full_edition_identity_proven'] or not any(
                            e['payload_sha256'] == unit['frozen_content_hash'] for e in decisive):
                        raise ValueError('Full frozen edition identity not authenticated')
                elif finding['full_edition_identity_proven']:
                    raise ValueError('Fragment proof cannot imply full edition identity')
            elif unit['kind'] == 'MAPPING':
                if set(finding['mapping_dimensions'].values()) != {'SUPPORTED'}:
                    raise ValueError('Mapping dimensions not all supported')
                if {d for e in decisive for d in e['supports_dimensions']} != set(DIMENSIONS):
                    raise ValueError('Decisive evidence must explicitly support every mapping dimension')
            elif unit['kind'] == 'TRANSLATION':
                if not finding['translation_ru'] or not finding['language_explanation']:
                    raise ValueError('Translation and semantic justification required')
                if not any(unit['target_id'] in e['fragment_ids'] and
                           registry['fragment_texts'][unit['target_id']] in e['exact_quote'] for e in decisive):
                    raise ValueError('Translation must cite the exact original fragment')
        if unit['kind'] != 'AVAILABILITY' and (finding['availability'] is not None or finding['full_edition_identity_proven']):
            raise ValueError('Unrelated availability finding')
        if unit['kind'] != 'MAPPING' and set(finding['mapping_dimensions'].values()) != {'NOT_APPLICABLE'}:
            raise ValueError('Unrelated mapping findings')
        if unit['kind'] != 'TRANSLATION' and (finding['translation_ru'] is not None or finding['language_explanation'] is not None):
            raise ValueError('Unrelated translation answer')
        output[unit['unit_id']] = row
    return output


def compare(responses, registry, schema):
    if set(responses) != set(ROLES):
        raise ValueError('All three independent responses are required')
    if len({r['session_id'] for r in responses.values()}) != 3:
        raise ValueError('Independent session IDs required')
    validated = {role: validate_response(responses[role], role, registry, schema) for role in ROLES}
    output = []
    for unit in registry['units']:
        rows = [validated[role][unit['unit_id']] for role in ROLES]
        if any(r['attestation']['outcome_contamination_detected'] for r in responses.values()):
            status, reason = 'HUMAN_EXCEPTION_QUEUE', 'SESSION_OUTCOME_CONTAMINATION_ALL_UNITS_QUARANTINED'
        else:
            status, reason = route(rows)
        output.append({'unit_id': unit['unit_id'], 'target_id': unit['target_id'], 'kind': unit['kind'],
                       'triage': status, 'reason_code': reason,
                       'expert_statuses': {role: validated[role][unit['unit_id']]['status'] for role in ROLES},
                       'evidence_authentication': 'NOT_PERFORMED_BY_COMPARATOR',
                       'separate_check': 'PENDING' if status == 'AI_TRIAGE_CANDIDATE' else 'NOT_APPLICABLE',
                       'admission_changed': False})
    return {'review_id': registry['review_id'], 'state': 'THREE_RESPONSES_COMPARED',
            'material_sha256': registry['material_sha256'], 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
            'counts': {s: sum(row['triage'] == s for row in output) for s in
                       ('AI_TRIAGE_RESOLVED', 'AI_TRIAGE_CANDIDATE', 'HUMAN_EXCEPTION_QUEUE')},
            'units': output, 'human_validation': 'NOT_PERFORMED', 'inter_coder_reliability': 'NOT_COMPUTED',
            'engineering_development_blocked_by_human_reliability': False,
            'frozen_H1_H2_release': 'UNCHANGED_NO_AUTOMATIC_DISTRIBUTION'}


def human_packet(result, registry, responses=None):
    if result['state'] != 'THREE_RESPONSES_COMPARED':
        raise ValueError('Do not export an empty queue before three complete responses')
    selected = {r['unit_id'] for r in result['units'] if r['triage'] == 'HUMAN_EXCEPTION_QUEUE'}
    units = [u for u in registry['units'] if u['unit_id'] in selected]
    material = registry['material']
    fragment_ids = {f for u in units for f in u['fragment_ids']}
    relevant_items = {u['target_id'] for u in units if u['kind'] == 'MAPPING'}
    links = [l for l in material['fact_fragment_links'] if l['fragment_id'] in fragment_ids]
    fact_ids = {l['fact_id'] for l in links}
    version_ids = {f['document_version_id'] for f in material['text_fragments'] if f['fragment_id'] in fragment_ids}
    versions = [v for v in material['document_versions'] if v['document_version_id'] in version_ids]
    document_ids = {v['document_id'] for v in versions}
    documents = [d for d in material['documents'] if d['document_id'] in document_ids]
    source_ids = {d['source_id'] for d in documents}
    items = [i for i in material['coding_items'] if i['coding_item_id'] in relevant_items]
    actors = {i['actor_id'] for i in items}
    subset = {'cutoff_utc': CUTOFF, 'units': units, 'coding_items': items,
              'actors': [a for a in material['actors'] if a['actor_id'] in actors],
              'facts': [f for f in material['facts'] if f['fact_id'] in fact_ids],
              'text_fragments': [f for f in material['text_fragments'] if f['fragment_id'] in fragment_ids],
              'fact_fragment_links': links,
              'coding_item_fact_links': [l for l in material['coding_item_fact_links'] if l['coding_item_id'] in relevant_items],
              'document_versions': versions, 'documents': documents,
              'sources': [s for s in material['sources'] if s['source_id'] in source_ids],
              'witness_records': [w for w in material['witness_records'] if w['document_version_id'] in version_ids]}
    supplements = {}
    for role, response in (responses or {}).items():
        if response['attestation']['outcome_contamination_detected']:
            continue
        for answer in response['answers']:
            uid = registry['packets'][role]['local_to_unit'][answer['local_id']]
            if uid not in selected:
                continue
            for evidence in answer['evidence']:
                if evidence['evidence_kind'] not in ('PRESERVATION_WITNESS', 'CURRENT_COPY'):
                    continue
                neutral = {k: evidence[k] for k in ('evidence_id', 'evidence_kind', 'target_id',
                           'fragment_ids', 'url_or_identifier', 'preserved_at_utc', 'payload_sha256',
                           'exact_quote', 'quote_sha256', 'locator')}
                neutral['unit_id'] = uid
                supplements[canonical(neutral)] = neutral
    subset['submitted_witnesses_not_yet_authenticated'] = list(supplements.values())
    text = '# AI_EXCEPTION_REVIEW_V1 — HUMAN_EXCEPTION_QUEUE\n\n'
    text += ('Два сотрудника: E1 и E2; это проверка исключений Evidence, не HUMAN coding, '
             'не adjudication POS/KVS и не inter-coder reliability. Работу людей этот файл не запускает. '
             'Каждый работает отдельно с одинаковым материалом и не видит ответов другого. '
             'Применяется cutoff 15.12.2011 23:59:59 UTC; дата публикации не доказывает доступность редакции. '
             'Не использовать исход конфликта, не менять frozen chains/H1/H2. '
             'Проверять только перечисленные unit_id; приложение — их минимально связанный контекст.\n\n')
    text += f'Единиц HUMAN_EXCEPTION_QUEUE: {len(units)}.\n\n'
    if not units:
        text += 'Три полных ответа сравнены: очередь сейчас пуста. Кандидаты требуют отдельной проверки; допуск H1/H2 не изменён.\n'
    else:
        text += ('Для каждой единицы E1 и E2 отдельно возвращают RESOLVED / NOT_RESOLVED / NEED_HUMAN, '
                 'exact evidence + URL/UUID + locator/hash/time, причину, confidence [0,1] '
                 'и точные remaining_unknowns. Не назначать POS/KVS, UNO, RGU/KVPTN. '
                 'Не называть согласие двух проверяющих измерением HUMAN reliability.\n\n')
        text += ('Submitted witnesses в приложении — нейтральные материалы поиска для проверки, '
                 'не принятые доказательства. Проверьте сохранность, bytes, scope и cutoff самостоятельно. '
                 'Материалы из сеанса с outcome-contamination не перенесены; исходные вопросы сохраняются.\n\n')
        for u in units:
            text += f"- `{u['unit_id']}` / `{u['target_id']}`: {u['question']}\n"
        text += '\n```json\n' + json.dumps(subset, ensure_ascii=False, indent=2) + '\n```\n'
        empty = [{'unit_id': u['unit_id'], 'status': None, 'exact_evidence': None,
                  'evidence_reference': None, 'reason': None, 'confidence': None,
                  'remaining_unknowns': None} for u in units]
        text += '\n## Отдельные пустые формы\n\n```json\n' + json.dumps(
            {'E1': copy.deepcopy(empty), 'E2': copy.deepcopy(empty)}, ensure_ascii=False, indent=2) + '\n```\n'
    return text


def self_test():
    # Artificial routing-only examples. Never answers to historical CodingItems.
    evidence = {'evidence_kind': 'FROZEN_FRAGMENT', 'target_id': 'TEST-F', 'fragment_ids': ['TEST-F'],
                'preserved_at_utc': None, 'payload_sha256': None, 'quote_sha256': sha(b'fictional'),
                'locator': 'TEST-LOCATOR', 'claim_scope': 'TEST', 'decisive': True}
    base = {'status': 'RESOLVED', 'finding': {'mapping_dimensions': {d: 'NOT_APPLICABLE' for d in DIMENSIONS},
                                           'translation_ru': 'тест'}, 'evidence': [evidence], 'material_issues': []}
    passed = []
    def case(name, rows, wanted):
        assert route(rows)[0] == wanted, name
        passed.append(name)
    case('3 same proof', [copy.deepcopy(base) for _ in range(3)], 'AI_TRIAGE_RESOLVED')
    nr = copy.deepcopy(base); nr['status'] = 'NOT_RESOLVED'
    nh = copy.deepcopy(base); nh['status'] = 'NEED_HUMAN'
    case('2 same plus unresolved', [base, base, nr], 'AI_TRIAGE_CANDIDATE')
    case('NEED_HUMAN overrides majority', [base, base, nh], 'HUMAN_EXCEPTION_QUEUE')
    case('all unresolved', [nr, nr, nr], 'HUMAN_EXCEPTION_QUEUE')
    case('one resolved', [base, nr, nr], 'HUMAN_EXCEPTION_QUEUE')
    bad = copy.deepcopy(base); bad['material_issues'] = ['TEST contradiction']
    case('material issue overrides consensus', [base, base, bad], 'HUMAN_EXCEPTION_QUEUE')
    bad = copy.deepcopy(base); bad['evidence'][0]['payload_sha256'] = '0' * 64
    case('different bytes', [base, base, bad], 'HUMAN_EXCEPTION_QUEUE')
    bad = copy.deepcopy(base); bad['finding']['translation_ru'] = 'другая формулировка'
    case('translation wording requires review', [base, base, bad], 'HUMAN_EXCEPTION_QUEUE')
    bad = copy.deepcopy(nr); bad['finding']['mapping_dimensions'][DIMENSIONS[0]] = 'CONTRADICTED'
    case('contradiction in third answer', [base, base, bad], 'HUMAN_EXCEPTION_QUEUE')
    bad = copy.deepcopy(base); bad['confidence'] = 0.01
    case('confidence does not change result', [base, base, bad], 'AI_TRIAGE_RESOLVED')
    return passed


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--a', type=Path); p.add_argument('--b', type=Path); p.add_argument('--c', type=Path)
    p.add_argument('--out', type=Path, help='New output directory, must not already exist')
    p.add_argument('--self-test', action='store_true')
    args = p.parse_args()
    if args.self_test:
        print(json.dumps({'synthetic_self_tests_passed': self_test()}, ensure_ascii=False, indent=2))
        return
    if not all((args.a, args.b, args.c, args.out)):
        p.error('Provide --a --b --c and a NEW --out directory; no partial comparison')
    here = Path(__file__).resolve().parent
    freeze = read(here / 'FREEZE_MANIFEST.json')
    for file in freeze['files']:
        if sha((here / file['path']).read_bytes()) != file['sha256']:
            raise ValueError('Review freeze mismatch: ' + file['path'])
    registry = read(here / 'coordinator/REGISTRY.json')
    schema = read(here / 'RESPONSE_SCHEMA.json')
    responses = {role: read(path) for role, path in zip(ROLES, (args.a, args.b, args.c))}
    # Validate everything before creating any outputs. Never overwrite a run.
    result = compare(responses, registry, schema)
    result['response_file_sha256'] = {role: sha(path.read_bytes()) for role, path in zip(ROLES, (args.a, args.b, args.c))}
    result['review_manifest_sha256'] = sha((here / 'FREEZE_MANIFEST.json').read_bytes())
    future_human = human_packet(result, registry, responses)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'COMPARISON_RESULTS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (args.out / 'HUMAN_EXCEPTION_PACKET.md').write_text(future_human, encoding='utf-8')
    candidates = [r for r in result['units'] if r['triage'] == 'AI_TRIAGE_CANDIDATE']
    (args.out / 'CANDIDATE_CHECK_TEMPLATE.json').write_text(json.dumps({
        'state': 'PENDING_SEPARATE_EVIDENCE_CHECK', 'admission_unchanged': True,
        'entries': [{'unit_id': r['unit_id'], 'independent_verifier': None, 'verified_exact_evidence': None,
                     'result': None, 'reason': None, 'remaining_unknowns': None} for r in candidates]
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (args.out / 'RUN_MANIFEST.json').write_text(json.dumps({
        'review_id': registry['review_id'], 'review_manifest_sha256': result['review_manifest_sha256'],
        'response_file_sha256': result['response_file_sha256'],
        'files': [{'path': f.name, 'sha256': sha(f.read_bytes())} for f in sorted(args.out.iterdir()) if f.is_file()]
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result['counts'], ensure_ascii=False))


if __name__ == '__main__':
    main()