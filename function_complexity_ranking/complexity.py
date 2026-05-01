import r2pipe
import sys
import re
import os

def clean_name(name):
    # Remove prefix (dbg., sym., etc.)
    name = re.sub(r'^(dbg|sym)\.', '', name)

    # Remove function arguments: (int, char*)
    name = re.sub(r'\(.*\)', '', name)

    return name.strip()

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 complexity.py <binary>")
        sys.exit(1)

    binary = sys.argv[1]

    if not os.path.exists(binary):
        print(f"Error: {binary} not found")
        sys.exit(1)

    r2 = r2pipe.open(binary, flags=["-e", "bin.relocs.apply=true"])
    r2.cmd("aaa")

    functions = r2.cmdj("aflj")

    results = {}

    for f in functions:
        offset = f["offset"]
        name = f["name"]

        r2.cmd(f"s {offset}")
        try:
            cc = int(r2.cmd("afCc").strip())
        except:
            continue

        if name.startswith("sym."):
            continue
        
        clean = clean_name(name)

        # Keep highest complexity if duplicate names exist
        if clean not in results or cc > results[clean]:
            results[clean] = cc

    # Sort descending
    sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)

    # Output file
    out_file = "complexity.txt"

    with open(out_file, "w") as f:
        for name, cc in sorted_results:
            f.write(f"{cc:4}  {name}\n")

    print(f"[+] Saved results to {out_file}")

if __name__ == "__main__":
    main()