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
#__version__ = 'v40 2020-02-21'# rev3. value,timestamp and numpy keys shortened to v,t,n
#__version__ = 'v41 2020-02-24'# err handling for missed chunks, 'pid' corruption fixed
#__version__ = 'v42 2020-02-25'# start command added
#__version__ = 'v43 2020-02-27'# serverState and setServerStatusText
#__version__ = 'v44 2020-02-29'# do not except if type mismatch in set
#__version__ = 'v45 2020-03-02'# Exiting, numpy array unpacked
#__version__ = 'v46 2020-03-04'# test for publishing
#__version__ = 'v47 2020-03-06'# Subscription OK
__version__ = 'v48 2020-03-07'

import sys, time, threading, math, traceback
from timeit import default_timer as timer
import socket
#import SocketServer# for python2
import socketserver as SocketServer# for python3
from collections import OrderedDict as OD
import array
import ubjson

UDP = True
ChunkSize = 60000
#ChunkSize = 10000
PrefixLength = 4
ChunkSleep = 0.001 # works on localhost, 50MB/s, and on shallow network
#ChunkSleep = 0.0005 # works on localhost, 100MB/s, rare KeyError: 'pid'
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

#````````````````````````````Base Classes`````````````````````````````````````
class Device():
    server = None# It will keep the server device after initialization
    """Device object has unique _name, its members are parameters (objects,
    derived from LDO class)."""
    def __init__(self,name='?',pars=None):
        self._name = name
        #print('Dbg',Dbg)
        printd('pars '+str(pars))

        # Add parameters
        for p,v in list(pars.items()):
            #print('setting '+p+' to '+str(v))
            #print('value type:',type(v.v))
            if not isinstance(v.v,(list)):
                try:    testForNumpy = v.v.shape
                except:
                    printe('illegal type of %s: '%p+str(type(v.v)))
                    sys.exit(1)
            setattr(self,p,v)
            par = getattr(self,p)
            #setattr(par,'_name',p)
            par._name = p

    def setServerStatusText(self,txt):
        Device.server.status.v[0] = txt
        Device.server.status.t = time.time()

    def serverState(self):
        return Device.server.start.v[0]

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
        self.t = None
        self.v = value
        self.count = [len(self.v)]
        self.features = features
        self.desc = desc
        self._parent = parent
        self._subscribers = {}
        
        # absorb optional properties
        self.opLimits = opLimits
        self.legalValues = legalValues
        self._setter = setter
        
    def __str__(self):
        print('LDO object desc: %s at %s'%(self.desc,id(self)))

    def update_value(self):
        """It is called during get() and read() request to refresh the value.
        """
        #printd('default get_values called for '+self._name)
        pass

    def is_writable(self): return 'W' in self.features
    def is_readable(self): return 'R' in self.features

    def set(self,vals,prop='v'):
        #print('features %s:%s'%(self._name,str(self.features)))
        print('type(vals)',self._name,type(vals))
        if not self.is_writable():
            raise PermissionError('LDO is not writable')
        try: # pythonic way for testing if object is iterable
            test = vals[0]
        except:
            vals = [vals]
        
        # Special treatment of the boolean and action parameters
        #print('set',len(self.v),type(self.v[0]))
        if len(self.v) == 1 and isinstance(self.v[0],bool):
            vals = [True] if vals[0] else [False] 

        if type(vals[0]) is not type(self.v[0]):
            msg='Setting %s: '%self._name+str(type(vals[0]))+' to '\
            +str(type(self.v[0]))
            #raise TypeError(msg)
            printw(msg)
            
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

        self.v = vals

        # call LDO setting method with new value
        #print('self._setter of %s is %s'%(self._name,self._setter))
        if self._setter is not None:
            self._setter(self) # (self) is important!

    def info(self):
        # list all members which are not None and not prefixed with '_'
        r = [i for i in vars(self) 
          if not (i.startswith('_') or getattr(self,i) is None)]
        return r

    #````````````````````````Subscriptions````````````````````````````````````
    def subscribe(self,clientAddr,socket,request):
        """Register a new subscriber for this object""" 
        printd('subscribe '+str(request))
        if clientAddr in self._subscribers:
            printw('subscriber %s is already subscribed  for '%str(clientAddr)\
            + self._name)
            return
        self._subscribers[clientAddr] = socket,request
        print('subscription added for %s: '%self._name+str((clientAddr,request)))
        Device.server.subscriptions.v[0] += 1

    def un_subscribe(self,request):
        print('deleting subscriber %s from '%str(request)+self._name)
        try:    del self._subscribers[subscriber]
        except: pass

    def publish(self):
        """Call this when data are ready to be published to subscribers"""
        printd('>publish '+self._name)
        for clientAddr,sockReq in self._subscribers.items():
            socket,request = sockReq
            printd('publishing request of %s by %s'%(str(request)\
            ,str(clientAddr)))
            
            # check if previous delivery was succesfull
            if (socket,clientAddr) in _myUDPServer.ackCounts:
                print('previous delivery failed for '+str(clientAddr))
                print('cancel subscription for '+str(clientAddr))
                del self._subscribers[clientAddr]
                return
            _reply(['read',request], socket, clientAddr)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#``````````````````functions for socket data preparation and sending``````````
