"""오답 노트 — 베타 데이터에서 Pie가 틀린 사례를 모아 다음 학습·평가 재료로 (가이드라인 ⑤ + 작업 순서 '베타에서 틀린 문장 추가').

  python scripts/wrong_notes.py <베타 데이터 폴더>      (없으면 이 PC의 베타 폴더)

만드는 것 (같은 폴더의 notes/):
  wrong_notes.md        사람이 읽는 오답 노트: 👎 이유별 사례 · 목적 정정(읽은 목적 → 사용자가 고른 목적) 표
  eval_candidates.jsonl pie_eval.jsonl에 넣을 문제 후보 (기대 답은 사람이 채워 넣기 — 'todo')
  calc_candidates.jsonl '금액이 틀렸어요' 문장 → calc_eval.jsonl 후보 (정답 분담표는 사람이 채우기)
"""
import collections, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if len(sys.argv) > 1:
    base = Path(sys.argv[1])
else:
    from agent import beta
    base = beta.DIR
rd = lambda n: [json.loads(l) for l in (base / n).open(encoding="utf-8") if l.strip()] if (base / n).exists() else []
D = {d["turn"]: d for d in rd("dialogs.jsonl")}
FB, PF = rd("feedback.jsonl"), rd("pie_feedback.jsonl")
out = base / "notes"
out.mkdir(exist_ok=True)

downs = [(f, D.get(f["turn"])) for f in FB if f.get("rating") == "down"]
by_reason = collections.defaultdict(list)
for f, d in downs:
    by_reason[f.get("reason") or "이유 없음"].append((f, d))
md = [f"# 오답 노트 — {base.name}", "", f"👎 {len(downs)}건 (대화가 저장된 것 {sum(1 for _, d in downs if d)}건) · 목적 정정 {sum(1 for r in PF if r.get('event') == 'correct')}건", ""]
for reason, xs in sorted(by_reason.items(), key=lambda x: -len(x[1])):
    md += [f"## {reason} ({len(xs)}건)", ""]
    for f, d in xs:
        if d:
            md += [f"- **사용자**: {d.get('user', '')[:120]}", f"  - Pie: {(d.get('reply') or '')[:160]}", f"  - 태그 {d.get('tags')} · {d.get('channel')} · {d.get('scenario') or '자유'}" + (f" · 의견: {f['note']}" if f.get("note") else "")]
    md.append("")
cor = [r for r in PF if r.get("event") == "correct"]
if cor:
    cm = collections.Counter((r.get("read"), r.get("gold")) for r in cor)
    md += ["## 목적 정정 — 읽은 목적 → 사용자가 고른 목적", "", "| 읽은 목적 | 고른 목적 | 건수 |", "|---|---|---|"]
    md += [f"| {a} | {b} | {n} |" for (a, b), n in cm.most_common()]
    rates = [r["satisfaction"] for r in PF if r.get("event") == "rate"]
    if rates:
        md += ["", f"만족도 평균 {sum(rates) / len(rates):.2f}점 ({len(rates)}건)"]
(out / "wrong_notes.md").write_text("\n".join(md) + "\n", encoding="utf-8")

ev, ce = [], []
for i, (f, d) in enumerate(downs, 1):
    if not d:
        continue
    item = {"id": f"bt-{i:03d}", "tags": d.get("tags") or ["offtopic"], "mode": "group" if d.get("channel") == "group" else "chat",
            "user": {"who": "가온", "text": d["user"]}, "todo": "기대 답(expect·must·must_not)을 채워 넣기",
            "bad": (d.get("reply") or "")[:200], "why_bad": f.get("reason")}
    ev.append(item)
    if f.get("reason") == "금액이 틀렸어요":
        ce.append({"id": f"ce-b{i:02d}", "text": d["user"], "todo": "정답 분담표(expected)를 채워 넣기", "bad": (d.get("reply") or "")[:200]})
(out / "eval_candidates.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in ev), encoding="utf-8")
(out / "calc_candidates.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in ce), encoding="utf-8")
print(f"오답 노트: {out / 'wrong_notes.md'}\n평가 후보 {len(ev)}개 · 계산 후보 {len(ce)}개 → {out}")
