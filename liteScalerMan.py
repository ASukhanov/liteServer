#!/usr/bin/env python3
"""Example of user-defined Process Variables"""
#__version__ = 'v01 2018-12-17'# created
#__version__ = 'v02 2018-12-19'# multiple devices
#__version__ = 'v03 2018-12-20'#
__version__ = 'v04 2018-12-23'# cloned from pvUser

import sys
Python3 = sys.version_info.major == 3
import liteServer
from collections import OrderedDict as OD# it is better than dict
import threading

PV = liteServer.PV
Device = liteServer.Device
EventExit = liteServer.EventExit
printd = liteServer.printd

#````````````````````````````Process Variables````````````````````````````````
# We create two instances of a Scalers device and one instance of WFG
class Scaler(Device):
    def __init__(self,name):
        pars = {
          'counters':   PV('W','Ten Scalers',[0]*10),
          'increments': PV('W','Scaler Increments',[-1]+[1]*4),
          'frequency':  PV('W','Update frequency of all scalers',[1.]), 
          'pause':      PV('WD','Pause control',['On','Off']),
          'reset':      PV('WB','Reset action',[0]),
        }
        #print('n,p',name,pars)
        if Python3:
            super().__init__(name,pars)
        else:
            super().__init__(name,pars)
        thread = threading.Thread(target=self._state_machine)
        thread.daemon = True
        thread.start()
        
    def _state_machine(self):
        self.cycle = 0
        ns = len(self.counters.values)
        while not EventExit.is_set():
            #instance = self._name
            EventExit.wait(self.frequency.values[0])
            #printd(instance+': cycle %d'%self.cycle)
            ns = len(self.counters.values)
            for i,increment in enumerate(self.increments.values[:ns]):
                #printd(instance+': c,i='+str((self.counters.values[i],increment)))
                self.counters.values[i] += increment
            self.cycle += 1
        print('Scaler '+self.name+' exit')

devices = (
  Device('passive',{
    'item': PV('W','Ten Variables',[0.])
    }),
  Scaler('dev1'),
  Scaler('dev2'),
)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# parse arguments
import argparse
parser = argparse.ArgumentParser(description=\
  'Simple Process Variable server, devices:'\
   +str([dev._name for dev in devices]))
parser.add_argument('-d','--dbg', action='store_true', help='debugging')
pargs = parser.parse_args()

server = liteServer.Server(devices,pargs.dbg)
server.loop()


