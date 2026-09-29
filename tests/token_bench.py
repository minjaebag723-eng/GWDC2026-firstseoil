"""토큰 효율 증명 벤치 — 같은 워크플로를 기준선(PIE_EFFICIENT=0)과 효율 설계(PIE_EFFICIENT=1)로 한 번씩 돌려
워크플로 단계별로 비교하고, 계산 결과가 같은지(효율화가 정확도를 해치지 않았는지)까지 검증한다.

  python tests/token_bench.py              ← 서버 PC (.env: 실제 Kiln · KILN_MODEL=qwen3-32b). 임시 데이터 폴더 · 모의 체인
  python tests/token_bench.py --repeat 2   ← 장면마다 2번씩 (AI 답의 흔들림을 평균)

결과: docs/evidence/token_efficiency_<시각>.md · .json  (심사 기준: 단계별 토큰 · 불필요한 추론 감소 · 에너지 가정)
"""
import argparse
import collections
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = [
    ("chat", "S01 똑같이 나누기", ["삼겹살 38,900원 넷이 똑같이 나눠줘"], {"total": 38900, "n": 4}),
    ("chat", "S02 여러 조건", ["치킨 2만 피자 1.8만 배달비 3천 넷이 나누는데 민재는 5천원 덜 내게 해줘"], {"total": 41000, "n": 4}),
    ("chat", "S03 퍼센트", ["한정식 15만원인데 부가세 10% 별도래 여섯이 나눠줘"], {"total": 165000, "n": 6}),
    ("chat", "S04 조건 변경", ["숙소 30만원 넷이 나눠줘", "아 총액 32만원이었어"], {"total": 320000, "n": 4}),
    ("chat", "S05 모호 → 되묻기", ["총 5만원인데 진주는 조금 더 내게 해줘"], {"ask": True}),
    ("chat", "S08 추천(가격)", ["월말이라 거지다 넷이 치킨 시키자 6만원 안에서"], {"card": True}),
    ("chat", "S13 사용법", ["AI 요금제는 어떻게 돼?"], {}),
    ("chat", "주제 밖", ["오늘 날씨 어때?"], {}),
    ("group", "S11 이름 부르기", ["파이야"], {}),
    ("group", "그룹 똑같이", ["파이야 8만원 넷이 똑같이 나눠"], {"total": 80000, "n": 4}),
    ("group", "S06 지출 한도", ["파이야 8만원 넷이 똑같이 나누는데 1인 1만5천원 넘으면 안 돼"], {"warn": True}),
]


def child(mode: str, repeat: int) -> dict:
    """한 가지 설정으로 모든 장면을 돌리고 usage.jsonl을 모아 돌려준다 (부모가 PIE_EFFICIENT를 정해 새 프로세스로 부름)."""
    sys.path.insert(0, str(ROOT))
    from agent import config, llm, service, store  # noqa: E402
    info = {"mode": mode, "efficient": config.PIE_EFFICIENT, "model": config.KILN_MODEL, "llm_mode": config.LLM_MODE,
            "reasoning_effort": config.KILN_REASONING_EFFORT, "npu_watts": config.NPU_POWER_WATTS, "npu_count": config.NPU_COUNT,
            "base_url_host": (config.KILN_BASE_URL or "").split("/")[2] if "//" in (config.KILN_BASE_URL or "") else config.KILN_BASE_URL}
    if config.LLM_MODE == "live":
        try:
            import httpx
            r = httpx.get(config.KILN_BASE_URL.rstrip("/") + "/models", headers={"Authorization": f"Bearer {config.KILN_API_KEY}"}, timeout=15)
            ids = [m.get("id") for m in (r.json().get("data") or [])]
            info.update(models=ids[:30], model_available=config.KILN_MODEL in ids)
        except Exception as e:  # noqa: BLE001
            info.update(models_error=str(e)[:160])
    results = []
    for rep in range(repeat):
        gid = f"gbench{mode}{rep}"
        service.group_create("벤치", {"id": gid, "name": "벤치방", "members": ["벤치", "진주", "민재", "지현"]})
        for ch, label, turns, exp in SCENARIOS:
            before = sum(1 for _ in open(Path(config.DATA_DIR) / "usage.jsonl", encoding="utf-8")) if (Path(config.DATA_DIR) / "usage.jsonl").exists() else 0
            out, hist = [], []
            for t in turns:
                if ch == "chat":
                    r = service.chat(t, history=hist, chat_id=f"bench-{label}-{rep}", user="벤치")
                    msgs = r.get("messages") or []
                    hist += [{"role": "user", "text": t}] + [{"role": "bot", "text": m.get("text", ""), "intent": m.get("intent"),
                                                                "needs_info": bool(m.get("needs_info"))} for m in msgs if m.get("text")]
                else:
                    mid = "m" + os.urandom(4).hex()
                    service.group_message("벤치", gid, {"id": mid, "from": "벤치", "text": t})
                    msgs = service.group_pie("벤치", gid, mid) or []
                out = msgs
            split = next((m.get("split") for m in out if m.get("split")), None)
            an = next((m.get("analysis") for m in out if m.get("analysis")), None)
            shares = split or (an or {}).get("shares")
            results.append({"label": label, "rep": rep, "channel": ch, "usage_from": before,
                            "shares": shares, "total": sum(a for _, a in shares) if shares else None,
                            "card": any(m.get("compare") for m in out), "ask": any(m.get("needs_info") for m in out) or "?" in " ".join(m.get("text") or "" for m in out),
                            "warn": bool((an or {}).get("warnings")), "text": " ".join(m.get("text") or "" for m in out)[:160]})
    rows = [json.loads(line) for line in open(Path(config.DATA_DIR) / "usage.jsonl", encoding="utf-8")] if (Path(config.DATA_DIR) / "usage.jsonl").exists() else []
    for i, r in enumerate(results):
        end = results[i + 1]["usage_from"] if i + 1 < len(results) else len(rows)
        r["usage"] = rows[r["usage_from"]:end]
    return {"info": info, "results": results}


