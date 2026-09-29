"""여행 가격 (가이드라인 ④ '여행 후보용 숙소·교통 가격 검색 도구').

구글 호텔·구글 항공편(SerpApi)에서 가격을 찾고, 방 수·총액·1인 비용은 코드가 계산해
웹 상품 카드와 같은 모양(최저가·가성비·프리미엄)으로 돌려준다 → 추천 카드 · ④ 목적 버튼 · 정산방 만들기가 그대로 동작.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
import re
from typing import Any

from . import websearch

_IATA = {"서울": "GMP", "김포": "GMP", "인천": "ICN", "제주": "CJU", "부산": "PUS", "김해": "PUS", "대구": "TAE", "광주": "KWJ",
         "여수": "RSU", "청주": "CJJ", "울산": "USN", "양양": "YNY", "강릉": "YNY", "포항": "KPO", "무안": "MWX", "목포": "MWX",
         "군산": "KUV", "사천": "HIN", "진주": "HIN", "원주": "WJU", "도쿄": "HND", "오사카": "KIX", "후쿠오카": "FUK",
         "삿포로": "CTS", "오키나와": "OKA", "방콕": "BKK", "다낭": "DAD", "나트랑": "CXR", "세부": "CEB", "타이베이": "TPE",
         "홍콩": "HKG", "싱가포르": "SIN", "괌": "GUM", "상하이": "PVG", "베이징": "PEK"}
_DATE = re.compile(r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$")


def iata(place: str | None) -> str | None:
    p = (place or "").strip()
    if re.fullmatch(r"[A-Za-z]{3}", p):
        return p.upper()
    return next((code for name, code in _IATA.items() if name in p), None)


def _date(s: str | None) -> dt.date | None:
    try:
        m = _DATE.match((s or "").strip())
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
    except ValueError:
        return None


def _won(n: int) -> str:
    return f"{n:,}원"


def _per(total: int, people: int | None) -> int | None:
    return math.floor(total / people + 0.5) if people else None      # 반올림(코드) — 실제 정산은 정산 엔진이 1원 단위로 다시 나눔


def _oid(*parts: str) -> str:
    return "t" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:9]


def _pick(items: list[dict[str, Any]], key_cheap, key_value, key_premium) -> list[tuple[str, dict[str, Any]]]:
    """최저가 · 가성비 · 프리미엄 — 서로 다른 후보 최대 3개."""
    out, seen = [], set()
    for ver, key, rev in (("cheapest", key_cheap, False), ("value", key_value, True), ("premium", key_premium, True)):
        for it in sorted(items, key=key, reverse=rev):
            if id(it) not in seen:
                seen.add(id(it)); out.append((ver, it)); break
    return out


def search(kind: str, destination: str, *, origin=None, check_in=None, check_out=None, depart_date=None, return_date=None,
           people=None, budget_total=None) -> dict[str, Any]:
    people = int(people) if people else None
    budget = int(budget_total) if budget_total else None
    if not websearch.travel_enabled():
        note = "여행 가격 검색 키(SERPAPI_API_KEY)가 없어 숙소·항공 가격을 찾을 수 없다. 모른다고 말하고, 본 가격을 알려 주면 나눠 준다고 안내한다."
        return {"log": "SerpApi 키 없음", "for_ai": {"source": "none", "note": note}}
    today = dt.date.today()
    if kind == "숙소":
        a, b = _date(check_in), _date(check_out)
        if not a or not b or b <= a or a < today:
            return {"log": "날짜 없음 → 되묻기", "for_ai": {"need": "날짜", "note": "체크인·체크아웃 날짜를 한 번에 묻는다 (예: 10월 3일~5일)."}}
        nights, rooms = (b - a).days, max(1, math.ceil((people or 2) / 2))
        found = websearch.serpapi_hotels(destination, a.isoformat(), b.isoformat(), adults=2)
        items = []
        for h in found:
            stay = h["total"] or (h["night"] or 0) * nights
            if stay <= 0:
                continue
            total = stay * rooms
            title = f"{h['name']}" + (f" · {h['stars']}성" if h.get("stars") else "") + (f" · ★{h['rating']}" if h.get("rating") else "") + f" · {nights}박 {rooms}실"
            items.append({**h, "stay": stay, "total_all": total, "title": title})
        src, label = "google_hotels", f"{destination} 숙소 {a.month}/{a.day}~{b.month}/{b.day}"
        picks = _pick(items, lambda x: x["total_all"], lambda x: (x.get("rating") or 0) / max(1, x["total_all"]) * 1e6,
                      lambda x: ((x.get("stars") or 0), (x.get("rating") or 0)))
        assume = f"2인 1실 기준 {rooms}실 · {nights}박" + (f" · {people}명" if people else "")
    elif kind == "항공":
        o, d = iata(origin or "서울"), iata(destination)
        a, r = _date(depart_date), _date(return_date)
        if not o or not d:
            return {"log": "공항 모름 → 되묻기", "for_ai": {"need": "출발지·도착지", "note": "출발·도착 도시(공항)를 묻는다 (예: 김포 → 제주)."}}
        if not a or a < today or (return_date and (not r or r < a)):
            return {"log": "날짜 없음 → 되묻기", "for_ai": {"need": "날짜", "note": "출발일(왕복이면 돌아오는 날도)을 한 번에 묻는다."}}
        found = websearch.serpapi_flights(o, d, a.isoformat(), r.isoformat() if r else None)
        items = []
        for f in found:
            n = people or 1
            total = f["price"] * n
            hm = lambda s: s[-5:] if s else ""
            title = f"{f['airline']} {hm(f['dep'])}→{hm(f['arr'])}" + (" 직항" if not f["stops"] else f" 경유 {f['stops']}회") + (" · 왕복" if r else " · 편도")
            items.append({**f, "total_all": total, "title": title, "link": None})
        src, label = "google_flights", f"{o}→{d} 항공 {a.month}/{a.day}" + (f"~{r.month}/{r.day}" if r else "")
        picks = _pick(items, lambda x: x["total_all"], lambda x: (-(x["stops"]), -(x.get("minutes") or 999), -x["total_all"]),
                      lambda x: (x["airline"] in ("대한항공", "아시아나항공"), -x["stops"]))
        assume = ("왕복" if r else "편도") + f" 1인 가격 × {people or 1}명"
    else:
        return {"log": f"알 수 없는 종류 {kind}", "for_ai": {"note": "kind는 숙소 또는 항공"}}

    cands = []
    for ver, it in picks:
        total = it["total_all"]
        cands.append({"id": _oid(src, it["title"], str(total)), "title": it["title"], "mall": "구글 호텔" if src == "google_hotels" else "구글 항공편",
                      "source": src, "version": ver, "price": total, "total": total, "units": 1, "per": _per(total, people),
                      "budget": budget, "within": (total <= budget) if budget else True, "verified": True, "trusted": True,
                      "url": it.get("link"), "qty": None, "ppp": None})
    q = {"product_query": label, "people": people or 0, "budget_total": budget, "allowed_malls": []}
    card = {"query": q, "candidates": cands, "explain": "",
            "web": {"stats": {src: len(items)}, "sources": {src: True}, "queries": [label]}}
    for_ai = {"source": src, "assumption": assume, "found": len(items), "candidates": [
        {"version": {"cheapest": "최저가", "value": "가성비", "premium": "프리미엄"}[c["version"]], "title": c["title"],
         "total": c["total"], "per_person": c["per"], "within_budget": c["within"]} for c in cands],
        "note": "총액·1인 비용은 코드가 계산한 값 그대로 말한다. 가격은 검색 시점 기준이라 예약 전에 다시 확인하라고 한다."}
    return {"log": f"{label} · 찾음 {len(items)}개 → 후보 {len(cands)}개 ({assume})", "candidates": cands, "card": card, "for_ai": for_ai}
