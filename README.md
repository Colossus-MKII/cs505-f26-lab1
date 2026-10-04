# CS 505 Lab 1: Adder Design Space Exploration

This project compares 32-bit ripple-carry, Kogge–Stone, and Brent–Kung
adders, both standalone and inside a counter. It evaluates correctness,
power, performance, and area using ASAP7 (7 nm), Nangate45 (45 nm), and
Sky130HD (130 nm), for 18 configurations in total.

## Rebuild

Use the complete project checkout in the configured course ilab environment.
Python with NumPy/Matplotlib, Icarus Verilog, and pdfLaTeX must also be available.

1. Open the project directory:

   ```bash
   cd cs505-f26-lab1
   ```

2. Run the full rebuild:

   ```bash
   python3 scripts/run_experiments.py --force
   ```

The command runs verification, synthesis, simulation, and PPA analysis.
Logs and reports are saved in `build/`; numerical results and plots are in
`results/`. The project root contains `report.pdf` and `submission.zip`,
which includes both new adders, both testbenches, and the report.
