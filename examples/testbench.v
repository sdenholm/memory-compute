`timescale 1ns / 1ps

module testbench;

  integer test_num = 0;

  //###########################################################################
  // configuration for a 4-bit multiplier with 4 parallel calls

  // 4 parallel function calls
  localparam integer NUM_FN_CALLS = 4;

  // input width is concatenation of inputs
  localparam integer FN_CALL_WIDTH = 4+4;

  // output data width
  localparam integer DATA_WIDTH = 8;
  //###########################################################################


  reg clk;
  reg [NUM_FN_CALLS*FN_CALL_WIDTH-1:0] data_in;
  reg [NUM_FN_CALLS-1: 0]              data_in_valid;
  wire                                 data_in_ready;

  wire [NUM_FN_CALLS*DATA_WIDTH-1:0] data_out;
  wire                               data_out_valid;
  reg                                data_out_ready = 1'b1;

  reg [NUM_FN_CALLS*DATA_WIDTH-1:0] local_data;

  // connect the memory-compute module
  memory_compute #(
    .NUM_FN_CALLS  (NUM_FN_CALLS),
    .FN_CALL_WIDTH (FN_CALL_WIDTH),
    .DATA_WIDTH    (DATA_WIDTH)
  )
  memory_compute_inst (
    .clk            (clk),

    .data_in_valid  (data_in_valid),
    .data_in_ready  (data_in_ready),
    .data_in        (data_in),

    .data_out_valid (data_out_valid),
    .data_out_ready (data_out_ready),
    .data_out       (data_out)
  );

  initial
  begin
    local_data = {NUM_FN_CALLS*DATA_WIDTH{1'b0}};

    // generate clock signal
    clk = 1'b0;
    forever #10 clk = ~clk;
  end


  //###########################################################################
  // input signals

  // when the input is ready to accept new data present
  // 4 instructions for multiplication:
  //   -test 0: 1*2, 2*3, 3*4, 4*5
  //   -test 1: 5*6, 6*7, 7*8, 8*9
  //   -test 2: 9*a, a*b, b*c, c*d
  //   -test 3: d*e, e*f, f*0, 0*1
  always @(posedge clk)
  begin

    if (test_num == 0) begin
      data_in       <= {8'h12, 8'h23, 8'h34, 8'h45};
      data_in_valid <= 4'b1111;
    end

    else if (test_num == 1) begin
      data_in       <= {8'h56, 8'h67, 8'h78, 8'h89};
      data_in_valid <= 4'b1111;
    end

    else if (test_num == 2) begin
      data_in       <= {8'h9a, 8'hab, 8'hbc, 8'hcd};
      data_in_valid <= 4'b1111;
    end

    else if (test_num == 3) begin
      data_in       <= {8'hde, 8'hef, 8'hf0, 8'h01};
      data_in_valid <= 4'b1111;
    end

    else begin
      data_in       <= {NUM_FN_CALLS*FN_CALL_WIDTH{1'b0}};
      data_in_valid <= 4'b0000;
    end

    if (data_in_ready == 1'b1 & test_num < 4) begin
      test_num <= test_num + 1;
    end

  end


  //###########################################################################
  // output signals

  // when the ouput is valid, store a local copy of the data
  always @(posedge clk)
  begin
    if (data_out_valid == 1'b1) begin
      local_data <= data_out;

      // wait a few cycles to register the output then finish
      if (test_num == 4)
        #50
        $finish;
    end
  end


endmodule
