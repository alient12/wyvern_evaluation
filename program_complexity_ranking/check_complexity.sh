for d in /usr/cpu2017/benchspec/CPU/*/; do
  scc --format json "$d" > "$(basename "$d").json"
done