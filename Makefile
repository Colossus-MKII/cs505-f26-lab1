BASE_OUTDIR  := build

###############################################################################
# TOOLS: YOSYS
###############################################################################
YOSYS        := /common/users/shared/fluxlab-tools/yosys-0.69/bin/yosys
YOSYS_SCRIPT := scripts/yosys.tcl

###############################################################################
# TOOLS: OpenSTA
###############################################################################
OPENSTA          := /common/users/shared/fluxlab-tools/opensta-2.2.0/bin/sta
OPENSTA_SCRIPT   := scripts/opensta.tcl

###############################################################################
# TOOLS: Verilator
###############################################################################
# Testbench using the gate-level design
VERILATOR       := /common/users/shared/fluxlab-tools/verilator-5.052/bin/verilator
VERILATOR_BIN   := V$(TESTBENCH_TOP_NAME)
VERILATOR_FLAGS := -Wall -Wno-DECLFILENAME --trace --trace-underscore
SKYHD130_DEFS   := -DFUNCTIONAL -DUNIT_DELAY
VERILATOR_DEFS  := $(SKYHD130_DEFS)

###############################################################################
# BASIC RECIPES
###############################################################################
.SUFFIXES:

.SECONDARY:

default:
	python3 build.py build

$(BASE_OUTDIR)/%/synth:
	mkdir -p $@

$(BASE_OUTDIR)/%/sta:
	mkdir -p $@

$(BASE_OUTDIR)/%/sim:
	mkdir -p $@

.PHONY: clean
clean:
	rm -rf $(BASE_OUTDIR)

.PHONY: FORCEBUILD
$(BASE_OUTDIR)/%: FORCEBUILD $(BASE_OUTDIR)/%/.stamp
	@:
	
$(BASE_OUTDIR)/%/.stamp: $(BASE_OUTDIR)/%/sta/power.rpt $(BASE_OUTDIR)/%/sim/$(TESTBENCH_TOP_NAME).vcd
	touch $@

###############################################################################
# OpenSTA (timing and power)
###############################################################################
# Run 1: Timing-only
$(BASE_OUTDIR)/%/sta/timing.rpt: $(BASE_OUTDIR)/%/synth/netlist.v | $(BASE_OUTDIR)/%/sta
	$(info [MAKE] Calculating Timing)
	export STA_OUTDIR=$(BASE_OUTDIR)/$*/sta; \
	export STA_TECHLIB_FILE=$(TECHLIB_LIB_FILENAME); \
	export STA_SOURCE_FILES=$<; \
	export STA_TOP_NAME=$(MODULE_TOP_NAME); \
	export STA_SDC_FILE=$(MODULE_SDC_FILENAME); \
	export STA_CLOCK_NS=0.0; \
	export STA_REPORT_POWER=0; \
	export STA_VCD_FILENAME="none"; \
	export STA_TB_DUT_NAME="none"; \
	$(OPENSTA) -no_splash -exit $(OPENSTA_SCRIPT) 2>&1 | tee $(BASE_OUTDIR)/$*/sta/stdout-timing.log

# Run 2: Power-only
$(BASE_OUTDIR)/%/sta/power.rpt: $(BASE_OUTDIR)/%/synth/netlist.v $(BASE_OUTDIR)/%/sta/timing.rpt | $(BASE_OUTDIR)/%/sta
	$(info [MAKE] Calculating Switching Power)
	export STA_OUTDIR=$(BASE_OUTDIR)/$*/sta; \
	export STA_TECHLIB_FILE=$(TECHLIB_LIB_FILENAME); \
	export STA_SOURCE_FILES=$<; \
	export STA_TOP_NAME=$(MODULE_TOP_NAME); \
	export STA_SDC_FILE=$(MODULE_SDC_FILENAME); \
	export STA_CLOCK_NS=$(shell cat $(BASE_OUTDIR)/$*/sta/timing-min-clock.rpt); \
	export STA_REPORT_POWER=1; \
	export STA_VCD_FILENAME="none"; \
	export STA_TB_DUT_NAME="none"; \
	$(OPENSTA) -no_splash -exit $(OPENSTA_SCRIPT) 2>&1 | tee $(BASE_OUTDIR)/$*/sta/stdout-power-switching.log

# Run 3: VCD power
$(BASE_OUTDIR)/%/sim/$(TESTBENCH_TOP_NAME).vcd: $(BASE_OUTDIR)/%/sim/$(VERILATOR_BIN)
	$(BASE_OUTDIR)/$*/sim/$(VERILATOR_BIN) +vcd=$@ 2>&1 | tee $(BASE_OUTDIR)/$*/sim/run-stdout.log

	$(info [MAKE] Calculating VCD Power)
	export STA_OUTDIR=$(BASE_OUTDIR)/$*/sta; \
	export STA_TECHLIB_FILE=$(TECHLIB_LIB_FILENAME); \
	export STA_SOURCE_FILES=$(BASE_OUTDIR)/$*/synth/netlist.v; \
	export STA_TOP_NAME=$(MODULE_TOP_NAME); \
	export STA_SDC_FILE=$(MODULE_SDC_FILENAME); \
	export STA_CLOCK_NS=$(shell cat $(BASE_OUTDIR)/$*/sta/timing-min-clock.rpt); \
	export STA_REPORT_POWER=2; \
	export STA_VCD_FILENAME=$@; \
	export STA_TB_DUT_NAME=$(TESTBENCH_TOP_NAME); \
	$(OPENSTA) -no_splash -exit $(OPENSTA_SCRIPT) 2>&1 | tee $(BASE_OUTDIR)/$*/sta/stdout-power-vcd.log

###############################################################################
# Yosys (netlist synthesis)
###############################################################################
$(BASE_OUTDIR)/%/synth/netlist.v: $(MODULE_SOURCES) | $(BASE_OUTDIR)/%/synth
	$(info [MAKE] Synthesizing Netlist)
	export SYNTH_OUTDIR=$(BASE_OUTDIR)/$*/synth; \
	export SYNTH_TECHLIB_FILE=$(TECHLIB_LIB_FILENAME); \
	export SYNTH_SOURCE_FILES="$^"; \
	export SYNTH_TOP_NAME=$(MODULE_TOP_NAME); \
	export SYNTH_NETLIST_FILE=$@; \
	export SYNTH_FLATTEN_EARLY=1; \
	$(YOSYS) -t -l $(BASE_OUTDIR)/$*/synth/stdout.log -c $(YOSYS_SCRIPT)

###############################################################################
# Verilator (to generate VCDs)
###############################################################################
$(BASE_OUTDIR)/%/sim/$(VERILATOR_BIN): $(BASE_OUTDIR)/%/synth/netlist.v $(TESTBENCH_SOURCES) $(TECHLIB_SIM_FILENAMES) scripts/verilator.vlt | $(BASE_OUTDIR)/%/sim
	$(info [MAKE] Simulating verilog)
	$(VERILATOR) -j 10 -Wno-fatal --cc --binary -exe --build --Mdir $(BASE_OUTDIR)/$*/sim \
		$(VERILATOR_FLAGS) $(VERILATOR_DEFS) $^ --top-module $(TESTBENCH_TOP_NAME) 2>&1 | tee $(BASE_OUTDIR)/$*/sim/compile-stdout.log
