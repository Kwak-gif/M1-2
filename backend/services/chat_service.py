import json
from typing import Any, Optional

from fastapi import HTTPException
from openai import OpenAI

from core.config import (
    DEFAULT_STOCK_SYMBOL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MAX_TOKENS,
    OPENAI_MODEL,
)
from schemas.chat_schema import ChatRequest
from services import conv_service, data_service

_openai_client: Any = None


def set_openai_client(client: Any) -> None:
    """테스트 환경에서 모의(Mock) OpenAI 클라이언트를 주입하기 위한 헬퍼."""
    global _openai_client
    _openai_client = client


def get_openai_client() -> Any:
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY 환경변수가 설정되지 않았습니다. backend/.env 파일을 확인하세요.",
        )
    client_kwargs: dict[str, Any] = {"api_key": OPENAI_API_KEY, "timeout": 30.0}
    if OPENAI_BASE_URL:
        client_kwargs["base_url"] = OPENAI_BASE_URL
    _openai_client = OpenAI(**client_kwargs)
    return _openai_client


# 보너스 과제: OpenAI Function Calling 도구 스키마 4종
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_summary",
            "description": "선택한 주식 종목(005930 삼성전자, 000150 두산 등)의 1년 기간, 평균가, 최고/최저가, 평균가 대비 위치(%), 추세, 주요 변곡점 및 최근 5거래일 요약을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "종목코드 (예: '005930' 삼성전자, '000150' 두산)",
                    }
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_statistics",
            "description": "이동평균선(MA5/MA20/MA60/MA120), 기간별 수익률(5일/20일/60일/1년), 일일 변동성(%), 최대낙폭(MDD), 월별 평균가 등 심화 리스크/기술적 통계를 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "종목코드 (예: '005930', '000150')",
                    }
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_inflection_points",
            "description": "종목의 전일 대비 급등락 변곡점 날짜, 종가, 등락률 및 [이슈]/[리스크] 메모를 상세 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "종목코드 (예: '005930', '000150')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "조회할 변곡점 개수 (기본 5, 최대 10)",
                        "default": 5,
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent_conversations",
            "description": "사용자가 이전에 나눈 주식 상담/브리핑 대화 목록을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "종목코드 또는 전체 조회 시 'ALL'",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "조회할 최근 대화 개수 (기본 5)",
                        "default": 5,
                    },
                },
                "required": [],
            },
        },
    },
]


def execute_tool(tool_name: str, arguments: dict[str, Any], default_symbol: str) -> dict[str, Any]:
    """Function Calling 및 MCP Server에서 공용으로 호출하는 내부 도구 실행기."""
    sym = (arguments.get("symbol") or default_symbol or DEFAULT_STOCK_SYMBOL).strip().upper()

    if tool_name == "get_stock_summary":
        return data_service.get_summary(sym)
    if tool_name == "get_stock_statistics":
        stats = data_service.get_statistics(sym)
        # LLM 토큰 절약을 위해 차트용 일별 전체 series 배열은 제외하고 핵심 통계만 반환
        return {k: v for k, v in stats.items() if k != "series"}
    if tool_name == "get_inflection_points":
        limit = int(arguments.get("limit", 5))
        return {
            "symbol": sym,
            "inflection_points": data_service.get_inflection_points(sym, limit=limit),
        }
    if tool_name == "list_recent_conversations":
        limit = int(arguments.get("limit", 5))
        convs = conv_service.list_conversations(symbol=arguments.get("symbol"), limit=limit)
        return {"conversations": convs}

    return {"error": f"알 수 없는 도구입니다: {tool_name}"}


