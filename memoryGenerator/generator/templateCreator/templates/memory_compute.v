`timescale 1ns / 1ps

module memory_compute #(
  

  // function call info
  NUM_FN_CALLS             = 0, // number of parallel function calls presented at the input
  FN_CALL_WIDTH            = 0, // bit-width of each function call
  DATA_WIDTH               = 0, // width of each function call's result
  
  // sub-memory info
  NUM_SUB_MEMORIES             = <<NUM_SUB_MEMORIES>>, // total number of sub-memories
  MEMORY_SELECTOR_BIT_WIDTH    = <<MEMORY_SELECTOR_BIT_WIDTH>>, // address bits used to select sub-memory
  SUB_MEMORY_ADDRESS_BIT_WIDTH = <<SUB_MEMORY_ADDRESS_BIT_WIDTH>>, // address bits used to read from sub-memroy
  //NUM_SUB_MEMORY_PORTS         =  2, // number of parallel read ports to sub-memory
  MEMORY_LATENCY               =  1  // number of cycles from address being processed until data is ready
)(
  input                                   clk,
  
  input  [NUM_FN_CALLS-1:0]               data_in_valid,
  output                                  data_in_ready,
  input  [NUM_FN_CALLS*FN_CALL_WIDTH-1:0] data_in,
  
  output                                  data_out_valid,
  input                                   data_out_ready,
  output [NUM_FN_CALLS*DATA_WIDTH-1:0]    data_out
  
);


//#############################################################################
// general setup

// HARD-CODED FOR NOW
localparam integer NUM_SUB_MEMORY_PORTS =  2;


genvar sub_mem, sub_mem_port, fn_call_num;

//#############################################################################
// carousel setup

// widths of the carousels
//  -in matches data_in, out matches data_out
localparam integer CAROUSEL_IN_WIDTH   = NUM_FN_CALLS*FN_CALL_WIDTH;
localparam integer CAROUSEL_OUT_WIDTH  = NUM_FN_CALLS*DATA_WIDTH;

// carousel in
wire [NUM_FN_CALLS-1:0]      data_in_carousel_valid;
reg  [NUM_FN_CALLS-1:0]      data_in_carousel_valid_prev;
reg  [CAROUSEL_IN_WIDTH-1:0] data_in_carousel = {CAROUSEL_IN_WIDTH{1'b0}};

// carousel out
reg [CAROUSEL_OUT_WIDTH-1:0] data_out_carousel;


//#############################################################################
// sub-memory setup

//localparam integer NUM_SUB_MEMORIES_BIT_WIDTH = $clog2(NUM_SUB_MEMORIES);


// one extra cycle after memory latency to process inputs before they are available to memory
localparam integer PROCESS_LATENCY       = MEMORY_LATENCY + 1;
localparam integer PROCESS_LATENCY_WIDTH = $clog2(PROCESS_LATENCY);

// input to block rams
reg  [NUM_SUB_MEMORY_PORTS-1:0]         sub_mem_en   [NUM_SUB_MEMORIES-1:0];
wire [SUB_MEMORY_ADDRESS_BIT_WIDTH-1:0] sub_mem_addr [NUM_SUB_MEMORIES-1:0][NUM_SUB_MEMORY_PORTS-1:0];

// output from block rams
reg  [PROCESS_LATENCY-1:0]              sub_mem_data_valid [NUM_SUB_MEMORIES-1:0][NUM_SUB_MEMORY_PORTS-1:0];
wire [DATA_WIDTH-1:0]                   sub_mem_data       [NUM_SUB_MEMORIES-1:0][NUM_SUB_MEMORY_PORTS-1:0];


//#############################################################################
// input and ouput registers

reg data_in_ready_r;

reg data_out_valid_r = 0;




//#############################################################################
// sub-memory group setup
//
//  -a group is made up of the sub-mems which all look at the same function call
//  -e.g., 32 sub-mems, each with 2 ports (= 64 ports) will wrap around the carousel
//   if there are fewer than 64 function calls:
//     -32 function call = function call 0 will be interrogated by sub-mem[0][0] and sub-mem[16][0]
//     -16 function call = function call 0 will be interrogated by sub-mem[0][0], sub-mem[8][0], sub-mem[16][0] and sub-mem[24][0]


//localparam integer SUB_MEMS_PER_GROUP = $ceil((NUM_SUB_MEMORIES * NUM_SUB_MEMORY_PORTS) / NUM_FN_CALLS);

// how many sub-memory groups are there
//  -if we have more ports than function calls, then multiple sub-memories check an function call each cycle, so we have <NUM_FN_CALLS> groups
//  -if we have more function calls than ports, then we are limited by the number of sub-memories, so we have <NUM_PORTS> groups
localparam integer NUM_PORTS  = NUM_SUB_MEMORIES * NUM_SUB_MEMORY_PORTS;
localparam integer NUM_GROUPS = NUM_PORTS >= NUM_FN_CALLS
                              ? NUM_FN_CALLS
                              : NUM_PORTS;

// wires that are pulled low on Z
tri0 [NUM_GROUPS-1:0] group_en;
tri0 [NUM_GROUPS-1:0] group_data_read;
tri0 [DATA_WIDTH-1:0] group_data [NUM_GROUPS-1:0];


//#############################################################################
// state machine

localparam NUM_STATES       = 4;
localparam NUM_STATES_WIDTH = $clog2(NUM_STATES);
localparam [NUM_STATES_WIDTH-1:0]
  STATE_IDLE                     = 0,
  STATE_PROCESSING               = 1,
  STATE_WAIT_FOR_PROCESS_LATENCY = 2,
  STATE_OUTPUT                   = 3;
reg [NUM_STATES_WIDTH-1:0] state = STATE_IDLE;



// the maximum number of cycles required to process all the input function calls
//localparam integer TOTAL_CYCLES       = $ceil(NUM_FN_CALLS/ ((NUM_SUB_MEMORIES * NUM_SUB_MEMORY_PORTS) / NUM_FN_CALLS));
localparam integer TOTAL_CYCLES       = $ceil(NUM_FN_CALLS/NUM_SUB_MEMORY_PORTS);
localparam integer TOTAL_CYCLES_WIDTH = $clog2(TOTAL_CYCLES);


// counts the cycle we are on when processing the input function calls
reg [TOTAL_CYCLES_WIDTH-1:0]    cycle_count;

// counts the cycles we need to wait for the last function call to be processed
// before it appears on the output
reg [PROCESS_LATENCY_WIDTH+1-1:0] latency_wait;


//#############################################################################
// instantiate the sub-memories

genvar g;
generate
for (g = 0; g < NUM_SUB_MEMORIES; g = g + 1) begin
  memory_compute_sub_memory #(
    .BANK_NUMBER       (g),
    .ADDRESS_BIT_WIDTH (SUB_MEMORY_ADDRESS_BIT_WIDTH),
    .DATA_BIT_WIDTH    (DATA_WIDTH)
  )
  sub_mem (
    .clka(clk), .ena(sub_mem_en[g][0]), .addra(sub_mem_addr[g][0]), .douta(sub_mem_data[g][0]),
    .clkb(clk), .enb(sub_mem_en[g][1]), .addrb(sub_mem_addr[g][1]), .doutb(sub_mem_data[g][1])
  );
end
endgenerate

//#############################################################################
// define the sub-memory groups

generate
for (sub_mem = 0; sub_mem < NUM_SUB_MEMORIES; sub_mem = sub_mem + 1) begin
  for (sub_mem_port = 0; sub_mem_port < NUM_SUB_MEMORY_PORTS; sub_mem_port = sub_mem_port + 1) begin
    
    localparam port = (sub_mem * NUM_SUB_MEMORY_PORTS) + sub_mem_port;
    
    // if this group read data from its function call
    //  -i.e., the function call is being processed, and is now invalid
    assign group_data_read[port % NUM_GROUPS] = sub_mem_en[sub_mem][sub_mem_port] 
                                              ? 1'b1
                                              : 1'bz;
    
    // if this group is outputting data now
    assign group_en[port % NUM_GROUPS] = sub_mem_data_valid[sub_mem][sub_mem_port][0] 
                                       ? 1'b1
                                       : 1'bz;
    
    // the data being output by this group
    assign group_data[port % NUM_GROUPS] = sub_mem_data_valid[sub_mem][sub_mem_port][0]
                                         ? sub_mem_data[sub_mem][sub_mem_port]
                                         : {DATA_WIDTH{1'bz}};
  
  end
end
endgenerate



//#############################################################################
// rotate the data in carousel's valid signal

always @(posedge clk) begin
  data_in_carousel_valid_prev <= data_in_carousel_valid;
end




//#############################################################################
// state machine to start and stop the function call processing

always @(posedge clk) begin
case (state)
  
  
  // waiting for input data
  STATE_IDLE: begin
    
    // nothing to do, nothing to output
    cycle_count      <= 0;
    latency_wait     <= 0;
    data_out_valid_r <= 1'b0;
        
    // if we have valid function calls and are ready to process them
    if (data_in_valid > 0 & data_in_ready) begin
      state <= STATE_PROCESSING;
      data_in_ready_r  <= 1'b0;

    end
    
    // else, keep waiting
    else
      data_in_ready_r  <= 1'b1;
      
      
  end
  
  
  // cycling the carousel and processing function calls
  STATE_PROCESSING: begin
    
    // if all function calls have been processed
    if (data_in_carousel_valid == 0) begin
    //if (cycle_count == TOTAL_CYCLES-1) begin
      
      // if we need to wait for the memory result, i.e., our process has a latency > 1
      //  -wait for the memory result to appear
      if (PROCESS_LATENCY > 1) begin
        latency_wait <= 1; //PROCESS_LATENCY-1;
        state        <= STATE_WAIT_FOR_PROCESS_LATENCY;
        
      end
      
      // else, skip straight to the output stage
      else begin
        state            <= STATE_OUTPUT;
        data_out_valid_r <= 1'b1;
        
      end
      
    end
    
    // still have processing to be done
    else begin
      cycle_count <= cycle_count + 1;
    end
    
  end
  
  
  // waiting for the final result(s) from memory
  STATE_WAIT_FOR_PROCESS_LATENCY: begin
    
    latency_wait <= latency_wait + 1;
    
    // wait for the memory result
    if (latency_wait == PROCESS_LATENCY-1) begin
      state            <= STATE_OUTPUT;
      data_out_valid_r <= 1'b1;
      
    end
    
    //else
    //  latency_wait <= latency_wait - 1;
    
  end
  
  
  // got all the results, so wait until they are read out
  STATE_OUTPUT: begin
    
    // if the result has been read out, go back to idle and wait for a new input
    if (data_out_valid & data_out_ready) begin
      state            <= STATE_IDLE;
      data_out_valid_r <= 1'b0;
      data_in_ready_r  <= 1'b1;
      
    end
    
  end
endcase
end





//#######################################################################
// carousel data
//
// -input:
//   -store new data when we get it, and rotate
// -output:
//  -write memory results when they appear, and rotate
//
// NOTE: not every part of data_out is wired straight to a group
//  -e.g., with 64 ports and 65 function calls, the final function call nas no direct connection
//  -the non-wired function calls are STILL EXECUTED, as the carousel will cycle it past the sub-mems
    

generate

// corner case where we don't need to rotate the carousel
if (TOTAL_CYCLES <= 1) begin
  
  // don't need to rotate the carousel
  always @(posedge clk) begin
    data_in_carousel <= data_in;
  end
  
  
  // if the group has output data ready to go, write it to the output
  for (fn_call_num = 0; fn_call_num < NUM_FN_CALLS; fn_call_num = fn_call_num + 1) begin
    always @(posedge clk) begin
      if (group_en[fn_call_num])
        data_out_carousel[fn_call_num*DATA_WIDTH +: DATA_WIDTH] <= group_data[fn_call_num];
    end
  end
  
end

// general case where we need to rotate the carousel
else begin

for (fn_call_num = 0; fn_call_num < NUM_FN_CALLS; fn_call_num = fn_call_num + 1) begin
  
  // every cycle the carousel shifts over one sub-memory "width"
  localparam integer fn_call_num_prev = fn_call_num  - NUM_SUB_MEMORY_PORTS < 0
                                      ? NUM_FN_CALLS + fn_call_num - NUM_SUB_MEMORY_PORTS // - NUM_SUB_MEMORY_PORTS
                                      : fn_call_num  - NUM_SUB_MEMORY_PORTS;


  always @(posedge clk) begin
  
    // state machine for rotating the input carousel
    case (state)
      
      // start rotating when we get new function calls
      STATE_IDLE: begin
    
        // if the function call at data_in wants to read from this sub-memory
        if (data_in_valid > 0 & data_in_ready)
          data_in_carousel <= {data_in[CAROUSEL_IN_WIDTH-(FN_CALL_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                               data_in[CAROUSEL_IN_WIDTH-1                                      : CAROUSEL_IN_WIDTH-(FN_CALL_WIDTH*NUM_SUB_MEMORY_PORTS)]};
      end
      
      // always rotate when processing
      STATE_PROCESSING: begin
        data_in_carousel <= {data_in_carousel[CAROUSEL_IN_WIDTH-(FN_CALL_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                             data_in_carousel[CAROUSEL_IN_WIDTH-1                                      : CAROUSEL_IN_WIDTH-(FN_CALL_WIDTH*NUM_SUB_MEMORY_PORTS)]};
      end
      
    // don't rotate the input in other states, as we are done dealing with the input
    endcase
    
    
    // state machine for rotating the output carousel
    case (state)
      
      //// useful for debugging
      //STATE_IDLE: begin
      //  data_out_carousel <= {CAROUSEL_OUT_WIDTH{1'bx}};
      //end
      
      // only rotate the output carousel whilst processing function calls and
      // waiting on their output results
      STATE_PROCESSING, STATE_WAIT_FOR_PROCESS_LATENCY: begin

        // if there is a group assigned to this output location
        //  -NOTE: we are looking at the PREVIOUS function call
        if (fn_call_num_prev < NUM_GROUPS) begin
          
          // if the group has output data ready to go, write it to the output
          if (group_en[fn_call_num_prev])
            data_out_carousel[fn_call_num*DATA_WIDTH +: DATA_WIDTH] <= group_data[fn_call_num_prev];
          
          // else, just rotate the data_out_carousel
          else
            data_out_carousel[fn_call_num*DATA_WIDTH +: DATA_WIDTH] <= data_out_carousel[fn_call_num_prev*DATA_WIDTH +: DATA_WIDTH];
          
        end

        // no group to assign to this location, so just rotate the data_out_carousel
        else begin
          data_out_carousel[fn_call_num*DATA_WIDTH +: DATA_WIDTH] <= data_out_carousel[fn_call_num_prev*DATA_WIDTH +: DATA_WIDTH];
        end
        
      end
    endcase
    
  end
end
end
endgenerate



//#############################################################################
// propagate the sub-memory enable signals so we can tell its valid data at the memory output

generate
for (sub_mem = 0; sub_mem < NUM_SUB_MEMORIES; sub_mem = sub_mem + 1) begin
  for (sub_mem_port = 0; sub_mem_port < NUM_SUB_MEMORY_PORTS; sub_mem_port = sub_mem_port + 1) begin
    always @(posedge clk) begin
      if (MEMORY_LATENCY == 1)
        sub_mem_data_valid[sub_mem][sub_mem_port] <= sub_mem_en[sub_mem][sub_mem_port];
      else
        sub_mem_data_valid[sub_mem][sub_mem_port] <= {sub_mem_en[sub_mem][sub_mem_port], sub_mem_data_valid[sub_mem][sub_mem_port][MEMORY_LATENCY-1:1]};
    end
  end
end
endgenerate  



//#############################################################################
// propagate input carousel's valid signals, updating them should a function call be read

generate
for (fn_call_num = 0; fn_call_num < NUM_FN_CALLS; fn_call_num = fn_call_num + 1) begin

  // every cycle the carousel shifts over one sub-memory "width"
  localparam integer fn_call_num_prev = fn_call_num  - NUM_SUB_MEMORY_PORTS < 0
                                      ? NUM_FN_CALLS + fn_call_num - NUM_SUB_MEMORY_PORTS
                                      : fn_call_num  - NUM_SUB_MEMORY_PORTS;
  
  // if there is a group assigned to this carousel location
  //  -NOTE: we are looking at the PREVIOUS function call
  if (fn_call_num_prev < NUM_GROUPS)
    
    // it's valid/invalid if:
    // -at input stage:
    //   -the input signal says it is
    // -while processing:
    //   -invalidated by being read by its group
    //   -else, just copy the last known validity
    assign data_in_carousel_valid[fn_call_num] = data_in_valid > 0 & data_in_ready & state == STATE_IDLE
                                               ? data_in_valid[fn_call_num]
                                               : group_data_read[fn_call_num_prev]
                                                 ? 1'b0
                                                 : data_in_carousel_valid_prev[fn_call_num_prev];

  // no group assigned to output to this function call location
  else
    
    // it's valid/invalid if:
    // -at input stage:
    //   -the input signal says it is
    // -while processing:
    //   -just copy the last know validity
    assign data_in_carousel_valid[fn_call_num] = data_in_valid > 0 & data_in_ready & state == STATE_IDLE
                                               ? data_in_valid[fn_call_num]
                                               : data_in_carousel_valid_prev[fn_call_num_prev];
                                                   
end
endgenerate 



//#############################################################################
// sub-memories INPUT
//  -should this sub-memory port read this function call
//
// -slightly awkward setup as the enable signal is clocked and the address is not
//  -we therefore:
//    -set the enable NEXT CYCLE if the function call at OUR LOCATION is valid, and meant for us
//    -set the address NOW to always point to the NEXT LOCATION 
// -this saves a LOT of registers and trouble in other areas

//reg [MEMORY_SELECTOR_BIT_WIDTH-1 : 0] mem_sel [NUM_SUB_MEMORIES-1:0][NUM_SUB_MEMORY_PORTS-1:0];

generate
for (sub_mem = 0; sub_mem < NUM_SUB_MEMORIES; sub_mem = sub_mem + 1) begin
  for (sub_mem_port = 0; sub_mem_port < NUM_SUB_MEMORY_PORTS; sub_mem_port = sub_mem_port + 1) begin
    
    localparam integer fn_call_num      = ((sub_mem * NUM_SUB_MEMORY_PORTS) + sub_mem_port) % NUM_FN_CALLS;
    
    localparam integer fn_call_num_prev = fn_call_num  - NUM_SUB_MEMORY_PORTS < 0
                                        ? NUM_FN_CALLS + fn_call_num - NUM_SUB_MEMORY_PORTS
                                        : fn_call_num  - NUM_SUB_MEMORY_PORTS;
    
    localparam integer fn_call_num_next = (fn_call_num  + NUM_SUB_MEMORY_PORTS) % NUM_FN_CALLS;
    
    
    reg sub_mem_selected;
    
    always @(posedge clk) begin
      

        
      
      if (state == STATE_IDLE) begin
        
        // looks to see if the function call is for this sub-memory
        if (MEMORY_SELECTOR_BIT_WIDTH > 0)
          sub_mem_selected = data_in[(fn_call_num+1)*FN_CALL_WIDTH-1 -: MEMORY_SELECTOR_BIT_WIDTH] == sub_mem;
        else
          sub_mem_selected = 1'b1;
    
        // only consider the DATA_IN function call if
        //  -the function call is valid
        //  -we are ready to processs new data
        //  -the function call is for this sub-memory
        //sub_mem_en[sub_mem][sub_mem_port] <= data_in_valid[fn_call_num]
        //                                   & data_in_ready
        //                                   & data_in[(fn_call_num+1)*FN_CALL_WIDTH-1 -: MEMORY_SELECTOR_BIT_WIDTH] == sub_mem;
        sub_mem_en[sub_mem][sub_mem_port] <= data_in_valid[fn_call_num]
                                           & data_in_ready
                                           & sub_mem_selected;
      end
      
      else begin
      
        // looks to see if the function call is for this sub-memory
        if (MEMORY_SELECTOR_BIT_WIDTH > 0)
          sub_mem_selected = data_in_carousel[(fn_call_num+1)*FN_CALL_WIDTH-1 -: MEMORY_SELECTOR_BIT_WIDTH] == sub_mem;
        else
          sub_mem_selected = 1'b1;
      
        // only consider the INPUT CAROUSEL function call if
        //  -the function call is valid
        //  -the function call is for this sub-memory
        //sub_mem_en[sub_mem][sub_mem_port] <= data_in_carousel_valid[fn_call_num]
        //                                   & data_in_carousel[(fn_call_num+1)*FN_CALL_WIDTH-1 -: MEMORY_SELECTOR_BIT_WIDTH] == sub_mem;
        sub_mem_en[sub_mem][sub_mem_port] <= data_in_carousel_valid[fn_call_num]
                                           & sub_mem_selected;
      end

    end
    
    
    // each sub-memory port permanently points at one function call location on the carousel
    //  -connected to NEXT function call, as the clocked check above takes a cycle to set the enable
    //assign sub_mem_addr[sub_mem][sub_mem_port] = data_in_carousel[fn_call_num_next*FN_CALL_WIDTH +: SUB_MEMORY_ADDRESS_BIT_WIDTH];
    if (SUB_MEMORY_ADDRESS_BIT_WIDTH > FN_CALL_WIDTH)
      assign sub_mem_addr[sub_mem][sub_mem_port] = {{SUB_MEMORY_ADDRESS_BIT_WIDTH-FN_CALL_WIDTH{1'b0}}, data_in_carousel[fn_call_num_next*FN_CALL_WIDTH +: FN_CALL_WIDTH]};
    else
      assign sub_mem_addr[sub_mem][sub_mem_port] = data_in_carousel[fn_call_num_next*FN_CALL_WIDTH +: SUB_MEMORY_ADDRESS_BIT_WIDTH];

  end
end
endgenerate


//#############################################################################
// assign the outputs
assign data_in_ready  = data_in_ready_r;
assign data_out_valid = data_out_valid_r;
//assign data_out       = data_out_carousel;






if (NUM_FN_CALLS/NUM_SUB_MEMORY_PORTS == 1) begin
  assign data_out = data_out_carousel;
  
end
else if (NUM_FN_CALLS/NUM_SUB_MEMORY_PORTS == 2) begin
  assign data_out = cycle_count + latency_wait == 0 //state == STATE_OUTPUT
                  ? data_out_carousel
                  : cycle_count + latency_wait == 1
                  ? data_out_carousel
                  : cycle_count + latency_wait == 2 // THIS IS THE PROCESS LATENCY
                  ? {data_out_carousel[(2-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                      data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (2-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                  : data_out_carousel
                  ;
end
else if (NUM_FN_CALLS/NUM_SUB_MEMORY_PORTS == 4) begin
  assign data_out = cycle_count + latency_wait == 0 //state == STATE_OUTPUT
                  ? data_out_carousel
                  : cycle_count + latency_wait == 1
                  ? data_out_carousel
                  : cycle_count + latency_wait == 2 // THIS IS THE PROCESS LATENCY
                  ? {data_out_carousel[(2-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                      data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (2-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                  : cycle_count + latency_wait == 3
                  ? {data_out_carousel[(3-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                      data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (3-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                  : cycle_count + latency_wait == 4
                  ? {data_out_carousel[(4-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                      data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (4-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                  : data_out_carousel
                  ;
end
else if (NUM_FN_CALLS/NUM_SUB_MEMORY_PORTS == 8) begin
  assign data_out = cycle_count + latency_wait == 0 //state == STATE_OUTPUT
                  ? data_out_carousel
                  : cycle_count + latency_wait == 1
                  ? data_out_carousel
                  : cycle_count + latency_wait == 2 // THIS IS THE PROCESS LATENCY
                  ? {data_out_carousel[(2-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                      data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (2-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                  : cycle_count + latency_wait == 3
                  ? {data_out_carousel[(3-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                      data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (3-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                  : cycle_count + latency_wait == 4
                  ? {data_out_carousel[(4-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                      data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (4-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                  : cycle_count + latency_wait == 5
                  ? {data_out_carousel[(5-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                      data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (5-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                  : cycle_count + latency_wait == 6
                  ? {data_out_carousel[(6-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                      data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (6-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                  : cycle_count + latency_wait == 7
                  ? {data_out_carousel[(7-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                      data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (7-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                  : cycle_count + latency_wait == 8
                  ? {data_out_carousel[(8-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                      data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (8-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                  : data_out_carousel
                  ;
end
else begin



assign data_out = cycle_count + latency_wait == 0 //state == STATE_OUTPUT
                ? data_out_carousel
                : cycle_count + latency_wait == 1
                ? data_out_carousel
                : cycle_count + latency_wait == 2 // THIS IS THE PROCESS LATENCY
                ? {data_out_carousel[(2-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                    data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (2-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                : cycle_count + latency_wait == 3
                ? {data_out_carousel[(3-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                    data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (3-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                : cycle_count + latency_wait == 4
                ? {data_out_carousel[(4-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                    data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (4-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                : cycle_count + latency_wait == 5
                ? {data_out_carousel[(5-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                    data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (5-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                : cycle_count + latency_wait == 6
                ? {data_out_carousel[(6-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                    data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (6-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                : cycle_count + latency_wait == 7
                ? {data_out_carousel[(7-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                    data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (7-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                : cycle_count + latency_wait == 8
                ? {data_out_carousel[(8-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                    data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (8-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                : cycle_count + latency_wait == 9
                ? {data_out_carousel[(9-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                    data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (9-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                : cycle_count + latency_wait == 10
                ? {data_out_carousel[(10-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                    data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (10-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                : cycle_count + latency_wait == 11
                ? {data_out_carousel[(11-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                    data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (11-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                : cycle_count + latency_wait == 12
                ? {data_out_carousel[(12-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                    data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (12-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                : cycle_count + latency_wait == 13
                ? {data_out_carousel[(13-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                    data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (13-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                : cycle_count + latency_wait == 14
                ? {data_out_carousel[(14-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                    data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (14-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                : cycle_count + latency_wait == 15
                ? {data_out_carousel[(15-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                    data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (15-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                : cycle_count + latency_wait == 16
                ? {data_out_carousel[(16-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)-1 : 0],
                    data_out_carousel[CAROUSEL_OUT_WIDTH-1 : (16-1)*(DATA_WIDTH*NUM_SUB_MEMORY_PORTS)]}
                : data_out_carousel
                ;

end


endmodule






