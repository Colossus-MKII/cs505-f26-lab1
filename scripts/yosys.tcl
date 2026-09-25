set required_vars { SYNTH_OUTDIR SYNTH_TECHLIB_FILE SYNTH_SOURCE_FILES SYNTH_TOP_NAME SYNTH_NETLIST_FILE SYNTH_FLATTEN_EARLY }
foreach var $required_vars {
    if {![info exists ::env($var)]} {
        puts "Error: Environment variable '$var' is not set."
        exit 1
    }
}

set OUTDIR        $::env(SYNTH_OUTDIR)
set LIB_FILE      $::env(SYNTH_TECHLIB_FILE)
set SOURCE_FILES  $::env(SYNTH_SOURCE_FILES)
set TOP_NAME      $::env(SYNTH_TOP_NAME)
set NETLIST_FILE  $::env(SYNTH_NETLIST_FILE)
set FLATTEN_EARLY $::env(SYNTH_FLATTEN_EARLY)

###############################################################################
#                           Synthesis Script                                  #
###############################################################################
foreach filename $SOURCE_FILES {
    yosys read -sv $filename
}
yosys hierarchy -check -top $TOP_NAME
yosys stat
# yosys show -prefix ${OUTDIR}/diagram-0-post-proc -format png ${TOP_NAME}
yosys proc
yosys clean

yosys read_liberty -lib $LIB_FILE


# flatten out the design
if { $FLATTEN_EARLY ne "" } {
    yosys flatten
    yosys autoname
    yosys opt -full
    yosys clean
    yosys stat
}

# coarse-grained optimization
yosys memory; yosys opt
yosys fsm; yosys opt
yosys share
yosys wreduce
yosys peepopt
yosys opt
yosys opt_clean
yosys stat
# yosys show -prefix ${OUTDIR}/diagram-1-post-coarse -format png ${TOP_NAME}

# map to internal yosys logic gates
yosys techmap
yosys opt
yosys autoname
yosys clean
yosys stat
# yosys show -prefix ${OUTDIR}/diagram-2-post-techmap -format png ${TOP_NAME}

# map to an actual hardware
yosys dfflibmap -liberty $LIB_FILE
yosys abc -liberty $LIB_FILE
yosys autoname
yosys clean
yosys stat

# flatten post-ABC
if { $FLATTEN_EARLY eq "" } {
    yosys flatten
    yosys autoname
    yosys opt -full
    yosys clean
    yosys stat
}

# show output
yosys stat
yosys stat -tech cmos
yosys stat -liberty $LIB_FILE
yosys write_verilog $NETLIST_FILE