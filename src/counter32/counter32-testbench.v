`timescale 1ns/1ps
module counter32_testbench ();
    reg tb_clock = 0;
    reg tb_reset_n = 0;
    wire [31:0] tb_counter;
    reg [31:0] expected_count = 0;
    reg last_edge_was_reset = 1;
    integer increments_checked = 0;
    integer reset_cycles_checked = 0;
    reg [32*255:0] vcd_name;

    // The supplied counter workload uses a fixed 10 ns period.
    always #5 tb_clock = ~tb_clock;

    // Reset is synchronous; compare after the register's nonblocking update.
    always @(posedge tb_clock) begin
        last_edge_was_reset = !tb_reset_n;
        if (!tb_reset_n)
            expected_count = 32'b0;
        else
            expected_count = expected_count + 32'd1;
    end

    always @(negedge tb_clock) begin
        if (tb_counter !== expected_count)
            $fatal(1, "[FAIL] %m @ %t expected %h got %h",
                   $time, expected_count, tb_counter);
        if (!last_edge_was_reset)
            increments_checked = increments_checked + 1;
        else
            reset_cycles_checked = reset_cycles_checked + 1;
    end

    initial begin
        if ($value$plusargs("vcd=%s", vcd_name)) begin
            $display("Dumping VCD: %0s", vcd_name);
            $dumpfile(vcd_name);
            $dumpvars(0);
        end
        // Change reset halfway between edges to avoid stimulus/check races.
        #17.5;
        tb_reset_n = 1;
        wait (increments_checked == 50000);
        #2.5;
        tb_reset_n = 0;
        #20;
        tb_reset_n = 1;
        wait (increments_checked == 100000);
        #1;
        if (reset_cycles_checked < 3)
            $fatal(1, "[FAIL] reset workload did not execute");
        $display("[PASS] %0d increments and %0d reset samples checked",
                 increments_checked, reset_cycles_checked);
        $finish;
    end

    counter32 dut (
        .clock_i(tb_clock), .reset_ni(tb_reset_n), .count_o(tb_counter)
    );
endmodule
