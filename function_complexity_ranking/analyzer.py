#!/usr/bin/env python3
import argparse
import json
import math


def weighted_quantile_from_counts(value_counts, q):
    """
    Exact quantile from compressed distribution.
    value_counts: list of {"value": x, "count": c}
    q in [0,1]
    """
    if not value_counts:
        return None

    pairs = []
    total = 0
    for item in value_counts:
        v = item.get("value")
        c = item.get("count", 0)

        if isinstance(v, bool):
            v = int(v)

        if not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        if not isinstance(c, int) or c <= 0:
            continue
        if not math.isfinite(float(v)):
            continue

        pairs.append((float(v), c))
        total += c

    if not pairs or total == 0:
        return None

    pairs.sort(key=lambda x: x[0])

    target = q * (total - 1)
    cumulative = 0
    for value, count in pairs:
        next_cum = cumulative + count
        if target < next_cum:
            return value
        cumulative = next_cum

    return pairs[-1][0]


def is_integer_like_type(type_name):
    if not type_name:
        return False
    t = type_name.strip().lower()
    integer_names = {
        "char", "signed char", "unsigned char",
        "short", "short int", "unsigned short", "unsigned short int",
        "int", "unsigned int",
        "long", "long int", "unsigned long", "unsigned long int",
        "long long", "long long int", "unsigned long long", "unsigned long long int",
        "int8_t", "int16_t", "int32_t", "int64_t",
        "uint8_t", "uint16_t", "uint32_t", "uint64_t",
        "size_t", "ssize_t", "_bool", "bool"
    }
    return t in integer_names


def build_discrete_model(entry, rare_ratio_threshold, rare_count_threshold):
    """
    For low-cardinality discrete args:
    - keep common observed values
    - mark infrequent ones as rare
    """
    numeric_count = entry.get("numeric_count", 0)
    values = entry.get("value_counts", [])

    common_values = []
    rare_values = []

    for item in values:
        v = item.get("value")
        c = item.get("count", 0)

        if not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        if not isinstance(c, int) or c <= 0:
            continue

        ratio = c / numeric_count if numeric_count else 0.0

        if c < rare_count_threshold or ratio < rare_ratio_threshold:
            rare_values.append({
                "value": v,
                "count": c,
                "ratio": ratio
            })
        else:
            common_values.append({
                "value": v,
                "count": c,
                "ratio": ratio
            })

    common_values.sort(key=lambda x: (-x["count"], x["value"]))
    rare_values.sort(key=lambda x: (x["count"], x["value"]))

    return {
        "method": "discrete_frequency_support",
        "normal_values": [x["value"] for x in common_values],
        "rare_values": [x["value"] for x in rare_values],
        "normal_value_stats": common_values,
        "rare_value_stats": rare_values,
    }


def build_iqr_model(entry, fence_multiplier):
    """
    For continuous-ish args:
    Tukey IQR fences.
    """
    q1 = weighted_quantile_from_counts(entry.get("value_counts", []), 0.25)
    q3 = weighted_quantile_from_counts(entry.get("value_counts", []), 0.75)

    if q1 is None or q3 is None:
        return {
            "method": "iqr",
            "q1": None,
            "q3": None,
            "iqr": None,
            "lower_bound": None,
            "upper_bound": None,
        }

    iqr = q3 - q1
    lower = q1 - fence_multiplier * iqr
    upper = q3 + fence_multiplier * iqr

    type_name = entry.get("type_name", "")
    if is_integer_like_type(type_name):
        lower = math.floor(lower)
        upper = math.ceil(upper)

    return {
        "method": "iqr",
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "lower_bound": lower,
        "upper_bound": upper,
    }


def choose_model(entry, discrete_unique_threshold, integer_only_discrete):
    """
    Decide whether an arg should be modeled as discrete or continuous.
    """
    values = entry.get("value_counts", [])
    type_name = entry.get("type_name", "")

    valid_numeric_values = [
        item for item in values
        if isinstance(item.get("value"), (int, float))
        and not isinstance(item.get("value"), bool)
        and isinstance(item.get("count"), int)
        and item.get("count", 0) > 0
    ]

    unique_count = len(valid_numeric_values)
    integer_like = is_integer_like_type(type_name)

    if integer_only_discrete:
        if integer_like and unique_count <= discrete_unique_threshold:
            return "discrete"
        return "iqr"

    if unique_count <= discrete_unique_threshold:
        return "discrete"
    return "iqr"


def find_slowest_value(value_counts):
    """
    Return the value whose avg_time is the highest.
    If tie: prefer higher avg_time, then higher count, then smaller value when comparable.
    """
    best = None

    for item in value_counts:
        v = item.get("value")
        c = item.get("count", 0)
        avg_time = item.get("avg_time")

        if not isinstance(avg_time, (int, float)) or not math.isfinite(float(avg_time)):
            continue
        if not isinstance(c, int):
            c = 0

        candidate = {
            "value": v,
            "count": c,
            "avg_time": float(avg_time),
        }

        if best is None:
            best = candidate
            continue

        if candidate["avg_time"] > best["avg_time"]:
            best = candidate
            continue

        if candidate["avg_time"] == best["avg_time"]:
            if candidate["count"] > best["count"]:
                best = candidate
                continue

            if candidate["count"] == best["count"]:
                try:
                    if candidate["value"] < best["value"]:
                        best = candidate
                except Exception:
                    pass

    return best


