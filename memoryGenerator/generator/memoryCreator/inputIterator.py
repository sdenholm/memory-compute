import math
from mpmath import mp

# default logging level is info
import logging
logger = logging.getLogger(__name__)

class Converter:
  """
  # 8-bit EX:
  eWidth = 4
  mWidth = 3
  bias   = 2**(eWidth-1)-1
  eMin   = -1 * (2**(eWidth-1)-2)
  
  # binary: s-e0-e1-e2-e3-m0-m1-m2
  
  s, e, m0, m1, m2 = (0, 0, 0,1,0)
  
  if e == 0:
      res = -1**(s) *  2**(eMin)   * (0 + (m0/(2**1)) + (m1/(2**2)) + (m2/(2**3)))
  else:
      res = -1**(s) *  2**(e-bias) * (1 + (m0/(2**1)) + (m1/(2**2)) + (m2/(2**3)))
  """
  
  def __init__(self, width, precision):
    """
    :param width:     (int) total number width
    :param precision: (int) precision of number
    """
    
    self.width     = width
    self.precision = precision
    
    # width of exponent section
    self.expWidth = width - precision
  
    self.expShift  = precision-1
    self.signShift = width-1
    
    # assemble the masks for isolating the exponent and mantissa sections
    self.expMask  = ((2**self.expWidth) -1) << self.expShift
    self.manMask  = 2**(precision-1) - 1
    self.signMask = 1 << self.signShift
    
    # smallest value exp can be at this width
    self.minExp = -1 * (2**(self.expWidth-1)-2)
    
    # exponent bias
    self.expBias = 2**(self.expWidth-1)-1
    
    # exceptions
    #  +inf: sign 0, exponents all 1, mantissa all 0
    #  -inf: sign 1, exponents all 1, mantissa all 0
    self.decimalInf  = self.expMask
    self.decimalNinf = self.expMask + self.signMask


  def _isNaN(self, x):
    """
    # NaN if: any sign, exponents all 1, mantissa > 0
    #
    :param x:
    :return:
    """
    expVal = (x & self.expMask)
    return (expVal == self.expMask) & ((x & self.manMask) > 0)
    
  
  def floatToIntRep(self, val):
    """
    # Convert float to bit string (in integer format)
    #
    :param val:
    :return:
    """

    if val == 0:
      return 0
    
    # convert the value to an mp fraction and extract the raw mantissa and exponent
    with mp.workprec(self.precision):
      mpVal = mp.mpmathify(val)
      #man, exp = math.frexp(mp.mpf(val))
      man, exp = math.frexp(mpVal)
      
    # if we're dealing with denormalised values
    expValueDiff = self.minExp - exp
    if exp <= self.minExp:
      
      # adjust the exponent and mantissa
      exp = self.minExp # to cancel out
      if man > 0:
        man = (man/2**(expValueDiff+1)) + 0.5
      else:
        man = (man/2**(expValueDiff+1)) - 0.5
        
        
    # convert the exponent to a binary int
    #expInt = exp + 2 ** (self.expWidth - 1) - 1 - 1
    expInt = exp + self.expBias - 1
    
    # iteratively subtract fractions to determine the mantissa
    recMan = abs(man) * 2
    
    manInt = 0
    for i in range(1, self.precision):
      op = 1 / (2**i)
      if recMan - op >= 1:
        manInt += 2**(self.precision-i-1)
        recMan -= op
    
    # assemble the exponent integer, mantissa integer, and set the sign
    result = (expInt << (self.precision-1)) + manInt
    if val < 0:
      result += self.signMask
    
    return result
  
  
  
  def intRepToFloat(self, val):
    """
    # Convert bit string (in integer format) to a float
    #
    :param val:
    :return:
    """
    
    # special case: 0
    if val == 0:
      return mp.mpf("0", prec=self.precision)

    # special case: -0
    elif val == self.signMask:
      return mp.mpf("-0", prec=self.precision)
    
    # special case -inf or NaN
    elif (val & self.decimalNinf) == self.decimalNinf:
      if self._isNaN(val):
        return mp.mpf("nan", prec=self.precision)
      else:
        return mp.mpf("-inf", prec=self.precision)
    
    # special case +inf or NaN
    elif (val & self.decimalInf) == self.decimalInf:
      if self._isNaN(val):
        return mp.mpf("nan", prec=self.precision)
      else:
        return mp.mpf("inf", prec=self.precision)
    
    
    # isolate the sign, exp and mantissa sections
    expPart = (val & self.expMask) >> self.expShift
    manPart = val & self.manMask
    isNeg   = (val & self.signMask) > 1
    
    # convert the mantissa to binary string so we can process each bit in turn
    manBin = format(manPart, "#0{}b".format(self.precision-1+2))[2:]

    # mantissa = (b[0]/2**1) + (b[1]/2**2) + (b[2]/2**3) + ...
    manVal = 0
    for i, v in enumerate(manBin):
      if v == "1":
        manVal += 1.0 / 2**(i+1)
    
    
    # normal floating point
    if expPart > 0:
      
      # exp = 2*<exp val> - <half way point>
      #expVal = 2 ** (expPart - (2 ** (self.expWidth - 1) - 1))
      expVal = 2 ** (expPart - self.expBias)
      
      # mantissa has leading 1
      manVal += 1

    # we're dealing with denormalised numbers
    else:
      
      # exp = 2**<half way point> - 2
      #expVal = 2**(-2**(self.expWidth-1) + 2)
      expVal  = 2 ** (-(self.expBias-1))
    
    # negate or not
    if isNeg:
      result = -1 * expVal * manVal
    else:
      result = expVal * manVal

    # set precision level to store final value
    with mp.workprec(self.precision):
      result = mp.mpmathify(result)
    return result