perfMBytes = 0
perfSeconds = 0
perfSends = 0
perfRetransmits = 0
def _send_UDP(buf,socket,clientAddr):
    """send buffer via UDP socket, chopping it to smaller chunks"""
    global perfMBytes, perfSeconds, perfSends
    
    # setup the EOD repetition count at the server
    _myUDPServer.ackCounts[(socket,clientAddr)] = MaxEOD

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
        socket.sendto(prefixed, clientAddr)
        time.sleep(ChunkSleep)
    dt = timer()-ts
    if lbuf > 1000:
        mbytes = 1e-6*len(buf)
        print('sent %i bytes, perf: %.1f MB/s'%(lbuf,mbytes/dt))
        perfMBytes += mbytes
        perfSeconds += dt
        perfSends += 1
        Device.server.perf.v = [perfSends, round(perfMBytes,3)\
        ,round(perfMBytes/perfSeconds,1),perfRetransmits]

def _replyData(cmdArgs):
    """Prepare data for reply"""
    global perfRetransmits
    printd('>_reply')
    try:    cmd,args = cmdArgs
    except: 
        print('cmdArgs',cmdArgs)
        if cmdArgs[0] == 'info':
            devs = list(Server.DevDict)
            return devs
        else:   raise ValueError('expect cmd,args')
    printd('cmd,args: '+str((cmd,args)))
        
    returnedDict = {}
    if cmd == 'retransmit':
        perfRetransmits += 1
        raise BufferError({'Retransmit':args})
        
    for devParPropVal in args:
        try:
            cnsDevName,sParPropVals = devParPropVal
        except Exception as e:
            msg = 'ERR.LS in _replyData for '+str(cmdArgs)
            print(msg)
            raise TypeError(msg) from e

        cnsHost,devName = cnsDevName.rsplit(',',1)
        parNames = sParPropVals[0]
        if len(sParPropVals) > 1:
            propNames = sParPropVals[1]
        else:   
            propNames = '*' if cmd == 'info' else 'v'
        printd('devNm,parNm,propNm:'+str((devName,parNames,propNames)))
        try:    vals = sParPropVals[2]
        except: vals = None
        if devName == '*':
            for devName in Server.DevDict:
                cdn = ','.join((cnsHost,devName))
                devDict = {}
                returnedDict[cdn] = devDict
                _process_parameters(cmd,parNames,devName,devDict,propNames,vals)
        else:
            if cnsDevName not in returnedDict:
                #print('add new cnsDevName',cnsDevName)
                returnedDict[cnsDevName] = {}
            devDict = returnedDict[cnsDevName]
            _process_parameters(cmd,parNames,devName,devDict,propNames,vals)
    return returnedDict

