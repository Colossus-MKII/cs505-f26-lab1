# set 10 ns clock
create_clock -name clk -period ${CLOCK_NS} {clock_i}
set_input_delay -clock clk 0 {reset_ni}

set_output_delay 0.0 -clock clk [get_ports count_o]
