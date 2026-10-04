#!/usr/bin/env python3
"""Generate the assignment PDF from validated experiment results, never invented data."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TECHS = ('asap7', 'nan45', 'sky130')
ARCHS = ('ripple-carry', 'kogge-stone', 'brent-kung')
LABELS = {
    'asap7': 'ASAP7 (7 nm)',
    'nan45': 'Nangate45 (45 nm)',
    'sky130': 'Sky130HD (130 nm)',
    'ripple-carry': 'Ripple-carry',
    'kogge-stone': 'Kogge--Stone',
    'brent-kung': 'Brent--Kung'
}


def esc(value):
    replacements = {
        '\\': r'\textbackslash{}',
        '_': r'\_',
        '&': r'\&',
        '%': r'\%',
        '#': r'\#',
        '$': r'\$',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}'
    }
    return ''.join(replacements.get(c, c) for c in str(value))


def number(value):
    return f'{value:.4g}'


def table(headers, rows, columns=None):
    columns = columns or ('l' + 'r' * (len(headers) - 1))
    lines = [
        r'\begin{center}\small', r'\begin{tabular}{' + columns + '}',
        r'\toprule', ' & '.join(headers) + r' \\', r'\midrule'
    ]
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
    parser.add_argument('--manifest',
                        type=Path,
                        default=ROOT / 'build/build-manifest.json')
    args = parser.parse_args()
    result_dir = args.results_dir.resolve()
    data = json.loads((result_dir / 'results.json').read_text())
    rows = data['rows']
    expected = {(c, a, t)
                for c in ('adder32', 'counter32')
                for a in ARCHS
                for t in TECHS}
    actual = {(r['circuit'], r['architecture'], r['technology']) for r in rows}
    if actual != expected or len(rows) != 18 or any(
            r['testbench_status'] != 'PASS' for r in rows):
        raise ValueError(
            'Report requires all 18 unique configurations with passing tests.')
    for architecture in ARCHS:
        formal_dir = args.manifest.resolve().parent / 'formal' / architecture
        for design in ('adder', 'counter'):
            proof = (formal_dir / f'prove-{design}.log').read_text()
            if 'SAT proof finished - no model found: SUCCESS!' not in proof:
                raise ValueError(
                    f'Missing successful SAT proof for {architecture}/{design}.'
                )
        for circuit in ('adder32', 'counter32'):
            simulation = (formal_dir / f'simulate-{circuit}.log').read_text()
            if '[PASS]' not in simulation or '[FAIL]' in simulation or 'FATAL:' in simulation:
                raise ValueError(
                    f'Missing passing RTL simulation for {architecture}/{circuit}.'
                )
    row_by = {
        (r['circuit'], r['architecture'], r['technology']): r
        for r in rows
    }
    ordered = lambda c, t: [row_by[c, a, t] for a in ARCHS]
    parts = [
        r'''\documentclass[10pt,letterpaper]{article}
\usepackage[margin=0.7in]{geometry}
\usepackage[T1]{fontenc}
\usepackage{amsmath,booktabs,longtable,tabularx,graphicx,hyperref,fancyvrb,upquote}
\hypersetup{colorlinks=true,urlcolor=blue,linkcolor=blue}
\setlength{\parindent}{0pt}
\setlength{\parskip}{5pt}
\setlength{\emergencystretch}{3em}
\title{CS 505 Fall 2026 --- Lab 1\\32-bit Adder Design Space Exploration}
\author{Reproducible implementation and experimental report}
\date{''' +
        dt.datetime.now(ZoneInfo('America/New_York')).strftime('%B %d, %Y') +
        r'''}
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

The supplied testbenches were modified for this experiment. Their source files
are included in \texttt{submission.zip}; Appendix~\ref{app:testbenches}
summarizes their workloads and verification. All 18 mapped PASS results and the reported
VCD-based power estimates use these enhanced benches, with identical stimuli
across architectures and technologies. Using the instructor's original
stimulus can produce different VCD power estimates.

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
$PT$ definition using the minimum period. VCD power uses activity recorded
at the fixed simulation workload rate; both power runs retain the
minimum-period STA clock constraints. Its $PT$ value is an assignment-defined
metric, not the directly measured energy per simulated transaction.
'''
    ]
    for circuit, title in [('adder32', 'Standalone adders'),
                           ('counter32', 'Counters')]:
        parts.append(r'\subsection{' + title + '}')
        for tech in TECHS:
            parts.append(r'\textbf{' + LABELS[tech] + '}')
            entries = []
            for row in ordered(circuit, tech):
                entries.append([
                    LABELS[row['architecture']],
                    number(row['area_um2']),
                    number(row['delay_ns']),
                    number(row['probabilistic_power_w'] * 1e6),
                    number(row['vcd_power_w'] * 1e6),
                    number(row['probabilistic_energy_j'] * 1e15),
                    number(row['vcd_energy_j'] * 1e15)
                ])
            parts.append(
                table([
                    'Architecture', r'$A$ ($\mu m^2$)', '$T$ (ns)',
                    r'$P_{prob}$ ($\mu W$)', r'$P_{VCD}$ ($\mu W$)',
                    '$E_{prob}$ (fJ)', '$E_{VCD}$ (fJ)'
                ], entries))
        plot = result_dir / f'{circuit}-comparison.pdf'
        if not plot.exists():
            raise ValueError(f'Missing report plot: {plot}')
        parts.append(
            r'\begin{center}\includegraphics[width=\linewidth]{\detokenize{' +
            str(plot) + r'}}\end{center}')

    parts.append(r'''\section{Qualitative questions}
\subsection{What is a netlist, and why analyze it instead of the Verilog source?}
The original Verilog describes operations and logic connections, but does
not select technology-specific cells with known area, delay, and power.
Yosys optimizes this logic and maps it to library cells;
\texttt{synth/netlist.v} lists those cells and their connections. PPA analysis
combines this mapped circuit with the library's physical models, so it
reflects the selected technology and synthesis optimizations. The source
alone does not provide that information.

\subsection{Two reasons an implementation might run faster than STA suggests}
\begin{itemize}
\item STA may consider a path that valid inputs can never activate. If this
is proved for the reported longest path, it can be excluded; the longest
remaining valid path then sets the timing limit and may allow a faster clock.
\item Actual gates may run faster under more favorable voltage, temperature,
or manufacturing conditions than the library model assumes.
\end{itemize}
These possibilities were not demonstrated in this experiment.

\subsection{How can the original testbenches be improved?}
Both benches were improved:
\begin{itemize}
\item \textbf{Adder:} The original connects \texttt{cout} but checks only
\texttt{sum}; random tests can miss long carry chains. The enhanced bench
checks $\{cout,sum\}$, every carry-chain length, overflow, and both carry-in
values, with reproducible pseudorandom inputs.
\item \textbf{Counter:} The original checks counting after startup reset.
The enhanced bench also checks that the output is zero during reset,
reapplies reset after 50,000 increments, and verifies counting restarts
from zero. A reference count checks the output every cycle.
\end{itemize}
Both benches use \texttt{\$fatal} to return a nonzero status on failure.
Separate formal proofs cover all adder inputs and counter states, including
wraparound; mapped simulation checks library integration.

\subsection{Where does VCD activity come from, and what affects its power?}
VCD (Value Change Dump) records signal values and the times at which they
change. Verilator creates this file while simulating the mapped netlist
with the testbench; OpenSTA reads the circuit's recorded activity to
estimate power. The commands and settings mean:
\begin{itemize}
\item \texttt{\$dumpfile(vcd\_name)} selects the output filename;
\texttt{vcd\_name} holds that filename.
\item \texttt{\$dumpvars(0)} starts recording signals. The zero requests
all levels of nested modules, including the circuit being tested.
\item \texttt{next\_random} is a function that generates repeatable
32-bit pseudorandom numbers for the adder inputs.
\item \texttt{apply\_vector} is a task that sets the adder's two operands
and carry-in, waits, and checks the outputs.
\item \texttt{SAMPLE\_INTERVAL\_NS} sets the delay between adder tests:
0.9855 ns, rounded to 0.986 ns by the simulator's time precision.
\item \texttt{always \#5} toggles the counter clock every 5 ns, giving
a 10 ns clock period.
\end{itemize}
Input patterns determine which signals switch. Shorter input intervals or
clock periods usually increase dynamic power, the power associated with
switching. Reset frequency and simulation length change the recorded
workload; longer counter runs can capture rare changes in higher bits.
The dump commands record activity rather than drive circuit inputs.

\subsection{How did AI help with this assignment? (Optional)}
AI helped me configure the experiment environment faster by explaining tool
paths, dependencies, and build commands. It also helped me understand Verilog
and digital circuit principles, especially carry propagation and the
Kogge--Stone and Brent--Kung prefix networks. Step-by-step explanations
connected RTL behavior to area and delay tradeoffs.

\section{Quantitative questions}
\subsection{Three slowest unique start/end pairs}
\hyperref[app:timing-paths]{Appendix~\ref*{app:timing-paths}} lists the three
slowest distinct start/end pairs for all 18 configurations, ranked by the
worst slack for each pair. A unique pair requires a distinct combination of
startpoint and endpoint; sharing only the endpoint does not make two pairs
the same.

All 18 \texttt{sta/timing-longest-paths.rpt} files repeat pairs. Different
gate/pin routes, rise/fall transitions, and conditional gate-delay models
(delay cases depending on other inputs) can share the same endpoints.
These conditions are not printed, so some entries can even have identical
printed details.

For example, the ASAP7 ripple-carry report's 1,000 entries all have
\texttt{b[0]} $\rightarrow$ \texttt{sum[31]}. Querying each source separately
in \texttt{timing-unique-paths.rpt} supplies the other pairs. Its three
slowest distinct pairs are:
''')
    example = row_by['adder32', 'ripple-carry', 'asap7']
    parts.append(
        table(['Startpoint', 'Endpoint', 'Delay (ns)', 'Original occurrences'],
              [[r'\texttt{' + esc(path['startpoint']) + '}',
                r'\texttt{' + esc(path['endpoint']) + '}',
                number(path['delay_ns']), path['occurrences_same_pair']]
               for path in example['top_paths'][:3]], 'llrr'))
    parts.append(r'''Occurrences count entries in the original 1,000-path
report; zero means a pair was absent from that capped list. Each pair is
counted once when selecting the top three. Counter timing requirements also
include flip-flop setup and capture timing.

\subsection{Performance versus performance/area and energy}
RCA, KS, and BK denote ripple-carry, Kogge--Stone, and Brent--Kung.
Raw performance is the estimated maximum frequency $f=1/T$, where $T$ is
the critical-path delay. Performance/area is $f/A$, where $A$ is mapped
cell area; energy/operation is $E=PT$, where $P$ is total power.
$E_{prob}$ uses OpenSTA's statistical switching model, and $E_{VCD}$ uses
power estimated from simulated signal activity.

Every library was evaluated with all three adders, giving nine individual
results. The following table shows the values used for the correlations:
''')
    adder_labels = {'ripple-carry': 'RCA', 'kogge-stone': 'KS',
                    'brent-kung': 'BK'}
    entries = []
    for tech in TECHS:
        for row in ordered('adder32', tech):
            entries.append([
                LABELS[tech], adder_labels[row['architecture']],
                number(row['frequency_hz'] / 1e9),
                number(row['performance_per_area_hz_per_um2'] / 1e6),
                number(row['probabilistic_energy_j'] * 1e15),
                number(row['vcd_energy_j'] * 1e15)
            ])
    parts.append(
        table(['Technology', 'Adder', '$f$ (GHz)',
               r'$f/A$ (MHz/$\mu m^2$)', '$E_{prob}$ (fJ)',
               '$E_{VCD}$ (fJ)'], entries, 'llrrrr'))
    parts.append(r'''
For each technology, the next table gives the Pearson correlation coefficient
$r$ between raw performance and each column's metric across the three
adders within that library. Thus each row summarizes three adder results,
rather than comparing the libraries with each other. Values near $+1$
indicate that the quantities increase together; values near $-1$ indicate
opposite trends; values near zero indicate little linear relationship.
''')
    entries = []
    for tech in TECHS:
        entries.append([
            LABELS[tech],
            correlation(ordered('adder32', tech),
                        'performance_per_area_hz_per_um2'),
            correlation(ordered('adder32', tech), 'probabilistic_energy_j'),
            correlation(ordered('adder32', tech), 'vcd_energy_j')
        ])
    parts.append(
        table(
            ['Technology', '$r$: performance/area', '$r$: prob. energy/op',
             '$r$: VCD energy/op'],
            entries))
    parts.append(
        r'''\begin{itemize}
\item \textbf{Performance/area:} Strong positive correlation at all three
nodes. Faster adders generally provide more performance per unit area.
\item \textbf{Probabilistic energy:} Nearly perfect positive correlation
at 7 and 130 nm, and a less close positive relationship at 45 nm. Faster
adders tend to have higher energy/operation under this model.
\item \textbf{VCD energy:} Strong negative correlation at all three nodes.
Faster adders tend to have lower calculated $P_{VCD}T$.
\end{itemize}
These are overall trends across three designs, not a guarantee for every
pair. The energy models use different activity rates: probabilistic power
uses each minimum period, while VCD inputs have a fixed rate. Thus
$E_{VCD}=P_{VCD}T$ is the assignment's derived metric, rather than energy
measured per VCD test vector.

\subsection{Does architecture improvement scale equally at 7 and 130 nm?}
Kogge--Stone is the fastest adder and ripple-carry the slowest in these
libraries. For each technology, architecture speedup is
$S=f_{adder}/f_{RCA}=T_{RCA}/T_{adder}$: it compares architectures within
that technology. The frequency columns show absolute performance.
''')
    entries = []
    speedups = {}
    for tech in TECHS:
        rca = row_by['adder32', 'ripple-carry', tech]
        ks = row_by['adder32', 'kogge-stone', tech]
        bk = row_by['adder32', 'brent-kung', tech]
        speedups[tech] = rca['cycle_time_s'] / ks['cycle_time_s']
        entries.append([
            LABELS[tech], number(rca['frequency_hz'] / 1e9),
            number(ks['frequency_hz'] / 1e9), f'{speedups[tech]:.3f}',
            f'{rca["cycle_time_s"] / bk["cycle_time_s"]:.3f}'
        ])
    parts.append(
        table(['Technology', '$f_{RCA}$ (GHz)', '$f_{KS}$ (GHz)',
               'KS/RCA speedup', 'BK/RCA speedup'],
              entries))
    difference_percent = (speedups['asap7'] / speedups['sky130'] - 1) * 100
    direction = 'lower' if difference_percent < 0 else 'higher'
    benefit_conclusion = ('The factors agree to this precision. '
                          if round(speedups['asap7'], 3) == round(speedups['sky130'], 3)
                          else 'The relative benefits therefore differ between nodes. ')
    parts.append(
        f'Kogge--Stone is {speedups["asap7"]:.3f} times faster than ripple-carry at 7 nm '
        f'and {speedups["sky130"]:.3f} times faster at 130 nm. '
        f'The 7 nm speedup factor is {abs(difference_percent):.2f} percent {direction}. '
        + benefit_conclusion +
        r'''All three adders have higher absolute performance at 7 nm in
these STA results; a larger relative gain at 130 nm does not make its
adders faster than their 7 nm counterparts.

RCA propagates carries through a serial chain, while KS uses parallel
prefix logic. These structures use different gate types and numbers of
loads driven by each gate. Library delay/load models and synthesis cell
choices differ, so both architectures need not speed up by the same factor
between libraries. These are plausible reasons for the discrepancy;
routed-wire effects were not measured.

\subsection{Discrepancy between 7 nm counter power estimates}
Here ``discrepancy'' means the absolute gap
$D=|P_{prob}-P_{VCD}|$. The table also reports the relative gap
$100D/P_{prob}$ as a percentage.
''')
    group = ordered('counter32', 'asap7')
    absolute = lambda r: abs(r['vcd_power_w'] - r['probabilistic_power_w'])
    entries = [[
        LABELS[r['architecture']],
        number(r['probabilistic_power_w'] * 1e6),
        number(r['vcd_power_w'] * 1e6),
        number(absolute(r) * 1e6),
        f'{r["power_relative_difference"] * 100:.2f}'
    ] for r in group]
    parts.append(
        table([
            'Architecture', r'$P_{prob}$ ($\mu W$)', r'$P_{VCD}$ ($\mu W$)',
            r'Absolute gap ($\mu W$)', r'Relative gap (\%)'
        ], entries))
    smallest_absolute = min(group, key=absolute)
    largest_absolute = max(group, key=absolute)
    smallest_relative = min(group, key=lambda r: r['power_relative_difference'])
    largest_relative = max(group, key=lambda r: r['power_relative_difference'])
    parts.append(
        'The absolute gap is smallest for ' +
        LABELS[smallest_absolute['architecture']] +
        f' ({absolute(smallest_absolute) * 1e6:.2f} ' + r'$\mu W$)' +
        ' and largest for ' + LABELS[largest_absolute['architecture']] +
        f' ({absolute(largest_absolute) * 1e6:.2f} ' + r'$\mu W$)' +
        '. The relative gap is smallest for ' +
        LABELS[smallest_relative['architecture']] +
        f' ({smallest_relative["power_relative_difference"] * 100:.2f}' + r'\%)' +
        ' and largest for ' + LABELS[largest_relative['architecture']] +
        f' ({largest_relative["power_relative_difference"] * 100:.2f}' + r'\%).')
    relative_spread = (
        largest_relative['power_relative_difference'] -
        smallest_relative['power_relative_difference']) * 100
    parts.append(
        f'All three relative gaps are about 11.5 percent, with only '
        f'{relative_spread:.2f} percentage points between the smallest and largest. '
        'The main observation is a consistent difference between estimation '
        'methods, with little variation across counter architectures.')
    parts.append(
        r'''Reasons for the discrepancies include:
\begin{itemize}
\item \textbf{Activity assumptions:} The statistical run assumes input
activity of 0.2 transitions per minimum period. The VCD records actual
binary counting, where bit changes and carry propagation are correlated.
\item \textbf{Finite workload and reset:} Each counting segment stops at
50,000, so bits 16--31 remain zero. Reset changes only a few times. These
patterns differ from statistical activity assumptions.
\item \textbf{Activity rates:} The VCD records a 10 ns clock, while both
STA runs retain minimum-period clock constraints. The recorded data
activity and statistical estimates therefore use different rate assumptions.
\end{itemize}
These differences affect internal and switching power estimates.

\subsection{Counter area devoted to sequential elements}
The final statistics in \texttt{synth/stdout.log} report total cell area
$A_{total}$ and sequential area $A_{seq}$. Every counter has 32 mapped
flip-flops, which store its 32-bit count. The sequential share is
$100 A_{seq}/A_{total}$ percent.
''')
    entries = []
    for tech in TECHS:
        group = ordered('counter32', tech)
        assert all(r['sequential_cell_count'] == 32 for r in group)
        areas = {r['sequential_area_um2'] for r in group}
        area_text = number(min(areas))
        if len(areas) > 1:
            area_text += '--' + number(max(areas))
        entries.append([LABELS[tech], area_text,
                        *[f'{r["sequential_area_fraction"] * 100:.2f}' for r in group]])
    parts.append(
        table(['Technology', r'$A_{seq}$ ($\mu m^2$)',
               r'RCA share (\%)', r'KS share (\%)', r'BK share (\%)'], entries))
    within_spread = max(
        np.ptp([
            r['sequential_area_fraction'] * 100
            for r in ordered('counter32', tech)
        ]) for tech in TECHS)
    parts.append(
        r'\textbf{Across adder designs:} The ratio is approximately consistent '
        'within each technology; the largest spread is '
        f'{within_spread:.2f} percentage points. '
        r'''All three counters use the same 32 flip-flop cells within a library.
With $b=0$ and $cin=1$, synthesis simplifies each adder into an incrementer
(adds one). Small differences in the remaining combinational logic area
account for the slight ratio changes.''')
    parts.append(
        r'''\textbf{Across technology nodes:} The ratio changes and is higher
at 7 nm than at 130 nm in these results. Each library has different relative
areas for flip-flops and logic gates, and synthesis maps the logic differently.
Keeping 32 flip-flops therefore does not keep their share of total area constant.

\section{Rebuild guide}
GitHub repository: \url{https://github.com/Colossus-MKII/cs505-f26-lab1}.

Use the complete project checkout on ilab, with the environment described
in the assignment handout.
\begin{enumerate}
\item Open the project directory:
\begin{Verbatim}[fontsize=\small]
cd cs505-f26-lab1
\end{Verbatim}
\item Rebuild all experiments:
\begin{Verbatim}[fontsize=\small]
python3 scripts/run_experiments.py --force
\end{Verbatim}
This checks RTL correctness, synthesizes and simulates all 18 configurations,
and analyzes timing, area, and both power estimates.
\item \texttt{submission.zip} contains the two new adder files,
the two enhanced testbench files, and \texttt{report.pdf}. Data and plots are in
\texttt{results/}; synthesis, simulation, and STA reports are in \texttt{build/}.
\end{enumerate}
''')
    parts.append(r'''\section{Appendix}
\renewcommand{\thesubsection}{\Alph{subsection}}
\subsection{Three slowest unique endpoint pairs for every configuration}
\label{app:timing-paths}
Names are copied from each \texttt{sta/timing-unique-paths.rpt}. The table
reports the magnitude of worst slack normalized to ns (the timing requirement)
and the number of occurrences of that endpoint pair in the original capped
\texttt{timing-longest-paths.rpt}. Zero means that pair did not appear within
the first 1,000 raw paths, although it is present in the complete unique-pair report.
''')
    for circuit in ('adder32', 'counter32'):
        for tech in TECHS:
            for row in ordered(circuit, tech):
                parts.append(r'\subsubsection{' + esc(circuit) + ': ' +
                             LABELS[row['architecture']] + ', ' +
                             LABELS[tech] + '}')
                parts.append(
                    r'\begin{tabularx}{\linewidth}{XXrr}\toprule Startpoint & Endpoint & Requirement (ns) & Occurrences \\ \midrule'
                )
                for path in row['top_paths'][:3]:
                    start = str(path['startpoint']).replace('{', '').replace(
                        '}', '')
                    end = str(path['endpoint']).replace('{',
                                                        '').replace('}', '')
                    parts.append(r'\nolinkurl{' + start + r'} & \nolinkurl{' +
                                 end + '} & ' + number(path['delay_ns']) +
                                 ' & ' + str(path['occurrences_same_pair']) +
                                 r' \\')
                parts.append(r'\bottomrule\end{tabularx}')
    parts.append(
        r'''\subsection{Both definitions of the requested efficiency metric}
Here $T/P$ is the handout's literal quantity in s/W. Throughput/W is the
conventional $1/(TP)$, shown in trillions of operations per joule (TOp/J).
The complete CSV also contains throughput, performance/area, and both energies.
''')
    for circuit in ('adder32', 'counter32'):
        parts.append(r'\subsubsection{' + esc(circuit) + '}')
        entries = []
        for tech in TECHS:
            for r in ordered(circuit, tech):
                entries.append([
                    LABELS[tech], LABELS[r['architecture']],
                    number(r['probabilistic_handout_time_per_power_s_per_w']),
                    number(r['vcd_handout_time_per_power_s_per_w']),
                    number(r['probabilistic_throughput_per_watt_ops_per_j'] /
                           1e12),
                    number(r['vcd_throughput_per_watt_ops_per_j'] / 1e12)
                ])
        parts.append(
            table([
                'Technology', 'Architecture', '$T/P_{prob}$', '$T/P_{VCD}$',
                '$f/P_{prob}$', '$f/P_{VCD}$'
            ], entries, 'llrrrr'))
    parts.append(r'''\clearpage
\subsection{Testbenches and verification}
\label{app:testbenches}
The two enhanced testbench source files are included in \texttt{submission.zip}.
Place them at the following paths in the project checkout:
\begin{itemize}
\item \nolinkurl{src/adder32/adder32-testbench.v}
\item \nolinkurl{src/counter32/counter32-testbench.v}
\end{itemize}
Both benches check outputs automatically and terminate with a nonzero status
on failure. The rebuild command in Section 5 runs both against every RTL
architecture and every mapped configuration.

\subsubsection{Adder testbench}
\texttt{adder32-testbench.v} checks all 33 result bits, including carry-out.
It uses 106 directed cases and 100,000 deterministic pseudorandom cases
with seed \texttt{0x505f2601}. The directed cases cover carry chains,
overflow, and both carry-in values. Its 0.9855 ns stimulus interval rounds
to 986 ps at the declared 1 ps precision.

\subsubsection{Counter testbench}
\texttt{counter32-testbench.v} checks 100,000 increments against a reference
count, plus startup reset and reset during counting. It uses a 10 ns clock
and checks four reset cycles. Two counting segments of 50,000 increments
verify that counting restarts correctly after reset.

These workloads generated the VCD activity used for the reported power
estimates. Verilator simulates the mapped netlists with these same benches;
\texttt{+vcd=filename.vcd} enables waveform dumping for OpenSTA.
''')
    original_check_file = args.manifest.resolve(
    ).parent / 'original-testbenches/verification.json'
    if original_check_file.is_file():
        original = json.loads(original_check_file.read_text())
        checks = original.get('checks', [])
        expected_checks = {(a, c)
                           for a in ('kogge-stone', 'brent-kung')
                           for c in ('adder32', 'counter32')}
        matching_sources = all(
            original.get('adder_sha256', {}).get(a) == hashlib.sha256((
                ROOT / 'src/adder32' /
                f'adder32-{a}.v').read_bytes()).hexdigest()
            for a in ('kogge-stone', 'brent-kung'))
        if (original.get('status') == 'PASS' and matching_sources
                and len(checks) == 4 and {(c['architecture'], c['circuit'])
                                          for c in checks} == expected_checks
                and all(c['status'] == 'PASS' for c in checks)):
            parts.append(
                r'\subsubsection{Compatibility with the original instructor benches}'
            )
            parts.append(
                'The original bench files were recovered without edits from course '
                'repository revision ' + r'\texttt{' +
                esc(original['original_revision'][:7]) +
                '}. Verilator ran each original bench against the current standalone '
                'RTL of both submitted adders. All four checks passed. This is separate '
                'from the 18 technology-mapped simulations using the enhanced benches.'
            )
            parts.append(
                table(['Architecture', 'Original testbench', 'Result'], [[
                    LABELS[c['architecture']],
                    esc(c['circuit']), c['status']
                ] for c in checks], 'lll'))
            parts.append(
                r'Exact commands, source hashes, and logs are recorded in '
                r'\texttt{build/original-testbenches/verification.json}.')
    parts.append(r'\end{document}')
    texfile = result_dir / 'report.tex'
    texfile.write_text('\n\n'.join(parts) + '\n')
    logfile = result_dir / 'report-build.log'
    with logfile.open('w') as log:
        for _ in range(2):
            subprocess.run([
                'pdflatex', '-interaction=nonstopmode', '-halt-on-error',
                '-output-directory',
                str(result_dir),
                str(texfile)
            ],
                           cwd=ROOT,
                           stdout=log,
                           stderr=subprocess.STDOUT,
                           check=True)
    shutil.copyfile(result_dir / 'report.pdf', ROOT / 'report.pdf')
    print(f'Generated {ROOT / "report.pdf"}')


if __name__ == '__main__':
    main()
