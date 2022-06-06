import os
import io
import math
import inspect

import logging
logger = logging.getLogger(__name__)

from memoryGenerator.generator import templateCreator
from memoryGenerator.generator.memoryCreator.inputIterator import Iterators




class BlockRAMCreator:
  """
  # Responsible for:
  #  -calculating the memory resources required for a given function's input
  #   and output widths
  #  -iterating through a given function and storing the results in the memory
  #   initialisation files
  #  -preparing the memory_compute and sub_memory_compute verilog files so that
  #   they reference and instantiate our memory
  #  -creating the tcl build script for vivado
  """
  
  TOTAL_BLOCK_RAM_MEMORY = 18 * 1024

  @staticmethod
  def calculateParallelMemoryConfig(addressWidth: int, dataWidth: int, subMemorySize: int = None):
    """
    # Calculate the specifics of parallel memory's sub-memories and the sub-memory selector
    #
    :param addressWidth:  (int) width of full memory's address input
    :param dataWidth:     (int) width of data held in memory
    :param subMemorySize: (int) bit size of each sub-memory (i.e., block RAM)
    :return:
    """
    
    # default block RAM size
    if subMemorySize is None:
      subMemorySize = BlockRAMCreator.TOTAL_BLOCK_RAM_MEMORY
    
    # width of each sub-memory depends on its depth, i.e., how many
    # "data items" it holds
    subMemoryAddressWidth = int(math.floor(math.log2(subMemorySize / dataWidth)))
  
    # how many bits of the full memory's address are used to select which
    # sub-memory to access
    memorySelectorWidth = max(0, addressWidth - subMemoryAddressWidth)
  
    return {
      "addressWidth":          addressWidth,             # address width of full memory
      "subMemoryAddressWidth": subMemoryAddressWidth,    # address width of each sub-memory bank
      "dataWidth":             dataWidth,                # width of data stored in memory
      "subMemoryDataDepth":    2**subMemoryAddressWidth, # depth of each sub-memory bank (i.e., number of items held)
      "memorySelectorWidth":   memorySelectorWidth,      # address width of the sub-memory selector
      "numSubMemories":        2**memorySelectorWidth    # total number of sub-memory banks
    }

  @staticmethod
  def createMemory(outputDir: str, memoryName: str, vivadoPrjDir: str, functionDict, func,
                   maxConcurrentRuns=1):
    """
    #
    #
    :param outputDir:    (str)  directory to store the coe directory, verilog file, and tcl file
    :param memoryName:   (str)  what this memory will be called
    :param vivadoPrjDir: (str)  where the Vivado project directory is
    :param functionDict: (dict) function information from the config file
    :param func:         (fn)   function to map to memory
    :param maxConcurrentRuns:
    :return:
    """
    
    logger.info("Creating coe files for each sub-memory...")
    # map the function to parallel memory, returning the bit-widths and
    # depth specifics of the mapping:
    #  -addressWidth
    #  -subMemoryAddressWidth
    #  -dataWidth
    #  -subMemoryDataDepth
    #  -memorySelectorWidth
    #  -numSubMemories
    memoryConfigInfo = BlockRAMCreator.createParallelMemory(
      memName      = memoryName,
      parentDirLoc = outputDir,
      functionDict = functionDict,
      func         = func,
      simulate     = False
    )
    
    # log the memory configuration information
    memConfigStr = "Memory configuration:\n"
    nameWidth = max(map(lambda x: len(x), (memoryConfigInfo.keys())))
    for k,v in memoryConfigInfo.items():
      memConfigStr += "-{}:".format(k).ljust(nameWidth+3, " ") + str(v) + "\n"
    totalDataMem = (2**memoryConfigInfo["addressWidth"] * memoryConfigInfo["dataWidth"])/1024
    totalBRAMMem = (memoryConfigInfo["numSubMemories"] * BlockRAMCreator.TOTAL_BLOCK_RAM_MEMORY)/1024
    utilised     = round(100*totalDataMem/totalBRAMMem, 2)
    memConfigStr += "-Total data memory:      {}k-bits\n".format(totalDataMem)
    memConfigStr += "-Total block RAM memory: {}k-bits ({}% utilised)\n".format(totalBRAMMem, utilised)
    logger.info(memConfigStr[:-1])
    
    
    coeFilesDir = os.path.join(outputDir, memoryName)
    tclFileLoc  = os.path.join(coeFilesDir, "{}.tcl".format(memoryName))
    
    # create the tcl script with commands to built the memory into block RAMs
    logger.info("Creating the tcl script for vivado...")
    logger.info("-command: 'source {}'".format(tclFileLoc))
    BlockRAMCreator.createVivadoScript(
      dirLoc            = coeFilesDir,
      memoryName        = memoryName,
      vivadoPrjDir      = vivadoPrjDir,
      coeFilesDir       = coeFilesDir,
      subMemDataWidth   = memoryConfigInfo["dataWidth"],
      subMemDataDepth   = memoryConfigInfo["subMemoryDataDepth"],
      numSubMemories    = memoryConfigInfo["numSubMemories"],
      maxConcurrentRuns = maxConcurrentRuns
    )
    
    # create the verilog file that instantiates the sub-memory blocks
    logger.info("Creating the verilog file for the sub-memory blocks...")
    BlockRAMCreator.createSubMemoryVerilog(
      dirLoc         = coeFilesDir, #outputDir,
      memoryName     = memoryName,
      addressWidth   = memoryConfigInfo["subMemoryAddressWidth"],
      dataWidth      = memoryConfigInfo["dataWidth"],
      numSubMemories = memoryConfigInfo["numSubMemories"]
    )

    # create the general memoryCompute verilog file
    logger.info("Creating the general memoryCompute verilog file...")
    templateCreator.memoryCompute(
      dirLoc                = coeFilesDir,
      numSubMemories        = memoryConfigInfo["numSubMemories"],
      memorySelectorWidth   = memoryConfigInfo["memorySelectorWidth"],
      subMemoryAddressWidth = memoryConfigInfo["subMemoryAddressWidth"]
    )
    
    return memoryConfigInfo, tclFileLoc
  
  
  @staticmethod
  def createVivadoScript(dirLoc: str, memoryName: str, vivadoPrjDir: str, coeFilesDir: str,
                         subMemDataWidth: int, subMemDataDepth: int, numSubMemories: int,
                         maxConcurrentRuns=1):
    """
    # Create a tcl script with vivado commands to generate the sub-memory block RAMs
    #
    :param maxConcurrentRuns:
    :param dirLoc:       (str) directory to write output tcl file
    :param memoryName:   (str) name of the full memory
    :param coeFilesDir:     (str) location of all the generated coe files for each sub-memory
    :param vivadoPrjDir:    (str) vivado project directory
    :param subMemDataWidth:
    :param subMemDataDepth:
    :param numSubMemories:
    :return:
    """

    # location of tcl file to create
    fileLoc = os.path.join(dirLoc, "{}.tcl".format(memoryName))

    # CHECK: destination directory exists
    if not (os.path.exists(dirLoc) and os.path.isdir(dirLoc)):
      raise FileNotFoundError("Output directory is not a valid directory: {}".format(dirLoc))

    # CHECK: destination file doesn't exist
    if os.path.exists(fileLoc):
      raise FileExistsError("Destination tcl file already exists: {}".format(dirLoc))
    

    
    
    dataWidthStr = str(subMemDataWidth)
    dataDepthStr = str(subMemDataDepth)

    enableASignal = "Use_ENA_Pin"  # "Always_Enabled"
    enableBSignal = "Use_ENB_Pin"  # "Always_Enabled"

    vivadoPrjName = os.path.basename(vivadoPrjDir)
    
    # vivado sources sub-directory in $projectDir/$vivadoPrjName.srcs
    sourceDir  = "sources_1"

    
    
    cmdList = []
    for iRun, memBankNum in enumerate(range(numSubMemories)):
      
      # name if this sub-memory bank
      memBankName = "{}_{}".format(memoryName, memBankNum)
      
      # location in the coe file directory of this sub-memory's coe file
      coeFileLoc = os.path.join(coeFilesDir, "{}.coe".format(memBankName))
    
      # simulation
      ipUserFilesDir = os.path.join(vivadoPrjDir, "{}.ip_user_files".format(vivadoPrjName))
      simLibDir      = os.path.join(vivadoPrjDir, "{}.cache/compile_simlib".format(vivadoPrjName))
      ipFileLocation = os.path.join(vivadoPrjDir, "{}.srcs".format(vivadoPrjName), sourceDir,
                                    "ip/{}/{}.xci".format(memBankName, memBankName))
    
      
    
      #precmdMaybe = "update_compile_order -fileset " + sourceDir
    
      cmdList += [
        "create_ip -name blk_mem_gen -vendor xilinx.com -library ip -version 8.4 -module_name " + memBankName
      ]
    
      cmdList += [
        "set_property -dict [list " + \
        "CONFIG.Component_Name {" + memBankName + "} " + \
        "CONFIG.Memory_Type {Dual_Port_ROM} " + \
        "CONFIG.Assume_Synchronous_Clk {true} " + \
        "CONFIG.Write_Width_A {" + dataWidthStr + "} " + \
        "CONFIG.Write_Depth_A {" + dataDepthStr + "} " + \
        "CONFIG.Read_Width_A {" + dataWidthStr + "} " + \
        "CONFIG.Enable_A {" + enableASignal + "} " + \
        "CONFIG.Write_Width_B {" + dataWidthStr + "} " + \
        "CONFIG.Read_Width_B {" + dataWidthStr + "} " + \
        "CONFIG.Enable_B {" + enableBSignal + "} " + \
        "CONFIG.Register_PortA_Output_of_Memory_Primitives {false} " + \
        "CONFIG.Register_PortB_Output_of_Memory_Primitives {false} " + \
        "CONFIG.Load_Init_File {true} " + \
        "CONFIG.Coe_File {" + coeFileLoc + "} " + \
        "CONFIG.Port_A_Write_Rate {0} " + \
        "CONFIG.Port_B_Clock {100} " + \
        "CONFIG.Port_B_Enable_Rate {100}" + \
        "] [get_ips " + memBankName + "]"
      ]
    
      cmdList += [
        "generate_target {instantiation_template} [get_files " + \
        ipFileLocation + \
        "]"
      ]
    
      cmdList += [
        "update_compile_order -fileset " + sourceDir
      ]
    
      cmdList += [
        "generate_target all [get_files  " + \
        ipFileLocation + \
        "]"
      ]
    
      cmdList += [
        "catch { config_ip_cache -export [get_ips -all " + memBankName + "] }"
      ]
    
      cmdList += [
        "export_ip_user_files -of_objects [get_files " + \
        ipFileLocation + \
        "] -no_script -sync -force -quiet"
      ]
    
      cmdList += [
        "create_ip_run [get_files -of_objects " + \
        "[get_fileset " + sourceDir + "] " + \
        ipFileLocation + \
        "]"
      ]
    
      cmdList += [
        "launch_runs " + memBankName + "_synth_1"
      ]
      
      cmdList += [
        "export_simulation -of_objects [get_files " + \
        ipFileLocation + \
        "] -directory " + ipUserFilesDir + "/sim_scripts " + \
        "-ip_user_files_dir " + ipUserFilesDir + " " + \
        "-ipstatic_source_dir " + ipUserFilesDir + "/ipstatic " + \
        "-lib_map_path [list " + \
        "{modelsim=" + simLibDir + "/modelsim} " + \
        "{questa=" + simLibDir + "/questa} " + \
        "{ies=" + simLibDir + "/ies} " + \
        "{xcelium=" + simLibDir + "/xcelium} " + \
        "{vcs=" + simLibDir + "/vcs} " + \
        "{riviera=" + simLibDir + "/riviera}" + \
        "] -use_ip_compiled_libs -force -quiet"
      ]
      
      # wait every <maxConcurrentRuns> runs
      if iRun+1 >= maxConcurrentRuns:
        waitOnMemBankName = "{}_{}".format(memoryName, memBankNum-maxConcurrentRuns+1)
        cmdList += [
          #"wait_on_run " + memBankName + "_synth_1"
          "wait_on_run " + waitOnMemBankName + "_synth_1"
        ]
      
      
    # open the output tcl file and write our commands
    with open(fileLoc, 'w') as f:
      for cmd in cmdList:
        f.write(cmd + "\n")
        

  
  @staticmethod
  def _assembleVerilogHeader(moduleName: str, addressWidth: int,
                             dataWidth: int, numSubMemories: int):
    """
    # Assemble the verilog file's module declaration
    #
    :param moduleName:     (str) name of the module
    :param addressWidth:   (int)
    :param dataWidth:      (int)
    :param numSubMemories: (int)
    :return:
    """
    return \
      "`timescale 1ns / 1ps\n" + \
      "\n" + \
      "module {}_sub_memory #(\n".format(moduleName) + \
      "  BANK_NUMBER       = {},\n".format(numSubMemories) + \
      "  ADDRESS_BIT_WIDTH = {},\n".format(addressWidth) + \
      "  DATA_BIT_WIDTH    = {}\n".format(dataWidth) + \
      ")(\n" + \
      "  input                          clka,\n" + \
      "  input                          ena,\n" + \
      "  input  [ADDRESS_BIT_WIDTH-1:0] addra,\n" + \
      "  output [DATA_BIT_WIDTH-1:0]    douta,\n" + \
      "\n" + \
      "  input                          clkb,\n" + \
      "  input                          enb,\n" + \
      "  input  [ADDRESS_BIT_WIDTH-1:0] addrb,\n" + \
      "  output [DATA_BIT_WIDTH-1:0]    doutb\n" + \
      ");\n" + \
      "\n" + \
      "\n" + \
      "case(BANK_NUMBER)\n"
  
  

  
  @staticmethod
  def createSubMemoryVerilog(dirLoc: str, memoryName: str, addressWidth: int, dataWidth: int, numSubMemories: int):
    """
    # Create the verilog file that will instantiate one of X possible sub-memories
    # based on the value of a verilog parameter passed in at module creation.
    #
    # Basically is just a large case statement, that instantiates block RAM 0 if
    # 0 is specified, 1 if 1 is specified, and so on.
    #
    :param dirLoc:       (str) directory to write output verilog file
    :param memoryName:   (str) name of the full memory
    :param addressWidth: (int) total bit-width of full memory's address
    :param dataWidth:    (int) bit-width of data stored in memory
    :param numSubMemories
    :return:
    """
    
    # verilog file to create
    fileLoc = os.path.join(dirLoc, "memory_compute_sub_memory.v")
    
    # CHECK: destination directory exists
    if not (os.path.exists(dirLoc) and os.path.isdir(dirLoc)):
      raise FileNotFoundError("Output directory is not a valid directory: {}".format(dirLoc))
    
    # CHECK: destination file already exists
    if os.path.exists(fileLoc):
      raise FileExistsError("Destination verilog file already exists: {}".format(dirLoc))
    

    # file header and footer
    fileHeaderStr = BlockRAMCreator._assembleVerilogHeader(
      moduleName     = "memory_compute",
      addressWidth   = addressWidth,
      dataWidth      = dataWidth,
      numSubMemories = numSubMemories
    )
    fileFooterStr = "endmodule\n"
    
    
    # create the case statement
    #  -if this is memory bank 0 then instantiate 0, if this is 1 then instantiate 1, etc
    caseStr = ""
    for i in range(numSubMemories):
      memBankNum = str(i)
      caseStr +=\
        "  " + memBankNum + ": begin\n" +\
        "    " + memoryName + "_" + memBankNum + " memory_inst (\n" +\
        "      .clka(clka), .ena(ena), .addra(addra), .douta(douta),\n" +\
        "      .clkb(clkb), .enb(enb), .addrb(addrb), .doutb(doutb)\n" +\
        "    );\n" +\
        "  end\n\n"
    
    
    # last case in the case statement is a default which catches any erroneous
    # memory bank values
    caseStr +=\
      "  default: begin\n" +\
      "    error_module();\n" +\
      "  end\n" +\
      "endcase\n\n"
    

    # open the output file and write our results
    with open(fileLoc, 'w') as f:
      f.write(fileHeaderStr)
      f.write(caseStr)
      f.write(fileFooterStr)
  
  



  @staticmethod
  def createParallelMemory(memName, parentDirLoc, functionDict, func, simulate=False):
    """
    #
    #
    :param memName:      (str)  prefix name for this memory
    :param parentDirLoc: (str)  location of parent directory for our output directory
    :param functionDict: (dict) function information from the config file
    :param func:         (func) function to populate the memory
    :param simulate:     (bool) just simulate file writing
    :return:
    """

    # calculate the total input width (for address) and output width (for data)
    totalInputWidth  = sum([argDict["width"] for argDict in functionDict["arguments"]])
    totalOutputWidth = functionDict["output-width"]
    
    dirLoc = os.path.join(parentDirLoc, memName)
    
    # CHECK: output parent directory exists
    if not os.path.exists(parentDirLoc):
     raise FileNotFoundError("Parent directory does not exist: {}".format(dirLoc))
    
    # CHECK: output directory doesn't exist
    if os.path.exists(dirLoc):
     raise FileExistsError("Directory already exists: {}".format(dirLoc))
    
    # create the output directory
    os.mkdir(dirLoc)
    
    # string buffer for output values
    opStr = ""
    
    # for each sub-memory:
    #  -number of results calculated
    #  -largest result calculated
    depthCount = 0
    maxResult  = None
    
    # output file names will start with the memory name prefix and iterate
    outputFileNameIterator = 0
    fileLoc = os.path.join(dirLoc, "{}_{}.coe".format(memName, outputFileNameIterator))

    # keep track of which memory bank we're creating
    bankCount = 0
    
    # calculate the specifics of the memory and sub memory
    memoryConfigInfo = BlockRAMCreator.calculateParallelMemoryConfig(
      addressWidth = totalInputWidth,
      dataWidth    = totalOutputWidth
    )
    

    # calculate the result for all possible input arguments
    for result in Iterators.iterator(functionDict, func):

      # update the max result (to later calculate the maximum bit-width of the data)
      try:
        maxResult = max(result, maxResult)
      except TypeError:
        maxResult = result
  
      # write the data to the string buffer
      # opStr += str(ipArgs) + " = " + str(result) + " (" + format(result, "x") + "),\n"
      opStr += format(result, "x") + ",\n"
      # if simulate:
      #  opStr += str(ipArgs) + " = " + str(result) + " (" + format(result, "x") + "),\n"
      # else:
      #  opStr += format(result, "x") + ",\n"
  
      depthCount += 1
  
      # if we have filled this memory bank
      if depthCount == memoryConfigInfo["subMemoryDataDepth"]:
        #
        additionalComments = \
          ";\n" + \
          "; Memory bank #{}\n".format(bankCount) + \
          "; Function:\n" + \
          "".join(["; {}".format(line) for line in inspect.getsourcelines(func)[0]])
    
        # terminate the string buffer
        opStr = opStr[:-2] + ";"
    
        # write our results
        BlockRAMCreator._writeOutputFile(
          fileLoc, opStr, maxResult, totalOutputWidth, depthCount,
          additionalComments = additionalComments,
          simulate           = simulate
        )
    
        # clear the output and result info
        maxResult  = None
        opStr      = ""
        depthCount = 0
    
        # finished this bank, so move on to the next one
        bankCount = bankCount + 1
    
        # assemble the name for the next file
        outputFileNameIterator += 1
        fileLoc = os.path.join(dirLoc, "{}_{}.coe".format(memName, outputFileNameIterator))
    
    
    if depthCount > 0:
      #
      additionalComments = \
        "; Function:\n" + \
        "".join(["; {}".format(line) for line in inspect.getsourcelines(func)[0]])
    
      # terminate the string buffer
      opStr = opStr[:-2] + ";"
    
      # write our results
      BlockRAMCreator._writeOutputFile(
        fileLoc, opStr, maxResult, totalOutputWidth, depthCount,
        additionalComments = additionalComments,
        simulate           = simulate
      )
    
    # return the specifics of the created memory
    return memoryConfigInfo

  

  @staticmethod
  def _writeOutputFile(fileLoc, dataStr, maxResult, bitWidthOut, depthCount,
                       additionalComments=None, simulate=False):
    """
    
    :param fileLoc:            (str)
    :param dataStr:            (str)
    :param maxResult           (int)  largest value in memory (actual value of bitWidthOut)
    :param bitWidthOut:        (int)  stored data's target bit-width for output
    :param depthCount:         (int)  number of items stored in memory
    :param additionalComments: (str) additional lines to write in the comments section
    :param simulate:           (bool) just simulate file write
    :return:
    """

    # CHECK: file doesn't already exist
    # if os.path.exists(fileLoc):
    #  raise FileExistsError("File already exists: {}".format(fileLoc))

    # CHECK:
    if not (isinstance(additionalComments, str) or additionalComments is None):
      raise ValueError("additionalComments must be a string or None")
    
    # if simulating, just output to terminal
    if simulate:
      output = io.StringIO("")
    else:
      output = open(fileLoc, 'w')
    
    # open the output file and write our results
    #with open(fileLoc, 'w') as f:
    with output as f:
      
      # write the memory information as a comment
      # -data bit-width and depth
      # -input address width
      f.write("; Data bit width: {} (Target: {})\n"
              .format(max(1, math.ceil(math.log2(max(1, maxResult)))), bitWidthOut))
      f.write("; Data bit depth: {}\n".format(depthCount))
      f.write("; Input address width: {}\n".format(max(1, math.ceil(math.log2(depthCount)))))
      if additionalComments is not None: f.write(additionalComments)
      f.write(";\n\n")
    
      # write the header
      f.write("memory_initialization_radix=16;\n")
      f.write("memory_initialization_vector=\n")
    
      # write the string buffer
      f.write(dataStr)
    
      if simulate:
        output.seek(0)
        for ln in output.readlines():
          print(ln, end="")
        print("")
    
