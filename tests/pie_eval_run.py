"""평가 세트(tests/pie_eval.jsonl 88문제)를 실제 Kiln으로 풀고 채점 — 가이드라인 '로더·채점 스크립트 연결, 학습 전 점수 측정'.

  python tests/pie_eval_run.py                 ← 서버 PC(.env에 Kiln 키). 임시 데이터 폴더라 실제 계정은 안 건드려요
  python tests/pie_eval_run.py --only ev-026,ev-036   특정 문제만
  python tests/pie_eval_run.py --both-group    1:1·그룹 공통 문제를 그룹방에서도 (앞에 '파이야 '를 붙여) 한 번 더

결과: tests/eval_results/pie_eval_<APP_VERSION>_<시각>.jsonl — 버전을 바꿔 다시 돌리면 학습 전/후 통과율을 비교할 수 있어요.
Kiln 호출이 문제당 1~6회라 한 번에 약 150~500회 나가요 (팀 키 한도 확인).
"""
import argparse, collections, json, os, re, sys, tempfile, time, uuid
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="sp-eval-")
os.environ.setdefault("CHAIN_MODE", "mock")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agent import config, service, store  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--only", default="")
ap.add_argument("--both-group", action="store_true")
ap.add_argument("--allow-mock", action="store_true", help="(개발용) 가짜 Kiln으로 흐름만 확인")
a = ap.parse_args()
if not a.allow_mock and (config.LLM_MODE != "live" or not config.KILN_API_KEY):
    sys.exit("실제 Kiln이 필요해요 (.env에 LLM_MODE=live · KILN_API_KEY)")

items = [json.loads(l) for l in (ROOT / "tests" / "pie_eval.jsonl").open(encoding="utf-8") if l.strip()]
if a.only:
    want = set(a.only.split(",")); items = [e for e in items if e["id"] in want]
REFUSE = re.compile(r"도와\s*드릴\s*수\s*없|도울\s*수\s*없|어려워요|할\s*수\s*없어요|불법")


def room_of(e):
    txt = e.get("room") or ""
    m = re.search(r"멤버\s*([^·\n]+(?:·[^·\n ]+)*)", txt)
    members = [x.strip() for x in (m.group(1).split("·") if m else []) if x.strip() and "정산" not in x][:8]
    who = e["user"]["who"]
    members = list(dict.fromkeys([who] + [h["who"] for h in e.get("history") or [] if h["who"] not in ("Pie", "Pie mate")] + members))
    tot = re.search(r"총액\s*([\d,]+)원", txt)
    active = bool(tot or re.search(r"온체인 상태|예치|승인 대기|지급", txt)) and not re.search(r"정산 상태:\s*(조건 입력|비용 입력)", txt)
    return members, active, (int(tot.group(1).replace(",", "")) if tot else 10000)


def run_chat(e):
    hist = [{"from": "bot" if h["who"] in ("Pie", "Pie mate") else "user", "text": h["text"]} for h in e.get("history") or []]
    out = service.chat(e["user"]["text"], history=hist, chat_id="eval-" + e["id"], user=e["user"]["who"])
    return out.get("messages") or []


def run_group(e, prefix=""):
    members, active, total = room_of(e)
    gid = "g" + uuid.uuid4().hex[:10]
    service.group_create(members[0], {"id": gid, "name": "평가방", "members": members})
    g = store.kv_get("groups", gid)
    g["evalRoom"] = e.get("room") or ""                     # Pie가 보는 방 정보 = 문제의 방 정보 그대로
    if active:
        g["total"] = total                                 # 정산이 진행 중인 방
    store.kv_put("groups", gid, g)
    for h in e.get("history") or []:
        service.group_message(h["who"], gid, {"id": "m" + uuid.uuid4().hex[:8], "from": h["who"], "text": h["text"]})
    mid = "m" + uuid.uuid4().hex[:8]
    service.group_message(e["user"]["who"], gid, {"id": mid, "from": e["user"]["who"], "text": prefix + e["user"]["text"]})
    return service.group_pie(e["user"]["who"], gid, mid) or []


def score(e, msgs, group):
    reply = " ".join(m.get("text") or "" for m in msgs).strip()
    card = any(m.get("split") or m.get("settle") or m.get("compare") or m.get("kind") == "confirm" or m.get("confirmData") for m in msgs)
    ask = any(m.get("needs_info") or m.get("ask") for m in msgs) or reply.endswith("?")
    why = []
    exp = e.get("expect")
    if exp == "card" and not card: why.append("카드 없음")
    if exp == "ask" and not ask: why.append("되묻지 않음")
    if exp == "silent" and msgs: why.append("잡담인데 답함")
    if exp == "refuse" and not REFUSE.search(reply): why.append("거절 안 함")
    if exp != "silent" and not msgs: why.append("답 없음")
    why += [f"빠짐: {w}" for w in e.get("must") or [] if w not in reply]
    if e.get("must_any") and not any(w in reply for w in e["must_any"]): why.append(f"다음 중 하나도 없음: {e['must_any']}")
    why += [f"금지어: {w}" for w in e.get("must_not") or [] if w in reply]
    if e.get("max_chars") and len(reply) > e["max_chars"]: why.append(f"길이 {len(reply)}자 > {e['max_chars']}")
    if e.get("expect_situation"):
        rec = next((m.get("rec") for m in msgs if m.get("rec")), None)
        got = (rec or {}).get("situation", {}).get("read")
        if got != e["expect_situation"] and f"'{e['expect_situation']}'" not in reply:
            why.append(f"상황 판단 {got or '-'} ≠ {e['expect_situation']}")
    return not why, why, reply


rows, t0 = [], time.time()
for e in items:
    runs = [("group", "")] if e["mode"] == "group" else [("chat", "")] + ([("group", "파이야 ")] if a.both_group and e["mode"] == "both" else [])
    for mode, prefix in runs:
        try:
            msgs = run_group(e, prefix) if mode == "group" else run_chat(e)
            ok, why, reply = score(e, msgs, mode == "group")
        except Exception as ex:  # noqa: BLE001
            ok, why, reply = False, [f"오류: {ex}"], ""
        rows.append({"id": e["id"], "mode": mode, "tags": e.get("tags"), "ok": ok, "why": why, "reply": reply[:300]})
        print(f"{'✓' if ok else '✗'} {e['id']} [{mode}] {', '.join(why) if why else ''}")

n = len(rows); p = sum(r["ok"] for r in rows)
print(f"\n== 통과 {p}/{n} ({p / max(1, n):.0%}) · {time.time() - t0:.0f}초 · 버전 {config.APP_VERSION}")
by = collections.defaultdict(lambda: [0, 0])
for r in rows:
    for t in r["tags"] or ["-"]:
        by[t][0] += r["ok"]; by[t][1] += 1
print("   태그별: " + " · ".join(f"{t} {x}/{y}" for t, (x, y) in sorted(by.items())))
out = ROOT / "tests" / "eval_results"
out.mkdir(exist_ok=True)
f = out / f"pie_eval_{config.APP_VERSION}_{time.strftime('%Y%m%d-%H%M')}.jsonl"
f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
print(f"   결과 저장: {f.relative_to(ROOT)}")
