from datetime import datetime
from pydantic import BaseModel, Field, model_validator

from app.services.oven_engine import NIGHT_EARLIEST


class ProductOut(BaseModel):
    id: int
    name: str
    ferment_min: int
    bake_min: int
    model_config = {"from_attributes": True}


class OvenOut(BaseModel):
    id: int
    label: str
    capacity_note: str
    model_config = {"from_attributes": True}


class BatchOut(BaseModel):
    id: int
    product_id: int
    oven_id: int
    code: str
    start_min: int
    start_day_offset: int = 0
    status: str
    product_name: str | None = None
    oven_label: str | None = None
    ferment_end: int | None = None
    bake_end: int | None = None
    night_start: bool = False
    model_config = {"from_attributes": True}


class BatchCreate(BaseModel):
    product_id: int
    oven_id: int
    # Signed minutes from today's 00:00; negative starts ferment the previous night.
    start_min: int = Field(ge=NIGHT_EARLIEST, le=24 * 60 - 1)
    # Explicit previous-day marker: -1 = work started the previous night, 0 = today.
    start_day_offset: int = Field(default=0, ge=-1, le=0)
    code: str | None = None

    @model_validator(mode="after")
    def _check_night_marker(self) -> "BatchCreate":
        if self.start_day_offset == -1 and self.start_min >= 0:
            raise ValueError("前一日夜间开工必须用负的开工分钟（相对当日 0 点）")
        if self.start_day_offset == 0 and self.start_min < 0:
            raise ValueError("负的开工分钟需要标记为前一日夜间开工")
        return self


class GanttBlock(BaseModel):
    batch_id: int
    code: str
    oven_id: int
    oven_label: str
    phase: str
    start_min: int
    end_min: int
    night_start: bool = False


class ConflictOut(BaseModel):
    id: int
    batch_code: str
    oven_id: int
    detail: str
    created_at: datetime
    model_config = {"from_attributes": True}


class WindowOut(BaseModel):
    oven_id: int
    oven_label: str
    start_min: int
    end_min: int
    duration_min: int
