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
- start liteServer for scalers:
ssh acnlin23 'liteScaler.py'
- get variables and metadata from another computer:
liteAccess.py # get/set several PVs on the server
- start liteServer to ADO bridge for liteScaler:
ssh acnlinf4 'liteServerMan.py'
adoPet liteServer.0
"""
#__version__ = 'v01 2018-12-14' # Created
#__version__ = 'v02 2018-12-15' # Simplified greatly using ubjson
#__version__ = 'v03 2018-12-17' # moved out the user-defined PVs, PV_all fixed
#__version__ = 'v04 2018-12-17' # python3
#__version__ = 'v05 2018-12-17'# more pythonic, using getattr,setattr
#__version__ = 'v06 2018-12-17'# get/set/info works, TODO: conserve type for set
#__version__ = 'v07 2018-12-21'# python2 compatibility, Device is method-less.
#__version__ = 'v08 2018-12-26'# python2 not supported, 
#__version__ = 'v09 2018-12-28'# PV.__init__ accepts parent, 
#Server.__init__ accepts host, port. No arguments in Server.loop().
#__version__ = 'v10 2019-01-03'# force parameters to be iterable, it simplifies the usage
#__version__ = 'v11 2019-01-17'# Device.__init__ checks if parameter is list.
__version__ = 'v12 2019-05-23'# Raising extention, instead of printing. Special treatment of action parameters

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
        #print('pars '+str(pars))
        for p,v in pars.items():
            #print('setting '+p+' to '+str(v))
            #print('values type:',type(v.values))
            if not isinstance(v.values,list):
                printe('parameter "'+p+'" should be a list')
                sys.exit(1)
            setattr(self,p,v)
        
class PV():
    """Base class for Process Variables. Standard properties:
    values, count, timestamp, features, decription.
    values should be iterable! It simplifies internal logic.
    The type and count is determined from default values.
    Features is string, containing letters from 'RWD'.
    More properties can be added in derived classes"""
    def __init__(self,features='RW', desc='', values=[0], setter=None,
      parent=None):#, name=''):
        #self.name = name # name is not needed, it is keyed in the dictionary 
        self.values = values
        self.count = len(self.values)
        self.features = features
        self.desc = desc
        self.timestamp = 0.
        self.parent = parent
        self.setter = setter
        
    def __str__(self):
        print('PV object desc: %s at %s'%(self.desc,id(self)))

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
    def is_readable(self): return 'R' in self.features

    def set(self,vals,prop='values'):
        if not self.is_writable():
            raise PermissionError('PV is not writable')
        try: # pythonic way for testing if object is iterable
            test = vals[0]
        except:
            vals = [vals]

        # Special treatment of the boolean an action parameters
        print('set',len(self.values),type(self.values[0]))
        if len(self.values) == 1 and isinstance(self.values[0],bool):
            print('Boolean treatment')
            # the action parameter is the boolean one but not reabable
            # it always is False
            if not self.is_readable():
                print('Action treatment')
                vals = [False]
                if self.setter is not None:
                    # call PV setting method
                    self.setter(self)
            else: # make it boolean 
                vals = [True] if vals[0] else [False] 

        if type(vals[0]) is not type(self.values[0]):
            printe('Cannot assign '+str(type(vals[0]))+' to '\
            + str(type(self.values[0])))
            raise TypeError('Cannot assign '+str(type(vals[0]))+' to '\
            + str(type(self.values[0])))

        self.values = vals
        
    def monitor(self,callback):
        raise NotImplementedError('PV Monitor() is not implemented yet')

    def info(self):
        r = [i for i in vars(self) if not i.startswith('_')]
        return r
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````The Request broker```````````````````````````````
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
                printd('get_value():'+str(r))
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
        printd('sending back %d '%len(reply)+'bytes:\n"'+str(r)+'" to '+str((host,port)))
        socket.sendto(reply, (host,port))
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Server```````````````````````````````````````````
class Server():
    def __init__(self,devices,host=None,port=PORT,dbg=False):
        global DevDict, Dbg
        Dbg = dbg
        # create global dictionary of all devices
        DevDict = {dev._name:dev for dev in devices}
        if False:
            print('DevDict',DevDict)
            for d,i in DevDict.items():
                print('device '+str(d)+':'+str(i.info()))
        self.host = host if host else ip_address()
        self.port = port
        self.server = SocketServer.UDPServer((self.host, self.port),
          PV_UDPHandler)
    
    def loop(self):
        print(__version__\
          +'. Waiting for messages at '+self.host+':'+str(self.port))
        self.server.serve_forever()
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# see liteScalerMan.py liteAccess.py
