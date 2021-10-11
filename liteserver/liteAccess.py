"""Module for accessing multiple Process Variables, served by a liteServer.
"""
__version__ = '1.0.4 2021-09-24'# Do not proceed if host IP is not resolved

#TODO: replace ubjson with mgspack

import sys, time, socket
from os import getpid
import getpass
from timeit import default_timer as _timer
import threading
recvLock = threading.Lock()

#from pprint import pformat, pprint
import ubjson

#````````````````````````````Globals``````````````````````````````````````````
UDP = True
Port = 9700
PrefixLength = 4
socketSize = 1024*64 # max size of UDP transfer
Dev,Par = 0,1
NSDelimiter = ':'# delimiter in the name field

Username = getpass.getuser()
Program = sys.argv[0]
PID = getpid()
def get_user():
	print(f'liteAcces user:{Username}, PID:{PID}, program:{Program}')
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Helper functions`````````````````````````````````
MaxPrint = 500
def _croppedText(obj, limit=200):
    txt = str(obj)
    if len(txt) > limit:
        txt = txt[:limit]+'...'
    return txt
def _printTime(): return time.strftime("%m%d:%H%M%S")
def _printi(msg): 
    print(_croppedText(f'INFO.LA@{_printTime()}: '+msg))

def _printw(msg):
    msg = msg = _croppedText(f'WARN.LA@{_printTime()}: '+msg)
    print(msg)
    #Device.setServerStatusText(msg)

def _printe(msg): 
    msg = _croppedText(f'ERROR.LA@{_printTime()}: '+msg)
    print(msg)
    #Device.setServerStatusText(msg)

def _printd(msg):
    if PVs.Dbg or Access.Dbg : print('Dbg.LA: '+msg)

def _croppedText(txt, limit=200):
    if len(txt) > limit:
        txt = txt[:limit]+'...'
    return txt

def testCallback(args):
    _printi(_croppedText(f'>testCallback({args})'))

def _printCallback(args):
    print(f'subcribed item received:\n{args}')

def ip_address():
    """Platform-independent way to get local host IP address"""
    return [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close())\
        for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]

CNSMap = {}# local map of cnsName to host:port
def _hostPort(cnsNameDev:tuple):
    """Return host;port of the cnsName,Dev try it first from already 
    registered records, or from the name service"""
    global CNSMap
    if len(cnsNameDev) == 1:
        _printe(f'Device name wrong: {cnsNameDev}, should be of the form: host:dev')
        sys.exit(1)
    cnsName,dev = cnsNameDev
    if isinstance(cnsName,list):
        cnsName = tuple(cnsName)
    # _printd(f'>_hostPort: {cnsNameDev}')
    try:  
        hp,dev = CNSMap[cnsName]# check if cnsName is in local map
    except  KeyError:
        from . import liteCNS
        _printi(f'cnsName {cnsName} not in local map: {CNSMap}')
        try:
            hp = liteCNS.hostPort(cnsName)
        #except NameError:
        except Exception as e:
            msg = (f'The host name {cnsName} is not in liteCNS: {e}\n'
                f"Trying to use it as is: '{cnsName}'")
            #raise   NameError(msg)
            _printw(msg)
            hp = cnsName
        # register externally resolved cnsName in local map
        hp = hp.split(';')
        hp = tuple(hp) if len(hp)==2 else (hp[0],Port)            
        #_printi('cnsName %s is locally registered as '%cnsName+str((hp,dev)))
        CNSMap[cnsName] = hp,dev
        _printi(f'Assuming host,port: {hp}')
    except ValueError:
        _printe(f'Device name {cnsName} wrong, it should be in form host:device ')
        sys.exit(1)
    h,p = hp
    try:
        h = socket.gethostbyname(h)
    except:
        _printe(f'Could not resolve host name {h}')
        sys.exit(1)
    return h,p

retransmitInProgress = None
def _recvUdp(sock, socketSize):
    """Receive the chopped UDP data"""
    port = sock.getsockname()[1]
    #print(f'>_recvUdp {port} locked: {recvLock.locked()}')
    #with recvLock:
    global retransmitInProgress
    chunks = {sock:{}}
    tryMore = 5# Max number of allowed lost packets
    ts = _timer()
    ignoreEOD = 3

    def ask_retransmit(offsetSize):
        global retransmitInProgress
        retransmitInProgress = tuple(offsetSize)
        cmd = {'cmd':('retransmit',offsetSize)}
        _printi(f'Asking to retransmit port {port}: {cmd}')
        sock.sendto(ubjson.dumpb(cmd),addr)
    
    while tryMore:
        try:
            buf, addr = sock.recvfrom(socketSize)
        #else:#except Exception as e:
        except socket.timeout as e:
            msg = f'Timeout in recvfrom port {port}'
            _printi(msg)
            raise
            # Don not return, raise exception, otherwise the pypet will not recover
            #_printw(msg)
            #return [],0
            #return ('WARNING: '+msg).encode(), 0
            #buf = None
        if buf is None:
            raise RuntimeError(msg)
        size = len(buf) - PrefixLength
        offset = int.from_bytes(buf[:PrefixLength],'big')# python3
        
        #DNP_printi(f'chunk received at port {port}: {offset,size}')

        if size > 0:
            chunks[sock][offset,size] = buf[PrefixLength:]
        if offset > 0 and not retransmitInProgress:
            # expect more chunks to come
            continue

        # check if chunk is EOD, i.e. offset,size = 0,0
        if size == 0:
            ignoreEOD -= 1
            if ignoreEOD >= 0:
                #print(f'premature EOD{ignoreEOD} received from, ignore it')
                continue
            else:
                msg = f'Looks like first chunk is missing at port {port}'
                _printw(msg)
                #This is hard to recover. Give up
                return [],0
                #return ('WARNING: '+msg).encode(), addr
                # sortedKeys = sorted(chunks[sock])
                # offsetSize = [0,sortedKeys[0][0]]
                # allAssembled = False
                # ask_retransmit(offsetSize)
                # break
        else:
            #print('First chunk received')
            pass

        if retransmitInProgress is not None:
            if (offset,size) in chunks[sock]:
                _printi(f'retransmission received {offset,size}')
            else:
                _printw(f'server failed to retransmit chunk {retransmitInProgress}')
                tryMore = 1
            retransmitInProgress = None

        # last chunk have been received, offset==0, size!=0
        # check for lost  chunks
        sortedKeys = sorted(chunks[sock])
        prev = [0,0]
        allAssembled = True
        for offset,size in sortedKeys:
            #print('check offset,size:'+str((offset,size)))
            last = prev[0] + prev[1]
            if last != offset:
                l = offset - last
                if l > 65536:
                    msg = f'Lost too many bytes at port {port}: {last,l}, data discarded'
                    _printw(msg)
                    #raise RuntimeError(msg)
                    return [],0
                    #return 'WARNING: '+msg, addr
                ask_retransmit((last, l))
                allAssembled = False
                break
            prev = [offset,size]

        if allAssembled:
            break
        #print(f'tryMore: {tryMore}')
        tryMore -= 1
    ts1 = _timer()
        
    if not allAssembled:
        msg = 'Partial assembly of %i frames'%len(chunks[sock])
        #raise BufferError(msg)
        _printw(msg)
        return [],0
        #return ('WARNING: '+msg).encode(), addr

    data = bytearray()
    sortedKeys = sorted(chunks[sock])
    for offset,size in sortedKeys:
        # _printd('assembled offset,size '+str((offset,size)))
        data += chunks[sock][(offset,size)]
    tf = _timer()
    # if len(data) > 500000:
        # _printd('received %i bytes in %.3fs, assembled in %.6fs'\
        # %(len(data),ts1-ts,tf-ts1))
    #_printi('assembled %i bytes'%len(data))
    return data, addr

def _send_dictio(dictio, sock, hostPort:tuple):
    """low level send"""
    global LastDictio
    LastDictio = dictio.copy()
    # _printd('executing: '+str(dictio))
    dictio['username'] = Username
    dictio['program'] = Program
    dictio['pid'] = PID
    # _printd(f'send_dictio to {hostPort}: {dictio}')
    encoded = ubjson.dumpb(dictio)
    if UDP:
        sock.sendto(encoded, hostPort)
    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(hostPort)
        except Exception as e:
            _printe('in sock.connect:'+str(e))
            sys.exit()
        sock.sendall(encoded)

def _send_cmd(cmd, devParDict:dict, sock, hostPort:tuple, values=None):
    import copy
    #DNPprint(f'_send_cmd({cmd}.{devParDict}')
    if cmd == 'set':
        if len(devParDict) != 1:
            raise ValueError('Set is supported for single device only')
        #devParDict = copy.deepcopy(devParDict)# that is IMPORTANT! otherwise setting in liteScaler.yaml is failing 
        #for key,value in zip(devParDict,values):
        #    devParDict[key] += 'v',value
        for key in devParDict:
            devParDict[key] += 'v',values
    devParList = list(devParDict.items())
    dictio = {'cmd':(cmd,devParList)}
    # _printd('sending cmd: '+str(dictio))
    _send_dictio(dictio, sock, hostPort)

def _llTransaction(dictio, sock, hostPort:tuple):
    # low level transaction
    _send_dictio(dictio, sock, hostPort)
    return  receve_dictio()

def _receive_dictio(sock, hostPort:tuple):
    '''Receive and decode message from associated socket'''
    # _printd('\n>receive_dictio')
    if UDP:
        # _printd('>_recvUdp')
        data, addr = _recvUdp(sock, socketSize)
        # _printd('<_recvUdp')
        # acknowledge the receiving
        try:
        	sock.sendto(b'ACK', hostPort)
        except OSError as e:
        	_printw(f'OSError: {e}')
        # _printd(f'ACK sent to {hostPort}')
        #self.sock.sendto(b'ACK', self.hostPort)
        #_printd('ACK2 sent to '+str(self.hostPort))
    # else:
        # if True:#try:
            # data = self.sock.recv(self.recvMax)
            # self.sock.close()
            # addr = (self.lHost,self.lPort)
        # else:#except Exception as e:
            # _printw('in sock.recv:'+str(e))
            # return {}

    #print('received %i bytes'%(len(data)))
    #_printd('received %i of '%len(data)+str(type(data))+' from '+str(addr)':')
    # decode received data
    # allow exception here, it will be caught in execute_cmd
    if len(data) == 0:
        _printw(f'empty reply for: {LastDictio}')
        return {}
    try:
        decoded = ubjson.loadb(data)
    except Exception as e:
        _printw(f'exception in ubjson.load Data[{len(data)}]: {e}')
        #print(str(data)[:150])
        #raise ValueError('in _receive_dictio: '+msg)
        return {}
    #for key,val in decoded.items():
    #    print(f'received from {key}: {val.keys()}')

    if not isinstance(decoded,dict):
        #print('decoded is not dict')
        return decoded
    for cnsDev in decoded:
        # items could by numpy arrays, the following should decode everything:
        parDict = decoded[cnsDev]
        for parName,item in list(parDict.items()):
            # _printd(f'parName {parName}: {parDict[parName].keys()}')
            # check if it is numpy array
            shapeDtype = parDict[parName].get('numpy')
            if shapeDtype is not None:
                #print(f'par {parName} is numpy {shapeDtype}')
                shape,dtype = shapeDtype
                v = parDict[parName]['value']
                # it is numpy array
                from numpy import frombuffer
                parDict[parName]['value'] =\
                    frombuffer(v,dtype).reshape(shape)
                del parDict[parName]['numpy']
            else:
                #print(f'not numpy {parName}')
                pass
    # _printd(f'<receive_dictio')
    return decoded

# class thread_with_exception(threading.Thread): 
    # def __init__(self, target=testCallback, args=None):
        # _printw('thread _with_extention may cause problems!')
        # threading.Thread.__init__(self, target=target, args=args) 
           
    # def get_id(self): 
        # # returns id of the respective thread 
        # if hasattr(self, '_thread_id'): 
            # return self._thread_id 
        # for id, thread in threading._active.items(): 
            # if thread is self: 
                # return id
   
    # def raise_exception(self):
        # import ctypes
        # thread_id = self.get_id()
        # _printi(f'thid: {thread_id}')
        # _printi(f'native_id: {threading.get_native_id()}')
        # res = ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 
              # ctypes.py_object(SystemExit)) 
        # if res > 1: 
            # ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0) 
            # _printw('Exception raise failure') 

class Subscriber():
    def __init__(self, hostPort:tuple, devParDict:dict, callback):
        self.name = f'{hostPort,devParDict}'
        self.hostPort = hostPort
        self.devParDict = devParDict
        self.callback = callback

class SubscriptionSocket():
    event = threading.Event()
    '''handles all subscriptions to single hostPort'''
    def __init__(self, hostPort):
        #_printi(f'>subsSocket {hostPort}')
        self.name = f'{hostPort}'
        self.hostPort = tuple(hostPort)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        #self.socket.bind(self.hostPort)
        self.callback = None# holds the callback for checking
        
        dispatchMode = 'Thread'
        if dispatchMode == 'Thread':
            self.selector = None
            #self.socket.settimeout(10)
            #self.thread = thread_with_exception(target=self.receivingThread, args=[])
            self.thread = threading.Thread(target=self.receivingThread)
            self.thread.daemon = True
            self.event.clear()
            self.thread.start()
        #DNW#elif  dispatchMode == 'Selector':
        #    import selectors
        #    self.socket.setblocking(0)
        #    self.selector = selectors.SelectSelector()
        #    self.selector.register(self.socket, selectors.EVENT_READ, self.dispatcher)
        #    # Current limitation: only one callback supported for all 
        #    # device,parameters on one hostPort.
        #    # It considered to be a reasonable approach.             

    def receivingThread(self):
        _printi(f'>receiving thread started for {self.hostPort}') 
        while not self.event.is_set():
            try:
                dictio = _receive_dictio(self.socket, self.hostPort)
            #except socket.timeout as e:
            #except RuntimeError as e:
            except Exception as e:
                msg = f'in subscription thread socket {self.name}: '+str(e)
                _printw(msg)
                raise
                #dictio = {'WARNING':msg}
                #dictio = None
            self.dispatch(dictio)
        _printi(f'<receiving thread stopped for {self.hostPort}') 
        
    def subscribe(self, subscriber):
        if self.socket is None:
            print(f'UDP socket created for {self.hostPort}')
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # just checking:
        if subscriber.hostPort != self.hostPort:
            _printe(f'Subscribe logic error in {self.name}')# this should never happen
        #_printd(f'subscribing {subscriber.name}')
        if self.callback is None:
            self.callback = subscriber.callback
        else:
            if self.callback != subscriber.callback:
                _printe(f'Only one callback is supported per hostPort, subscription for {subscriber.name} is discarded')
                return
        self.event.clear()
        _send_cmd('subscribe', subscriber.devParDict, self.socket\
        , self.hostPort)

    def unsubscribe_all(self):
        _printi(f'unsubscribing {self.hostPort}, {self.socket}')
        if self.socket is None:
            return
        _send_cmd('unsubscribe', {'*':'*'}, self.socket, self.hostPort)
        _printi(f'killing thread of {self.name}')
        self.event.set()
        #self.thread.raise_exception()
        print(f'shutting down {self.hostPort}')
        try:    self.socket.shutdown(socket.SHUT_RDWR)
        except Exception as e: 
            _printw(f'Exception in shutting down: {e}')
        print(f'closing down {self.hostPort}')
        try:    self.socket.close()
        except Exception as e: 
            _printw(f'Exception in closing: {e}')
        self.socket = None
        
    #def dispatcher(self, *args):
    #    #_printi(f'>dispatcher for {self.hostPort} started')
    #    dictio = _receive_dictio(self.socket, self.hostPort)
    #    self.dispatch(dictio)

    def dispatch(self, dictio):
        if dictio:
            #_printi(_croppedText(f'>dispatch {dictio}'))
            self.callback(dictio)
        else:
            _printw(f'empty data from {self.hostPort}')
            #if self.selector:
            #    self.selector.unregister(self.socket)
            #self.socket.close()
            return
    
subscriptionSockets = {}

def _add_subscriber(hostPort:tuple, devParDict:dict, callback=testCallback):
    subscriber = Subscriber(hostPort, devParDict, callback)
    #self.subscribers[subscriber.name] = subscriber

    # register new socket if not registered yet
    try:
        ssocket = subscriptionSockets[hostPort]
    except:
        ssocket = SubscriptionSocket(hostPort)
        subscriptionSockets[hostPort] =  ssocket
        #_printd(f'new socket in publishingHouse: {hostPort}')
    subscriptionSockets[hostPort] = ssocket
    ssocket.subscribe(subscriber)

def unsubscribe_all():
    global subscriptionSockets
    for hostPort,ssocket in subscriptionSockets.items():
        ssocket.unsubscribe_all()
    subscriptionSockets = {}
    _printi('all unsibscribed')

#TODO: cache the channel sockets for reuse
pvSockets = {}
class Channel():
    Perf = False
    """Provides access to host;port"""#[(dev1,[pars1]),(dev2,[pars2]),...]
    def __init__(self, hostPort:tuple, devParDict={}, timeout=10):
        # _printd(f'>Channel {hostPort,devParDict}')
        self.devParDict = devParDict
        host = hostPort[0]
        if host.lower() in ('','localhost'):
            host = ip_address()
        try:    port = int(hostPort[1])
        except: port = 9700
        self.hostPort = host,port
        self.name = f'{self.hostPort}'
        self.recvMax = 1024*1024*4
        if UDP:
            self.sock = pvSockets.get(self.hostPort)
            if self.sock is None:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                #self.sock.bind((self.lHost,self.lPort)) # bind is not necessary for client, an automatic bind() will take place using system assigned local port number
                self.sock.settimeout(timeout)
                pvSockets[self.hostPort] = self.sock
                
        #print('%s client of %s, timeout %s'
        #%(('TCP','UDP')[UDP],str((self.sHost,self.sPort)),str(timeout)))

    def _llTransaction(self, dictio):
        # low level transaction
        _send_dictio(dictio, self.sock, self.hostPort)
        return _receive_dictio(self.sock, self.hostPort)

    def _sendCmd(self, cmd, values=None):
        r = _send_cmd(cmd, self.devParDict, self.sock, self.hostPort, values)

    def _transaction(self, cmd, value=None):
        # normal transaction: send command, receive response
        if Channel.Perf: ts = _timer()
        self._sendCmd(cmd,value)
        r = _receive_dictio(self.sock, self.hostPort)
        if Channel.Perf: print('transaction time: %.5f'%(_timer()-ts))
        # _printd(f'reply from channel {self.name}: {r}')
        return r
    
class PVs(object): #inheritance from object is needed in python2 for properties to work
    """Class, representing multiple data access objects."""
    Dbg = False
    subscriptionsCancelled = True

    def __init__(self, *ldoPars, timeout=5):
        self.timeout = timeout
        # _printd(f'``````````````````Instantiating PVs ldoPars:{ldoPars}')        
        # unpack arguments to hosRequest map
        self.channelMap = {}
        if isinstance(ldoPars[0], str):
            _printe('Device,parameter should be a list or tuple')
            return
            sys.exit(1)
        for ldoPar in ldoPars:
            ldo = ldoPar[0]
            pars = ldoPar[1] if len(ldoPar) > 1 else ''
            try:    ldo = ldo.split(NSDelimiter)
            except: pass
            ldo = tuple(ldo)
            # _printd(f'ldo,Pars:{ldo,pars}')            
            if isinstance(pars,str): pars = [pars]
            # ldo is in form: (hostName,devName)
            ldoHost = _hostPort(ldo)
            #cnsNameDev = ','.join(ldoPar[0])
            cnsNameDev = NSDelimiter.join(ldo)
            #print('ldoHost,cnsNameDev',ldoHost,cnsNameDev)
            if ldoHost not in self.channelMap:
                self.channelMap[ldoHost] = {cnsNameDev:[pars]}
                # _printd(f'created self.channelMap[{ldoHost,self.channelMap[ldoHost]}')
            else:
                try:
                    # _printd(f'appending old cnsNameDev {ldoHost,cnsNameDev} with {pars[0]}')
                    self.channelMap[ldoHost][cnsNameDev][0].append(pars[0])
                except:
                    # _printd(f'creating new cnsNameDev {ldoHost,cnsNameDev} with {pars[0]}')
                    self.channelMap[ldoHost][cnsNameDev] = [pars]
                #print(('updated self.channelMap[%s]='%ldoHost\
                #+ str(self.channelMap[ldoHost]))
        channelList = list(self.channelMap.items())
        # _printd(f',,,,,,,,,,,,,,,,,,,channelList constructed: {channelList}')
        self.channels = [Channel(*i) for i in channelList]
        return

    def info(self):
        for channel in self.channels:
            return channel._transaction('info')

    def get(self):
        for channel in self.channels:
            return channel._transaction('get')

    def _firstValueAndTime(self):
        if True:#try: skip 'server,device'
            firstDict = self.channels[0]._transaction('get')
            if not isinstance(firstDict,dict):
                return firstDict
            firstValsTDict = list(firstDict.values())[0]
        else:#except Exception as e:
            _printw('in _firstValueAndTime: '+str(e))
            return (None,)
        # skip parameter key
        firstValsTDict = list(firstValsTDict.values())[0]
        ValsT = list(firstValsTDict.values())[:2]
        try:     return (ValsT[0], ValsT[1])
        except:  return (ValsT[0],)

    #``````````````Property 'value````````````````````````````````````````````
    # It is for frequently needed get/set access to a single parameter
    @property
    def value(self):
        """Request from server first item of the PVs and return its 
        value and timestamp,"""
        return self._firstValueAndTime()

    @value.setter
    def value(self,value):
        """Send command to set the value to the first item of the PVs"""
        return self.set(value)
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,

    def read(self):
        """Return only readable parameters"""
        for channel in self.channels:
            return channel._transaction('read')

    def set(self,value):
        #for channel in self.channels:
        #TODO: the set is not supported yet for multiple objects
        for channel in self.channels[:1]:
            r = channel._transaction('set',value)
            if isinstance(r,str):
                raise RuntimeError(r)
        return r

    #``````````````subscription ``````````````````````````````````````````````
    def subscribe(self, callback=testCallback):
        if len(self.channels) > 1:
            raise NameError('subscription is supported only for single host;port')
        channel = self.channels[0]
        _add_subscriber(channel.hostPort, channel.devParDict, callback)

    def unsubscribe(self):
        unsubscribe_all()

#``````````````````Universal Access```````````````````````````````````````````
#PVC_PV, PVC_CB, PVC_Props = 0, 1, 2
PVC_PV, PVC_Thread = 0, 1
    
class Access():
    """Universal interface to liteServer parameters, similar to cad_io.
    The pvName should be a tuple: (deviceName,parameterName)
    The full form of the device name: hostName;Port:deviceName,
    if Port is default then it can be omitted: hostName:deviceName.
    Returned values are remapped to the form {(hostDev,par):{parprop:{props}...}...}
    that could be time consuming for complex requests.
    """
    _Subscriptions = []
    __version__ = __version__
    Dbg = False

    def info(*devParNames):
        return PVs(*devParNames).info()

    def get(*devParNames, **kwargs):# kwargs are for compatibility with ADO, they ignored here
        return PVs(*devParNames).get()

    def set(devPar_Value):
        #Only one object supported so far
        dev,par,value = devPar_Value
        return PVs((dev,par)).set(value)

    def subscribe(callback, *devParNames):
        if not callable(callback):
            _printe(('subscribe arguments are wrong,'
            'expected: subscribe(callback,(dev,par))'))
            return
        pvs = PVs(*devParNames)
        pvs.subscribe(callback)

    def unsubscribe():
        '''Unsubscribe all paramters'''
        unsubscribe_all()
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
