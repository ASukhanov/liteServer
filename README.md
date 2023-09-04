# liteserver 3.1.0
Very Lightweight Data Object Server. 
It hosts Lite Data Objects (**LDO**, analog of Process Variables in 
EPICS) and provides info/set/get/read/subscribe remote access to them using 
UDP protocol. Data encoding is implemented using **CBOR** specification, 
which makes it very fast and efficient.

### Data logging and retrieving
Data objects can be logged and retrieved using an **apstrim** package (https://pypi.org/project/apstrim).

### Features
 - Simplicity. The network protocol is **UDP**, error correction of 
late/missing/mangled data is implemented. Binary serialization protocol **CBOR**. 
Programming interface is very similar to JSON.
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
 - Basic spreadsheet-based GUI: **pypeto**
 - Architectures. All programs are 100% python. Tested on Linux and partially on Windows.
 - Companion applications:
   - [liteAccess: Access to liteServer's](https://pypi.org/project/liteaccess)
   - [pvplot: Dynamic plotting tool](https://pypi.org/project/pvplot)
   - [apstrim: Data Logger](https://pypi.org/project/apstrim)
   - [Imagin: Image analysis](https://github.com/ASukhanov/Imagin) 

### Supported devices
Server implementations for various devices are located in .device sub-package. 
A device server can be started using following command:<br>
    python3 -m liteserv.device.<deviceName> <Arguments>

- **device.litePeakSimulator**: Waveform simulator with multiple peaks and a background noise.
- **device.liteScaler**: Test implementation of the liteServer, 
supporting 1000 of up/down counters as well as multi-dimensional arrays.
- **device.senstation**: Server for various devices, connected to Raspberry Pi
GPIOs: 1-wire temperature sensor, Pulse Counter, Fire alarm and Spark detector,
Buzzer, RGB LED indicator, OmegaBus serial sensors. 
Various I2C devices: ADC: ADS1x15, Magnetometers: MMC5983MA, HMC5883, QMC5983, 
TLV493D.
I2C multiplexing using TCA9548 or PCA9546.
NUCLEO-STM33 mixed signal MCU boards, connected to Raspberry Pi over USB.
- **device.liteGQ**: Geiger Counter and a gyro sensor GMC-500 from GQ Electronics.
- **device.liteWLM**: Wavelength Meter WS6-600 from HighFinesse.
- **device.liteLabjack**: LabJack U3 analog and digital IO module.
- **device.liteUSBCam**: Server for USB cameras.
- **device.liteUvcCam**: Server for USB cameras using UVC library.
- **device.liteVGM**: (Obsolete) Server for multiple gaussmeters from AlphaLab Inc.

## Installation

### Dependencies:
- Python3 3.6 or higher.
- [CBOR2](https://pypi.org/project/cbor2/)

### Installation:<br>
```python3 -m pip install liteserver```

Additional libraries may be required for specific devices.

## Examples
Most convenient way to test a base class functionality is by using **ipython3**, 

#### Test server: liteScaler
Start liteScaler on a local host:<br>
```python -m liteserver.device.liteScaler -ilo```<br>
To monitor, use:<br>
```python -m pvplot L:localhost:dev1:counters```

#### Peak simulator
```python -m liteserver.device.litePeakSimulator -ilo```<br>
To monitor, use:<br>
```python -m pvplot -s.01 -a'L:localhost:dev1' 'x,y'```

#### Labjack U3-HV
```python -m liteserver.device.liteLabjack -ilo```<br>
To monitor, use:<br>
```python -m pvplot -a'L:localhost:dev1' 'tempU3 ADC_HV[0] ADC_HV[1] ADC_HV[2] ADC_HV[3] ADC_LV'```

### Server for all supported peripherals: senstation:
#### I2C Support
To detect available devices on the multiplexed I2C chain:<br>
```python -m utils.i2cmux -M 112```<br>
If multiplexer address on your board is not 112, you can find it using:<br>
```i2cdetect -y 1```

#### Start the senstation server
Start the senstation server through default network interface:<br>
```python -m liteserver.device.senstation```

#### Interfacing to senstation using python
```python
from liteserver import liteAccess as LA 
from pprint import pprint

Host = 'localhost'
LAserver = Host+':server'
LAdev1   = Host+':dev1'
LAdev2   = Host+':dev2'

#``````````````````Programmatic way, using Access`````````````````````````````
LA.Access.info((Host+':*','*'))# map of all devices and parameters the Host
LA.Access.info((LAserver,'*'))
LA.Access.get((LAserver,'*'))
LA.Access.set((LAdev1,'frequency',2.0))
LA.Access.subscribe(LA.testCallback,(LAdev1,'cycle'))
LA.Access.unsubscribe()
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,	
#``````````````````Object-oriented way````````````````````````````````````````
# Advantage: The previuosly created PVs are reused.
allServerParameters = LA.PVs((LAserver,'*'))
pprint(allServerParameters.info())
pprint(allServerParameters.get())# get all parameters from device LAserver
# get all readable parameters from device Scaler1:server, which have been 
# modified since the last read:
pprint(allServerParameters.read())

allDev1Parameters = LA.PVs((LAdev1,'*'))
print(allDev1Parameters.info())

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
Timing of Access.get using ipython on localhost.
    from liteserver import liteAccess as LA
    Host='localhost'
    LAdev1   = Host+':dev1'
    %timeit image = LA.Access.get((LAdev1,['image']))
    145 µs ± 1.95 µs per loop (mean ± std. dev. of 7 runs, 10000 loops each)
    image[(LAdev1,'image')]['value'].shape
    (120, 160, 3)
Retrieving time of 57600 values (120*160*3) is 145 µs,
which corresponds to 400 mValues/s

Retrieving time of 57600 values (120*160*3) 220 µs,
which corresponds to 260 MValues/s (on entry-level workstation). 
It was 400 MValues/s on top-level workstation.
Note: Msgpack was 4% faster.
#``````````````````Tips```````````````````````````````````````````````````````
# To enable debugging: LA.PVs.Dbg = True
# To enable transaction timing: LA.Channel.Perf = True
```
