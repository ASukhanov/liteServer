"""Very lightweight base class of the Lite Data Object Server.
It hosts the Lite Data Objects and responds to get/set/monitor/info commands.

Transport protocol: UDP with handshaking and re-transmission. 

Encoding protocol: UBJSON. It takes care about parameter types.

Dependecies: py-ubjson, very simple and efficient data serialization protocol

Performance: liteServer is fastest possible python access to parameters over ethernet.

message format:
  {'cmd':[command,[[dev1,dev2,...],[arg1,arg2,...]]],
  'user':user,...}

Supported commands:
- info      reply with information of LDOs
- get       reply with values of LDOs
- read      reply with values of readable LDOs only, 
            readable LDO have 'R' in their feature, 
- set       set values of LDOs
- ACK       internal, response from a client on server reply
- subscribe not implemented yet, send reply when LDO has changed.

Example usage:
- start liteServer for 2 Scalers on a remote host:
liteScaler.py
- get list of devices on a remote host:
liteAccess.py -i host::
- simple GUI to control remote liteServer on a host:
LDOsheet.py -Hhost

Known issues:
  The implemented UDP-based transport protocol works reliable on 
  point-to-point network connection but may fail on a multi-hop network. 
"""
#__version__ = 'v34 2020-02-07'# wildcarding with *
#__version__ = 'v35 2020-02-08'# 'read' instead of 'measure'
__version__ = 'v36 2020-02-09'# PV replaced with LDO

import sys, time, threading, math, traceback
from timeit import default_timer as timer
import socket
#import SocketServer# for python2
import socketserver as SocketServer# for python3
from collections import OrderedDict as OD
import ubjson

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

