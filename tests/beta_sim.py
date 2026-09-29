"""가상 베타 테스트 — 실제 Kiln·SerpApi로 가상 참여자가 미션과 자유 대화를 하고 자동 채점 → 👍/👎 기록 → 보고서.

  python tests/beta_sim.py                 (기본: 가상 참여자 3명)
  python tests/beta_sim.py --people 2 --no-travel

- 임시 데이터 폴더 · APP_VERSION=beta-sim · 체인은 모의(실제 ETH 안 씀) → 실제 계정·베타 데이터는 건드리지 않아요.
- 끝나면 <임시 폴더>/beta/ 에 베타 데이터가, tests/eval_results/beta_sim_<시각>.md 에 평가 보고서가 남아요.
- 이의제기(S07)는 실제 정산·예치가 필요해 건너뛰어요 (Sepolia 증거로 확인).
"""
import argparse
import collections
import json
import os
import re
import statistics as S
import sys
import tempfile
import time
import uuid
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--people", type=int, default=3)
ap.add_argument("--no-travel", action="store_true")
ap.add_argument("--allow-mock", action="store_true", help="(개발용) 가짜 Kiln으로 흐름만 확인")
A = ap.parse_args()
TMP = tempfile.mkdtemp(prefix="sp-betasim-")
os.environ.update({"DATA_DIR": TMP, "APP_VERSION": os.environ.get("SIM_VERSION", "beta-sim"), "BETA_ENABLED": "1", "CHAIN_MODE": "mock"})
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from starlette.testclient import TestClient  # noqa: E402
from agent import beta, config, service, store  # noqa: E402
from backend.app import app  # noqa: E402

if not A.allow_mock and (config.LLM_MODE != "live" or not config.KILN_API_KEY):
    sys.exit("실제 Kiln이 필요해요 (.env에 LLM_MODE=live · KILN_API_KEY)")
config.BETA_ENABLED = True
ARITH = re.compile(r"\d[\d,]*\s*[+×x*÷/]\s*\d[\d,]*\s*=")
turns: list[dict] = []


def judge(kind, msgs, exp):
    """자동 채점 → (좋음?, 이유들). 금액은 분담표(코드 결과)로, 말은 규칙으로."""
    text = " ".join(m.get("text") or "" for m in msgs)
    split = next((m.get("split") for m in msgs if m.get("split")), None)
    card = next((m for m in msgs if m.get("compare")), None)
    bad = []
    if (not msgs or not text.strip()) and not exp.get("silent"):
        bad.append("답 없음")
    if "**" in text or re.search(r"[\U0001F300-\U0001FAFF]", text):
        bad.append("형식(**·이모지)")
    if ARITH.search(text):
        bad.append("AI가 계산식을 씀")
    if kind == "split":
        if not split:
            bad.append("분담표 없음" + (f" (되물음: {text[:40]})" if "?" in text else ""))
        else:
            if exp.get("n") and len(split) != exp["n"]:
                bad.append(f"인원 {len(split)}≠{exp['n']}")
            if exp.get("total") and sum(a for _, a in split) != exp["total"]:
                bad.append(f"합계 {sum(a for _, a in split):,}≠{exp['total']:,}")
            if exp.get("less"):
                who, amt = exp["less"]
                d = dict(split)
                if who not in d or any(v - d[who] != amt for k, v in d.items() if k != who):
                    bad.append(f"{who} {amt:,}원 덜 조건 틀림")
        if "누구" in text:
            bad.append("1:1에서 이름 되묻기")
    elif kind == "ask":
        if split:
            bad.append("모호한데 되묻지 않고 계산")
    elif kind == "shop":
        if not card:
            if not re.search(r"못 찾|찾지 못|날짜|며칠|언제", text):
                bad.append("추천 카드 없음")
            if re.search(r"\d[\d,]{3,}\s*원", text) and not card:
                bad.append("카드 없이 가격을 말함 (지어냈을 수 있음)")
        else:
            rec = card.get("rec") or {}
            if not rec.get("rec_id"):
                bad.append("rec_id 없음 (④)")
            line = (rec.get("situation") or {}).get("line", "")
            first = (next((m.get("text") for m in msgs if m.get("text") and not m.get("compare")), "") or "").split(".")[0]
            if line and line.split("'")[1:2] and line.split("'")[1] not in first and "여러 방향" not in line:
                bad.append("상황 한 줄로 시작 안 함")
    elif kind == "howto":
        if exp.get("any") and not any(w in text for w in exp["any"]):
            bad.append(f"사실 누락 ({'/'.join(exp['any'])})")
    elif kind == "group":
        if exp.get("silent") and msgs:
            bad.append("잡담에 끼어듦")
        if not exp.get("silent") and not msgs:
            bad.append("답 없음")
        if exp.get("any") and msgs and not any(w in text for w in exp["any"]):
            bad.append(f"빠짐 ({'/'.join(exp['any'])})")
    return not bad, bad, text, split, card


