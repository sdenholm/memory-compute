import argparse
import os
import sys
import logging

# the current and root directories
currentDirectory = os.path.dirname(os.path.realpath(__file__))
rootDirectory    = os.path.dirname(currentDirectory)

# CHECK: log file can be created
LOG_FILENAME = os.path.join(rootDirectory, "memoryGenerator.log")
logFileDir = os.path.dirname(LOG_FILENAME)
if not os.path.exists(logFileDir):
  raise FileNotFoundError("log directory does not exist: {}".format(logFileDir))

# create a file logger that automatically rotates log files
logging.getLogger("").setLevel(logging.DEBUG)
from logging.handlers import RotatingFileHandler
fileHandler = RotatingFileHandler(filename=LOG_FILENAME, maxBytes=5000000, backupCount=5, encoding="utf-8")
fileHandler.setLevel(logging.DEBUG)
fileHandler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.getLogger("").addHandler(fileHandler)


from generator.generator import MemoryGenerator

if __name__ == "__main__":
  
  #############################################################################
  # Setup arguments
  #############################################################################
  
  # parser
  parser = argparse.ArgumentParser()
  
  # arguments
  parser.add_argument(metavar="config-file", type=str, dest="configFile",
                      help="YAML configuration file")
  parser.add_argument(metavar="function-file", type=str, dest="functionFile",
                      help="Python file with the user function to implement")
  
  # optional arguments
  parser.add_argument("--working-dir", type=str, dest="workingDir",
                      help="Directory to store generated files")
  parser.set_defaults(workingDir=rootDirectory)
  parser.add_argument("--suppress-confirmation", action="store_true", dest="suppressConfirmation",
                      help="Suppress the intital creation confirmation")
  parser.set_defaults(verbose=False)
  parser.add_argument("--verbose", action="store_true",
                      help="Turn on verbose mode")
  parser.set_defaults(verbose=False)
  
  #############################################################################
  # Process arguments
  #############################################################################
  
  # parse the arguments
  args = parser.parse_args()
  
  # Setup console logger
  #  -verbose turns on DEBUG messages
  console = logging.StreamHandler()
  console.setLevel(logging.DEBUG if args.verbose else logging.INFO)
  console.setFormatter(logging.Formatter("%(message)s"))
  logging.getLogger("").addHandler(console)
  logger = logging.getLogger(__name__)
  
  # CHECK: make sure the config file exists
  if not os.path.isfile(args.configFile):
    logger.error("ERROR: Config file not found at: {}".format(args.configFile))
    sys.exit(1)

  # CHECK: make sure the user function file exists
  if not os.path.isfile(args.functionFile):
    logger.error("ERROR: Function file not found at: {}".format(args.functionFile))
    sys.exit(1)
  
  # CHECK: make sure the working directory exists
  if not os.path.isdir(args.workingDir):
    logger.error("ERROR: Working directory not found at: {}".format(args.workingDir))
    sys.exit(1)
  
  #############################################################################
  # Perform operation
  #############################################################################
  
    
  # generate the memory
  gen = MemoryGenerator(
    workingDir   = args.workingDir,
    configFile   = args.configFile,
    functionFile = args.functionFile
  )

  gen.generate(suppressConfirmation=args.suppressConfirmation)
  logger.info("Generation process complete")
  sys.exit(0)

