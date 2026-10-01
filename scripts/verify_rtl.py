#!/usr/bin/env python3
"""Prove complete addition/counter transitions and run the shared RTL benches.

The counter proof leaves its initial register state unconstrained. At the next
transition, it proves synchronous reset or modulo-2**32 increment for every
state, including 0xffffffff, under either reset input.
"""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ADDERS = ("ripple-carry", "kogge-stone", "brent-kung")
SHARED_YOSYS = "/common/users/shared/fluxlab-tools/yosys-0.69/bin/yosys"

FORMAL_WRAPPER = """module formal_adder (
    input [31:0] a, b,
    input cin,
    output correct
);
    wire [31:0] sum;
    wire cout;
    adder32 dut (.a(a), .b(b), .cin(cin), .sum(sum), .cout(cout));
    assign correct = {cout, sum} ==
        ({1'b0, a} + {1'b0, b} + {32'b0, cin});
endmodule

module formal_counter (
    input clock_i, reset_ni,
    output correct
);
    wire [31:0] count_o;
    reg [31:0] previous_count;
    reg previous_reset;
    counter32 dut (.clock_i(clock_i), .reset_ni(reset_ni), .count_o(count_o));
    always @(posedge clock_i) begin
        previous_count <= count_o;
        previous_reset <= reset_ni;
    end
    assign correct = count_o ==
        (previous_reset ? previous_count + 32'd1 : 32'd0);
endmodule
"""


def tool_path(name, override=None, fallback=None):
    candidate = override or shutil.which(name) or fallback
    if candidate is None or not Path(candidate).is_file():
        raise RuntimeError(f"Cannot locate {name}; supply --{name} /path/to/{name}.")
    return str(Path(candidate).resolve())


def run_checked(command, logfile):
    with logfile.open("w") as output:
        completed = subprocess.run(
            command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=False
        )
    if completed.returncode:
        tail = logfile.read_text(errors="replace")[-4000:]
        raise RuntimeError(f"Command failed ({completed.returncode}); see {logfile}\n{tail}")


def yosys_quote(path):
    # Yosys command scripts use double-quoted filename arguments.
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def prove_adder(name, outdir, yosys):
    source = ROOT / "src" / "adder32" / f"adder32-{name}.v"
    counter = ROOT / "src" / "counter32" / "counter32.v"
    wrapper = outdir / "formal.v"
    wrapper.write_text(FORMAL_WRAPPER)
    for design in ("adder", "counter"):
        script = outdir / f"prove-{design}.ys"
        sources = " ".join(yosys_quote(path) for path in (source, counter, wrapper))
        proof_options = "-seq 2 -prove-skip 1 " if design == "counter" else ""
        script.write_text(
            f"read_verilog {sources}\n"
            f"prep -top formal_{design} -flatten\n"
            "check -assert\n"
            f"sat -verify {proof_options}-prove correct 1 -show-inputs -show-outputs\n"
        )
        run_checked([yosys, "-Q", "-T", "-s", str(script)], outdir / f"prove-{design}.log")
        print(f"[PASS] {name}: formal {design}", flush=True)


def simulate_adder(name, outdir, iverilog, vvp):
    source = ROOT / "src" / "adder32" / f"adder32-{name}.v"
    for design in ("adder32", "counter32"):
        top = f"{design}_testbench"
        testbench = ROOT / "src" / design / f"{design}-testbench.v"
        sources = [source]
        if design == "counter32":
            sources.append(ROOT / "src" / "counter32" / "counter32.v")
        executable = outdir / f"{design}.vvp"
        run_checked(
            [iverilog, "-g2012", "-s", top, "-o", str(executable)]
            + [str(path) for path in sources + [testbench]],
            outdir / f"compile-{design}.log",
        )
        logfile = outdir / f"simulate-{design}.log"
        run_checked([vvp, str(executable)], logfile)
        if "[PASS]" not in logfile.read_text(errors="replace"):
            raise RuntimeError(f"Testbench did not report [PASS]; see {logfile}")
        print(f"[PASS] {name}: RTL {design}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adders", nargs="+", choices=ADDERS, default=list(ADDERS))
    parser.add_argument("--outdir", type=Path, default=ROOT / "build" / "formal")
    parser.add_argument("--yosys", help="Override Yosys executable.")
    parser.add_argument("--iverilog", help="Override Icarus Verilog executable.")
    parser.add_argument("--vvp", help="Override Icarus runtime executable.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--formal-only", action="store_true")
    mode.add_argument("--simulation-only", action="store_true")
    args = parser.parse_args()
    try:
        yosys = None if args.simulation_only else tool_path("yosys", args.yosys, SHARED_YOSYS)
        iverilog = None if args.formal_only else tool_path("iverilog", args.iverilog)
        vvp = None if args.formal_only else tool_path("vvp", args.vvp)
        for name in args.adders:
            outdir = args.outdir.resolve() / name
            outdir.mkdir(parents=True, exist_ok=True)
            if not args.simulation_only:
                prove_adder(name, outdir, yosys)
            if not args.formal_only:
                simulate_adder(name, outdir, iverilog, vvp)
    except (OSError, RuntimeError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    print("All selected RTL checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
