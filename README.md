# liteServer
Very Lightweight Process Variable Server. The basic principle is similar to the 
pvAccess protocol of EPICS. It hosts the process variables and provides 
set/get/monitor remote access to process variables using UDP protocol. 
Data encoding is implemented using UBJSON specification, which makes it very 
fast and efficient.

User responsibility is to provide private methods for connecting process variables to physical devices.

## Motivation
Provide control for devices connected to non-linux machines. 
The simplicity of the protocol makes it possible to implemente it in FPGA on a cpu-less device.

The server is running on the remote machine. Device parameters can be 
manipulated using liteAccess.py.

The liteAccess.py is the base class for accessing the server parameters.

## Status
Released

### Examples
- liteScaler.py # server for 2 devices 
- liteAccess.py -i :: # list of supported devices on local host
- liteAccess.py -i "192.168.1.0;9700:: # list of devices, served by a liteServer with IP adrress 192.168.1.0 at port 9700
- liteAccess.py -i :dev1: # list of parameters of dev1, served by a liteServer  on local host
- liteAccess.py -i :dev1:counters # list of features of parameter dev1:counters
- liteAccess.py ":dev1:frequency" ":dev2:frequency"# print frequencies of dev1 and dev2
- liteAccess.py ":dev1:frequency=2" ":dev2:frequency=3"# set frequencies of dev1 and dev2

