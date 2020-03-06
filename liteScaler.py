#!/usr/bin/env python3
"""Example of user-defined Lite Data Objects"""
#__version__ = 'v20a 2020-02-21'# liteServer-rev3
#__version__ = 'v21 2020-02-29'# command, pause, moved to server
#__version__ = 'v21 2020-03-02'# numpy array unpacked
__version__ = 'v22 2020-03-03'# coordinate is numpy (for testing) 
 
import sys, time, threading
import numpy as np

import liteServer
LDO = liteServer.LDO
Device = liteServer.Device
EventExit = liteServer.EventExit

#````````````````````````````Helper functions`````````````````````````````````
def printw(msg): print('WARNING: '+msg)
def printe(msg): print('ERROR: '+msg)
def printd(msg): 
    if pargs.dbg:
        print('dbgScaler: '+str(msg))
#````````````````````````````Lite Data Objects````````````````````````````````
class LDOt(LDO):
    '''LDO, returning current time.''' 
    # override data updater
    def update_value(self):
        self.v = [time.time()]
        self.t = time.time()

class Scaler(Device):
    """ Derived from liteServer.Device.
    Note: All class members, which are not process variables should 
    be prefixed with _"""
    def __init__(self,name,bigImage=False):
        #initials = (np.random.rand(pargs.nCounters)*1000).round().astype(int).tolist()
        initials = [0]*pargs.nCounters
        #2000,3000,3 #works on localhost with 1ms delay 50MB/s, server busy 200%
        #960,1280,3 # 3.6 MB, OK on localhost with 60K chunks and 0.5ms ChunkSleep, 100MB/s, sporadic KeyError 'pid'
        #480,640,3 # 0.9 MB, OK on localhost with 60K chunks, 1ms ChunkSleep, 48MB/s chunk speed
        h,w,p = (960,1280,3) if bigImage else (120,160,3)
        img = np.arange(h*w*p).astype('uint8').reshape(h,w,p)
        incs = []
        for i in range(1,1+pargs.nCounters//2):
            incs += [-i,i]
        pars = {
          'counters':   LDO('R','%i of counters'%len(initials),initials),
          'increments': LDO('W','Increments of the individual counters',incs),
          'frequency':  LDO('RW','Update frequency of all counters',[1.]\
                        ,opLimits=(0,10)),
          'reset':      LDO('RW','Reset all counters',[False]\
                        ,setter=self.reset),
          'image':      LDO('R','Image',img),
          'coordinate': LDO('RW','Just 2-component numpy vector for testing'\
                        ,np.array([0.,1.]).astype('float32')),#
          'time':       LDOt('R','Current time',[0.],parent=self),#parent is for testing
        }
        super().__init__(name,pars)
        #print('n,p',self._name,pars)
        thread = threading.Thread(target=self._state_machine)
        thread.daemon = True
        thread.start()
        
    def reset(self,pv):
        #print('resetting scalers of %s'%self._name)
        for i in range(len(self.counters.v)):
            self.counters.v[i] = 0
        t = time.time()
        self.counters.t = t
        self.reset.v[0] = False# reset parameter
        self.reset.t = t
        
    def _state_machine(self):
        time.sleep(.2)# give time for server to startup

        self._cycle = 0
        ns = len(self.counters.v)
        while not EventExit.is_set():
            EventExit.wait(1./self.frequency.v[0])
            idling = self.serverState()[:5] != 'Start'
            if idling:
                continue

            if self._cycle%100 == 0:#Status report through server.status
                self.setServerStatusText('Cycle %i on '%self._cycle+self._name)

            # increment counters individually
            for i,increment in enumerate(self.increments.v[:ns]):
                #print(instance+': c,i='+str((self.counters.v[i],increment)))
                self.counters.v[i] += increment
            self.counters.t = time.time()
                
            # increment pixels in the image
            # this is very time consuming:
            #self.image.v[0] = (self.image.v[0] + 1).astype('uint8')

            # change only one pixel            
            self.image.v[0,0,0] = self._cycle
            self.image.t = time.time()
     
            self._cycle += 1
            
            # publish image once per 10 cycles
            if self._cycle % 10 == 0:
                self.image.publish()
            
        print('Scaler '+self._name+' exit')
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# parse arguments
import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-d','--dbg', action='store_true', help='Debugging mode')
parser.add_argument('-b','--bigImage', action='store_true', help=\
'generate big image >64kB')
parser.add_argument('-s','--scalers', type=int, default=2,help=\
'number of devices/scalers (2)')
parser.add_argument('-n','--nCounters', type=int, default=1100,
  help='Number of counters in each scaler')
  #default liteAcces accepts 1100 doubles, 9990 int16s
  #the UDP socket size is limited to 64k bytes
pargs = parser.parse_args()

liteServer.Server.Dbg = pargs.dbg
devices = [Scaler('dev'+str(i+1),bigImage=pargs.bigImage)\
  for i in range(pargs.scalers)]

print('Serving:'+str([dev._name for dev in devices]))

server = liteServer.Server(devices)
server.loop()


