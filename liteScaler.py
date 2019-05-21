#!/usr/bin/env python3
"""Example of user-defined Process Variables"""
#__version__ = 'v01 2018-12-17'# created
#__version__ = 'v02 2018-12-19'# multiple devices
#__version__ = 'v03 2018-12-20'#
#__version__ = 'v04 2018-12-23'# cloned from pvUser
#__version__ = 'v05 2019-01-02'# feature 'R' for monitored parameters
#__version__ = 'v06 2019-01-02'# action parameter is OK
#__version__ = 'v07 2019-01-08'# super() corrected for python2
__version__ = 'v08 2019-01-19'# flexible number of scalers, random initialization

import sys, threading
Python3 = sys.version_info.major == 3
import numpy as np

import liteServer
PV = liteServer.PV
Device = liteServer.Device
EventExit = liteServer.EventExit
printd = liteServer.printd

#````````````````````````````Process Variables````````````````````````````````
# We create two instances of a Scalers device and one instance of 'passive'
class Scaler(Device):
    """ Derived from liteServer.Device.
    Note: All class members, which are not process variables should 
    be prefixed with _"""
    def __init__(self,name):
        initials = list((np.random.rand(pargs.nCounters)*1000).round())
        print('initials '+name+'[%d]: '%len(initials)+str(initials[:20]))
        pars = {
          'counters':   PV('RW','Scalers',initials),
          'increments': PV('W','Scaler Increments',[-1.]+[1.]*(pargs.nCounters-1)),
          'frequency':  PV('W','Update frequency of all scalers',[1.]), 
          'reset':      PV('WB','Action parameter',[0]),
          #TODO:'pause':      PV('WD','Discrete parameter',['On','Off']),
        }
        #print('n,p',name,pars)
        if Python3:
            super().__init__(name,pars)
        else:
            Device.__init__(self,name,pars)
        thread = threading.Thread(target=self._state_machine)
        thread.daemon = True
        thread.start()
        
    def _state_machine(self):
        self._cycle = 0
        ns = len(self.counters.values)
        while not EventExit.is_set():
            EventExit.wait(1./self.frequency.values[0])
            #instance = self._name
            #printd(instance+': cycle %d'%self._cycle)
            ns = len(self.counters.values)
            for i,increment in enumerate(self.increments.values[:ns]):
                #print(instance+': c,i='+str((self.counters.values[i],increment)))
                self.counters.values[i] += increment
            if self.reset.values[0]:
                print('Scaler reset: '+self._name)
                self.reset.values[0] = 0
                for i in range(len(self.counters.values)):
                    self.counters.values[i] = 0
            self._cycle += 1
        print('Scaler '+self._name+' exit')
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# parse arguments
import argparse
parser = argparse.ArgumentParser(description=\
  'Simple Process Variable server.')
parser.add_argument('-d','--dbg', action='store_true', help='debugging')
parser.add_argument('-n','--nCounters', type=int, default=1100,
  help='Number of counters in each scaler')
  #default liteAcces accepts 1100 doubles, 9990 int16s
  #the UDP socket size is limited to 64k bytes
pargs = parser.parse_args()

devices = (
  Device('basic',{'item': PV('RW','Basic parameter',[0.])}),
  Scaler('dev1'),
  Scaler('dev2'),
)
print('Serving:'+str([dev._name for dev in devices]))

server = liteServer.Server(devices,dbg=pargs.dbg)
server.loop()


