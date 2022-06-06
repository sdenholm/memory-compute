import os


def memoryCompute(dirLoc: str, numSubMemories: str,
                  memorySelectorWidth: str, subMemoryAddressWidth: str):
  """
  # Create the verilog file that will instantiate this memoryCompute function
  #
  # Takes the basic "memoryCompute" interface and instantiates our exact
  # implementation
  #
  :param dirLoc:               (str) directory to write output verilog file
  :param numSubMemories        (int) total number of sub-memories
  :param memorySelectorWidth   (int) address width when selecting a sub-memory
  :param subMemoryAddressWidth (int) address width of the sub-memory
  :return:
  """
  
  # verilog file to create
  ouputFileLoc = os.path.join(dirLoc, "memory_compute.v")
  
  # CHECK: destination directory exists
  if not (os.path.exists(dirLoc) and os.path.isdir(dirLoc)):
    raise FileNotFoundError("Output directory is not a valid directory: {}".format(dirLoc))
  
  # CHECK: destination file already exists
  if os.path.exists(ouputFileLoc):
    raise FileExistsError("Destination verilog file already exists: {}".format(dirLoc))
  
  # get the template file location
  currentDirectory = os.path.dirname(os.path.realpath(__file__))
  templateFileLoc = os.path.join(currentDirectory, "templates", "memory_compute.v")
  
  # read in the template file
  with open(templateFileLoc, 'r') as f:
    txt = f.read()
  
  # replace the placeholder sections
  # txt = txt.replace("<<MEMORY_NAME>>", str(memoryName))
  txt = txt.replace("<<NUM_SUB_MEMORIES>>", str(numSubMemories))
  txt = txt.replace("<<MEMORY_SELECTOR_BIT_WIDTH>>", str(memorySelectorWidth))
  txt = txt.replace("<<SUB_MEMORY_ADDRESS_BIT_WIDTH>>", str(subMemoryAddressWidth))
  
  # write the new output file
  with open(ouputFileLoc, 'w') as f:
    f.write(txt)