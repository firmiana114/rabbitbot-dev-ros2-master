#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
from collections import defaultdict
from pathlib import Path


SUMMARY_LABELS = [
    "audio_input",
    "plan_llm",
    "chat_llm",
    "chat_tts",
    "action",
    "navi_check",
    "completion_check",
]


def read_records(path):
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def summary_label(span):
    return {
        "audio_input": "audio_input",
        "listen_answer": "audio_input",
        "plan_llm": "plan_llm",
        "chat_llm": "chat_llm",
        "chat_tts": "chat_tts",
        "tts_segment": "chat_tts",
        "arm_action": "action",
        "navi_check": "navi_check",
        "completion_check": "completion_check",
    }.get(span)


def print_profile_summary(records):
    ended_spans = [record for record in records if record.get("event") == "end"]
    stats = {label: {"count": 0, "sum": 0.0} for label in SUMMARY_LABELS}
    loop_iterations = 0
    loop_total = 0.0

    starts = [record for record in records if record.get("event") == "start"]
    if starts and records:
        # JSONL 已经记录了绝对时间，但离线汇总优先使用已结束的 docx_total/loop_iteration 近似总耗时。
        loop_total = sum(float(record.get("elapsed", 0) or 0) for record in ended_spans if record.get("span") == "loop_iteration")

    docx_total = [record for record in ended_spans if record.get("span") == "docx_total"]
    if docx_total:
        loop_total = float(docx_total[-1].get("elapsed", 0) or 0)

    for record in ended_spans:
        elapsed = float(record.get("elapsed", 0) or 0)
        span = record.get("span")
        if span == "loop_iteration":
            loop_iterations += 1
        label = summary_label(span)
        if label:
            stats[label]["count"] += 1
            stats[label]["sum"] += elapsed

    if loop_iterations == 0:
        loop_iterations = len([record for record in ended_spans if record.get("span") == "docx_step"])
    if loop_total == 0.0:
        loop_total = sum(float(record.get("elapsed", 0) or 0) for record in ended_spans if record.get("span") == "docx_step")

    print("========== Workflow Profile Summary ==========")
    print(f"loop_total:{loop_total:>20.3f}s")
    print(f"loop_iterations:{loop_iterations:>9}")
    for label in SUMMARY_LABELS:
        stat = stats[label]
        count = stat["count"]
        avg = stat["sum"] / count if count else 0.0
        print(f"{label + ' (avg):':<22}{avg:>9.3f}s  (×{count})")


def main():
    parser = argparse.ArgumentParser(description="汇总 workflow_profile.jsonl 中的耗时 span")
    parser.add_argument(
        "profile",
        nargs="?",
        default="logs/workflow_profile.jsonl",
        help="profile JSONL 路径，默认 logs/workflow_profile.jsonl",
    )
    parser.add_argument("--top", type=int, default=30, help="输出最慢 span 明细数量")
    args = parser.parse_args()

    profile_path = Path(args.profile)
    if not profile_path.exists():
        raise SystemExit(f"profile 文件不存在: {profile_path}")

    records = list(read_records(profile_path))
    ended_spans = [record for record in records if record.get("event") == "end"]
    if not ended_spans:
        raise SystemExit(f"未找到 end span: {profile_path}")

    print_profile_summary(records)

    groups = defaultdict(list)
    for record in ended_spans:
        groups[record.get("span", "unknown")].append(float(record.get("elapsed", 0) or 0))

    print()
    print("按 span 汇总:")
    print(f"{'span':<24} {'count':>6} {'sum(s)':>10} {'avg(s)':>10} {'max(s)':>10}")
    for span, values in sorted(groups.items(), key=lambda item: sum(item[1]), reverse=True):
        total = sum(values)
        avg = total / len(values)
        max_value = max(values)
        print(f"{span:<24} {len(values):>6} {total:>10.3f} {avg:>10.3f} {max_value:>10.3f}")

    print()
    print(f"最慢 {args.top} 条:")
    for record in sorted(ended_spans, key=lambda item: float(item.get("elapsed", 0) or 0), reverse=True)[:args.top]:
        detail = {
            key: value
            for key, value in record.items()
            if key not in {"event", "span_id", "start_perf"}
        }
        print(json.dumps(detail, ensure_ascii=False))


if __name__ == "__main__":
    main()
