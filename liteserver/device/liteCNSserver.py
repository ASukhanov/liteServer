#!/usr/bin/env python3
"""liteServer working as a name server
"""
# pylint: disable=invalid-name
"""
#``````````````````Low level usage:```````````````````````````````````````````
from liteaccess import Access as la
reply = la.set(('localhost;9700:liteCNS','query','PeakSimGlobal'))
print(reply)
{'query': {'value': ['liteCNSHost,9701,dev1', 'PeakSimulator, running on the liteCNSHost']}}
"""
__version__= 'v3.3.7 2025-08-19'# external (if defined) name resolution server

import sys, time, os
from importlib import import_module

from liteserver import liteserver
LDO = liteserver.LDO
Device = liteserver.Device

#````````````````````````````Process Variables````````````````````````````````
class CNS(Device):
    def __init__(self):
        self.cnsLDO = None# external (if defined) name resolution server
        self.lookup = {}# lookup table for name resolutions
        PV = {
          'devices': LDO('R','Registered devices',['']),
          'query':   LDO('W','Provides reply on written query',[''],
            setter=self._query_received),
          'time':    LDO('R','Current time', round(time.time(),6), 
            getter=self._get_time),
        }
        # import the name resolution map
        mdir,mname = pargs.lookup.rsplit('/',1)
        path = os.path.abspath(mdir)
        #print(f'path: {path}')
        mname = mname[:-3]# remove .py form the filename
        sys.path.append(path)
        try:
            lookupModule = import_module(mname)
        except:
            print(f'ERROR: Could not import {pargs.lookup}')
            sys.exit(1)

        try:
            siteCNShost = lookupModule.SiteCNShost
            print(f'Name resolution will be re-directed to {siteCNShost}')
            from liteaccess import PVs
            self.cnsLDO = PVs((f'{siteCNShost};9700:liteCNS','query'))
        except AttributeError as e:
            print(f'Name resolution using {pargs.lookup}')
            self.lookup = lookupModule.deviceMap

        PV['devices'].set_valueAndTimestamp(list(self.lookup.keys()))

        super().__init__('liteCNS',PV)
  
    def _get_time(self):
        t = round(time.time(),6)
        self.PV['time'].value = t
        self.PV['time'].timestamp = t

    def _query_received(self):
        v = self.PV['query'].value[0]
        #print(f'>query: {v}')
        if self.cnsLDO:
            r = self.cnsLDO.set(v)
            print(f'cnsLDO: {r}')
            reply = f'ERROR: Not implemented: Name service re-direction to SiteCNSHost {self.cnsLDO}'
        else:
            try:    reply = self.lookup[v]
            except:
                reply = f'ERROR: Device {v} is not registered at {pargs.ip}'
                self.PV['status'].set_valueAndTimestamp(reply)
        self.PV['query'].set_valueAndTimestamp(reply)
        #print(f'<query: {reply}')
        #self.publish()# Calling publish inside a setter is dangerous
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# parse arguments
import argparse
parser = argparse.ArgumentParser(description=__doc__,
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    epilog=f'liteCNSserver: {__version__}')
parser.add_argument('-i','--ip', default = 'localhost',
        choices=liteserver.ip_choices() + ['localhost'], help=\
'Server will be serving this IP address, port 9700. If None, then IP with internet access will be used')
parser.add_argument('lookup',  nargs='?', help=
    'File, containing lookup table for name resolution',
    default=    '/operations/app_store/liteServer/liteCNSresolv.py',
    )
pargs = parser.parse_args()

liteCNS = CNS()
server = liteserver.Server([liteCNS], interface=pargs.ip, port=9700)
server.loop()


