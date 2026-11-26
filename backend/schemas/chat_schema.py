from typing import Literal, Optional
from pydantic import BaseModel, Field

from core.config import DEFAULT_STOCK_SYMBOL


class MessageItem(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(..., min_length=1, max_length=8000)
    timestamp: Optional[str] = None


class ConversationCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=150, description="대화 제목")
    symbol: str = Field(default=DEFAULT_STOCK_SYMBOL, description="관련 종목코드")
    stock_name: Optional[str] = Field(default=None, description="관련 종목명")
    messages: list[MessageItem] = Field(default_factory=list, description="대화 메시지 목록")


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="사용자 자연어 질문",
        examples=["현재 종가가 1년 평균가 대비 어느 위치이고, 최근 급등락 이슈가 무엇이었는지 알려줘."],
    )
    symbol: str = Field(
        default=DEFAULT_STOCK_SYMBOL,
        description="분석 대상 종목코드 (005930: 삼성전자, 000150: 두산)",
        examples=["005930"],
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="이어서 대화할 기존 대화 ID (신규 대화 시 생략 또는 null)",
    )
    use_tools: bool = Field(
        default=True,
        description="보너스 기능: OpenAI Function Calling 도구 호출 활성화 여부",
    )