def build_range_entry(
    entry,
    discrete_unique_threshold,
    rare_ratio_threshold,
    rare_count_threshold,
    fence_multiplier,
    integer_only_discrete,
):
    function_name = entry.get("function")
    arg_index = entry.get("arg_index")
    arg_name = entry.get("arg_name")
    type_name = entry.get("type_name")
    numeric_count = entry.get("numeric_count", 0)
    total_function_calls = entry.get("total_function_calls", 0)
    avg_time = entry.get("avg_time")
    value_counts = entry.get("value_counts", [])

    model_kind = choose_model(
        entry,
        discrete_unique_threshold=discrete_unique_threshold,
        integer_only_discrete=integer_only_discrete,
    )

    if model_kind == "discrete":
        model = build_discrete_model(
            entry,
            rare_ratio_threshold=rare_ratio_threshold,
            rare_count_threshold=rare_count_threshold,
        )
    else:
        model = build_iqr_model(entry, fence_multiplier=fence_multiplier)

    slowest_value_info = find_slowest_value(value_counts)

    result = {
        "function": function_name,
        "arg_index": arg_index,
        "arg_name": arg_name,
        "type_name": type_name,
        "total_function_calls": total_function_calls,
        "numeric_count": numeric_count,
        "unique_numeric_values": len(value_counts),
        "avg_time": avg_time,
        "model": model,
    }

    # keep useful metadata from stats.json
    for k in ("min", "max", "mean", "std", "mode", "mode_count", "mode_ratio"):
        if k in entry:
            result[k] = entry[k]

    if slowest_value_info is not None:
        result["slowest_value"] = slowest_value_info["value"]
        result["slowest_value_count"] = slowest_value_info["count"]
        result["slowest_value_avg_time"] = slowest_value_info["avg_time"]
    else:
        result["slowest_value"] = None
        result["slowest_value_count"] = 0
        result["slowest_value_avg_time"] = None

    return result


def process_stats_file(
    input_path,
    output_path,
    discrete_unique_threshold,
    rare_ratio_threshold,
    rare_count_threshold,
    fence_multiplier,
    integer_only_discrete,
):
    with open(input_path, "r", encoding="utf-8") as f:
        stats = json.load(f)

    if not isinstance(stats, list):
        raise ValueError("stats.json must contain a JSON array")

    out = []
    for entry in stats:
        if not isinstance(entry, dict):
            continue
        out.append(
            build_range_entry(
                entry,
                discrete_unique_threshold=discrete_unique_threshold,
                rare_ratio_threshold=rare_ratio_threshold,
                rare_count_threshold=rare_count_threshold,
                fence_multiplier=fence_multiplier,
                integer_only_discrete=integer_only_discrete,
            )
        )

    # sort by highest avg_time first
    def sort_key(x):
        avg_time = x.get("avg_time")
        if isinstance(avg_time, (int, float)) and math.isfinite(float(avg_time)):
            return float(avg_time)
        return -math.inf

    out.sort(key=sort_key, reverse=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def parse_args():
    p = argparse.ArgumentParser(
        description="Build normal/rare argument models from stats.json"
    )
    p.add_argument("input", help="Input stats.json")
    p.add_argument("output", help="Output JSON with per-function arg ranges/models")
    p.add_argument(
        "--discrete-unique-threshold",
        type=int,
        default=16,
        help="If unique numeric values <= this, treat as discrete (default: 16)"
    )
    p.add_argument(
        "--rare-ratio-threshold",
        type=float,
        default=0.01,
        help="For discrete args, values below this frequency ratio are rare (default: 0.01)"
    )
    p.add_argument(
        "--rare-count-threshold",
        type=int,
        default=3,
        help="For discrete args, values with count below this are rare (default: 3)"
    )
    p.add_argument(
        "--fence-multiplier",
        type=float,
        default=1.5,
        help="IQR fence multiplier (default: 1.5)"
    )
    p.add_argument(
        "--integer-only-discrete",
        action="store_true",
        help="Only allow discrete modeling for integer-like args"
    )
    return p.parse_args()


def main():
    args = parse_args()
    process_stats_file(
        input_path=args.input,
        output_path=args.output,
        discrete_unique_threshold=args.discrete_unique_threshold,
        rare_ratio_threshold=args.rare_ratio_threshold,
        rare_count_threshold=args.rare_count_threshold,
        fence_multiplier=args.fence_multiplier,
        integer_only_discrete=args.integer_only_discrete,
    )


if __name__ == "__main__":
    main()