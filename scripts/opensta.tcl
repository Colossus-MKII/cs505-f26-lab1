set required_vars {STA_OUTDIR STA_SOURCE_FILES STA_TOP_NAME STA_TECHLIB_FILE STA_SDC_FILE STA_CLOCK_NS STA_REPORT_POWER STA_VCD_FILENAME STA_TB_DUT_NAME}
foreach var $required_vars {
    if {![info exists ::env($var)]} {
        puts "Error: Environment variable '$var' is not set."
        exit 1
    }
}

set VERILOG_SRCS  $::env(STA_SOURCE_FILES)
set TOP_NAME      $::env(STA_TOP_NAME)
set LIB_FILE      $::env(STA_TECHLIB_FILE)
set OUTDIR        $::env(STA_OUTDIR)
set SDC_FILE      $::env(STA_SDC_FILE)
set CLOCK_NS      $::env(STA_CLOCK_NS)
set REPORT_POWER  $::env(STA_REPORT_POWER)
set VCD_FILENAME  $::env(STA_VCD_FILENAME)
set TB_DUT_NAME   $::env(STA_TB_DUT_NAME)

###############################################################################
#                           OpenSTA Script                                    #
###############################################################################
try {
read_liberty ${LIB_FILE}
foreach file ${VERILOG_SRCS} {
    read_verilog $file
}
link_design ${TOP_NAME}

# SDC constraints
read_sdc ${SDC_FILE}

# reports for power and timing
if {${REPORT_POWER} == 1} {
    set_power_activity -input -activity 0.2
    report_power -digits 6 > ${OUTDIR}/power-switching.rpt
} elseif {${REPORT_POWER} == 2} {
    read_vcd -scope ${TB_DUT_NAME}/dut ${VCD_FILENAME}
    with_output_to_variable vcd_annotation {
        report_activity_annotation
    }
    puts $vcd_annotation
    if {![regexp {vcd\s+([0-9]+)} $vcd_annotation -> annotated_pins] || $annotated_pins == 0} {
        error "VCD did not annotate any DUT pin activities: ${TB_DUT_NAME}/dut"
    }
    report_power -digits 6 > ${OUTDIR}/power-vcd.rpt
} else {
    report_checks -digits 8 -endpoint_path_count 1000 -group_path_count 1000 > ${OUTDIR}/timing-longest-paths.rpt

    # The original report can fill with many routes for one start/end pair.
    # Enumerate each source separately to retain the worst path for every pair.
    close [open "${OUTDIR}/timing-unique-paths.rpt" w]
    foreach startpoint [concat [all_inputs -no_clocks] [all_registers -output_pins]] {
        report_checks -from $startpoint -digits 8 -endpoint_path_count 1 -group_path_count 1000 -no_line_splits >> ${OUTDIR}/timing-unique-paths.rpt
    }

    with_output_to_variable max_slack_string {report_worst_slack -digits 8 -max}
    if {![regexp {worst slack(?:\s+(?:max|min))?\s+([-+0-9.eE]+)} $max_slack_string -> max_slack] || ![string is double -strict $max_slack]} {
        error "Cannot parse worst slack: $max_slack_string"
    }
    set minimum_period [expr {-double($max_slack)}]
    if {$minimum_period <= 0.0} {
        error "Expected a positive critical delay at clock period zero: $max_slack_string"
    }
    
    set file_id [open "${OUTDIR}/timing-min-clock.rpt" w]
    puts -nonewline $file_id $minimum_period
    close $file_id
    
    with_output_to_variable units {report_units}
    set file_id [open "${OUTDIR}/units.log" w]
    puts -nonewline $file_id $units
    close $file_id
}
} on error {message options} {
    puts stderr "OpenSTA analysis failed: $message"
    exit 1
}
