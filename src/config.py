from pathlib import Path
import yaml
from pydantic import BaseModel, Field, model_validator

class PageRange(BaseModel):
    start: int = Field(ge=1)
    end: int = Field(ge=1)

    @model_validator(mode='after')
    def ordered(self):
        if self.end < self.start:
            raise ValueError('Page range must be ascending (physical, one-based pages).')
        return self

def load_config(path: str, pdf: str | None = None, pages: str | None = None, note: int | None = None) -> dict:
    config_path = Path(path).resolve()
    cfg = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    base = config_path.parent
    if pages:
        parts = pages.split('-')
        cfg['summary_tables']['page_range'] = dict(start=int(parts[0]), end=int(parts[-1]))
    PageRange(**cfg['summary_tables']['page_range'])
    if note is not None:
        cfg['notes']['target_note'] = note
    if cfg['notes']['target_note'] < 1:
        raise ValueError('Note number must be positive.')
    candidate = Path(pdf) if pdf else base / cfg['document']['input_path']
    if not candidate.exists() and not pdf:
        candidates = sorted(base.glob('*.pdf')) + sorted((base / 'data/input').glob('*.pdf'))
        if len(candidates) == 1:
            candidate = candidates[0]
        elif len(candidates) > 1:
            raise ValueError('Multiple PDFs found; select one with --pdf.')
    if not candidate.is_file():
        raise FileNotFoundError('PDF not found; provide --pdf PATH.')
    cfg['document']['input_path'] = str(candidate.resolve())
    for key in ['cache_dir', 'output_dir']:
        cfg[key] = str((base / cfg[key]).resolve())
    cfg['ocr']['tessdata'] = str((base / cfg['ocr']['tessdata']).resolve())
    return cfg
