# liteServer
Very Lightweight Process Variable Server. The basic principle is similar to the 
pvAccess protocol of EPICS. It hosts Lite Data Objects (LDO, analog of process variables in EPICS) and provides 
info/set/get/read/subscribe remote access to them using UDP protocol. 
Data encoding is implemented using UBJSON specification, which makes it very 
fast and efficient.

User responsibility is to provide private methods for connecting process variables to physical devices.

## Motivation
Provide control for devices connected to non-linux machines. 
The simplicity of the protocol makes it possible to implement in CPU-less FPGA device.

The server is running on a remote machine. Device parameters can be 
manipulated using liteAccess.py.

The liteAccess.py is the base class for accessing the server parameters.

## Status
Released

### Examples
- liteScaler.py # test server, providing two multi-channel scalers and a multi-dimesional array.
