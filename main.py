"""CLI entry point. All page numbers are physical and one-based."""
import argparse
import logging
import sys
from src.config import load_config
from src.pipeline import run

def main() -> int:
    parser=argparse.ArgumentParser(description='Extract financial tables and link note rows using multilingual ML.')
    parser.add_argument('--config',default='config.yaml')
    parser.add_argument('--pdf')
    parser.add_argument('--pages',help='Physical pages, e.g. 5-7')
    parser.add_argument('--note',type=int)
    parser.add_argument('--force',action='store_true',help='Recompute render/OCR/model caches')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',handlers=[logging.StreamHandler(sys.stdout)])
    try:
        cfg=load_config(args.config,args.pdf,args.pages,args.note)
        run(cfg,args.force)
    except (FileNotFoundError,ValueError,RuntimeError) as exc:
        logging.error('%s',exc)
        return 1
    return 0

if __name__=='__main__':
    raise SystemExit(main())
