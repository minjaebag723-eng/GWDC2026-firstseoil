"""④ 상황 인식 추천 (Pie mate 학습 가이드라인 ④·⑤).

- 목적 읽기는 코드 규칙이라 토큰 0: 가격 · 양 · 품질 · 경험 · 판단 없음 + 확신도 상/중/하
- '상황 한 줄'은 가이드라인 ④ 표의 문장 틀 그대로 → 추천 답의 첫 문장 (assistant가 프롬프트에 넣음)
- 추천 응답마다 rec_id를 붙여 세 사건(choose 선택 · correct 목적 정정 · rate 만족도)을 같은 id로 묶는다
- 기록: DATA_DIR/pie_feedback.jsonl (+ 베타면 베타 데이터 폴더에 비식별 사본). 사람은 uid로만 남긴다.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from typing import Any

from . import config, store

PURPOSES = ("가격", "양", "품질", "경험")
NONE = "판단 없음"
# 목적 버튼 4개 (화면 순서 그대로) — 누르면 그 목적으로 다시 고르게 Pie에게 보낼 말
BUTTONS = [{"purpose": "가격", "label": "더 싸게", "say": "더 싸게 다시 골라 줘"},
           {"purpose": "양", "label": "더 많이", "say": "양 많은 걸로 다시 골라 줘"},
           {"purpose": "품질", "label": "더 좋게", "say": "더 좋은 걸로 다시 골라 줘"},
           {"purpose": "경험", "label": "안 해본 걸로", "say": "안 해본 걸로 다시 골라 줘"}]
# 직접 말한 신호 (확신도 상)
_DIRECT = {"가격": r"싸게|저렴|가성비|싼\s*(거|걸로|것)|아껴|절약|최저가|싸고|적게\s*쓰",
           "양": r"많이|푸짐|배불|넉넉|양\s*많|양으로|대용량",
           "품질": r"좋은\s*(거|걸로|것)|제대로|고급|퀄리티|품질|프리미엄|비싸도|맛있는\s*걸로",
           "경험": r"안\s*해\s*본|새로운|색다른|처음\s*(먹|해)|특이한|이색|안\s*먹어\s*본|새로\s*나온"}
# 상황 단서 (확신도 중)
_CLUE = {"가격": r"월말|거지|용돈|빠듯\w*|적자|파산|돈이\s*없\w*|통장",
         "양": r"운동\s*끝\w*|배고\w*|굶\w*|대식가",
         "품질": r"생일|기념일|축하|부모님|승진|합격|선물",
         "경험": r"질려\w*|질렸\w*|맨날|매번|늘\s*먹던|심심\w*"}
_NOUN_CLUE = re.compile(r"^(월말|거지|용돈|적자|파산|통장|대식가|생일|기념일|축하|부모님|승진|합격|선물)$")
_KIND = [("가격", r"가성비|저렴|최저|싼|알뜰"), ("양", r"푸짐|대용량|넉넉|많이|배부"),
         ("경험", r"다양|이색|새로|신메뉴|색다|특별한"), ("품질", r"프리미엄|고급|인기|제대로|명품|베스트")]
_DOMAIN = [("음식·배달", r"배달|치킨|피자|족발|메뉴|시켜|먹|야식|음식|고기|떡볶이|버거"),
           ("여행", r"여행|숙소|호텔|펜션|항공|기차|렌트"),
           ("물품", r"선물|사자|살까|구매|공구|공동구매|상품|옷|물건|세트")]
_lock = threading.Lock()


def _i(word: str) -> str:
    """받침이 있으면 '이'를 붙인다 ('월말'→'월말이', '파티'→'파티')."""
    ch = word[-1:] if word else ""
    return word + "이" if ch and "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 else word


def _quote(w: str) -> str:
    """말한 그대로 인용: '"가성비"라고' · '"맨날"이라고'."""
    return f"\"{w}\"" + ("이라고" if _i(w) != w else "라고")


def _clue(w: str, tail: str) -> str:
    """상황 단서 문구 — 명사면 '월말이라'·'생일이지만', 말이면 '"배고파"라고 하셔서'·'"돈이 없어서"라고 하셨지만'."""
    if _NOUN_CLUE.match(w):
        return _i(w) + tail
    return _quote(w) + (" 하셔서" if tail == "라" else " 하셨지만")


def _hit(pats: dict[str, str], text: str) -> tuple[str | None, str | None]:
    best = None
    for p in PURPOSES:
        m = re.search(pats[p], text)
        if m and (best is None or m.start() < best[2]):
            best = (p, m.group(0).strip(), m.start())
    return (best[0], best[1]) if best else (None, None)


def composition(sit: dict[str, Any]) -> str:
    """⑤ 확신도 규칙: 상 = 1순위 2개 + 2순위 1개 · 중 = 1순위·2순위·나머지 1개씩 · 하 = 모두 다른 방향."""
    r, r2 = sit.get("read"), sit.get("read2")
    if sit.get("confidence") == "상":
        return f"후보 3개 중 2개는 '{r}' 방향, 1개는 다른 방향"
    if sit.get("confidence") == "중":
        return f"후보 3개를 '{r}' 1개 · '{r2 or '다른 방향'}' 1개 · 나머지 방향 1개로"
    return "후보 3개를 가격·양·품질·경험 중 서로 다른 방향으로"


def preferred(user: str | None, domain: str) -> str | None:
    """④ 사례 꺼내기: 이 사람이 같은 분야에서 목적 버튼으로 마지막에 고른 목적."""
    return ((store.kv_get("rec_prefs", user) or {}).get(domain)) if user else None


def classify(text: str, history: list[str] | None = None, prefer: str | None = None) -> dict[str, Any]:
    """이번 말(+ 최근 사용자 말 두 개)에서 목적을 읽는다. 직접 말함 > 상황 단서 > 지난 정정 사례 > 판단 없음."""
    now = text or ""
    ctx = " ".join((history or [])[-2:])
    d, dw = _hit(_DIRECT, now)
    c, cw = _hit(_CLUE, now)
    if not c:
        c, cw = _hit(_CLUE, ctx)
    if not d and not c:
        d, dw = _hit(_DIRECT, ctx)
    if d and c and c != d:
        return {"read": d, "read2": c, "confidence": "중", "line": f"{_clue(cw, '지만')} {_quote(dw)} 하셔서 '{d}'을 먼저 봤어요."}
    if d:
        return {"read": d, "read2": None, "confidence": "상", "line": f"{_quote(dw)} 하셔서 '{d}' 위주로 골랐어요."}
    if c:
        return {"read": c, "read2": None, "confidence": "중", "line": f"{_clue(cw, '라')} '{c}' 쪽으로 봤어요."}
    if prefer in PURPOSES:
        return {"read": prefer, "read2": None, "confidence": "중", "line": f"지난번에 '{prefer}' 쪽을 고르셔서 '{prefer}' 쪽으로 봤어요.", "from_case": True}
    return {"read": NONE, "read2": None, "confidence": "하", "line": "어느 쪽이 좋을지 몰라서 여러 방향으로 골랐어요."}


def domain_of(text: str) -> str:
    for name, pat in _DOMAIN:
        if re.search(pat, text or ""):
            return name
    return "기타"


def kind_of(text: str) -> str | None:
    for name, pat in _KIND:
        if re.search(pat, text or ""):
            return name
    return None


def _log(row: dict[str, Any]) -> None:
    from . import beta                                    # 순환 import 방지
    who = row.pop("user", None)
    out = {"ts": round(time.time(), 3), "version": config.APP_VERSION, "uid": beta.uid(who) if who else None, **row}
    line = json.dumps(out, ensure_ascii=False) + "\n"
    paths = [config.DATA_DIR / "pie_feedback.jsonl"] + ([beta.DIR / "pie_feedback.jsonl"] if beta.enabled() else [])
    with _lock:
        for p in paths:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(line)


def attach(msg: dict[str, Any], text: str, history: list[str] | None = None, user: str | None = None) -> dict[str, Any]:
    """추천 답(후보 카드가 있는 메시지)에 rec_id · 상황 판단 · 후보별 성격을 붙이고 '보여 줌'을 기록한다."""
    dom = domain_of(" ".join([text or ""] + (history or [])[-2:]))
    sit = classify(text, history, prefer=preferred(user, dom))
    sit["domain"] = dom
    prods = msg.get("products") or {}
    shown = []
    for i, cid in enumerate(msg.get("compare") or []):
        p = prods.get(cid) or {}
        k = kind_of(" ".join(str(p.get(x) or "") for x in ("name", "label", "tag", "reason", "where")))
        shown.append({"id": cid, "kind": k or (sit["read"] if i == 0 and sit["read"] in PURPOSES else "기타")})
    rid = "r_" + uuid.uuid4().hex[:8]
    rec = {"rec_id": rid, "situation": sit, "shown": shown}
    store.kv_put("recs", rid, {**rec, "user": user, "ts": time.time(), "events": [], "ratings": {}})
    msg["rec"], msg["recButtons"] = rec, BUTTONS
    _log({"event": "shown", "rec_id": rid, "user": user, "read": sit["read"], "read2": sit["read2"],
          "confidence": sit["confidence"], "domain": sit["domain"], "kinds": [s["kind"] for s in shown]})
    return rec


def feedback(user: str, rec_id: str, event: str, candidate: str | None = None, purpose: str | None = None,
             satisfaction: int | None = None) -> dict[str, Any]:
    """choose(후보 선택: 읽은 목적과 같으면 +1) · correct(목적 정정: -1, 정답 목적 확정) · rate(만족도 1~5, 한 사람 한 번)."""
    r = store.kv_get("recs", rec_id or "")
    if not r:
        raise ValueError("REC_NOT_FOUND")
    sit = r["situation"]
    row: dict[str, Any] = {"event": event, "rec_id": rec_id, "user": user, "read": sit["read"],
                           "confidence": sit["confidence"], "domain": sit.get("domain")}
    if event in ("choose", "correct") and r.get("user") and user != r.get("user"):
        raise ValueError("NOT_OWNER")                  # 남의 추천에 선택·정정을 넣으면 그 사람 기록과 내 사례가 섞임
    if event == "choose":
        kinds = {s["id"]: s["kind"] for s in r.get("shown") or []}
        if candidate not in kinds:
            raise ValueError("BAD_CANDIDATE")
        row.update(candidate=candidate, kind=kinds[candidate], score=1 if kinds[candidate] == sit["read"] else 0)
    elif event == "correct":
        if purpose not in PURPOSES:
            raise ValueError("BAD_PURPOSE")
        row.update(purpose=purpose, gold=purpose, score=-1)
        if user and sit.get("domain"):                 # 다음 추천에서 꺼내 쓸 사례
            store.kv_put("rec_prefs", user, {**(store.kv_get("rec_prefs", user) or {}), sit["domain"]: purpose})
    elif event == "rate":
        s = int(satisfaction or 0)
        if not 1 <= s <= 5:
            raise ValueError("BAD_SATISFACTION")
        if (r.get("ratings") or {}).get(user):
            return {"ok": True, "duplicate": True}
        r["ratings"] = {**(r.get("ratings") or {}), user: s}
        row.update(satisfaction=s, score=round((s - 3) / 2, 2))
    else:
        raise ValueError("BAD_EVENT")
    ev = {k: v for k, v in row.items() if k != "user"}
    r["events"] = (r.get("events") or [])[-49:] + [{**ev, "ts": time.time()}]
    store.kv_put("recs", rec_id, r)
    _log(row)
    return {"ok": True, "score": row.get("score")}