AI = ("tools", "json", "text")


def summarize(run: dict) -> dict:
    by = collections.defaultdict(lambda: {"calls": 0, "code": 0, "pt": 0, "ct": 0, "ms": 0, "wh": 0.0})
    for r in run["results"]:
        for u in r["usage"]:
            b = by[u.get("stage")]
            if u.get("mode") in AI:
                b["calls"] += 1; b["pt"] += u.get("prompt_tokens") or 0; b["ct"] += u.get("completion_tokens") or 0
                b["ms"] += u.get("latency_ms") or 0; b["wh"] += u.get("energy_wh") or 0
            elif u.get("mode") == "code":
                b["code"] += 1
    return by


def scen_tokens(run: dict) -> dict:
    out = collections.defaultdict(lambda: [0, 0])
    for r in run["results"]:
        ai = [u for u in r["usage"] if u.get("mode") in AI]
        out[r["label"]][0] += sum(u.get("total_tokens") or 0 for u in ai)
        out[r["label"]][1] += len(ai)
    return out


def pct(a, b):
    return f"{(b - a) / a * 100:+.0f}%" if a else "—"


def report(base: dict, eff: dict, repeat: int) -> str:
    sb, se = summarize(base), summarize(eff)
    stages = sorted(set(sb) | set(se), key=lambda s: -(sb[s]["pt"] + sb[s]["ct"]))
    tot = lambda s, k: sum(v[k] for v in s.values())
    i = eff["info"]
    L = [f"# 토큰 효율 증명 — 같은 워크플로, 기준선 vs 효율 설계", "",
         f"- 모델: **{i['model']}** (Kiln · `{i.get('base_url_host')}`) · 모드 {i['llm_mode']} · "
         + ("긴 사고 끄기 `/no_think` (분쟁 판정·구매 계획만 사고)" if "qwen3" in (i['model'] or "").lower() else f"reasoning_effort={i.get('reasoning_effort') or '보내지 않음'}")
         + (f" · Kiln 모델 목록에 있음: **{i.get('model_available')}**" if 'model_available' in i else ""),
         f"- 장면 {len(SCENARIOS)}개 × {repeat}회 · 같은 입력 · 체인은 모의(토큰 비교가 목적) · 임시 데이터 폴더",
         f"- 기준선 = `PIE_EFFICIENT=0` (효율 설계 끔) · 효율 = `PIE_EFFICIENT=1`", "",
         "## 전체", "", "| | 기준선 | 효율 설계 | 변화 |", "|---|---|---|---|",
         f"| Kiln 호출 | {tot(sb, 'calls')} | {tot(se, 'calls')} | {pct(tot(sb, 'calls'), tot(se, 'calls'))} |",
         f"| 입력 토큰 | {tot(sb, 'pt'):,} | {tot(se, 'pt'):,} | {pct(tot(sb, 'pt'), tot(se, 'pt'))} |",
         f"| 출력 토큰 | {tot(sb, 'ct'):,} | {tot(se, 'ct'):,} | {pct(tot(sb, 'ct'), tot(se, 'ct'))} |",
         f"| 토큰 합계 | {tot(sb, 'pt') + tot(sb, 'ct'):,} | {tot(se, 'pt') + tot(se, 'ct'):,} | {pct(tot(sb, 'pt') + tot(sb, 'ct'), tot(se, 'pt') + tot(se, 'ct'))} |",
         f"| Kiln 응답 시간 합 | {tot(sb, 'ms') / 1000:.1f}초 | {tot(se, 'ms') / 1000:.1f}초 | {pct(tot(sb, 'ms'), tot(se, 'ms'))} |",
         f"| 에너지 추정(상한) | {tot(sb, 'wh'):.3f} Wh | {tot(se, 'wh'):.3f} Wh | {pct(tot(sb, 'wh'), tot(se, 'wh'))} |",
         f"| AI 없이 코드로 처리한 단계 | {tot(sb, 'code')} | {tot(se, 'code')} | |", "",
         "## 워크플로 단계별", "", "| 단계 | 호출 (기준→효율) | 입력 토큰 | 출력 토큰 | 에너지 Wh | 코드 처리 |", "|---|---|---|---|---|---|"]
    for s in stages:
        a, b = sb[s], se[s]
        L.append(f"| {s} | {a['calls']} → {b['calls']} | {a['pt']:,} → {b['pt']:,} ({pct(a['pt'], b['pt'])}) | {a['ct']:,} → {b['ct']:,} | "
                 f"{a['wh']:.3f} → {b['wh']:.3f} | {a['code']} → {b['code']} |")
    tb, te = scen_tokens(base), scen_tokens(eff)
    L += ["", "## 장면별 토큰 (AI 호출 수)", "", "| 장면 | 기준선 | 효율 설계 | 변화 |", "|---|---|---|---|"]
    for _, label, _, _ in SCENARIOS:
        L.append(f"| {label} | {tb[label][0]:,} ({tb[label][1]}회) | {te[label][0]:,} ({te[label][1]}회) | {pct(tb[label][0], te[label][0])} |")
    L += ["", "## 결과 동일성 — 효율화가 계산을 바꾸지 않았는지", "", "| 장면 | 기대 | 기준선 | 효율 설계 | 같음 |", "|---|---|---|---|---|"]
    same_all = True
    for (ch, label, _, exp) in SCENARIOS:
        rb = [r for r in base["results"] if r["label"] == label]
        re_ = [r for r in eff["results"] if r["label"] == label]
        if not exp:                                     # 자유 답 장면(사용법·주제 밖·이름 부르기): 표현은 달라도 되니 '답이 나왔는지'만
            f = lambda rs: "답함" if rs and all((r["text"] or "").strip() for r in rs) else "답 없음"
        else:
            f = lambda rs: ("카드" if rs and all(r["card"] for r in rs) else "되묻기" if rs and all(r["ask"] for r in rs) else
                            "한도 경고" if rs and all(r["warn"] for r in rs) else
                            ", ".join(sorted({f"{r['total']:,}원/{len(r['shares'])}명" for r in rs if r["shares"]})) or "답만")
        want = ("카드" if exp.get("card") else "되묻기" if exp.get("ask") else "한도 경고" if exp.get("warn") else
                f"{exp['total']:,}원/{exp['n']}명" if exp.get("total") else "답함")
        same = f(rb) == f(re_)
        if exp.get("total") and not exp.get("warn"):
            same = same and all(r["total"] == exp["total"] and len(r["shares"] or []) == exp["n"] for r in rb + re_ if r["shares"])
            amt = lambda rs: [sorted(a for _, a in (r["shares"] or [])) for r in rs]     # 금액으로 비교 (자리 이름은 AI마다 다를 수 있음)
            same = same and amt(rb) == amt(re_)
        same_all &= same
        L.append(f"| {label} | {want} | {f(rb)} | {f(re_)} | {'✓' if same else '✗'} |")
    L += ["", f"**{'모든 장면에서 결과가 같아요 — 효율화가 정확도를 해치지 않았어요.' if same_all else '결과가 다른 장면이 있어요 — 위 표를 확인하세요.'}**", "",
          "## 효율 설계 (무엇을, 어느 단계에서)", "",
          "| # | 설계 | 단계 | 줄이는 것 |", "|---|---|---|---|",
          "| E1 | 요청 종류별로 필요한 도구 설명만 보냄 (음식→메뉴 검색·조합 · 여행→여행 검색 · 사용법→도구 없음) | assistant.step | 호출마다 되풀이되는 도구 설명 입력 토큰 |",
          "| E2 | 금액·인원만 있는 단순 나누기는 코드 해석 (AI 해석 생략) | settlement.analyze | AI 호출 자체 (0 토큰) |",
          "| E3 | 똑같이 나눈 결과는 문장 틀로 설명 | settlement.explain | AI 호출 자체 (0 토큰) |",
          "| E4 | 그룹방에서 '파이야'만 부르면 코드가 안내 | group.pie | AI 호출 자체 (0 토큰) |",
          "| E5 | 예시 3→2개 · 지식은 사용법·상태 질문일 때만 2조각 | 프롬프트(모든 Pie 호출) | 입력 토큰 |",
          "| E6 | 대화 기록 최근 8→6개 · 400→300자 | 프롬프트 | 입력 토큰 |",
          "| E7 | qwen3-32b · `/no_think` 긴 사고 끄기 (분쟁 판정·구매 계획만 사고 허용) | 모든 AI 호출 | 추론(출력) 토큰 |",
          "| — | 금액 계산·검증·지출 통제·온체인은 처음부터 코드 | settlement.calculate 등 | AI 추론을 쓰지 않음 |", "",
          "## 에너지 추정 가정", "",
          f"- 호출마다 **실제로 잰 Kiln 응답 시간(초) × NPU 전력 {i['npu_watts']:g} W × NPU {i['npu_count']:g}개 ÷ 3600** = Wh (`agent/usage.py`).",
          "- 그 시간 동안 NPU가 이 요청만 처리했다고 보는 **상한값**이에요. 실제 서버는 여러 요청을 묶어 처리하므로 요청당 에너지는 이보다 작아요.",
          "- 전력 값은 `.env`의 `NPU_POWER_WATTS`·`NPU_COUNT`로 바꿀 수 있어요 (Kiln이 쓰는 NPU 보드의 전력 사양에 맞춰 넣으세요).",
          "- 코드로 처리한 단계는 NPU를 쓰지 않으므로 0 Wh예요.", "",
          "재현: `python tests/token_bench.py` · 원자료: 같은 이름의 `.json` (호출별 usage 행 포함)"]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--child", choices=["base", "eff"])
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.child:
        res = child(a.child, a.repeat)
        Path(a.out).write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        return
    runs = {}
    for mode, flag in (("base", "0"), ("eff", "1")):
        tmp = tempfile.mkdtemp(prefix=f"sp-bench-{mode}-")
        out = Path(tmp) / "result.json"
        env = {**os.environ, "PIE_EFFICIENT": flag, "DATA_DIR": tmp, "CHAIN_MODE": "mock", "APP_VERSION": f"bench-{mode}", "BETA_ENABLED": "0"}
        print(f"== {'기준선' if mode == 'base' else '효율 설계'} (PIE_EFFICIENT={flag}) 실행 중…", flush=True)
        t0 = time.time()
        subprocess.run([sys.executable, __file__, "--child", mode, "--repeat", str(a.repeat), "--out", str(out)], env=env, check=True, cwd=ROOT)
        runs[mode] = json.loads(out.read_text(encoding="utf-8"))
        print(f"   {time.time() - t0:.0f}초", flush=True)
    md = report(runs["base"], runs["eff"], a.repeat)
    d = ROOT / "docs" / "evidence"; d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M")
    (d / f"token_efficiency_{stamp}.md").write_text(md, encoding="utf-8")
    (d / f"token_efficiency_{stamp}.json").write_text(json.dumps(runs, ensure_ascii=False), encoding="utf-8")
    print("\n" + "\n".join(md.splitlines()[:16]))
    print(f"\n보고서: docs/evidence/token_efficiency_{stamp}.md")


if __name__ == "__main__":
    main()
