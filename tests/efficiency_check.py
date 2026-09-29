"""토큰 효율 설계(E1~E6) 검사 — AI 없이. 효율 스위치를 켜고 끄며 설계대로 줄어드는지, 계산 결과는 같은지.
실행: DATA_DIR=/tmp/sp-eff LLM_MODE=mock CHAIN_MODE=mock KILN_API_KEY= python tests/efficiency_check.py
(실제 Kiln으로 단계별 토큰을 비교하는 건 tests/token_bench.py)
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent import assistant, brain, config, service, settlement  # noqa: E402

fails = []


def ok(c, label):
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c:
        fails.append(label)


names = lambda ts: sorted(t["name"] for t in ts)
config.PIE_EFFICIENT = True
print("[E1 요청 종류별 도구]")
ok(names(assistant.tools_for("넷이 치킨 시키자 6만원 안에서")) == ["check_delivery_combos", "menu_price_search", "web_search"], "음식 → 메뉴 검색·조합·웹")
ok(names(assistant.tools_for("10월 3일부터 2박 부산 숙소")) == ["travel_price_search", "web_search"], "여행 → 여행 검색·웹")
ok(names(assistant.tools_for("친구 생일 선물 사자 넷이 10만원")) == ["search_products", "web_search"], "물건 → 상품 검색·웹")
ok(assistant.tools_for("AI 요금제는 어떻게 돼?") == [] and assistant.tools_for("안녕") == [], "사용법·인사 → 도구 없음")
ok(len(assistant.tools_for("너가 알아서 추천해줘")) == len(assistant.TOOLS), "무엇을 찾는지 모르면 전부 (정확도 먼저)")
ok(names(assistant.tools_for("다른 거는 없어?", [{"role": "user", "text": "넷이 치킨 6만원"}])) == ["check_delivery_combos", "menu_price_search", "web_search"], "이어지는 말은 최근 대화로 판단")
full = len(str(assistant.TOOLS)); food = len(str(assistant.tools_for("넷이 치킨 시키자")))
ok(food < full * 0.6, f"도구 설명 글자 {full:,} → {food:,} ({(food - full) / full:+.0%})")

print("[E2 단순 나누기는 코드 해석 · E3 문장 틀 설명]")
S = settlement._simple_split
ok(S("삼겹살 38,900원 넷이 똑같이 나눠줘", [], None, None), "금액·인원·나누기만 → 코드")
for t in ("치킨 2만 넷이 나누는데 민재는 5천원 덜", "15만원 부가세 10% 여섯이 나눠", "8만원 넷이 나누는데 1인 1만5천원 넘으면 안 돼", "총 5만원 진주는 조금 더", "3만원 진주랑 민재랑 셋이 나눠"):
    ok(not S(t, [], None, None), f"조건·이름이 있으면 AI: '{t}'")
ok(not S("아 총액 32만원이었어 넷이 나눠", [], None, ["숙소 30만원 넷이"]), "이전 대화가 있으면(조건 변경) AI")
r = service.chat("삼겹살 38,900원 넷이 똑같이 나눠줘", [], {}, "e-s01", "효율")
m = r["messages"][0]
ok(m.get("split") and [a for _, a in m["split"]] == [9725, 9725, 9725, 9725], f"결과: {m.get('split')}")
ok("1인 9,725원" in m.get("text", ""), f"문장 틀 설명: {m.get('text', '')[:50]}")
stages = {x.get("stage"): x.get("mode") for x in (r.get("usage") or {}).get("steps", [])} if isinstance(r.get("usage"), dict) else {}
calc = settlement.calculate(text="삼겹살 38,900원 넷이 똑같이 나눠줘", members=[], payer="효율", fill_unnamed=True)
ok(calc["metas"][0].get("mode") == "code" and calc["metas"][0].get("total_tokens", 0) == 0, "정산 해석 단계: 코드 (0 토큰)")
ex_text, ex_meta = settlement.explain(calc, None)
ok(ex_meta.get("mode") == "code", "결과 설명 단계: 코드 (0 토큰)")
config.PIE_EFFICIENT = False
calc0 = settlement.calculate(text="삼겹살 38,900원 넷이 똑같이 나눠줘", members=[], payer="효율", fill_unnamed=True)
ok(calc0["metas"][0].get("mode") != "code" and calc0["shares"] == calc["shares"], "효율을 끄면 AI 해석 · 분담표는 같음")
config.PIE_EFFICIENT = True

print("[E4 그룹방 이름만 부르기]")
gid = "geff" + uuid.uuid4().hex[:8]
service.group_create("효율", {"id": gid, "name": "t", "members": ["효율", "진주"]})
mid = "m" + uuid.uuid4().hex[:8]
service.group_message("효율", gid, {"id": mid, "from": "효율", "text": "파이야"})
out = service.group_pie("효율", gid, mid) or []
ok(out and "한 문장" in out[0]["text"] and "0 토큰" in (out[0].get("meta") or "") or (out and "code" in (out[0].get("meta") or "")), f"코드 안내: {out and out[0]['text'][:40]}")

print("[E5·E6 프롬프트]")
config.PIE_EFFICIENT = False
p0, m0 = brain.compose("chat", tool_rules="", situation=[], text="넷이 치킨 시키자 6만원 안에서")
h0 = assistant._history_messages([{"role": "user", "text": "가" * 500}] * 10)
config.PIE_EFFICIENT = True
p1, m1 = brain.compose("chat", tool_rules="", situation=[], text="넷이 치킨 시키자 6만원 안에서")
h1 = assistant._history_messages([{"role": "user", "text": "가" * 500}] * 10)
ok(len(m1["examples"]) <= 2 and len(m1["knowledge"]) <= 1 and len(p1) < len(p0), f"예시 {len(m0['examples'])}→{len(m1['examples'])} · 지식 {len(m0['knowledge'])}→{len(m1['knowledge'])} · 프롬프트 {len(p0):,}→{len(p1):,}자")
ok(len(h1) == 6 and len(h1[0]["content"]) == 300 and len(h0) == 8, f"대화 기록 {len(h0)}개×{len(h0[0]['content'])}자 → {len(h1)}개×{len(h1[0]['content'])}자")
_, mh = brain.compose("chat", tool_rules="", situation=[], text="충전은 어디서 해?")
ok(len(mh["knowledge"]) >= 1, "사용법 질문은 지식을 그대로 넣음")

print("[E7 모델 · 긴 사고 끄기]")
from agent import llm  # noqa: E402
ok(config.KILN_MODEL == os.environ.get("KILN_MODEL", "qwen3-32b"), f"기본 모델 {config.KILN_MODEL} (심사 기준)")
sent = []


class _R:
    status_code = 200
    headers = {}
    text = ""

    def json(self):
        return {"choices": [{"message": {"content": "{\"answer\": \"ok\"}"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}

    def raise_for_status(self):
        return None


_http, _mode, _model, _key = llm.client._http, llm.client.mode, config.KILN_MODEL, config.KILN_API_KEY
llm.client._http = type("H", (), {"post": lambda self, url, **k: (sent.append(k.get("json") or {}), _R())[1]})()
llm.client.mode, config.KILN_MODEL, config.KILN_API_KEY = "live", "qwen3-32b", "x"
try:
    for st in ("assistant.step", "dispute.investigate"):
        try:
            llm.client.call_text(st, "시스템", "질문", mock=lambda: "", flow="t-e7")
        except Exception:  # noqa: BLE001 — 응답 해석 실패는 상관없음 (보낸 내용만 확인)
            pass
finally:
    llm.client._http, llm.client.mode, config.KILN_MODEL, config.KILN_API_KEY = _http, _mode, _model, _key
last = lambda b: (b.get("messages") or [{}])[-1].get("content", "")
ok(len(sent) >= 2 and last(sent[0]).endswith("/no_think") and "/no_think" not in last(sent[1]),
   "일반 단계는 /no_think(긴 사고 끔) · 분쟁 판정은 사고 허용" if sent else "Kiln 요청을 만들지 못함")

print("\n✓ 전체 통과" if not fails else f"\n✗ 실패 {len(fails)}건")
sys.exit(1 if fails else 0)
