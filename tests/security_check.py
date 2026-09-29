"""보안 검사 — 개발용 API 잠금 · 베타 다운로드 키 (모의 체인에서).
실행: DATA_DIR=/tmp/sp-sec LLM_MODE=mock CHAIN_MODE=mock KILN_API_KEY= python tests/security_check.py
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from starlette.testclient import TestClient  # noqa: E402
from agent import service  # noqa: E402
from backend.app import app  # noqa: E402

fails = []


def ok(c, label):
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c:
        fails.append(label)


def user(name):
    email = f"sec.{uuid.uuid4().hex[:5]}@t.test"
    u = service.signup(name, email, "pass1234", code=service.send_code(email, "signup")["dev_code"])
    return u, {"Authorization": f"Bearer {u.get('token') or service.login(email, 'pass1234')['token']}"}


with TestClient(app) as cli:
    a, ha = user("보안가")
    b, hb = user("보안나")
    print("[개발용 API — 모의 체인]")
    body = {"sid": "없는정산", "name": a.get("short")}
    ok(cli.post("/api/dev/mock-lock", json=body).status_code == 401, "로그인 없이 모의 결제 → 401")
    ok(cli.post("/api/dev/mock-lock", json=body, headers=hb).status_code == 403, "남의 이름으로 모의 결제 → 403")
    ok(cli.post("/api/dev/mock-lock", json=body, headers=ha).status_code != 403, "본인 이름은 통과 (정산이 없어 다른 오류)")
    ok(cli.post("/api/dev/tamper", json={"sid": "x", "name": "y", "amount": 1}).status_code == 401, "로그인 없이 금액 조작 → 401")
    ok(cli.post("/api/dev/fast-forward", json={"settlement_id": "x"}).status_code == 401, "로그인 없이 시간 건너뛰기 → 401")
    print("[AI 사용량·추천 피드백은 로그인 필요]")
    ok(cli.post("/api/pie/feedback", json={"rec_id": "r_x", "event": "rate", "satisfaction": 3}).status_code in (401, 403), "로그인 없이 추천 피드백 → 거절")

print("\n✓ 전체 통과" if not fails else f"\n✗ 실패 {len(fails)}건")
sys.exit(1 if fails else 0)
