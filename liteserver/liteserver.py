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
- info:     reply with information of LDOs
- get:      reply with values of LDOs
- read:     reply only with values of readable LDOs, with changed timestamp, 
            readable LDO have 'R' in their feature, 
- set:      set values of LDOs
- ACK:      internal, response from a client on server reply
- subscribe: server will reply when any of requsted readable parameters have changed
- unsubscribe

Example usage:
- start liteServer for 2 Scalers on a remote host:
liteScaler.py
- use ipython3 to communicate with devices:
ipython3
from liteAccess import liteAccess as LA
LA.Access.info(('Scaler1:server','*'))
LA.Access.info(('Scaler1:dev1','*'))
LA.Access.set(('Scaler1:dev1','run','Stop'))
LA.Access.set(('Scaler1:dev1','run','Run'))
LA.Access.get(('Scaler1:dev1','run'))
LA.Access.subscribe(LA.testCallback,('Scaler1:server','clientsInfo'))

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
#__version__ = 'v48 2020-03-07'
#__version__ = 'v49 2020-03-09'# Read and subscription deliver only changed objects, subscriptions are per-device basis
#__version__ = 'v50a 2020-03-26'# error propagation to clients
#__version__ = 'v52 2020-12-17'# NSDelimiter=':' to conform EPICS and ADO
#__version__ = 'v53b 2020-12-18'# .v and .t replaced with .value and .timestamp to be consistent with ADO and EPICS
#__version__ = 'v54 2020-12-23'# publish() delivers parameters which have been changed since previous delivery. Unsubscribe is supported, may need locking.
#__version__ = 'v55d 2020-12-31'# unsubscribing all, timeShift replaces time 
#__version__ = 'v56 2021-01-01'# major update.
#__version__ = 'v57 2021-01-02'# heartbeat thread
#__version__ = 'v58 2021-01-04'# 'run' PV added to Device, 'start' PV removed from server, Device.aborted()
#__version__ = 'v60e 2021-01-06'# itemsLost counter, send_udp got arg: subscribed 
#__version__ = 'v61 2021-01-06'# Reasonably good
#__version__ = 'v62 2021-01-12'# scalar allowed in parameter definition, it will be treated as array[1]
#__version__ = 'v63 2021-04-08'# more informative exception handling
#__version__ = 'v64 2021-04-11'# Server.Dbg is boolean
#__version__ = 'v65 2021-04-12'# handling of a wrong command format exception
#__version__ = 'v66 2021-04-20'# all threads should be non-daemonic
#__version__ = 'v67 2021-04-21'# numpy array attribute is 'numpy', not 'n'
#__version__ = 'v68 2021-04-22'# oplimits are violated when value is out of bounds
#__version__ = 'v69 2021-04-24'# handling retransmissions
#__version__ = 'v70 2021-04-29'# works OK for data  up to 5MB
#__version__ = 'v71 2021-05-01'# added getter to LDO, removed second argument in LDO.setter
#__version__ = 'v72 2021-05-03'# don't need to use value[0] most cases, require Ack even for 1-chunk messages
#__version__ = 'v73 2021-05-05'# parent removed.
#__version__ = 'v74 2021-05-19'# targeted un-subscribing
#__version__ = 'v76 2021-05-26'# ItemLostLimit reduced to 1, with MaxAckCount = 10, parameters are copied, not bound in LDO.__init__
#__version__ = 'v77 2021-05-27'# LDO._name replaced with LDO.name
#__version__ = 'v78 2021-06-10'# runFlag removed, added LDO.start() LDO.stop()
#__version__ = 'v79 2021-07-06'# use float32 for encoding, could be overridded by setting Device.no_float32=True. Server.Dbg handled properly
__version__ = 'v80 2021-07-07'# opLimits for debug

#TODO: test retransmit
#TODO: WARN.LS and ERROR.LS messages should be published in server:status

import sys, time, math, traceback
import threading
publish_Lock = threading.Lock()
ackCount_Lock = threading.Lock()
send_UDP_Lock = threading.Lock()
from timeit import default_timer as timer
import socket
#import SocketServer# for python2
import socketserver as SocketServer# for python3
import array
import ubjson

UDP = True
ChunkSize = 65000
#ChunkSize = 10000
PrefixLength = 4
#ChunkSleep = 0.001 # works on localhost, 50MB/s, and on shallow network
#ChunkSleep = 0.0005 # works on localhost, 100MB/s, rare KeyError: 'pid'
ChunkSleep = 0
#SendSleep = 0.001
MaxAckCount = 10# Number of attempts to ask for delivery acknowledge
ItemLostLimit = 1# Number of failed deliveries before considering that the client is dead.
AckInterval =0.5# interval of acknowledge checking (default=0.5)

