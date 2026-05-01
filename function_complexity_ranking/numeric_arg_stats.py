#!/usr/bin/env python3
import argparse
import json
import math
import os
import re
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from tqdm import tqdm


MAX_VALUES = 1000

INT_RE = re.compile(r"^[+-]?\d+$")
FLOAT_RE = re.compile(
    r"^[+-]?("
    r"(\d+\.\d*)|"
    r"(\.\d+)|"
    r"(\d+)"
    r")([eE][+-]?\d+)?$"
)


@dataclass
class RunningStats:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0
    min_val: float = math.inf
    max_val: float = -math.inf
    type_name: str = ""
    arg_name: str = ""

    def update(self, x: float):
        self.count += 1

        if x < self.min_val:
            self.min_val = x
        if x > self.max_val:
            self.max_val = x

        delta = x - self.mean
        self.mean += delta / self.count
        delta2 = x - self.mean
        self.m2 += delta * delta2

    def stddev(self) -> float:
        if self.count < 2:
            return 0.0
        return math.sqrt(self.m2 / self.count)   # population std


def parse_number_like(v):
    """
    Accept:
      - int / float / bool directly
      - numeric strings like "123", "-5", "3.14", "2e10"
    Reject:
      - hex strings like "0x1234"
      - placeholders like "<read-error>"
      - null / objects / arrays
    """
    if isinstance(v, bool):
        return float(int(v))

    if isinstance(v, int):
        return float(v)

    if isinstance(v, float):
        if math.isfinite(v):
            return v
        return None

    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        if s.startswith("0x") or s.startswith("0X"):
            return None
        if s.startswith("<") and s.endswith(">"):
            return None
        if INT_RE.match(s):
            try:
                return float(int(s))
            except Exception:
                return None
        if FLOAT_RE.match(s):
            try:
                x = float(s)
                if math.isfinite(x):
                    return x
            except Exception:
                return None
        return None

    return None


def extract_top_level_numeric_arg(arg_obj):
    """
    Expect one arg object like:
    {
      "index": 0,
      "name": "arg0",
      "type_kind": "base",
      "type_name": "int",
      "decoded": { "kind":"base", "type_name":"int", "value":123 }
    }

    Returns:
      (numeric_value, type_name) or (None, None)
    """
    if not isinstance(arg_obj, dict):
        return None, None

    decoded = arg_obj.get("decoded")
    if not isinstance(decoded, dict):
        return None, None

    kind = decoded.get("kind")
    if kind != "base":
        return None, None

    val = decoded.get("value")
    num = parse_number_like(val)
    if num is None:
        return None, None

    type_name = decoded.get("type_name") or arg_obj.get("type_name") or ""
    return num, type_name


