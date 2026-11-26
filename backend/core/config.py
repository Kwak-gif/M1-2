import os
from dotenv import load_dotenv

load_dotenv()

STOCK_CATALOG: dict[str, dict[str, str]] = {
    "005930": {
        "symbol": "005930",
        "stock_name": "삼성전자",
        "yahoo_ticker": "005930.KS",
        "market": "KOSPI",
    },
    "000150": {
        "symbol": "000150",
        "stock_name": "두산",
        "yahoo_ticker": "000150.KS",
        "market": "KOSPI",
    },
}

DEFAULT_STOCK_SYMBOL: str = os.getenv("DEFAULT_STOCK_SYMBOL", "005930").strip() or "005930"
DEFAULT_STOCK_NAME: str = os.getenv(
    "DEFAULT_STOCK_NAME",
    STOCK_CATALOG.get(DEFAULT_STOCK_SYMBOL, {}).get("stock_name", "삼성전자"),
).strip() or "삼성전자"

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "").strip()
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
OPENAI_MAX_TOKENS: int = int(os.getenv("OPENAI_MAX_TOKENS", "650"))


def get_allowed_origins() -> list[str]:
    raw = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000,http://127.0.0.1:3000",
    )
    origins = [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
    return origins or ["*"]


def resolve_stock_name(symbol: str, provided_name: str | None = None) -> str:
    if provided_name and provided_name.strip():
        return provided_name.strip()
    if symbol in STOCK_CATALOG:
        return STOCK_CATALOG[symbol]["stock_name"]
    return symbol