PORT = 9700# Communication port number
NSDelimiter = ':'# delimiter in the name field
#````````````````````````````Helper functions`````````````````````````````````
MaxPrint = 500
def croppedText(obj, limit=200):
    txt = str(obj)
    if len(txt) > limit:
        txt = txt[:limit]+'...'
    return txt
def printTime(): return time.strftime("%m%d:%H%M%S")
def printi(msg): 
    print(croppedText(f'INFO.LS@{printTime()}: '+msg))

def printw(msg):
    msg = msg = croppedText(f'WARN.LS@{printTime()}: '+msg)
    print(msg)
    #Device.setServerStatusText(msg)

def printe(msg): 
    msg = croppedText(f'ERROR.LS@{printTime()}: '+msg)
    print(msg)
    #Device.setServerStatusText(msg)

def printd(msg):
    if Server.Dbg: print(croppedText('LS.DBG:'+str(msg)))

def ip_address(interface = ''):
    """Platform-independent way to get local host IP address"""
    def ip_fromGoogle():
        ipaddr = [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close())\
          for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]
        printi(f'IP address is obtained using Google')
        return ipaddr
    if len(interface) > 0:
        #assume it is linux
        try:
            import subprocess
            r = subprocess.run(f'ip address show dev {interface}'.split()\
            , capture_output=True)
            tokens = r.stdout.split()
            ipaddr = tokens[tokens.index(b'inet')+1].decode().split('/')[0]
        except Exception as e:
            printw(f'Could not get IP address using ip command: {e}')
            ipaddr = ip_fromGoogle()
    else: # get it from Google
        ipaddr = ip_fromGoogle()
    return ipaddr

def send_ack(socket, hostPort):
    #DNPprinti(f'ack from {socket.getsockname()} to {hostPort}')
    socket.sendto(b'\x00\x00\x00\x00',hostPort)

#````````````````````````````Base Classes`````````````````````````````````````
class LDO():
    """Base class for Lite Data Objects. Standard properties:
    value, count, timestamp, features, decription.
    value should be iterable! It simplifies internal logic.
    The type and count is determined from default value.
    Features is string, containing letters from 'RWD'.
    More properties can be added in derived classes"""
    def __init__(self,features='RW', desc='', value=[0], units=None,
            opLimits=None, legalValues=None, setter=None,
            getter=None):
        printd(croppedText('>LDO: '+str((features,desc,value,opLimits))))
        self.name = None # assigned in device.__init__.
        # name is not really needed, as it is keyed in the dictionary
        self.timestamp = time.time()# None
        import copy
        try:
            self.count = [len(value)]
            self.value = copy.copy(value)
        except: 
            self.count = [1]
            self.value = [value]
        self.features = features
        self.desc = desc
        self.units = units

        # absorb optional properties
        self.opLimits = opLimits
        self.legalValues = legalValues
        self._setter = setter
        self._getter = getter

    def __str__(self):
        printi('LDO object desc: %s at %s'%(self.desc,id(self)))

    def update_value(self):
        """It is called during get() and read() request to refresh the value.
        """
        if self._getter:
            self._getter()

    def is_writable(self): return 'W' in self.features
    def is_readable(self): return 'R' in self.features

    def set(self, vals):#, prop='value'):
        """Set LDO property to vals"""
        printd(f'>set {self.name}={vals}')
        if not self.is_writable():
            raise PermissionError('LDO is not writable')
        try: # pythonic way for testing if object is iterable
            test = vals[0]
        except:
            vals = [vals]

        # Special treatment of the boolean and action parameters
        #printi(f'set {len(self.value)}, {type(self.value[0])}')
        try:    l = len(self.value)
        except:
            l = 1
            self.value = [self.value]

        if l == 1 and isinstance(self.value[0],bool):
            vals = [True] if vals[0] else [False] 

        if type(vals[0]) is not type(self.value[0]):
            msg='Setting %s: '%self.name+str(type(vals[0]))+' to '\
            +str(type(self.value[0]))
            #raise TypeError(msg)
            printw(msg)
            
        if self.opLimits is not None:
            #print(f'checking for opLimits {vals,self.opLimits}')
            if vals[0] < self.opLimits[0] or vals[0] > self.opLimits[1]:
                print('Exception')
                raise ValueError('out of opLimits '+str(self.opLimits)+': '\
                + str(vals[0]))

        if self.legalValues is not None:
            #printi('checking for legalValues %s = '%self.name+str(vals[0]))
            if vals[0] not in self.legalValues:
                raise ValueError('not a legal value of %s:'\
                %self.name+str(vals[0]))

        prev = self.value
        printd(f'set {self.name}={vals}')
        self.value = vals
        self.timestamp = time.time()

        # call LDO setting method with new value
        #print('self._setter of %s is %s'%(self.name,self._setter))
        if self._setter is not None:
            #self._setter(self) # (self) is important!
            try:
                self._setter() # (self) is important!
            except:
                self.value = prev
                raise

    def info(self):
        """list all members which are not None and not prefixed with '_'
        """
        r = [i for i in vars(self)
          if not (i.startswith('_') or getattr(self,i) is None)]
        return r

