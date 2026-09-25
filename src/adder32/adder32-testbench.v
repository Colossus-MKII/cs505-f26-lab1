module adder32_testbench ();
    reg  [31:0] tb_a;
    reg  [31:0] tb_b;
    reg         tb_cin;
    reg  [32:0] expected_result;
    wire [31:0] tb_sum;
    
    
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

        for(i = 0; i < 100000; i = i + 1) 
        begin
            tb_a   = $urandom();
            tb_b   = $urandom();
            tb_cin = $urandom_range(0, 1)[0];
            #0.9855; 
            check_outputs();
        end

        $display("[PASS]");
        $finish;
    end

    task check_outputs;
    begin
        expected_result = tb_a + tb_b + tb_cin;
        
        if(tb_sum !== expected_result[31:0])
        begin
            $display("[FAIL] %m: %h + %h + %b - expected: %b %h  got: %b %h", 
                tb_a, tb_b, tb_cin, expected_result[32], expected_result[31:0], tb_cout, tb_sum);
            $finish;
        end
    end
    endtask

    adder32 dut (
        .a    (tb_a),
        .b    (tb_b),
        .cin  (tb_cin),
        .sum  (tb_sum),
        .cout (tb_cout)
    );
endmodule
