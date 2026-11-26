"""
삼성전자(005930)·두산(000150) 오늘 기준 최근 1년 실제 과거 종가 데이터 수집 및 Firestore 적재 스크립트.

특징:
- 외부 무거운 라이브러리(yfinance/pandas) 없이 파이썬 표준 라이브러리만으로 Yahoo Finance 실제 일별 종가 수집
- 1년치 실제 종가 중 전일 대비 급등락 변곡점([이슈]), 기간 최고/최저/평균가 구간([리스크]),
  최근 5거래일 흐름([시황])에 사실 기반(실제 종가·등락률 근거) 메모를 자동 태깅
- 로컬 스냅샷(backend/data/real_stock_1y_snapshot.json) 저장 및 Firestore `data` 컬렉션 적재 지원

사용법:
  1) 실제 1년 종가 스냅샷만 먼저 내려받기 (Firebase 키 없이 확인 가능):
     python scripts/seed_stock_data.py --fetch-only

  2) 소량(종목당 10건)으로 Firestore 연동 먼저 검증:
     python scripts/seed_stock_data.py --limit 10

  3) 삼성전자·두산 전체 1년 실제 종가(각 약 244거래일) Firestore 적재:
     python scripts/seed_stock_data.py --reset
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.config import STOCK_CATALOG

SNAPSHOT_PATH = BACKEND_DIR / "data" / "real_stock_1y_snapshot.json"
KST = timezone(timedelta(hours=9))


def fetch_yahoo_1y_closes(yahoo_ticker: str) -> list[tuple[str, float]]:
    """오늘 날짜 기준 최근 1년(365일) 실제 과거 종가를 Yahoo Finance에서 수집합니다."""
    now_kst = datetime.now(KST)
    start_kst = now_kst - timedelta(days=366)
    period1 = int(start_kst.timestamp())
    period2 = int((now_kst + timedelta(days=1)).timestamp())

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}"
        f"?period1={period1}&period2={period2}&interval=1d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Yahoo Finance({yahoo_ticker}) 데이터 수집 실패: {exc}") from exc

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        raise RuntimeError(f"Yahoo Finance({yahoo_ticker}) 응답이 비어 있습니다.")

    chart = result[0]
    timestamps = chart.get("timestamp") or []
    quote_list = (chart.get("indicators") or {}).get("quote") or [{}]
    closes = quote_list[0].get("close") or []

    dedup: dict[str, float] = {}
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        dt_str = datetime.fromtimestamp(ts, KST).strftime("%Y-%m-%d")
        dedup[dt_str] = float(round(close))

    return sorted(dedup.items(), key=lambda x: x[0])


def build_stock_records(symbol: str, stock_name: str, rows: list[tuple[str, float]]) -> list[dict[str, Any]]:
    """실제 과거 종가 시계열에 사실 기반 [이슈]/[리스크]/[시황] 메모를 태깅합니다."""
    if not rows:
        return []

    values = [v for _, v in rows]
    avg_val = sum(values) / len(values)
    max_val = max(values)
    min_val = min(values)
    max_date = next(dt for dt, v in rows if v == max_val)
    min_date = next(dt for dt, v in rows if v == min_val)

    # 전일 대비 변동률 계산
    enriched: list[dict[str, Any]] = []
    for idx, (dt, val) in enumerate(rows):
        if idx == 0 or rows[idx - 1][1] == 0:
            chg = 0.0
        else:
            prev = rows[idx - 1][1]
            chg = round(((val - prev) / prev) * 100, 2)
        enriched.append({"date": dt, "value": val, "change_pct": chg})

    # 변동폭 상위 8개 날짜를 [이슈] 변곡점 후보로 식별
    top_moves = {
        item["date"]
        for item in sorted(enriched[1:], key=lambda x: abs(x["change_pct"]), reverse=True)[:8]
    }
    recent_dates = {item["date"] for item in enriched[-5:]}

    now_iso = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []

    for idx, item in enumerate(enriched):
        dt = item["date"]
        val = item["value"]
        chg = item["change_pct"]
        sign = "+" if chg >= 0 else ""
        vs_avg = round(((val - avg_val) / avg_val) * 100, 1)
        vs_avg_sign = "+" if vs_avg >= 0 else ""

        memo = ""
        if dt in recent_dates:
            direction = "상승" if chg > 0 else ("하락" if chg < 0 else "보합")
            memo = (
                f"[시황] 최근 거래일 종가 {int(val):,}원 "
                f"(전일 대비 {sign}{chg}% {direction}, 1년 평균가 대비 {vs_avg_sign}{vs_avg}%)"
            )
        elif dt == max_date:
            memo = (
                f"[리스크] 최근 1년 최고 종가({int(val):,}원) 기록 "
                f"(1년 평균가 대비 {vs_avg_sign}{vs_avg}%, 고점 부담 점검 구간)"
            )
        elif dt == min_date:
            memo = (
                f"[리스크] 최근 1년 최저 종가({int(val):,}원) 기록 "
                f"(1년 평균가 대비 {vs_avg_sign}{vs_avg}%, 지지선·분할 관망 점검 구간)"
            )
        elif dt in top_moves:
            direction = "급등" if chg > 0 else "급락"
            memo = (
                f"[이슈] 전일 대비 {sign}{chg}% {direction} 변곡점 "
                f"(종가 {int(val):,}원 — 공시·업황·수급 이슈 메모 보완 권장)"
            )
        elif idx > 0 and (enriched[idx - 1]["value"] >= avg_val > val):
            memo = f"[리스크] 1년 평균가({int(avg_val):,}원) 하향 이탈 (종가 {int(val):,}원, 관망 체크)"
        elif idx > 0 and (enriched[idx - 1]["value"] <= avg_val < val):
            memo = f"[리스크] 1년 평균가({int(avg_val):,}원) 상향 돌파 (종가 {int(val):,}원, 추세 전환 체크)"

        records.append(
            {
                "symbol": symbol,
                "stock_name": stock_name,
                "date": dt,
                "value": val,
                "memo": memo,
                "created_at": now_iso,
                "updated_at": now_iso,
            }
        )

    return records


def fetch_and_save_snapshot() -> dict[str, list[dict[str, Any]]]:
    all_data: dict[str, list[dict[str, Any]]] = {}
    for sym, info in STOCK_CATALOG.items():
        rows = fetch_yahoo_1y_closes(info["yahoo_ticker"])
        records = build_stock_records(sym, info["stock_name"], rows)
        all_data[sym] = records
        print(
            f"[수집 완료] {info['stock_name']}({sym}): {len(records)}거래일 "
            f"({records[0]['date']} ~ {records[-1]['date']}, 최근 종가 {int(records[-1]['value']):,}원)"
        )

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "fetched_at": datetime.now(KST).isoformat(),
                "source": "Yahoo Finance Daily Close (1Y)",
                "stocks": all_data,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"[스냅샷 저장] {SNAPSHOT_PATH}")
    return all_data


def seed_firestore(all_data: dict[str, list[dict[str, Any]]], limit: int | None, reset: bool) -> None:
    from core.firebase import get_firestore_client

    db = get_firestore_client()
    col = db.collection("data")

    if reset:
        target_symbols = set(all_data.keys())
        existing_docs = list(col.stream())
        deleted = 0
        batch = db.batch()
        batch_count = 0
        for doc in existing_docs:
            doc_sym = (doc.to_dict() or {}).get("symbol", "005930")
            if doc_sym in target_symbols:
                batch.delete(doc.reference)
                deleted += 1
                batch_count += 1
                if batch_count >= 400:
                    batch.commit()
                    batch = db.batch()
                    batch_count = 0
        if batch_count > 0:
            batch.commit()
        print(f"[초기화 완료] 기존 대상 종목 문서 {deleted}건 삭제")

    total_written = 0
    for sym, records in all_data.items():
        subset = records[-limit:] if limit else records
        batch = db.batch()
        batch_count = 0
        for rec in subset:
            # 날짜+종목 기반 결정적 문서 ID를 사용해 재실행 시 중복 증식을 방지
            doc_id = f"{sym}_{rec['date']}"
            batch.set(col.document(doc_id), rec)
            batch_count += 1
            total_written += 1
            if batch_count >= 400:
                batch.commit()
                batch = db.batch()
                batch_count = 0
        if batch_count > 0:
            batch.commit()
        print(f"[Firestore 적재 완료] {sym}: {len(subset)}건")

    print(f"[전체 완료] 총 {total_written}건이 Firestore 'data' 컬렉션에 저장되었습니다.")


def main() -> None:
    parser = argparse.ArgumentParser(description="삼성전자·두산 1년 실제 종가 수집 및 Firestore 적재")
    parser.add_argument("--fetch-only", action="store_true", help="Firestore 적재 없이 로컬 JSON 스냅샷만 저장")
    parser.add_argument("--use-snapshot", action="store_true", help="네트워크 재수집 대신 기존 로컬 스냅샷으로 적재")
    parser.add_argument("--limit", type=int, default=None, help="종목당 적재할 최근 거래일 수 제한 (예: 10)")
    parser.add_argument("--reset", action="store_true", help="적재 전 대상 종목 기존 데이터 삭제")
    args = parser.parse_args()

    if args.use_snapshot and SNAPSHOT_PATH.exists():
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        all_data = snapshot["stocks"]
        print(f"[스냅샷 로드] {SNAPSHOT_PATH} (수집시각: {snapshot.get('fetched_at')})")
    else:
        all_data = fetch_and_save_snapshot()

    if args.fetch_only:
        print("[종료] --fetch-only 옵션으로 스냅샷 저장만 수행했습니다.")
        return

    seed_firestore(all_data, limit=args.limit, reset=args.reset)


if __name__ == "__main__":
    main()