class Device():
    """Device object has unique name, its members are parameters (objects,
    derived from LDO class)."""
    server = None# It will keep the server device after initialization
    EventExit = threading.Event()

    def __init__(self, name='?', pars={}, no_float32=False):
        """
        pars:   dictionary of {parameterName:LDO}
        no_float32 (bool): Never use float32 to store float numbers (other than
                           for zero). Disabling this might save space at the
                           loss of precision.
        """
        self.name = name
        self.no_float32 = no_float32
        self.lastPublishTime = 0.
        self.subscribers = {}
        printd(croppedText('pars '+str(pars)))

        requiredParameters = {
          'run':    LDO('RWE','Stop/Run/Exit', ['Running'],legalValues\
            = ['Exit'] if self.name == 'server' else ['Run','Stop']\
            , setter=self._set_run),
          'status': LDO('R','Device status', ['']),
        }
        parDefs = requiredParameters
        parDefs.update(pars)
        # Add parameters
        for p,v in list(parDefs.items()):
            setattr(self,p,v)
            par = getattr(self,p)
            par.name = p

    def aborted(self):
        self.stop()
        return Device.EventExit.is_set()

    def setServerStatusText(txt):
        """Not thread safe. Publish text in server.status pararameter"""
        print(f'setServerStatusText() not safe: {txt}')
        #return
        try:
            Device.server.status.value[0] = txt
            Device.server.status.timestamp = time.time()
            Device.server.publish()
        except Exception as e:
            print(f'Exception in setServerStatusText: {e}')

    #````````````````````````Subscriptions````````````````````````````````````
    #@staticmethod
    def register_subscriber(self, hostPort, socket, serverCmdArgs):
        #printd('register subscriber for '+str(serverCmdArgs))
        # the first dev,ldo in the list will trigger the publishing
        try:    cnsDevName,parPropVals = serverCmdArgs[0]
        except: raise NameError('cnsDevName,parPropVals wrong: '+serverCmdArgs)
        cnsHost,devName = cnsDevName.rsplit(NSDelimiter,1)
        parName = parPropVals[0][0]
        if parName == '*':
            dev = Server.DevDict[devName]
            pvars = vars(dev)
            # use first LDO of the device
            for parName,val in pvars.items():
                if isinstance(val,LDO):
                    #printd('ldo %s, features '%parName+val.features)
                    if 'R' in val.features:
                        break
            printi('The master parameter: '+parName)

        """Register a new subscriber for this object""" 
        #printd(f'subscribe {hostPort}:{serverCmdArgs}')
        if hostPort in self.subscribers:
            #printi(f'subscriber {hostPort} is already subscribed  for {self.name}')
            # extent list of parameters for given socket
            socket, argList, *_ =  self.subscribers[hostPort]
            serverCmdArgs = argList + serverCmdArgs
        self.subscribers[hostPort] = [socket, serverCmdArgs, 0, 0]
        l = len(self.subscribers)
        printd(f'subscription {self.name}#{l} added: {hostPort,serverCmdArgs}')
        Device.server.clientsInfo.timestamp = time.time()# this will cause to publish it during heartbeat
        #Device.server.publish()# this is useless

    def get_statistics(self):
        """Return number of subscribers and number of subscribed items"""
        nSockets = len(self.subscribers)
        nItems = 0
        for hostPort,value in self.subscribers.items():
            socket, request, itemsLost, lastDelivered = value
            nItems += len(request)
        return nSockets, nItems

    def unsubscribe(self, clientHostPort):
        """Unsubscribe all device parameters."""
        d = {}
        #d = {hostPort:ss[1] for hostPort,ss in self.subscribers.items()}
        #toDelete = []
        for hostPort, value in list(self.subscribers.items()):# list is used to prevent runtime error
            if hostPort != clientHostPort:
                continue
            socket, request, *_ = value
            #printi(f'unsubscribe: {hostPort, socket, request}') 
            d[hostPort] = request
            #socket.close()
            printi(croppedText(f'subscriptions cancelled for {d}:'))
            #toDelete.append(hostPort)
            del self.subscribers[hostPort]
        #for i in toDelete:
        #    del self.subscribers[i]
        #self.subscribers = {}
        Device.server.clientsInfo.timestamp = time.time()

    def publish(self):
        """Publish fresh data to subscribers. 
        The data, which timestamp have not changed since the last update
        will not be published.
        If data have changed several times since the last update then only 
        the last change will be published.
        Call this when the data are ready to be published to subscribers.
        usually at the end of the data pocessing.
        """
        if len(self.subscribers) == 0:
            return 0
        #print('>pub')
        bytesShipped = 0
        blocked = not publish_Lock.acquire(blocking=False)
        if blocked:
            #printd(f'publishing for {self.name} is blocked, waiting for lock release')
            ts = time.time()
            publish_Lock.acquire(blocking=True)
            printi(f'publishing for {self.name} is unblocked after {round(time.time()-ts,6)}s')
        currentTime = time.time()
        #dt = [0.]*2
        #print(f'subscribers of {self.name}: {self.subscribers.keys()}')
        for hostPort, value in list(self.subscribers.items()):
            #print(f'serving {hostPort}')
            ts = timer()
            socket, request, itemsLost, lastDelivered = value
            if Server.Dbg > 1:
                printd(f'```````````````device {self.name} responding to {hostPort}:\n publishing request {request}')
            #print(f'subscriber:{self.subscribers[hostPort]}')
            # check if previous delivery was succesful
            sockAddr = (socket,hostPort)
            if sockAddr in list(_myUDPServer.ackCounts):
                ackCount = _myUDPServer.ackCounts[(sockAddr)][0]
                #print(f'Posting to {hostPort} dropped as it did not acknowlege previous delivery: {ackCount}')
                Server.Perf['Dropped'] += 1
                #if ackCount < MaxAckCount:
                if ackCount <= 0:
                    printi(f'Client {hostPort} stuck {itemsLost+1} times in a row')
                    itemsLost += 1
                    Server.Perf['ItemsLost'] += itemsLost
                    self.subscribers[hostPort][2] = itemsLost
                    with ackCount_Lock:
                        _myUDPServer.ackCounts[sockAddr][0] = MaxAckCount
                if itemsLost >= ItemLostLimit:
                    printw((f'Subscription to {hostPort} cancelled, it was '\
                    f'not acknowledging for {itemsLost} delivery of:\n'\
                    f'{request}'))
                    del self.subscribers[hostPort]
                    with ackCount_Lock:
                        del _myUDPServer.ackCounts[sockAddr]
                    print(f'reduced subscribers: {self.subscribers.keys()}')
                    Device.server.clientsInfo.timestamp = currentTime
                continue
            else:
                self.subscribers[hostPort][2] = 0# reset itemsLost counter

            # do publish
            self.subscribers[hostPort][3] = currentTime# update lastDelivered time

            # _reply() will deliver only parameters with modified timestamp
            #tn = timer(); dt[0] += tn - ts
            r = _reply(['read',request], socket, hostPort
            , no_float32=self.no_float32)
            #printd(f'<_reply: {r}')
            #tn = timer(); dt[1] += tn - ts
            bytesShipped += r
        self.lastPublishTime = time.time()
        publish_Lock.release()
        printd(f'published {bytesShipped} bytes')#, times:{[round(i,4) for i in dt]}') 
        #print('<pub')
        return bytesShipped

    def _set_run(self):
        """special treatment of the setting of the 'run' parameter"""
        val = self.run.value[0]
        if val == 'Stop':
            val = 'Stopped'
            self.stop()
        elif val == 'Run':
            val = 'Running'
            self.start()
        elif val == 'Exit':
            printi('Exiting server')
            Device.EventExit.set()
            time.sleep(1)
            sys.exit()
        else:
            raise ValueError(f'LS:not accepted setting for "run": {val[0]}') 
        self.run.value[0] = val

    def stop(self):
        """Overriddable. Called when run is stopped."""
        pass

    def start(self):
        """Overriddable. Called when run is started."""
        pass

