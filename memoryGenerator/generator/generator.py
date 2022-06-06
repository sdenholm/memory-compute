import importlib
import os
import sys
import yaml

# default logging level is info
import logging
logger = logging.getLogger(__name__)

from memoryGenerator.generator.memoryCreator.memoryCreator import BlockRAMCreator

class MemoryGenerator:
  
  DEFAULT_PRJ_NAME = "vivado_builder"
  
  @staticmethod
  def _wordisePositiveInt(num):
    conv = {
      "1": "st", "2": "nd", "3":"rd"
    }
    strNum = str(num)
    if len(strNum) > 2 and strNum[1] == 1:
      return "th"
    else:
      return conv.get(strNum[0], "th")
  
  @staticmethod
  def _parseConfigFile(configFileLoc: str):
    """
    :param configFileLoc:
    :return:
    """
    
    logger.info("Parsing config file...")
    
    from memoryGenerator.generator.memoryCreator.inputIterator import Iterators
    
    # CHECK: file exists
    if not os.path.isfile(configFileLoc):
      logger.error("ERROR: Config file not found: {}".format(configFileLoc))
      sys.exit(1)

    # read yaml file
    try:
      with open(configFileLoc, 'r') as f:
    
        # load the yaml data
        yamlDict = yaml.safe_load(f)
        
        #######################################################################
        # top level check of config file
        
        # CHECK: entry for "vivado-project-directory"
        if yamlDict.get("vivado-project-directory", None) is None:
          logger.error("ERROR: No entry in config file for vivado-project-directory")
          sys.exit(1)

        # CHECK: entry for "function"
        if yamlDict.get("function", None) is None:
          logger.error("ERROR: No entry in config file for function")
          sys.exit(1)
        
        # CHECK: no other entries
        if len(yamlDict) != 2:
          unknownEntries = [k for k,_ in yamlDict.items() if k not in ["vivado-project-directory", "function"]]
          logger.error("ERROR: Unknown config file entries: {}".format(unknownEntries))
          sys.exit(1)
        
        
        #######################################################################
        # top level function check

        functionDict = yamlDict["function"]
        
        
        # CHECK: top level function entries are all present and the correct type
        functionEntries = {
          "name":         str,
          "arguments":    list,
          "output-width": int,
          "output-type":  str
        }
        for fnEntryName, fnEntryType in functionEntries.items():
          if functionDict.get(fnEntryName, None) is None:
            logger.error("ERROR: Missing '{}' entry for function".format(fnEntryName))
            sys.exit(1)
          if not isinstance(functionDict[fnEntryName], fnEntryType):
            logger.error("ERROR: '{}' must be of type {}".format(fnEntryName, fnEntryType))
            sys.exit(1)
        
        # CHECK: output type is supported
        if functionDict["output-type"] not in Iterators.SUPPORTED_TYPES:
          logger.error("ERROR: Output must be of type: {}".format(Iterators.SUPPORTED_TYPES))
          sys.exit(1)
        
        # CHECK: output type/precision are valid
        if functionDict["output-type"] == "float":
          
          if functionDict.get("output-precision", None) is None:
            logger.error("ERROR: Missing 'output-precision' entry for function")
            sys.exit(1)
            
          # CHECK: width and precision are numbers > 0
          for fnEntry in ["output-width", "output-precision"]:
            if not isinstance(functionDict[fnEntry], int) or functionDict[fnEntry] <= 0:
              logger.error("ERROR: '{}' must be a non-zero integer".format(fnEntry))
              sys.exit(1)
              
          # CHECK: precision < width
          if functionDict["output-precision"] >= functionDict["output-width"]:
            logger.error("ERROR: Output precision must be < output width")
            sys.exit(1)
        
        
        #######################################################################
        # function argument check
        
        argumentsList = functionDict["arguments"]
        
        # CHECK: at least 1 argument
        if len(argumentsList) == 0:
          logger.error("ERROR: Function must have at least 1 argument")
          sys.exit(1)

        argumentEntries = {
          "name":  str,
          "type":  str,
          "width": int,
        }
        
        # for each argument:
        for iArg, argumentDict in enumerate(argumentsList):
          
          # CHECK: argument entries are all present and the correct type
          for argEntryName, argEntryType in argumentEntries.items():
            if argumentDict.get(argEntryName, None) is None:
              logger.error("ERROR: {}{} argument is missing the '{}' entry"
                           .format(iArg+1, MemoryGenerator._wordisePositiveInt(iArg+1), argEntryName))
              sys.exit(1)
            if not isinstance(argumentDict[argEntryName], argEntryType):
              logger.error("ERROR: {}{} argument's '{}' entry must be of type {}"
                           .format(iArg+1, MemoryGenerator._wordisePositiveInt(iArg+1),
                                   argEntryName, argEntryType))
              sys.exit(1)

          # CHECK: type is supported
          if argumentDict["type"] not in Iterators.SUPPORTED_TYPES:
            logger.error("ERROR: {}{} argument's type must be one of: {}"
                         .format(iArg + 1, MemoryGenerator._wordisePositiveInt(iArg + 1),
                                 Iterators.SUPPORTED_TYPES))
            sys.exit(1)
          
          # CHECK: width is number > 0
          if not isinstance(argumentDict["width"], int) or argumentDict["width"] <= 0:
            logger.error("ERROR: {}{} argument's 'width' entry must be a non-zero integer"
                         .format(iArg+1, MemoryGenerator._wordisePositiveInt(iArg+1)))
            sys.exit(1)
          
          # CHECK: type/precision are valid
          if argumentDict["type"] == "float":
  
            if argumentDict.get("precision", None) is None:
              logger.error("ERROR: {}{} argument is missing the 'precision' entry"
                           .format(iArg+1, MemoryGenerator._wordisePositiveInt(iArg+1)))
              sys.exit(1)

            # CHECK: precision is number > 0
            if not isinstance(argumentDict["precision"], int) or argumentDict["precision"] <= 0:
              logger.error("ERROR: {}{} argument's 'precision' entry must be a non-zero integer"
                           .format(iArg + 1, MemoryGenerator._wordisePositiveInt(iArg + 1)))
              sys.exit(1)
  
            # CHECK: precision < width
            if argumentDict["precision"] >= argumentDict["width"]:
              logger.error("ERROR: {}{} argument' precision must be < output width"
                           .format(iArg+1, MemoryGenerator._wordisePositiveInt(iArg+1)))
              sys.exit(1)

    except Exception as err:
      logger.error("ERROR: Could not parse the YAML file:", err)
      sys.exit(1)

    logger.info("Config file parsed okay")
    return yamlDict
      
  
  def _parseFiles(self, configFile: str, functionFile: str):
    """
    :param configFile:
    :param functionFile:
    :return:
    """
    
    ###########################################################################
    # get config file's data

    # check and get config file data
    yamlDict = MemoryGenerator._parseConfigFile(configFile)

    self.functionDict = yamlDict["function"]

    self.functionName = self.functionDict["name"]
    self.totalInputWidth = sum([argDict["width"] for argDict in self.functionDict["arguments"]])
    self.totalOutputWidth = self.functionDict["output-width"]

    self.memoryName = "{}_{}b_{}b" \
      .format(self.functionName, self.totalInputWidth, self.totalOutputWidth)

    self.vivadoPrjDir = yamlDict["vivado-project-directory"]
    
    # CHECK: Vivado project directory exists
    if not os.path.isdir(self.vivadoPrjDir):
      logger.error("ERROR: Vivado project directory not found: {}".format(self.vivadoPrjDir))
      sys.exit(1)
    
    
    ###########################################################################
    # get user's python function

    # CHECK: function file exists
    if not os.path.exists(functionFile):
      raise FileNotFoundError(functionFile)

    # load function from function file as a module
    tempSysPath = sys.path
    sys.path = ["", os.path.dirname(functionFile)]
    userFunction = importlib.import_module(os.path.splitext(os.path.basename(functionFile))[0])
    sys.path = tempSysPath
    
    # import the user function
    try:
      self.function = None
      exec("self.function = userFunction.{}".format(self.functionName))
    except Exception as err:
      logger.error("ERROR: could not import user function '{}': {}".format(self.functionName, err))
      sys.exit(1)
    


  def __init__(self, workingDir: str, configFile: str, functionFile: str):
    
    
    # parse the config and function files
    self._parseFiles(configFile, functionFile)
    

    # locations of generation directory
    self.generatedFilesDir = workingDir #os.path.join(workingDir, "sources")
    
    # directory where generated memory files will be stored
    self.generatedMemDir = os.path.join(self.generatedFilesDir, self.memoryName)
    
    # CHECK: general
    #  -directories exist or not
    if not os.path.exists(workingDir):
      raise FileNotFoundError("Working directory not found: {}".format(workingDir))
    if not os.path.exists(self.generatedFilesDir):
      raise FileNotFoundError("Directory for generated files not found: {}".format(self.generatedFilesDir))
  
  
  def generate(self, suppressConfirmation: bool=False, maxConcurrentRuns: int=1):
    """
    # Generate the memory from the user function
    #
    :param suppressConfirmation: (bool) suppress the intital creation confirmation
    :param maxConcurrentRuns:    (int)  number of ip cores to build in parallel
    :return:
    """
    
    # CHECK: memory name isn't already being used
    if os.path.exists(self.generatedMemDir):
      logger.error("ERROR: Generated files directory for {} already exists: {}"
                            .format(self.memoryName, self.generatedMemDir))
      sys.exit(1)

    # calculate the specifics of the memory and sub memory
    memoryConfigInfo = BlockRAMCreator.calculateParallelMemoryConfig(
      addressWidth = self.totalInputWidth,
      dataWidth    = self.totalOutputWidth
    )
    
    # confirm the memory configuration with the user
    totalDataMem = (2**memoryConfigInfo["addressWidth"] * memoryConfigInfo["dataWidth"])/1024
    totalBRAMMem = (memoryConfigInfo["numSubMemories"] * BlockRAMCreator.TOTAL_BLOCK_RAM_MEMORY)/1024
    utilised     = round(100*totalDataMem/totalBRAMMem, 2)
    memConfigStr = "Memory configuration:\n" +\
      "-Total input width:      {}\n".format(memoryConfigInfo["addressWidth"]) +\
      "-Total output width:     {}\n".format(memoryConfigInfo["dataWidth"]) +\
      "-Number of sub-memories: {}\n".format(memoryConfigInfo["numSubMemories"]) +\
      "-Total data memory:      {}k-bits\n".format(totalDataMem) +\
      "-Total block RAM memory: {}k-bits ({}% utilised)\n".format(totalBRAMMem, utilised)
    if suppressConfirmation:
      logger.info(memConfigStr[-1])
    elif str(input(memConfigStr + "Continue (y/n)?: ")).lower() == "n":
      sys.exit(0)
    
    logger.info("Creating block RAM memory...")
    memoryConfigInfo, tclFileLoc = BlockRAMCreator.createMemory(
      outputDir         = self.generatedFilesDir,
      vivadoPrjDir      = self.vivadoPrjDir,
      memoryName        = self.memoryName,
      functionDict      = self.functionDict,
      func              = self.function,
      maxConcurrentRuns = maxConcurrentRuns,
    )
    
    return tclFileLoc
    