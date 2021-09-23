#!/usr/bin/env python3
"""liteServer working as a name server"""
"""#``````````````````Low level usage:```````````````````````````````````````````
import liteAccess as LA
LA.LdoPars(['cns','*']).devices()#  lists served LDOs
LA.LdoPars(['cns','*']).info()#     lists parameters
"""
__version__ = 'v01 2020-01-28'# created, not fully functional yet

import time
import yaml

import liteServer
LDO = liteServer.LDO

#````````````````````````````Globals``````````````````````````````````````````
CNSFile = 'liteCNS.yaml'
Device = liteServer.Device

#````````````````````````````Helper functions`````````````````````````````````
def printw(msg): print('WARNING: '+msg)
def printe(msg): print('ERROR: '+msg)
def printd(msg): 
    if pargs.dbg:
        print('dbgCNS: '+str(msg))
def liteCNS():
    """returns map of LDO to [hostPort,device]"""
    import json
    ldoMapDirect = {} # de-refernced map
    with open(CNSFile,'r') as f:
        fullDict = yaml.load(f.read(),Loader=yaml.FullLoader)
        ldoMap = fullDict['ldo']
    return ldoMap

#````````````````````````````Process Variables````````````````````````````````
class LDOt(LDO):
    '''LDO, returning current time.''' 
    # override data updater
    def update_value(self):
        self.value = [time.time()]
        self.timestamp = time.time()

class CNS(Device):
    def __init__(self):
        pars = {
          'query':   LDO('W','Provides reply on written query',['','']\
          ,setter=self._query_received),
          'time':    LDOt('R','Current time',[0.],parent=self),
        }
        self._ldoMap = liteCNS()
        printd('ldoMap: '+str(self._ldoMap))
        super().__init__('liteCNS',pars)
        printd('n,p '+str((self._name,pars)))
  
    def _query_received(self,LDO):
        printd('query: '+str(self.query.value))
        hostPort,devs = self._ldoMap[ldo]
        self.query.value = hostPort,devs        
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# parse arguments
import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-d','--dbg', action='store_true', help='Debugging mode')
pargs = parser.parse_args()
liteServer.Server.Dbg = pargs.dbg

liteCNS = CNS()
server = liteServer.Server([liteCNS],port=9699,serverPars=False)
server.loop()