#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#``````````````````functions for socket data preparation and sending``````````
def _send_UDP(buf, socket, hostPort):
  """send buffer via UDP socket, chopping it to smaller chunks"""
  with send_UDP_Lock:# prevent this method from re-entrancy
    # setup the EOD repetition count at the server
    
    if (socket,hostPort) in _myUDPServer.ackCounts:
        printe(f'TODO:Did not finish serving previous request from {hostPort}')
        # it cannot last longer than MaxAckCount*AckInterval
        time.sleep(MaxAckCount*AckInterval)
        if (socket,hostPort) in _myUDPServer.ackCounts:
            # The acknowledging have not been resolved in the service_action()
            #with ackCount_Lock:
            #    del _myUDPServer.ackCounts[socket,hostPort]
            msg = '<_send_UDP abnormal exit'
            printe(msg)
            #raise RuntimeError(msg)
            return

    lbuf = len(buf)
    #DNPprint(f'>_send_UDP {lbuf} bytes to {hostPort}')
    ts = [0.]*6
    ts[0] = timer()
    nChunks = (lbuf-1)//ChunkSize + 1
    chunksInfo = {}
    # send chunks in backward order
    for iChunk in range(nChunks-1,-1,-1):
        #ts[1] = timer()# 6% here
        slice = iChunk*ChunkSize, min((iChunk+1)*ChunkSize, lbuf)
        chunk = buf[slice[0]:slice[1]]
        #ts[2] = timer()# 5% here
        prefixInt = iChunk*ChunkSize
        #print('pi',prefixInt)
        prefixBytes = (prefixInt).to_bytes(PrefixLength,'big')
        prefixed = b''.join([prefixBytes,chunk])# 5% here
        #txt = str(chunk)
        #if len(txt) > 100:
        #    txt = txt[:100]+'...'
        #print('sending prefix %i'%prefixInt+' %d bytes:'%len(prefixed),txt)
        #ts[3] = timer()# 10% here
        offsetSize = prefixInt, len(chunk)
        #DNPprinti(f'chunk[{iChunk}]: {offsetSize}')
        chunksInfo[(offsetSize)] = prefixed # <1 % here
        #ts[4] = timer()
        #TODO: the sending takes no time
        socket.sendto(prefixed, hostPort) # 90% here
        if nChunks > 1:
            time.sleep(ChunkSleep)

    # register multi-chunk chunksInfo for acknowledge processing
    if True:#lbuf >= ChunkSize:# Do not ask for acknowledge for 1-chunk transfers
        with ackCount_Lock:
            if (socket,hostPort) in _myUDPServer.ackCounts:
                printi(f'Client {hostPort} presumed dead')
                return
            _myUDPServer.ackCounts[(socket,hostPort)] = [MaxAckCount, chunksInfo]
            #print(f'ackCounts for {hostPort} set to {MaxAckCount}')    

    ts[5] = timer()
    dt = ts[5] - ts[0]
    if lbuf > 1000:
        mbytes = 1e-6*len(buf)
        #dts = ts[1]-ts[0], ts[2]-ts[1], ts[3]-ts[2], ts[4]-ts[3], ts[5]-ts[4],
        #printi(f'sent {lbuf} b/{round(dt,4)}s, '+'perf: %.1f MB/s'%(mbytes/dt)+f' deltas(us): {[int(i*1e6) for i in dts]}')
        Server.Perf['MBytes']  += mbytes
        Server.Perf['Seconds'] += dt
        Server.Perf['Sends']   += 1
    #DNPprint(f'<_send_UDP')
    #time.sleep(SendSleep)

