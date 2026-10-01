#!/usr/bin/env python3
"""Generate the assignment PDF from validated experiment results, never invented data."""
import argparse
import datetime as dt
import json
from pathlib import Path
import shutil
import subprocess
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TECHS = ('asap7', 'nan45', 'sky130')
ARCHS = ('ripple-carry', 'kogge-stone', 'brent-kung')
LABELS = {'asap7': 'ASAP7 (7 nm)', 'nan45': 'Nangate45 (45 nm)',
          'sky130': 'Sky130HD (130 nm)', 'ripple-carry': 'Ripple-carry',
          'kogge-stone': 'Kogge--Stone', 'brent-kung': 'Brent--Kung'}


def esc(value):
    replacements = {'\\': r'\textbackslash{}', '_': r'\_', '&': r'\&',
                    '%': r'\%', '#': r'\#', '$': r'\$', '{': r'\{',
                    '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
    return ''.join(replacements.get(c, c) for c in str(value))


def number(value):
    return f'{value:.4g}'


def table(headers, rows, columns=None):
    columns = columns or ('l' + 'r' * (len(headers) - 1))
    lines = [r'\begin{center}\small', r'\begin{tabular}{' + columns + '}', r'\toprule',
             ' & '.join(headers) + r' \\', r'\midrule']
    lines.extend(' & '.join(map(str, row)) + r' \\' for row in rows)
    lines.extend([r'\bottomrule', r'\end{tabular}', r'\end{center}'])
    return '\n'.join(lines)


def correlation(rows, field):
    x = np.array([r['frequency_hz'] for r in rows])
    y = np.array([r[field] for r in rows])
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        return 'undefined (constant values)'
    return f'{np.corrcoef(x, y)[0, 1]:.3f}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results-dir', type=Path, default=ROOT / 'results')
    parser.add_argument('--manifest', type=Path, default=ROOT / 'build/build-manifest.json')
    args = parser.parse_args()
    result_dir = args.results_dir.resolve()
    data = json.loads((result_dir / 'results.json').read_text())
    rows = data['rows']
    expected = {(c, a, t) for c in ('adder32', 'counter32') for a in ARCHS for t in TECHS}
    actual = {(r['circuit'], r['architecture'], r['technology']) for r in rows}
    if actual != expected or len(rows) != 18 or any(r['testbench_status'] != 'PASS' for r in rows):
        raise ValueError('Report requires all 18 unique configurations with passing tests.')
    manifest = json.loads(args.manifest.read_text()) if args.manifest.exists() else {}
    for architecture in ARCHS:
        formal_dir = args.manifest.resolve().parent / 'formal' / architecture
        for design in ('adder', 'counter'):
            proof = (formal_dir / f'prove-{design}.log').read_text()
            if 'SAT proof finished - no model found: SUCCESS!' not in proof:
                raise ValueError(f'Missing successful SAT proof for {architecture}/{design}.')
        for circuit in ('adder32', 'counter32'):
            simulation = (formal_dir / f'simulate-{circuit}.log').read_text()
            if '[PASS]' not in simulation or '[FAIL]' in simulation or 'FATAL:' in simulation:
                raise ValueError(f'Missing passing RTL simulation for {architecture}/{circuit}.')
    row_by = {(r['circuit'], r['architecture'], r['technology']): r for r in rows}
    ordered = lambda c, t: [row_by[c, a, t] for a in ARCHS]
    parts = [r'''\documentclass[10pt,letterpaper]{article}
\usepackage[margin=0.7in]{geometry}
\usepackage[T1]{fontenc}
\usepackage{amsmath,booktabs,longtable,tabularx,graphicx,hyperref}
\hypersetup{colorlinks=true,urlcolor=blue,linkcolor=blue}
\setlength{\parindent}{0pt}
\setlength{\parskip}{5pt}
\setlength{\emergencystretch}{3em}
\title{CS 505 Fall 2026 --- Lab 1\\32-bit Adder Design Space Exploration}
\author{Reproducible implementation and experimental report}
\date{''' + dt.datetime.now(ZoneInfo('America/New_York')).strftime('%B %d, %Y') + r'''}
\begin{document}
\maketitle

\section{Designs, experiment method, and verification}
The experiment compares the supplied ripple-carry adder with two new standalone
implementations, Kogge--Stone and Brent--Kung. Each has exactly the supplied
\texttt{adder32(a,b,cin,sum,cout)} interface. Every design is evaluated both as a
combinational adder and inside the supplied 32-bit synchronous counter, using
the supplied ASAP7 LVT TT, Nangate45 typical, and Sky130HD TT cell libraries.
This gives 18 configurations. The optional NAND-only Nangate library is excluded.

Both new designs first form $p_i=a_i\oplus b_i$ and $g_i=a_i b_i$.
Prefix groups combine as $(G_H,P_H)\circ(G_L,P_L)=
(G_H\lor(P_H\land G_L),P_H\land P_L)$.
Kogge--Stone uses five prefix stages with distances 1, 2, 4, 8, and 16
(129 prefix-combine nodes). Brent--Kung uses five reduction stages followed by
four distribution stages at distances 8, 4, 2, and 1 (57 combine nodes).
Complete prefixes provide $c_0=cin$, $c_{i+1}=G_{i:0}\lor(P_{i:0}\land cin)$,
$sum_i=p_i\oplus c_i$, and $cout=c_{32}$. The original bit propagate values are
retained for the sum. The RTL uses explicit combinational stages rather than
an inferred generic addition operator. These node counts describe the source
prefix graphs, not the number of cells after optimization and mapping.

Yosys maps each design into the selected library. OpenSTA first determines
the minimum timing period, then estimates power with input activity 0.2
transitions per minimum period. Verilator simulates the mapped netlist using
the supplied cell simulation models and produces the VCD used in a separate
power analysis. Thus correctness, area, timing, and power refer to the same
mapped implementation. All 18 mapped simulations passed; the analyzer also
requires nonzero VCD activity annotation and complete reports.

The enhanced adder bench compares all 33 result bits, including carry-out,
uses directed full/partial carry chains and overflow cases with both values
of carry-in, and then 100,000 deterministic pseudorandom vectors. The counter
bench checks reset results after clock edges, normal counting, and reset during counting.
Icarus runs both benches against every RTL architecture. In addition, six
Yosys SAT proofs pass: complete 33-bit addition for all $2^{65}$ combinations
of inputs in each architecture, and the counter transition/reset property
from an unconstrained register state for each architecture. The latter covers
wraparound from \texttt{0xffffffff} without simulating billions of cycles.

The adder stimulus interval is 0.9855 ns (quantized to the testbench 1 ps
precision); the counter clock period is 10 ns. These VCD workloads are fixed
across architectures and technologies. Their activity rates differ from the
probabilistic model, which uses each circuit's minimum period. Consequently,
differences between the two power columns reflect both activity assumptions
and rate assumptions, not only circuit implementation. Specify timing checks
are ignored by Verilator; this is functional gate-level activity, not a
post-layout, delay-annotated measurement of silicon glitches.

\subsection{Units and derived metrics}
Timing reports use ps for ASAP7 and ns for Nangate45/Sky130HD; the analyzer
reads \texttt{sta/units.log} and converts to seconds before calculations.
OpenSTA's \texttt{report\_power} table is already in watts, even when
\texttt{report\_units} shows a different Liberty power unit.
Area is the sum of mapped cell areas in the library, reported as $\mu m^2$;
it does not include placement utilization or routed wire area.
Let $T$ be the minimum period in seconds, $A$ mapped area, and $P$ total power.
Then throughput is $f=1/T$, performance/area is $f/A$, and energy/operation
is $E=PT$. Conventional throughput/watt is $f/P=1/(TP)$ in operations/joule.
The handout instead explicitly specifies $T/P$ for ``performance per Watt'';
both quantities are retained with distinct names in the results and tables.
Neither is silently substituted for the other.

The provided screenshot removes the official-template CSV instruction. The
generated \texttt{results.csv} is therefore an auxiliary reproducibility
artifact with our own explicit headers, not a purported official template.

\section{Measured PPA results}
The tables report total power (internal, switching, and leakage combined).
All rows passed their mapped testbench. Energy here follows the handout's
$PT$ definition using the minimum period. For VCD power, $P$ is measured at
the fixed simulation workload rate: its $PT$ value is an assignment-defined
metric, not the directly measured energy per simulated transaction.
''']
    for circuit, title in [('adder32', 'Standalone adders'), ('counter32', 'Counters')]:
        parts.append(r'\subsection{' + title + '}')
        for tech in TECHS:
            parts.append(r'\textbf{' + LABELS[tech] + '}')
            entries = []
            for row in ordered(circuit, tech):
                entries.append([LABELS[row['architecture']], number(row['area_um2']),
                                number(row['delay_ns']), number(row['probabilistic_power_w'] * 1e6),
                                number(row['vcd_power_w'] * 1e6),
                                number(row['probabilistic_energy_j'] * 1e15),
                                number(row['vcd_energy_j'] * 1e15)])
            parts.append(table(['Architecture', r'$A$ ($\mu m^2$)', '$T$ (ns)',
                                r'$P_{prob}$ ($\mu W$)', r'$P_{VCD}$ ($\mu W$)',
                                '$E_{prob}$ (fJ)', '$E_{VCD}$ (fJ)'], entries))
        plot = result_dir / f'{circuit}-comparison.pdf'
        if not plot.exists():
            raise ValueError(f'Missing report plot: {plot}')
        parts.append(r'\begin{center}\includegraphics[width=\linewidth]{\detokenize{' + str(plot)
                     + r'}}\end{center}')

    parts.append(r'''\section{Qualitative questions}
\subsection{1. What is a netlist, and why analyze it?}
\texttt{synth/netlist.v} describes the cells and connections that Yosys actually
selected after flattening, optimization, and technology mapping. Behavioral
Verilog and prefix equations do not identify cell sizes, input capacitances,
timing arcs, leakage, or internal-power tables. Those depend on the selected
library. For this experiment, the source node counts are fixed at 129 and 57,
but the mapped area and delay vary by technology and counter constant folding.
Analyzing the mapped netlist associates the circuit with those physical cell
models and accounts for logic that was optimized away.

\subsection{2. Two reasons an implementation might run faster than STA suggests}
First, STA can include a structurally connected path that cannot be logically
sensitized by a legal input transition (a false path), or use combinations of
worst-case transitions that cannot occur together. A sensitization proof and
appropriate constraints can remove that pessimism. A merely rare path is
still relevant if correctness is required for every legal input.
Second, real operating voltage, temperature, process, input slew, or load may
be more favorable than the conditions used by the cell timing model. Cell
characterization is a model; actual silicon under more favorable conditions
can have a shorter delay. These are possible explanations, not measured
speedups or proven false paths in these adders. Our supplied files use typical
corners; no corner sweep or physical implementation was performed. Missing
routed parasitics can also make this flow optimistic, so exceeding its
frequency estimate is not guaranteed.

\subsection{3. How can the original testbenches be improved?}
Random testing alone misses very long carry chains with high probability, and
the original adder bench checks only the low 32 sum bits. The implemented
bench explicitly checks $\{cout,sum\}$, exercises every carry-chain length,
tests both carry-in values, and makes failures terminate with a nonzero status.
Deterministic pseudorandom inputs reproduce failures across simulators. The
counter bench checks reset during operation as well as normal increments.
Formal proof covers every input/state, including carry-out and wraparound;
mapped-netlist simulation then checks technology-model integration. Four-state
Icarus simulation complements Verilator's mostly two-state simulation.

\subsection{4. Where does VCD activity come from, and what affects its power?}
The VCD records signal changes while Verilator executes each synthesized
netlist with the testbench stimuli. OpenSTA matches the correct
\texttt{adder32\_testbench/dut} or \texttt{counter32\_testbench/dut} scope and
uses annotated activity to estimate power. Random addition toggles many bits;
counting has strongly unequal activity by bit position. Changing data patterns,
input rate, reset fraction, simulated duration, dump coverage, or delay models
changes the observed transition densities and hence switching/internal power.
Leakage is less dependent on transition rate. A counter trace of roughly
100,000 increments mostly exercises low bits, while higher bits rarely toggle;
formal correctness coverage does not turn that workload into a full activity
sample of all states. The short directed adder prelude is included in its VCD
and is identical across comparisons. The raw VCD files and annotation logs
are retained, rather than assuming every pin received valid activity.

\section{Quantitative questions}
\subsection{1. Three slowest unique start/end pairs}
Appendix A lists the three slowest distinct pairs for every configuration.
The original longest-path report is capped at 1,000 paths and can be dominated
by repeated routes for a single pair. A supplementary
\texttt{timing-unique-paths.rpt} enumerates the worst path per reachable pair
by querying each primary-input or register-output source separately.
Paths are ordered by reported slack; with the zero-period timing run this
captures the limiting timing requirement. A pair can appear more than once
because STA enumerates different intervening cell/pin routes and rise/fall
transitions; the same endpoints need not identify the same timing path.
For counters, setup/capture timing contributes to the minimum cycle time,
so data-arrival time alone need not equal the required period. No repeated
pair is counted twice in the appendix's three-pair selection.

\subsection{2. Performance versus performance/area and energy}
For each technology, the following table gives Pearson correlations between
raw throughput and the other metrics across our three standalone adders.
For energy, negative correlation means higher throughput accompanies lower
energy. With only three designs these values are descriptive, not evidence
of statistical significance or a general law.
''')
    entries = []
    for tech in TECHS:
        entries.append([LABELS[tech], correlation(ordered('adder32', tech), 'performance_per_area_hz_per_um2'),
                        correlation(ordered('adder32', tech), 'probabilistic_energy_j'),
                        correlation(ordered('adder32', tech), 'vcd_energy_j')])
    parts.append(table(['Technology', '$r(f,f/A)$', '$r(f,E_{prob})$', '$r(f,E_{VCD})$'], entries))
    for tech in TECHS:
        group = ordered('adder32', tech)
        rank = lambda field, reverse: ', '.join(LABELS[r['architecture']] for r in sorted(group, key=lambda r: r[field], reverse=reverse))
        parts.append(r'\textbf{' + LABELS[tech] + '}: throughput order: ' + rank('frequency_hz', True)
                     + '; performance/area order: ' + rank('performance_per_area_hz_per_um2', True)
                     + '. Lowest probabilistic energy: ' + LABELS[min(group, key=lambda r: r['probabilistic_energy_j'])['architecture']]
                     + '; lowest VCD energy: ' + LABELS[min(group, key=lambda r: r['vcd_energy_j'])['architecture']] + '.')
    parts.append(r'''A faster design can spend more area and draw more power, so the best
raw delay need not maximize $f/A$ or minimize $PT$. The probability model's
activity rate scales with $1/T$, while the VCD workload rate is fixed; energy
rankings can consequently differ between power models.

\subsection{3. Does architecture improvement scale equally at 7 and 130 nm?}
''')
    entries = []
    speedups = {}
    for tech in TECHS:
        group = ordered('adder32', tech)
        fastest = min(group, key=lambda r: r['cycle_time_s'])
        slowest = max(group, key=lambda r: r['cycle_time_s'])
        speedups[tech] = slowest['cycle_time_s'] / fastest['cycle_time_s']
        rca = row_by['adder32', 'ripple-carry', tech]
        ks = row_by['adder32', 'kogge-stone', tech]
        bk = row_by['adder32', 'brent-kung', tech]
        entries.append([LABELS[tech], LABELS[fastest['architecture']], LABELS[slowest['architecture']],
                        f'{speedups[tech]:.3f}', f'{rca["cycle_time_s"] / ks["cycle_time_s"]:.3f}',
                        f'{rca["cycle_time_s"] / bk["cycle_time_s"]:.3f}'])
    parts.append(table(['Technology', 'Fastest', 'Slowest', 'Fast/slow speedup', 'KS/RCA', 'BK/RCA'], entries, 'lllrrr'))
    difference_percent = (speedups['asap7'] / speedups['sky130'] - 1) * 100
    benefit_conclusion = ('The architecture benefit is comparable within five percent between these nodes. '
                          if abs(difference_percent) <= 5 else
                          'The architecture benefit does not scale equally between these nodes. ')
    parts.append(f'The measured fastest/slowest speedup is {speedups["asap7"]:.3f} at 7 nm and '
                 f'{speedups["sky130"]:.3f} at 130 nm. ' +
                 f'The 7 nm speedup factor differs from the 130 nm factor by {difference_percent:+.2f} percent, '
                 'relative to the 130 nm factor. ' + benefit_conclusion +
                 r'''These ratios, rather than absolute delay, show the relative architecture benefit.
Technology libraries differ in relative XOR and AND/OR delays, complex-gate
availability, drive strengths, fanout sensitivity, and ABC mapping choices.
The same prefix equations can map to different gate chains. Faster processes
therefore do not uniformly scale every architecture by the same factor.
Our flow has no routed-wire extraction, so wire-layout explanations remain
hypotheses rather than measured causes here.

\subsection{4. Discrepancy between 7 nm counter power estimates}
''')
    group = ordered('counter32', 'asap7')
    absolute = lambda r: abs(r['vcd_power_w'] - r['probabilistic_power_w'])
    entries = [[LABELS[r['architecture']], number(r['probabilistic_power_w'] * 1e6),
                number(r['vcd_power_w'] * 1e6), number(absolute(r) * 1e6),
                f'{r["power_relative_difference"] * 100:.2f}'] for r in group]
    parts.append(table(['Architecture', r'$P_{prob}$ ($\mu W$)', r'$P_{VCD}$ ($\mu W$)',
                        r'$|\Delta P|$ ($\mu W$)', r'$|\Delta P|/P_{prob}$ (\%)'], entries))
    parts.append('By absolute difference, the smallest discrepancy is ' +
                 LABELS[min(group, key=absolute)['architecture']] + ' and the largest is ' +
                 LABELS[max(group, key=absolute)['architecture']] + '. By relative difference, the smallest is ' +
                 LABELS[min(group, key=lambda r: r['power_relative_difference'])['architecture']] +
                 ' and the largest is ' + LABELS[max(group, key=lambda r: r['power_relative_difference'])['architecture']] + '.')
    parts.append(r'''Probabilistic input activity and propagated statistical assumptions differ
from the correlated binary-count sequence. Counter high bits rarely toggle,
the VCD covers only a finite counting interval, and reset changes the activity.
The statistical power run uses each minimum period while the VCD clock is
10 ns. Clocked cell/internal power can therefore dominate the discrepancy.
Library internal/leakage power models, and functional simulation's limited
glitch information, are additional model differences. Constant $b=0$, $cin=1$,
and unused carry-out also allow synthesis to simplify an adder into an incrementer.

\subsection{5. Counter area devoted to sequential elements}
Sequential area is computed from mapped sequential-cell counts times each
cell's Liberty area, then divided by total mapped area. A cell is identified
as sequential through its Liberty \texttt{ff}/\texttt{latch} definition,
rather than its name alone.
''')
    entries = []
    for tech in TECHS:
        for row in ordered('counter32', tech):
            entries.append([LABELS[tech], LABELS[row['architecture']], str(row['sequential_cell_count']),
                            number(row['sequential_area_um2']), number(row['area_um2']),
                            f'{row["sequential_area_fraction"] * 100:.2f}'])
    parts.append(table(['Technology', 'Architecture', 'Seq. cells', r'$A_{seq}$ ($\mu m^2$)',
                        r'$A_{total}$ ($\mu m^2$)', r'Seq. area (\%)'], entries, 'llrrrr'))
    for tech in TECHS:
        shares = [r['sequential_area_fraction'] * 100 for r in ordered('counter32', tech)]
        parts.append(LABELS[tech] + f': sequential share ranges from {min(shares):.2f} to {max(shares):.2f} percent '
                     f'(spread {max(shares)-min(shares):.2f} percentage points).')
    all_shares = [r['sequential_area_fraction'] * 100 for r in rows if r['circuit'] == 'counter32']
    within_spread = max(np.ptp([r['sequential_area_fraction'] * 100 for r in ordered('counter32', tech)])
                        for tech in TECHS)
    parts.append(f'Across all counters the share ranges from {min(all_shares):.2f} to {max(all_shares):.2f} percent. '
                 f'The largest within-node spread is {within_spread:.2f} percentage points; '
                 f'the total cross-design/node spread is {max(all_shares)-min(all_shares):.2f} percentage points. '
                 'The ratio is therefore ' + ('constant to the displayed precision.'
                    if max(all_shares)-min(all_shares) < .005 else
                    'not constant across all designs and technologies.'))
    parts.append(r'''The architectural state is always 32 bits, but the fraction is determined
by flip-flop area relative to combinational increment/reset logic. Different
adder structures and synthesis simplifications can change the denominator;
different technologies change both flop and logic cell areas. Thus a constant
state-bit count alone does not imply a constant area ratio. The measured table
shows how closely that ratio agrees in each library.

\section{Reproduction and artifacts}
From the repository root run \texttt{python3 scripts/run\_experiments.py --force}.
It runs RTL simulation and formal verification, builds all 18 configurations,
validates/parses the reports, generates plots and this PDF, and creates
\texttt{submission.zip} containing the two new RTL files and \texttt{report.pdf}.
The optional \texttt{--skip-build} regenerates analysis/report from existing
builds; it still reruns RTL checks. A fresh build needs the supplied ilab tool
and library paths, Icarus, Python with NumPy/Matplotlib, and pdfLaTeX.
\texttt{build/build-manifest.json} records executable versions, exact commands,
the original repository revision, and SHA-256 hashes of input source/library
files. Per-target configuration files record build settings. The raw netlists,
STA reports, simulation logs, VCDs, and proof logs remain under \texttt{build/}.
\texttt{results/results.json}, \texttt{results/results.csv}, and figures are
regenerable auxiliary files. No remote submission was performed.
''')
    if manifest.get('tools'):
        parts.append(r'\textbf{Recorded tool versions:}')
        for name in ('yosys', 'opensta', 'verilator', 'iverilog'):
            version = manifest['tools'].get(name, {}).get('output', '').splitlines()
            if version:
                parts.append(esc(name + ': ' + version[0]) + r'\par')
    parts.append(r'''\appendix
\section{Three slowest unique endpoint pairs for every configuration}
Names are copied from each \texttt{sta/timing-unique-paths.rpt}. The table
reports the magnitude of worst slack normalized to ns (the timing requirement)
and the number of occurrences of that endpoint pair in the original capped
\texttt{timing-longest-paths.rpt}. Zero means that pair did not appear within
the first 1,000 raw paths, although it is present in the complete unique-pair report.
''')
    for circuit in ('adder32', 'counter32'):
        for tech in TECHS:
            for row in ordered(circuit, tech):
                parts.append(r'\subsection{' + esc(circuit) + ': ' + LABELS[row['architecture']] + ', ' + LABELS[tech] + '}')
                parts.append(r'\begin{tabularx}{\linewidth}{XXrr}\toprule Startpoint & Endpoint & Requirement (ns) & Occurrences \\ \midrule')
                for path in row['top_paths'][:3]:
                    start = str(path['startpoint']).replace('{', '').replace('}', '')
                    end = str(path['endpoint']).replace('{', '').replace('}', '')
                    parts.append(r'\nolinkurl{' + start + r'} & \nolinkurl{' + end + '} & ' +
                                 number(path['delay_ns']) + ' & ' + str(path['occurrences_same_pair']) + r' \\')
                parts.append(r'\bottomrule\end{tabularx}')
    parts.append(r'''\section{Both definitions of the requested efficiency metric}
Here $T/P$ is the handout's literal quantity in s/W. Throughput/W is the
conventional $1/(TP)$, shown in trillions of operations per joule (TOp/J).
The complete CSV also contains throughput, performance/area, and both energies.
''')
    for circuit in ('adder32', 'counter32'):
        parts.append(r'\subsection{' + esc(circuit) + '}')
        entries = []
        for tech in TECHS:
            for r in ordered(circuit, tech):
                entries.append([LABELS[tech], LABELS[r['architecture']],
                                number(r['probabilistic_handout_time_per_power_s_per_w']),
                                number(r['vcd_handout_time_per_power_s_per_w']),
                                number(r['probabilistic_throughput_per_watt_ops_per_j'] / 1e12),
                                number(r['vcd_throughput_per_watt_ops_per_j'] / 1e12)])
        parts.append(table(['Technology', 'Architecture', '$T/P_{prob}$', '$T/P_{VCD}$',
                            '$f/P_{prob}$', '$f/P_{VCD}$'], entries, 'llrrrr'))
    parts.append(r'\end{document}')
    texfile = result_dir / 'report.tex'
    texfile.write_text('\n\n'.join(parts) + '\n')
    logfile = result_dir / 'report-build.log'
    with logfile.open('w') as log:
        for _ in range(2):
            subprocess.run(['pdflatex', '-interaction=nonstopmode', '-halt-on-error',
                            '-output-directory', str(result_dir), str(texfile)],
                           cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    shutil.copyfile(result_dir / 'report.pdf', ROOT / 'report.pdf')
    print(f'Generated {ROOT / "report.pdf"}')


if __name__ == '__main__':
    main()
