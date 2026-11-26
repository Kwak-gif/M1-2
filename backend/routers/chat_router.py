from fastapi import APIRouter

from schemas.chat_schema import ChatRequest
from services import chat_service

router = APIRouter(prefix="/api", tags=["AI Chat"])


@router.post("/chat", summary="종목 컨텍스트 주입 + Function Calling AI 채팅")
def chat_with_assistant(payload: ChatRequest):
    return chat_service.process_chat(payload)
