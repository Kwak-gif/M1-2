from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator

from core.config import DEFAULT_STOCK_SYMBOL, resolve_stock_name


def _validate_iso_date(v: str) -> str:
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("date는 YYYY-MM-DD 형식의 유효한 날짜여야 합니다. (예: 2026-11-25)") from exc
    return v


class DataCreate(BaseModel):
    date: str = Field(..., description="거래일자 (YYYY-MM-DD)", examples=["2026-11-26"])
    value: float = Field(..., gt=0, description="종가 (0보다 큰 숫자, 단위: 원)", examples=[172000])
    memo: str = Field(
        default="",
        max_length=300,
        description="이슈/리스크/시황 메모",
        examples=["[시황] 외인 순매수 전환, 반도체 동반 강세"],
    )
    symbol: str = Field(
        default=DEFAULT_STOCK_SYMBOL,
        min_length=1,
        max_length=20,
        description="종목코드 (미입력 시 기본 종목 005930 적용)",
        examples=["005930"],
    )
    stock_name: Optional[str] = Field(
        default=None,
        max_length=50,
        description="종목명 (미입력 시 종목코드 기준 자동 매핑)",
        examples=["삼성전자"],
    )

    @field_validator("date")
    @classmethod
    def check_date(cls, v: str) -> str:
        return _validate_iso_date(v.strip())

    @field_validator("symbol")
    @classmethod
    def check_symbol(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not cleaned:
            return DEFAULT_STOCK_SYMBOL
        return cleaned

    def resolved_stock_name(self) -> str:
        return resolve_stock_name(self.symbol, self.stock_name)


class DataUpdate(BaseModel):
    date: Optional[str] = Field(default=None, description="수정할 거래일자 (YYYY-MM-DD)")
    value: Optional[float] = Field(default=None, gt=0, description="수정할 종가 (0보다 큰 숫자)")
    memo: Optional[str] = Field(default=None, max_length=300, description="수정할 메모")
    symbol: Optional[str] = Field(default=None, min_length=1, max_length=20, description="수정할 종목코드")
    stock_name: Optional[str] = Field(default=None, max_length=50, description="수정할 종목명")

    @field_validator("date")
    @classmethod
    def check_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return _validate_iso_date(v.strip())

    @field_validator("symbol")
    @classmethod
    def check_symbol(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v.strip().upper()


class DataResponse(BaseModel):
    id: str
    symbol: str
    stock_name: str
    date: str
    value: float
    memo: str
    created_at: str
    updated_at: str
