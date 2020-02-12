# liteServer
Very Lightweight Process Variable Server. The basic principle is similar to the 
pvAccess protocol of EPICS. It hosts Lite Data Objects (LDO, analog of process variables in EPICS) and provides 
info/set/get/read/subscribe remote access to them using UDP protocol. 
Data encoding is implemented using UBJSON specification, which makes it very 
fast and efficient.

User responsibility is to provide private methods for connecting process variables to physical devices.

### Motivation
Provide control for devices connected to non-linux machines. 
The simplicity of the protocol makes it possible to implement in CPU-less FPGA device.

The server is running on a remote machine. Device parameters can be 
manipulated using liteAccess.py.

The liteAccess.py is the base class for accessing the server parameters.

### Bridged usage
To monitor and control liteServer-served devices from an existing architecture one can use or build a simple bridge:
#### For RHIC ADO Control architecture: liteServerMan.py
    liteServerMan.py -HmyHost myADO 
An ADO manager liteServerMan.py connects to a liteServer, running on myHost and creates the myADO. 
  - all input objects of the liteServer are translated to myADO input parameters
  - all output parameters of the myADO are translated to the liteServer objects
#### For EPICS Control architecture
The bridge liteServer-EPICS can be developed using a python-based implementation of IOC, for example:
[caproto](https://nsls-ii.github.io/caproto/)

### Features
 - Simplicity. The network protocol is **UDP**, error correction of late/missing/mangled data is
implemented. The serialization protocol is **UBJSON**: binary, easier than RPC, provides all JSON features. All this makes it possible to implement liteServer on a CPU-less FPGA.
 - Low latency, connection-less.
 - Supported requests:
   - **info()**, returns dictionary with information on requested LDOs and parameters
   - **get()**, returns dictionary of values of requested LDOs and parameters
   - **read()**, returns dictionary of all readable (non-constant) parameters of requested LDO
   - **set()**, set values or attributes of requested LDO parameters
   - **subscribe()** (not commissioned yet)
 - Multidimensional data (numpy arrays) are supported.
 - Access control info (username, program name) supplied in every request
 - Name service
   - file-based
   - network-based using a dedicated liteServer  (not commissioned yet)
 - Basic spreadsheet-based GUI: **ldoPet.py**
 - Architectures. All programs are 100% python. Tested on Linux and Windows.
 - Supported applications:
   - [Image analysis](https://github.com/ASukhanov/Imagin)

### Status
Commissioning of the second release.

## Examples
### liteScaler.py
Test server, providing two multi-channel scalers and a multi-dimesional array.
  To start the server:
  
    litescaler.py
  To show and control liteScaler parameters using pre-configured spreadsheet liteScaler.yaml:

    ldoPet.py -f liteScaler.yaml
  