def _process_parameters(cmd,parNames,devName,devDict,propNames,vals):
    """part of _replyData"""
    if parNames[0][0] == '*':
        # replace parNames with a list of all parameters
        try:    dev = Server.DevDict[devName]
        except: raise NameError("device '%s' not served"%(str(devName)))
        #parNames = [i for i in vars(dev) if not i.startswith('_')]
        parNames = vars(dev)
    
    #print('parNames:'+str(parNames))
    for idx,parName in enumerate(parNames):
        pv = getattr(Server.DevDict[devName],parName)
        #print('parName',parName,type(pv),isinstance(pv,LDO))
        if not isinstance(pv,LDO):
            continue
        features = getattr(pv,'features','')
        if cmd == 'read' and 'R' not in features:
            #print('par %s is not readable, it will not be replied.'%parName)
            continue
        parDict = {}
        devDict[parName] = parDict
        if cmd in ('get','read'):
            #if Server.Dbg: 
            ts = timer()
            pv.update_value()
            value = getattr(pv,propNames)
            printd('value of %s=%s, timing=%.6f'%(parName,str(value)[:100],timer()-ts))
            vv = value#[0]
            try:
                # if value is numpy array:
                shape,dtype = vv.shape, str(vv.dtype)
            except Exception as e:
                #printd('not numpy %s, %s'%(pv._name,str(e)))
                parDict['v'] = value
            else:
                printd('numpy array %s, shape,type:%s, add key "n"'\
                  %(str(pv._name),str((shape,dtype))))
                parDict['v'] = vv.tobytes()
                parDict['n'] = shape,dtype
            timestamp = getattr(pv,'t',None)
            if not timestamp: timestamp = time.time()
            parDict['t'] = timestamp
        elif cmd == 'set':
            try:
                val = vals[idx]\
                  if len(parNames) > 1 else vals
            except:   raise NameError('set value missing')
            if not isinstance(val,(list,array.array)):
                val = [val]
            pv.set(val)
            printd('set: %s=%s'%(parName,str(val)))
        elif cmd == 'info':
            printd('info (%s.%s)'%(parName,str(propNames)))
            #if len(propNames[0]) == 0:
            if propNames[0] == '*':
                propNames = pv.info()
            printd('propNames of %s: %s'%(pv._name,str(propNames)))
            for propName in propNames:
                if propName == 'v': 
                    # do not return value on info() it could be very long
                    parDict['v'] = '?'
                else:
                    pv = getattr(Server.DevDict[devName],parName)
                    propVal = getattr(pv,propName)
                    parDict[propName] = propVal
        else:   raise ValueError('accepted commands: info,get,set,read')

def _reply(cmd, socket, client_address=None):
    """Build a reply data and send it to client"""
    try:
        r = _replyData(cmd)
    except Exception as e:
        if isinstance(e, BufferError ):
            print('Retransmit ignored: '+str(e))
            r = 'WARN.LS: Retransmit ignored'
        else:
            r = 'ERR.LS. Exception: '+repr(e)
            exc = traceback.format_exc()
            print('Traceback: '+repr(exc))
            return
    
    printd('reply object: '+str(r)[:200]+'...'+str(r)[-40:])
    reply = ubjson.dumpb(r)
    
    host,port = client_address# the port here is temporary
    printd('sending back %d bytes to %s:'%(len(reply)\
    ,str(client_address)))
    printd(str(reply)[:200])

    if UDP:
        _send_UDP(reply, socket, client_address)
        # initiate the sending of EOD to that client
    else:
        #self.request.sendall(reply)
        print('TCP not supported yet')
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````The Request broker```````````````````````````````
class _LDO_Handler(SocketServer.BaseRequestHandler):
    lastPID = '?'
                 
    def handle(self):
        """Override the handle method"""
        if UDP:
            data = self.request[0].strip()
            socket = self.request[1]
            if data == b'ACK':
                printd('Got ACK from %s'%str(self.client_address))
                try:
                    del self.server.ackCounts[(socket,self.client_address)]
                except Exception as e:
                    printw('no ACK to delete from '+str(self.client_address))
                return
        else:
            data = self.request.recv(1024).strip()

        printd('Client %s wrote:'%str(self.client_address))
        cmd = ubjson.loadb(data)
        printd(str(cmd))

        # retrieve previous source to server.lastPID LDO
        try:
            Device.server.lastPID.v[0] = _LDO_Handler.lastPID
            # remember current source 
            _LDO_Handler.lastPID = '%s;%i %s %s'%(*self.client_address\
            ,cmd['pid'], cmd['username'], )
            #print('lastPID now',_LDO_Handler.lastPID)
        except:
            pass

        try:    cmdArgs =  cmd['cmd']
        except: raise  KeyError("'cmd' key missing in request")

        if  cmdArgs[0] == 'subscribe':
            self.register_subscriber(self.client_address, socket, cmdArgs[1])
            return

        _reply(cmdArgs,socket,self.client_address)
        
    def register_subscriber(self,clientAddr,socket,serverCmdArgs):
        print('register subscriber for '+str(serverCmdArgs))
        # the first dev,ldo in the list will trigger the publishing
        try:    cnsDevName,parPropVals = serverCmdArgs[0]
        except: raise NameError('cnsDevName,parPropVals wrong: '+serverCmdArgs)
        cnsHost,devName = cnsDevName.rsplit(',',1)
        parName = parPropVals[0][0]
        if parName == '*':
            dev = Server.DevDict[devName]
            pvars = vars(dev)
            # use first LDO of the device
            for parName,val in pvars.items():
                if isinstance(val,LDO):
                    printd('ldo %s, features '%parName+val.features)
                    if 'R' in val.features:
                        break
            print('The master parameter: '+parName)
        pv = getattr(Server.DevDict[devName],parName)
        pv.subscribe(clientAddr,socket,serverCmdArgs)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Server```````````````````````````````````````````
