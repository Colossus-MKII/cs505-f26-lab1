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
    read_vcd -scope adder32_testbench/dut ${VCD_FILENAME}
    report_power -digits 6 > ${OUTDIR}/power-vcd.rpt
} else {
    report_checks -digits 8 -endpoint_path_count 1000 -group_path_count 1000 > ${OUTDIR}/timing-longest-paths.rpt

    with_output_to_variable max_slack_string {report_worst_slack -digits 8 -max}
    set max_slack [string map {"-" ""} [lindex [split $max_slack_string " "] 3]]
    
    set file_id [open "${OUTDIR}/timing-min-clock.rpt" w]
    puts -nonewline $file_id $max_slack
    close $file_id
    
    with_output_to_variable units {report_units}
    set file_id [open "${OUTDIR}/units.log" w]
    puts -nonewline $file_id $units
    close $file_id
}