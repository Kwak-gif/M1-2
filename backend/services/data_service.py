from collections import defaultdict
from datetime import datetime, timezone
import math
from typing import Any, Optional

from fastapi import HTTPException

from core.config import DEFAULT_STOCK_SYMBOL, STOCK_CATALOG, resolve_stock_name
from core.firebase import get_firestore_client
from schemas.data_schema import DataCreate, DataUpdate

DATA_COLLECTION = "data"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_doc(doc_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    symbol = (raw.get("symbol") or DEFAULT_STOCK_SYMBOL).strip().upper()
    stock_name = resolve_stock_name(symbol, raw.get("stock_name"))
    return {
        "id": doc_id,
        "symbol": symbol,
        "stock_name": stock_name,
        "date": str(raw.get("date", "")),
        "value": float(raw.get("value", 0)),
        "memo": str(raw.get("memo", "")),
        "created_at": str(raw.get("created_at", "")),
        "updated_at": str(raw.get("updated_at", "")),
    }


def _fetch_all_records() -> list[dict[str, Any]]:
    db = get_firestore_client()
    docs = db.collection(DATA_COLLECTION).stream()
    items = [_normalize_doc(doc.id, doc.to_dict() or {}) for doc in docs]
    items.sort(key=lambda x: (x["date"], x["created_at"]))
    return items


def list_stocks() -> list[dict[str, Any]]:
    all_items = _fetch_all_records()
    counts: dict[str, int] = defaultdict(int)
    names: dict[str, str] = {}

    for sym, info in STOCK_CATALOG.items():
        names[sym] = info["stock_name"]

    for item in all_items:
        sym = item["symbol"]
        counts[sym] += 1
        if sym not in names:
            names[sym] = item["stock_name"]

    result = []
    for sym, name in names.items():
        catalog_info = STOCK_CATALOG.get(sym, {})
        result.append(
            {
                "symbol": sym,
                "stock_name": name,
                "market": catalog_info.get("market", "KRX"),
                "count": counts.get(sym, 0),
            }
        )
    return result


def create_data(payload: DataCreate) -> dict[str, Any]:
    db = get_firestore_client()
    now = _utc_now_iso()
    record = {
        "symbol": payload.symbol,
        "stock_name": payload.resolved_stock_name(),
        "date": payload.date,
        "value": float(payload.value),
        "memo": payload.memo.strip(),
        "created_at": now,
        "updated_at": now,
    }
    _, doc_ref = db.collection(DATA_COLLECTION).add(record)
    return {"id": doc_ref.id, **record}


def list_data(symbol: Optional[str] = None) -> list[dict[str, Any]]:
    target_symbol = (symbol or DEFAULT_STOCK_SYMBOL).strip().upper()
    all_items = _fetch_all_records()
    if target_symbol == "ALL":
        return all_items
    return [item for item in all_items if item["symbol"] == target_symbol]


def get_data_by_id(item_id: str) -> dict[str, Any]:
    db = get_firestore_client()
    doc = db.collection(DATA_COLLECTION).document(item_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail=f"데이터를 찾을 수 없습니다: {item_id}")
    return _normalize_doc(doc.id, doc.to_dict() or {})


def update_data(item_id: str, payload: DataUpdate) -> dict[str, Any]:
    db = get_firestore_client()
    doc_ref = db.collection(DATA_COLLECTION).document(item_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail=f"수정할 데이터를 찾을 수 없습니다: {item_id}")

    current = _normalize_doc(doc.id, doc.to_dict() or {})
    updates: dict[str, Any] = {}

    if payload.date is not None:
        updates["date"] = payload.date
    if payload.value is not None:
        updates["value"] = float(payload.value)
    if payload.memo is not None:
        updates["memo"] = payload.memo.strip()
    if payload.symbol is not None:
        updates["symbol"] = payload.symbol
        updates["stock_name"] = resolve_stock_name(payload.symbol, payload.stock_name)
    elif payload.stock_name is not None:
        updates["stock_name"] = payload.stock_name.strip()

    updates["updated_at"] = _utc_now_iso()
    doc_ref.update(updates)
    current.update(updates)
    return current


def delete_data(item_id: str) -> dict[str, Any]:
    db = get_firestore_client()
    doc_ref = db.collection(DATA_COLLECTION).document(item_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail=f"삭제할 데이터를 찾을 수 없습니다: {item_id}")
    doc_ref.delete()
    return {"deleted": True, "id": item_id}


def _enrich_daily_changes(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for idx, rec in enumerate(records):
        if idx == 0 or records[idx - 1]["value"] == 0:
            change_pct = 0.0
        else:
            prev_val = records[idx - 1]["value"]
            change_pct = round(((rec["value"] - prev_val) / prev_val) * 100, 2)
        enriched.append({**rec, "change_pct": change_pct})
    return enriched


def get_inflection_points(symbol: Optional[str] = None, limit: int = 5) -> list[dict[str, Any]]:
    records = list_data(symbol)
    if not records:
        return []
    enriched = _enrich_daily_changes(records)
    tagged_or_moved = sorted(
        enriched,
        key=lambda r: (
            1 if ("[이슈]" in r["memo"] or "[리스크]" in r["memo"]) else 0,
            abs(r["change_pct"]),
        ),
        reverse=True,
    )
    top = tagged_or_moved[: max(1, min(limit, 15))]
    top.sort(key=lambda r: r["date"], reverse=True)
    return [
        {
            "date": r["date"],
            "value": r["value"],
            "change_pct": r["change_pct"],
            "memo": r["memo"],
        }
        for r in top
    ]


def get_summary(symbol: Optional[str] = None) -> dict[str, Any]:
    target_symbol = (symbol or DEFAULT_STOCK_SYMBOL).strip().upper()
    stock_name = resolve_stock_name(target_symbol)
    records = list_data(target_symbol)

    if not records:
        return {
            "symbol": target_symbol,
            "stock_name": stock_name,
            "period": "데이터 없음",
            "count": 0,
            "metrics": {
                "total": 0,
                "average": 0,
                "max": 0,
                "max_date": None,
                "max_memo": "",
                "min": 0,
                "min_date": None,
                "min_memo": "",
                "latest_close": 0,
                "latest_date": None,
                "prev_close": 0,
                "latest_change_pct": 0.0,
                "vs_average_pct": 0.0,
                "position_in_range_pct": 0.0,
            },
            "trend": "데이터 부족",
            "key_events": [],
            "recent_records": [],
        }

    stock_name = records[-1]["stock_name"]
    enriched = _enrich_daily_changes(records)
    values = [r["value"] for r in enriched]
    count = len(values)
    total = round(sum(values), 2)
    average = round(total / count, 2)

    max_rec = max(enriched, key=lambda r: r["value"])
    min_rec = min(enriched, key=lambda r: r["value"])
    latest = enriched[-1]
    prev_close = enriched[-2]["value"] if count >= 2 else latest["value"]

    vs_average_pct = round(((latest["value"] - average) / average) * 100, 2) if average else 0.0
    if max_rec["value"] == min_rec["value"]:
        position_pct = 50.0
    else:
        position_pct = round(
            ((latest["value"] - min_rec["value"]) / (max_rec["value"] - min_rec["value"])) * 100,
            2,
        )

    # 최근 20거래일 평균 vs 직전 20거래일 평균으로 추세 판정
    if count >= 40:
        recent_slice = values[-20:]
        prev_slice = values[-40:-20]
        window_label = "최근 20거래일 평균 대비"
    elif count >= 2:
        half = count // 2
        recent_slice = values[-half:]
        prev_slice = values[:half]
        window_label = f"최근 {half}거래일 평균 대비"
    else:
        recent_slice = values
        prev_slice = values
        window_label = "단일 데이터"

    recent_avg = sum(recent_slice) / len(recent_slice)
    prev_avg = sum(prev_slice) / len(prev_slice) if prev_slice else recent_avg
    trend_diff_pct = round(((recent_avg - prev_avg) / prev_avg) * 100, 2) if prev_avg else 0.0

    if count < 2:
        trend = "유지 (데이터 1건)"
    elif trend_diff_pct > 2.0:
        trend = f"상승 ({window_label} +{trend_diff_pct}%)"
    elif trend_diff_pct < -2.0:
        trend = f"감소 ({window_label} {trend_diff_pct}%)"
    else:
        sign = "+" if trend_diff_pct >= 0 else ""
        trend = f"유지 ({window_label} {sign}{trend_diff_pct}%)"

    key_events = get_inflection_points(target_symbol, limit=5)
    recent_records = [
        {
            "date": r["date"],
            "value": r["value"],
            "change_pct": r["change_pct"],
            "memo": r["memo"],
        }
        for r in reversed(enriched[-5:])
    ]

    return {
        "symbol": target_symbol,
        "stock_name": stock_name,
        "period": f"{enriched[0]['date']} ~ {enriched[-1]['date']}",
        "count": count,
        "metrics": {
            "total": total,
            "average": average,
            "max": max_rec["value"],
            "max_date": max_rec["date"],
            "max_memo": max_rec["memo"],
            "min": min_rec["value"],
            "min_date": min_rec["date"],
            "min_memo": min_rec["memo"],
            "latest_close": latest["value"],
            "latest_date": latest["date"],
            "prev_close": prev_close,
            "latest_change_pct": latest["change_pct"],
            "vs_average_pct": vs_average_pct,
            "position_in_range_pct": position_pct,
        },
        "trend": trend,
        "key_events": key_events,
        "recent_records": recent_records,
    }


def _moving_average(values: list[float], window: int) -> Optional[float]:
    if len(values) < window:
        return None
    return round(sum(values[-window:]) / window, 2)


def _period_return(values: list[float], lookback: int) -> Optional[float]:
    if len(values) <= lookback or values[-lookback - 1] == 0:
        return None
    base = values[-lookback - 1]
    return round(((values[-1] - base) / base) * 100, 2)


def get_statistics(symbol: Optional[str] = None) -> dict[str, Any]:
    """보너스 과제: 이동평균, 변동성, 기간별 수익률, 최대낙폭(MDD), 월별 평균 및 차트 시계열 제공."""
    target_symbol = (symbol or DEFAULT_STOCK_SYMBOL).strip().upper()
    stock_name = resolve_stock_name(target_symbol)
    records = list_data(target_symbol)

    if not records:
        return {
            "symbol": target_symbol,
            "stock_name": stock_name,
            "count": 0,
            "moving_averages": {"ma5": None, "ma20": None, "ma60": None, "ma120": None},
            "returns_pct": {"return_5d": None, "return_20d": None, "return_60d": None, "return_1y": None},
            "risk_metrics": {"daily_volatility_pct": 0.0, "max_drawdown_pct": 0.0},
            "monthly_averages": [],
            "series": [],
        }

    stock_name = records[-1]["stock_name"]
    enriched = _enrich_daily_changes(records)
    values = [r["value"] for r in enriched]
    daily_returns = [r["change_pct"] for r in enriched[1:]]

    if len(daily_returns) >= 2:
        mean_ret = sum(daily_returns) / len(daily_returns)
        variance = sum((x - mean_ret) ** 2 for x in daily_returns) / len(daily_returns)
        volatility_pct = round(math.sqrt(variance), 2)
    else:
        volatility_pct = 0.0

    # 최대 낙폭 (MDD: Maximum Drawdown)
    running_peak = values[0]
    max_drawdown = 0.0
    for v in values:
        if v > running_peak:
            running_peak = v
        if running_peak > 0:
            dd = ((v - running_peak) / running_peak) * 100
            if dd < max_drawdown:
                max_drawdown = dd

    first_val = values[0]
    return_1y = round(((values[-1] - first_val) / first_val) * 100, 2) if first_val else 0.0

    # 월별 평균가
    monthly_bucket: dict[str, list[float]] = defaultdict(list)
    for r in enriched:
        month_key = r["date"][:7]
        monthly_bucket[month_key].append(r["value"])

    monthly_averages = [
        {
            "month": month,
            "average": round(sum(vals) / len(vals), 2),
            "count": len(vals),
        }
        for month, vals in sorted(monthly_bucket.items())
    ]

    # 차트 시각화용 시계열 (종가 + 20일 이동평균)
    series = []
    for idx, r in enumerate(enriched):
        ma20_val = (
            round(sum(values[idx - 19 : idx + 1]) / 20, 2)
            if idx >= 19
            else round(sum(values[: idx + 1]) / (idx + 1), 2)
        )
        series.append(
            {
                "date": r["date"],
                "value": r["value"],
                "ma20": ma20_val,
                "change_pct": r["change_pct"],
                "memo": r["memo"],
            }
        )

    return {
        "symbol": target_symbol,
        "stock_name": stock_name,
        "count": len(values),
        "moving_averages": {
            "ma5": _moving_average(values, 5),
            "ma20": _moving_average(values, 20),
            "ma60": _moving_average(values, 60),
            "ma120": _moving_average(values, 120),
        },
        "returns_pct": {
            "return_5d": _period_return(values, 5),
            "return_20d": _period_return(values, 20),
            "return_60d": _period_return(values, 60),
            "return_1y": return_1y,
        },
        "risk_metrics": {
            "daily_volatility_pct": volatility_pct,
            "max_drawdown_pct": round(max_drawdown, 2),
        },
        "monthly_averages": monthly_averages,
        "series": series,
    }
