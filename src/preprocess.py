from pathlib import Path
import cv2
import numpy as np

def preprocess(path: Path, force: bool = False) -> tuple[Path, dict]:
    dest = path.with_name(path.name.replace('original', 'preprocessed'))
    gray = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError(f'Cannot read {path}')
    # Long horizontal strokes estimate skew without eroding punctuation.
    edges = cv2.Canny(gray, 80, 180)
    lines = cv2.HoughLinesP(edges, 1, np.pi/1800, 100, minLineLength=gray.shape[1]//8, maxLineGap=15)
    angles = [] if lines is None else [np.degrees(np.arctan2(y2-y1, x2-x1)) for x1,y1,x2,y2 in lines.reshape(-1,4) if x2 != x1 and abs(np.degrees(np.arctan2(y2-y1,x2-x1))) < 4]
    angle = float(np.median(angles)) if angles else 0.
    if force or not dest.exists():
        smooth = cv2.GaussianBlur(gray, (3,3), .35)
        if .1 < abs(angle) < 3:
            h,w = smooth.shape
            smooth = cv2.warpAffine(smooth, cv2.getRotationMatrix2D((w/2,h/2), angle, 1), (w,h), borderValue=255)
        _, binary = cv2.threshold(smooth, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        cv2.imencode('.png', binary)[1].tofile(dest)
    return dest, dict(deskew_degrees=angle, method='grayscale, mild Gaussian, guarded Hough deskew, Otsu')
