from typing import Optional
from pydantic import BaseModel, Field


class ACModelBase(BaseModel):
    brand: str = Field(..., description="冷氣品牌", example="日立")
    model_number: str = Field(..., description="冷氣型號", example="RAC-28YB")
    cooling_capacity: float = Field(
        ..., gt=0, description="冷房能力 (kW)", example=2.8
    )
    notes: Optional[str] = Field(
        None, description="備註事項", example="適用 4-5 坪"
    )


class ACModelCreate(ACModelBase):
    pass


class ACModelResponse(ACModelBase):
    id: int

    class Config:
        from_attributes = True