import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description='Print extracted tables, links and validation counts.')
    parser.add_argument('result', nargs='?', default='data/output/result.json')
    args = parser.parse_args()
    path = Path(args.result)
    if not path.is_file():
        parser.error(f'Result not found: {path}; run python main.py first.')
    result = json.loads(path.read_text(encoding='utf8'))
    document = result['document']
    print(f"Company: {document.get('company')} | Periods: {', '.join(document.get('reporting_period', []))} | Currency: {document.get('currency')}")
    print(f"PDF pages: {document['page_count']} | Summary tables: {len(result['summary_tables'])}")
    for note in result['notes']:
        print(f"Note {note['number']}: pages {note['start_page']}-{note['end_page']} | Tables: {len(note['tables'])}")
    rows = {row['id']: row for table in result['summary_tables'] for row in table['rows']}
    for relation in result['relationships']:
        print(f"\n{rows[relation['summary_row_id']]['normalized_label']} -> {', '.join(relation['note_row_ids'])}")
        print(f"  Confidence: {relation['confidence']:.3f} | Warnings: {', '.join(relation['warnings']) or '-'}")
        for evidence in relation['numeric_evidence']:
            print(f"  {evidence['period']}: {evidence['summary_value']} = {evidence['note_value']} | Equal: {evidence['equal']}")
    from src.validation import summarize
    print('\nValidation: ' + json.dumps(summarize(result['validation']), ensure_ascii=False))
    ml = result['processing']['ml']
    print(f"Models: embedding={ml['embedding_inference']}, reranker={ml['reranker_inference']}, fallbacks={len(ml['fallbacks'])}")
    print(f'JSON: {path.resolve()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