def _send_UDP(buf,socket,addr):
    # send buffer via UDP socked, chopping it to smaller chunks
    lbuf = len(buf)
    #print('>_send_UDP %i bytes'%lbuf)
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
    derived from LDO class)."""
    def __init__(self,name='?',pars=None):
        self._name = name
        #print('Dbg',Dbg)
        printd('pars '+str(pars))
        for p,v in list(pars.items()):
            #print('setting '+p+' to '+str(v))
            #print('value type:',type(v.value))
            if not isinstance(v.value,list):
                printe('parameter "'+p+'" should be a list')
                sys.exit(1)
            setattr(self,p,v)
            par = getattr(self,p)
            #setattr(par,'_name',p)
            par._name = p
        
class LDO():
    """Base class for Lite Data Objects. Standard properties:
    value, count, timestamp, features, decription.
    value should be iterable! It simplifies internal logic.
    The type and count is determined from default value.
    Features is string, containing letters from 'RWD'.
    More properties can be added in derived classes"""
    def __init__(self,features='RW', desc='', value=[0], opLimits=None\
        , legalValues=None, setter=None, parent=None):
        printd('>LDO: '+str((features,desc,value,opLimits,parent)))
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
        self.legalValues = legalValues
        self._setter = setter
        #self.numpy = numpy# for numpy array it is: (shape,dtype)
        
    def __str__(self):
        print('LDO object desc: %s at %s'%(self.desc,id(self)))

    def update_value(self):
        """Overridable getter"""
        #printd('default get_values called for '+self._name)
        pass

    def is_writable(self): return 'W' in self.features
    def is_readable(self): return 'R' in self.features

    def set(self,vals,prop='value'):
        #print('features %s:%s'%(self._name,str(self.features)))
        if not self.is_writable():
            raise PermissionError('LDO is not writable')
        try: # pythonic way for testing if object is iterable
            test = vals[0]
        except:
            vals = [vals]
        
        # Special treatment of the boolean and action parameters
        #print('set',len(self.value),type(self.value[0]))
        if len(self.value) == 1 and isinstance(self.value[0],bool):
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

        if self.legalValues is not None:
            print('checking for legalValues %s = '%self._name+str(vals[0]))
            if vals[0] not in self.legalValues:
                raise ValueError('not a legal value of %s:'\
                %self._name+str(vals[0]))

        self.value = vals

        # call LDO setting method with new value
        #print('self._setter of %s is %s'%(self._name,self._setter))
        if self._setter is not None:
            self._setter(self) # (self) is important!
        
    def subscribe(self,callback):
        raise NotImplementedError('LDO.subscribe() is not implemented yet')

    def info(self):
        # list all members which are not None and not prefixed with '_'
        r = [i for i in vars(self) 
          if not (i.startswith('_') or getattr(self,i) is None)]
        return r
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````The Request broker```````````````````````````````
class _LDO_Handler(SocketServer.BaseRequestHandler):

    def _reply(self,serverMsg):
        #printd('>_reply [%d'%len(serverMsg)+', type:'+str(type(serverMsg[0])))
        printd('>_reply')
        try:    replyCmd =  serverMsg['cmd']
        except: raise  KeyError("'cmd' key missing in request")
        try:    cmd,args = replyCmd
        except: 
            #cmd,args = replyCmd[0],[['']]
            print('replyCmd',replyCmd)
            if replyCmd[0] == 'info':
                devs = [i[0] for i in list(Server.DevDict.items())]
                return devs
            else:   raise ValueError('expect cmd,args')
        printd('cmd,args: '+str((cmd,args)))
        returnedDict = {}

        for devParPropVal in args:
          devName,parPropValNames = devParPropVal
          parNames = parPropValNames[0]
          if len(parPropValNames) > 1:
            propNames = parPropValNames[1]
          else:   
            propNames = propNames = ['*'] if cmd == 'info' else ['value']
          printd('devNm,parNm,propNm:'+str((devName,parNames,propNames)))
          if parNames[0][0] == '*':
            # replace parNames with a list of all parameters
            dev = Server.DevDict[devName]
            parNames = [i for i in vars(dev) if not i.startswith('_')]
          printd('parNames:'+str(parNames))
          for parName in parNames:
            pv = getattr(Server.DevDict[devName],parName)
            features = getattr(pv,'features','')
            if cmd == 'read' and 'R' not in features:
                #print('par %s is not readable, it will not be replied.'%parName)
                continue
            devParName = devName+':'+parName
            parDict = {}
            returnedDict[devParName] = parDict
            if cmd in ('get','read'):
                #if Server.Dbg: 
                ts = timer()
                pv.update_value()
                value = getattr(pv,propNames[0])
                printd('value of %s=%s, timing=%.6f'%(devParName,str(value)[:100],timer()-ts))
                try:
                    # if value is numpy array:
                    shape,dtype = value[0].shape, str(value[0].dtype)
                except Exception as e:
                    #printd('not numpy %s, %s'%(pv._name,str(e)))
                    parDict['value'] = value
                else:
                    printd('numpy array %s, shape,type:%s, add key "numpy"'\
                      %(str(pv._name),str((shape,dtype))))
                    parDict['value'] = value[0].tobytes()
                    parDict['numpy'] = shape,dtype
                timestamp = getattr(pv,'timestamp',None)
                if not timestamp: timestamp = time.time()
                parDict['timestamp'] = timestamp
            elif cmd == 'set':
                try:    val = parPropValNames[2]
                except:   raise NameError('set value missing')
                if not isinstance(val,list):
                    val = [val]
                pv.set(val)
                printd('set: %s=%s'%(parName,str(val)))
            elif cmd == 'info':
                printd('info (%s.%s)'%(parName,str(propNames)))
                #if len(propNames[0]) == 0:
                if propNames[0][0] == '*':
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
            else:   raise ValueError('accepted commands: info,get,set,read')
        return returnedDict
                
    def handle(self):
        """Override handle method"""
        if UDP:
            data = self.request[0].strip()
            socket = self.request[1]
            if data == b'ACK':
                printd('Got ACK from %s'%str(self.client_address))
                try:
                    del self.server.ackCounts[(socket,self.client_address)]
                except Exception as e:
                    printw('deleting ackCounts: '+str(e))
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
            _send_UDP(reply, socket, self.client_address)
            # initiate the sending of EOD to that client
            self.server.ackCounts[(socket,self.client_address)] = MaxEOD
        else:
            self.request.sendall(reply)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Server```````````````````````````````````````````
class _myUDPServer(SocketServer.UDPServer):
    """Subclass the UDPServer to override the service_actions()"""
    def __init__(self,hostPort, handler):
        super().__init__(hostPort, handler, False)
        #self.handler = handler
        self.ackCounts = {}

    def service_actions(self):
        """service_actions() called by server periodically (0.5s)"""
        #printd('ackCounts: %s'%str(self.ackCounts))
        
        for sockAddr,ackCount in list(self.ackCounts.items()):
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
    """liteServer object"""
    #``````````````Attributes`````````````````````````````````````````````````
    Dbg = 10
    DevDict = None
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #``````````````Instantiation``````````````````````````````````````````````
    def __init__(self,devices,host=None,port=PORT,dbg=False,serverPars=True):
        print('Server,Dbg',Server.Dbg)
        # create Device 'server'
        if serverPars:
            dev = [Device('server',{\
              'version':LDO('','liteServer',[__version__]),
              'host':   LDO('','Host name',[socket.gethostname()]),
              'status': LDO('R','Messages from liteServer',['']),
              'debug':  LDO('W','debugging level: 14:ERROR, 13:WARNING, 12:INFO, 11-1:DEBUG, bits[15:4] are for user needs'\
              ,[Server.Dbg],setter=self._debug_set),
              'tstInt': LDO('W','test integer variables',[1,2],setter=self.par_set),
            })]
        else: dev = []
        
        # create global dictionary of all devices
        devs = dev + list(devices)
        #DevDict = {dev._name:dev for dev in devs}
        Server.DevDict = OD([[dev._name,dev] for dev in devs])
        #for d,i in DevDict.items():  print('device '+str(d))
        #print('DevDict',Server.DevDict)
                    
        self.host = host if host else ip_address()
        self.port = port
        s = _myUDPServer if UDP else SocketServer.TCPServer
        self.server = s((self.host, self.port), _LDO_Handler)#, False)
        self.server.allow_reuse_address = True
        self.server.server_bind()
        self.server.server_activate()
        print('Server instantiated')
    
    def loop(self):
        print(__version__+'. Waiting for %s messages at %s'%(('TCP','UDP')[UDP],self.host+';'+str(self.port)))
        self.server.serve_forever()
        
    def _debug_set(self,par):
        par_debug = Server.DevDict['server'].debug.value
        print('par_debug',par_debug)
        Server.Dbg = par_debug[0]
        print('Debugging level set to '+str(Server.Dbg))

    def par_set(self,par):
        """Generic parameter setter"""
        parVal = par.value
        print('par_set %s='%par.name + str(parval))
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# see liteScaler.py liteAccess.py
