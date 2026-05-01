how to install


## how to build after install

```bash
source shrc
sudo -E $(which runcpu) -config=wyvern.cfg -action build
```

### if error with fortran
```bash
sudo dnf install gcc-gfortran
```

### if error with 511.povray_r peak:

add `OPTIMIZE = -O2` under `511.povray_r=peak:` in config file

### if error with 527.cam4_r:

add `CC = $(SPECLANG)gcc -std=gnu89 %{model}` under `527.cam4_r,627.cam4_s:  #lang='F,C'` and for `527.cam4_r,627.cam4_s=peak:` use the following flags:

```cfg
   527.cam4_r,627.cam4_s=peak:              # https://www.spec.org/cpu2017/Docs/benchmarks/527.cam4_r.html
      OPTIMIZE = -O2
      EXTRA_CFLAGS = -fno-strict-aliasing -fno-lto
%     ifdef %{GCCge10}                      # workaround for GCC v10 (and presumably later)
         EXTRA_FFLAGS = -fallow-argument-mismatch -fno-lto
%     endif
      EXTRA_LDFLAGS = -fno-lto
```

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