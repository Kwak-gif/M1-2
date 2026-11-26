"""OpenAI API 키 및 OPENAI_BASE_URL 인증 상태를 안전하게(키 원문 노출 없이) 점검하는 유틸리티."""

import os
from pathlib import Path
import re
from dotenv import load_dotenv
from openai import OpenAI

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BACKEND_DIR / ".env"

load_dotenv(ENV_PATH, override=True)

key = os.getenv("OPENAI_API_KEY", "").strip()
base = os.getenv("OPENAI_BASE_URL", "").strip()
model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

commented_base = ""
if not base and ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*#\s*OPENAI_BASE_URL\s*=\s*(https?://\S+)", line)
        if m:
            commented_base = m.group(1).strip()
            break

effective_base = base or commented_base
print(f"OPENAI_API_KEY prefix: {key[:12]}... (length={len(key)})")
print(f"OPENAI_BASE_URL (active): {base or '(미설정 - 공식 OpenAI 사용)'}")
if commented_base:
    print(f"[주의] .env에 주석 처리된 OPENAI_BASE_URL 발견: {commented_base}")
print(f"OPENAI_MODEL: {model}")

client = OpenAI(api_key=key, base_url=effective_base or None, timeout=20.0, max_retries=0)
try:
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "인증 성공이라고만 답해줘."}],
        max_tokens=20,
    )
    print("[인증 성공] 응답:", resp.choices[0].message.content)
except Exception as exc:
    resp_obj = getattr(exc, "response", None)
    body = resp_obj.text if resp_obj is not None else ""
    print(f"[인증 실패] {type(exc).__name__}: {exc}")
    if body:
        print(f"[서버 응답 본문] {body[:400]}")