class _myUDPServer(SocketServer.UDPServer):
    """Subclass the UDPServer to override the service_actions()"""
    ackCounts = {}
    def __init__(self,hostPort, handler):
        super().__init__(hostPort, handler, False)
        #self.handler = handler

    def service_actions(self):
        """service_actions() called by server periodically (0.5s)"""
        for sockAddr,ackCount in list(_myUDPServer.ackCounts.items()):
            sock,addr = sockAddr
            if ackCount == 1:
                _myUDPServer.ackCounts[sockAddr] = 0
                printw('No ACK from %s'%str(addr))
                #del _myUDPServer.ackCounts[sockAddr]
                return
            if ackCount <= 0:
                return

            # keep sending EODs to that client until it detects it
            print('waiting for ACK%i from '%ackCount+str(addr))
            _myUDPServer.ackCounts[sockAddr] -= 1
            sock.sendto(b'\x00\x00\x00\x00',addr)
            
class LDOt(LDO):
    '''LDO, returning current time.''' 
    # override data updater
    def update_value(self):
        self.v = [time.time()]
        self.t = time.time()

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
              'start':LDO('RW','Start/Stop',['Started']\
              , legalValues=['Start','Stop','Exit'],setter=self._start_set),
              'version':LDO('','liteServer',[__version__]),
              'host':   LDO('','Host name',[socket.gethostname()]),
              'status': LDO('R','Messages from liteServer',['']),
              'time':   LDOt('R','server time',[0.]),
              'debug':  LDO('W','debugging level: 14:ERROR, 13:WARNING, 12:INFO, 11-1:DEBUG, bits[15:4] are for user needs'\
              ,[Server.Dbg],setter=self._debug_set),
              'lastPID': LDO('','report source of the last request ',['?']),
              'perf':   LDO('R'\
                ,'Server performance [RQ,MBytes,MBytes/s],Retransmits'\
                ,[0.,0.,0.,0]),
              'subscriptions': LDO('R','Number of subscriptions',[0]),
            })]
        else: dev = []
        
        # create global dictionary of all devices
        devs = dev + list(devices)
        Server.DevDict = OD([[dev._name,dev] for dev in devs])
                    
        self.host = host if host else ip_address()
        self.port = port
        s = _myUDPServer if UDP else SocketServer.TCPServer
        self.server = s((self.host, self.port), _LDO_Handler)#, False)
        self.server.allow_reuse_address = True
        self.server.server_bind()
        self.server.server_activate()
        print('Server instantiated')

    def loop(self):
        Device.server = Server.DevDict['server']
        print(__version__+'. Waiting for %s messages at %s'%(('TCP','UDP')[UDP],self.host+';'+str(self.port)))
        self.server.serve_forever()
        
    def _debug_set(self,par):
        par_debug = Device.server.debug.v
        print('par_debug',par_debug)
        Server.Dbg = par_debug[0]
        print('Debugging level set to '+str(Server.Dbg))

    def _start_set(self,pv):
        cmd = Device.server.start.v[0]
        print('Server state: '+cmd)
        if cmd == 'Exit':
            print('Exiting')
            EventExit.set()
            sys.exit()
        Device.server.start.v[0] = 'Started'\
          if cmd == 'Start' else 'Stopped'

    def par_set(self,par):
        """Generic parameter setter"""
        parVal = par.v
        print('par_set %s='%par.name + str(parval))
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# see liteScaler.py, liteAccess.py