def _replyData(cmdArgs):
    """Prepare data for reply"""
    #printd('>_replyData')
    try:    cmd,args = cmdArgs
    except: 
        #printd(f'cmdArgs: {cmdArgs}')
        if cmdArgs[0] == 'info':
            devs = list(Server.DevDict)
            return devs
        else:   raise ValueError('expect cmd,args')
    #DNTprint('cmd,args: '+str((cmd,args)))
        
    returnedDict = {}
        
    for devParPropVal in args:
        #printd(f'devParPropVal: {devParPropVal}')
        try:
            cnsDevName,sParPropVals = devParPropVal
        except Exception as e:
            msg = 'ERR.LS in _replyData for '+str(cmdArgs)
            printi(msg)
            raise TypeError(msg) from e

        cnsHost,devName = cnsDevName.rsplit(NSDelimiter,1)
        parNames = sParPropVals[0]
        if len(sParPropVals) > 1:
            propNames = sParPropVals[1]
        else:   
            propNames = '*' if cmd == 'info' else 'value'
        #printd('devNm,parNm,propNm:'+str((devName,parNames,propNames)))
        try:    vals = sParPropVals[2]
        except: vals = None
        if devName == '*':
            for devName in Server.DevDict:
                cdn = NSDelimiter.join((cnsHost,devName))
                devDict = _process_parameters(cmd, parNames, devName\
                , propNames, vals)
                returnedDict[cdn] = devDict
        else:
            if cnsDevName not in returnedDict:
                #print('add new cnsDevName',cnsDevName)
                devDict = _process_parameters(cmd, parNames, devName\
                , propNames, vals)
                if len(devDict) > 0:
                    returnedDict[cnsDevName] = devDict
                else:
                    #print(f'no fresh data for {devName,parNames}')
                    pass
            else:
                devDict = returnedDict[cnsDevName]
                additionalDevDict = _process_parameters(cmd, parNames, devName\
                , propNames, vals)
                #printd(croppedText(f'additional devDict: {additionalDevDict}'))
                devDict.update(additionalDevDict)
                returnedDict[cnsDevName] = devDict
    return returnedDict

