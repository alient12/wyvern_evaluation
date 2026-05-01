#!/usr/bin/env python3
import argparse
import json
import math
from collections import defaultdict


def is_finite_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def format_number(x):
    if isinstance(x, bool):
        return "1" if x else "0"

    if isinstance(x, int):
        return str(x)

    if isinstance(x, float):
        if x.is_integer():
            return str(int(x))
        return format(x, ".15g")

    return str(x)


def make_eq_trigger(arg_index, value):
    return f"arg{arg_index} == {format_number(value)}"


def make_iqr_trigger(arg_index, lower, upper):
    left = f"arg{arg_index} < {format_number(lower)}" if lower is not None else None
    right = f"arg{arg_index} > {format_number(upper)}" if upper is not None else None

    if left and right:
        return f"{left} || {right}"
    if left:
        return left
    if right:
        return right
    return None


def dedup_preserve_order(items):
    out = []
    seen = set()
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def build_triggers_for_entry(entry, max_rare_values=5):
    triggers = []

    arg_index = entry.get("arg_index")
    if not isinstance(arg_index, int):
        return triggers

    slowest_value = entry.get("slowest_value")
    if is_finite_number(slowest_value):
        triggers.append(make_eq_trigger(arg_index, slowest_value))

    model = entry.get("model")
    if not isinstance(model, dict):
        return dedup_preserve_order(triggers)

    method = model.get("method")

    if method == "iqr":
        lower = model.get("lower_bound")
        upper = model.get("upper_bound")

        if lower is not None and not is_finite_number(lower):
            lower = None
        if upper is not None and not is_finite_number(upper):
            upper = None

        trig = make_iqr_trigger(arg_index, lower, upper)
        if trig:
            triggers.append(trig)

    elif method == "discrete_frequency_support":
        rare_values = model.get("rare_values", [])
        count = 0
        for v in rare_values:
            if is_finite_number(v):
                triggers.append(make_eq_trigger(arg_index, v))
                count += 1
                if count >= max_rare_values:
                    break

    return dedup_preserve_order(triggers)


def group_entries_by_function(entries):
    groups = defaultdict(list)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        fn = entry.get("function")
        if isinstance(fn, str) and fn:
            groups[fn].append(entry)
    return groups


def function_total_calls(entries):
    best = 0
    for entry in entries:
        c = entry.get("total_function_calls", 0)
        if isinstance(c, int) and c > best:
            best = c
    return best


def build_target_for_function(function_name, entries):
    entries = sorted(
        entries,
        key=lambda e: (
            e.get("arg_index") if isinstance(e.get("arg_index"), int) else 10**9
        )
    )

    triggers = []
    for entry in entries:
        triggers.extend(build_triggers_for_entry(entry))

    triggers = dedup_preserve_order(triggers)

    return {
        "Func": function_name,
        "Recursive": False,
        "TriggerFunc": function_name,
        "Triggers": triggers if triggers else ["1 == 1"]
    }


def build_always_on_target(function_name):
    return {
        "Func": function_name,
        "Recursive": False,
        "TriggerFunc": function_name,
        "Triggers": ["1 == 1"]
    }


def build_always_off_target(function_name):
    return {
        "Func": function_name,
        "Recursive": False,
        "TriggerFunc": function_name,
        "Triggers": ["1 == 0"]
    }


def yaml_quote_string(s):
    if s == "":
        return '""'

    special_chars = [":", "#", "{", "}", "[", "]", ",", "&", "*", "?", "|", ">", "!", "%", "@", "`"]
    if (
        s.strip() != s
        or any(ch in s for ch in special_chars)
        or "&&" in s
        or "||" in s
        or "==" in s
        or "<" in s
        or ">" in s
    ):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

    return s


def dump_yaml_config(targets, logs_dir):
    lines = []
    lines.append("TraceCondition:")
    lines.append(f"  LogsDir: {logs_dir}")
    lines.append("  Targets:")

    for target in targets:
        lines.append(f"  - Func: {yaml_quote_string(target['Func'])}")
        lines.append(f"    Recursive: {'true' if target['Recursive'] else 'false'}")
        lines.append(f"    TriggerFunc: {yaml_quote_string(target['TriggerFunc'])}")
        lines.append("    Triggers:")
        for trig in target["Triggers"]:
            lines.append(f"      - {yaml_quote_string(trig)}")

    return "\n".join(lines) + "\n"


def parse_complexity_file(path):
    out = []

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue

            parts = s.split(None, 1)
            if len(parts) != 2:
                continue

            cc_text, func_name = parts
            try:
                cc = int(cc_text)
            except ValueError:
                continue

            func_name = func_name.strip()
            if not func_name:
                continue

            out.append({
                "function": func_name,
                "complexity": cc
            })

    return out