class Iterators:
  """
  # All iterators must start at 0 and iterate up to 2**totalWidth
  #   -e.g., for 4-bits: "0001", "0010", "0011", "0100", etc
  # Iterator then converts this bit-string to whatever format we need
  #  -uint:  straight-forward 0 to 2**N
  #  -int:   -2**(N-1) to +2**(N-1)
  #  -float: converted to IEEE float for a given bit-string
  """
  
  SUPPORTED_TYPES = ["float", "int", "uint"]

  

  @staticmethod
  def _nestedArgInterator(argList, currentArgVals=None):
    """
    # Create a nested iterator for each width
    #
    :param argList:        (list) of argument info
    :param currentArgVals: <used for recursion>
    :return:
    """
  
    if currentArgVals is None:
      currentArgVals = {}

    iterLen = len(argList)
    
    # should have at least one argument to iterate over
    if iterLen == 0:
      raise ValueError("No arguments given")

    # find max value held with this width
    maxValue = 2 ** argList[0]["width"]

    # midway point where signed ints turn negative
    midValue = 2 ** (argList[0]["width"] - 1)
    
    # instantiate the converter if needed
    if argList[0]["type"] == "float":
      converter = Converter(width=argList[0]["width"], precision=argList[0]["precision"])
    else:
      converter = None
    
    convert = {
      "uint":  lambda val: val,
      "int":   lambda val: val - maxValue if val >= midValue else val,
      "float": lambda val: converter.intRepToFloat(val)
    }
    
    # if there are multiple arguments, iterate the first and nest
    # the remaining ones
    if iterLen > 1:
      for x in range(maxValue):
        
        # convert the value to the input type
        x = convert[argList[0]["type"]](x)
        
        # add to arguments
        currentArgVals.update({argList[0]["name"]: x})

        yield from Iterators._nestedArgInterator(argList[1:], currentArgVals)
  
    # last iterator
    else:
      for x in range(maxValue):
        
        # convert the value to the input type
        x = convert[argList[0]["type"]](x)
  
        # add to arguments
        currentArgVals.update({argList[0]["name"]: x})
        
        yield currentArgVals


        
  
  @staticmethod
  def iterator(functionDict, func):
    """
    # Iterate over every possible argument input combination.
    #  -Note: Each input must start at 0b000...000 and iterate upwards as this
    #   is the first address in memory.
    #
    :param functionDict: (dict) function information from the config file
    :param func:         (fn)   reference to the python user function
    :return:
    """
    
    if functionDict["output-type"] not in ["int", "uint", "float"]:
      raise ValueError("Unknown output type: {}".format(functionDict["output-type"]))
    
    # enforce maximum bit-width for the output value
    outputMask = (2 ** functionDict["output-width"]) - 1
    
    # instantiate the output converter if needed
    if functionDict["output-type"] == "float":
      converter = Converter(width=functionDict["output-width"], precision=functionDict["output-precision"])
    else:
      converter = None

    # loop over all possible inputs starting from bx0
    for i, ipKwargs in enumerate(Iterators._nestedArgInterator(functionDict["arguments"])):
      
      # call function
      result = func(**ipKwargs)
      
      # keep function output for warning message
      preConvResult = result
      
      # convert floats
      if functionDict["output-type"] == "float":
        result = converter.floatToIntRep(result)
      
      # generate a warning if the function result is too large
      if result > outputMask:
        logger.warning("WARNING: Output {} overflowed (max = {})".format(preConvResult, outputMask))
      
      yield result & outputMask
    
    