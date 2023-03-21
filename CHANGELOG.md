# Change Log for liteServer project.

## 2.0.0 2023-03-20. Major upgrade

## Changed
liteserver

PVs are not class memmbers but items of a self.PV dictionary.
The UDP is much more stable.
Object encoding changed to MessagePack instead of UBJSON.

## Added
I2C devices to senstation: ADC: ADS1115, Magnetometers: MMC5983MA, HMC5883, QMC5983.

## [Not released yet] 2021-11-23 

## Changed
liteserver/device/liteGQ.py added parameter:mR/h

## 1.0.6 2021-11-19

### Added 
Support for Radiation Monitor and  Gyro sensor GMC-500 from GQ Electronics:
liteserver/device/liteGQ.py

### Changed

Minor bug fixing in:

   liteserver/device/litePeakSimulator.py
   liteserver/liteAccess.py

## [1.0.5] - 2021-10-07

## Changed

### liteserver.py

Device server.run now have ['Run','Stop', 'Exit']

 Added
- Device.add_parameter(self, name, ldo).
- Device.poll(self).
- Device.reset(self).
- Class ServerDev(Device): it is separated from the Server class.
- Use printd() and printdd() for 2-level debugging. 
- Do not change button-like parameter from None to int during setting.

### liteVGM.py
Cleanup
- PAUSE_AFTER_WRITE = 0.05.
- 2-level debugging.
- frequency parameter removed.
- set_status(), poll() and reset_VGM_timestamp() rewritten.

### liteGQ.py
Added

### liteserver/device/liteVGM.py

- Determine available serial ports using serial.tools.list_ports.comports.
- Use .value[0] instead of .value. That is more correct.
- Thread state_machine removed. The job done in a poll() method.
- Overridden: reset().

## [old] - 2021-09-21

### liteServer
- version__ = 'v40 2020-02-21'# rev3. value,timestamp and numpy keys shortened to v,t,n
- version__ = 'v41 2020-02-24'# err handling for missed chunks, 'pid' corruption fixed
- version__ = 'v42 2020-02-25'# start command added
- version__ = 'v43 2020-02-27'# serverState and setServerStatusText
- version__ = 'v44 2020-02-29'# do not except if type mismatch in set
- version__ = 'v45 2020-03-02'# Exiting, numpy array unpacked
- version__ = 'v46 2020-03-04'# test for publishing
- version__ = 'v47 2020-03-06'# Subscription OK
- version__ = 'v48 2020-03-07'
- version__ = 'v49 2020-03-09'# Read and subscription deliver only changed objects, subscriptions are per-device basis
- version__ = 'v50a 2020-03-26'# error propagation to clients
- version__ = 'v52 2020-12-17'# NSDelimiter=':' to conform EPICS and ADO
- version__ = 'v53b 2020-12-18'# .v and .t replaced with .value and .timestamp to be consistent with ADO and EPICS
- version__ = 'v54 2020-12-23'# publish() delivers parameters which have been changed since previous delivery. Unsubscribe is supported, may need locking.
- version__ = 'v55d 2020-12-31'# unsubscribing all, timeShift replaces time 
- version__ = 'v56 2021-01-01'# major update.
- version__ = 'v57 2021-01-02'# heartbeat thread
- version__ = 'v58 2021-01-04'# 'run' PV added to Device, 'start' PV removed from server, Device.aborted()
- version__ = 'v60e 2021-01-06'# itemsLost counter, send_udp got arg: subscribed 
- version__ = 'v61 2021-01-06'# Reasonably good
- version__ = 'v62 2021-01-12'# scalar allowed in parameter definition, it will be treated as array[1]
- version__ = 'v63 2021-04-08'# more informative exception handling
- version__ = 'v64 2021-04-11'# Server.Dbg is boolean
- version__ = 'v65 2021-04-12'# handling of a wrong command format exception
- version__ = 'v66 2021-04-20'# all threads should be non-daemonic
- version__ = 'v67 2021-04-21'# numpy array attribute is 'numpy', not 'n'
- version__ = 'v68 2021-04-22'# oplimits are violated when value is out of bounds
- version__ = 'v69 2021-04-24'# handling retransmissions
- version__ = 'v70 2021-04-29'# works OK for data  up to 5MB
- version__ = 'v71 2021-05-01'# added getter to LDO, removed second argument in LDO.setter
- version__ = 'v72 2021-05-03'# don't need to use value[0] most cases, require Ack even for 1-chunk messages
- version__ = 'v73 2021-05-05'# parent removed.
- version__ = 'v74 2021-05-19'# targeted un-subscribing
- version__ = 'v76 2021-05-26'# ItemLostLimit reduced to 1, with MaxAckCount = 10, parameters are copied, not bound in LDO.__init__
- version__ = 'v77 2021-05-27'# LDO._name replaced with LDO.name
- version__ = 'v78 2021-06-10'# runFlag removed, added LDO.start() LDO.stop()
- version__ = 'v79 2021-07-06'# use float32 for encoding, could be overridded by setting Device.no_float32=True. Server.Dbg handled properly
- version__ = 'v80 2021-07-07'# opLimits for debug

