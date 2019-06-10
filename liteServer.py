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
#__version__ = 'v12 2019-05-23'# Raising extention, instead of printing. Special treatment of action parameters
#__version__ = 'v13 2019-05-23'# Tuple, tried use tuple for non writable, it does not work  
#__version__ = 'v14 2019-05-23'# opLimits
#__version__ = 'v15 2019-05-31'# count is array 
#__version__ = 'v16 2019-06-01'# Device 'server' incorporated
#__version__ = 'v17 2019-06-02'# DevDict is OrderedDict
__version__ = 'v18 2019-06-09'# numpy array support

import sys
import socket
#import SocketServer# for python2
import socketserver as SocketServer# for python3
import time
from collections import OrderedDict as OD
import ubjson
import threading
import math

UDP = True
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
    def __init__(self,features='RW', desc='', values=[0], opLimits=None\
        ,setter=None):#, numpy=None):
        #self.name = name # name is not needed, it is keyed in the dictionary
        self.timestamp = None
        self.values = values
        self.count = [len(self.values)]
        self.features = features
        self.desc = desc
        
        # if the parameter is numpy :
        try:    
            shape,dtype = values[0].shape, values[0].dtype
            printd('par is numpy')
        except: 
            pass
        
        # absorb optional properties
        self.opLimits = opLimits
        self.setter = setter
        #self.numpy = numpy# for numpy array it is: (shape,dtype)
        
    def __str__(self):
        print('PV object desc: %s at %s'%(self.desc,id(self)))

    def get_prop(self,propName):
        #print('>get_prop',propName)
        prop = self.add_prop(getattr(self,propName))
        #print('prop',type(prop),len(prop),str(prop)[:60]+'...')
        return prop
    
    def add_prop(self,prop,parDict={}):
        # add property to parameter dictionary
        #print('>add_prop',prop,str(parDict)[:60])
        try:
            # if the parameter is numpy array:
            value = prop[0]
            shape,dtype = value.shape, str(value.dtype)
        except Exception as e:
            printd('not numpy, %s'%str(e))
            parDict['values'] = prop
        else:
            #print('numpy array, add key "numpy"')
            parDict['values'] = value.tobytes()
            parDict['numpy'] = shape,dtype
        printd('_get_values:'+str(parDict)[:200])
        return parDict

    def _get_values(self):
        parDict = {'timestamp':self.timestamp}
        return self.add_prop(self.values,parDict)
        
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

        # Special treatment of the boolean and action parameters
        #print('set',len(self.values),type(self.values[0]))
        if len(self.values) == 1 and isinstance(self.values[0],bool):
            #print('Boolean treatment %s'%str(vals))
            # the action parameter is the boolean one but not reabable
            # it always is False
            if not self.is_readable():
                print('Action treatment')
                vals = [False]
                # call PV setting method
                if self.setter is not None:
                    self.setter(self) # (self) is important!
            else: # make it boolean 
                vals = [True] if vals[0] else [False] 

        if type(vals[0]) is not type(self.values[0]):
            printe('Cannot assign '+str(type(vals[0]))+' to '\
            + str(type(self.values[0])))
            raise TypeError('Cannot assign '+str(type(vals[0]))+' to '\
            + str(type(self.values[0])))
            
        if self.opLimits is not None:
            printd('checking for opLimits')
            if vals[0] <= self.opLimits[0] or vals[0] >= self.opLimits[1]:
                raise ValueError('out of opLimits '+str(self.opLimits)+': '\
                + str(vals[0]))

        self.values = vals
        
    def monitor(self,callback):
        raise NotImplementedError('PV Monitor() is not implemented yet')

    def info(self):
        # list all members which are not None and not prefixed with '_'
        r = [i for i in vars(self) 
          if not (i.startswith('_') or getattr(self,i) is None)]
        return r
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````The Request broker```````````````````````````````
class PV_Handler(SocketServer.BaseRequestHandler):

    def parse_devPar(self,devPar):
        try:
           dev,par = devPar.split(':')
        except:
           raise NameError('Expected dev:par, got '+str(devPar))
        return dev,par

    def _reply(self,serverMsg):
        #printd('>_reply [%d'%len(serverMsg)+', type:'+str(type(serverMsg[0])))
        printd('>_reply')
        #cmd = tostr(serverMsg[0])
        cmd,arg = serverMsg['cmd']
        returnedDict = {}
        if cmd == 'get':
            for devParName in arg:
                dev,parProp = self.parse_devPar(devParName)
                try:
                    par,prop = parProp.split('.',1)
                except:
                    # case: device:parameter
                    pv = getattr(DevDict[dev],parProp)
                    returnedDict[devParName] = pv.get_values()
                    printd('repl %s:'%devParName+str((len(returnedDict[devParName]),type(returnedDict[devParName]))))
                else:
                    #print('case: device:parameter.property, %s'%devParName)
                    pv = getattr(DevDict[dev],par)
                    v = pv.get_prop(prop)
                    returnedDict[devParName] = v
                printd('get_value():'+str(returnedDict)[:200])
        elif cmd == 'set':
            dev,par = self.parse_devPar(arg[0])
            pv = getattr(DevDict[dev],par)
            printd('set:'+str(arg[1]))
            return pv.set(arg[1])
        elif cmd == 'ls':
            if len(arg) == 0:
                return {'supported devices':[i for i in DevDict]}
            for devParName in arg:
                try:
                    dev,par = devParName.split(':')
                    #print('case: ls(dev:parProp): %s:%s'%(dev,par))
                    try:
                        pv = getattr(DevDict[dev],par)
                        #print('subcase: dev:par')
                        returnedDict[devParName] = pv.info()
                    except Exception as e: 
                        #print('subcase: dev:par.prop %s, %s'%(devParName,e))
                        par,prop = par.split('.')
                        #print(dev,par,prop)
                        pv = getattr(DevDict[dev],par)
                        returnedDict[devParName] = pv.get_prop(prop)
                except Exception as e:
                    #print('case: ls(dev): %s, %s'%(devParName,e))
                    dev = DevDict[devParName]
                    returnedDict[devParName] = [i for i in vars(dev)\
                      if not i.startswith('_')]
        else:
            return {'ERR':'Wrong command "'+str(cmd)+'"'}
        return returnedDict
                
    def handle(self):
        if UDP:
            data = self.request[0].strip()
            socket = self.request[1]
        else:
            data = self.request.recv(1024).strip()
        printd('Client %s wrote:'%str(self.client_address))
        cmd = ubjson.loadb(data)
        printd(str(cmd))
        
        try:
            r = self._reply(cmd)
        except Exception as e:
            r = 'ERR. Exception: '+repr(e)
        reply = ubjson.dumpb(r)
        
        host,port = self.client_address# the port here is temporary
        printd('sending back %d bytes to %s:'%(len(reply)\
        ,str(self.client_address)))
        printd(str(reply)[:200])
        if UDP:
            socket.sendto(reply, self.client_address)
        else:
            self.request.sendall(reply)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Server```````````````````````````````````````````
class Server():
    def __init__(self,devices,host=None,port=PORT,dbg=False):
        global DevDict, Dbg
        Dbg = dbg
        
        # create Device 'server'
        dev = [Device('server',{\
          'version': PV('R','liteServer',[__version__]),
          'host':    PV('R','Host name',[socket.gethostname()]),
          'status':  PV('R','Messages from liteServer',['']),
        })]
        
        # create global dictionary of all devices
        devs = dev + list(devices)
        #DevDict = {dev._name:dev for dev in devs}
        DevDict = OD([[dev._name,dev] for dev in devs])
        #for d,i in DevDict.items():  print('device '+str(d))
                    
        self.host = host if host else ip_address()
        self.port = port
        s = SocketServer.UDPServer if UDP else SocketServer.TCPServer
        self.server = s((self.host, self.port), PV_Handler, False)
        self.server.allow_reuse_address = True
        self.server.server_bind()
        self.server.server_activate()
    
    def loop(self):
        print(__version__+'. Waiting for %s messages at %s'%(('TCP','UDP')[UDP],self.host+':'+str(self.port)))
        self.server.serve_forever()
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# see liteScalerMan.py liteAccess.py
