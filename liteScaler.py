#!/usr/bin/env python3
"""Example of user-defined Process Variables"""
#__version__ = 'v01 2018-12-17'# created
#__version__ = 'v02 2018-12-19'# multiple devices
#__version__ = 'v03 2018-12-20'#
#__version__ = 'v04 2018-12-23'# cloned from pvUser
#__version__ = 'v05 2019-01-02'# feature 'R' for monitored parameters
#__version__ = 'v06 2019-01-02'# action parameter is OK
#__version__ = 'v07 2019-01-08'# super() corrected for python2
#__version__ = 'v08 2019-01-19'# flexible number of scalers, random initialization
#__version__ = 'v09 2019-05-21'# version parameter, includes description
#__version__ = 'v10 2019-06-08'# timestamping
#__version__ = 'v11 2019-06-09'# numpy array support
__version__ = 'v12 2019-06-17'# release

import sys, time, threading
Python3 = sys.version_info.major == 3
import numpy as np

import liteServer
PV = liteServer.PV
Device = liteServer.Device
EventExit = liteServer.EventExit
printd = liteServer.printd

#````````````````````````````Helper functions`````````````````````````````````
def printw(msg): print('WARNING: '+msg)
def printe(msg): print('ERROR: '+msg)
def printd(msg): 
    if pargs.dbg:
        print('DBG:'+str(msg))
#````````````````````````````Process Variables````````````````````````````````
# We create two instances of a Scalers device and one instance of 'passive'
class Scaler(Device):
    """ Derived from liteServer.Device.
    Note: All class members, which are not process variables should 
    be prefixed with _"""
    def __init__(self,name,bigImage=False):
        initials = (np.random.rand(pargs.nCounters)*1000).round().astype(int).tolist()
        #print('initials '+name+'[%d]: '%len(initials)+str(initials[:20]))
        h,w,p = 120,160,3
        smallImg = np.arange(h*w*p).astype('uint8').reshape(h,w,p)
        #h,w,p = 2000,3000,3 #works on localhost with 1ms delay 50MB/s, server busy 200%
        #h,w,p = 960,1280,3 # 3.6 MB, OK on localhost with 60K chunks and 1ms delay
        h,w,p = 480,640,3 # 0.9 MB, OK on localhost with 60K chunks
        bigImg = np.arange(h*w*p).astype('uint8').reshape(h,w,p)
        img = bigImg if bigImage else smallImg    
        pars = {
          'counters':   PV('R','%i of counters'%len(initials),initials),
          'increments': PV('RW','Increments of the individual counters'\
                        ,[-1]+[1]*(pargs.nCounters-1)),
          'frequency':  PV('RW','Update frequency of all counters',[1.]\
                        ,opLimits=(0,10)),
          'pause':      PV('RW','Pause all counters',[False]), 
          'reset':      PV('W','Reset all counters',[False]\
                        ,setter=self.reset),
          'image':      PV('R','Image',[img])
        }
        if Python3:
            super().__init__(name,pars)
        else:
            Device.__init__(self,name,pars)
        #print('n,p',self._name,pars)
        thread = threading.Thread(target=self._state_machine)
        thread.daemon = True
        thread.start()
        
    def reset(self,pv):
        print('resetting scalers of %s'%self._name)
        for i in range(len(self.counters.value)):
            self.counters.value[i] = 0
        
    def _state_machine(self):
        self._cycle = 0
        ns = len(self.counters.value)
        while not EventExit.is_set():
            EventExit.wait(1./self.frequency.value[0])
            if self.pause.value[0]:
                continue

            # increment counters individually
            for i,increment in enumerate(self.increments.value[:ns]):
                #print(instance+': c,i='+str((self.counters.value[i],increment)))
                self.counters.value[i] += increment
                self.counters.timestamp = [time.time()]
                
            # increment pixels in the image
            # this is very time consuming:
            #self.image.value[0] = (self.image.value[0] + 1).astype('uint8')
            
            self.image.value[0][0,0,0] = self._cycle
            
            self._cycle += 1
        print('Scaler '+self._name+' exit')
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# parse arguments
import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-d','--dbg', action='store_true', help='debugging')
parser.add_argument('-b','--bigImage', action='store_true', help=\
'generate big image >64kB')
parser.add_argument('-s','--scalers', type=int, default=2,help=\
'number of devices/scalers (2)')
parser.add_argument('-n','--nCounters', type=int, default=1100,
  help='Number of counters in each scaler')
  #default liteAcces accepts 1100 doubles, 9990 int16s
  #the UDP socket size is limited to 64k bytes
pargs = parser.parse_args()

devices = [Scaler('dev'+str(i+1),bigImage=pargs.bigImage)\
  for i in range(pargs.scalers)]

print('Serving:'+str([dev._name for dev in devices]))

server = liteServer.Server(devices,dbg=pargs.dbg)
server
server.loop()


