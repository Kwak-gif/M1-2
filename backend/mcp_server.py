"""
[보너스 과제] StockPulse AI — MCP (Model Context Protocol) Server (JSON-RPC 2.0 over stdio)

외부 MCP 클라이언트(Antigravity, Claude Desktop 등)가 StockPulse AI의 내부 도구
(종목 요약, 심화 통계, 변곡점 조회, 이전 대화 목록 조회)를 표준 MCP 프로토콜로 호출할 수 있도록 제공합니다.

동작 모드:
- 기본(HTTP 연동 모드): 환경변수 API_BASE_URL(예: Render 배포 URL 또는 http://127.0.0.1:8000)로 REST API 호출
- 로컬 직접 모드(MCP_MODE=local): 백엔드 서비스 모듈(chat_service.execute_tool)을 직접 호출

실행 예시:
    set API_BASE_URL=https://your-backend.onrender.com
    python mcp_server.py
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "stockpulse-ai-mcp", "version": "1.0.0"}

MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_stock_summary",
        "description": "선택 종목(005930 삼성전자, 000150 두산)의 1년 기간 요약, 평균가 대비 위치(%), 추세, 변곡점 및 최근 시황을 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "종목코드 ('005930' 또는 '000150')",
                    "default": "005930",
                }
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_stock_statistics",
        "description": "이동평균선(MA5/20/60/120), 기간별 수익률, 변동성, 최대낙폭(MDD), 월별 평균가를 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "종목코드 ('005930' 또는 '000150')",
                    "default": "005930",
                }
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_inflection_points",
        "description": "종목의 전일 대비 급등락 변곡점 날짜, 종가, 등락률 및 [이슈]/[리스크] 메모를 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "default": "005930"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "list_recent_conversations",
        "description": "저장된 AI 주식 상담/브리핑 대화 목록을 조회합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "종목코드 또는 생략 시 전체"},
                "limit": {"type": "integer", "default": 5},
            },
        },
    },
]


def _call_remote_api(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    symbol = (arguments.get("symbol") or "005930").strip().upper()

    if tool_name == "get_stock_summary":
        url = f"{base_url}/api/data/summary?symbol={urllib.parse.quote(symbol)}"
    elif tool_name == "get_stock_statistics":
        url = f"{base_url}/api/data/statistics?symbol={urllib.parse.quote(symbol)}"
    elif tool_name == "get_inflection_points":
        url = f"{base_url}/api/data/summary?symbol={urllib.parse.quote(symbol)}"
    elif tool_name == "list_recent_conversations":
        params = {"limit": str(arguments.get("limit", 5))}
        if arguments.get("symbol"):
            params["symbol"] = str(arguments["symbol"]).upper()
        url = f"{base_url}/api/conversations?{urllib.parse.urlencode(params)}"
    else:
        return {"error": f"지원하지 않는 도구: {tool_name}"}

    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return {"error": f"백엔드 API({url}) 호출 실패: {exc}"}

    if tool_name == "get_inflection_points":
        limit = int(arguments.get("limit", 5))
        return {
            "symbol": symbol,
            "inflection_points": (data.get("key_events") or [])[:limit],
        }
    if tool_name == "get_stock_statistics":
        return {k: v for k, v in data.items() if k != "series"}
    return data


def _dispatch_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if os.getenv("MCP_MODE", "http").lower() == "local":
        from services.chat_service import execute_tool

        return execute_tool(tool_name, arguments, default_symbol="005930")
    return _call_remote_api(tool_name, arguments)


def handle_jsonrpc_request(request: dict[str, Any]) -> dict[str, Any] | None:
    req_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    # Notifications have no id and expect no response
    if method == "notifications/initialized" or req_id is None:
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_TOOLS},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments") or {}
        result_data = _dispatch_tool(tool_name, arguments)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result_data, ensure_ascii=False, indent=2),
                    }
                ],
                "isError": "error" in result_data,
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle_jsonrpc_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