def reason_of(bad):
    return "금액이 틀렸어요" if any(("합계" in b or "덜" in b or "계산" in b or "인원" in b) for b in bad) else "엉뚱한 답이에요"


class User:
    def __init__(self, cli, i):
        self.cli, self.name = cli, ["가상민지", "가상도윤", "가상서연", "가상하준"][i % 4]
        email = f"sim{i}.{uuid.uuid4().hex[:4]}@beta.test"
        code = service.send_code(email, "signup")["dev_code"]
        u = service.signup(self.name, email, "pass1234", code=code)
        self.tok = u.get("token") or service.login(email, "pass1234")["token"]
        self.short = u.get("short") or self.name
        self.me = {**u, "email": email}
        service.beta_consent(self.me, True)
        self.h = {"Authorization": f"Bearer {self.tok}"}
        self.hist: list[dict] = []

    def say(self, text, scenario=None, keep=True, label="", kind="split", exp=None):
        t0 = time.time()
        r = self.cli.post("/api/chat", json={"message": text, "chat_id": "sim-" + self.short, "user": self.short,
                                             "history": self.hist[-8:], "context": {}, "scenario": scenario}, headers=self.h)
        d = r.json().get("data", r.json())
        msgs = d.get("messages") or []
        ok, bad, reply, split, card = judge(kind, msgs, exp or {})
        tid = next((m.get("turn") for m in msgs if m.get("turn")), None)
        if tid:
            self.cli.post("/api/beta/feedback", json={"turn": tid, "rating": "up" if ok else "down",
                                                      **({} if ok else {"reason": reason_of(bad), "note": "; ".join(bad)[:120]})}, headers=self.h)
        if keep:
            self.hist += [{"from": "user", "text": text}] + [{"from": "bot", "text": m["text"]} for m in msgs if m.get("text")]
        turns.append({"who": self.short, "label": label or scenario or "자유", "text": text, "ok": ok, "bad": bad,
                      "reply": reply[:220], "sec": round(time.time() - t0, 1), "card": bool(card), "split": split,
                      "rec": (card or {}).get("rec"), "kind": kind})
        mark = "✓" if ok else "✗"
        print(f"  {mark} [{label or scenario or '자유'}] {text[:38]} → {reply[:70]!r}" + (f"  ({', '.join(bad)})" if bad else ""))
        return msgs, card