### liteAccess
__version__ = 'v42 2020-02-21'# liteServer-rev3.
__version__ = 'v43 2020-02-24'# noCNS, err nandling in retransmission
__version__ = 'v44 2020-03-06'# subscription supported
__version__ = 'v45 2020-12-14'# The Access is working.
__version__ = 'v46c 2020-12-23'# Access returns data as cad_io expects
__version__ = 'v47 2020-12-24'# unsubscribe is working using thread_with_exception
TODO: subscription process is not efficient: every parameter is served by a separate thread. It is better to use selectors.
__version__ = 'v48c 2020-12-27'# send_cmd, send_dictio, receive_dictio
__version__ = 'v49 2020-12-27'# PVs is quite universal, Access hopefully not needed, cleanup required
__version__ = 'v50b 2020-12-30'# gethostbyname, cleanup, shippedBytes
__version__ = 'v51 2021-01-04'# Access.get() accepts **kwargs, for compatibility with the ADO
__version__ = 'v52 2021-01-05'# typo fixed
__version__ = 'v53 2021-01-06'# bug-free dispatch() 
__version__ = 'v54 2021-01-06'# cnsname handling, socket.timeout
__version__ = 'v55 2021-04-08'# better diagnostics
__version__ = 'v57 2021-04-12'# OS independent get user name and PID
__version__ = 'v58 2021-04-16'# liteCNS imported from the same package, __doc__ corrected
__version__ = 'v59 2021-04-20'# comments and printing updated
__version__ = 'v60 2021-04-20'# numpy array handlied correctly
__version__ = 'v61 2021-04-21'# debugging printout have been updated
__version__ = 'v62 2021-04-25'# chunks is dict
__version__ = 'v63 2021-05-04'# bug fixing, OK for data sizes up to 5 MB
__version__ = 'v64 2021-05-04'# raising exceptions instead of returning error code.
__version__ = 'v65 2021-06-10'# subscription sockets are blocking now

### liteScaler
__version__ = 'v20a 2020-02-21'# liteServer-rev3
__version__ = 'v21 2020-02-29'# command, pause, moved to server
__version__ = 'v21 2020-03-02'# numpy array unpacked
__version__ = 'v22 2020-03-03'# coordinate is numpy (for testing) 
__version__ = 'v23 2020-03-06'# publish image and counters
__version__ = 'v24 2020-03-09'# publish is called once per loop
__version__ = 'v25 2020-03-26'# test number
__version__ = 'v26 2020-12-24'# cycle parameter added
__version__ = 'v27 2020-12-28'# --interface
__version__ = 'v28a 2020-12-30'# publishingSpeed parameter
__version__ = 'v29 2021-01-04'# idling replaced with 'not aborted()'
__version__ = 'v30 2021-04-23'# --port, setServerStatusText, self.status.value
__version__ = 'v31 2021-05-02'# added performance parameters,
__version__ = 'v32 2021-07-06'# no_float32 and ServerDbg are handled properly

### liteVGM
__version__ = 'v01 2018-12-27'# created
__version__ = 'v02 2018-05-07'# better error handling
__version__ = 'v03 2018-05-08'# longer (0.5s) time.sleep on opening, it helps
__version__ = 'v04 2011-11-07'# support new liteServer 
__version__ = 'v05 2011-11-09'# parent abandoned, global serialDev
__version__ = 'v06 2011-11-10'# parent is back, it is simplest way to provide PVD with the proper serial device
__version__ = 'v07 2011-11-22'# IMPORTANT: _serialDev replaces serialDev, non-underscored members are treated as parameters
__version__ = 'v08 2011-11-26'# do not process not-connected devices
__version__ = 'v09 2011-11-27'# reset_VGM_timestamp action added 
__version__ = 'v10 2011-11-27'# reset_VGM_timestamp needs pv argument
__version__ = 'v11 2011-11-30'# print('no data') shows the serial device
__version__ = 'v12 2011-11-30'# Start parameter renamed by Reset
__version__ = 'v13 2011-11-30'# reset_VGM_timestamp during __
__version__ = 'v14 2021-09-21'# 
