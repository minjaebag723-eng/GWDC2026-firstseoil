"""기능 정밀 검사 (정식 버전 전) — 계정 · 개인정보 · 친구·알림·대화 · 정산(현금 결제·취소) · 삭제한 기능.
정상 경로와 틀린 경로를 실제 API로 두드린다 (모의 체인 · AI 없음).
실행: DATA_DIR=/tmp/sp-feat LLM_MODE=mock CHAIN_MODE=mock KILN_API_KEY= CHARGE_COOLDOWN_SEC=0 python tests/feature_check.py
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from starlette.testclient import TestClient  # noqa: E402
from agent import service, store  # noqa: E402
from backend.app import app  # noqa: E402

fails = []
PW, PW2 = "abc12345", "xyz98765"


def ok(c, label):
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c:
        fails.append(label)


with TestClient(app) as cli:
    def call(path, body=None, tok=None, get=False):
        h = {"Authorization": f"Bearer {tok}"} if tok else {}
        r = cli.get(path, headers=h) if get else cli.post(path, json=body or {}, headers=h)
        d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        err = (d.get("error") or {}) if isinstance(d, dict) else {}
        return r.status_code, (d.get("data") if isinstance(d, dict) and "data" in d else d), err.get("code"), err.get("message", "")

    def code_for(email, purpose="signup"):
        st, d, c, _ = call("/api/auth/email-code", {"email": email, "purpose": purpose})
        return (d or {}).get("dev_code"), c

    def signup(name, email=None, pw=PW, pid=None):
        email = email or f"f.{uuid.uuid4().hex[:6]}@t.test"
        code, _ = code_for(email)
        st, d, c, m = call("/api/auth/signup", {"name": name, "email": email, "password": pw, "code": code, "pie_id": pid or "f" + uuid.uuid4().hex[:7]})
        return st, d, c, m, email

    print("[가입]")
    for name, why in (("", "빈 이름"), ("가" * 13, "13자 이름")):
        st, _, c, m, _ = signup(name)
        ok(st == 400, f"{why} → 거절 ({c}: {m[:30]})")
    st, _, c, _ = call("/api/auth/email-code", {"email": "abc", "purpose": "signup"})
    ok(st == 400, f"잘못된 이메일 형식 → 거절 ({c})")
    for pw, why in (("abc", "8자 미만"), ("abcdefgh", "숫자 없음"), ("12345678", "영문 없음")):
        st, _, c, _, _ = signup("약한비번", pw=pw)
        ok(c == "WEAK_PASSWORD", f"약한 비밀번호({why}) → {c}")
    st, _, c, _, _ = signup("아이디틀림", pid="1abc")
    ok(st == 400, f"잘못된 Pie ID → 거절 ({c})")
    st, A, c, _, ea = signup("검사가")
    ok(st == 200 and A.get("token"), "정상 가입")
    _, c = code_for(ea)
    ok(c == "EMAIL_TAKEN", f"이미 가입한 이메일로 인증번호 → {c}")

    print("[로그인 · 로그아웃]")
    st, _, c1, m1 = call("/api/auth/login", {"email": ea, "password": "wrong1234"})
    st2, _, c2, m2 = call("/api/auth/login", {"email": "nobody@t.test", "password": "wrong1234"})
    ok(st == 401 and st2 == 401 and m1 == m2, f"틀린 비밀번호·없는 이메일 → 같은 안내 (가입 여부 노출 안 함): {m1}")
    st, B, _, _, eb = signup("검사나")
    for _ in range(5):
        call("/api/auth/login", {"email": eb, "password": "wrong1234"})
    st, _, c, m = call("/api/auth/login", {"email": eb, "password": PW})
    ok(st == 429 and c == "LOGIN_LOCKED", f"5번 실패 → 맞는 비밀번호도 잠금: {m}")
    st, _, c, _ = call("/api/auth/me", get=True)
    ok(st == 401, "로그인 없이 내 정보 → 401")
    st, L, _, _ = call("/api/auth/login", {"email": ea, "password": PW})
    t = L["token"]
    ok(call("/api/auth/me", tok=t, get=True)[0] == 200, "로그인 → 내 정보")
    call("/api/auth/logout", tok=t)
    ok(call("/api/auth/me", tok=t, get=True)[0] == 401, "로그아웃하면 그 토큰은 더 못 씀")

    print("[아이디 찾기 · 비밀번호 재설정 · 변경]")
    st, d, _, _ = call("/api/auth/find-id", {"name": "검사가"})
    ok(st == 200 and "@" in str(d) and ea not in str(d), f"아이디 찾기 → 가린 이메일: {str(d)[:60]}")
    st, d, c, _ = call("/api/auth/find-id", {"name": "없는사람" + uuid.uuid4().hex[:3]})
    ok(st in (200, 404) and c != "INTERNAL", f"없는 이름 → 오류 없이 안내 ({st})")
    rc, _ = code_for(ea, "reset")
    ok(call("/api/auth/reset-password", {"email": ea, "code": "000000" if rc != "000000" else "111111", "password": PW2})[2] == "CODE_MISMATCH", "틀린 인증번호 → 재설정 거부")
    ok(call("/api/auth/reset-password", {"email": ea, "code": rc, "password": "short"})[2] == "WEAK_PASSWORD", "약한 새 비밀번호 → 거부")
    old_tok = call("/api/auth/login", {"email": ea, "password": PW})[1]["token"]
    st, _, c, _ = call("/api/auth/reset-password", {"email": ea, "code": rc, "password": PW2})
    ok(st == 200, f"재설정 성공 ({c})")
    ok(call("/api/auth/login", {"email": ea, "password": PW})[0] == 401 and call("/api/auth/login", {"email": ea, "password": PW2})[0] == 200, "옛 비밀번호 거부 · 새 비밀번호 로그인")
    ok(call("/api/auth/me", tok=old_tok, get=True)[0] == 401, "재설정 전 로그인은 끊김")
    t = call("/api/auth/login", {"email": ea, "password": PW2})[1]["token"]
    ok(call("/api/auth/change-password", {"old_password": "wrong1234", "new_password": PW}, tok=t)[2] == "AUTH_FAILED", "변경: 틀린 현재 비밀번호 → 거부")
    ok(call("/api/auth/change-password", {"old_password": PW2, "new_password": "12345678"}, tok=t)[2] == "WEAK_PASSWORD", "변경: 약한 새 비밀번호 → 거부")
    st, _, c, _ = call("/api/auth/change-password", {"old_password": PW2, "new_password": PW}, tok=t)
    ok(st == 200 and call("/api/auth/login", {"email": ea, "password": PW})[0] == 200, f"변경 성공 → 새 비밀번호 로그인 ({c})")

    print("[비밀번호 없는 계정 (예전 방식 계정)]")
    st, C, _, _, ec = signup("검사다")
    store.update_user(ec, {"pw": ""})
    st, _, c, m = call("/api/auth/login", {"email": ec, "password": PW})
    ok(c == "NO_PASSWORD" and "재설정" in m, f"로그인 → 재설정 안내: {m[:40]}")
    rc, _ = code_for(ec, "reset")
    call("/api/auth/reset-password", {"email": ec, "code": rc, "password": PW})
    ok(call("/api/auth/login", {"email": ec, "password": PW})[0] == 200, "재설정으로 비밀번호를 만들면 로그인")

    print("[프로필]")
    ta = call("/api/auth/login", {"email": ea, "password": PW})[1]["token"]
    ok(call("/api/auth/profile", {"address": "a"}, tok=ta)[0] == 400, "동네 1자 → 거절")
    st, d, _, _ = call("/api/auth/profile", {"address": "서울 성동구 성수동"}, tok=ta)
    ok(st == 200, "동네 저장")
    ok(call("/api/auth/profile", {"pie_id": B["id"]}, tok=ta)[2] == "PIE_ID_TAKEN", "남의 Pie ID로 바꾸기 → 거절")

    print("[개인정보: 사용자 목록은 나와 친구만]")
    names = [u["short"] for u in call("/api/users", tok=ta, get=True)[1]]
    ok(A["short"] in names and B["short"] not in names, f"친구가 아닌 사람은 안 보임: {names}")
    tb = service._new_session(eb)
    call("/api/friends/add", {"id": B["id"]}, tok=ta)
    reqs = call("/api/friends/requests", tok=tb, get=True)[1]
    rid = next((r.get("id") for r in (reqs.get("incoming") if isinstance(reqs, dict) else reqs) or [] if r), None) if reqs else None
    service.friend_accept(store.user_by_email(eb), A["id"])
    rows = call("/api/users", tok=ta, get=True)[1]
    names = [u["short"] for u in rows]
    ok(B["short"] in names and all("email" not in u for u in rows), "친구가 되면 보임 · 이메일은 안 보임")

    print("[친구 삭제 · 알림 읽음 · 대화 저장·삭제]")
    st, _, c, _ = call("/api/friends/remove", {"id": B["id"]}, tok=ta)
    fl = call("/api/friends", tok=ta, get=True)[1]
    ok(st == 200 and not any((f.get("id") == B["id"]) for f in (fl or [])), f"친구 삭제 ({c})")
    nl = call("/api/notifs", tok=tb, get=True)[1] or []
    items = nl.get("items") if isinstance(nl, dict) else nl
    st, _, c, _ = call("/api/notifs/read", {}, tok=tb)
    nl2 = call("/api/notifs", tok=tb, get=True)[1] or []
    items2 = nl2.get("items") if isinstance(nl2, dict) else nl2
    ok(st == 200 and not any(not n.get("read") for n in (items2 or [])), f"알림 모두 읽음 ({len(items or [])}개)")
    cid = "c" + uuid.uuid4().hex[:8]
    call("/api/chats/save", {"id": cid, "title": "검사", "summary": "검사", "msgs": [{"from": "user", "text": "안녕"}]}, tok=ta)
    have = any(c.get("id") == cid for c in call("/api/chats", tok=ta, get=True)[1] or [])
    call(f"/api/chats/{cid}/delete", tok=ta)
    gone = not any(c.get("id") == cid for c in call("/api/chats", tok=ta, get=True)[1] or [])
    ok(have and gone, "대화 저장 → 목록 → 삭제")

    print("[정산: 현금 결제 기록 · 정산 취소 (결제자만)]")
    st, D, _, _, ed = signup("검사라")
    td = D["token"]; tc = call("/api/auth/login", {"email": ec, "password": PW})[1]["token"]
    for tok, u in ((ta, A), (tc, C), (td, D)):
        call("/api/members/register", {"name": u["short"], "wallet": None}, tok=tok)
        call("/api/wallet/charge", {"name": u["short"]}, tok=tok)   # 잔액이 없으면 지출 통제가 정산을 시작 전에 중단함
    body = {"group_name": "현금 검사", "members": [A["short"], C["short"], D["short"]], "shares": [[A["short"], 1000], [C["short"], 1000], [D["short"], 1000]],
            "total": 3000, "payer": A["short"], "rule_text": "3천원 셋이", "purpose": "검사"}
    st, rec, c, m = call("/api/settlement/request", body, tok=ta)
    sid = (rec or {}).get("id")
    ok(st == 200 and sid, f"정산 등록 ({c or 'ok'} {m[:30]})")
    if sid:
        st, _, c, _ = call("/api/settlement/offline-payment", {"settlement_id": sid, "participant": C["short"], "confirmer": C["short"]}, tok=tc)
        ok(st == 403, f"결제자가 아니면 현금 결제 기록 불가 ({st} {c})")
        st, r2, c, m = call("/api/settlement/offline-payment", {"settlement_id": sid, "participant": C["short"], "confirmer": A["short"]}, tok=ta)
        cst = next((x.get("state") for x in (r2 or {}).get("members", []) if x.get("name") == C["short"]), None)
        ok(st == 200 and cst not in (None, "wait") and any(x.get("kind") == "offline" for x in (r2 or {}).get("txs", [])),
           f"결제자가 현금 결제 기록 → {C['short']} 상태 '{cst}' · 온체인 기록")
        ok(call("/api/settlement/cancel", {"settlement_id": sid, "name": D["short"]}, tok=td)[0] == 403, "결제자가 아니면 정산 취소 불가")
        st, r3, c, _ = call("/api/settlement/cancel", {"settlement_id": sid, "name": A["short"]}, tok=ta)
        ok(st == 200 and (r3 or {}).get("status") not in ("open", "locked"), f"결제자 정산 취소 → {(r3 or {}).get('status')}")

    print("[탈퇴]")
    ok(call("/api/auth/withdraw", {"password": "wrong1234"}, tok=td)[2] == "AUTH_FAILED", "틀린 비밀번호 → 탈퇴 거부")
    body2 = {**body, "group_name": "진행 중", "members": [A["short"], D["short"]], "shares": [[A["short"], 1000], [D["short"], 1000]], "total": 2000}
    call("/api/settlement/request", body2, tok=ta)
    ok(call("/api/auth/withdraw", {"password": PW}, tok=td)[2] == "HAS_ACTIVE_SETTLEMENT", "진행 중인 정산이 있으면 탈퇴 불가")
    st, E, _, _, ee = signup("검사마")
    st, _, c, _ = call("/api/auth/withdraw", {"password": PW}, tok=E["token"])
    ok(st == 200 and call("/api/auth/login", {"email": ee, "password": PW})[0] == 401, f"탈퇴 → 로그인 불가 ({c or 'ok'})")
    ok(code_for(ee)[1] is None, "탈퇴한 이메일로 다시 가입 가능")

    print("[삭제한 기능]")
    ok(call("/api/auth/social/providers", get=True)[0] == 404 and call("/api/auth/social/kakao/start", get=True)[0] == 404, "소셜 로그인 API 없음")
    ok(call("/api/ai/pay", {"amount": 100}, tok=ta)[0] in (404, 405), "예전 AI 후불 결제 API 없음 (없는 주소와 같은 응답)")
    ok(call("/api/settle/calculate", {"text": "1만원 둘이"}, tok=ta)[0] in (404, 405), "옛 이름 /api/settle/* 없음")

print("\n✓ 전체 통과" if not fails else f"\n✗ 실패 {len(fails)}건")
sys.exit(1 if fails else 0)