#LastUpdateTime = 0.
def _process_parameters(cmd, parNames, devName, propNames, vals):
    """part of _replyData"""
    #global LastUpdateTime
    devDict = {}
    try:    dev = Server.DevDict[devName]
    except:
        msg = f'device {devName} not served'
        printe(msg)
        raise NameError(msg)

    if parNames[0][0] == '*':
        parNames = vars(dev)
    
    #print('parNames:'+str(parNames))
    for idx,parName in enumerate(parNames):
        pv = getattr(dev,parName)
        #print('parName',parName,type(pv),isinstance(pv,LDO))
        if not isinstance(pv,LDO):
            continue
        features = getattr(pv,'features','')

        if cmd == 'read' and 'R' not in features:
            #print('par %s is not readable, it will not be replied.'%parName)
            continue
        parDict = {}

        def valueDict(value):
            try: # if value is numpy array:
                if dev.no_float32 == False:
                    value = value.astype('f4')
                shape,dtype = value.shape, str(value.dtype)
            except Exception as e:
                #printd('not numpy %s, %s'%(pv.name,str(e)))
                return {'value':value}
            else:
                #printd("numpy array %s, shape,type:%s, add key 'numpy'"%(str(pv.name),str((shape,dtype))))
                return {'value':value.tobytes(), 'numpy':(shape,dtype)}

        if cmd in ('get', 'read'):
            ts = timer()
            timestamp = getattr(pv,'timestamp',None)
            #printd(f'parName {parName}, ts:{timestamp}, lt:{dev.lastPublishTime}')
            if not timestamp: 
                printw('parameter '+parName+' does ot have timestamp')
                timestamp = time.time()
            dt = timestamp - dev.lastPublishTime
            #if dt < 0.:
            #    printw(f'timestamp issue with parameter {parNmame}: {dt}') 
            if cmd == 'read' and dt < 0.:
                #printd(f'parameter {parName} is skipped as it did not change since last update: {dt}')
                continue
                
            pv.update_value()
            devDict[parName] = parDict
            value = getattr(pv,propNames)
            #printd('value of %s %s=%s, timing=%.6f'%(type(value), parName,str(value)[:100],timer()-ts))
            vd = valueDict(value)
            #printd(croppedText(f'vd:{vd}'))
            parDict.update(vd)
            parDict['timestamp'] = getattr(pv,'timestamp',None)

        elif cmd == 'set':
            try:
                val = vals[idx]\
                  if len(parNames) > 1 else vals
            except:   raise NameError('set value missing')
            devDict[parName] = parDict
            if not isinstance(val,(list,array.array)):
                val = [val]
            if True:#try:
                #printi(f'set: {dev.name}:{parName}={val}')
                pv.set(val)
            else:#except Exception as e:
                msg = f'in set {parName}: {e}'
                printe(msg)
                raise ValueError(msg)

        elif cmd == 'info':
            #printd('info (%s.%s)'%(parName,str(propNames)))
            devDict[parName] = parDict
            #if len(propNames[0]) == 0:
            if propNames[0] == '*':
                propNames = pv.info()
            #printd('propNames of %s: %s'%(pv.name,str(propNames)))
            for propName in propNames:
                pv = getattr(dev,parName)
                propVal = getattr(pv,propName)
                if propName == 'value':
                    vd = valueDict(propVal)
                    #printd(croppedText(f'value of {parName}:{vd}'))
                    parDict.update(vd)
                else:
                    parDict[propName] = propVal
        else:   raise ValueError(f'command "{cmd}" not accepted')
    return devDict

