BASE_OUTDIR  ?= build
TARGET_DIR   ?= $(BASE_OUTDIR)/$(MODULE_TOP_NAME)
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DELETE_ON_ERROR:

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
VERILATOR_JOBS  ?= 4
SKYHD130_DEFS   := -DFUNCTIONAL -DUNIT_DELAY
VERILATOR_DEFS  := $(SKYHD130_DEFS)

###############################################################################
# BASIC RECIPES
###############################################################################
.SUFFIXES:


default:
	python3 build.py $(BASE_OUTDIR)

$(TARGET_DIR)/synth:
	mkdir -p $@

$(TARGET_DIR)/sta:
	mkdir -p $@

$(TARGET_DIR)/sim:
	mkdir -p $@

.PHONY: clean
clean:
	rm -rf $(BASE_OUTDIR)

$(TARGET_DIR): $(TARGET_DIR)/.stamp
	@:
	
$(TARGET_DIR)/.stamp: $(TARGET_DIR)/sta/power-switching.rpt $(TARGET_DIR)/sta/power-vcd.rpt $(TARGET_DIR)/sta/timing-longest-paths.rpt $(TARGET_DIR)/sta/timing-unique-paths.rpt $(TARGET_DIR)/sta/units.log
	touch $@

###############################################################################
# OpenSTA (timing and power)
###############################################################################
# Run 1: Timing-only
$(TARGET_DIR)/sta/timing-min-clock.rpt $(TARGET_DIR)/sta/timing-longest-paths.rpt $(TARGET_DIR)/sta/timing-unique-paths.rpt $(TARGET_DIR)/sta/units.log &: $(TARGET_DIR)/synth/netlist.v $(MODULE_SDC_FILENAME) $(OPENSTA_SCRIPT) | $(TARGET_DIR)/sta
	$(info [MAKE] Calculating Timing)
	export STA_OUTDIR=$(TARGET_DIR)/sta; \
	export STA_TECHLIB_FILE=$(TECHLIB_LIB_FILENAME); \
	export STA_SOURCE_FILES=$<; \
	export STA_TOP_NAME=$(MODULE_TOP_NAME); \
	export STA_SDC_FILE=$(MODULE_SDC_FILENAME); \
	export STA_CLOCK_NS=0.0; \
	export STA_REPORT_POWER=0; \
	export STA_VCD_FILENAME="none"; \
	export STA_TB_DUT_NAME="none"; \
	$(OPENSTA) -no_splash -exit $(OPENSTA_SCRIPT) 2>&1 | tee $(TARGET_DIR)/sta/stdout-timing.log

# Run 2: Power-only
$(TARGET_DIR)/sta/power-switching.rpt: $(TARGET_DIR)/synth/netlist.v $(TARGET_DIR)/sta/timing-min-clock.rpt $(MODULE_SDC_FILENAME) $(OPENSTA_SCRIPT) | $(TARGET_DIR)/sta
	$(info [MAKE] Calculating Switching Power)
	export STA_OUTDIR=$(TARGET_DIR)/sta; \
	export STA_TECHLIB_FILE=$(TECHLIB_LIB_FILENAME); \
	export STA_SOURCE_FILES=$<; \
	export STA_TOP_NAME=$(MODULE_TOP_NAME); \
	export STA_SDC_FILE=$(MODULE_SDC_FILENAME); \
	export STA_CLOCK_NS=$(shell cat $(TARGET_DIR)/sta/timing-min-clock.rpt); \
	export STA_REPORT_POWER=1; \
	export STA_VCD_FILENAME="none"; \
	export STA_TB_DUT_NAME="none"; \
	$(OPENSTA) -no_splash -exit $(OPENSTA_SCRIPT) 2>&1 | tee $(TARGET_DIR)/sta/stdout-power-switching.log

# Generate deterministic gate-level switching traces.
$(TARGET_DIR)/sim/$(TESTBENCH_TOP_NAME).vcd: $(TARGET_DIR)/sim/$(VERILATOR_BIN)
	$(TARGET_DIR)/sim/$(VERILATOR_BIN) +vcd=$@ 2>&1 | tee $(TARGET_DIR)/sim/run-stdout.log
	test -s $@
	rg -q '\[PASS\]' $(TARGET_DIR)/sim/run-stdout.log

# Run 3: VCD power
$(TARGET_DIR)/sta/power-vcd.rpt: $(TARGET_DIR)/synth/netlist.v $(TARGET_DIR)/sta/timing-min-clock.rpt $(TARGET_DIR)/sim/$(TESTBENCH_TOP_NAME).vcd $(MODULE_SDC_FILENAME) $(OPENSTA_SCRIPT) | $(TARGET_DIR)/sta
	$(info [MAKE] Calculating VCD Power)
	export STA_OUTDIR=$(TARGET_DIR)/sta; \
	export STA_TECHLIB_FILE=$(TECHLIB_LIB_FILENAME); \
	export STA_SOURCE_FILES=$(TARGET_DIR)/synth/netlist.v; \
	export STA_TOP_NAME=$(MODULE_TOP_NAME); \
	export STA_SDC_FILE=$(MODULE_SDC_FILENAME); \
	export STA_CLOCK_NS=$(shell cat $(TARGET_DIR)/sta/timing-min-clock.rpt); \
	export STA_REPORT_POWER=2; \
	export STA_VCD_FILENAME=$(TARGET_DIR)/sim/$(TESTBENCH_TOP_NAME).vcd; \
	export STA_TB_DUT_NAME=$(TESTBENCH_TOP_NAME); \
	$(OPENSTA) -no_splash -exit $(OPENSTA_SCRIPT) 2>&1 | tee $(TARGET_DIR)/sta/stdout-power-vcd.log

###############################################################################
# Yosys (netlist synthesis)
###############################################################################
$(TARGET_DIR)/synth/netlist.v: $(MODULE_SOURCES) $(TECHLIB_LIB_FILENAME) $(YOSYS_SCRIPT) $(CONFIG_FILENAME) Makefile | $(TARGET_DIR)/synth
	$(info [MAKE] Synthesizing Netlist)
	export SYNTH_OUTDIR=$(TARGET_DIR)/synth; \
	export SYNTH_TECHLIB_FILE=$(TECHLIB_LIB_FILENAME); \
	export SYNTH_SOURCE_FILES="$(MODULE_SOURCES)"; \
	export SYNTH_TOP_NAME=$(MODULE_TOP_NAME); \
	export SYNTH_NETLIST_FILE=$@; \
	export SYNTH_FLATTEN_EARLY=1; \
	$(YOSYS) -t -l $(TARGET_DIR)/synth/stdout.log -c $(YOSYS_SCRIPT)

###############################################################################
# Verilator (to generate VCDs)
###############################################################################
$(TARGET_DIR)/sim/$(VERILATOR_BIN): $(TARGET_DIR)/synth/netlist.v $(TESTBENCH_SOURCES) $(TECHLIB_SIM_FILENAMES) scripts/verilator.vlt Makefile | $(TARGET_DIR)/sim
	$(info [MAKE] Simulating verilog)
	$(VERILATOR) -j $(VERILATOR_JOBS) -Wno-fatal --cc --binary -exe --build --Mdir $(TARGET_DIR)/sim \
		$(VERILATOR_FLAGS) $(VERILATOR_DEFS) $(TARGET_DIR)/synth/netlist.v $(TESTBENCH_SOURCES) $(TECHLIB_SIM_FILENAMES) scripts/verilator.vlt --top-module $(TESTBENCH_TOP_NAME) 2>&1 | tee $(TARGET_DIR)/sim/compile-stdout.log
