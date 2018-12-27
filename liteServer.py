"""Very lightweight base class of the Process Variable Server.
It hosts the process variables and responds to get/set/monitor/info commands.

The main purpose is to provide an easy way to communicate with a device on 
Windows machine, which does not have the Linux support.
Usage:
  + Add user-defined processing in Device-derived object or override the 
  get()/set() methods of PV-derived objects.
  + Run this script on a Windows.
  + Use pvAdoMan manager on linux (not developed yet), which connects PV and ADO worlds.

Transport protocol: UDP. It is reliable for data blocks less than 1500 bytes,
for larger items TCP can be used.

Encoding protocol: UBJSON. It takes care about parameter types.

Dependecies: py-ubjson, very simple and efficient data serialization protocol

Performance: liteServer is fastest possible python access to parameters over ethernet.

Example usage:
- start server on acnlinec:
  python3 liteScalerMan.py
- get variables and metadata from another computer:
  python3 liteAccess.py # get/set several PVs on the server
"""
#__version__ = 'v01 2018-12-14' # Created
#__version__ = 'v02 2018-12-15' # Simplified greatly using ubjson
#__version__ = 'v03 2018-12-17' # moved out the user-defined PVs, PV_all fixed
#__version__ = 'v04 2018-12-17' # python3
#__version__ = 'v05 2018-12-17'# more pythonic, using getattr,setattr
#__version__ = 'v06 2018-12-17'# get/set/info works, TODO: conserve type for set
#__version__ = 'v07 2018-12-21'# python2 compatibility, Device is method-less.
__version__ = 'v08 2018-12-26'# python2 not supported, 

import sys
import socket
#import SocketServer# for python2
import socketserver as SocketServer# for python3
import time
#from collections import OrderedDict as OD
import ubjson
import threading

PORT = 9999# Communication port number
DevDict = None # forward declaration
Dbg = False
EventExit = threading.Event()

#````````````````````````````Helper functions`````````````````````````````````
def printi(msg): print('info: '+msg)
def printw(msg): print('WARNING: '+msg)
def printe(msg): print('ERROR: '+msg)
def printd(msg):
    if Dbg: print('dbg: '+msg)

def ip_address():
    """Platform-independent way to get local host IP address"""
    return [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close())\
      for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]

def tostr(item):
    return item if isinstance(item,str) else item.decode()

#````````````````````````````Base Classes`````````````````````````````````````
class Device():
    """Device object has unique _name, its members are parameters (objects,
    derived from PV class).
    """
    def __init__(self,name='?',pars=None):
        self._name = name
        printd('pars '+str(pars))
        for p,v in pars.items():
            printd('setting '+p+' to '+str(v))
            setattr(self,p,v)
        
class PV():
    """Base class for Process Variables. Standard properties:
    values, count, timestamp, features, decription. 
    The type and count is determined from default values.
    Features is string, containing letters from 'RWD'.
    More properties can be added in derived classes"""
    def __init__(self,features='RW',desc='',values=[0]):#, name=''):
        #self.name = name
        self.values = values
        self.count = len(self.values)
        self.features = features
        self.desc = desc
        self.timestamp = 0.

    def get_prop(self,prop):
        return getattr(self,prop)
    
    def _get_values(self):
        t = self.timestamp
        if t == 0.: t = time.time()
        printd('prop:'+str(getattr(self,'values')))
        return [t] + getattr(self,'values')
        
    def get_values(self):
        """Overridable getter"""
        return self._get_values()

    def is_writable(self): return 'W' in self.features

    def set(self,vals,prop='values'):
        if self.is_writable():
            setattr(self,prop,vals)
            return {}
        else:
            return {'ERR':'Not Writable'}
        
    def monitor(self,callback):
        printe('monitor() not yet implemented for '+name+':'+par)   

    def info(self):
        r = [i for i in vars(self) if not i.startswith('_')]
        return r
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Request broker```````````````````````````````````
class PV_UDPHandler(SocketServer.BaseRequestHandler):

    def _reply(self,items):
        printd('>_reply [%d'%len(items)+', type:'+str(type(items[0])))
        action = tostr(items[0])
        r = {}
        if action == 'get':
            for i in items[1]:
                devParName = tostr(i)
                dev,parProp = devParName.split(':')
                pp = parProp.split('.',1)
                pv = getattr(DevDict[dev],pp[0])
                if len(pp) == 1:
                    r[devParName] = pv.get_values()
                else:
                    v = pv.get_prop(pp[1])
                    r[devParName] = v
        elif action == 'set':
            dev,par = tostr(items[1]).split(':')
            pv = getattr(DevDict[dev],par)
            printd('set:'+str(items[2]))
            return pv.set(items[2])
        elif action == 'ls':
            if len(items) == 1:
                return {'supported devices':[i for i in DevDict]}
            if len(items[1]) == 0:
                return {'supported devices':[i for i in DevDict]}
            for i in items[1]:
                devParName = tostr(i)
                devPar = devParName.split(':')
                if len(devPar) == 1:
                    dev = DevDict[devPar[0]]
                    r[devPar[0]] = [i for i in vars(dev)\
                      if not i.startswith('_')]
                else:
                    #TODO handle dev:par.feature
                    pv = getattr(DevDict[devPar[0]],devPar[1])
                    r[devParName] = pv.info()
        else:
            return {'ERR':'Wrong command "'+str(action)+'"'}
        return r
                
    def handle(self):
        data = self.request[0].strip()
        socket = self.request[1]
        printd("{} wrote:".format(self.client_address[0]))
        cmd = ubjson.loadb(data)
        printd(str(cmd))
        try:
            r = self._reply(cmd)
        except Exception as e:
            r = 'ERR. Exception: '+repr(e)
        reply = ubjson.dumpb(r)
        host,port = self.client_address# the port here is temporary
        printd('sending back: "'+str(reply)+'" to '+str((host,PORT)))
        socket.sendto(reply, (host,PORT))
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Server```````````````````````````````````````````
class Server():
    def __init__(self,devices,dbg=False):
        global DevDict, Dbg
        Dbg = dbg
        # create global dictionary of all devices
        DevDict = {dev._name:dev for dev in devices}
        if False:
            print('DevDict',DevDict)
            for d,i in DevDict.items():
                print('device '+str(d)+':'+str(i.info()))
    
    def loop(self):
        host = ip_address()
        server = SocketServer.UDPServer((host, PORT), PV_UDPHandler)
        print(__version__+'. Waiting for messages at '+host+':'+str(PORT))
        server.serve_forever()
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# see liteScalerMan.py liteAccess.py
