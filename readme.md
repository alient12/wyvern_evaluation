# Dynamic Control-Flow Tracing Using LibPatch: A Software-Based Adaptive Approach

This repo is the replication package for "Dynamic Control-Flow Tracing Using LibPatch: A Software-Based Adaptive Approach" paper.

- [Installation](https://github.com/alient12/wyvern_evaluation#installation)
  * [SPEC CPU 2017 Benchmark Suite](https://github.com/alient12/wyvern_evaluation#spec-cpu-2017-benchmark-suite)
  * [magic-trace](https://github.com/alient12/wyvern_evaluation#magic-trace)
  * [Valgrind CFGgrind](https://github.com/alient12/wyvern_evaluation#valgrind-cfggrind)
  * [Wyvern](https://github.com/alient12/wyvern_evaluation#wyvern)
- [Ranking Benchmark Programs By Cyclomatic Complexity Decsity (Optional)](https://github.com/alient12/wyvern_evaluation#ranking-benchmark-programs-by-cyclomatic-complexity-decsity-optional)
- [Running All Tracers on Benchmark Programs](https://github.com/alient12/wyvern_evaluation#running-all-tracers-on-benchmark-programs)

## Installation
In order to replicate this paper, you need SPEC CPU 2017 Benchmark Suite, Wyvern, magic trace and Valgrind CFGgrind

### SPEC CPU 2017 Benchmark Suite

Follow this [link](https://www.spec.org/cpu2017/) for accessing SPEC CPU 2017 Benchmark Suite.
It is highly recommanded to install it in `/usr/cpu2017/` compatibility with the scripts in this repo.

Then you have to copy `wyvern.cfg` from this repo and place it at `/usr/cpu2017/config/`. Next, open the terminal in the spec folder and run the following commands to build the benchmark programs: (you may use `cshrc` instead)

```bash
source shrc
sudo -E $(which runcpu) -config=wyvern.cfg -action build
```

### magic-trace

Follow [magic-trace official repo](https://github.com/janestreet/magic-trace) to download the latest version of magic-trace and place it at `wyvern_evaluation/function_complexity_ranking/`.

### Valgrind CFGgrind

Follow [CFGgrind repo](https://github.com/rimsa/CFGgrind) to build valgrind with CFGgrind plugin.

### Wyvern
#### Installing Requirements
You should have the following libraries installed:
capstone, libpatch, yaml, libdawrf, cjson, llttng-ust

Fedora/RHEL:
```bash
sudo dnf install capstone-devel
sudo dnf install libyaml-devel
sudo dnf install libdwarf-devel
sudo dnf install cjson-devel
# libpatch dependencies
sudo dnf install guile30
sudo dnf install elfutils-devel
sudo dnf install userspace-rcu-devel
# LTTng dependencies
sudo dnf install popt-devel
sudo dnf install libuuid-devel
sudo dnf install libxml2-devel
sudo dnf install libbabeltrace2-devel
```

Ubuntu:
```bash
sudo apt install libcapstone-dev
sudo apt install libyaml-dev
sudo apt install libdwarf-dev
sudo apt install libcjson-dev
# libpatch dependencies
sudo apt install guile-3.0
sudo apt install libdw-dev
sudo apt install liburcu-dev
# LTTng dependencies
sudo apt install libpopt-dev
sudo apt install uuid-dev
sudo apt install libxml2-dev
sudo dnf install libbabeltrace2-dev
```

Install libolx (required for libpatch):
```bash
git clone https://git.sr.ht/~old/libolx
cd libolx
mkdir build; cd build; ../configuration
make -j4
sudo make install

# verify installatino
pkg-config --modversion libolx
# if not found
export PKG_CONFIG_PATH=/usr/local/lib/pkgconfig:$PKG_CONFIG_PATH
```

Install libpatch:
```bash
git clone https://git.sr.ht/~old/libpatch
cd libpatch
mkdir build; cd build
../configuration \
    --disable-ftrace-build \
    --disable-patch-coverage-build \
    --disable-patch-integrity-build \
    --without-manpages \
    --without-lttng \
    --without-dyninst \
    --without-liteinst \
    --without-benchmarks
make -j4
sudo make install
```

Then you can confirm the installation with the following command:
```bash
ldconfig -p | grep capstone
```

install LTTng:

```bash
cd $(mktemp -d) &&
wget https://lttng.org/files/lttng-modules/lttng-modules-latest-2.15.tar.bz2 &&
tar -xf lttng-modules-latest-2.15.tar.bz2 &&
cd lttng-modules-2.15.* &&
make &&
sudo make modules_install &&
sudo depmod -a
```

```bash
cd $(mktemp -d) &&
wget https://lttng.org/files/lttng-ust/lttng-ust-latest-2.15.tar.bz2 &&
tar -xf lttng-ust-latest-2.15.tar.bz2 &&
cd lttng-ust-2.15.* &&
./configure --disable-numa &&
make &&
sudo make install &&
sudo ldconfig
```

for LTTng tools:
```bash
wget https://lttng.org/files/lttng-tools/lttng-tools-latest-2.15.tar.bz2 &&
tar -xf lttng-tools-latest-2.15.tar.bz2 &&
cd lttng-tools-2.15.* &&
./configure &&
make &&
sudo make install &&
sudo ldconfig
```

#### Building Wyvern

Clone Wyvern's repo:

```bash
git clone https://github.com/alient12/adaptive_control_flow_tracer.git
```

```bash
cd adaptive_control_flow_tracer
gcc -shared -fPIC libdwscan.c -o libdwscan.so -ldwarf -lz
gcc -shared -fPIC cft-auto-data-test.c lttng_tp.c trigger_check.c trigger_compiler.c trace_config.c -o cft-auto-data-test.so -I. -L. -ldwscan -Wl,-rpath,'$ORIGIN' -lyaml -ldl -lcapstone -lpatch -llttng-ust
gcc -shared -fPIC -pthread arg-recorder.c lttng_tp.c trigger_check.c trigger_compiler.c trace_config.c -o arg-recorder.so -I. -L. -ldwscan -Wl,-rpath,'$ORIGIN' -lyaml -lcjson -ldl -lcapstone -lpatch -llttng-ust
```
After compilation, copy `libdwscan.so`, `cft-auto-data-test.so` and `arg-recorder.so` and place them at `wyvern_evaluation/function_complexity_ranking/`.

## Ranking Benchmark Programs By Cyclomatic Complexity Decsity (Optional)

In this step, we compute cyclomatic complexity of each benchmark program by using [SCC](https://github.com/boyter/scc) on their source code directory. Then, we rank them by cyclomatic comlexity density by the mean of `rank.py`. Follow [SCC](https://github.com/boyter/scc#install) for installation.

```
cd program_complexity_ranking
./check_complexity.sh
python3 rank.py
```
After runnning this, it generates `ranking_complexity_density.csv` and `ranking_total_complexity.csv` files.

## Running All Tracers on Benchmark Programs

You need to install `radare2` and `r2pipe` for the automatic trigger config generation pipeline.
```bash
# Fedora/RHEL
sudo dnf install radare2
# Ubuntu
sudo apt install radare2
pip3 install r2pipe
```
Then for running any benchmark program, you just need to copy the input files from data folder in SPEC CPU 2017 and place it in the corresponding folder.
For example, for running `538.imagick_r` you have to copy the inputs from `/usr/cpu2017/benchspec/CPU/538.imagick_r/data/test` to `wyvern_evaluation/function_complexity_ranking/538.imagick_r/` and then run `./run.sh`.
You can check `dir_tree.txt` to ensure how which files and where you have to copy them.

You can edit `run.sh` file.

```bash
# === Config ===
BIN="/usr/cpu2017/benchspec/CPU/538.imagick_r/exe/imagick_r_base.wyvern-m64"
INPUT=(
    -limit disk 0
    input/test_input.tga
    -shear 25
    -resize 640x480
    -negate
    -alpha Off
    test_output.tga
)
CPU=7
RUNS=5
GENERATE_CONFIGS=true

OUT_DIR="logs"
TIME_LOG="timings.txt"

NORMAL_CFG="config.yaml"
RELAXED_CFG="config-relaxed.yaml"
STRESS_CFG="config-stress.yaml"
```

- `BIN` is the path to benchmark program.
- `INPUT` is the arguments that are passed to the benchmark program.
- `CPU` is the CPU core that you have isolated and you want to run the tests on it.
- `RUNS` is how many times you want to repeat the test.
- `GENERATE_CONFIGS` if it's false, it assumes that config files already exist and directly runs the tests without running arg-recorder and python scripts.

After running, these files will be generated:
```
RQ1: Control-Flow Coverage
probe_success_rates.txt

RQ2: Effectiveness of Trigger-Based Activation
logs/wyvern_relaxed_run.out
logs/wyvern_normal_run.out
logs/wyvern_stress_run.out
(End of each file shows how many times each probe invoked)

RQ3: Performance Overhead
timings.txt
```
