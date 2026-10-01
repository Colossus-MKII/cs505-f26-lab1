// 32-bit Brent-Kung parallel-prefix adder with 57 prefix-combine nodes.
// Compile this file as an alternative implementation of module adder32.
module adder32 (
    input  [31:0] a,
    input  [31:0] b,
    input         cin,
    output [31:0] sum,
    output        cout
);
    wire [31:0] bit_p;
    wire [32:0] carry;

    assign bit_p = a ^ b;

    genvar stage, bit_index;
    generate
        // Reduction: combine endpoints of blocks of 2, 4, 8, 16, and 32.
        // This forms complete prefixes at bits 1, 3, 7, 15, and 31.
        for (stage = 0; stage < 5; stage = stage + 1) begin : reduction_stage
            wire [31:0] p_in, g_in;
            wire [31:0] p_out, g_out;
            if (stage == 0) begin : initial_pairs
                assign p_in = bit_p;
                assign g_in = a & b;
            end else begin : previous_stage
                assign p_in = reduction_stage[stage-1].p_out;
                assign g_in = reduction_stage[stage-1].g_out;
            end
            for (bit_index = 0; bit_index < 32; bit_index = bit_index + 1) begin : prefix_bit
                if (((bit_index + 1) % (1 << (stage + 1))) == 0) begin : combine
                    assign g_out[bit_index] = g_in[bit_index]
                        | (p_in[bit_index] & g_in[bit_index-(1 << stage)]);
                    assign p_out[bit_index] = p_in[bit_index]
                        & p_in[bit_index-(1 << stage)];
                end else begin : forward
                    assign g_out[bit_index] = g_in[bit_index];
                    assign p_out[bit_index] = p_in[bit_index];
                end
            end
        end

        // Distribution: distances 8, 4, 2, and 1 fill the missing prefixes.
        // At distance d, update endpoints 3*d-1, 5*d-1, 7*d-1, ... .
        for (stage = 0; stage < 4; stage = stage + 1) begin : distribution_stage
            wire [31:0] p_in, g_in;
            wire [31:0] p_out, g_out;
            if (stage == 0) begin : reduction_result
                assign p_in = reduction_stage[4].p_out;
                assign g_in = reduction_stage[4].g_out;
            end else begin : previous_stage
                assign p_in = distribution_stage[stage-1].p_out;
                assign g_in = distribution_stage[stage-1].g_out;
            end
            for (bit_index = 0; bit_index < 32; bit_index = bit_index + 1) begin : prefix_bit
                if ((bit_index >= (3 * (1 << (3 - stage)) - 1))
                    && (((bit_index + 1) % (1 << (4 - stage))) == (1 << (3 - stage)))) begin : combine
                    assign g_out[bit_index] = g_in[bit_index]
                        | (p_in[bit_index] & g_in[bit_index-(1 << (3 - stage))]);
                    assign p_out[bit_index] = p_in[bit_index]
                        & p_in[bit_index-(1 << (3 - stage))];
                end else begin : forward
                    assign g_out[bit_index] = g_in[bit_index];
                    assign p_out[bit_index] = p_in[bit_index];
                end
            end
        end

        // Each final prefix now spans [bit_index:0]. Retain the original
        // bit propagate for sums and include cin explicitly in every carry.
        for (bit_index = 0; bit_index < 32; bit_index = bit_index + 1) begin : result_bit
            assign carry[bit_index+1] = distribution_stage[3].g_out[bit_index]
                | (distribution_stage[3].p_out[bit_index] & cin);
            assign sum[bit_index] = bit_p[bit_index] ^ carry[bit_index];
        end
    endgenerate

    assign carry[0] = cin;
    assign cout = carry[32];
endmodule
