"""Page-local native extraction / Tesseract OCR with content-addressed caches."""
from pathlib import Path
import json
import logging
import hashlib
import pymupdf
from tesserocr import PyTessBaseAPI, RIL, iterate_level, tesseract_version
from PIL import Image
from src.pdf import render_page
from src.preprocess import preprocess
from src.confidence import mean

LOG = logging.getLogger(__name__)

class OCREngine:
    def __init__(self, config: dict, inspection: dict, force: bool = False):
        self.cfg, self.inspection, self.force = config, inspection, force
        self.pdf = config['document']['input_path']
        settings = json.dumps(dict(rendering=config['rendering'], ocr=config['ocr'], backend=tesseract_version(), version=4), sort_keys=True)
        self.root = Path(config['cache_dir']) / inspection['sha256'][:16] / hashlib.sha256(settings.encode()).hexdigest()[:12]
        self.folder = self.root / 'ocr'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.languages = '+'.join(config['ocr']['languages'])
        needs_ocr = any(not p['native_usable'] for p in inspection['pages'])
        self.tessdata = str(Path(config['ocr']['tessdata']).resolve())
        if needs_ocr:
            missing = [lang for lang in config['ocr']['languages'] if not (Path(self.tessdata) / f'{lang}.traineddata').is_file()]
            if missing:
                raise RuntimeError(f'Missing OCR languages: {missing}; run python scripts/setup_assets.py --ocr --config PATH_TO_CONFIG')

    def read_image(self, image: Image.Image, page: int, psm: int = 6, whitelist: str = '') -> list[dict]:
        tokens = []
        with PyTessBaseAPI(path=self.tessdata, lang=self.languages, psm=psm) as api:
            if whitelist:
                api.SetVariable('tessedit_char_whitelist', whitelist)
            api.SetImage(image)
            api.Recognize()
            iterator = api.GetIterator()
            if iterator is None:
                return tokens
            for word in iterate_level(iterator, RIL.WORD):
                if word.Empty(RIL.WORD):
                    continue
                text = word.GetUTF8Text(RIL.WORD)
                box = word.BoundingBox(RIL.WORD)
                if text and text.strip() and box:
                    tokens.append(dict(text=text.strip(), bbox=list(box), confidence=max(0., min(1., word.Confidence(RIL.WORD)/100)), page=page))
        return tokens

    def _tesseract(self, image: Path, page: int) -> list[dict]:
        with Image.open(image) as source:
            return self.read_image(source, page)

    def page(self, page: int, detailed: bool = False) -> dict:
        dpi = self.cfg['rendering']['dpi' if detailed else 'scan_dpi']
        cache = self.folder / f'p{page:03d}-{dpi}.json'
        if cache.exists() and not self.force:
            cached = json.loads(cache.read_text(encoding='utf-8'))
            if cached['confidence'] >= .65 or 'rotation_checked' in cached:
                rotation = cached.get('rotation', 0)
                name = f'p{page:03d}-{dpi}-original' + (f'-rot{rotation}' if rotation else '') + '.png'
                cached['image'] = str(self.root / 'pages' / name)
                if not Path(cached['image']).is_file():
                    source = render_page(self.pdf, page, dpi, self.root/'pages')
                    if rotation:
                        with Image.open(source) as original:
                            original.rotate(rotation, expand=True).save(cached['image'])
                return cached
        source = render_page(self.pdf, page, dpi, self.root/'pages', self.force)
        width, height = Image.open(source).size
        native = self.inspection['pages'][page-1]['native_usable']
        alternatives, preprocessing = [], {}
        rotation = 0
        if native:
            with pymupdf.open(self.pdf) as doc:
                tokens = [dict(text=w[4], bbox=[float(v*dpi/72) for v in w[:4]], confidence=1., page=page) for w in doc[page-1].get_text('words')]
            backend, selected = 'native', 'native'
        else:
            tokens = self._tesseract(source, page)
            backend, selected = 'tesserocr', 'original'
            if mean(t['confidence'] for t in tokens) < .65:
                for degrees in [90,270]:
                    rotated = source.with_name(source.stem+f'-rot{degrees}.png')
                    Image.open(source).rotate(degrees,expand=True).save(rotated)
                    trial = self._tesseract(rotated,page)
                    if mean(t['confidence'] for t in trial) > mean(t['confidence'] for t in tokens):
                        tokens, rotation = trial, degrees
                if rotation:
                    source = source.with_name(source.stem+f'-rot{rotation}.png')
                    width,height = Image.open(source).size
            if detailed or mean(t['confidence'] for t in tokens) < self.cfg['ocr']['fallback_threshold']:
                processed, preprocessing = preprocess(source, self.force)
                other = self._tesseract(processed, page)
                maximum = max(len(tokens), len(other), 1)
                quality = lambda ts: .8*mean(t['confidence'] for t in ts) + .2*len(ts)/maximum
                alternatives = [dict(variant='original', score=quality(tokens), tokens=tokens), dict(variant='preprocessed', score=quality(other), tokens=other)]
                if quality(other) > quality(tokens):
                    tokens, selected = other, 'preprocessed'
        result = dict(page=page, dpi=dpi, width=width, height=height, backend=backend, selected=selected, tokens=tokens, alternatives=alternatives, preprocessing=preprocessing, confidence=mean(t['confidence'] for t in tokens), image=str(source), rotation_checked=True, rotation=rotation)
        cache.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        LOG.info('OCR page %s (%s, %s tokens, confidence %.3f)', page, selected, len(tokens), result['confidence'])
        return result

