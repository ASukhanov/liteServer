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
- liteScalerMan.py # server for 10 scalers with individual increments
- liteAccess.py -l # list of supported devices
- liteAccess.py -l dev1 # list of parameters of dev1
- liteAccess.py -l dev1:counters # list of features of parameter dev1:counters
- liteAccess.py dev1:counters # print counters values
- liteAccess.py dev1:counters.desc # print description of dev1:counters
- liteAccess.py -s dev1:counters 1 2 3 4 5 6 7 8 9 10 # initialize dev1:counters
- liteAccess.py dev1:counters dev2:counters # get values of dev1:counters and dev2:counters

