from typing import Literal, Optional, Tuple

from pydantic import BaseModel, Field, field_validator, model_validator

DiscountType = Literal["percent", "fixed"]

DISCOUNT_TYPE_PERCENT: DiscountType = "percent"
DISCOUNT_TYPE_FIXED: DiscountType = "fixed"


class YearlyDiscountInput(BaseModel):
    discount_type: DiscountType = DISCOUNT_TYPE_PERCENT
    official_retail_price: float = Field(..., gt=0)
    discount_percent: Optional[float] = Field(None, gt=0, le=100)
    discount_amount: Optional[float] = Field(None, gt=0)

    @model_validator(mode="after")
    def validate_discount(self) -> "YearlyDiscountInput":
        if self.discount_type == DISCOUNT_TYPE_PERCENT:
            if self.discount_percent is None:
                raise ValueError("折數不可為空")
            return self
        if self.discount_amount is None:
            raise ValueError("固定扣款金額不可為空")
        if self.discount_amount >= self.official_retail_price:
            raise ValueError("扣減金額必須小於官方零售價")
        return self

    def to_db_values(self) -> Tuple[DiscountType, Optional[float], Optional[float]]:
        if self.discount_type == DISCOUNT_TYPE_FIXED:
            return self.discount_type, None, self.discount_amount
        ratio = self.discount_percent / 100  # type: ignore[operator]
        return self.discount_type, ratio, None


class ACRecordInput(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    cooling_capacity: float = Field(..., gt=0)
    official_retail_price: float = Field(..., gt=0)
    discount_type: DiscountType = DISCOUNT_TYPE_PERCENT
    discount_percent: Optional[float] = Field(None, gt=0, le=100)
    discount_amount: Optional[float] = Field(None, gt=0)
    cadr: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None

    @field_validator("year")
    @classmethod
    def validate_year(cls, value: int) -> int:
        if value < 2000 or value > 2100:
            raise ValueError("年份必須介於 2000 至 2100 之間")
        return value

    def discount_values(self) -> Tuple[DiscountType, Optional[float], Optional[float]]:
        discount = YearlyDiscountInput(
            discount_type=self.discount_type,
            official_retail_price=self.official_retail_price,
            discount_percent=self.discount_percent,
            discount_amount=self.discount_amount,
        )
        return discount.to_db_values()

    def calc_discount_price(self) -> float:
        discount_type, ratio, amount = self.discount_values()
        if discount_type == DISCOUNT_TYPE_FIXED:
            return self.official_retail_price - amount  # type: ignore[operator]
        return self.official_retail_price * ratio  # type: ignore[operator]


def calc_discount_price(
    official_retail_price: float,
    discount_type: str,
    discount_ratio: Optional[float],
    discount_amount: Optional[float],
) -> float:
    percent = discount_ratio * 100 if discount_ratio is not None else None
    data = ACRecordInput(
        year=2000,
        cooling_capacity=1.0,
        official_retail_price=official_retail_price,
        discount_type=discount_type,  # type: ignore[arg-type]
        discount_percent=percent,
        discount_amount=discount_amount,
    )
    return data.calc_discount_price()


def format_discount_label(
    discount_type: str,
    discount_ratio: Optional[float],
    discount_amount: Optional[float],
) -> str:
    if discount_type == DISCOUNT_TYPE_FIXED:
        amount = discount_amount or 0
        return f"扣 {amount:,.0f} 元"
    ratio = discount_ratio or 0
    return f"{round(ratio * 100)} 折"
