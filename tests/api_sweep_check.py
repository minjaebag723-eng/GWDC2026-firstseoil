"""API 전수 검사 — 모든 경로를 로그인 없이 · 깨진 요청 · 빈 요청 · 없는 id로 두드려 서버 오류(500)와 잘못 열린 곳을 찾는다.
실행: DATA_DIR=/tmp/sp-sweep LLM_MODE=mock CHAIN_MODE=mock KILN_API_KEY= python tests/api_sweep_check.py [--show]
"""
import json
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from starlette.routing import Route  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402
from agent import service  # noqa: E402
from backend.app import app as inner  # noqa: E402
from deploy.asgi import app  # noqa: E402

SHOW = "--show" in sys.argv
# 로그인 없이 열려 있어야 하는 곳 (가입·로그인·찾기 · 공개 설정 · 제3자가 검토하는 정산 인증서 · 공개 체인 잔액 · 베타 공개 보고서)
PUBLIC = re.compile(r"^/(healthz|api/health|api/config|api/auth/(signup|login|email-code|reset-password|find-id|remembered|remembered/forget)|"
                    r"api/users/check-id|api/settlement/\{sid\}|api/settle/\{sid\}|api/wallet/\{address\}|api/beta|api/beta/report(\.md)?|"
                    r"api/beta/(storage|chain)|api/groupbuy/nearby|api/auth/logout|api/usage|api/usage/report\.md|api/usage/calls\.csv)$")   # usage: 익명 단계별 토큰 보고 (심사 공개 자료 · 이메일·대화 없음)
fails, rows = [], []


def ok(c, label):
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c:
        fails.append(label)


def user(name):
    email = f"sw.{uuid.uuid4().hex[:6]}@t.test"
    u = service.signup(name, email, "abc12345", code=service.send_code(email, "signup")["dev_code"])
    return u, {"Authorization": f"Bearer {u['token']}"}


with TestClient(app) as cli:
    A, HA = user("스윕가"); B, HB = user("스윕나")
    gid = "gsw" + uuid.uuid4().hex[:8]
    service.group_create(A["short"], {"id": gid, "name": "스윕방", "members": [A["short"], B["short"]]})
    mid = "m" + uuid.uuid4().hex[:8]
    service.group_message(A["short"], gid, {"id": mid, "from": A["short"], "text": "안녕"})
    real = {"gid": gid, "mid": mid, "sid": "sp-없는정산", "cid": "c-없는대화", "pid": "없는아이디", "address": "0x" + "0" * 40, "provider": "kakao"}
    extra = [Route(p, lambda r: None, methods=["GET"]) for p in ("/healthz", "/api/beta/storage", "/api/beta/bundle.zip", "/api/beta/chain")]
    for r in list(inner.routes) + extra:
        if not isinstance(r, Route) or not r.path.startswith(("/api", "/healthz")):
            continue
        for meth in sorted(m for m in (r.methods or {"GET"}) if m != "HEAD"):
            url = re.sub(r"\{(\w+)(?::\w+)?\}", lambda m: real.get(m.group(1), "x"), r.path)
            call = (lambda **k: cli.request(meth, url, **k))
            res = {}
            res["anon"] = call(json={} if meth == "POST" else None).status_code
            res["broken"] = call(headers={**HA, "Content-Type": "application/json"}, content=b"not json").status_code if meth == "POST" else None
            res["empty"] = call(headers=HA, json={} if meth == "POST" else None).status_code
            is_public = bool(PUBLIC.match(r.path))
            rows.append((meth, r.path, res, is_public))
    five = [(m, p, r) for m, p, r, _ in rows if any((v or 0) >= 500 for v in r.values())]
    open_ = [(m, p, r) for m, p, r, pub in rows if not pub and r["anon"] < 400]
    NOBODY = {"/api/auth/logout", "/api/auth/remembered/forget"}   # 몸통을 읽지 않는 API
    broken = [(m, p, r) for m, p, r, _ in rows if r["broken"] is not None and p not in NOBODY and not (400 <= r["broken"] < 500)]
    print(f"[API {len(rows)}개 (메서드별)]")
    ok(not five, f"서버 오류(500) 없음 {'' if not five else '→ ' + ', '.join(f'{m} {p} {r}' for m, p, r in five)}")
    ok(not open_, f"로그인 없이 열린 곳은 공개용뿐 {'' if not open_ else '→ ' + ', '.join(f'{m} {p}({r[chr(97)+chr(110)+chr(111)+chr(110)]})' for m, p, r in open_)}")
    ok(not broken, f"깨진 요청은 400대로 거절 {'' if not broken else '→ ' + ', '.join(f'{m} {p}({r[chr(98)+chr(114)+chr(111)+chr(107)+chr(101)+chr(110)]})' for m, p, r in broken)}")
    ok(not any("/api/auth/social" in p for _, p, _, _ in rows), "소셜 로그인 API 없음")
    if SHOW:
        for m, p, r, pub in rows:
            print(f"   {m:5} {p:48} 로그인없이 {r['anon']} · 깨진요청 {r['broken']} · 빈요청 {r['empty']}{' (공개)' if pub else ''}")
print("\n✓ 전체 통과" if not fails else f"\n✗ 실패 {len(fails)}건")
sys.exit(1 if fails else 0)
