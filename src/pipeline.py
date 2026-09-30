from pathlib import Path
import json
import logging
import time
import platform
from datetime import datetime,timezone
from importlib.metadata import version
from src.pdf import inspect_pdf
from src.ocr import OCREngine
from src.tables import extract_table,extract_note_tables
from src.locator import locate_note
from src.layout import group_lines
from src.refinement import refine_cells
from src.matching import Matchers
from src.validation import validate,summarize,error_analysis
from src.schema import Result
from src.confidence import mean,flag

LOG=logging.getLogger(__name__)

def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    tmp.replace(path)

def run(cfg: dict,force: bool=False) -> dict:
    start=time.perf_counter()
    out=Path(cfg['output_dir'])
    out.mkdir(parents=True,exist_ok=True)
    handler=logging.FileHandler(out/'pipeline.log',encoding='utf8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logging.getLogger().addHandler(handler)
    LOG.info('[1/15] Inspecting PDF')
    document=inspect_pdf(cfg['document']['input_path'])
    write_json(out/'inspection.json',document)
    rng=cfg['summary_tables']['page_range']
    if rng['end']>document['page_count']:
        raise ValueError('Summary page range exceeds document page count.')
    engine=OCREngine(cfg,document,force)
    threshold=cfg['confidence']['low_confidence_threshold']
    LOG.info('[2-4/15] Rendering, preprocessing, OCR summary pages')
    summary_pages=[engine.page(p,True) for p in range(rng['start'],rng['end']+1)]
    LOG.info('[5-6/15] Layout, hierarchy, normalization and uncertain-cell re-reading')
    summaries=[]
    for page in summary_pages:
        table=extract_table(page,threshold)
        if table:
            refine_cells(table,page,engine)
            summaries.append(table)
    LOG.info('[7/15] Searching headings across every physical page')
    pages=[engine.page(p) for p in range(1,document['page_count']+1)]
    note=locate_note(pages,cfg['notes']['target_note'])
    LOG.info('Detected note %s at physical pages %s-%s',note['number'],note['start_page'],note['end_page'])
    LOG.info('[8/15] Extracting note tables inside detected section')
    note['tables']=[]
    for p in range(note['start_page'],note['end_page']+1):
        page=engine.page(p,True)
        tables=extract_note_tables(page,note,threshold)
        for table in tables:
            refine_cells(table,page,engine)
        note['tables'].extend(tables)
    # Propagate refined cell uncertainty up to rows/tables.
    for table in summaries+note['tables']:
        for row in table['rows']:
            row['confidence']=round(.6*row['confidence']+.4*mean(v['confidence'] for v in row['values'].values()),6)
            flag(row,threshold,'refined_cells_uncertain')
        table['confidence']=round(.5*table['confidence']+.5*mean(r['confidence'] for r in table['rows']),6)
        flag(table,threshold,'refined_rows_uncertain')
    write_json(out/'extracted_tables.json',dict(summary_tables=summaries,notes=[note]))
    LOG.info('[9-12/15] Candidates, embeddings, cross-encoder and confidence aggregation')
    matchers=Matchers(cfg)
    relationships,comparison=matchers.run(summaries,note,force)
    LOG.info('[13/15] Structural, format and financial validation')
    checks=validate(summaries,note,relationships,cfg)
    errors=error_analysis(summaries+note['tables'],checks,relationships)
    document.update(company=group_lines(summary_pages[0]['tokens'])[0]['text'] if summary_pages else None,reporting_period=sorted(set(p for t in summaries for p in t['periods'] if p)),currency=next((t['currency'] for t in summaries if t['currency']),None))
    processing=dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),duration_seconds=time.perf_counter()-start,python=platform.python_version(),platform=platform.platform(),packages={p:version(p) for p in ['PyMuPDF','tesserocr','sentence-transformers','torch','numpy','pydantic']},configuration=cfg,cache_root=str(engine.root),ocr_backends=sorted(set(p['backend'] for p in pages)),ocr_page_mean_confidence=mean(p['confidence'] for p in pages),rotated_pages=[p['page'] for p in pages if p.get('rotation')],ml=matchers.metadata,confidence_calibrated=False)
    processing['acceptance']=dict(embedding_inference=matchers.metadata['embedding_inference'],reranker_inference=matchers.metadata['reranker_inference'],source_rows_linked=len(relationships),summary_tables=len(summaries),note_tables=len(note['tables']),no_failed_checks=not any(c['status']=='failed' for c in checks),warnings_present=any(c['status']=='warning' for c in checks))
    result=Result(document=document,processing=processing,summary_tables=summaries,notes=[note],relationships=relationships,validation=checks,method_comparison=comparison,error_analysis=errors).model_dump()
    LOG.info('[14/15] Writing JSON artifacts')
    write_json(out/'result.json',result)
    write_json(out/'validation.json',dict(summary=summarize(checks),checks=checks))
    write_json(out/'comparison.json',comparison)
    write_json(out/'error_analysis.json',errors)
    write_json(out/'result.schema.json',Result.model_json_schema())
    LOG.info('[15/15] Comparison and error analysis complete: %s',summarize(checks))
    for relation in relationships:
        if relation['warnings']:
            LOG.warning('Relation %s: %s',relation['summary_row_id'],relation['warnings'])
    logging.getLogger().removeHandler(handler)
    handler.close()
    return result
