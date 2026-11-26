import json
import os
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore

_db_client: Any = None


def set_firestore_client(client: Any) -> None:
    """테스트 환경에서 모의(Mock) 클라이언트를 주입하기 위한 헬퍼."""
    global _db_client
    _db_client = client


def get_firestore_client() -> Any:
    """환경변수 기반 Firebase Firestore 클라이언트를 반환합니다."""
    global _db_client
    if _db_client is not None:
        return _db_client

    if not firebase_admin._apps:
        cred_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
        cred_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip()

        if cred_json:
            try:
                cred_dict = json.loads(cred_json)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "FIREBASE_SERVICE_ACCOUNT_JSON 환경변수가 올바른 JSON 형식이 아닙니다."
                ) from exc
            if "private_key" in cred_dict and isinstance(cred_dict["private_key"], str):
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
        elif cred_path:
            path_obj = Path(cred_path)
            if not path_obj.is_absolute():
                backend_dir = Path(__file__).resolve().parent.parent
                candidate = backend_dir / path_obj
                if candidate.exists():
                    path_obj = candidate
            if not path_obj.exists():
                raise RuntimeError(
                    f"Firebase 서비스 계정 키 파일을 찾을 수 없습니다: {path_obj}"
                )
            cred = credentials.Certificate(str(path_obj))
        else:
            raise RuntimeError(
                "Firebase 인증 환경변수(FIREBASE_SERVICE_ACCOUNT_JSON 또는 "
                "FIREBASE_SERVICE_ACCOUNT_PATH)가 설정되지 않았습니다."
            )

        firebase_admin.initialize_app(cred)

    _db_client = firestore.client()
    return _db_client
