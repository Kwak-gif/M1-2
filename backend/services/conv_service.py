from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from core.config import DEFAULT_STOCK_SYMBOL, resolve_stock_name
from core.firebase import get_firestore_client
from schemas.chat_schema import ConversationCreate

CONVERSATIONS_COLLECTION = "conversations"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_conv(doc_id: str, raw: dict[str, Any], include_messages: bool = True) -> dict[str, Any]:
    symbol = (raw.get("symbol") or DEFAULT_STOCK_SYMBOL).strip().upper()
    stock_name = resolve_stock_name(symbol, raw.get("stock_name"))
    messages = raw.get("messages") or []
    result = {
        "id": doc_id,
        "title": str(raw.get("title", "제목 없는 대화")),
        "symbol": symbol,
        "stock_name": stock_name,
        "message_count": len(messages),
        "created_at": str(raw.get("created_at", "")),
        "updated_at": str(raw.get("updated_at", "")),
    }
    if include_messages:
        result["messages"] = messages
    return result


def create_conversation(payload: ConversationCreate) -> dict[str, Any]:
    db = get_firestore_client()
    now = _utc_now_iso()
    symbol = (payload.symbol or DEFAULT_STOCK_SYMBOL).strip().upper()
    stock_name = resolve_stock_name(symbol, payload.stock_name)
    messages = [
        {
            "role": m.role,
            "content": m.content,
            "timestamp": m.timestamp or now,
        }
        for m in payload.messages
    ]
    record = {
        "title": payload.title.strip(),
        "symbol": symbol,
        "stock_name": stock_name,
        "messages": messages,
        "created_at": now,
        "updated_at": now,
    }
    _, doc_ref = db.collection(CONVERSATIONS_COLLECTION).add(record)
    return _normalize_conv(doc_ref.id, record, include_messages=True)


def list_conversations(symbol: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
    """대화 목록 조회 (UX A안: 목록에서는 메타데이터만 반환하고 단건 조회에서 전체 messages 반환)."""
    db = get_firestore_client()
    docs = db.collection(CONVERSATIONS_COLLECTION).stream()
    items = [_normalize_conv(doc.id, doc.to_dict() or {}, include_messages=False) for doc in docs]

    if symbol and symbol.strip().upper() != "ALL":
        target = symbol.strip().upper()
        items = [item for item in items if item["symbol"] == target]

    items.sort(key=lambda x: x["updated_at"], reverse=True)
    return items[: max(1, min(limit, 100))]


def get_conversation(conv_id: str) -> dict[str, Any]:
    """UX A안: 특정 대화의 전체 messages를 조회합니다."""
    db = get_firestore_client()
    doc = db.collection(CONVERSATIONS_COLLECTION).document(conv_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail=f"대화를 찾을 수 없습니다: {conv_id}")
    return _normalize_conv(doc.id, doc.to_dict() or {}, include_messages=True)


def append_messages(
    conv_id: Optional[str],
    symbol: str,
    user_message: str,
    assistant_reply: str,
    tools_used: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    db = get_firestore_client()
    now = _utc_now_iso()
    sym = (symbol or DEFAULT_STOCK_SYMBOL).strip().upper()
    stock_name = resolve_stock_name(sym)

    new_entries = [
        {"role": "user", "content": user_message, "timestamp": now},
        {
            "role": "assistant",
            "content": assistant_reply,
            "timestamp": _utc_now_iso(),
            "tools_used": tools_used or [],
        },
    ]

    if conv_id:
        doc_ref = db.collection(CONVERSATIONS_COLLECTION).document(conv_id)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict() or {}
            messages = list(data.get("messages") or [])
            messages.extend(new_entries)
            doc_ref.update({"messages": messages, "updated_at": now})
            data["messages"] = messages
            data["updated_at"] = now
            return _normalize_conv(conv_id, data, include_messages=True)

    short_q = user_message.strip().replace("\n", " ")[:32]
    title = f"[{stock_name}] {short_q}"
    record = {
        "title": title,
        "symbol": sym,
        "stock_name": stock_name,
        "messages": new_entries,
        "created_at": now,
        "updated_at": now,
    }
    _, doc_ref = db.collection(CONVERSATIONS_COLLECTION).add(record)
    return _normalize_conv(doc_ref.id, record, include_messages=True)


def delete_conversation(conv_id: str) -> dict[str, Any]:
    db = get_firestore_client()
    doc_ref = db.collection(CONVERSATIONS_COLLECTION).document(conv_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail=f"삭제할 대화를 찾을 수 없습니다: {conv_id}")
    doc_ref.delete()
    return {"deleted": True, "id": conv_id}
