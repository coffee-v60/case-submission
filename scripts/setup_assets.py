from pathlib import Path
import argparse
import os
import urllib.request

import yaml


def main() -> int:
    parser = argparse.ArgumentParser(description='Download OCR languages and matching models.')
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--ocr', action='store_true', help='Download OCR languages only')
    parser.add_argument('--models', action='store_true', help='Download matching models only')
    args = parser.parse_args()
    path = Path(args.config).resolve()
    cfg = yaml.safe_load(path.read_text(encoding='utf8'))
    both = not (args.ocr or args.models)
    if args.ocr or both:
        from tesserocr import PyTessBaseAPI, tesseract_version
        target = path.parent / cfg['ocr']['tessdata']
        target.mkdir(parents=True, exist_ok=True)
        for language in cfg['ocr']['languages']:
            if not language.replace('_', '').isalnum():
                parser.error(f'Invalid OCR language: {language}')
            destination = target / f'{language}.traineddata'
            if not destination.is_file():
                temporary = destination.with_suffix('.part')
                try:
                    urllib.request.urlretrieve(
                        f'https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/{language}.traineddata',
                        temporary,
                    )
                    temporary.replace(destination)
                finally:
                    temporary.unlink(missing_ok=True)
        with PyTessBaseAPI(path=str(target), lang='+'.join(cfg['ocr']['languages'])):
            print(f'OCR ready: {tesseract_version().splitlines()[0]} ({target})', flush=True)
    if args.models or both:
        os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
        from huggingface_hub import snapshot_download
        for key in ['embedding_model', 'reranker_model']:
            name = cfg['matching'][key]
            folder = path.parent / cfg['cache_dir'] / 'models' / name.replace('/', '--')
            downloaded = snapshot_download(name, local_dir=folder, allow_patterns=['*.json', '*.txt', '*.model', '*.safetensors'], ignore_patterns=['onnx/*', 'openvino/*'])
            print(f'Model ready: {downloaded}', flush=True)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