def _reply(cmd, socket, client_address=None, no_float32=False):
    """Build a reply data and send it to client"""
    #ts = []; ts.append(timer())
    try:
        r = _replyData(cmd)
        if len(r) == 0:
            return 0
    except Exception as e:
            r = f'ERR.LS. Exception for cmd {cmd}: {e}'
            exc = traceback.format_exc()
            print('LS.Traceback: '+repr(exc))
    #printd(croppedText(f'reply object: {r}'))
    #ts.append(timer()); ts[-2] = round(ts[-1] - ts[-2],4)
    
    reply = ubjson.dumpb(r, no_float32)# 75% time is spent here
    #ts.append(timer()); ts[-2] = round(ts[-1] - ts[-2],4)
    #printd(f'reply {len(reply)} bytes, doubles={no_float32}')
    host,port = client_address# the port here is temporary
    #printd(croppedText(f'sending back {len(reply)} bytes to {client_address}'))
    #ts.append(timer()); ts[-2] = round(ts[-1] - ts[-2],4)
    if UDP:
        _send_UDP(reply, socket, client_address)# 25% time spent here
        # initiate the sending of EOD to that client
    else:
        #self.request.sendall(reply)
        printi('TCP not supported yet')
    #ts.append(timer()); ts[-2] = round(ts[-1] - ts[-2],4)
    #print(f'reply times: {ts[:-1]}')
    return len(reply)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````The Request broker```````````````````````````````
class _LDO_Handler(SocketServer.BaseRequestHandler):
    lastPID = '?'
                 
    def handle(self):
        """Override the handle method"""
        if UDP:
            data = self.request[0].strip()
            socket = self.request[1]
            sockAddr = socket,self.client_address
            if data == b'ACK':
                with send_UDP_Lock: # we need to wait when sending is done
                    #DNPprinti('Got ACK from %s'%str(self.client_address))
                    if (sockAddr) not in self.server.ackCounts:
                        #DNPprintw('no ACK to delete from '+str(self.client_address))
                        pass
                    else:
                        #printi(croppedText(f'deleting {sockAddr}: {self.server.ackCounts[sockAddr][1].keys()}'))
                        with ackCount_Lock:
                            del self.server.ackCounts[sockAddr]
                    return
        else:
            data = self.request.recv(1024).strip()

        try:
            cmd = ubjson.loadb(data)
        except:
            msg = f'ERR.LS: wrong command format (not ubjson): {data}'
            if UDP:
                #_send_UDP(msg.encode('utf-8'), *sockAddr)
                socket.sendto(b'\x00\x00\x00\x00', self.client_address)
            return
        #printi((f'Client {self.client_address} wrote:\n{cmd}'))

        # retrieve previous source to server.lastPID LDO
        try:
            Device.server.lastPID.value[0] = _LDO_Handler.lastPID
            # remember current source 
            _LDO_Handler.lastPID = '%s;%i %s %s'%(*self.client_address\
            ,cmd['pid'], cmd['username'], )
            #print('lastPID now',_LDO_Handler.lastPID)
        except:
            pass

        try:    cmdArgs =  cmd['cmd']
        except: raise  KeyError("'cmd' key missing in request")

        if cmdArgs[0] == 'unsubscribe':
            #print(f'cmdArgs: {cmdArgs} from {self.client_address}')
            for devName,dev in Server.DevDict.items():
                printi(f'unsubscribing {self.client_address} from {devName}')
                dev.unsubscribe(self.client_address)
            printi('<unsubscribe')
            return

        if cmdArgs[0] == 'retransmit':
            Server.Perf['Retransmits'] += 1
            #print(f'Retransmit {cmdArgs} from {sockAddr}, ackCount:{_myUDPServer.ackCounts.keys()}')
            if not sockAddr in _myUDPServer.ackCounts:
                    printw(f'sockaddr wrong\n{sockAddr}')
                    #for key in _myUDPServer.ackCounts:
                    #    print(key)
                    
            printw(croppedText(f'Retransmitting: {cmd}'))#: {_myUDPServer.ackCounts[sockAddr][0],_myUDPServer.ackCounts[sockAddr][1].keys()}'))
            offsetSize = tuple(cmdArgs[1])
            try:
                chunk = _myUDPServer.ackCounts[sockAddr][1][offsetSize]
            except Exception as e:
                msg = f'in LDO_Handle: {e}, sa:{sockAddr[1]}, os:{offsetSize}'
                printe(msg)
                raise RuntimeError(msg)
            #DNTprint(f'sending {len(chunk)} bytes of chunk {offsetSize} to {sockAddr[1]}')
            socket.sendto(chunk, sockAddr[1])
            return

        try:
            devName= cmdArgs[1][0][0].split(NSDelimiter)[1]
            #print('subscriber for device '+devName)
            dev = Server.DevDict[devName]
        except KeyError:
            printe(f'Device not supported: devName')
        except:
            printe(f'unexpected exception, cmdArgs: {cmdArgs}')
            raise NameError(('Subscription should be of the form:'\
            "[['host,dev1', [parameters]]]\ngot: "+str(cmdArgs[1])))

        if  cmdArgs[0] == 'subscribe':
            #print(f'>register_subscriber {self.client_address} for cmd {cmdArgs}')
            dev.register_subscriber(self.client_address, socket, cmdArgs[1])
            return

        r = _reply(cmdArgs, *sockAddr)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Server```````````````````````````````````````````
class _myUDPServer(SocketServer.UDPServer):
    """Subclass the UDPServer to override the service_actions()"""
    ackCounts = {}
    def __init__(self,hostPort, handler):
        super().__init__(hostPort, handler, False)
        #self.handler = handler

    def service_actions(self):
      """Service_actions() called by server periodically with AckInterval.
      Check if there are not acknowledged send_UDPs and send several 
      additional acknowledges in case they were missed. 
      """
      #with ackCount_Lock:
      for sockAddr,v in list(_myUDPServer.ackCounts.items()):# list is used to avoid RuntimeError
            sock,hostPort = sockAddr
            ackCount = v[0]
            #if ackCount <= 0:
            #    printw(f'No ACK{ackCount} from {hostPort}')
            #    with ackCount_Lock:
            #        del _myUDPServer.ackCounts[sockAddr]
            #    continue

            # keep sending EODs to that client until it detects it
            if ackCount <= 2:
                printw('waiting for ACK%i from '%ackCount+str(hostPort))
                #printd(f'ackCounts:{_myUDPServer.ackCounts}')
            if ackCount < -10:
                printw(f'abnormal unsubscribing of {sockAddr}')
                with ackCount_Lock:
                	del _myUDPServer.ackCounts[sockAddr]
                	return
            with ackCount_Lock:
                _myUDPServer.ackCounts[sockAddr][0] -= 1
            send_ack(sock, hostPort)

