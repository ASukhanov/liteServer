# Change Log for tek5ScopeMan manager.
 
## [1.0.0] - 2021-09-22


## [old] - 2021-09-21

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