def init_mode_db(db_path, reset=False):
    if reset and os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS value_counts (
            function_name TEXT NOT NULL,
            arg_index     INTEGER NOT NULL,
            value_text    TEXT NOT NULL,
            count         INTEGER NOT NULL,
            time_sum      REAL NOT NULL DEFAULT 0.0,
            time_count    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (function_name, arg_index, value_text)
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_value_counts_group
        ON value_counts(function_name, arg_index)
    """)

    conn.commit()
    return conn


def bump_mode_count(conn, function_name, arg_index, value, time_ns=None):
    """
    Store exact counts in SQLite so mode is exact without keeping huge Counters in RAM.
    Also accumulate time per exact value so we can output avg_time_per_value.

    value_text is a stable text representation of the numeric value.
    """
    value_text = format(value, ".17g")

    time_sum = float(time_ns) if time_ns is not None else 0.0
    time_count = 1 if time_ns is not None else 0

    conn.execute("""
        INSERT INTO value_counts(
            function_name, arg_index, value_text, count, time_sum, time_count
        )
        VALUES (?, ?, ?, 1, ?, ?)
        ON CONFLICT(function_name, arg_index, value_text)
        DO UPDATE SET
            count = count + 1,
            time_sum = time_sum + excluded.time_sum,
            time_count = time_count + excluded.time_count
    """, (function_name, arg_index, value_text, time_sum, time_count))


def parse_mode_value(value_text):
    if value_text is None:
        return None

    s = str(value_text).strip()
    if not s:
        return None

    try:
        if INT_RE.match(s):
            return int(s)
        x = float(s)
        return x
    except Exception:
        return value_text


def normalize_time_ns(v):
    """
    Parse time_ns if it is numeric or numeric string.
    """
    x = parse_number_like(v)
    if x is None:
        return None
    return float(x)


def process_file(input_path, output_path, db_path, reset_db=False, commit_every=10000):
    conn = init_mode_db(db_path, reset=reset_db)

    # key: (function_name, arg_index) -> RunningStats
    stats = {}

    # function -> total matched/completed calls (args + time paired)
    function_call_counts = defaultdict(int)

    # function -> RunningStats for time
    function_time_stats = {}

    # function -> stack of pending arg records waiting for a time record
    pending_calls = defaultdict(list)

    total_records = 0
    total_args = 0
    numeric_args = 0
    bad = 0
    arg_records = 0
    time_records = 0
    matched_times = 0
    unmatched_time_records = 0

    file_size = os.path.getsize(input_path)

    with open(input_path, "r", encoding="utf-8", errors="replace") as fin, \
         tqdm(total=file_size, unit="B", unit_scale=True, desc="Processing") as pbar:

        for line_no, line in enumerate(fin, start=1):
            pbar.update(len(line))

            line = line.strip()
            if not line:
                continue

            total_records += 1

            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue

            if not isinstance(rec, dict):
                bad += 1
                continue

            function_name = rec.get("function")
            if not isinstance(function_name, str):
                bad += 1
                continue

            has_args = isinstance(rec.get("args"), list)
            has_time = "time_ns" in rec

            # ------------------------------
            # ARG RECORD
            # ------------------------------
            if has_args:
                args = rec["args"]
                arg_records += 1

                numeric_items = []

                for arg in args:
                    total_args += 1

                    if not isinstance(arg, dict):
                        continue

                    arg_index = arg.get("index")
                    arg_name = arg.get("name", f"arg{arg_index}")

                    if not isinstance(arg_index, int):
                        continue

                    value, type_name = extract_top_level_numeric_arg(arg)
                    if value is None:
                        continue

                    numeric_args += 1
                    numeric_items.append({
                        "arg_index": arg_index,
                        "arg_name": arg_name or f"arg{arg_index}",
                        "type_name": type_name or "",
                        "value": value,
                    })

                # push this call onto stack; it will get time when a matching time record arrives
                pending_calls[function_name].append({
                    "numeric_items": numeric_items
                })
                continue

            # ------------------------------
            # TIME RECORD
            # ------------------------------
            if has_time:
                time_records += 1
                time_ns = normalize_time_ns(rec.get("time_ns"))
                if time_ns is None:
                    bad += 1
                    continue

                stack = pending_calls.get(function_name)
                if not stack:
                    # time without a matching arg record
                    unmatched_time_records += 1
                    continue

                call_info = stack.pop()
                matched_times += 1
                function_call_counts[function_name] += 1

                # update per-function average time
                trs = function_time_stats.get(function_name)
                if trs is None:
                    trs = RunningStats()
                    function_time_stats[function_name] = trs
                trs.update(time_ns)

                # update per-arg numeric stats + value counts + avg time per value
                for item in call_info["numeric_items"]:
                    arg_index = item["arg_index"]
                    arg_name = item["arg_name"]
                    type_name = item["type_name"]
                    value = item["value"]

                    key = (function_name, arg_index)

                    rs = stats.get(key)
                    if rs is None:
                        rs = RunningStats(
                            type_name=type_name,
                            arg_name=arg_name
                        )
                        stats[key] = rs

                    rs.update(value)
                    bump_mode_count(conn, function_name, arg_index, value, time_ns=time_ns)

                if total_records % commit_every == 0:
                    conn.commit()
                    pbar.set_postfix({
                        "records": f"{total_records:,}",
                        "arg_recs": f"{arg_records:,}",
                        "time_recs": f"{time_records:,}",
                        "matched": f"{matched_times:,}",
                        "numeric": f"{numeric_args:,}",
                        "groups": f"{len(stats):,}",
                        "bad": f"{bad:,}",
                    })
                continue

            # unknown record type
            bad += 1

        conn.commit()

    cur = conn.cursor()

    out = []

    for (function_name, arg_index), rs in sorted(stats.items()):
        total_function_calls = function_call_counts.get(function_name, 0)
        time_rs = function_time_stats.get(function_name)

        cur.execute("""
            SELECT value_text, count, time_sum, time_count
            FROM value_counts
            WHERE function_name = ? AND arg_index = ?
            ORDER BY count DESC, value_text ASC
        """, (function_name, arg_index))

        values = []
        for i, (value_text, count, time_sum, time_count) in enumerate(cur):
            if i >= MAX_VALUES:
                values.append({
                    "value": "<truncated>",
                    "count": 0,
                    "avg_time": None
                })
                break

            val = parse_mode_value(value_text)
            avg_time = (time_sum / time_count) if time_count else None

            values.append({
                "value": val,
                "count": count,
                "avg_time": avg_time
            })

        if values:
            mode_val = values[0]["value"]
            mode_count = values[0]["count"]
        else:
            mode_val = None
            mode_count = 0

        out.append({
            "function": function_name,
            "arg_index": arg_index,
            "arg_name": rs.arg_name,
            "type_name": rs.type_name,

            "total_function_calls": total_function_calls,
            "numeric_count": rs.count,

            "min": rs.min_val if rs.count else None,
            "max": rs.max_val if rs.count else None,
            "mean": rs.mean if rs.count else None,
            "std": rs.stddev() if rs.count else None,

            "avg_time": time_rs.mean if (time_rs and time_rs.count) else None,

            "mode": mode_val,
            "mode_count": mode_count,
            "mode_ratio": (mode_count / rs.count) if rs.count else None,

            "value_counts": values
        })

    conn.close()

    with open(output_path, "w", encoding="utf-8") as fout:
        json.dump(out, fout, ensure_ascii=False, indent=2)

    unmatched_arg_records = sum(len(v) for v in pending_calls.values())

    print(
        f"[done] records={total_records:,} arg_records={arg_records:,} "
        f"time_records={time_records:,} matched_times={matched_times:,} "
        f"unmatched_arg_records={unmatched_arg_records:,} "
        f"unmatched_time_records={unmatched_time_records:,} "
        f"args={total_args:,} numeric={numeric_args:,} "
        f"groups={len(stats):,} bad={bad:,}",
        file=sys.stderr
    )


def parse_args():
    p = argparse.ArgumentParser(
        description="Compute per-(function,arg) statistics for top-level numeric args in NDJSON, with recursive time matching."
    )
    p.add_argument("input", help="Input NDJSON file")
    p.add_argument("output", help="Output summary JSON file")
    p.add_argument(
        "--db",
        default="numeric_modes.sqlite",
        help="SQLite DB for exact mode counting"
    )
    p.add_argument(
        "--reset-db",
        action="store_true",
        help="Delete existing SQLite DB before processing"
    )
    p.add_argument(
        "--commit-every",
        type=int,
        default=10000,
        help="Commit SQLite every N records"
    )
    return p.parse_args()


def main():
    args = parse_args()
    process_file(
        input_path=args.input,
        output_path=args.output,
        db_path=args.db,
        reset_db=args.reset_db,
        commit_every=args.commit_every,
    )


if __name__ == "__main__":
    main()