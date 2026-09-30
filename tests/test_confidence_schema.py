import json
from src.confidence import score
from src.schema import Result

def test_evidence_changes_confidence():
    assert score(dict(a=.9),dict(a=1))>score(dict(a=.1),dict(a=1))
    assert 0<=score(dict(a=-3,b=2),dict(a=.4,b=.6))<=1

def test_json_round_trip():
    result=Result(document={},processing={},summary_tables=[],notes=[],relationships=[],validation=[],method_comparison={},error_analysis=[])
    assert Result.model_validate_json(result.model_dump_json())==result
    json.dumps(Result.model_json_schema())