def main():
    print(f"== 가상 베타 테스트 · 참여자 {A.people}명 · 버전 {config.APP_VERSION} · 데이터 {TMP}")
    with TestClient(app) as cli:
        people = [User(cli, i) for i in range(A.people)]
        for i, u in enumerate(people):
            print(f"\n[{u.short}] 1:1 미션")
            u.hist = []
            u.say("삼겹살 38,900원 넷이 똑같이 나눠줘", "S01", exp={"n": 4, "total": 38900})
            u.hist = []
            u.say("치킨 2만 피자 1.8만 배달비 3천 넷이 나누는데 진주는 5천원 덜 내게 해줘", "S02", exp={"n": 4, "total": 41000, "less": ("진주", 5000)})
            u.hist = []
            u.say("한정식 15만원인데 부가세 10% 별도래 여섯이 나눠줘", "S03", exp={"n": 6, "total": 165000})
            u.hist = []
            u.say("숙소 30만원 넷이 나눠줘", "S04", exp={"n": 4, "total": 300000})
            u.say("아 총액 32만원이었어", "S04", label="S04 조건 변경", exp={"n": 4, "total": 320000})
            u.hist = []
            u.say("총 5만원인데 진주는 조금 더 내게 해줘", "S05", kind="ask")
            u.hist = []
            _, card = u.say("월말이라 거지다 넷이 치킨 시키자 6만원 안에서", "S08", kind="shop")
            if card and card.get("rec"):                                  # ④ 목적 버튼 → 다시 고르기
                b = card["recButtons"][1 if i % 2 else 0]
                cli.post("/api/pie/feedback", json={"rec_id": card["rec"]["rec_id"], "event": "correct", "purpose": b["purpose"]}, headers=u.h)
                cli.post("/api/pie/feedback", json={"rec_id": card["rec"]["rec_id"], "event": "choose", "candidate": card["compare"][0]}, headers=u.h)
                u.say(b["say"], label=f"④ 버튼 '{b['label']}'", kind="shop")
            u.say("다른 거는 없어?", label="추천 이어가기", kind="shop")
            u.hist = []
            u.say("민재 생일인데 제대로 된 걸로 시키자 넷이 10만원", "S09", kind="shop")
            u.hist = []
            u.say("아무거나 시켜줘 우리 넷 8만", "S10", kind="shop")
            u.hist = []
            u.say("AI 요금제는 어떻게 돼?", "S13", kind="howto", exp={"any": ["Pie Max", "베타", "무료"]})
            u.hist = []
            u.say("4명 3만8천원 +배달비 3천인데 나는 5천원 덜 내게 해줘", label="베타👎 '나는 덜'", exp={"n": 4, "total": 41000, "less": ("나", 5000)})
            if not A.no_travel and i == 0:
                import datetime as dt
                d1 = dt.date.today() + dt.timedelta(days=10)
                u.hist = []
                u.say(f"{d1.month}월 {d1.day}일부터 2박 부산 해운대 숙소 넷이 60만원 안에서", label="여행 숙소", kind="shop")
                u.hist = []
                u.say(f"{d1.month}월 {d1.day}일 김포에서 제주 가는 비행기 셋이 편도", label="여행 항공", kind="shop")
                u.hist = []
                u.say("다음 주에 강릉 숙소 추천해줘", label="여행 날짜 없음", kind="shop")

        print("\n[그룹방 미션]")
        a, b = people[0], people[min(1, len(people) - 1)]
        gid = "g" + uuid.uuid4().hex[:10]
        service.group_create(a.short, {"id": gid, "name": "가상 정산방", "members": [a.short, b.short, "진주", "민재"]})

        def gsay(who, text, label, exp, active=False):
            if active:
                g = store.kv_get("groups", gid); g["total"] = 38900; store.kv_put("groups", gid, g)
            mid = "m" + uuid.uuid4().hex[:8]
            service.group_message(who.short, gid, {"id": mid, "from": who.short, "text": text})
            t0 = time.time()
            msgs = service.group_pie(who.short, gid, mid, scenario=label if label.startswith("S") else None) or []
            ok, bad, reply, _, _ = judge("group", msgs, exp)
            turns.append({"who": who.short, "label": label, "text": text, "ok": ok, "bad": bad, "reply": reply[:220],
                          "sec": round(time.time() - t0, 1), "card": False, "split": None, "rec": None, "kind": "group"})
            print(f"  {'✓' if ok else '✗'} [{label}] {text[:38]} → {reply[:70]!r}" + (f"  ({', '.join(bad)})" if bad else ""))
        gsay(a, "ㅋㅋ 오늘 날씨 좋다", "잡담", {"silent": True})
        gsay(a, "파이야", "S11", {})
        gsay(b, "8만원 넷이 똑같이 나누는데 1인 1만5천원 넘으면 안 돼", "S06", {"any": ["1만5천", "15,000", "한도", "넘"]})
        gsay(a, "파이야 누가 아직 안 냈어?", "S12", {}, active=True)
        gsay(b, "아직 누구 남음?", "진행 질문(ev-026)", {}, active=True)

    report(people)


