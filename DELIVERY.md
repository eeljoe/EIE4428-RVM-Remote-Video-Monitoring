# Delivery package — EIE4428 Mini Project (RVM)

**Archive:** `EIE4428-RVM.zip` · **Top-level folder:** `EIE4428-RVM/`

This package contains the complete source code, the test suite, the tooling, the
written report and a one-click launcher, as required by the brief
("a zip file containing all source codes and executable files").

---

## 1. What is inside

```
EIE4428-RVM/
├─ run.bat                      one-click launcher (venv + deps + firewall + start)
├─ run_server.py                server entry point (no install / PYTHONPATH needed)
├─ verify_system.py             end-to-end live self-check
├─ README.md                    project documentation
├─ DELIVERY.md                  this file
├─ requirements.txt             runtime dependencies
├─ requirements-dev.txt         test + report-tooling dependencies
├─ pyproject.toml               package metadata and pytest configuration
│
├─ src/rvm/                     implementation (13 modules, own codec from scratch)
│  ├─ core/       colorspace.py, bitstream.py
│  ├─ codec/      dct.py, quant.py, entropy.py, motion.py, ratecontrol.py, video.py
│  ├─ network/    packet.py, jitter.py, stats.py
│  ├─ analysis/   quality.py, detect.py
│  ├─ server/     source.py, session.py, recorder.py, app.py
│  └─ web/        index.html, app.js, style.css
│
├─ tests/                       373 tests (pytest)
├─ tools/                       report builder, benchmark, block-diagram generator, packaging script
│
└─ docs/
   ├─ EIE4428-mini-project-report-RVM.docx     the written report (7 pages)
   ├─ figures/system_block_diagram.png         system block diagram
   └─ EIE4428-mini-project-report-template.docx   the original course template
```

Deliberately **not** included: the five lecture PDFs, the task brief PDF, the
local virtual environment, and Python caches. The lecture notes are course
material and are not ours to redistribute; the virtual environment is machine
specific and is rebuilt by `run.bat` in about a minute.

---

## 2. Running it

### On the machine that hosts the server

1. Install **Python 3.10 or newer** (3.12 recommended) from
   <https://www.python.org/downloads/> and tick *Add python.exe to PATH*.
2. Double-click **`run.bat`**.

That single step creates a virtual environment, installs the three runtime
dependencies, opens the firewall port and starts the server. It prints the
address to open. First run takes one to two minutes (the OpenCV wheel is
large); later runs start instantly.

Equivalent manual steps:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_server.py
```

Useful options: `--no-camera` (generated scene, works on a machine with no
webcam), `--port 8099`, `--camera 1`, `--width 640 --height 480`.

The default is 320x240 at 15 frames/s, which is the operating point the
report quotes. 640x480 is supported but is not real time in Python; the
dashboard says so rather than pretending otherwise.

### Watching from a remote PC

The server binds `0.0.0.0:8080` by default, so any other PC on the same
network can open:

```
http://<server-ip>:8080
```

Find the server's IP with `ipconfig` (IPv4 address of the active adapter).
If the remote browser cannot connect, the Windows firewall is the usual
cause — `run.bat` adds the rule when it is started as administrator,
otherwise run this once in an **administrator** terminal:

```
netsh advfirewall firewall add rule name="RVM 8080" dir=in action=allow protocol=TCP localport=8080
```

The dashboard shows the live picture, the live metrics, a motion alarm with
bounding boxes, and the recorded-clip list.

---

## 3. Verifying the package

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest          # 373 tests, about 10 s
.\.venv\Scripts\python.exe verify_system.py   # end-to-end live check
.\.venv\Scripts\python.exe tools\benchmark.py # encoder measurement
```

`tools/make_zip.py` performs this same check on the extracted archive at build
time, so the shipped ZIP is known to boot and to pass the suite.

---

## 4. Before submitting

* The member table in the report carries `[Student ID]` placeholders until the
  real names are supplied. Give them on the command line, then rebuild:

  ```powershell
  .\.venv\Scripts\python.exe tools\build_report.py `
      --member "Name | Student ID" `
      --member "Name | Student ID"
  .\.venv\Scripts\python.exe tools\verify_report.py
  ```

  The name then appears on the cover sheet and in the co-operation section,
  and the "to be completed" note disappears by itself. The build prints a
  reminder while the placeholders are still in place.

* Rebuild the ZIP after any change: `python tools/make_zip.py --out <folder>`.
