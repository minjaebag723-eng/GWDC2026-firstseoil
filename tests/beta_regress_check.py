"""베타에서 👎 받은 실제 사례로 만든 회귀 검사 (AI 없이 도는 부분: 계산 엔진 · 질문 안전장치 · 태그 규칙).
실행: DATA_DIR=/tmp/sp-br LLM_MODE=mock CHAIN_MODE=mock KILN_API_KEY= python tests/beta_regress_check.py
실제 Kiln으로 답 전체를 보는 검사는 tests/beta_regress.jsonl (live) — 서버 PC에서.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent import settlement, brain

fails = []
def ok(c, label):
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c: fails.append(label)

def shares(r): return dict(r.get("shares") or [])

_real = settlement.llm.client.call_tool
def as_ai(rule):
    """실제 Kiln이 돌려주는 해석 결과를 흉내 (테스트는 AI 없이 돌기 때문) — 계산·자리 이름·안전장치 경로를 그대로 탄다."""
    base = {"total_amount": None, "amount_parts": [], "members": [], "adjustments": [], "missing": [], "question": None, "payer": None, "per_person_amount": None,
            "per_person_cap": None, "total_cap": None, "round_unit": None, "items": [], "subject": None, "purpose": None, "prohibited": False}
    base.update(rule)
    settlement.llm.client.call_tool = lambda *a, **k: (dict(base), {"stage": "settlement.analyze", "mode": "tools", "total_tokens": 0})

print("[1:1 나누기 — 인원만 있으면 이름을 묻지 않고 계산]")
as_ai({"amount_parts": [20000, 18000, 3000], "members": ["민재"], "adjustments": [{"name": "민재", "kind": "less", "value": 5000}]})
r = settlement.calculate(text="치킨 2만 피자 1.8만 배달비 3천 넷이 나누는데 민재는 5천원 덜 내게 해줘", members=[], payer="가온", fill_unnamed=True)
s = shares(r)
ok(r["status"] == "ok" and len(s) == 4 and sum(s.values()) == 41000, f"4명 · 합계 41,000원 → {r['status']} {s}")
others = [v for k, v in s.items() if k != "민재"]
ok("민재" in s and all(v - s["민재"] == 5000 for v in others), "민재만 5,000원 덜")
ok(not any("누구" in (x or "") for x in [r.get("question")]), "'누구인가요' 되묻기 없음")

as_ai({"amount_parts": [38000, 3000], "members": ["나"], "adjustments": [{"name": "나", "kind": "less", "value": 5000}]})
r = settlement.calculate(text="4명 3만8천원 +배달비 3천인데 나는 5천원 덜 내게 해줘", members=[], payer="가온", fill_unnamed=True)
s = shares(r)
ok(r["status"] == "ok" and "나" in s and len(s) == 4 and sum(s.values()) == 41000, f"'나' 포함 4명 · 41,000원 → {r['status']} {s or r.get('question')}")
if "나" in s:
    ok(all(v - s["나"] == 5000 for k, v in s.items() if k != "나"), "나만 5,000원 덜")

settlement.llm.client.call_tool = _real
r = settlement.calculate(text="한정식 15만원인데 부가세 10% 별도래 여섯이 나눠줘", members=[], payer="가온", fill_unnamed=True)
s = shares(r)
ok(r["status"] == "ok" and len(s) == 6 and sum(s.values()) == 165000 and set(s.values()) == {27500}, f"부가세 포함 165,000원 · 6명 1인 27,500원 → {r['status']} {sorted(set(s.values()))}")

print("[버그 검수 ② — 조정 금액과 같은 금액의 진짜 항목은 빼지 않음]")
as_ai({"amount_parts": [20000, 5000], "members": ["민재"], "adjustments": [{"name": "민재", "kind": "less", "value": 5000}]})
r = settlement.calculate(text="치킨 2만 피자 5천 넷이 나누는데 민재는 5천원 덜 내게 해줘", members=[], payer="가온", fill_unnamed=True)
ok(r.get("total") == 25000, f"치킨 2만 + 피자 5천 = 25,000원 (민재 5천원 덜과 헷갈리지 않음) → {r.get('total')}")
settlement.llm.client.call_tool = _real

print("[그룹방은 그대로 — 실제 멤버가 필요하니 인원이 모자라면 묻기]")
r = settlement.calculate(text="치킨 4만원 넷이 똑같이 나눠줘", members=["가온", "민재"], payer="가온")
ok(r["status"] == "need_info" and "members" in r.get("missing", []), f"그룹 경로(자리 이름 끔) → {r['status']} · {r.get('question')}")

print("[AI가 계산식을 넣어 되물어도 사용자에게는 안 나감]")
as_ai({"amount_parts": [20000, 18000, 3000], "missing": ["vague"], "question": "총액이 20000 + 18000 + 3000 = 3만 1천원인가요? 참여자는 넷이 맞나요?"})
r = settlement.calculate(text="치킨 2만 피자 1.8만 배달비 3천 넷이 나누는데 가온은 5천원 덜 내게 해줘", members=[], payer="가온", fill_unnamed=True)
ok("3만 1천" not in (r.get("question") or "") and "+" not in (r.get("question") or ""), f"틀린 합계 질문 차단 → '{r.get('question')}'")
settlement.llm.client.call_tool = _real

print("[되묻기 질문 안전장치 — 금액은 코드만 말한다]")
text = "치킨 2만 피자 1.8만 배달비 3천 넷이 나누는데"
ok(settlement._safe_question("총액이 20000 + 18000 + 3000 = 3만 1천원인가요?", text, ["total_amount"]) is None, "계산식이 든 질문은 버림 (베타 👎)")
ok(settlement._safe_question("합계가 4만 5천원인가요?", text, ["vague"]) == "모호한 조건이 있어요. 정확한 금액이나 비율로 알려 주세요.", "문장에 없는 금액이 든 질문 → 정해진 문장")
ok(settlement._safe_question("배달비 3천원도 넷이 나누나요?", text, ["vague"]) == "배달비 3천원도 넷이 나누나요?", "문장에 있던 금액만 쓴 질문은 그대로")
ok(settlement._safe_question("몇 명이서 나누나요?", text, ["members"]) == "몇 명이서 나누나요?", "숫자 없는 질문은 그대로")

print("[태그 — 이어지는 추천 요청이 '주제 밖'으로 빠지지 않게]")
for t, want in [("다른거는 없어? 옷 종류로", "shop"), ("아니 3개를 알려줘", "shop"), ("황올을 인당 1개씩 해서 4개를 사는거야?", "shop"),
                ("비슷한 상품 4명 기준으로 찾아줘", "shop"), ("아 총액 32만원이었어", "settle_change")]:  # noqa
    tags = brain.tags_for(t, "chat", has_history=True)
    ok(want in tags, f"'{t}' → {tags}")

ok("shop" not in brain.tags_for("이거 넷이 똑같이 나눠줘", "chat", has_history=True), "버그 검수 ⑥: 추천 뒤 '이거 넷이 똑같이 나눠줘'는 추천이 아님")

print("[그룹방 진행 상황 질문 — 가이드라인 평가 ev-026·028·033]")
from agent import service
for t in ["아직 누구 남음?", "이거 끝났어?", "내가 뭘 해야 해?"]:
    ok(service.pie_should_reply(t, [], "지현", active=True)[0], f"정산 중인 방: '{t}' → 답함")
ok(not service.pie_should_reply("수업 끝났어?", [], "지현", active=False)[0], "정산 없는 방의 잡담 '수업 끝났어?' → 끼어들지 않음")
ok(not service.pie_should_reply("ㅋㅋ 오늘 날씨 좋다", [], "지현", active=True)[0], "정산 중이어도 잡담은 넘김")

print("[베타 2차 G1 — 도구 호출을 글자로 쓴 답]")
from agent import assistant, llm
ok(assistant.text_tool_call('menu_price_search(food="치킨")') == {"name": "menu_price_search", "arguments": {"food": "치킨"}}, "글자 도구 호출 알아봄")
ok((assistant.text_tool_call('<tool_call>{"name": "search_products", "arguments": {"query": "선물"}}</tool_call>') or {}).get("name") == "search_products", "<tool_call> JSON 형식도")
ok(assistant.text_tool_call("치킨으로 찾아볼게요.") is None and assistant.clean('menu_price_search(food="피자")') == "", "보통 문장은 그대로 · 도구 글자는 답에서 숨김")
seq = [{"content": 'menu_price_search(food="치킨")', "tool_calls": []}, {"content": "치킨 가격을 찾아봤어요.", "tool_calls": []}]
_step = llm.client.agent_step
llm.client.agent_step = lambda *a, **k: (seq.pop(0), {"stage": "assistant.step", "mode": "tools", "total_tokens": 0})
ran = []
_rt = assistant.Session.run_tool
assistant.Session.run_tool = lambda self, name, args: (ran.append((name, args)), {"results": []})[1]
try:
    out = assistant.run("배달음식 먹고싶은데 추천해줘", [], user="가온", flow="t-g1", metas=[])
finally:
    llm.client.agent_step, assistant.Session.run_tool = _step, _rt
ok(ran == [("menu_price_search", {"food": "치킨"})] and "menu_price_search" not in out["text"], f"실제 도구로 실행 · 답: {out['text']!r}")

print("[베타 2차 G2 — 'Pie: Pie:' 말머리]")
ok(assistant.clean("Pie: Pie: Pie: 가온님, 확인해 주세요.") == "가온님, 확인해 주세요." and assistant.clean("파이: 네") == "네", "말머리 제거")

print("[베타 2차 G3·G7 — 직전에 정산을 물었어도 엉뚱한 말은 조건 아님]")
recent = [{"pie": True, "ask": "settle", "text": "정확한 금액을 알려주세요"}]
for t, want in [("그거", False), ("홈화면에 있는", False), ("생일선물 추천", False), ("나래 5천원 덜", True), ("2만원", True), ("진이가 다 낼거야", True)]:
    ok(service._pie_is_condition(t, "followup", recent) is want, f"'{t}' → {'조건' if want else '조건 아님'}")

print("[베타 2차 G4 — 그룹방 '내가 40%를 송금' = 말한 사람 몫]")
ok(settlement.self_to_name("5만원 중에 내가 40%를 나래에게 내야돼", "가온", ["가온", "나래"]) == "5만원 중에 가온가 40%를 나래에게 내야돼", "'내가' → 말한 사람")
ok(settlement.self_to_name("나래랑 나랑 둘이서 나눠", "가온", ["가온", "나래"]) == "나래랑 가온랑 둘이서 나눠", "'나랑' → 말한 사람 · '나래'·'나눠'는 그대로")
q = "나래가 5만원을 냈는데 내가 나래한테 40%를 송금해야돼"
as_ai({"amount_parts": [50000], "total_percent": 40, "pct_type": "portion", "members": ["나래"], "payer": "나래"})   # 베타의 잘못 읽은 해석
r = settlement.calculate(text=q, members=["가온", "나래"], payer="나래", speaker="가온")
ok(r["status"] == "ok" and dict(r["shares"]) == {"가온": 20000, "나래": 30000}, f"AI가 총액의 %로 읽어도 → 가온 20,000 · 나래 30,000: {r.get('shares') or r.get('question')}")
settlement.llm.client.call_tool = _real
r = settlement.calculate(text=q, members=["가온", "나래"], payer="나래", speaker="가온")
ok(r["status"] == "ok" and dict(r["shares"]) == {"가온": 20000, "나래": 30000}, f"AI 없이(코드)도 → {r.get('shares') or r.get('question')}")

r = settlement.calculate(text="10만원 가온 40% 나래 40% 진이 20%", members=["가온", "나래", "진이"], payer="가온")
ok(r["status"] == "ok" and dict(r["shares"]) == {"가온": 40000, "나래": 40000, "진이": 20000}, f"여러 사람이 각자 %를 내면 그대로: {r.get('shares') or r.get('question')}")

print("[라이브 QA — 경로 판단: 금액 + 인원 + 나누기 말은 계산]")
for q, want in [("삼겹살 38,900원 넷이 똑같이 나눠줘", "settle"), ("숙소 30만원 넷이 나눠줘", "settle"),
                ("한정식 15만원인데 부가세 10% 별도래 여섯이 나눠줘", "settle"), ("4명 3만8천원 +배달비 3천인데 나는 5천원 덜 내게 해줘", "settle"),
                ("넷이 치킨 6만원 안에서", "shop"), ("월말이라 거지다 넷이 치킨 시키자 6만원 안에서", "shop"), ("부산 숙소 추천해줘 넷이 60만원", "shop")]:
    got = service._route(q, [], "t-route", use_llm=False)[0]
    ok(got == want, f"'{q}' → {got}")

print("[라이브 QA — 조건에 나온 이름은 참여자 (민재 없이 친구1~4)]")
as_ai({"amount_parts": [20000, 18000, 3000], "members": [], "adjustments": [{"name": "민재", "kind": "less", "value": 5000}]})
r = settlement.calculate(text="치킨 2만 피자 1.8만 배달비 3천 넷이 나누는데 민재는 5천원 덜 내게 해줘", members=[], payer="QA하나", fill_unnamed=True)
s = dict(r.get("shares") or [])
ok(len(s) == 4 and "민재" in s and all(v - s["민재"] == 5000 for k, v in s.items() if k != "민재"), f"민재 포함 4명 · 5천원 덜: {s}")
as_ai({"amount_parts": [50000], "members": [], "missing": ["vague"], "question": "민재님, 진주님이 얼마나 더 내면 될까요?"})
r = settlement.calculate(text="총 5만원인데 진주는 조금 더 내게 해줘", members=[], payer="QA하나", fill_unnamed=True)
ok(not (r.get("question") or "").startswith("민재님"), f"되묻기 질문에 엉뚱한 호칭 없음: {r.get('question')}")
settlement.llm.client.call_tool = _real

print("[라이브 QA — 나누기 도구: '4명'인데 1명으로 계산하지 않음]")
sess = assistant.Session("t-split", [])
sess.text = "4명 3만8천원 +배달비 3천인데 똑같이 나눠줘"
out = sess.split_cost(total=41000, members=["QA하나"])
ok(len(out["shares"]) == 4 and out["sum"] == 41000, f"4명: {[(x['name'], x['amount']) for x in out['shares']]}")

print("[라이브 QA — AI 답 안전장치]")
sess = assistant.Session("t-guard", [])
msgs = [{"role": "system", "content": "x"}, {"role": "user", "content": "🍕🍕🍕"}]
ok(assistant._guard_final("피자 3판이에요. 도미노 피자 12인치 (29,000원) · 파파존스 (31,000원)", sess, msgs, "t") == assistant.SAFE_ASK, "검색 없이 지어낸 가격 → 되묻기")
ok(assistant._guard_final("인기 있는 치킨, 디저트, 피자를 하나씩 넣었고 1인 비용을 붙였어요.", sess, [{"role": "system", "content": ""}, {"role": "user", "content": "배달음식 추천해줘"}], "t") == assistant.SAFE_ASK,
   "카드 없이 '넣었어요' → 되묻기")
ok(assistant._guard_final("삼겹살 38,900원을 네 분이 나눠요.", sess, [{"role": "system", "content": ""}, {"role": "user", "content": "삼겹살 38,900원 넷이"}], "t") == "삼겹살 38,900원을 네 분이 나눠요.",
   "사용자가 말한 금액은 그대로")
sess = assistant.Session("t-guard2", []); sess.used = {"split_cost"}; sess.last_split = [("가", 27500), ("나", 27500)]
ok("1인 27,500원" in assistant._guard_final("여섯 명이 나누는 조건으로 계산했어요. 확인해 주세요.", sess, [{"role": "system", "content": ""}], "t"), "나누기 결과 금액이 빠지면 덧붙임")

print("[라이브 QA — 여행 도구: 날짜를 말하지 않았거나 이미 금액이 있는 나누기면 검색 안 함]")
sess = assistant.Session("t-travel", []); sess.text = "다음 주에 강릉 숙소 추천해줘"; sess.hist = []
ok(sess.travel_price_search(kind="숙소", destination="강릉", check_in="2026-10-12", check_out="2026-10-15").get("need") == "날짜", "'다음 주에' → 날짜 묻기 (AI가 날짜를 정해도)")
sess.text = "숙소 30만원 넷이 나눠줘"
ok("split_cost" in (sess.travel_price_search(kind="숙소", destination="숙소", check_in="2026-10-12", check_out="2026-10-14").get("note") or ""), "'숙소 30만원 넷이 나눠줘' → 검색 대신 나누기")

print("[라이브 QA — 추천 답의 첫 문장은 상황 한 줄 (코드)]")
_rt = service._chat_turn
service._chat_turn = lambda *a, **k: {"messages": [{"from": "bot", "intent": "shop", "text": "예산·인원에 맞는 조합 2개를 찾았어요.", "compare": ["c1", "c2"],
                                                     "products": {"c1": {"name": "가성비 세트"}, "c2": {"name": "푸짐한 세트"}}}]}
try:
    m = service.chat("월말이라 거지다 넷이 치킨 시키자 6만원 안에서", [], {}, "t-line", "QA하나")["messages"][0]
finally:
    service._chat_turn = _rt
ok(m["text"].startswith("월말이라 '가격' 쪽으로 봤어요."), f"첫 문장: {m['text'][:40]}")

print("[라이브 QA — 그룹방 '지금보다 2천원 더' (규칙 모드)]")
import uuid as _u
gid = "gqa" + _u.uuid4().hex[:8]
service.group_create("QA하나", {"id": gid, "name": "t", "members": ["QA하나", "큐에이하나", "큐에이둘"]})
def gsay(t):
    mid = "m" + _u.uuid4().hex[:8]
    service.group_message("QA하나", gid, {"id": mid, "from": "QA하나", "text": t})
    return service.group_pie("QA하나", gid, mid) or []
o1 = gsay("파이야 6만원 셋이 나누는데 큐에이하나는 5천원 덜 내게 해줘")
c1 = next((x for x in o1 if x.get("analysis")), None)
ok(c1 and dict(c1["analysis"]["shares"]).get("큐에이하나") == 16667, f"처음: {c1 and c1['analysis']['shares']}")
o2 = gsay("파이야 큐에이하나가 지금보다 2천원 더 내게 해줘")
c2 = next((x for x in o2 if x.get("analysis")), None)
sh = dict(c2["analysis"]["shares"]) if c2 else {}
ok(sh.get("큐에이하나") == 18667 and sum(sh.values()) == 60000, f"지금보다 2천원 더 → 큐에이하나 18,667원: {sh or [x.get('text') for x in o2]}")

print("[라이브 QA 2차]")
ok(service._route("아 총액 32만원이었어", [{"role": "bot", "intent": "settle", "text": "1인 75,000원"}], "t", use_llm=False)[0] == "settle", "R1: 계산 뒤 '총액 32만원이었어' → 계산 엔진")
q = service._ask_1on1("총 5만원인데 진주는 조금 더 내게 해줘", {"question": "총 금액과 참여자 이름을 알려주세요."})
ok(q == "몇 명이서 나누나요? 진주님은 얼마나 더(덜) 낼까요? 예: '5천원 더'", f"R3: 1:1 되묻기 — {q}")
seq = [{"content": "프리미엄 스테이크 세트 인당 24,000원 어때요?", "tool_calls": []},
       {"content": "", "tool_calls": [{"id": "t1", "name": "menu_price_search", "args": {"food": "치킨"}}]},
       {"content": "찾아본 메뉴로 다시 알려 드릴게요.", "tool_calls": []}]
_step = llm.client.agent_step
llm.client.agent_step = lambda *a, **k: (seq.pop(0) if seq else {"content": "찾아본 메뉴로 다시 알려 드릴게요.", "tool_calls": []}, {"stage": "assistant.step", "mode": "tools", "total_tokens": 0})
ran = []
_rt = assistant.Session.run_tool
assistant.Session.run_tool = lambda self, name, args: (ran.append(name), self.used.add(name), {"results": []})[2]
try:
    out = assistant.run("민재 생일인데 제대로 된 걸로 시키자 넷이 10만원", [], user="QA셋", flow="t-r2", metas=[])
finally:
    llm.client.agent_step, assistant.Session.run_tool = _step, _rt
ok(ran == ["menu_price_search"] and "24,000" not in out["text"], f"R2: 지어낸 추천 → 도구로 다시 찾게 · 답: {out['text']!r}")
sess = assistant.Session("t-r4", []); sess.need = "날짜"
ok(assistant._guard_final("다음 주를 10월 7일부터 10일로 가정하고 찾았어요.", sess, [{"role": "system", "content": ""}], "t") == assistant.ASK_DATE, "R4: 날짜를 모르면 검색한 척 대신 날짜 묻기")
sess = assistant.Session("t-r1b", []); sess.text = "아 총액 32만원이었어 넷이 나눠"
ok(assistant._guard_final("1인 80,000원이에요.", sess, [{"role": "system", "content": ""}, {"role": "user", "content": sess.text}], "t") == assistant.SAFE_SETTLE, "나누기 요청에서 근거 없는 금액 → 계산 안내 문장")

print("[실측 벤치 (qwen3-32b) — 결과 동일성 표에서 나온 것]")
M4 = ["벤치", "진주", "민재", "지현"]
as_ai({"amount_parts": [], "per_person_amount": 80000, "missing": ["total_amount"]})
r = settlement.calculate(text="8만원 넷이 똑같이 나눠", members=M4, payer="벤치", speaker="벤치")
ok(r["status"] == "ok" and sum(a for _, a in r["shares"]) == 80000, f"'8만원 넷이' → 총액 80,000원 (AI가 1인 8만원으로 읽어도): {r.get('shares')}")
as_ai({"amount_parts": [], "per_person_amount": 80000, "missing": ["total_amount"]})
r = settlement.calculate(text="1인 8만원씩 넷이 나눠", members=M4, payer="벤치", speaker="벤치")
ok(r["status"] == "ok" and sum(a for _, a in r["shares"]) == 320000, "'1인 8만원씩'은 그대로 1인 금액 (320,000원)")
as_ai({"amount_parts": [38900], "members": ["모든 사람"]})
r = settlement.calculate(text="삼겹살 38,900원 넷이 똑같이 나눠줘", members=[], payer="벤치", fill_unnamed=True)
ok(r["status"] == "ok" and len(r["shares"]) == 4 and all(n != "모든 사람" for n, _ in r["shares"]), f"'모든 사람'은 참여자 이름이 아님: {r.get('shares')}")
settlement.llm.client.call_tool = _real
t1 = service.chat("숙소 30만원 넷이 나눠줘", [], {}, "t-s04", "벤치")
h = [{"role": "user", "text": "숙소 30만원 넷이 나눠줘"}] + [{"role": "bot", "text": m.get("text", ""), "intent": m.get("intent"), "needs_info": bool(m.get("needs_info"))} for m in t1["messages"]]
t2 = service.chat("아 총액 32만원이었어", h, {}, "t-s04", "벤치")
sp = next((m.get("split") for m in t2["messages"] if m.get("split")), None)
ok(sp and len(sp) == 4 and sum(a for _, a in sp) == 320000, f"S04 조건 변경: 앞 대화의 '넷이' → 4명 · 320,000원 ({sp or t2['messages'][0].get('text')})")
ok(settlement._simple_split("파이야 8만원 넷이 똑같이 나눠", M4, None, ["파이야"]), "이전 말이 이름 부르기뿐이면 단순 나누기(E2) 그대로")
ok(not settlement._simple_split("아 총액 32만원이었어 넷이 나눠", [], None, ["숙소 30만원 넷이 나눠줘"]), "이전 말에 금액이 있으면(조건 변경) AI")

print("\n✓ 전체 통과" if not fails else f"\n✗ 실패 {len(fails)}건")
sys.exit(1 if fails else 0)
