# liteserv
Very Lightweight Data Object Server. 
It hosts Lite Data Objects (**LDO**, analog of process variables in 
EPICS) and provides info/set/get/read/subscribe remote access to them using 
UDP protocol. Data encoding is implemented using UBJSON specification, 
which makes it very fast and efficient.

### Data logging and retrieving
Data objects can be logged and retrieved using an **apstrim** package (https://pypi.org/project/apstrim).

### Bridged usage
To monitor and control liteserv-served devices from an existing architecture 
one can use or build a simple bridge:
##### A bridge for RHIC ADO Control architecture is liteServerMan.py
    liteServerMan.py -HmyHost myADO.
An ADO manager liteServerMan.py connects to a liteServer, running on myHost and 
creates the myADO. 
  - All input LDOs are translated to myADO input parameters.
  - All output parameters of the myADO are translated to LDOs.

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
   - [Data Logger](https://github.com/ASukhanov/apstrim)

### Key Components
- **liteServer**: Module for building liteServer applications.
- **liteAccess**: Module for for accessing the Process Variables from a liteServer.
- **liteCNS.py**: Name service module, it provides file-based (**liteCNS.yaml**) or network-based name service (**liteCNSserver.py**).

### Supportted devices
Server implementations for various devices are located in .device sub-package. 
A device server can be started using following command:

    python3 -m liteserv.device.<deviceName> <Arguments>

- **device.liteScaler**: test implementation of the liteServer
, supporting 1000 of up/down counters as well as multi-dimensional arrays.
- **device.litePeakSimulator**: Waveform simulator with multiple peaks and
a background noise.
- **device.liteVGM**: Server for multiple gaussmeters from AlphaLab Inc.
- **device.liteUSBCam**: Server for USB cameras.
- **device.liteUvcCam**: Server for USB cameras using UVC library, allows for 
pan, zoom and tilt control.
- **device.liteWLM**: Server for Wavelength Meter WS6-600 from HighFinesse.
- **device.liteLabjack**: LabJack U3 analog and digital IO module.
- **device.senstation**: Server for various devices, connected to Raspberry Pi
GPIOs: 1-wire temperature sensor, Pulse Counter, Fire alarm and Spark detector,
Buzzer, RGB LED indicator, OmegaBus serial sensors. Coming soon: NUCLEO-STM33 
mixed signal MCU boards, connected to Raspberry Pi over USB.
- **device.liteGQ**: Geiger Counter and a gyro sensor GMC-500 from GQ Electronics.

### Installation
Python3 should be 3.6 or higher.

    python3 pip install liteserver

Additional libraries may be required for specific devices.

## Examples
Most convenient way to test base class functionality is by using **ipython3**, 

Start a server liteScaler on a local host:

    python3 -m liteserver.device.liteScaler -ilo -s2
    ipython3

```python
from liteserver import liteAccess as LA 
from pprint import pprint

Host = 'localhost'
LAserver = Host+':server'
LAdev1   = Host+':dev1'
LAdev2   = Host+':dev2'

#``````````````````Programmatic way, using Access`````````````````````````````
# Advantage: The previuosly created PVs are reused.
list(LA.Access.info((Host+':*','*')))# list of all devices on the Host
LA.Access.info((LAserver,'*'))
LA.Access.get((LAserver,'*'))
LA.Access.set((LAdev1,'frequency',[2.0]))
LA.Access.subscribe(LA.testCallback,(LAdev1,'cycle'))
LA.Access.unsubscribe()
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,	
#``````````````````Object-oriented way````````````````````````````````````````
allServerParameters = LA.PVs((LAserver,'*'))
pprint(allServerParameters.info())
pprint(allServerParameters.get())# get all parameters from device LAserver
# get all readable parameters from device Scaler1:server, which have been 
# modified since the last read:
pprint(allServerParameters.read())

allDev1Parameters = LA.PVs((LAdev1,'*'))
print(allDev1Parameter.info())

server_performance = LA.PVs((LAserver,'perf'))
pprint(server_performance.info())
pprint(server_performance.get())
# simplified get: returns (value,timestamp) of a parameter 'perf' 
pprint(server_performance.value)

server_multiple_parameters = LA.PVs((LAserver,('perf','run')))
pprint(server_multiple_parameters.info())
pprint(server_multiple_parameters.get())

server_multiple_devPars = LA.PVs((LAdev1,('time','frequency')),(LAserver,('statistics','perf')))
pprint(server_multiple_devPars.get())

# setting
dev1_frequency = LA.PVs((LAdev1,'frequency'))
dev1_frequency.set([1.5])
dev1_frequency.value
dev1_multiple_parameters = LA.PVs([LAdev1,('frequency','coordinate')])
dev1_multiple_parameters.set([8.,[3.,4.]])

# subscribing
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
# To enable debugging: LA.PVs.Dbg = True
# To enable transaction timing: LA.Channel.Perf = True
```
