"""베타 👎 사례를 실제 Kiln으로 다시 물어보는 검사 — 서버 PC(.env에 Kiln·SerpApi 키)에서.

  python tests/beta_regress_live.py            ← 임시 데이터 폴더를 써서 실제 계정·베타 데이터는 건드리지 않아요

사례마다 자동 점검(✓/✗)과 Pie의 실제 답을 함께 보여 줘요. ✗가 있거나 답이 어색하면 그 줄을 그대로 보내 주세요.
(AI 없이 도는 부분은 tests/beta_regress_check.py)
"""
import os
import re
import sys
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="sp-regress-")
os.environ.setdefault("CHAIN_MODE", "mock")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent import config, service  # noqa: E402

if config.LLM_MODE != "live" or not config.KILN_API_KEY:
    sys.exit("실제 Kiln이 필요해요 (.env에 LLM_MODE=live · KILN_API_KEY)")

AMOUNT = re.compile(r"\d{1,3}(?:,\d{3})+|\d{4,}")
fails = []


def ok(c, label):
    print(("   ✓ " if c else "   ✗ ") + label)
    if not c:
        fails.append(label)


def turn(text, history=None):
    out = service.chat(text, history=history or [], chat_id="beta-regress", user="가온")
    msgs = out.get("messages") or []
    reply = " ".join(m.get("text") or "" for m in msgs)
    split = next((m.get("split") for m in msgs if m.get("split")), None)
    cards = any(any(k in m for k in ("products", "combos", "items", "cards", "shop")) for m in msgs)
    return reply, split, cards


def nums(s):
    return {int(x.replace(",", "")) for x in AMOUNT.findall(s or "")}


def case(title, text, history=None):
    print(f"\n[{title}]\n   사용자: {text}")
    reply, split, cards = turn(text, history)
    print(f"   Pie   : {reply[:220]}")
    if split:
        print(f"   분담  : {split}")
    return reply, split, cards


# ① 1:1 나누기 — 인원만 있으면 이름을 묻지 않음 · 합계를 AI가 말하지 않음
r, s, _ = case("① 이름 되묻기 (👎 5건)", "치킨 2만 피자 1.8만 배달비 3천 넷이 나누는데 민재는 5천원 덜 내게 해줘")
ok("누구" not in r and not re.search(r"\d\s*[+=]\s*\d", r), "이름을 되묻지 않고 계산식도 없음")
ok(bool(s) and len(s) == 4 and sum(a for _, a in s) == 41000, "4명 · 합계 41,000원")

r, s, _ = case("② '나는 5천원 덜' (👎 · 합계 오류)", "4명 3만8천원 +배달비 3천인데 나는 5천원 덜 내게 해줘")
ok(bool(s) and len(s) == 4 and sum(a for _, a in s) == 41000, "4명 · 합계 41,000원 (5천원을 더하지 않음)")

r, s, _ = case("③ 1인 금액을 글로 (👎 기타)", "한정식 15만원인데 부가세 10% 별도래 여섯이 나눠줘")
ok(bool(s) and {a for _, a in s} == {27500}, "6명 모두 27,500원")
ok("27,500" in r, "답에 '1인 27,500원'이 적혀 있음")

# ④ 이어지는 추천 — 검색 결과만
hist = [{"from": "user", "text": "민재 생일인데 넷이 10만원 안에서 선물 추천해줘"}, {"from": "bot", "text": "네 명이 10만원 안에서 고를 만한 선물을 찾아봤어요."}]
r, s, cards = case("④ 이어지는 추천 요청 (👎 · 지어낸 상품)", "다른거는 없어? 옷 종류로", hist)
ok(cards or "못 찾" in r or "찾지 못" in r, "새로 검색한 결과(카드)를 보여 주거나, 못 찾았다고 말함")
ok(cards or not nums(r), "카드 없이 가격을 지어내지 않음")

# ⑤ 앞 조합 확인 — 새 금액을 만들지 않음
hist2 = [{"from": "user", "text": "넷이 치킨 시키자 6만원 안에서"},
         {"from": "bot", "text": "다양하게: 교촌 허니콤보 1개 + BBQ 황금올리브반반 + 황금알치즈볼, 51,440원 + 배달 3,000원, 1인 약 13,610원"}]
r, s, cards = case("⑤ 앞 조합 확인 (👎 · 새 금액)", "황올을 인당 1개씩 해서 4개를 사는거야?", hist2)
ok(nums(r) <= nums(" ".join(h["text"] for h in hist2)) or cards, "기록에 없던 금액을 새로 만들지 않음")

# ⑥ 못 찾을 때도 대안 제시
r, s, cards = case("⑥ 비슷한 상품 찾기 (👎 · 대안 없이 끝냄)", "비슷한 상품 4명 기준으로 찾아줘", hist2)
ok(cards or re.search(r"찾아볼까요|넓게|다른\s*검색|바꿔", r), "결과를 보여 주거나 다른 검색 방향을 제안")

print("\n✓ 전체 통과" if not fails else f"\n✗ 확인 필요 {len(fails)}건 — 위 답을 함께 보내 주세요")
sys.exit(1 if fails else 0)
