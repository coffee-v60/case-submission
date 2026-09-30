from typing import Literal, Any
from pydantic import BaseModel, Field, model_validator, ConfigDict

class AuditModel(BaseModel):
    model_config = ConfigDict(extra='allow')

class FinancialValue(AuditModel):
    raw: str
    value: int | float | None = None
    state: Literal['numeric', 'dash', 'blank', 'invalid']
    confidence: float = Field(ge=0, le=1)
    bbox: list[float] | None = None
    low_confidence: bool = False
    warnings: list[str] = Field(default_factory=list)
    unit: Literal['percent'] | None = None

    @model_validator(mode='after')
    def consistent(self):
        if (self.state == 'numeric') != (self.value is not None):
            raise ValueError('Only numeric cells may carry a value.')
        return self

class Hierarchy(AuditModel):
    level: int = Field(ge=0)
    parent_id: str | None

class Row(AuditModel):
    id: str
    raw_label: str
    normalized_label: str
    note_reference: list[int]
    hierarchy: Hierarchy
    row_type: Literal['section','line_item','subtotal','total','grand_total']
    values: dict[str,FinancialValue]
    confidence: float = Field(ge=0,le=1)
    low_confidence: bool
    warnings: list[str]
    component_ids: list[str] = Field(default_factory=list)
    aggregation_rule: str | None = None
    financial_role: str | None = None
    reconciles_to: str | None = None
    distribution_of: str | None = None

class Column(AuditModel):
    id: str
    title: str
    period: str | None

class Table(AuditModel):
    id: str
    title: str
    page: int = Field(ge=1)
    columns: list[Column]
    periods: list[str | None]
    confidence: float = Field(ge=0,le=1)
    low_confidence: bool
    rows: list[Row]

class Note(AuditModel):
    number: int = Field(ge=1)
    title: str
    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)
    detection_confidence: float = Field(ge=0,le=1)
    tables: list[Table]

class Relationship(AuditModel):
    summary_row_id: str
    note_number: int
    note_table_id: str
    note_row_ids: list[str]
    relation_type: Literal['closing_balance','opening_balance','movement','valuation_gain','component','total','other']
    confidence: float = Field(ge=0,le=1)
    low_confidence: bool
    warnings: list[str]

class ValidationCheck(AuditModel):
    rule: str
    status: Literal['passed','failed','warning']
    expected: Any
    observed: Any
    difference: float | int | None
    confidence: float = Field(ge=0,le=1)

class Result(BaseModel):
    document: dict[str, Any]
    processing: dict[str, Any]
    summary_tables: list[Table]
    notes: list[Note]
    relationships: list[Relationship]
    validation: list[ValidationCheck]
    method_comparison: dict
    error_analysis: list[dict]