def report(people):
    rows = [json.loads(l) for l in (Path(TMP) / "usage.jsonl").open(encoding="utf-8")] if (Path(TMP) / "usage.jsonl").exists() else []
    llm = [r for r in rows if r.get("mode") in ("tools", "json", "text")]
    by = collections.defaultdict(lambda: [0, 0])
    for r in llm:
        by[r["stage"]][0] += 1; by[r["stage"]][1] += r.get("total_tokens") or 0
    tot = sum(v[1] for v in by.values())
    good = sum(t["ok"] for t in turns)
    lab = collections.defaultdict(lambda: [0, 0])
    for t in turns:
        k = t["label"].split(" ")[0]
        lab[k][0] += t["ok"]; lab[k][1] += 1
    problems = collections.Counter(b.split(" (")[0] for t in turns for b in t["bad"])
    pf = [json.loads(l) for l in (beta.DIR / "pie_feedback.jsonl").open(encoding="utf-8")] if (beta.DIR / "pie_feedback.jsonl").exists() else []
    L = [f"# 가상 베타 테스트 보고서 — {config.APP_VERSION}", "",
         f"- 가상 참여자 {len(people)}명 · 턴 {len(turns)}개 · **자동 채점 통과 {good}/{len(turns)} ({good / max(1, len(turns)):.0%})**",
         f"- Kiln 호출 {len(llm)}회 · 토큰 {tot:,} · 턴당 평균 {tot // max(1, len(turns)):,} · 응답 시간 중앙값 {S.median([t['sec'] for t in turns]) if turns else 0}초",
         f"- ④ 추천 기록 {sum(1 for r in pf if r.get('event') == 'shown')}건 · 목적 버튼 {sum(1 for r in pf if r.get('event') == 'correct')}건 · 선택 {sum(1 for r in pf if r.get('event') == 'choose')}건", "",
         "## 항목별", "", "| 항목 | 통과 |", "|---|---|"] + [f"| {k} | {x}/{y} |" for k, (x, y) in sorted(lab.items())] + [
         "", "## 자주 나온 문제", ""] + ([f"- {p}: {n}회" for p, n in problems.most_common()] or ["- 없음"]) + [
         "", "## 단계별 토큰", "", "| 단계 | 호출 | 토큰 |", "|---|---|---|"] + [f"| {s} | {n} | {t:,} |" for s, (n, t) in sorted(by.items(), key=lambda x: -x[1][1])] + [
         "", "## 실패한 턴 (원문)", ""] + [f"- **[{t['label']}]** {t['text']}\n  - Pie: {t['reply']}\n  - 문제: {', '.join(t['bad'])}" for t in turns if not t["ok"]]
    out = ROOT / "tests" / "eval_results"
    out.mkdir(exist_ok=True)
    f = out / f"beta_sim_{time.strftime('%Y%m%d-%H%M')}.md"
    f.write_text("\n".join(L) + "\n", encoding="utf-8")
    (out / f.name.replace(".md", ".jsonl")).write_text("".join(json.dumps(t, ensure_ascii=False, default=str) + "\n" for t in turns), encoding="utf-8")
    print("\n" + "\n".join(L[:4]))
    print(f"\n평가 보고서: {f.relative_to(ROOT)}\n베타 데이터(보고서 report.md 포함): {beta.DIR}")
    try:
        service.beta_report()
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    main()