def build_system_prompt(summary: dict[str, Any], use_tools: bool) -> str:
    """P-14 시스템 프롬프트: 선택 종목 요약 컨텍스트를 동적으로 주입합니다."""
    tool_guidance = (
        "\n[도구 호출(Function Calling) 지침]\n"
        "- 이동평균선(MA20/60/120), 변동성, 최대낙폭(MDD), 월별 평균가나 다른 종목 비교가 필요하면 `get_stock_statistics` 또는 `get_stock_summary` 도구를 호출하세요.\n"
        "- 급등락 변곡점 상세 분석이 필요하면 `get_inflection_points`를, 이전 상담 이력을 물으면 `list_recent_conversations`를 호출하세요.\n"
        if use_tools
        else ""
    )

    return (
        "당신은 사용자가 선택한 주식 종목의 1년치 실제 시계열 종가 데이터와 메모를 분석하는 '나만의 주식 분석 AI 비서'입니다.\n"
        "아래 3가지 역할 중 사용자의 질문 의도에 맞는 관점으로(복합 질문이면 통합하여) 답변하세요.\n\n"
        "[역할 1: 주가 변곡점 & 시장 이슈 분석 애널리스트]\n"
        "- 급등락일의 날짜, 종가, 등락률과 [이슈] 메모를 연결해 변동 흐름과 핵심 포인트를 리포트형으로 설명합니다.\n\n"
        "[역할 2: 분할 매수 & 가격 위치 리스크 관리 비서]\n"
        "- 최근 종가, 1년 평균가, 최고가/최저가, 평균가 대비 괴리율(%), 가격 위치(%)와 [리스크] 메모를 근거로 현재 가격대 리스크를 객관적으로 정리합니다.\n\n"
        "[역할 3: 장 마감 데일리 시황 브리핑 비서]\n"
        "- 최근 5거래일 종가 흐름, 추세(trend), [시황] 메모를 종합해 간결한 장 마감 브리핑을 제공합니다.\n\n"
        "[선택 종목 데이터 컨텍스트]\n"
        f"- 종목: {summary['stock_name']} ({summary['symbol']})\n"
        f"- 분석 기간: {summary['period']} (총 {summary['count']}거래일)\n"
        f"- 핵심 가격 통계: {json.dumps(summary['metrics'], ensure_ascii=False)}\n"
        f"- 최근 추세: {summary['trend']}\n"
        f"- 주요 급등락 변곡점 및 이슈 메모: {json.dumps(summary['key_events'], ensure_ascii=False)}\n"
        f"- 최근 거래일 종가 및 시황 메모: {json.dumps(summary['recent_records'], ensure_ascii=False)}\n"
        f"{tool_guidance}\n"
        "[엄격한 답변 원칙]\n"
        "1. 반드시 위 컨텍스트와 도구 조회 결과에 포함된 실제 수치와 메모만 근거로 답변하세요.\n"
        "2. 저장되지 않은 실시간 호가, 미확인 뉴스, 추측 수치는 절대 지어내지 말고 '저장된 데이터에서 확인되지 않습니다'라고 안내하세요.\n"
        "3. 특정 매수/매도를 단정 지시하지 말고, 통계적 가격 위치와 사용자가 기록한 기준 메모 중심으로 설명하세요.\n"
        "4. [핵심 요약] → [근거 수치/메모] → [체크 포인트] 순으로 깔끔한 한국어로 답하고, 마지막에 "
        "'※ 본 답변은 저장된 데이터 기반 참고 정보이며 투자 권유가 아닙니다.'를 덧붙이세요."
    )


def process_chat(payload: ChatRequest) -> dict[str, Any]:
    symbol = (payload.symbol or DEFAULT_STOCK_SYMBOL).strip().upper()

    # 1. 최신 데이터 요약 조회 (컨텍스트 주입용)
    summary = data_service.get_summary(symbol)

    # 2. 시스템 프롬프트 생성 (요약 주입)
    system_prompt = build_system_prompt(summary, use_tools=payload.use_tools)
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    # 기존 대화가 있으면 최근 6개 메시지만 문맥으로 포함 (토큰 절약)
    if payload.conversation_id:
        try:
            existing = conv_service.get_conversation(payload.conversation_id)
            for msg in existing.get("messages", [])[-6:]:
                if msg.get("role") in ("user", "assistant") and msg.get("content"):
                    messages.append({"role": msg["role"], "content": msg["content"]})
        except HTTPException:
            pass

    messages.append({"role": "user", "content": payload.message})

    # 3. OpenAI GPT API 호출 (+ 보너스 Function Calling 루프)
    client = get_openai_client()
    tools_used: list[dict[str, Any]] = []
    reply_text = ""

    try:
        for _ in range(3):
            kwargs: dict[str, Any] = {
                "model": OPENAI_MODEL,
                "messages": messages,
                "max_tokens": OPENAI_MAX_TOKENS,
                "temperature": 0.2,
            }
            if payload.use_tools:
                kwargs["tools"] = TOOL_DEFINITIONS
                kwargs["tool_choice"] = "auto"

            response = client.chat.completions.create(**kwargs)
            choice_msg = response.choices[0].message
            tool_calls = getattr(choice_msg, "tool_calls", None)

            if payload.use_tools and tool_calls:
                assistant_tool_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": choice_msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
                messages.append(assistant_tool_msg)

                for tc in tool_calls:
                    fn_name = tc.function.name
                    try:
                        fn_args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        fn_args = {}
                    tool_result = execute_tool(fn_name, fn_args, default_symbol=symbol)
                    tools_used.append(
                        {
                            "tool": fn_name,
                            "arguments": fn_args,
                            "status": "ok" if "error" not in tool_result else "error",
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(tool_result, ensure_ascii=False),
                        }
                    )
                continue

            reply_text = (choice_msg.content or "").strip()
            break

        if not reply_text:
            reply_text = "죄송합니다. 답변을 생성하지 못했습니다. 잠시 후 다시 시도해주세요."
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI API 호출 중 오류가 발생했습니다: {exc}",
        ) from exc

    # 4. 대화 내용을 Firestore conversations 컬렉션에 자동 저장
    saved_conv = conv_service.append_messages(
        conv_id=payload.conversation_id,
        symbol=symbol,
        user_message=payload.message,
        assistant_reply=reply_text,
        tools_used=tools_used,
    )

    return {
        "conversation_id": saved_conv["id"],
        "symbol": symbol,
        "stock_name": summary["stock_name"],
        "reply": reply_text,
        "tools_used": tools_used,
        "summary": summary,
    }
