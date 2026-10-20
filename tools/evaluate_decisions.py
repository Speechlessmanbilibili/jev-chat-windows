"""用合成中文场景实测完整 29 题和候选排序，保存原始结果及耗时。"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from datetime import datetime
from pathlib import Path

from app import settings
from core.engine import analyze
from core.jev_client import ask
from core.questions import build_rank_question


def summary(values):
    ordered = sorted(values)
    return {"count": len(values), "p50_ms": round(statistics.median(values), 2),
            "p95_ms": round(ordered[math.ceil(len(values) * .95) - 1], 2)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="d3-mini")
    parser.add_argument("--base-url", default="http://127.0.0.1:1234")
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("decision_cases.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    settings.jev_key("lmstudio")
    results = []
    # 每条高标签预先要求至少 2.5/4，低标签最多 1.5/4，阈值不随结果调整。
    for repetition in range(args.repeat):
        for case in cases:
            start = time.perf_counter()
            analysis = analyze(case["messages"], case["relationship"], reply_to=case.get("reply_to"),
                               jev_provider="lmstudio", jev_model=args.model,
                               jev_base_url=args.base_url, timeout=120)
            analysis_ms = (time.perf_counter() - start) * 1000
            answers = analysis["answers"]
            checks = [{"label": label, "expected": direction, "score": answers[label]["score"],
                       "pass": answers[label]["score"] >= 2.5 if direction == "high"
                       else answers[label]["score"] <= 1.5}
                      for direction in ("high", "low") for label in case[direction]]
            start = time.perf_counter()
            ranking = ask(analysis["state"], build_rank_question(case["replies"]),
                          provider="lmstudio", model=args.model, base_url=args.base_url, timeout=120)
            ranking_ms = (time.perf_counter() - start) * 1000
            expected = ("reply_a", "reply_b", "reply_c")[case["best"]]
            actual = ranking["answers"]["best_reply"]["choice"]
            row = {"case": case["id"], "repetition": repetition + 1, "analysis_ms": analysis_ms,
                   "ranking_ms": ranking_ms, "checks": checks, "ranking_expected": expected,
                   "ranking_actual": actual, "ranking_pass": actual == expected,
                   "answers": answers, "ranking": ranking}
            results.append(row)
            print(f"{repetition + 1}/{args.repeat} {case['id']}: "
                  f"分析 {analysis_ms:.0f} ms，排序 {ranking_ms:.0f} ms，"
                  f"标签 {sum(c['pass'] for c in checks)}/{len(checks)}，排序 {actual == expected}", flush=True)
    checks = [c for row in results for c in row["checks"]]
    report = {"created_at": datetime.now().astimezone().isoformat(), "model": args.model,
              "base_url": args.base_url, "cases": cases, "repeat": args.repeat,
              "thresholds": {"high_min": 2.5, "low_max": 1.5},
              "summary": {"checks_passed": sum(c["pass"] for c in checks), "checks_total": len(checks),
                          "ranking_passed": sum(r["ranking_pass"] for r in results),
                          "ranking_total": len(results),
                          "first_analysis_ms": results[0]["analysis_ms"],
                          "warm_analysis": summary([r["analysis_ms"] for r in results[1:]]),
                          "ranking": summary([r["ranking_ms"] for r in results])}, "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
