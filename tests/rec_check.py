"""④ 상황 인식 추천 검사 (Pie mate 학습 가이드라인 ④).
실행: DATA_DIR=/tmp/sp-rec LLM_MODE=mock CHAIN_MODE=mock KILN_API_KEY= APP_VERSION=beta-1 python tests/rec_check.py
"""
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent import beta, config, recs, service, store  # noqa: E402

fails = []


def ok(c, label):
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c:
        fails.append(label)


print("[상황 판단 — 가이드라인 ④ 문장 틀]")
c = recs.classify("가성비 좋은 치킨 넷이 시키자")
ok(c["read"] == "가격" and c["confidence"] == "상" and c["line"] == "\"가성비\"라고 하셔서 '가격' 위주로 골랐어요.", f"직접 말함(상): {c['line']}  (ex-035)")
c = recs.classify("월말이라 거지다 넷이 치킨 시키자 6만원 안에서")
ok(c["read"] == "가격" and c["confidence"] == "중" and c["line"] == "월말이라 '가격' 쪽으로 봤어요.", f"상황 단서(중): {c['line']}  (ex-034)")
c = recs.classify("민재 생일인데 싸게 시키자")
ok(c["read"] == "가격" and c["read2"] == "품질" and c["confidence"] == "중" and c["line"] == "생일이지만 \"싸게\"라고 하셔서 '가격'을 먼저 봤어요.",
   f"신호 부딪힘(중): {c['line']}  (ex-039)")
c = recs.classify("아무거나 시켜줘 우리 넷 8만")
ok(c["read"] == "판단 없음" and c["confidence"] == "하", f"판단 없음(하): {c['line']}  (ex-045)")
ok(recs.classify("더 싸게 다시 골라 줘")["read"] == "가격" and recs.classify("안 해본 걸로 다시 골라 줘")["read"] == "경험",
   "목적 버튼이 보내는 말을 다시 읽으면 그 목적 (다시 고르기)")
for q, want in [("배고파 넷이 뭐 먹지", "\"배고파\"라고 하셔서 '양' 쪽으로 봤어요."),
                ("돈이 없어서 넷이 치킨 시키자", "\"돈이 없어서\"라고 하셔서 '가격' 쪽으로 봤어요."),
                ("맨날 먹던 거 말고 넷이", "\"맨날\"이라고 하셔서 '경험' 쪽으로 봤어요."),
                ("푸짐하게 넷이 먹자", "\"푸짐\"이라고 하셔서 '양' 위주로 골랐어요.")]:
    ok(recs.classify(q)["line"] == want, f"버그 검수 ①: 문장 문법 — {recs.classify(q)['line']}")
ok(recs.domain_of("넷이 치킨 시키자") == "음식·배달" and recs.domain_of("부산 숙소 추천") == "여행" and recs.domain_of("선물 사자") == "물품", "도메인")

print("[⑤ 확신도별 후보 구성]")
ok(recs.composition(recs.classify("가성비 좋은 치킨")) == "후보 3개 중 2개는 '가격' 방향, 1개는 다른 방향", "상 → 1순위 2개 + 2순위 1개")
ok(recs.composition(recs.classify("민재 생일인데 싸게")) == "후보 3개를 '가격' 1개 · '품질' 1개 · 나머지 방향 1개로", "중 → 1·2순위·나머지 1개씩")
ok(recs.composition(recs.classify("아무거나")) == "후보 3개를 가격·양·품질·경험 중 서로 다른 방향으로", "하 → 모두 다른 방향")

print("[추천 답에 rec 붙이기 + 피드백 API]")
from starlette.testclient import TestClient  # noqa: E402
from backend.app import app  # noqa: E402
run = uuid.uuid4().hex[:4]
email = f"rec.{run}@t.test"
code = service.send_code(email, "signup")["dev_code"]
u = service.signup("김민재", email, "pass1234", code=code)
tok = u.get("token") or service.login(email, "pass1234")["token"]
H = {"Authorization": f"Bearer {tok}"}
_real_turn = service._chat_turn
def _fake_turn(message, history, context, chat_id, user):     # Pie 추천 결과(후보 3개)를 고정 — AI·검색 없이 /api/chat 경로 전체를 확인
    return {"messages": [{"from": "bot", "intent": "shop", "text": "월말이라 '가격' 쪽으로 봤어요. 후보 3개예요.",
                          "compare": ["c1", "c2", "c3"], "n": 4, "best": "c1",
                          "products": {"c1": {"name": "BBQ 황금올리브 가성비 세트"}, "c2": {"name": "푸짐한 치킨 대용량 2마리"},
                                       "c3": {"name": "이색 신메뉴 치킨"}}}]}
