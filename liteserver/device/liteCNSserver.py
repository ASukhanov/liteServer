#!/usr/bin/env python3
"""liteServer working as a name server"""
"""#``````````````````Low level usage:```````````````````````````````````````````
from liteaccess import Access as la
reply = la.set(('liteCNSHost;9700:liteCNS','query','PeakSimGlobal'))
print(reply)
{'query': {'value': ['liteCNSHost,9701,dev1', 'PealSimulator, running on the liteCNSHost']}}
"""
__version__= 'v3.3.6 2025-08-14'

import sys, time, os
from importlib import import_module

from liteserver import liteserver
LDO = liteserver.LDO
Device = liteserver.Device

#````````````````````````````Process Variables````````````````````````````````
class CNS(Device):
    def __init__(self):
        parameters = {
          'query':   LDO('W','Provides reply on written query',[''],
            setter=self._query_received),
          'time':    LDO('R','Current time', round(time.time(),6), 
            getter=self._get_time),
        }
        # import the name resolution map
        mdir,mname = pargs.lookup.rsplit('/',1)
        path = os.path.abspath(mdir)
        mname = mname[:-3]# remove .py form the filename
        sys.path.append(path)
        lookupModule = import_module(mname)
        self.lookup = lookupModule.deviceMap

        super().__init__('liteCNS',parameters)
  
    def _get_time(self):
        t = round(time.time(),6)
        self.PV['time'].value = t
        self.PV['time'].timestamp = t

    def _query_received(self):
        v = self.PV['query'].value[0]
        try:    reply = self.lookup[v]
        except:
            reply = f'ERROR: Device {v} is not registered'
            self.PV['status'].set_valueAndTimestamp(reply)
        self.PV['query'].set_valueAndTimestamp(reply)
        #self.publish()# Calling publish inside a setter is dangerous
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# parse arguments
import argparse
parser = argparse.ArgumentParser(description=__doc__,
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    epilog=f'liteCNSserver: {__version__}')
parser.add_argument('lookup',  nargs='?', help=
    'File, containing lookup table for name resolution',
    default=    '/operations/app_store/liteServer/liteCNSresolv.py',
    )
pargs = parser.parse_args()

liteCNS = CNS()
server = liteserver.Server([liteCNS], port=9700)
server.loop()


