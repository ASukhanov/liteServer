#!/usr/bin/env python3
"""liteServer working as a name server"""
"""#``````````````````Low level usage:```````````````````````````````````````````
from liteserver import liteAccess as LA
LA.Access.set(('192.168.1.132;9699:liteCNS','query','apc'))
  {'query': {'value': '192.168.1.105'}}
"""
#__version__ = 'v01 2020-01-28'# created, not fully functional yet
__version__ = 'v02 2023-03-18'# 

import time

from liteserver import liteserver,liteCNS
LDO = liteserver.LDO
Device = liteserver.Device

#````````````````````````````Process Variables````````````````````````````````
class CNS(Device):
    def __init__(self):
        pars = {
          'query':   LDO('W','Provides reply on written query',[''],
            setter=self._query_received),
          'time':    LDO('R','Current time', round(time.time(),6), 
            getter=self._get_time),
        }
        self._ldoMap = liteCNS.hostPort()
        super().__init__('liteCNS',pars)
  
    def _get_time(self):
        t = round(time.time(),6)
        self.PV['time'].value = t
        self.PV['time'].timestamp = t

    def _query_received(self):
        v = self.PV['query'].value[0]
        try:    hostPort = self._ldoMap[v]
        except: hostPort = '?'
        self.PV['query'].value = hostPort       
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# parse arguments
import argparse
parser = argparse.ArgumentParser(description=__doc__,
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    epilog=f'liteCNSserver: {__version__}')
pargs = parser.parse_args()

liteCNS = CNS()
server = liteserver.Server([liteCNS], port=9699)
server.loop()


