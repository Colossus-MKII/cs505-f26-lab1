module counter32 (
    input         clock_i,
    input         reset_ni,
    
    output [31:0] count_o
);
    // counter logic
    wire  [31:0] sum;
    reg   [31:0] counter;

    always @(posedge clock_i) 
    begin
        counter <= reset_ni ? sum : 32'b0;
    end

    // design under test
    wire [31:0] a;
    wire [31:0] b;
    wire        cin;
    
    assign a = counter;
    assign b = 32'b0;
    assign cin = 1'b1;

    adder32 dut (
        .a    (a),
        .b    (b),
        .cin  (cin),
        .sum  (sum),
        .cout ()
    );
    
    // module outputs
    assign count_o = counter;
endmodule