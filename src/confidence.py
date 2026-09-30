import math

def mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0

def score(features: dict[str, float], weights: dict[str, float]) -> float:
    return round(max(0., min(1., sum(max(0., min(1., features.get(k, 0.))) * w for k, w in weights.items()) / sum(weights.values()))), 6)

def sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-max(-40., min(40., value))))

def flag(record: dict, threshold: float, reason: str) -> dict:
    record['low_confidence'] = record['confidence'] < threshold
    record.setdefault('warnings', [])
    if record['low_confidence']:
        record['warnings'].append(reason)
    return record
