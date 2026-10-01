#!/usr/bin/env python3
"""Validate and summarize Lab 1 synthesis, timing, and activity reports.

Default invocation requires all 18 configurations. For a single completed build:
  python3 scripts/analyze_results.py --design adder32-ripple-carry --tech nan45

CSV headers are local to this project: the handout's CSV-template requirement was
removed. Numeric power values from OpenSTA report_power are already in watts.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
from scripts.build_tools import TECH_LIBS  # noqa: E402

ARCHITECTURES = ("ripple-carry", "kogge-stone", "brent-kung")
CIRCUITS = ("adder32", "counter32")
TECHNOLOGIES = ("asap7", "nan45", "sky130")
DESIGNS = tuple(f"{circuit}-{architecture}" for circuit in CIRCUITS for architecture in ARCHITECTURES)
NODE_NM = {"asap7": 7, "nan45": 45, "sky130": 130}
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
TIME_FACTORS = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12, "fs": 1e-15}
CSV_COLUMNS = [
    "design", "circuit", "architecture", "technology", "node_nm",
    "area_um2", "mapped_cell_count", "sequential_cell_count", "sequential_area_um2",
    "sequential_area_fraction", "delay_native", "time_unit", "cycle_time_s", "delay_ns",
    "frequency_hz", "performance_per_area_hz_per_um2", "probabilistic_power_w",
    "vcd_power_w", "power_relative_difference", "probabilistic_energy_j", "vcd_energy_j",
    "probabilistic_throughput_per_watt_ops_per_j", "vcd_throughput_per_watt_ops_per_j",
    "probabilistic_handout_time_per_power_s_per_w", "vcd_handout_time_per_power_s_per_w",
    "testbench_status", "vcd_annotated_pins", "vcd_total_pins", "paths_reported",
    "unique_path_pairs", "liberty_file",
]


class AnalysisError(RuntimeError):
    """A build artifact is absent, incomplete, or failed validation."""


def read_required(path: Path) -> str:
    if not path.is_file() or path.stat().st_size == 0:
        raise AnalysisError(f"Missing or empty artifact: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def positive(value: float, description: str) -> float:
    if not math.isfinite(value) or value <= 0:
        raise AnalysisError(f"Expected positive finite {description}, got {value}")
    return value


def reject_errors(text: str, path: Path) -> None:
    if re.search(r"(?mi)^\s*(?:Error:|ERROR:|%Error|\[FAIL\]|FATAL:)", text):
        raise AnalysisError(f"Tool or testbench failure reported in {path}")


def parse_time_units(text: str) -> tuple[float, str]:
    match = re.search(rf"(?mi)^\s*time\s+(?:unit\s*[:=]?\s*)?({NUMBER})\s*(fs|ps|ns|us|ms|s)\b", text)
    if match is None:
        raise AnalysisError("Cannot parse the Time unit from sta/units.log")
    multiplier, unit = float(match[1]), match[2].lower()
    return positive(multiplier * TIME_FACTORS[unit], "time-unit scale"), f"{multiplier:g}{unit}"


def parse_power(text: str, description: str) -> dict[str, float]:
    # report_power's fixed columns are Internal, Switching, Leakage, Total (W),
    # followed by a percentage. report_units' leakage-power unit does not scale them.
    match = re.search(rf"(?mi)^\s*Total\s+({NUMBER})\s+({NUMBER})\s+({NUMBER})\s+({NUMBER})(?:\s|$)", text)
    if match is None:
        raise AnalysisError(f"Missing complete Total row in {description}")
    values = dict(zip(("internal_w", "switching_w", "leakage_w", "total_w"), map(float, match.groups())))
    if any(not math.isfinite(value) or value < 0 for value in values.values()):
        raise AnalysisError(f"Invalid power value in {description}")
    positive(values["total_w"], f"total power in {description}")
    subtotal = sum(values[key] for key in ("internal_w", "switching_w", "leakage_w"))
    if not math.isclose(subtotal, values["total_w"], rel_tol=2e-5, abs_tol=1e-15):
        raise AnalysisError(f"Power components do not sum to total in {description}")
    return values


def parse_vcd_annotation(text: str) -> tuple[int, int | None]:
    # OpenSTA versions have printed both 'Annotated N pin activities.' and
    # 'N pins annotated with activity.' Require a positive explicit count.
    patterns = (
        r"(?i)annotated\s+(\d+)\s+(?:of\s+(\d+)\s+)?pin(?:s|\s+activities)?",
        r"(?i)(\d+)\s+(?:of\s+(\d+)\s+)?pins?\s+annotated",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            annotated = int(match[1])
            total = int(match[2]) if match[2] is not None else None
            if annotated <= 0:
                raise AnalysisError("OpenSTA annotated zero VCD pin activities")
            table_vcd = re.search(r"(?mi)^\s*vcd\s+(\d+)\s*$", text)
            table_unannotated = re.search(r"(?mi)^\s*unannotated\s+(\d+)\s*$", text)
            if table_vcd and int(table_vcd[1]) != annotated:
                raise AnalysisError("VCD annotation message disagrees with activity-source table")
            if total is None and table_unannotated:
                total = annotated + int(table_unannotated[1])
            return annotated, total
    raise AnalysisError("Missing explicit VCD activity annotation count in sta/stdout-power-vcd.log")


def parse_timing_paths(text: str, scale_s: float, *, require_three: bool = True) -> tuple[list[dict[str, Any]], int, int, list[dict[str, Any]]]:
    paths = []
    for block in re.findall(r"(?ms)^Startpoint:.*?(?=^Startpoint:|\Z)", text):
        start = re.search(r"(?m)^Startpoint:\s*(.+)", block)
        end = re.search(r"(?m)^Endpoint:\s*(.+)", block)
        slack = re.search(rf"(?m)^\s*({NUMBER})\s+slack\s*\(", block)
        arrival = re.search(rf"(?m)^\s*({NUMBER})\s+data arrival time", block)
        if not (start and end and slack and arrival):
            raise AnalysisError("Incomplete Startpoint/Endpoint timing-path block")
        paths.append({
            "startpoint": start[1].split(" (")[0].strip(),
            "endpoint": end[1].split(" (")[0].strip(),
            "slack_native": float(slack[1]),
            "arrival_native": float(arrival[1]),
            "delay_ns": -float(slack[1]) * scale_s * 1e9,
            "details": block.strip(),
        })
    if not paths:
        raise AnalysisError("No complete constrained paths in timing-longest-paths.rpt")
    counts = Counter((path["startpoint"], path["endpoint"]) for path in paths)
    if require_three and len(counts) < 3:
        raise AnalysisError("Fewer than three unique timing startpoint/endpoint pairs")
    top_paths = []
    seen = set()
    for path in sorted(paths, key=lambda item: item["slack_native"]):
        pair = (path["startpoint"], path["endpoint"])
        if pair not in seen:
            seen.add(pair)
            top_paths.append({**path, "occurrences_same_pair": counts[pair]})
            if len(top_paths) == 3:
                break
    repeated = [
        {"startpoint": pair[0], "endpoint": pair[1], "occurrences": count}
        for pair, count in counts.most_common() if count > 1
    ]
    return top_paths, len(paths), len(counts), repeated


def parse_synthesis(text: str, top: str) -> tuple[float, dict[str, int], int]:
    # `yosys -t` prefixes every report line with elapsed time. Strip that prefix
    # while retaining report indentation. Yosys 0.69 adds a per-type area column.
    text = re.sub(r"(?m)^\[\d+\.\d+\] ?", "", text)
    areas = list(re.finditer(rf"Chip area for module\s+['\"]?\\?{re.escape(top)}['\"]?\s*:\s*({NUMBER})", text))
    if not areas:
        raise AnalysisError(f"No final mapped chip area for module {top} in synth/stdout.log")
    area_match = areas[-1]
    area = positive(float(area_match[1]), "mapped cell area")
    # Use the final module statistics immediately before its Liberty area report,
    # not one of Yosys's earlier unmapped/coarse statistics.
    prefix = text[:area_match.start()]
    headers = list(re.finditer(rf"(?m)^===\s+\\?{re.escape(top)}\s+===\s*$", prefix))
    if not headers:
        raise AnalysisError(f"Missing final mapped statistics for {top}")
    block = prefix[headers[-1].end():]
    cells_marker = re.search(r"(?m)^\s*Number of cells:\s*(\d+)\s*$", block)
    if cells_marker is None:
        cells_marker = re.search(rf"(?m)^\s*(\d+)(?:\s+(?:{NUMBER}|-))?\s+cells\s*$", block)
    if cells_marker is None:
        raise AnalysisError("Cannot find final mapped cell count")
    counts = {}
    for line in block[cells_marker.end():].splitlines():
        match = re.fullmatch(r"\s+(\S+)\s+(\d+)\s*", line)
        if match:
            counts[match[1].lstrip("\\")] = int(match[2])
            continue
        match = re.fullmatch(rf"\s+(\d+)\s+(?:(?:{NUMBER}|-)\s+)?(\S+)\s*", line)
        if match:
            counts[match[2].lstrip("\\")] = int(match[1])
    expected = int(cells_marker[1])
    if not counts or sum(counts.values()) != expected:
        raise AnalysisError(f"Mapped cell counts do not sum to reported total {expected}")
    # Scope metadata is retained in Yosys's counts but is not a physical cell,
    # does not contribute Liberty area, and is omitted by the Verilog backend.
    metadata_count = counts.pop("$scopeinfo", 0)
    return area, counts, metadata_count


_LIB_CACHE: dict[str, tuple[dict[str, dict[str, Any]], str]] = {}


def liberty_cells(technology: str) -> tuple[dict[str, dict[str, Any]], str]:
    """Read only the configured course Liberty library; include compressed ASAP7."""
    path = Path(TECH_LIBS[technology]["lib"])
    key = str(path)
    if key in _LIB_CACHE:
        return _LIB_CACHE[key]
    if not path.is_file():
        raise AnalysisError(f"Configured Liberty library is unavailable: {path}")
    with (gzip.open(path, "rt") if path.suffix == ".gz" else path.open()) as handle:
        text = handle.read()
    matches = list(re.finditer(r'(?m)^\s*cell\s*\(\s*"?([^"\s)]+)"?\s*\)\s*\{', text))
    cells = {}
    for index, match in enumerate(matches):
        body = text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        area = re.search(rf"(?m)^\s*area\s*:\s*({NUMBER})[ \t]*;?", body)
        if area is None:
            raise AnalysisError(f"No Liberty area for cell {match[1]} in {path}")
        cells[match[1]] = {"area_um2": float(area[1]), "sequential": bool(re.search(r"\b(?:ff|latch)\s*\(", body))}
    if not cells:
        raise AnalysisError(f"No cells parsed from configured Liberty library {path}")
    result = cells, hashlib.sha256(path.read_bytes()).hexdigest()
    _LIB_CACHE[key] = result
    return result


def analyze_configuration(build_dir: Path, design: str, technology: str) -> dict[str, Any]:
    circuit, architecture = design.split("-", 1)
    directory = build_dir / design / technology
    config_path = directory / ".config.json"
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text())
            configured_lib = config["techlib"]["lib"]
            configured_top = config["target"]["top"]
        except (KeyError, json.JSONDecodeError) as exc:
            raise AnalysisError(f"Invalid per-build configuration: {config_path}") from exc
        if configured_lib != TECH_LIBS[technology]["lib"] or configured_top != circuit:
            raise AnalysisError(f"Build configuration does not match design/library: {config_path}")
    required = [
        "synth/stdout.log", "synth/netlist.v", "sta/units.log", "sta/timing-min-clock.rpt",
        "sta/timing-longest-paths.rpt", "sta/timing-unique-paths.rpt", "sta/power-switching.rpt", "sta/power-vcd.rpt",
        "sta/stdout-timing.log", "sta/stdout-power-switching.log", "sta/stdout-power-vcd.log",
        "sim/run-stdout.log",
    ]
    # VCDs can be much larger than all the textual reports together. Check the
    # header without retaining the entire waveform in memory.
    vcd_path = directory / "sim" / f"{circuit}_testbench.vcd"
    if not vcd_path.is_file() or vcd_path.stat().st_size == 0:
        raise AnalysisError(f"Missing or empty waveform: {vcd_path}")
    with vcd_path.open("r", encoding="utf-8", errors="replace") as handle:
        header = handle.read(1024 * 1024)
    if "$enddefinitions" not in header or "$timescale" not in header:
        raise AnalysisError(f"Missing complete VCD header: {vcd_path}")
    artifacts = {}
    for filename in required:
        path = directory / filename
        # Successful OpenSTA timing/probabilistic runs can be silent. Their
        # reports must be complete, but the tool stdout logs may be empty.
        if filename in ("sta/stdout-timing.log", "sta/stdout-power-switching.log"):
            if not path.is_file():
                raise AnalysisError(f"Missing tool log: {path}")
            artifacts[filename] = path.read_text(encoding="utf-8", errors="replace")
        else:
            artifacts[filename] = read_required(path)
    for filename, content in artifacts.items():
        if filename.endswith(".log"):
            reject_errors(content, directory / filename)
    if "[PASS]" not in artifacts["sim/run-stdout.log"]:
        raise AnalysisError(f"Missing actual testbench [PASS] result in {directory}/sim/run-stdout.log")
    if "[FAIL]" in artifacts["sim/run-stdout.log"]:
        raise AnalysisError(f"Testbench failed in {directory}/sim/run-stdout.log")
    scale_s, time_unit = parse_time_units(artifacts["sta/units.log"])
    try:
        delay_native = positive(float(artifacts["sta/timing-min-clock.rpt"].strip()), "critical timing delay")
    except ValueError as exc:
        raise AnalysisError(f"Invalid timing-min-clock.rpt in {directory}") from exc
    area, counts, metadata_count = parse_synthesis(artifacts["synth/stdout.log"], circuit)
    cells, liberty_sha256 = liberty_cells(technology)
    missing = set(counts) - set(cells)
    if missing:
        raise AnalysisError(f"Mapped cells absent from configured {technology} Liberty: {sorted(missing)}")
    reconstructed_area = sum(count * cells[name]["area_um2"] for name, count in counts.items())
    if not math.isclose(area, reconstructed_area, rel_tol=2e-5, abs_tol=1e-5):
        raise AnalysisError(f"Liberty sum {reconstructed_area} disagrees with final synthesis area {area} in {directory}")
    sequential_names = [name for name in counts if cells[name]["sequential"]]
    seq_area = sum(counts[name] * cells[name]["area_um2"] for name in sequential_names)
    seq_count = sum(counts[name] for name in sequential_names)
    if (circuit == "adder32" and seq_count != 0) or (circuit == "counter32" and seq_count != 32):
        raise AnalysisError(f"Unexpected sequential cell count {seq_count} for {design}")
    probabilistic = parse_power(artifacts["sta/power-switching.rpt"], "probabilistic power report")
    vcd = parse_power(artifacts["sta/power-vcd.rpt"], "VCD power report")
    annotated, total = parse_vcd_annotation(artifacts["sta/stdout-power-vcd.log"])
    longest_text = artifacts["sta/timing-longest-paths.rpt"]
    _, npaths, longest_npairs, repeated = parse_timing_paths(longest_text, scale_s, require_three=False)
    paths, unique_npaths, npairs, _ = parse_timing_paths(artifacts["sta/timing-unique-paths.rpt"], scale_s)
    # The original globally ranked report can be saturated by alternate paths
    # between one pair. The separate per-source report includes the worst path
    # for every reachable pair, so it determines the three distinct winners.
    source_names = [name.split(" (")[0].strip() for name in re.findall(r"(?m)^Startpoint:\s*(.+)", longest_text)]
    endpoint_names = [name.split(" (")[0].strip() for name in re.findall(r"(?m)^Endpoint:\s*(.+)", longest_text)]
    longest_counts = Counter(zip(source_names, endpoint_names))
    for path in paths:
        path["occurrences_same_pair"] = longest_counts[(path["startpoint"], path["endpoint"])]
    if not math.isclose(delay_native, -paths[0]["slack_native"], rel_tol=1e-6, abs_tol=1e-8):
        raise AnalysisError(f"Critical delay disagrees with worst per-source timing path in {directory}")
    clock_warning = re.search(rf"clock\s+\S+\s+vcd period\s+({NUMBER})\s+differs from SDC clock period\s+({NUMBER})",
                              artifacts["sta/stdout-power-vcd.log"])
    critical_s = delay_native * scale_s
    row = {
        "design": design, "circuit": circuit, "architecture": architecture,
        "technology": technology, "node_nm": NODE_NM[technology],
        "area_um2": area, "mapped_cell_count": sum(counts.values()), "metadata_cell_count": metadata_count,
        "sequential_cell_count": seq_count, "sequential_area_um2": seq_area,
        "sequential_area_fraction": seq_area / area, "delay_native": delay_native,
        "time_unit": time_unit, "cycle_time_s": critical_s, "delay_ns": critical_s * 1e9,
        "frequency_hz": 1 / critical_s, "performance_per_area_hz_per_um2": 1 / (critical_s * area),
        "probabilistic_power_w": probabilistic["total_w"], "vcd_power_w": vcd["total_w"],
        "power_relative_difference": abs(vcd["total_w"] - probabilistic["total_w"]) / probabilistic["total_w"],
        "testbench_status": "PASS", "vcd_annotated_pins": annotated, "vcd_total_pins": total,
        "vcd_unannotated_pins": total - annotated if total is not None else None,
        "vcd_clock_period_s": float(clock_warning[1]) * scale_s if clock_warning else None,
        "paths_reported": npaths, "unique_path_pairs": npairs,
        "longest_report_unique_pairs": longest_npairs, "unique_report_paths": unique_npaths,
        "timing_pair_report_method": "Worst path to each endpoint, queried separately for every primary-input/register-output source",
        "top_paths": paths, "repeated_endpoint_pairs": repeated, "cell_counts": counts,
        "probabilistic_power_components": probabilistic, "vcd_power_components": vcd,
        "liberty_file": TECH_LIBS[technology]["lib"], "liberty_sha256": liberty_sha256,
        "artifact_directory": str(directory.resolve()),
    }
    for model, power in (("probabilistic", probabilistic["total_w"]), ("vcd", vcd["total_w"])):
        row[f"{model}_energy_j"] = power * critical_s
        row[f"{model}_throughput_per_watt_ops_per_j"] = 1 / (power * critical_s)
        row[f"{model}_handout_time_per_power_s_per_w"] = critical_s / power
    return row


def make_plots(rows: list[dict[str, Any]], output_dir: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "pdf.fonttype": 42, "ps.fonttype": 42})
    colors = ("#4477AA", "#EE6677", "#228833")
    names = ("Ripple carry", "Kogge–Stone", "Brent–Kung")
    metrics = (
        ("area_um2", 1, "Mapped cell area (µm²)"),
        ("delay_ns", 1, "Critical delay (ns)"),
        ("probabilistic_power_w", 1e6, "Probabilistic power (µW)"),
        ("vcd_power_w", 1e6, "VCD power (µW)"),
        ("probabilistic_energy_j", 1e15, "Probabilistic energy (fJ/op)"),
        ("vcd_energy_j", 1e15, "VCD energy (fJ/op)"),
    )
    output_paths = []
    for circuit in CIRCUITS:
        selected = [row for row in rows if row["circuit"] == circuit]
        if not selected:
            continue
        available_techs = [tech for tech in TECHNOLOGIES if any(row["technology"] == tech for row in selected)]
        fig, axes = plt.subplots(2, 3, figsize=(13.8, 7.6))
        width = .23
        x = np.arange(len(available_techs))
        for axis, (metric, multiplier, label) in zip(axes.flat, metrics):
            for index, (architecture, name, color) in enumerate(zip(ARCHITECTURES, names, colors)):
                values = [next((row[metric] * multiplier for row in selected
                                if row["technology"] == tech and row["architecture"] == architecture), float("nan"))
                          for tech in available_techs]
                bars = axis.bar(x + (index - 1) * width, values, width, label=name, color=color, edgecolor="white", linewidth=.4)
                axis.bar_label(bars, labels=[f"{value:.3g}" if math.isfinite(value) else "" for value in values],
                               fontsize=7, padding=2, rotation=90)
            axis.set_xticks(x, [f"{tech}\n{NODE_NM[tech]} nm" for tech in available_techs])
            axis.set_xlim(-.6, len(available_techs) - .4)
            axis.set_ylabel(label)
            # Different process nodes span orders of magnitude in area/power.
            # A logarithmic axis keeps architecture comparisons legible at each node.
            axis.set_yscale("log")
            axis.grid(axis="y", which="major", alpha=.25, linewidth=.6)
            axis.set_axisbelow(True)
            low, high = axis.get_ylim()
            axis.set_ylim(low, high * 2)
        handles, labels = axes[0, 0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(.5, .97))
        fig.suptitle(f"32-bit {'standalone adders' if circuit == 'adder32' else 'counters'}: mapped-cell comparisons", y=1.0, fontsize=14)
        fig.text(.5, .005, "Logarithmic y axes. Energy = critical delay × power; excludes physical implementation and routing.",
                 ha="center", fontsize=9)
        fig.tight_layout(rect=(0, .025, 1, .93))
        for suffix in ("pdf", "png"):
            filename = f"{circuit}-comparison.{suffix}"
            fig.savefig(output_dir / filename, dpi=220, bbox_inches="tight", metadata={"Creator": "CS505 Lab 1 analysis"})
            output_paths.append(filename)
        plt.close(fig)
    return output_paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--build-dir", type=Path, default=PROJECT_DIR / "build")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_DIR / "results")
    parser.add_argument("--design", action="append", choices=DESIGNS, help="Select completed design(s); default: all six")
    parser.add_argument("--tech", action="append", choices=TECHNOLOGIES, help="Select completed technology(s); default: all three")
    parser.add_argument("--no-plots", action="store_true", help="Validate and export numeric results without Matplotlib")
    args = parser.parse_args()
    designs = tuple(dict.fromkeys(args.design or DESIGNS))
    technologies = tuple(dict.fromkeys(args.tech or TECHNOLOGIES))
    rows, errors = [], []
    for design in designs:
        for technology in technologies:
            try:
                row = analyze_configuration(args.build_dir, design, technology)
                rows.append(row)
                print(f"[PASS] {design}/{technology}: area {row['area_um2']:.6g} µm², delay {row['delay_ns']:.6g} ns")
            except (AnalysisError, OSError) as exc:
                errors.append(f"{design}/{technology}: {exc}")
    if errors:
        for error in errors:
            print(f"[ERROR] {error}", file=sys.stderr)
        print("No results were exported: every selected configuration must pass validation.", file=sys.stderr)
        return 1
    args.output_dir.mkdir(parents=True, exist_ok=True)
    plots = [] if args.no_plots else make_plots(rows, args.output_dir)
    document = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "build_dir": str(args.build_dir.resolve()),
        "complete_matrix": len(rows) == len(DESIGNS) * len(TECHNOLOGIES),
        "methodology": {
            "area_units": "Mapped Liberty cell areas in µm²; sequential area sums cells with ff/latch groups.",
            "time_units": "Native STA delay converted using report_units Time scale; normalized CSV columns use s and ns.",
            "power_units": "OpenSTA report_power prints watts directly; report_units leakage-power factor is not applied.",
            "performance_per_watt_note": "Conventional throughput/W = 1/(T*P). The handout's literal T/P is reported separately.",
            "energy_note": "Energy/op = P*T at critical-delay operation rate; VCD power is tied to the testbench's measured workload.",
            "power_relative_difference_definition": "abs(VCD - probabilistic) / probabilistic",
            "timing_paths_note": "Three slowest distinct start/end pairs come from per-source enumeration. occurrences_same_pair counts appearances in the original globally ranked report; zero means the pair was absent from that truncated report.",
            "csv_note": "Project-defined CSV headers; the official CSV-template requirement was deleted.",
        },
        "rows": rows, "plots": plots,
    }
    (args.output_dir / "results.json").write_text(json.dumps(document, indent=2) + "\n")
    with (args.output_dir / "results.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Exported {len(rows)} validated configurations to {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
