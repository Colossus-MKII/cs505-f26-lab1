create_clock -name virt_clk -period ${CLOCK_NS}

set_input_delay 0.0 -clock virt_clk [get_ports a]
set_input_delay 0.0 -clock virt_clk [get_ports b]
set_input_delay 0.0 -clock virt_clk [get_ports cin]

set_output_delay 0.0 -clock virt_clk [get_ports sum]
set_output_delay 0.0 -clock virt_clk [get_ports cout]