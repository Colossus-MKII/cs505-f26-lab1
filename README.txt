CS 505 Fall 2026 Lab 1: Adder Design Space Exploration

Implemented designs
-------------------
src/adder32/adder32-ripple-carry.v is the supplied baseline.
src/adder32/adder32-kogge-stone.v implements five parallel-prefix stages.
src/adder32/adder32-brent-kung.v implements reduction/distribution prefix trees.
Every file provides the same adder32(a,b,cin,sum,cout) interface. Compile one
adder implementation per design; their identical module names are intentional.
The two new implementations are standalone and need no extra RTL files.

Reproduce the entire assignment
-------------------------------
From this directory on ilab:

    python3 scripts/run_experiments.py --force

The script verifies all three architectures with Yosys SAT and Icarus, builds
all 18 configurations (3 adders x 2 circuits x 3 real technologies), validates
and extracts PPA results, plots comparisons, generates report.pdf, and packages
the required two new Verilog files and report into submission.zip.
It requires the course's shared Yosys/OpenSTA/Verilator and technology files,
Icarus Verilog, Python with NumPy/Matplotlib, and pdfLaTeX. These are available
in the provided ilab environment. --jobs controls simultaneous target builds
(default 3, with four Verilator compile workers per target).

The default technologies are asap7 (7 nm), nan45 (Nangate45, 45 nm), and sky130
(Sky130HD, 130 nm). The optional nan45-nand2 library remains selectable but is
excluded from the required experiment matrix.

Useful individual commands
--------------------------
    python3 scripts/verify_rtl.py
    python3 build.py build
    python3 build.py build --adders brent-kung --techlibs nan45 --jobs 1
    python3 scripts/analyze_results.py
    python3 scripts/run_experiments.py --skip-build

The Makefile default also runs the 18-target build. build.py accepts --force
and alternate output directories. run_experiments.py accepts --build-dir and
--results-dir. Builds return nonzero on failure; an analyzer also checks actual
PASS logs, report completeness, VCD annotation, units, and cell-area totals.

Artifacts and assignment conventions
-----------------------------------
build/<circuit>-<architecture>/<technology>/ contains the mapped netlist,
synthesis/timing/power reports, Verilator logs/executable, and VCD waveform.
timing-unique-paths.rpt supplements the capped longest-path report by enumerating
the worst path for each reachable start/end pair, preventing duplicate routes
from hiding the required three slowest distinct endpoint pairs.
build/formal/<architecture>/ contains SAT scripts/proofs and Icarus logs.
build/build-manifest.json records tool versions, commands, base revision, and
SHA-256 hashes of source and library inputs. Each target also has .config.json.
results/results.csv and results/results.json contain the full measured data.
results/*-comparison.pdf/.png contain comparison plots.
results/report.tex and results/report-build.log reproduce report.pdf.
submission.zip contains exactly the three required submission files.

The user-provided updated handout screenshot strikes out the official-template
CSV instruction. The CSV here uses explicit local headers and is an auxiliary
reproducibility artifact, not a claimed official template.

Timing uses ps in ASAP7 and ns in the other libraries; analysis converts timing
using units.log. OpenSTA report_power tables already use W, regardless of the
Liberty power unit shown by report_units. Area is mapped cell area in um^2.
Both the handout's literal T/P (s/W) and conventional 1/(T*P) (operations/J)
are retained under separate column names. Energy/operation follows P*T.

Adder simulation uses the supplied 0.9855 ns stimulus interval (1 ps precision),
106 directed vectors and 100,000 xorshift32 vectors with seed 0x505f2601.
Counter simulation uses the supplied 10 ns clock and checks 100,000 increments
with startup and midrun reset. These fixed-rate VCD workloads differ from
probabilistic activity 0.2 transitions per minimum circuit period. VCD energy
P*T is therefore the handout-defined metric, not an observed energy per fixed-
rate simulated transaction. Verilator ignores specify timing checks; no
placement, routing, extracted parasitics, or silicon power measurement is used.

The SAT adder proof covers all 65 input bits, including cout. The counter
transition/reset proof starts from an arbitrary 32-bit state, covering wraparound
as well as synchronous reset. The enhanced RTL benches also run with Icarus's
four-state simulation, alongside each mapped netlist's Verilator simulation.

Review report.pdf and the two new adders before your own Gradescope submission.
This workspace workflow does not send or upload the assignment anywhere.