def select_from_candidates(candidates, available_functions, used_functions, count, min_calls):
    selected = []

    for item in candidates:
        fn = item["function"]

        if fn in used_functions:
            continue
        if fn not in available_functions:
            continue

        entries = available_functions[fn]
        total_calls = function_total_calls(entries)
        if total_calls < min_calls:
            continue

        selected.append(item)
        used_functions.add(fn)

        if len(selected) >= count:
            break

    return selected


def choose_complexity_buckets(complexity_rows, available_functions, min_calls):
    n = len(complexity_rows)
    if n == 0:
        return []

    used_functions = set()

    top_candidates = complexity_rows
    top_selected = select_from_candidates(
        top_candidates, available_functions, used_functions, count=3, min_calls=min_calls
    )

    bottom_candidates = list(reversed(complexity_rows))
    bottom_selected = select_from_candidates(
        bottom_candidates, available_functions, used_functions, count=3, min_calls=min_calls
    )

    center = n // 2
    middle_candidates = []
    left = center
    right = center + 1

    if 0 <= center < n:
        middle_candidates.append(complexity_rows[center])

    while left - 1 >= 0 or right < n:
        if left - 1 >= 0:
            left -= 1
            middle_candidates.append(complexity_rows[left])
        if right < n:
            middle_candidates.append(complexity_rows[right])
            right += 1

    middle_selected = select_from_candidates(
        middle_candidates, available_functions, used_functions, count=3, min_calls=min_calls
    )

    return [
        ("high", x) for x in top_selected
    ] + [
        ("mid", x) for x in middle_selected
    ] + [
        ("low", x) for x in bottom_selected
    ]


def process_files(analysis_path, complexity_path, output_path, always_on_output_path, always_off_output_path, logs_dir, min_calls):
    with open(analysis_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Analysis JSON must contain a list")

    available_functions = group_entries_by_function(data)
    complexity_rows = parse_complexity_file(complexity_path)

    selected = choose_complexity_buckets(
        complexity_rows=complexity_rows,
        available_functions=available_functions,
        min_calls=min_calls,
    )

    normal_targets = []
    always_on_targets = []
    always_off_targets = []

    for bucket_name, item in selected:
        fn = item["function"]
        entries = available_functions[fn]

        normal_targets.append(build_target_for_function(fn, entries))
        always_on_targets.append(build_always_on_target(fn))
        always_off_targets.append(build_always_off_target(fn))
    normal_yaml = dump_yaml_config(normal_targets, logs_dir=logs_dir)
    always_on_yaml = dump_yaml_config(always_on_targets, logs_dir=logs_dir)
    always_off_yaml = dump_yaml_config(always_off_targets, logs_dir=logs_dir)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(normal_yaml)

    with open(always_on_output_path, "w", encoding="utf-8") as f:
        f.write(always_on_yaml)

    with open(always_off_output_path, "w", encoding="utf-8") as f:
        f.write(always_off_yaml)

    print(f"[done] selected_targets={len(normal_targets)}")
    print(f"[done] normal_config={output_path}")
    print(f"[done] always_on_config={always_on_output_path}")
    print(f"[done] always_off_config={always_off_output_path}")
    print(f"[info] high={sum(1 for b, _ in selected if b == 'high')}")
    print(f"[info] mid={sum(1 for b, _ in selected if b == 'mid')}")
    print(f"[info] low={sum(1 for b, _ in selected if b == 'low')}")


def parse_args():
    p = argparse.ArgumentParser(
        description="Generate normal and always-on tracer configs from analysis JSON and complexity.txt"
    )
    p.add_argument("analysis_input", help="Input JSON from previous analysis/model script")
    p.add_argument("complexity_input", help="Input complexity.txt sorted by cyclomatic complexity")
    p.add_argument("output", help="Output normal config.yaml")
    p.add_argument("always_on_output", help="Output always-on config.yaml")
    p.add_argument("always_off_output", help="Output always-off config.yaml")
    p.add_argument(
        "--logs-dir",
        default="./tracer_logs",
        help="LogsDir value for YAML (default: ./tracer_logs)"
    )
    p.add_argument(
        "--min-calls",
        type=int,
        default=2,
        help="Minimum total_function_calls required to consider a function (default: 2)"
    )
    return p.parse_args()


def main():
    args = parse_args()
    process_files(
        analysis_path=args.analysis_input,
        complexity_path=args.complexity_input,
        output_path=args.output,
        always_on_output_path=args.always_on_output,
        always_off_output_path=args.always_off_output,
        logs_dir=args.logs_dir,
        min_calls=args.min_calls,
    )


if __name__ == "__main__":
    main()