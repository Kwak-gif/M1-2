from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_allowed_origins
from routers import chat_router, conv_router, data_router

app = FastAPI(
    title="StockPulse AI — 나만의 주식 분석 AI 비서 API",
    description=(
        "삼성전자(005930)·두산(000150) 1년치 실제 과거 종가 시계열 데이터를 기반으로 "
        "① 주가 변곡점·시장 이슈 분석, ② 분할 매수·가격 위치 리스크 관리, ③ 장 마감 데일리 시황 브리핑을 "
        "수행하는 FastAPI + Firestore + OpenAI GPT 기반 AI 비서 백엔드입니다. "
        "(/openapi.json 스키마로 GPT Actions 연동도 지원합니다.)"
    ),
    version="1.0.0",
)

allowed_origins = get_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data_router.router)
app.include_router(conv_router.router)
app.include_router(chat_router.router)


@app.get("/", tags=["Health"], summary="서버 상태 확인 (헬스체크)")
def health_check():
    return {
        "status": "ok",
        "service": "StockPulse AI Backend",
        "docs_url": "/docs",
        "openapi_url": "/openapi.json",
    }