service._chat_turn = _fake_turn
with TestClient(app) as cli:
    d = cli.post("/api/chat", json={"message": "월말이라 거지다 넷이 치킨 시키자 6만원 안에서", "chat_id": "c1", "user": u.get("short"), "history": [], "context": {}}, headers=H).json()
    d = d.get("data", d)
    m = next((x for x in d.get("messages") or [] if x.get("compare")), None)
    ok(m is not None and (m.get("rec") or {}).get("rec_id", "").startswith("r_"), f"추천 답에 rec_id ({(m or {}).get('rec', {}).get('rec_id')})")
    if m:
        rec = m["rec"]
        ok(rec["situation"]["read"] == "가격" and rec["situation"]["line"] == "월말이라 '가격' 쪽으로 봤어요." and rec["situation"]["domain"] == "음식·배달",
           f"situation: {rec['situation']}")
        ok([x["kind"] for x in rec["shown"]] == ["가격", "양", "경험"], f"후보별 성격(가성비·대용량·이색): {rec['shown']}")
        ok([b["label"] for b in m.get("recButtons") or []] == ["더 싸게", "더 많이", "더 좋게", "안 해본 걸로"], "목적 버튼 4개 (화면 순서)")
        rid, cid = rec["rec_id"], rec["shown"][0]["id"]
        post = lambda b: cli.post("/api/pie/feedback", json={"rec_id": rid, **b}, headers=H)
        r1 = post({"event": "choose", "candidate": cid})
        ok(r1.status_code == 200 and r1.json()["data"]["score"] in (0, 1), f"choose → {r1.status_code} score {r1.json().get('data', {}).get('score')}")
        r2 = post({"event": "correct", "purpose": "양"})
        ok(r2.status_code == 200 and r2.json()["data"]["score"] == -1, "correct(목적 버튼) → -1점, 정답 목적 확정")
        r3 = post({"event": "rate", "satisfaction": 4})
        ok(r3.status_code == 200 and r3.json()["data"]["score"] == 0.5, "rate 4점 → +0.5")
        r4 = post({"event": "rate", "satisfaction": 2})
        ok(r4.status_code == 200 and r4.json()["data"].get("duplicate"), "같은 사람의 두 번째 만족도는 무시 (한 번만)")
        bad = [post({"event": "choose", "candidate": "없는후보"}).status_code, post({"event": "correct", "purpose": "맛"}).status_code,
               post({"event": "rate", "satisfaction": 9}).status_code, post({"event": "shout"}).status_code,
               cli.post("/api/pie/feedback", json={"rec_id": "r_nope", "event": "rate", "satisfaction": 3}, headers=H).status_code,
               cli.post("/api/pie/feedback", json={"rec_id": rid, "event": "rate", "satisfaction": 3}).status_code]
        ok(bad[:4] == [400, 400, 400, 400] and bad[4] == 404 and bad[5] in (401, 403), f"잘못된 값 거절 {bad}")
        email2 = f"rec2.{run}@t.test"
        u2 = service.signup("이진주", email2, "pass1234", code=service.send_code(email2, "signup")["dev_code"])
        H2 = {"Authorization": f"Bearer {u2.get('token') or service.login(email2, 'pass1234')['token']}"}
        sc = [cli.post("/api/pie/feedback", json={"rec_id": rid, "event": e, **x}, headers=H2).status_code
              for e, x in (("choose", {"candidate": cid}), ("correct", {"purpose": "가격"}))]
        ok(sc == [403, 403] and not store.kv_get("rec_prefs", u2.get("short")), f"버그 검수 ③: 남의 추천에 선택·정정 불가 {sc}")
        saved = store.kv_get("recs", rid)
        ok([e["event"] for e in saved["events"]] == ["choose", "correct", "rate"], "같은 rec_id로 세 사건이 묶임")

print("[④ 사례 꺼내기 — 목적 버튼으로 고친 목적을 다음 추천의 단서로]")
if m:
    c = recs.classify("넷이 뭐 시켜 먹을까", prefer=recs.preferred(u.get("short"), "음식·배달"))
    ok(c["read"] == "양" and c.get("from_case") and c["line"] == "지난번에 '양' 쪽을 고르셔서 '양' 쪽으로 봤어요.", f"같은 분야 · 신호 없음 → {c['line']}")
    c = recs.classify("가성비로 시켜 먹자", prefer="양")
    ok(c["read"] == "가격", "이번에 직접 말한 목적이 지난 사례보다 먼저")

print("[기록 파일 — 비식별]")
p = config.DATA_DIR / "pie_feedback.jsonl"
rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []
ok([r["event"] for r in rows][-4:] == ["shown", "choose", "correct", "rate"], f"data/pie_feedback.jsonl: {[r['event'] for r in rows]}")
blob = p.read_text(encoding="utf-8") if p.exists() else ""
ok(email not in blob and "김민재" not in blob and all(r.get("uid") for r in rows), "이메일·이름 없이 uid로만")
bp = beta.DIR / "pie_feedback.jsonl"
ok(beta.enabled() and bp.exists() and len(bp.read_text(encoding="utf-8").splitlines()) == len(rows), "베타 데이터 폴더에도 같은 기록 (묶어 보낼 때 포함)")

print("[추천에서 만든 정산방이 추천을 기억]")
g = service.group_create(u.get("short") or "민재", {"id": "g" + run, "name": "치킨 공동주문", "members": [u.get("short") or "민재", "진주"], "recId": rid if m else "r_x"})
got = store.kv_get("groups", "g" + run) or {}
ok(got.get("recId") == (rid if m else "r_x"), "그룹에 recId 저장 (정산 기록·그룹 카드로 이어짐)")
view = service._room_view(got, u.get("short"))
ok(view.get("recId") == (rid if m else "r_x") and view.get("recRated") is bool(m), "버그 검수 ④⑧: 방 정보에 recId · 이미 매긴 만족도(recRated)가 화면으로 감")
import inspect  # noqa: E402
ok('"recId": rec.get("rec_id")' in inspect.getsource(service.public) and '"rec_id": ((store.kv_get("groups", group_id)' in inspect.getsource(service.propose),
   "정산 만들 때 방의 recId를 기록 · 정산 공개 정보에 recId (그룹 카드 만족도)")
service._chat_turn = _real_turn

print("\n✓ 전체 통과" if not fails else f"\n✗ 실패 {len(fails)}건")
sys.exit(1 if fails else 0)
