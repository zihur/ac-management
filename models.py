from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

DiscountType = Literal["percent", "fixed"]


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


class ACModelYearlyBase(BaseModel):
    year: int = Field(..., ge=2000, le=2100, description="年份", example=2026)
    official_retail_price: float = Field(..., gt=0, description="官方零售價（元）", example=30000)
    discount_type: DiscountType = Field(default="percent", description="優惠方式")
    discount_percent: Optional[float] = Field(
        None, gt=0, le=100, description="折數（85 表示 85 折）", example=85
    )
    discount_amount: Optional[float] = Field(
        None, gt=0, description="固定扣款金額（元）", example=3000
    )
    cadr: Optional[float] = Field(None, ge=0, description="CADR (m³/h)", example=350)
    notes: Optional[str] = Field(None, description="該年度備註")

    @field_validator("year")
    @classmethod
    def validate_year(cls, value: int) -> int:
        if value < 2000 or value > 2100:
            raise ValueError("年份必須介於 2000 至 2100 之間")
        return value

    @model_validator(mode="after")
    def validate_discount(self) -> "ACModelYearlyBase":
        if self.discount_type == "percent":
            if self.discount_percent is None:
                raise ValueError("折數不可為空")
        elif self.discount_amount is None:
            raise ValueError("固定扣款金額不可為空")
        elif self.discount_amount >= self.official_retail_price:
            raise ValueError("扣減金額必須小於官方零售價")
        return self


class ACModelYearlyCreate(ACModelYearlyBase):
    ac_model_id: int


class ACModelYearlyResponse(ACModelYearlyBase):
    id: int
    ac_model_id: int
    discount_ratio: Optional[float] = None

    @property
    def discount_price(self) -> float:
        if self.discount_type == "fixed":
            assert self.discount_amount is not None
            return self.official_retail_price - self.discount_amount
        assert self.discount_ratio is not None
        return self.official_retail_price * self.discount_ratio

    class Config:
        from_attributes = True
