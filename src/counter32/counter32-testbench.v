`define assert(signal, value) \
    if (signal !== value) begin \
        $display("[FAIL] %m @ %t: %b != %b", $time, signal, value); \
        $finish; \
    end

`timescale 1ns/1ps
module counter32_testbench ();
    reg          tb_clock;
    reg          tb_reset_n;
    
    wire [31:0]  tb_counter;
    
    always #5 tb_clock = ~tb_clock;

    integer i;

    reg [32*255:0] vcd_name;

    initial 
    begin
        if ($test$plusargs("vcd"))
        begin
            if ($value$plusargs("vcd=%s", vcd_name)) 
            begin
                $display("Dumping VCD: %0s", vcd_name);
                $dumpfile(vcd_name);
                $dumpvars(0);
            end
        end

        tb_clock   = 0;
        tb_reset_n = 0;
        i = 0;

        #15; // align with posedge
        #2.5 // deassert reset between clock edges
        tb_reset_n = 1;    
    end

    // check values at negedge
    always @(negedge tb_clock)
    begin
        if(tb_reset_n)
        begin
            i <= i + 1;
            `assert(tb_counter, i); 
            
            if(i >= 100000)
            begin
                $display("[PASS]");
                $finish;    
            end
        end
    end

    counter32 dut (
        .clock_i(tb_clock),
        .reset_ni(tb_reset_n),
        
        .count_o(tb_counter)
    );

endmodule
