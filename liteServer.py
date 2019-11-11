#!/usr/bin/env python3
"""Very lightweight base class of the Process Variable Server.
It hosts the process variables and responds to get/set/monitor/info commands.

Transport protocol: UDP with handshaking and re-transmission. 

Encoding protocol: UBJSON. It takes care about parameter types.

Dependecies: py-ubjson, very simple and efficient data serialization protocol

Performance: liteServer is fastest possible python access to parameters over ethernet.

Example usage:
- start liteServer for 2 Scalers on a remote host:
liteScaler.py
- get list of devices on a remote host:
liteAccess.py -i host::
- simple GUI to control remote liteServer on a host:
PVsheet.py -Hhost

Known issues:
  The implemented UDP-based transport protocol works reliable on 
  point-to-point network connection but may fail on a multi-hop network. 
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
#__version__ = 'v19 2019-06-09'# numpy array support
#__version__ = 'v20 2019-06-10'# UDP Acknowledge
#__version__ = 'v20 2019-06-10'# framing works 
#__version__ = 'v21 2019-06-10'# chunking OK
#__version__ = 'v22a 2019-06-17'# release
#__version__ = 'v23a 2019-06-21'# redesign
#__version__ = 'v24 2019-11-07'# release
#__version__ = 'v24 2019-11-08'# PV.parent removed, it conflicts with json
__version__ = 'v24 2019-11-10'# Dbg and devDict are Server attributes 

import sys
import socket
#import SocketServer# for python2
import socketserver as SocketServer# for python3
import time
from timeit import default_timer as timer
from collections import OrderedDict as OD
import ubjson
import threading
import math
import traceback

UDP = True
ChunkSize = 60000
#ChunkSize = 10000
PrefixLength = 4
ChunkSleep = 0.001 # works on localhost, 50MB/s, and on shallow network

MaxEOD = 4

PORT = 9700# Communication port number
EventExit = threading.Event()

#````````````````````````````Helper functions`````````````````````````````````
def printi(msg): print('info: '+msg)
def printw(msg): print('WARNING: '+msg)
def printe(msg): print('ERROR: '+msg)
def printd(msg):
    if Server.Dbg: print('dbgServ: '+str(msg))

def ip_address():
    """Platform-independent way to get local host IP address"""
    return [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close())\
      for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]

def tostr(item):
    return item if isinstance(item,str) else item.decode()

def sendUdp(buf,socket,addr):
    # send buffer via UDP socked, chopping it to smaller chunks
    lbuf = len(buf)
    #print('>sendUdp %i bytes'%lbuf)
    ts = timer()
    nChunks = (lbuf-1)//ChunkSize + 1
    # send chunks in backward order
    for iChunk in range(nChunks-1,-1,-1):
        chunk = buf[iChunk*ChunkSize:min((iChunk+1)*ChunkSize,lbuf)]
        prefixInt = iChunk*ChunkSize
        #print('pi',prefixInt)
        prefixBytes = (prefixInt).to_bytes(PrefixLength,'big')
        prefixed = b''.join([prefixBytes,chunk])
        #txt = str(chunk)
        #if len(txt) > 100:
        #    txt = txt[:100]+'...'
        #print('sending prefix %i'%prefixInt+' %d bytes:'%len(prefixed),txt)
        socket.sendto(prefixed, addr)
        time.sleep(ChunkSleep)
    dt = timer()-ts
    if lbuf > 1000:
        print('sent %i bytes, perf: %.1f MB/s'%(lbuf,1e-6*len(buf)/dt))

#````````````````````````````Base Classes`````````````````````````````````````
class Device():
    """Device object has unique _name, its members are parameters (objects,
    derived from PV class).
    """
    def __init__(self,name='?',pars=None):
        self._name = name
        #print('Dbg',Dbg)
        printd('pars '+str(pars))
        for p,v in pars.items():
            #print('setting '+p+' to '+str(v))
            #print('value type:',type(v.value))
            if not isinstance(v.value,list):
                printe('parameter "'+p+'" should be a list')
                sys.exit(1)
            setattr(self,p,v)
            par = getattr(self,p)
            #setattr(par,'_name',p)
            par._name = p
        
class PV():
    """Base class for Process Variables. Standard properties:
    value, count, timestamp, features, decription.
    value should be iterable! It simplifies internal logic.
    The type and count is determined from default value.
    Features is string, containing letters from 'RWD'.
    More properties can be added in derived classes"""
    def __init__(self,features='RW', desc='', value=[0]\
        ,opLimits=None, setter=None, parent=None):#, numpy=None):
        printd('>PV: '+str((features,desc,value,opLimits,parent)))
        self._name = None # assighned in device.__init__. 
        # name is not really needed, as it is keyed in the dictionary
        self.timestamp = None
        self.value = value
        self.count = [len(self.value)]
        self.features = features
        self.desc = desc
        self._parent = parent
        
        # if the parameter is numpy :
        try:    
            shape,dtype = value[0].shape, value[0].dtype
            printd('par is numpy')
        except: 
            pass
        
        # absorb optional properties
        self.opLimits = opLimits
        self._setter = setter
        #self.numpy = numpy# for numpy array it is: (shape,dtype)
        
    def __str__(self):
        print('PV object desc: %s at %s'%(self.desc,id(self)))

    def update_value(self):
        """Overridable getter"""
        printd('default get_values')
        pass

    def is_writable(self): return 'W' in self.features
    def is_readable(self): return 'R' in self.features

    def set(self,vals,prop='value'):
        #print('features %s:%s'%(self._name,str(self.features)))
        if not self.is_writable():
            raise PermissionError('PV is not writable')
        try: # pythonic way for testing if object is iterable
            test = vals[0]
        except:
            vals = [vals]

        # Special treatment of the boolean and action parameters
        #print('set',len(self.value),type(self.value[0]))
        if len(self.value) == 1 and isinstance(self.value[0],bool):
            #print('Boolean treatment %s'%str(vals))
            # the action parameter is the boolean one but not reabable
            # it always is False
            if not self.is_readable():
                print('Action treatment')
                vals = [False]
                # call PV setting method
                if self._setter is not None:
                    self._setter(self) # (self) is important!
            else: # make it boolean 
                vals = [True] if vals[0] else [False] 

        if type(vals[0]) is not type(self.value[0]):
            printe('Cannot assign '+str(type(vals[0]))+' to '\
            + str(type(self.value[0])))
            raise TypeError('Cannot assign '+str(type(vals[0]))+' to '\
            + str(type(self.value[0])))
            
        if self.opLimits is not None:
            printd('checking for opLimits')
            if vals[0] <= self.opLimits[0] or vals[0] >= self.opLimits[1]:
                raise ValueError('out of opLimits '+str(self.opLimits)+': '\
                + str(vals[0]))

        self.value = vals
        
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

    def _reply(self,serverMsg):
        #printd('>_reply [%d'%len(serverMsg)+', type:'+str(type(serverMsg[0])))
        printd('>_reply')
        try:
            cmd,args = serverMsg['cmd']
            devs = args[0]
            if len(devs[0]) == 0:
                devs = [i[0] for i in Server.DevDict.items()]
                if len(args[1][0])+len(args[2][0]) == 0:
                    return devs
        except Exception as e:
            raise ValueError('serverMsg:%s, exc:'%str(serverMsg)+str(e))
        printd('devs:'+str(devs))
        returnedDict = {}
        for devName in devs:
          parNames = args[1]
          if len(parNames[0]) == 0:
            # replace parNames with a list of all parameters
            dev = Server.DevDict[devName]
            parNames = [i for i in vars(dev) if not i.startswith('_')]
          printd('parNames:'+str(parNames))
          for parName in parNames:
            pv = getattr(Server.DevDict[devName],parName)
            devParName = devName+':'+parName
            parDict = {}
            returnedDict[devParName] = parDict
            if cmd == 'get':
                self.value = pv.update_value()
                value = getattr(pv,'value')
                printd('value:'+str(value))
                try:
                    # if value is numpy array:
                    shape,dtype = value[0].shape, str(value[0].dtype)
                except Exception as e:
                    printd('not numpy %s, %s'%(pv._name,str(e)))
                    parDict['value'] = value
                else:
                    printd('numpy array %s, shape,type:%s, add key "numpy"'\
                      %(str(pv._name),str((shape,dtype))))
                    parDict['value'] = value[0].tobytes()
                    parDict['numpy'] = shape,dtype
            elif cmd == 'set':
                try:    val = args[3]
                except:
                    raise NameError('expected host,dev,par,prop,value, got '+str(args))
                if not isinstance(val,list):
                    val = [val]
                pv.set(val)
                printd('set: %s=%s'%(parName,str(val)))
            elif cmd == 'info':
                try:    propNames = args[2]
                #except: propNames[0] == ['*']
                except: propNames[0] == ['']
                printd('info (%s.%s)'%(parName,str(propNames)))
                #if propNames[0] == '*':
                if len(propNames[0]) == 0:
                    propNames = pv.info()
                printd('propNames of %s: %s'%(pv._name,str(propNames)))
                for propName in propNames:
                    if propName == 'value': 
                        # do not return value on info() it could be very long
                        parDict['value'] = '?'
                    else:
                        pv = getattr(Server.DevDict[devName],parName)
                        propVal = getattr(pv,propName)
                        parDict[propName] = propVal
        return returnedDict
                
    def handle(self):
        if UDP:
            data = self.request[0].strip()
            socket = self.request[1]
            if data == b'ACK':
                printd('Got ACK from %s'%str(self.client_address))
                del self.server.ackCounts[(socket,self.client_address)]
                return
        else:
            data = self.request.recv(1024).strip()
        printd('Client %s wrote:'%str(self.client_address))
        cmd = ubjson.loadb(data)
        printd(str(cmd))
        
        try:
            r = self._reply(cmd)
        except Exception as e:
            r = 'ERR. Exception: '+repr(e)
            exc = traceback.format_exc()
            print('Traceback: '+repr(exc))
        
        printd('reply object: '+str(r)[:200]+'...'+str(r)[-40:])
        reply = ubjson.dumpb(r)
        
        host,port = self.client_address# the port here is temporary
        printd('sending back %d bytes to %s:'%(len(reply)\
        ,str(self.client_address)))
        printd(str(reply)[:200])

        if UDP:
            sendUdp(reply, socket, self.client_address)
            # initiate the sending of EOD to that client
            self.server.ackCounts[(socket,self.client_address)] = MaxEOD
        else:
            self.request.sendall(reply)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Server```````````````````````````````````````````
class myUDPServer(SocketServer.UDPServer):
    """Subclass the UDPServer to override the service_actions()"""
    def __init__(self,hostPort, handler):
        super().__init__(hostPort, handler, False)
        #self.handler = handler
        self.ackCounts = {}

    def service_actions(self):
        """service_actions() called by server periodically (0.5s)"""
        #printd('ackCounts: %s'%str(self.ackCounts))
        
        for sockAddr,ackCount in self.ackCounts.items():
            sock,addr = sockAddr
            if ackCount == 0:
                printw('No ACK from %s'%str(addr))
                del self.ackCounts[sockAddr]
                return
            # keep sending EODs to that client
            printd('waiting for ACK%i from '%ackCount+str(addr))
            self.ackCounts[sockAddr] -= 1
            sock.sendto(b'\x00\x00\x00\x00',addr)
            
class Server():
    '''liteServer object'''
    
    #``````````````Attributes`````````````````````````````````````````````````
    Dbg = False
    DevDict = None
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #``````````````Instantiation``````````````````````````````````````````````
    def __init__(self,devices,host=None,port=PORT,dbg=False):
        print('Server.Dbg',Server.Dbg)
        # create Device 'server'
        dev = [Device('server',{\
          'version': PV('R','liteServer',[__version__]),
          'host':    PV('R','Host name',[socket.gethostname()]),
          'status':  PV('R','Messages from liteServer',['']),
        })]
        
        # create global dictionary of all devices
        devs = dev + list(devices)
        #DevDict = {dev._name:dev for dev in devs}
        Server.DevDict = OD([[dev._name,dev] for dev in devs])
        #for d,i in DevDict.items():  print('device '+str(d))
        #print('DevDict',Server.DevDict)
                    
        self.host = host if host else ip_address()
        self.port = port
        s = myUDPServer if UDP else SocketServer.TCPServer
        self.server = s((self.host, self.port), PV_Handler)#, False)
        self.server.allow_reuse_address = True
        self.server.server_bind()
        self.server.server_activate()
        print('Server instantiated')
    
    def loop(self):
        print(__version__+'. Waiting for %s messages at %s'%(('TCP','UDP')[UDP],self.host+';'+str(self.port)))
        self.server.serve_forever()
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# see liteScaler.py liteAccess.py
