# liteServer
Very Lightweight Data Object Server. 
It hosts Lite Data Objects (**LDO**, analog of process variables in 
EPICS) and provides info/set/get/read/subscribe remote access to them using 
UDP protocol. Data encoding is implemented using UBJSON specification, 
which makes it very fast and efficient.

### Motivation
- Provide control for devices connected to non-linux machines. 
- The simplicity of the protocol makes it possible to implement in CPU-less FPGA device.
- The server is running on a remote machine. Device parameters can be 
manipulated using liteAccess.py.
The liteAccess.py is the base class for accessing the server parameters.

### Bridged usage
To monitor and control liteServer-served devices from an existing architecture 
one can use or build a simple bridge:
##### A bridge for RHIC ADO Control architecture is liteServerMan.py
    liteServerMan.py -HmyHost myADO 
An ADO manager liteServerMan.py connects to a liteServer, running on myHost and 
creates the myADO. 
  - all input objects of the liteServer are translated to myADO input parameters
  - all output parameters of the myADO are translated to the liteServer objects

##### For EPICS Control architecture
The bridge liteServer-EPICS can be developed using a python-based implementation of IOC, for example:
[caproto](https://nsls-ii.github.io/caproto/)

### Features
 - Simplicity. The network protocol is **UDP**, error correction of 
late/missing/mangled data is
implemented. The serialization protocol is **UBJSON**: binary, easier than RPC, 
provides all JSON features. All this makes it possible to implement liteServer 
on a CPU-less FPGA.
 - Low latency, connection-less.
 - Supported requests:
   - **info()**, returns dictionary with information on requested LDOs and 
   parameters
   - **get()**, returns dictionary of values of requested LDOs and parameters
   - **read()**, returns dictionary of changed readable (non-constant) 
   parameters of requested LDOs
   - **set()**, set values or attributes of requested LDO parameters
   - **subscribe(callback)**, subscribe to a set of the objects, if any object 
of the requested LDOs have been changed, the server will publish the changed 
objects to client and the callback function on the client will be invoked.
 - Multidimensional data (numpy arrays) are supported.
 - Access control info (username, program name) supplied in every request
 - Name service
   - file-based
   - network-based using a dedicated liteServer  (not commissioned yet)
 - Basic spreadsheet-based GUI: **pypet**
 - Architectures. All programs are 100% python. Tested on Linux and Windows.
 - Supported applications:
   - [Image analysis](https://github.com/ASukhanov/Imagin)

### Installation
Prerequisites:
 - **python3**: preferrably python3.6+ (it keeps dictionaries sorted)
 - **py-ubjson**: versions 0.12+ provides greatly improved performance for multi-dimensional arrays
 - **pyQT5**: for GUI
 - **opencv-python**: for liteUSBCam

### Key Components
- **liteServer**: Module, providing classes Server, Device and LDO for building
liteServer application.
- **liteAccess.py**: Module for for accessing the Process Variables.
- **liteCNS.py**:    lite name service module, provides file-based (**liteCNS.yaml**) or network-based name service (**liteCNSserver.py**).

### Supportted devices
Server implementation for various devices are located in .device sub-module. 

- **device.liteScaler**: test implementation of the liteServer
, supporting 1000 of up/down counters as well as multi-dimensional arrays.
- **device.litePeakSimulator**: Waveforf simulator with multiple peaks and
a background noise.
- **device.liteVGM**: Server for multiple gaussmeters from AlphaLab Inc.
- **device.liteUSBCam**: Server for USB camera.
- **device.liteUvcCam**: Server for USB camera using UVC library, allows for 
pan, zoom and tilt control.
- **device.liteWLM**: Server for Wavelength Meter WS6-600 from HighFinesse.
- **device.senstation**: Server for various devices, connected to Raspberry Pi
GPIOs: 1-wire temperature sensor, Pulse Counter, Fire alarm and Spark detector,
Buzzer, RGB LED indicator, OmegaBus serial sensors. Coming soon: NUCLEO-STM33 
mixed signal MCU boards, connected to Raspberry Pi.

### Status
Revision 4 released.

## Examples
Most convenient way to test base class functionality is by using **ipython3**, 
```python
#``````````````````Usage:`````````````````````````````````````````````````````
Start a server liteScaler on a local host:
python3 -m device.liteScaler -ilo

ipython3
from liteAccess import liteAccess as LA 
from pprint import pprint

Host = 'localhost'
LAserver = Host+':server'
LAdev1   = Host+':dev1'
LAdev2   = Host+':dev2'

#``````````````````Programmatic way, using Access`````````````````````````````
# Advantage: The previuosly created PVs are reused.
LA.Access.info((LAserver,'*'))
LA.Access.get((LAserver,'*'))
LA.Access.subscribe(LA.testCallback,(LAdev1,'cycle'))
LA.Access.subscribe(LA.testCallback,(LAdev2,'time'))
LA.Access.unsubscribe()
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,	
#``````````````````Object-oriented way````````````````````````````````````````
    #``````````````Info```````````````````````````````````````````````````````
    # list of all devices on a Host
print(list(LA.PVs((Host+':*','*')).info()))
    # info on all parameters of a device
pprint(LA.PVs((LAserver,'*')).info())
print(LA.PVs((LAdev1,'*')).info())
# info on single parameter
pprint(LA.PVs((LAserver,'run')).info())
    # info on multiple parameters
pprint(LA.PVs((LAserver,('perf','run'))).info())
    #``````````````Get```````````````````````````````````````````````````````
    # get all parameters from device LAserver
pprint(LA.PVs((LAserver,'*')).get())
    # get single parameter from device:
pprint(LA.PVs((LAserver,    'perf')).get())
    # simplified get: returns (value,timestamp) of a parameter 'perf' 
pprint(LA.PVs((LAserver,    'perf')).value)
    # get multiple parameters from device: 
pprint(LA.PVs((LAserver,('perf','run'))).get())
    # get multiple parameters from multiple devices 
#DNW#pprint(LA.PVs((LAdev1,('time','frequency')),(LAdev2,('time','coordinate'))).get())
    #``````````````Read```````````````````````````````````````````````````````
    # get all readable parameters from device Scaler1:server, which have been modified since the last read
print(LA.PVs((LAserver,'*')).read())
    #``````````````Set````````````````````````````````````````````````````````
    # simplified set, for single parameter:
LA.PVs((LAdev1,'frequency')).value = [1.1]
    # explicit set, could be used for multiple parameters:
LA.PVs((LAdev1,'frequency')).set([1.1])
print(LA.PVs((LAdev1,'frequency')).value)
    # multiple set
LA.PVs((LAdev1,('frequency','coordinate'))).set([8.,[3.,4.]])
pprint(LA.PVs([LAdev1,('frequency','coordinate')]).get())
    #``````````````Subscribe``````````````````````````````````````````````````
ldo = LA.PVs([LAdev1,'cycle'])
ldo.subscribe()# it will print image data periodically
ldo.unsubscribe()# cancel the subscruption

# test for timeout, should timeout in 10s:
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#``````````````````Observations```````````````````````````````````````````````
    # Measured transaction time is 1.8ms for:
LA.PVs([[['Scaler1','dev1'],['frequency','command']]]).get()
    # Measured transaction time is 6.4ms per 61 KBytes for:
LA.PVs([[['Scaler1','dev1'],'*']]).read() 
#``````````````````Tips```````````````````````````````````````````````````````
To enable debugging: LA.PVs.Dbg = True
To enable transaction timing: LA.Channel.Perf = True
```
