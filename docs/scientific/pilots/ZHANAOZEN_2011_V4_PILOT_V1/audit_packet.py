"""Read CP3 without modifying it; audit identifiers, hashes and reference coverage.

These checks do not establish historical truth, source independence or cutoff
admissibility. No factor values, weights or model calculations are produced.
"""
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

import openpyxl

ROOT = Path(__file__).resolve().parent
PACKET = ROOT / 'sources' / 'ZHANAOZEN_V4_2011_SEALED_EVIDENCE_PACKET_CP3.xlsx'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    source_json = ROOT / 'sources' / 'ZHANAOZEN_V4_2011_SEALED_EVIDENCE_PACKET_CP3.json'
    source_zip = ROOT / 'sources' / 'ZHANAOZEN_V4_2011_CP3_VALIDATION_PACKAGE.zip'
    packet_json = json.loads(source_json.read_text(encoding='utf-8-sig'))
    book = openpyxl.load_workbook(PACKET, read_only=True, data_only=True)
    tables = {}
    for sheet in book:
        if sheet.title == 'README':
            continue
        rows = iter(sheet.values)
        header = next(rows)
        tables[sheet.title] = [dict(zip(header, row)) for row in rows if any(v is not None for v in row)]
    book.close()
    json_tables = {'Actors': 'actors', 'Elements': 'analytical_elements', 'CodingItems': 'coding_items',
                   'Sources': 'sources', 'Documents': 'documents', 'DocumentVersions': 'document_versions',
                   'TextFragments': 'text_fragments', 'Facts': 'facts', 'FactFragmentLinks': 'fact_fragment_links',
                   'ItemFactLinks': 'coding_item_fact_links'}
    differing_cells = []
    for tab, key in json_tables.items():
        assert len(tables[tab]) == len(packet_json[key]), tab
        for i, (excel_row, json_row) in enumerate(zip(tables[tab], packet_json[key])):
            for field, value in excel_row.items():
                expected = json_row.get(field)
                if field in ('captured_at', 'accessed_at') and isinstance(value, (int, float)):
                    value = openpyxl.utils.datetime.from_excel(value).strftime('%Y-%m-%dT%H:%M:%SZ')
                if value is None and expected == '':
                    value = ''
                if value != expected:
                    differing_cells.append(dict(sheet=tab, row=i + 2, field=field))
    assert not differing_cells, differing_cells
    with zipfile.ZipFile(source_zip) as archive:
        manifest = json.loads(archive.read('ZHANAOZEN_V4_2011_CP3_MANIFEST.json'))
        archive_checks = {name: digest(archive.read(name)) == expected for name, expected in manifest['sha256'].items()}
        assert all(archive_checks.values())
        assert archive.read(PACKET.name) == PACKET.read_bytes()
        assert archive.read(source_json.name) == source_json.read_bytes()
        capture_files_present = [v['local_or_archive_locator'] for v in packet_json['document_versions']
                                 if v['local_or_archive_locator'] in archive.namelist()]
        human_book = openpyxl.load_workbook(io.BytesIO(archive.read('ZHANAOZEN_V4_2011_HUMAN_BLIND_CODING_TEMPLATE_CP3.xlsx')), read_only=True, data_only=True)
        human_rows = []
        for sheet in human_book:
            rows = iter(sheet.values)
            header = next(rows)
            if 'human_status' in header:
                human_rows = [dict(zip(header, row)) for row in rows if any(v is not None for v in row)]
        human_book.close()
        human_completed = sum(any(row.get(field) is not None for field in ('human_status','human_pos','human_sal','human_confidence','human_rationale','coder_id','coded_at')) for row in human_rows)
        assert len(human_rows) == 20
    keys = {'Actors': 'actor_id', 'Elements': 'element_id', 'CodingItems': 'coding_item_id',
            'Sources': 'source_id', 'Documents': 'document_id', 'DocumentVersions': 'document_version_id',
            'TextFragments': 'fragment_id', 'Facts': 'fact_id', 'FactFragmentLinks': 'link_id', 'ItemFactLinks': 'link_id'}
    indexes = {name: {row[keys[name]]: row for row in data} for name, data in tables.items()}
    duplicates = {name: [key for key, n in Counter(r[keys[name]] for r in rows).items() if n > 1]
                  for name, rows in tables.items()}
    references = [('Documents', 'source_id', 'Sources'), ('DocumentVersions', 'document_id', 'Documents'),
                  ('TextFragments', 'document_version_id', 'DocumentVersions'), ('FactFragmentLinks', 'fact_id', 'Facts'),
                  ('FactFragmentLinks', 'fragment_id', 'TextFragments'), ('ItemFactLinks', 'fact_id', 'Facts'),
                  ('ItemFactLinks', 'coding_item_id', 'CodingItems'), ('CodingItems', 'actor_id', 'Actors'),
                  ('CodingItems', 'element_id', 'Elements')]
    broken = [dict(table=t, row_id=r[keys[t]], field=f, target=r[f])
              for t, f, dst in references for r in tables[t] if r[f] not in indexes[dst]]
    if broken or any(duplicates.values()):
        raise ValueError(json.dumps({'broken': broken, 'duplicates': duplicates}))
    traces = []
    for n, link in enumerate(tables['FactFragmentLinks'], 2):
        fact = indexes['Facts'][link['fact_id']]
        fragment = indexes['TextFragments'][link['fragment_id']]
        version = indexes['DocumentVersions'][fragment['document_version_id']]
        document = indexes['Documents'][version['document_id']]
        source = indexes['Sources'][document['source_id']]
        traces.append(dict(fact_id=fact['fact_id'], fact_status=fact['status'], fact_type=fact['fact_type'],
                           fact_statement=fact['statement'], fact_time_start=fact['time_start'], fact_time_end=fact['time_end'],
                           fact_fragment_link_id=link['link_id'], relation=link['relation'],
                           fragment_id=fragment['fragment_id'], exact_text=fragment['exact_text'],
                           fragment_hash=fragment['fragment_hash'], fragment_hash_matches=digest(fragment['exact_text'].encode('utf-8')) == fragment['fragment_hash'],
                           document_version_id=version['document_version_id'], publication_date=version['publication_date'],
                           publication_date_precision=version['publication_date_precision'], captured_at=version['captured_at'],
                           is_after_cutoff=version['is_after_cutoff'], content_hash=version['content_hash'],
                           capture_locator=version['local_or_archive_locator'], document_id=document['document_id'],
                           document_title=document['title'], source_id=source['source_id'], publisher=source['publisher_or_origin'],
                           independence_group=source['independence_group'], source_url=source['url_or_locator']))
    coverage = []
    for item in tables['CodingItems']:
        links = [r for r in tables['ItemFactLinks'] if r['coding_item_id'] == item['coding_item_id']]
        fact_ids = sorted({r['fact_id'] for r in links})
        tt = [t for t in traces if t['fact_id'] in fact_ids]
        groups = sorted({t['independence_group'] for t in tt})
        coverage.append(dict(coding_item_id=item['coding_item_id'], actor_code=item['actor_code'],
                             actor_id=item['actor_id'], element_code=item['element_code'], element_id=item['element_id'],
                             time_slice_id=item['time_slice_id'], cutoff_date=item['cutoff_date'],
                             reference_statement=item['reference_statement'], fact_ids=';'.join(fact_ids),
                             link_roles=';'.join(sorted({r['role'] for r in links})),
                             fact_count=len(fact_ids), fragment_count=len({t['fragment_id'] for t in tt}),
                             recorded_independence_groups=';'.join(groups), recorded_group_count=len(groups),
                             disputed_fact_count=sum(indexes['Facts'][fid]['status'] == 'DISPUTED' for fid in fact_ids)))
    def write_csv(name, rows):
        with (ROOT / name).open('w', encoding='utf-8-sig', newline='') as out:
            writer = csv.DictWriter(out, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    write_csv('EVIDENCE_TRACE_INDEX.csv', traces)
    write_csv('CODING_ITEM_COVERAGE.csv', coverage)
    linked = {r['fact_id'] for r in tables['ItemFactLinks']}
    paired = {(r['actor_id'], r['element_id']) for r in tables['CodingItems']}
    missing = [dict(actor_code=a['code'], element_code=e['code'])
               for a in tables['Actors'] for e in tables['Elements'] if (a['actor_id'], e['element_id']) not in paired]
    summary = dict(
        report_id='ZHANAOZEN_2011_HISTORICAL_ASSESSMENT_REPORT',
        pilot_id='ZHANAOZEN_2011_V4_PILOT_V1',
        audit_kind='PACKET_STRUCTURE_AND_COVERAGE_ONLY',
        source_url='https://docs.google.com/spreadsheets/d/1QbPyyXk09RrMoFiFsxXknZyiky4TTFyM/edit',
        packet_bytes=PACKET.stat().st_size, packet_sha256=digest(PACKET.read_bytes()),
        packet_json_bytes=source_json.stat().st_size, packet_json_sha256=digest(source_json.read_bytes()),
        archive_bytes=source_zip.stat().st_size, archive_sha256=digest(source_zip.read_bytes()),
        archive_manifest_checks=archive_checks,
        json_excel_differing_cells=differing_cells,
        case_id=packet_json['metadata']['case_id'], time_slice_id=packet_json['time_slices'][0]['time_slice_id'],
        information_cutoff_date=packet_json['metadata']['cutoff_date'],
        capture_files_present_in_cp3_archive=capture_files_present,
        human_template_rows=len(human_rows), human_template_rows_with_coding=human_completed,
        sheet_counts={k: len(v) for k, v in tables.items()},
        duplicate_ids=duplicates, broken_references=broken,
        fact_status_counts=dict(Counter(r['status'] for r in tables['Facts'])),
        fact_type_counts=dict(Counter(r['fact_type'] for r in tables['Facts'])),
        fact_fragment_relation_counts=dict(Counter(r['relation'] for r in tables['FactFragmentLinks'])),
        item_fact_role_counts=dict(Counter(r['role'] for r in tables['ItemFactLinks'])),
        fragment_hash_matches=sum(digest(r['exact_text'].encode('utf-8')) == r['fragment_hash'] for r in tables['TextFragments']),
        fragment_hash_mismatch_ids=[r['fragment_id'] for r in tables['TextFragments'] if digest(r['exact_text'].encode('utf-8')) != r['fragment_hash']],
        missing_fragment_context=sum(not r['page_section'] for r in tables['TextFragments']),
        missing_translation_text=sum(not r['translation_text'] for r in tables['TextFragments']),
        publication_date_range=[min(str(r['publication_date']) for r in tables['DocumentVersions']), max(str(r['publication_date']) for r in tables['DocumentVersions'])],
        fact_date_range=[min(str(r['time_start']) for r in tables['Facts']), max(str(r['time_end']) for r in tables['Facts'])],
        capture_dates=sorted({r['captured_at'] for r in packet_json['document_versions']}),
        after_cutoff_flag_counts=dict(Counter(str(r['is_after_cutoff']) for r in tables['DocumentVersions'])),
        publication_precision_counts=dict(Counter(r['publication_date_precision'] for r in tables['DocumentVersions'])),
        recorded_independence_groups=dict(Counter(r['independence_group'] for r in tables['Sources'])),
        coding_items_by_element=dict(Counter(r['element_code'] for r in tables['CodingItems'])),
        coding_items_by_actor=dict(Counter(r['actor_code'] for r in tables['CodingItems'])),
        linked_unique_facts=len(linked), unlinked_fact_ids=[r['fact_id'] for r in tables['Facts'] if r['fact_id'] not in linked],
        disputed_facts=[dict(fact_id=r['fact_id'], statement=r['statement'], linked_to_coding_item=r['fact_id'] in linked)
                        for r in tables['Facts'] if r['status'] == 'DISPUTED'],
        missing_actor_element_pairs=missing,
        limits=['Record counts are inventory statistics, never factor values.',
                'Recorded independence-group counts do not establish independent corroboration.',
                'Publication dates and is_after_cutoff flags do not establish availability of the captured version before cutoff.',
                'Document capture files are not embedded in this workbook; their content hashes were not verified.',
                'No HUMAN historical assessment or ValidationRecord is created.'])
    (ROOT / 'PACKET_AUDIT.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')
    repo = ROOT.parents[3]
    method_files = ['FACTOR_ONTOLOGY.md', 'factors.metadata.json', 'HISTORICAL_ASSESSMENT_SCHEMA.json',
                    'HISTORICAL_ASSESSMENT_MODEL.md', 'NON_INFERENCE_RULES.md', 'CASE_MAPPING_SCHEMA.json',
                    'CASE_MAPPING_MODEL.md', 'ZHANAOZEN_2011_EXAMPLE.json', 'VALIDATION_SCHEMA.json', 'VALIDATION_PROTOCOL.md']
    frozen = {'baseline_commit': 'ea7b8c40f18bd1dc78bc41564af146c0f13b3012',
              'files': {f'docs/scientific/{name}': digest((repo / 'docs/scientific' / name).read_bytes()) for name in method_files},
              'sources': {str(path.relative_to(ROOT)).replace('\\', '/'): digest(path.read_bytes()) for path in (PACKET, source_json, source_zip)},
              'source_manifest_hash_as_recorded_not_recomputed': packet_json['metadata']['source_manifest_hash']}
    (ROOT / 'INPUT_MANIFEST.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: summary[key] for key in (
        'sheet_counts', 'fragment_hash_matches', 'fact_status_counts',
        'archive_manifest_checks', 'json_excel_differing_cells',
        'human_template_rows_with_coding', 'broken_references')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
