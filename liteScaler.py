#!/usr/bin/env python3
"""Example of user-defined Lite Data Objects"""
#__version__ = 'v18 2020-02-09'# PV replaced with LDO
#__version__ = 'v19 2020-02-18'# reset drops after clearing
__version__ = 'v20 2020-02-21'# liteServer-rev3
 
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
          'counters':   LDO('R','%i of counters'%len(initials),initials),
          'increments': LDO('W','Increments of the individual counters'\
                        ,[-1]+[1]*(pargs.nCounters-1)),
          'frequency':  LDO('RW','Update frequency of all counters',[1.]\
                        ,opLimits=(0,10)),
          # 'pause' is boolean because it is readable
          #'pause':      LDO('RW','Pause all counters',[False]),
          # 'reset' is action because it is not readable 
          'reset':      LDO('RW','Reset all counters',[False]\
                        ,setter=self.reset),
          'command':    LDO('RW','Command to execute',['Started']\
                        ,legalValues=['Start','Stop'],setter=self.command_set),
          'image':      LDO('R','Image',[img]),
          'time':       LDOt('R','Current time',[0.],parent=self),#parent is for testing
        }
        self._pause = False
        super().__init__(name,pars)
        #print('n,p',self._name,pars)
        thread = threading.Thread(target=self._state_machine)
        thread.daemon = True
        thread.start()
        
    def reset(self,pv):
        #print('resetting scalers of %s'%self._name)
        for i in range(len(self.counters.v)):
            self.counters.v[i] = 0
        self.reset.v[0] = False# reset parameter
  
    def command_set(self,pv):
        print('command',str(self.command.v))
        if self.command.v[0] == 'Start':
            self.command.v[0] = 'Started'
            self._pause = False
        else:
            self.command.v[0] = 'Stopped'
            self._pause = True
        
    def _state_machine(self):
        self._cycle = 0
        ns = len(self.counters.v)
        while not EventExit.is_set():
            EventExit.wait(1./self.frequency.v[0])
            #print('self.pause',self.pause.v)
            if self._pause:
                continue

            # increment counters individually
            for i,increment in enumerate(self.increments.v[:ns]):
                #print(instance+': c,i='+str((self.counters.v[i],increment)))
                self.counters.v[i] += increment
                self.counters.t = time.time()
                
            # increment pixels in the image
            # this is very time consuming:
            #self.image.v[0] = (self.image.v[0] + 1).astype('uint8')
            
            self.image.v[0][0,0,0] = self._cycle
            
            self._cycle += 1
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
server
server.loop()


