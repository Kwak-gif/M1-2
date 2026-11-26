from typing import Optional
from fastapi import APIRouter, Query

from schemas.chat_schema import ConversationCreate
from services import conv_service

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])


@router.post("", status_code=201, summary="대화 기록 수동 저장")
def create_conversation(payload: ConversationCreate):
    return conv_service.create_conversation(payload)


@router.get("", summary="대화 목록 조회 (최신순)")
def list_conversations(
    symbol: Optional[str] = Query(
        default=None,
        description="특정 종목 대화만 조회 시 종목코드 입력 (미입력 시 전체 조회)",
    ),
    limit: int = Query(default=50, ge=1, le=100),
):
    items = conv_service.list_conversations(symbol=symbol, limit=limit)
    return {"count": len(items), "items": items}


@router.get("/{conv_id}", summary="특정 대화의 전체 메시지 불러오기 (UX A안)")
def get_conversation(conv_id: str):
    return conv_service.get_conversation(conv_id)


@router.delete("/{conv_id}", summary="특정 대화 삭제")
def delete_conversation(conv_id: str):
    return conv_service.delete_conversation(conv_id)
