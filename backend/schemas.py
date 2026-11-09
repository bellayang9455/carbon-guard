from pydantic import BaseModel, Field, field_validator, ConfigDict

class Login(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)

class Record(BaseModel):
    model_config = ConfigDict(extra='forbid')
    supplier: str = Field(min_length=1, max_length=100)
    month: str = Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    scope: int = Field(ge=1, le=3, strict=True)
    emission: float = Field(ge=0, le=1e12, allow_inf_nan=False)
    production: float = Field(ge=0.001, le=1e12, allow_inf_nan=False)
    @field_validator('supplier')
    @classmethod
    def trim(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('供應商不可空白')
        return value

class Batch(BaseModel):
    records: list[Record] = Field(min_length=1, max_length=1000)

class Train(BaseModel):
    samples: list[Record] = Field(min_length=32, max_length=10000)
    contamination: float = Field(default=.05, gt=0, le=.5, allow_inf_nan=False)
    note: str = Field(min_length=1, max_length=500)

class Review(BaseModel):
    decision: str = Field(pattern=r'^(confirmed|rejected|pending)$')
    note: str = Field(min_length=1, max_length=500)
