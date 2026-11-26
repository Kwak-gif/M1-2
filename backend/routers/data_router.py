from typing import Optional
from fastapi import APIRouter, Query

from schemas.data_schema import DataCreate, DataUpdate
from services import data_service

router = APIRouter(prefix="/api", tags=["Stock Data & Analytics"])


@router.get("/stocks", summary="등록된 주식 종목 목록 조회")
def list_stocks():
    """선택 가능한 주식 종목(삼성전자 005930, 두산 000150 등)과 저장 건수를 반환합니다."""
    return {"stocks": data_service.list_stocks()}


# 주의: /data/summary 및 /data/statistics 는 반드시 /data/{item_id} 보다 먼저 선언!
@router.get("/data/summary", summary="종목 시계열 데이터 요약 조회 (프롬프트 주입용)")
def get_data_summary(
    symbol: Optional[str] = Query(
        default=None,
        description="종목코드 (예: 005930 삼성전자, 000150 두산). 미입력 시 기본 종목 조회",
    )
):
    return data_service.get_summary(symbol)


@router.get("/data/statistics", summary="[보너스] 종목 심화 통계 및 차트 시계열 조회")
def get_data_statistics(
    symbol: Optional[str] = Query(
        default=None,
        description="종목코드 (예: 005930, 000150). 미입력 시 기본 종목 조회",
    )
):
    return data_service.get_statistics(symbol)


@router.post("/data", status_code=201, summary="새 주가 데이터(종가·메모) 추가")
def create_data(payload: DataCreate):
    return data_service.create_data(payload)


@router.get("/data", summary="종목 시계열 데이터 목록 조회")
def list_data(
    symbol: Optional[str] = Query(
        default=None,
        description="종목코드 (예: 005930, 000150, 전체 조회는 ALL). 미입력 시 기본 종목 조회",
    )
):
    items = data_service.list_data(symbol)
    return {"count": len(items), "items": items}


@router.put("/data/{item_id}", summary="기존 주가 데이터 수정")
def update_data(item_id: str, payload: DataUpdate):
    return data_service.update_data(item_id, payload)


@router.delete("/data/{item_id}", summary="주가 데이터 삭제")
def delete_data(item_id: str):
    return data_service.delete_data(item_id)
