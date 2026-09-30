import re
import unicodedata
from src.schema import FinancialValue

def normalize_text(text: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', text).split())

def fold(text: str) -> str:
    text = text.replace('İ', 'i').replace('ı', 'i').lower()
    return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c)).replace('ş', 's')

def parse_number(raw: str, ocr_confidence: float = 1.0, alignment: float = 1.0, bbox=None, threshold: float = .6) -> dict:
    s = raw.strip().replace('\u00a0', '')
    unit = 'percent' if s.startswith('%') or s.endswith('%') else None
    if unit:
        s = s.strip('%')
    state, value = 'invalid', None
    if not s:
        state = 'blank'
    elif s in {'-', '–', '—', '−'}:
        state = 'dash'
    else:
        negative = s.startswith('(') and s.endswith(')')
        number = s[1:-1] if negative else s
        if re.fullmatch(r'-?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?', number):
            converted = number.replace('.', '').replace(',', '.')
            value = float(converted) if '.' in converted else int(converted)
            value = -value if negative else value
            state = 'numeric'
    validity = float(state != 'invalid')
    confidence = min(1., max(0., .55 * ocr_confidence + .25 * validity + .20 * alignment))
    if state == 'invalid':
        confidence *= .35
    if state == 'blank':
        confidence *= .7  # absence is less certain than a recognized glyph
    warnings = ['unrecognized_numeric_format'] if state == 'invalid' else []
    if confidence < threshold:
        warnings.append('cell_evidence_below_threshold')
    return FinancialValue(raw=raw, value=value, state=state, confidence=round(confidence, 6), bbox=bbox, low_confidence=confidence < threshold, warnings=warnings, unit=unit).model_dump()

def extract_years(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r'\b(?:19|20)\d{2}\b', text)))
