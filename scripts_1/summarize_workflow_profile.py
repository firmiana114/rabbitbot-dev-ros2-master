#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
from collections import defaultdict
from pathlib import Path


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

    ended_spans = [record for record in read_records(profile_path) if record.get("event") == "end"]
    if not ended_spans:
        raise SystemExit(f"未找到 end span: {profile_path}")

    groups = defaultdict(list)
    for record in ended_spans:
        groups[record.get("span", "unknown")].append(float(record.get("elapsed", 0) or 0))

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
