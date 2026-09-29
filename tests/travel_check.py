"""여행 가격 검색 검사 (구글 호텔·항공편 → 추천 카드). 가짜 검색 서버로 — AI 없이.
실행: 가짜 검색 서버를 켜고  SERPAPI_API_KEY=x SERPAPI_API_BASE=http://127.0.0.1:8012/serpapi SERPER_API_KEY= python tests/travel_check.py
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent import assistant, config, service, travel, websearch  # noqa: E402

fails = []


def ok(c, label):
    print(("  ✓ " if c else "  ✗ ") + label)
    if not c:
        fails.append(label)


d = lambda n: (dt.date.today() + dt.timedelta(days=n)).isoformat()
print("[숙소 — 4명 · 2박 → 2실, 계산은 코드]")
r = travel.search("숙소", "부산 해운대", check_in=d(5), check_out=d(7), people=4, budget_total=600000)
c = {x["version"]: x for x in r.get("candidates", [])}
ok(len(c) == 3 and len({x["title"] for x in c.values()}) == 3, f"최저가·가성비·프리미엄 서로 다른 3곳: {[x['title'] for x in c.values()]}")
ok(c.get("cheapest", {}).get("total") == 180000 and c["cheapest"]["per"] == 45000, "최저가: 게스트하우스 90,000원 × 2실 = 180,000원 · 1인 45,000원")
ok(c.get("premium", {}).get("total") == 1240000 and not c["premium"]["within"], "프리미엄: 5성 620,000원 × 2실 = 1,240,000원 · 예산 60만원 초과 표시")
ok(c.get("value", {}).get("title", "").startswith("해운대 오션 호텔"), "가성비: 평점 대비 가격이 좋은 곳")
ok(all("가격 없는" not in x["title"] for x in c.values()), "가격 없는 숙소는 제외")
ok(r["for_ai"]["assumption"] == "2인 1실 기준 2실 · 2박 · 4명", f"가정을 AI에 전달: {r['for_ai']['assumption']}")

print("[항공 — 김포→제주 3명 왕복]")
r = travel.search("항공", "제주", origin="김포", depart_date=d(5), return_date=d(7), people=3)
c = {x["version"]: x for x in r.get("candidates", [])}
ok(c.get("cheapest", {}).get("total") == 294000 and c["cheapest"]["per"] == 98000, "최저가: 진에어 98,000원 × 3명 = 294,000원")
ok(c.get("premium", {}).get("title", "").startswith("대한항공"), "프리미엄: 대한항공")
ok(len(c) == 3 and all("왕복" in x["title"] for x in c.values()), f"왕복 3개: {[x['title'] for x in c.values()]}")
ok(travel.iata("김포") == "GMP" and travel.iata("CJU") == "CJU" and travel.iata("제주도 여행") == "CJU" and travel.iata("화성") is None, "공항 코드")

print("[날짜가 없으면 검색하지 않고 되묻기]")
ok(travel.search("숙소", "부산", people=4)["for_ai"].get("need") == "날짜", "숙소 날짜 없음 → 날짜 묻기")
ok(travel.search("숙소", "부산", check_in=d(-3), check_out=d(-1))["for_ai"].get("need") == "날짜", "지난 날짜 → 날짜 묻기")
ok(travel.search("항공", "제주", origin="김포")["for_ai"].get("need") == "날짜", "항공 날짜 없음 → 날짜 묻기")
ok(travel.search("항공", "화성", origin="김포", depart_date=d(3))["for_ai"].get("need") == "출발지·도착지", "모르는 도착지 → 묻기")

ok(travel._date("2026-10-3") == dt.date(2026, 10, 3) and travel._date("2026.10.03") == dt.date(2026, 10, 3) and travel._date("10월 3일") is None,
   "버그 검수 ⑤: 날짜 '2026-10-3'·'2026.10.03'도 읽음")

print("[Pie 도구 → 추천 카드 · 정산방용 상품]")
s = assistant.Session("travel-check", [])
_d5 = dt.date.today() + dt.timedelta(days=5)
s.text, s.hist = f"{_d5.month}월 {_d5.day}일부터 2박 부산 해운대 숙소 넷이", []
out = s.travel_price_search(kind="숙소", destination="부산 해운대", check_in=d(5), check_out=d(7), people=4)
ok(s.card and s.card[0] == "web" and out["candidates"][0]["per_person"] == 45000, "Pie에게는 코드가 계산한 금액, 화면에는 웹 카드")
msgs = service._chat_shop_web(s.card[1])
m = msgs[0]
p = m["products"][m["compare"][0]]
ok(len(m["compare"]) == 3 and p["isWeb"] and p["merchant"] == "구글 호텔" and p["total"] == 180000, f"카드 상품: {p['name']} · {p['merchant']} · {p['total']:,}원")
ok("구글 호텔" in m["text"], f"안내 문구: {m['text'][:60]}")
ok(any(t["name"] == "travel_price_search" for t in assistant.TOOLS) and "travel_price_search" in assistant.TOOL_RULES, "도구 정의 · 규칙")

print("[키가 없으면 솔직하게]")
key = config.SERPAPI_API_KEY; config.SERPAPI_API_KEY = ""
ok(travel.search("숙소", "부산", check_in=d(5), check_out=d(7))["for_ai"].get("source") == "none", "SerpApi 키 없음 → 모른다고 안내")
config.SERPAPI_API_KEY = key

print("\n✓ 전체 통과" if not fails else f"\n✗ 실패 {len(fails)}건")
sys.exit(1 if fails else 0)
