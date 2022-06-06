# Memory Compute

This is an automated tool for FPGA development that turns Python functions into memory-compute cores, implemented in Verilog.



---
## Memory-based Computing


Instead of using traditional logic to implement a function, we instead pre-compute all the function's possible values, store them in FPGA memory, then access them at runtime. The memory is loaded onto the FPGA during initial configuration, and the architecture we provide allows the user to treat these memory-compute units like any other Verilog module.

We can "call" our implemented function at runtime by reading the data out of memory. As our architecture parallelises memory accesses to the memory's underlying block RAMs, we can serve multiple function calls at once.


---
## Installation

This tool requires Python 3.6 or above, and while the automated scripts we generate were designed around Vivado 2019.2, other versions of Vivado should also work. Please let me know if there are any issues.

First, get the tool from GitHub using:
```bash
git clone https://github.com/sdenholm/memory-compute.git
```

The Python packages we need to install are given in the __requirements.txt__ file. This can be done using any Python package manager, like __pip__. From within the memory-compute directory we would run:
```bash
pip3 install -r requirements.txt
```

---
## Creating Your Python Function


The Python function's output must be based solely on its inputs. Apart from that, it can be anything. 

Our automated tool will brute-force every possible input and record the output. What happens within the function is completely ignored. The user can create new variables, convert the input variable(s), call other functions, etc. Only the final output value is recorded.

For variable types, we support both signed and unsigned integers, as well as arbitrary precision floating point numbers.


### Function Configuration File

The user writes their function in a traditional Python file, and separately defines its parameters in the configuration file.

An example implementation of the tanh(x) function:
```python
def tanh(x):
  import numpy as np
  xNumpyFloat = np.float16(x)
  return np.tanh(xNumpyFloat)
```

An example configuration file that describes this function:
```yaml
---
vivado-project-directory: "/path/to/vivado_project_dir"
function:
  name: "tanh"
  arguments:
    - name:      x
      type:      float
      width:     16
      precision: 11
  output-width:     16
  output-type:      float
  output-precision: 11
```

The Vivado project directory is needed to create the scripts that build the memory-compute unit's block RAMs. This must be set to the directory of the user's Vivado project, i.e., where the Vivado xpr project file is located.

The details of the function definition are given below.


#### Defining the Function

The function name must match the name of the user's Python function, while the argument names must match those of the function arguments.

Inputs and outputs:
- there can only be one output 
- there is no maximum number of inputs, but there must be at least one
- type must be one of: "int", "uint", or "float"
  - floats must also specify their precision 

Floating point numbers are presented to the user function as [mpmath](http://mpmath.org) representations. These inputs can be converted freely to native Python floats, NumPy floats---as shown in the above example--or to any other format.

As the tanh(x) example above specifies a 16-bit float with 11-bits of precision, its representation within the FPGA will conform to the IEEE-754 standard for half-precision numbers.

Signed and unsigned numbers are presented as standard python integers.

---
## Examples


Three examples are provided in the __examples__ directory. They include the __tanh__ example above, a __4-bit multiplier__, and finally an __arbitrary function__ to show how to use mixed types.


### Worked Example: 4-bit Multiplier

The 4-bit multiplier takes two 4-bit unsigned integers and outputs the unsigned 8-bit product. The configuration file, user function file, and a Verilog testbench are provided in the __examples__ directory.


#### The Configuration and Function Files

The configuration file for our multiplier, examples/configFile_mult.yaml:
```yaml
---
vivado-project-directory: "/path/to/vivado_project_dir"
function:
  name: "mult"
  arguments:
    - name:  x
      type:  uint
      width: 4
    - name:  y
      type:  uint
      width: 4
  output-width: 8
  output-type:  uint
```

The user function in examples/function.py:
```python
def mult(x, y):
  return x * y
```


#### Creating the Memory-Compute Files

In the memory-compute directory run:
```bash
python3 memoryGenerator examples/configFile_mult.yaml examples/function.py
```

The tool will parse the configuration and function files, presenting a brief description of the memory resources required.

The user then confirms they wish to proceed, at which point the tool will:
- iterate though all possible input values for the user function to obtain the corresponding outputs
- create initialisation files for each block RAM sub-memory
- wrap the memories inside our memory-compute framework, so everything appears to the user as a single Verilog module
- create a tcl script with commands to synthesise the memories within Vivado

The output files will be written into a directory called---in the case of this example---__mult_8b_8b__.


#### Within Vivado

The tcl script we just generated can now be directly called within Vivado, either as part of a command line, or from within the GUI:
```
source /path/to/file.tcl
```

Synthesis typically takes about 2-5 minutes per block RAM, for which this example only has one.

Adding the __memory_compute.v__ and __memory_compute_sub_memory.v__ files to your project will wrap the newly built memory into a standard Verilog interface.

By instantiating the __memory_compute.v__ module you can specify how many parallel function calls you want to have. The number of parallel function calls must be:
- a power of two, i.e., 2, 4, 8, 16, etc
- greater than or equal to two, as the block RAM's dual read ports make this the minimum number

A Verilog testbench is provided in the __examples__ directory to show how the memory-compute core can be accessed, and gives some example function calls.


### Example of Arbitrary Inputs

Using memory-compute cores means computation is now just a read to memory. We can therefore mix and match computation and look-up tables. Below is a function with two inputs: a 2-bit selector and a 12-bit floating point variable.

This example uses an unsigned integer to select the type of function to perform, and which pre-defined constant to use. In this way, we can control the use of different function configurations at runtime, e.g., selecting different filters, data formatting, etc.
 
Configuration file, examples/configFile_arb.yaml:
```yaml
---
vivado-project-directory: "/path/to/vivado_project_dir"
function:
  name: "arb"
  arguments:
    - name:  select
      type:  uint
      width: 2
    - name:  value
      type:  float
      width: 12
      precision: 7
  output-width:     16
  output-type:      float
  output-precision: 11
```

User function in examples/function.py:
```python
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
```
