import json
from pathlib import Path
from types import SimpleNamespace
import uuid

from fastapi.testclient import TestClient
import pytest

from core.firebase import set_firestore_client
from main import app
import mcp_server
from services.chat_service import set_openai_client


# ---------------------------------------------------------------------------
# Firestore 인메모리 테스트 더블 (실제 프로덕션에서는 Firebase Firestore 사용)
# ---------------------------------------------------------------------------
class _FakeSnapshot:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict | None:
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, store: dict, doc_id: str):
        self._store = store
        self.id = doc_id

    def get(self) -> _FakeSnapshot:
        return _FakeSnapshot(self.id, self._store.get(self.id))

    def set(self, data: dict) -> None:
        self._store[self.id] = dict(data)

    def update(self, updates: dict) -> None:
        self._store[self.id].update(updates)

    def delete(self) -> None:
        self._store.pop(self.id, None)


class _FakeCollection:
    def __init__(self, store: dict):
        self._store = store

    def add(self, data: dict):
        doc_id = uuid.uuid4().hex[:12]
        self._store[doc_id] = dict(data)
        return None, _FakeDocRef(self._store, doc_id)

    def document(self, doc_id: str) -> _FakeDocRef:
        return _FakeDocRef(self._store, doc_id)

    def stream(self):
        return [_FakeSnapshot(k, v) for k, v in self._store.items()]


class _FakeFirestore:
    def __init__(self):
        self._collections: dict[str, dict] = {}

    def collection(self, name: str) -> _FakeCollection:
        if name not in self._collections:
            self._collections[name] = {}
        return _FakeCollection(self._collections[name])


