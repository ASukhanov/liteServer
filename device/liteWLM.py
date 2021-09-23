#!/usr/bin/env python3
"""liteserver for Wavelength Meter WS/6"""
#__version__ = 'v01 2018-12-20'# created
#__version__ = 'v02 2018-12-21'# wavelength is LDO_WLM object
#__version__ = 'v03 2018-12-26'# use liteserver instead of pvServer
#__version__ = 'v03 2018-02-04'# deliver frequency instead of Wavelength
#__version__ = 'v04 2021-04-08'# using liteserver v63+
#__version__ = 'v05 2021-04-11'# --port
__version__ = 'v06 2021-04-11'# real frequency
print(f'liteWLM {__version__}')

import sys, ctypes#, os, threading
from liteserver import liteserver

LDO = liteserver.LDO
Device = liteserver.Device
#EventExit = liteserver.EventExit
printd = liteserver.printd

#````````````````````````````Process Variables````````````````````````````````
class LDO_WLM(LDO):

    def set_dll(self):
        printd('>set_dll:')
        self.dll = ctypes.WinDLL('C:\Windows\System32\wlmData.dll')
        #self.dll.GetWavelengthNum.restype = ctypes.c_double
        self.dll.GetFrequencyNum.restype = ctypes.c_double
        printd('<set_dll:')

    def update_value(self):
        printd('>update_value')
        #self.values[0] = self.dll.GetWavelengthNum(\
        self.value = [self.dll.GetFrequencyNum(\
          ctypes.c_long(1), ctypes.c_double(0))]
        self.timestamp = liteserver.time.time()
        printd(f'<update_value: {self.value}')
        #return self._get_values()

    # override the data updater, which is called on get request
    def simulate_update_value(self):
        #print('>update_value()')
        self.value = [liteserver.time.time()]
        self.timestamp = liteserver.time.time()
        #print('<update_value()')

class WLM(Device):
    def __init__(self, name):
        pars = {
          #'wavelength': LDO_WLM('R','Wavelength [nM]',[0.]),
          'frequency': LDO_WLM('R','Frequency [THz]',[0.]),
          'sleep':      LDO('W','Sleep time between readings [s]',[.1]),
        }
        super().__init__(name, pars)
        
        #self.wavelength.set_dll()
        self.frequency.set_dll()

supportedDevices = (
  WLM('WLM1'),
)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,

# parse arguments
import argparse
parser = argparse.ArgumentParser(description=\
  'Process Variable server for:'\
   +str([dev._name for dev in supportedDevices]))
parser.add_argument('-d','--dbg', action='store_true', help='debugging')
parser.add_argument('-p','--port', type=int, default=9700,
    help='UDP port to listen')
pargs = parser.parse_args()

server = liteserver.Server(supportedDevices, port=pargs.port, debug=pargs.dbg)
printd('>loop')
server.loop()


