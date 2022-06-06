
def mult(x, y):
  return x * y

def tanh(x):
  import numpy as np
  return np.tanh(np.float16(x))

def arb(select, value):
  import numpy as np
  
  if select == 0:
    return np.sin(value)
  elif select == 1:
    return np.cos(value)
  elif select == 2:
    someConstant = 112358
    return np.tan(value) + someConstant
  else:
    someOtherConstant = 314159
    return np.tan(value) + someOtherConstant