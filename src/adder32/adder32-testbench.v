`timescale 1ns/1ps
module adder32_testbench ();
    reg  [31:0] tb_a;
    reg  [31:0] tb_b;
    reg         tb_cin;
    reg  [32:0] expected_result;
    wire [31:0] tb_sum;
    wire        tb_cout;
    integer i;
    integer checked_vectors = 0;
    reg [31:0] random_state;
    reg [31:0] carry_mask;
    reg [32*255:0] vcd_name;

    // Preserve the supplied workload interval; 1 ps precision rounds it to 986 ps.
    localparam real SAMPLE_INTERVAL_NS = 0.9855;
    localparam integer RANDOM_VECTORS = 100000;

    // A fixed xorshift32 stream makes all architectures see identical inputs.
    function [31:0] next_random;
        input [31:0] state;
        reg [31:0] value;
        begin
            value = state ^ (state << 13);
            value = value ^ (value >> 17);
            next_random = value ^ (value << 5);
        end
    endfunction

    task check_outputs;
        begin
            expected_result = {1'b0, tb_a} + {1'b0, tb_b} + {32'b0, tb_cin};
            if ({tb_cout, tb_sum} !== expected_result)
                $fatal(1, "[FAIL] %m: %h + %h + %b expected %h got %b%h",
                       tb_a, tb_b, tb_cin, expected_result, tb_cout, tb_sum);
            checked_vectors = checked_vectors + 1;
        end
    endtask

    task apply_vector;
        input [31:0] value_a;
        input [31:0] value_b;
        input value_cin;
        begin
            tb_a = value_a;
            tb_b = value_b;
            tb_cin = value_cin;
            #(SAMPLE_INTERVAL_NS);
            check_outputs();
        end
    endtask

    initial begin
        if ($value$plusargs("vcd=%s", vcd_name)) begin
            $display("Dumping VCD: %0s", vcd_name);
            $dumpfile(vcd_name);
            $dumpvars(0);
        end

        apply_vector(32'h00000000, 32'h00000000, 1'b0);
        apply_vector(32'h00000000, 32'h00000000, 1'b1);
        apply_vector(32'hffffffff, 32'h00000000, 1'b1);
        apply_vector(32'hffffffff, 32'h00000001, 1'b0);
        apply_vector(32'hffffffff, 32'hffffffff, 1'b0);
        apply_vector(32'hffffffff, 32'hffffffff, 1'b1);
        apply_vector(32'h80000000, 32'h80000000, 1'b0);
        apply_vector(32'h7fffffff, 32'h00000000, 1'b1);
        apply_vector(32'haaaaaaaa, 32'h55555555, 1'b0);
        apply_vector(32'haaaaaaaa, 32'h55555555, 1'b1);
        // Force carries across every possible prefix boundary, including bit 31.
        for (i = 1; i <= 32; i = i + 1) begin
            carry_mask = 32'hffffffff >> (32 - i);
            apply_vector(carry_mask, 32'h00000001, 1'b0);
            apply_vector(carry_mask, 32'h00000000, 1'b1);
            apply_vector(32'h00000001, carry_mask, 1'b0);
        end

        random_state = 32'h505f2601;
        for (i = 0; i < RANDOM_VECTORS; i = i + 1) begin
            random_state = next_random(random_state);
            tb_a = random_state;
            random_state = next_random(random_state);
            tb_b = random_state;
            random_state = next_random(random_state);
            tb_cin = random_state[0];
            #(SAMPLE_INTERVAL_NS);
            check_outputs();
        end
        $display("[PASS] %0d full 33-bit vectors checked", checked_vectors);
        $finish;
    end

    adder32 dut (
        .a(tb_a), .b(tb_b), .cin(tb_cin), .sum(tb_sum), .cout(tb_cout)
    );
endmodule
