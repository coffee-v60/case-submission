import pytest
from src.normalization import parse_number
from src.schema import FinancialValue

def test_financial_numbers():
    for raw, expected in [('373.992.222',373992222),('(19.846.865)',-19846865),('1.234,50',1234.5)]:
        result=parse_number(raw)
        assert (result['state'],result['value'])==('numeric',expected)
    percent=parse_number('%10,5')
    assert (percent['value'],percent['unit'])==(10.5,'percent')

def test_distinct_states():
    for raw,state,value in [('-','dash',None),('','blank',None),('0','numeric',0)]:
        parsed=parse_number(raw)
        assert (parsed['state'],parsed['value'])==(state,value)
    with pytest.raises(ValueError):
        FinancialValue(raw='-',value=0,state='dash',confidence=.5)

def test_invalid_is_not_coerced():
    for raw in ['12.34','(123','%2-%4']:
        parsed=parse_number(raw)
        assert parsed['state']=='invalid'
        assert parsed['value'] is None
        assert parsed['warnings']
