from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class AnalysisRequest(BaseModel):
    query: str = Field(min_length=2, max_length=120)

    @field_validator("query")
    @classmethod
    def clean_query(cls, value: str) -> str:
        return " ".join(value.split())


class JobSuggestion(BaseModel):
    label: str
    code: str


class SkillResult(BaseModel):
    name: str
    offer_count: int
    percentage: float


class EducationResult(BaseModel):
    level: str
    offer_count: int
    percentage: float


class AnalysisResponse(BaseModel):
    query: str
    generated_at: datetime
    cached: bool = False
    total_offers: int
    usable_offers: int
    coverage_percentage: float
    skills: list[SkillResult]
    education_levels: list[EducationResult]