# ---------------------------------------------------------------------------
# OpenAI Function Calling 테스트 더블
# ---------------------------------------------------------------------------
class _FakeOpenAIClient:
    def __init__(self):
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        # 1차 호출: Function Calling 도구 호출 시뮬레이션
        if kwargs.get("tools") and self.calls == 1:
            tc = SimpleNamespace(
                id="call_test_001",
                function=SimpleNamespace(
                    name="get_stock_statistics",
                    arguments=json.dumps({"symbol": "005930"}),
                ),
            )
            msg = SimpleNamespace(content="", tool_calls=[tc])
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

        # 2차 호출: 도구 결과를 바탕으로 최종 답변 생성
        msg = SimpleNamespace(
            content=(
                "[핵심 요약] 삼성전자(005930)는 1년 평균가 대비 하회 구간입니다.\n"
                "[근거 수치/메모] 심화 통계 도구를 통해 이동평균선과 변동성을 함께 확인했습니다.\n"
                "※ 본 답변은 저장된 데이터 기반 참고 정보이며 투자 권유가 아닙니다."
            ),
            tool_calls=None,
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


@pytest.fixture()
def client():
    fake_db = _FakeFirestore()
    snapshot_path = Path(__file__).resolve().parent.parent / "data" / "real_stock_1y_snapshot.json"
    assert snapshot_path.exists(), "먼저 seed_stock_data.py --fetch-only로 실제 1년 스냅샷을 생성해야 합니다."
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    data_col = fake_db.collection("data")
    for sym, records in snapshot["stocks"].items():
        for rec in records:
            data_col.document(f"{sym}_{rec['date']}").set(rec)

    set_firestore_client(fake_db)
    set_openai_client(_FakeOpenAIClient())
    yield TestClient(app)
    set_firestore_client(None)
    set_openai_client(None)


def test_health_and_stocks(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    s = client.get("/api/stocks")
    assert s.status_code == 200
    stocks = {item["symbol"]: item for item in s.json()["stocks"]}
    assert "005930" in stocks and stocks["005930"]["stock_name"] == "삼성전자"
    assert "000150" in stocks and stocks["000150"]["stock_name"] == "두산"
    assert stocks["005930"]["count"] >= 200
    assert stocks["000150"]["count"] >= 200


def test_data_crud_and_pdf_compatibility(client: TestClient):
    # PDF 기본 형태(symbol 생략)로 POST 테스트
    create_res = client.post(
        "/api/data",
        json={"date": "2026-11-26", "value": 175000, "memo": "[시황] 외인 순매수 전환"},
    )
    assert create_res.status_code == 201
    created = create_res.json()
    assert created["symbol"] == "005930"
    item_id = created["id"]

    # Pydantic 검증 실패 테스트 (음수 종가 및 잘못된 날짜)
    bad_res = client.post("/api/data", json={"date": "2026-99-99", "value": -100, "memo": ""})
    assert bad_res.status_code == 422

    # 수정
    upd_res = client.put(
        f"/api/data/{item_id}",
        json={"value": 176500, "memo": "[시황] 외인·기관 동반 순매수"},
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["value"] == 176500

    # 삭제
    del_res = client.delete(f"/api/data/{item_id}")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True

    # 존재하지 않는 ID 삭제 시 404
    not_found = client.delete("/api/data/nonexistent_id")
    assert not_found.status_code == 404


def test_summary_and_bonus_statistics_for_both_stocks(client: TestClient):
    for sym, expected_name in [("005930", "삼성전자"), ("000150", "두산")]:
        sum_res = client.get(f"/api/data/summary?symbol={sym}")
        assert sum_res.status_code == 200
        body = sum_res.json()
        assert body["stock_name"] == expected_name
        assert body["count"] >= 200
        assert "average" in body["metrics"]
        assert "vs_average_pct" in body["metrics"]
        assert "position_in_range_pct" in body["metrics"]
        assert len(body["key_events"]) == 5
        assert len(body["recent_records"]) == 5

        stat_res = client.get(f"/api/data/statistics?symbol={sym}")
        assert stat_res.status_code == 200
        stat = stat_res.json()
        assert stat["moving_averages"]["ma20"] is not None
        assert stat["moving_averages"]["ma60"] is not None
        assert stat["moving_averages"]["ma120"] is not None
        assert stat["risk_metrics"]["max_drawdown_pct"] <= 0
        assert len(stat["series"]) == body["count"]


def test_chat_function_calling_and_conversations_flow(client: TestClient):
    chat_res = client.post(
        "/api/chat",
        json={
            "symbol": "005930",
            "message": "삼성전자 1년 평균가 대비 위치와 이동평균선 리스크를 분석해줘",
            "use_tools": True,
        },
    )
    assert chat_res.status_code == 200
    data = chat_res.json()
    assert data["symbol"] == "005930"
    assert len(data["tools_used"]) == 1
    assert data["tools_used"][0]["tool"] == "get_stock_statistics"
    conv_id = data["conversation_id"]

    # 대화 목록 조회
    list_res = client.get("/api/conversations")
    assert list_res.status_code == 200
    assert list_res.json()["count"] >= 1

    # 특정 대화 불러오기 (UX A안)
    detail_res = client.get(f"/api/conversations/{conv_id}")
    assert detail_res.status_code == 200
    assert len(detail_res.json()["messages"]) == 2

    # 대화 삭제
    del_res = client.delete(f"/api/conversations/{conv_id}")
    assert del_res.status_code == 200


def test_bonus_mcp_server_protocol(client: TestClient, monkeypatch):
    monkeypatch.setenv("MCP_MODE", "local")

    init_resp = mcp_server.handle_jsonrpc_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init_resp["result"]["serverInfo"]["name"] == "stockpulse-ai-mcp"

    list_resp = mcp_server.handle_jsonrpc_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tool_names = [t["name"] for t in list_resp["result"]["tools"]]
    assert "get_stock_summary" in tool_names
    assert "get_stock_statistics" in tool_names

    call_resp = mcp_server.handle_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_stock_summary", "arguments": {"symbol": "000150"}},
        }
    )
    assert call_resp["result"]["isError"] is False
    parsed = json.loads(call_resp["result"]["content"][0]["text"])
    assert parsed["symbol"] == "000150"
    assert parsed["stock_name"] == "두산"
