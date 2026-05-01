#!/bin/bash

# === Config ===
BIN="/usr/cpu2017/benchspec/CPU/531.deepsjeng_r/exe/deepsjeng_r_base.wyvern-m64"
INPUT=(inputs/test.txt)
CPU=7
RUNS=5
GENERATE_CONFIGS=true

OUT_DIR="logs"
TIME_LOG="timings.txt"

NORMAL_CFG="config.yaml"
RELAXED_CFG="config-relaxed.yaml"
STRESS_CFG="config-stress.yaml"

mkdir -p "$OUT_DIR"
: > "$TIME_LOG"

export MAX_CALLS_PER_SITE=10000

# =========================
# Helper: run + time
# =========================
run_and_time () {
    local label="$1"
    local outfile="$2"
    shift 2

    local tmp=$(mktemp)

    /usr/bin/time -f "$label: %e" -o "$tmp" \
        "$@" \
        > "$outfile" 2>&1

    cat "$tmp" >> "$TIME_LOG"
    rm "$tmp"
}

# =========================
# Preprocessing (NO timing)
# =========================
if [ "$GENERATE_CONFIGS" = true ]; then
    echo "[*] Arg recorder run"
    env LD_PRELOAD=../arg-recorder.so \
        "$BIN" "${INPUT[@]}" \
        > "$OUT_DIR/arg_recorder.out" 2>&1

    python3 ../numeric_arg_stats.py ./wyvern-data-args.json ./stats.json --reset-db
    python3 ../analyzer.py ./stats.json ./wyvern-analysis.txt
    python3 ../complexity.py "$BIN"
    python3 ../config_generator.py ./wyvern-analysis.txt ./complexity.txt ./config.yaml ./config-stress.yaml ./config-relaxed.yaml
fi
# =========================
# Benchmark runs
# =========================
for i in $(seq 1 $RUNS); do
    echo "==============================" >> "$TIME_LOG"
    echo "RUN $i" >> "$TIME_LOG"
    echo "==============================" >> "$TIME_LOG"

    # -------------------------
    # VANILLA (no instrumentation)
    # -------------------------
    echo "[*] VANILLA run $i"
    run_and_time "VANILLA run $i" \
        "$OUT_DIR/vanilla_run${i}.out" \
        taskset -c $CPU \
        "$BIN" "${INPUT[@]}"
    
    # -------------------------
    # WYVERN (NORMAL)
    # -------------------------
    echo "[*] WYVERN NORMAL run $i"
    run_and_time "WYVERN-NORMAL run $i" \
        "$OUT_DIR/wyvern_normal_run${i}.out" \
        taskset -c $CPU \
        env LD_PRELOAD=../cft-auto-data-test.so \
            WYVERN_CONFIG_PATH="$NORMAL_CFG" \
        "$BIN" "${INPUT[@]}"

    # -------------------------
    # WYVERN (RELAXED)
    # -------------------------
    echo "[*] WYVERN RELAXED run $i"
    run_and_time "WYVERN-RELAXED run $i" \
        "$OUT_DIR/wyvern_relaxed_run${i}.out" \
        taskset -c $CPU \
        env LD_PRELOAD=../cft-auto-data-test.so \
            WYVERN_CONFIG_PATH="$RELAXED_CFG" \
        "$BIN" "${INPUT[@]}"

    # -------------------------
    # WYVERN (STRESS)
    # -------------------------
    echo "[*] WYVERN STRESS run $i"
    run_and_time "WYVERN-STRESS run $i" \
        "$OUT_DIR/wyvern_stress_run${i}.out" \
        taskset -c $CPU \
        env LD_PRELOAD=../cft-auto-data-test.so \
            WYVERN_CONFIG_PATH="$STRESS_CFG" \
        "$BIN" "${INPUT[@]}"

    # -------------------------
    # MAGIC TRACE
    # -------------------------
    echo "[*] Magic Trace run $i"
    run_and_time "magic-trace run $i" \
        "$OUT_DIR/magic_trace_run${i}.out" \
        taskset -c $CPU ../magic-trace run "$BIN" -- "${INPUT[@]}"
    
    mv trace.fxt.gz "$OUT_DIR/magic_trace_run${i}.fxt.gz"

    # -------------------------
    # VALGRIND
    # -------------------------
    echo "[*] Valgrind run $i"
    run_and_time "valgrind run $i" \
        "$OUT_DIR/valgrind_run${i}.out" \
        taskset -c $CPU valgrind --tool=cfggrind \
        --cfg-outfile="$OUT_DIR/test_run${i}.cfg" --instrs-map="asm_map.map" --cfg-dump=bubble \
        "$BIN" "${INPUT[@]}"

    callgrind_annotate --inclusive=yes \
        "$OUT_DIR/cfggrind_run${i}.out" \
        > "$OUT_DIR/cfggrind_report_run${i}.txt"
    
    # cleanup valgrind garbage
    rm -f vgcore.*
done

# =========================
# AVERAGES
# =========================
echo "" >> "$TIME_LOG"
echo "===== AVERAGES =====" >> "$TIME_LOG"

awk '
/VANILLA run/        {n0++; s0+=$NF}
/WYVERN-NORMAL run/  {n1++; s1+=$NF}
/WYVERN-STRESS run/  {n2++; s2+=$NF}
/WYVERN-RELAXED run/ {n3++; s3+=$NF}
/magic-trace run/    {n4++; s4+=$NF}
/valgrind run/       {n5++; s5+=$NF}

END {
    if (n0) print "VANILLA avg:", s0/n0, "s"
    if (n1) print "WYVERN NORMAL avg:", s1/n1, "s"
    if (n2) print "WYVERN STRESS avg:", s2/n2, "s"
    if (n3) print "WYVERN RELAXED avg:", s3/n3, "s"
    if (n4) print "magic-trace avg:", s4/n4, "s"
    if (n5) print "valgrind avg:", s5/n5, "s"
}
' "$TIME_LOG" >> "$TIME_LOG"