class LDO_clientsInfo(LDO):
    '''Debugging LDO, providing textual dictionary of all subscribers.''' 
    # override data updater
    def update_value(self):
        from pprint import pformat
        d = {}
        currentTime = time.time()
        for devName,dev in Server.DevDict.items():
            d[devName] = {}
            for hostPort,value in dev.subscribers.items():
                socket, request, itemsLost, lastDelivered = value
                #print(f'hps:{hostPort,socket}')
                dt = round(currentTime - lastDelivered, 6)
                d[devName][hostPort] = dt,request
        self.value = [pformat(d)]
        self.timestamp = currentTime

class Server():
    """liteServer object"""
    #``````````````Attributes`````````````````````````````````````````````````
    Dbg = 0
    DevDict = {}
    Perf= {'Sends': 0, 'MBytes': 0., 'Seconds': 0., 'Retransmits': 0,
        'ItemsLost': 0, 'Dropped':0}
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #``````````````Instantiation`````````````````````````````````````````````
    def __init__(self, devices=[], interface='', port=PORT
    , serverPars=True):
        printi(f'Server.Dbg: {Server.Dbg}')
        # create Device 'server'
        if serverPars:
            serverDev = Device('server',{\
              'version':LDO('','liteServer',[__version__]),
              'host':   LDO('','Host name',[socket.gethostname()]),
              'status': LDO('R','Messages from liteServer',['']),
              'debug':  LDO('RWE','Debugging'\
              ,[Server.Dbg], opLimits=[0,10], setter=self._debug_set),
              'lastPID': LDO('','report source of the last request ',['?']),
              'perf':   LDO('R'\
                ,'Performance: RQ,MBytes,MBytes/s,Retransmits,Losts,Dropped'\
                ,[0., 0., 0., 0, 0, 0]),
              'statistics': LDO('R','Number of items and subscriptions in circulations',[0,0]),
              'clientsInfo': LDO_clientsInfo('R','Info on all subscriptions',['']),
            })
            self.DevDict[serverDev.name] = serverDev
        
        for dev in devices:
            self.DevDict[dev.name] = dev

        self.host = ip_address(interface)
        self.port = port
        s = _myUDPServer if UDP else SocketServer.TCPServer
        self.server = s((self.host, self.port), _LDO_Handler)#, False)
        self.server.allow_reuse_address = True
        self.server.server_bind()
        self.server.server_activate()
        printi(f'Server for {self.host}:{self.port} have been instantiated')
        printi(f'devices: {list(self.DevDict.keys())}')
        thread = threading.Thread(target=self._heartbeat, daemon=True)
        thread.start()

    def _heartbeat(self):
        printi('heartbeat thread started')
        prevs = [0.,0.]
        while not Device.EventExit.is_set():
            Device.EventExit.wait(10)
            ts = time.time()
            subscriptions = 0
            nItems = 0
            nSockets = 0
            for devName,dev in self.DevDict.items():
                ns,ni,*_ = dev.get_statistics()
                #printi(f'dev {devName}, has {ns} subscriptions for for total of {ni} items')
                nItems += ni
                nSockets += ns
            Device.server.statistics.value = [nItems,nSockets]
            # timestamps need to be updated for published parameters 
            Device.server.statistics.timestamp = ts
            try:
                dt = Server.Perf['Seconds'] - prevs[1]
                mbps = round((Server.Perf['MBytes'] - prevs[0])/dt, 1)
            except:
                mbps = 0.
            Device.server.perf.timestamp = ts
            Device.server.perf.value = [Server.Perf['Sends'],
                round(Server.Perf['MBytes'],3), mbps,
                Server.Perf['Retransmits'], Server.Perf['ItemsLost'],
                Server.Perf['Dropped']]
            prevs = Server.Perf['MBytes'], Server.Perf['Seconds']

            Device.server.publish()
            #printi(f'hearbeat duration: {timer() - ts}')# ~10 us
        printi('heartbeat stopped')

    def loop(self):
        Device.server = self.DevDict['server']
        printi(__version__+'. Waiting for %s messages at %s'%(('TCP','UDP')[UDP],self.host+';'+str(self.port)))
        try:
            self.server.serve_forever(poll_interval=AckInterval)
        except KeyboardInterrupt:
            printe('KeyboardInterrupt in server loop')
            Device.EventExit.set()
        
    def _debug_set(self, *_):
        par_debug = Device.server.debug.value
        printi(f'par_debug: {par_debug}')
        Server.Dbg = par_debug[0]
        printi('Debugging level set to '+str(Server.Dbg))

    def par_set(self, par):
        """Generic parameter setter"""
        parVal = par.value
        printi('par_set %s='%par.name + str(parval))

def isHostPortSubscribed(hostPort):
    """For testing purposes"""
    for dev in Server.DevDict.values():
        if hostPort in dev.subscribers:
            return True
    return False

#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# see liteScaler.py, liteAccess.py
