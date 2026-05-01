# Dynamic Control-Flow Tracing Using LibPatch: A Software-Based Adaptive Approach

This repo is the replication package for "Dynamic Control-Flow Tracing Using LibPatch: A Software-Based Adaptive Approach" paper.

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

### Building Wyvern
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

#### Build

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

## how to find the hot path

### run each program

```bash
# sudo -E $(which runcpu) --config=wyvern.cfg --size=test --command="perf record -g" 527.cam4_r
# sudo -E $(which runcpu) --config=wyvern.cfg --size=test 538.imagick_r
```

```bash
sudo perf record -g /usr/cpu2017/benchspec/CPU/538.imagick_r/run/run_base_test_wyvern-m64.0000/imagick_r_base.wyvern-m64
sudo chown -R $(whoami) perf.data
perf report --stdio > report.txt
```

# ALSO YOU MAY WANT TO ADD `-g -O0` TO CONFIG FLAGS

```bash
LD_PRELOAD=record_args.so /usr/cpu2017/benchspec/CPU/538.imagick_r/run/run_base_test_wyvern-m64.0000/imagick_r_base.wyvern-m64
/usr/cpu2017/benchspec/CPU/538.imagick_r/run/run_base_test_wyvern-m64.0000/imagick_r_base.wyvern-m64 -limit disk 0 test_input.tga -shear 25 -resize 640x480 -negate -alpha Off test_output.tga > test_convert.out 2>> test_convert.err
```

# Function complexity

install radare2
```bash
sudo dnf install radare2
pip3 install r2pipe
```
