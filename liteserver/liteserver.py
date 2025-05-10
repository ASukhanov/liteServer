"""Base class of the Lite Data Object Server.
It hosts the Lite Data Objects and responds to info/get/set/subscribe commands.

Transport protocol: UDP with handshaking and re-transmission. 

Binary object encoding protocol: CBOR

message format:
  {'cmd':[command,[[dev1,dev2,...],[arg1,arg2,...]]],
  'user':user,...}

Supported commands:
- info:     reply with information of LDOs
- get:      reply with values of LDOs
- read:     reply only with values of readable LDOs, with changed timestamp, 
- set:      set values of LDOs
- ACK:      internal, response from a client on server reply
- subscribe: server will reply when any of requsted readable parameters have changed
- unsubscribe: cancel all subscriptions.
"""
__version__ = '3.3.4 2025-05-08'# added 'clear' parameter to every device
#TODO: WARN.LS and ERROR.LS messages should be published in server:status

import sys, time, math, traceback
timer = time.perf_counter
import threading
publish_Lock = threading.Lock()
ackCount_Lock = threading.Lock()
send_UDP_Lock = threading.Lock()
import socket
import array

# object encoding, uncomment encoder of your choice: msgpack or ubjson:
#import ubjson as encoder
#import msgpack as encoder # More popular than ubjson
import cbor2 as encoder # More standard than MsgPack
encoderDump = encoder.dumps
encoderLoad = encoder.loads

import selectors
Selector = selectors.DefaultSelector()
LastPID = '?'
UDP = True# If True then it will use UDP protocol, else - TCP.
if UDP:
    ChunkSize = 65000
    #ChunkSize = 10000
    PrefixLength = 4
    #ChunkSleep = 0.001 # works on localhost, 50MB/s, and on shallow network
    #ChunkSleep = 0.0005 # works on localhost, 100MB/s, rare KeyError: 'pid'
    ChunkSleep = 0
    #SendSleep = 0.001
    MaxAckCount = 10# Number of attempts to ask for delivery acknowledge
    ItemLostLimit = 2# Number of failed deliveries before considering that the client is dead.
    AckInterval = 10.# Not used. Interval of acknowledge checking

defaultServerPort = 9700# Communication port number
NSDelimiter = ':'# delimiter in the name field
#````````````````````````````Helper functions`````````````````````````````````
def croppedText(obj, limit=300):
    txt = str(obj)
    if len(txt) > limit:
        txt = txt[:limit]+'...'
    return txt
def printTime(): return time.strftime("%m%d:%H%M%S")
def printi(msg): 
    print(croppedText(f'INFO_LS@{printTime()}: '+msg))

def printw(msg):
    msg = msg = croppedText(f'WARNING_LS@{printTime()}: '+msg)
    print(msg)
    #Device.setServerStatusText(msg)

def printe(msg): 
    msg = croppedText(f'ERROR_LS@{printTime()}: '+msg)
    print(msg)
    #Device.setServerStatusText(msg)

def printv(msg):
    if Server.Dbg >= 1: print(croppedText('DBG_LS: '+str(msg)))

def printvv(msg):
    if Server.Dbg >= 2: print(croppedText('DBG2_LS: '+str(msg)))

def ip_address(interface = ''):
    """Platform-independent way to get local host IP address"""
    def ip_fromGoogle():
        try:
            ipaddr = [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close())\
              for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]
            printi(f'IP address {ipaddr} is obtained using Google')
        except:
            ipaddr = 'localhost'
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
            #printw(f'Could not get IP address using ip command: {e}')
            ipaddr = ip_fromGoogle()
    else: # get it from Google
        ipaddr = ip_fromGoogle()
    return ipaddr

def accept_TCP(sock, mask):
    conn, addr = sock.accept()  # Should be ready
    print('accepted', conn, 'from', addr)
    conn.setblocking(False)
    Selector.register(conn, selectors.EVENT_READ, read_TCP)

def read_TCP(conn, mask):
    print(f'read_TCP: {conn, mask}')
    data = conn.recv(1024)  # Should be ready
    if data:
        print('echoing', repr(data), 'to', conn)
        conn.send(data)  # Hope it won't block
    else:
        print('closing', conn)
        Selector.unregister(conn)
        conn.close()

#````````````````````````````Base Classes`````````````````````````````````````
class LDO():
    """Base class for Lite Data Objects. Standard properties:
    value, count, timestamp, features, decription.
    value should be iterable! It simplifies internal logic.
    The type and count is determined from default value.
    Features is string, containing letters from 'RWDEI'.
    R stands for Readable
    W - for Writable
    D - for Discrete
    E - for Editable
    I - for diagnostic
    More properties can be added in derived classes"""
    def __init__(self,features='RW', desc='', value=[0], units=None,
            opLimits=None, legalValues=None, setter=None,
            getter=None, ptype=None, ):
        self.name = None # assigned in device.__init__.
        # name is not really needed, as it is keyed in the dictionary
        self.timestamp = time.time()# None
        import copy
        try:
            if isinstance(value,str):
                self.count = [1]
                self.value = value
            else:
                self.count = [len(value)]
                self.value = copy.copy(value)
        except: 
            self.count = [1]
            self.value = [value]
        self.features = features
        self.desc = desc
        self.units = units
        if ptype is None:
            self.type = str(type(self.value[0])).split('\'')[1]
        else:
            self.type = ptype
 
        # absorb optional properties
        self.opLimits = opLimits
        if legalValues:
            if not isinstance(legalValues[0], str):
                printe(f'Legal values {legalValues} are not strings')
                sys.exit(1)
        self.legalValues = legalValues
        self._setter = setter
        self._getter = getter

    def __str__(self):
        return(f'LDO({self.features}, {self.desc},  {self.value})')

    def update_value(self):
        """It is called during get() and read() request to refresh the value.
        """
        if self._getter:
            self._getter()

    def is_writable(self): return 'W' in self.features
    def is_readable(self): return 'R' in self.features

    def set_valueAndTimestamp(self, value, timestamp=None):
        self.value = value
        if timestamp is None:   timestamp = time.time()
        self.timestamp = timestamp

    def set(self, vals):#, prop='value'):
        """Set LDO property to vals, test for oplimits, legal values etc... before setting"""
        printv(f'>set {self.name}={vals}')
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
        valueType = type(self.value[0])
        if l == 1 and valueType == bool:
            vals = [True] if vals[0] else [False] 

        if valueType != type(None) and type(vals[0]) != valueType:
            msg='Setting %s: '%self.name+str(type(vals[0]))+' to '\
            +str(type(self.value[0]))
            #raise TypeError(msg)
            printw(msg)
            # convert to proper type:
            vals[0] = valueType(vals[0])
            
        if self.opLimits is not None:
            #print(f'checking for opLimits {vals,self.opLimits}')
            if   (self.opLimits[0] is not None and float(vals[0]) < self.opLimits[0])\
              or (self.opLimits[1] is not None and float(vals[0]) > self.opLimits[1]):
                print('Exception')
                raise ValueError('out of opLimits '+str(self.opLimits)+': '\
                + str(vals[0]))

        if self.legalValues is not None:
            #printi(f'checking for legalValues {self.name,vals[0],type(vals[0])}')
            if vals[0] not in self.legalValues:
                raise ValueError('not a legal value of %s:'\
                %self.name+str(vals[0]))

        prev = self.value
        if valueType != type(None):
            printv(f'set value {self.name}={vals}')
            self.value = vals
        self.timestamp = time.time()

        # call LDO setting method with new value
        #print('self._setter of %s is %s'%(self.name,self._setter))
        if self._setter is not None:
            try:
                with publish_Lock:
                    self._setter() # (self) is important!
            except:
                self.value = prev
                raise

    def info(self):
        """list all PVs"""
        """members which are not None and not prefixed with '_'"""
        r = [i for i in vars(self)
          if not (i.startswith('_') or getattr(self,i) is None)]
        
        return r

class Device():
    """Device object has unique name, its members are parameters (objects,
    derived from LDO class)."""
    server = None# It will keep the server device after initialization
    EventExit = threading.Event()

    def __init__(self, name='?', pars={}):
        """pars:   dictionary of {parameterName:LDO}"""
        self.name = name
        self.lastPublishTime = 0.
        self.subscribers = {}
        self.alreadyRunning = False

        requiredParameters = {
          'run':    LDO('RWE','Start/Stop/Exit', ['Started'],legalValues=
            ['Start','Stop', 'Exit']
              if self.name == 'server' else ['Start','Stop'],
            setter=self.set_run),
          'status': LDO('RWE','Device status', ['']),
          'clear': LDO('WE','Clear cerain parameters', None,
            setter=self.set_clear),
        }
        self.PV = requiredParameters
        # Add parameters
        self.PV.update(pars)
        for p,v in (self.PV.items()):
            v.name = p
            printv(croppedText(f'PV {p}: {v}'))

    def add_parameter(self, name, ldo):
        self.PV[name] = ldo

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
    def register_subscriber(self, hostPort, sock, serverCmdArgs):
        printv(f'register subscriber for {serverCmdArgs}: {sock}')
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
                    #printv('ldo %s, features '%parName+val.features)
                    if 'R' in val.features:
                        break
            printi('The master parameter: '+parName)

        """Register a new subscriber for this object""" 
        #printv(f'subscribe {hostPort}:{serverCmdArgs}')
        if hostPort in self.subscribers:
            #printi(f'subscriber {hostPort} is already subscribed  for {self.name}')
            # extent list of parameters for given socket
            sock, argList, *_ =  self.subscribers[hostPort]
            serverCmdArgs = argList + serverCmdArgs
        self.subscribers[hostPort] = [sock, serverCmdArgs, 0, 0]
        l = len(self.subscribers)
        printv(f'subscription {self.name}#{l} added: {hostPort,serverCmdArgs}. sock: {sock}')
        Device.server.PV['clientsInfo'].timestamp = time.time()# this will cause to publish it during heartbeat

    def get_statistics(self):
        """Return number of subscribers and number of subscribed items"""
        nSockets = len(self.subscribers)
        nItems = 0
        for hostPort,value in self.subscribers.items():
            sock, request, itemsLost, lastDelivered = value
            nItems += len(request)
        return nSockets, nItems

    def unsubscribe(self, clientHostPort):
        """Unsubscribe all device parameters."""
        d = {}
        for hostPort, value in list(self.subscribers.items()):# list is used to prevent runtime error
            if hostPort != clientHostPort:
                continue
            sock, request, *_ = value
            d[hostPort] = request
            printi(croppedText(f'subscriptions cancelled for {d}:'))
            del self.subscribers[hostPort]
        Device.server.PV['clientsInfo'].timestamp = time.time()

    def publish(self):
        """Publish fresh data to subscribers. 
        The data, which timestamp have not changed since the last update
        will not be published.
        If data have changed several times since the last update, then only 
        the last change will be published.
        Call this when the data are ready to be published to subscribers.
        usually at the end of the data processing.
        """
        if len(self.subscribers) == 0:
            return 0
        bytesShipped = 0
        blocked = not publish_Lock.acquire(blocking=False)
        if blocked:
            #printv(f'publishing for {self.name} is blocked, waiting for lock release')
            ts = time.time()
            publish_Lock.acquire(blocking=True)
            printi(f'publishing for {self.name} is unblocked after {round(time.time()-ts,6)}s')
        currentTime = time.time()
        #dt = [0.]*2
        #print(f'subscribers of {self.name}: {self.subscribers.keys()}')
        for hostPort, value in list(self.subscribers.items()):
            printv(f'serving {hostPort} {value}')
            ts = timer()
            sock, request, itemsLost, lastDelivered = value
            if Server.Dbg > 1:
                printv(f'```````````````device {self.name} responding to {hostPort}:\n publishing request {request}')
            if UDP:
              #print(f'subscriber:{self.subscribers[hostPort]}')
              # check if previous delivery was succesful
              sockAddr = (sock,hostPort)
              if sockAddr in list(_myUDPServer.ackCounts):
                _myUDPServer.ackCounts[(sockAddr)][0] -= 1
                ackCount = _myUDPServer.ackCounts[(sockAddr)][0]
                printv(f'Missed ACK from {hostPort}: {ackCount}')
                Server.Perf['Dropped'] += 1
                #if ackCount < MaxAckCount:
                if ackCount <= 0:
                    printi(f'Client {hostPort} stuck {itemsLost+1} times in a row')
                    itemsLost += 1
                    Server.Perf['ItemsLost'] = itemsLost
                    self.subscribers[hostPort][2] = itemsLost
                    with ackCount_Lock:
                        try:
                            _myUDPServer.ackCounts[sockAddr][0] = MaxAckCount
                        except KeyError:
                            printw('Logic error in line 394')
                if itemsLost >= ItemLostLimit:
                    printw((f'Subscription to {hostPort} cancelled, it was '\
                    f'not acknowledging for {itemsLost} delivery of:\n'\
                    f'{request}'))
                    del self.subscribers[hostPort]
                    with ackCount_Lock:
                        del _myUDPServer.ackCounts[sockAddr]
                    print(f'reduced subscribers: {self.subscribers.keys()}')
                    Device.server.PV['clientsInfo'].timestamp = currentTime
                    continue
              else:
                try:
                    self.subscribers[hostPort][2] = 0# reset itemsLost counter
                except KeyError:
                    printw('Logic error at line 409')

            # do publish
            self.subscribers[hostPort][3] = currentTime# update lastDelivered time

            # _reply('read',...) will deliver only parameters with modified timestamp
            #tn = timer(); dt[0] += tn - ts
            r = _reply(['read',request], sock, hostPort)
            printvv(f'<_reply: {r}')
            #tn = timer(); dt[1] += tn - ts
            bytesShipped += r
        self.lastPublishTime = time.time()
        publish_Lock.release()
        printv(f'published {bytesShipped} bytes')#, times:{[round(i,4) for i in dt]}') 
        #print('<pub')
        return bytesShipped

    def set_run(self, state=None):
        """Special treatment of the setting of the 'run' parameter"""
        if state == None:
            state = self.PV['run'].value[0]
        printi(f'>setter for run = {state}')
        if state == 'Stop':
            state = 'Stopped'
            self.alreadyRunning = False
            self.stop()
        elif state == 'Start':
            if self.alreadyRunning:
                raise ValueError('LS: already running')
            state = 'Started'
            self.alreadyRunning = True
            self.start()
        elif state == 'Exit':
            printi('Exiting server')
            Device.EventExit.set()
            time.sleep(1)
            sys.exit()
        else:
            raise ValueError(f'LS:not accepted setting for "run": {state}') 
        self.PV['run'].value[0] = state

    def set_clear(self):
        """Override it"""
        pass

    def poll(self):
        """Override this method if device need to react on periodic polling 
        from server."""
        #printi(f'Device {self.name} polled')# at {time.time()}, serverTS:{Server.Timestamp}')
        pass

    def reset(self):
        """Overriddable. Called when Reset clicked on server."""
        pass

    def stop(self):
        """Overriddable. Called when run is stopped."""
        printw('Device.stop() is not provided!')
        pass

    def start(self):
        """Overriddable. Called when run is started."""
        printw('Device.start() is not provided!')
        pass

    def exit(self):
        printi(f'Device {self.name} is exiting')
        Device.EventExit.set()
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#``````````````````functions for socket data preparation and sending``````````
if UDP:
  def _send_UDP(buf, sock, hostPort):
    """Send buffer via UDP socket, chopping it to smaller chunks"""
    with send_UDP_Lock:# prevent this method from re-entrancy
        lbuf = len(buf)
        printvv(f'>_send_UDP {lbuf} bytes to {hostPort}')
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
            offsetSize = prefixInt, len(chunk)
            #DNPprinti(f'chunk[{iChunk}]: {offsetSize}')
            chunksInfo[(offsetSize)] = prefixed # <1 % here
            #ts[4] = timer()
            sock.sendto(prefixed, hostPort) # 90% time spent here
            if nChunks > 1:
                time.sleep(ChunkSleep)

        # register multi-chunk chunksInfo for acknowledge processing
        if True:#lbuf >= ChunkSize:# Do not ask for acknowledge for 1-chunk transfers
            with ackCount_Lock:
                if (sock,hostPort) in _myUDPServer.ackCounts:
                    printv(f'Client {hostPort} presumed dead')
                    return
                _myUDPServer.ackCounts[(sock,hostPort)] = [MaxAckCount, chunksInfo]
                printvv(f'ackCounts for {hostPort} set to {MaxAckCount}')    

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
    printvv(f'>_replyData {cmdArgs}')
    try:    cmd,args = cmdArgs
    except: 
        if cmdArgs[0] == 'info':
            devs = list(Server.DevDict)
            return devs
        else:   raise ValueError('expect cmd,args')
        
    returnedDict = {}
        
    for devParPropVal in args:
        try:
            cnsDevName,sParPropVals = devParPropVal
        except Exception as e:
            msg = 'ERR.LS in _replyData for '+str(cmdArgs)
            printi(msg)
            raise TypeError(msg) from e

        cnsHost,devName = cnsDevName.rsplit(NSDelimiter,1)
        #printv(f'sParPropVals: {sParPropVals}')
        parNames = sParPropVals[0]
        vals = None
        if len(sParPropVals) > 1:
            propNames = sParPropVals[1]
            try:    vals = sParPropVals[2]
            except: pass
        else:   
            propNames = '*' if cmd == 'info' else 'value'
        printvv(f'cnsHost,dev,par,vals: {cnsHost,devName,parNames,vals}')
        if devName == '*':
            returnedDict = {cnsHost:{}}
            for devName in Server.DevDict:
                printvv(f'devName: {devName}')
                cdn = NSDelimiter.join((cnsHost,devName))
                devDict = _process_parameters(cmd, parNames, cdn,
                  propNames, vals)
                returnedDict[cnsHost][devName] = list(devDict.keys())
            printvv(f'host devices: {returnedDict}')
        else:
            additionalDevDict = _process_parameters(cmd, parNames,
              cnsDevName, propNames, vals)
            #printv(croppedText(f'additional devDict: {additionalDevDict}'))
            returnedDict.update(additionalDevDict)
    printvv(f'<_replyData: {returnedDict}')
    return returnedDict

def _process_parameters(cmd, parNames, cnsDevName, propNames, vals):
    """part of _replyData"""
    devDict = {}
    host,devName = cnsDevName.split(':',1)
    try:    dev = Server.DevDict[devName]
    except:
        msg = f'device {cnsDevName} not served'
        printe(msg)
        raise NameError(msg)

    if parNames[0][0] == '*':
        parNames = dev.PV.keys()
    
    #print('parNames:'+str(parNames))
    for idx,parName in enumerate(parNames):
        pv = dev.PV.get(parName)
        if not isinstance(pv,LDO):
            msg = f'No such name: {cnsDevName,parName}'
            #printe(msg)
            raise NameError(msg)
            #printv('WARNING '+msg)
            continue
        features = getattr(pv,'features')

        if cmd == 'read' and 'R' not in features:
            #print('par %s is not readable, it will not be replied.'%parName)
            continue
        parDict = {}

        def valueDict(propName, value):
            try: # if value is numpy array:
                dtype = str(value.dtype)
                shape, dtype = value.shape, dtype
                return {propName:value.tobytes(), 'numpy':(shape,dtype)}
            except:
                #printv(f'not numpy {pv.name}')
                return {propName:value}

        if cmd in ('get', 'read'):
            ts = timer()
            timestamp = getattr(pv,'timestamp')
            #printvv(f'parName {parName}, ts:{timestamp}, lt:{dev.lastPublishTime}')
            if not timestamp: 
                printw('parameter '+parName+' does ot have timestamp')
                timestamp = time.time()
            dt = timestamp - dev.lastPublishTime
            #if dt < 0.:
            #    printw(f'timestamp issue with parameter {parNmame}: {dt}') 
            if cmd == 'read' and dt < 0.:
                #printv(f'parameter {parName} is skipped as it did not change since last update: {timestamp,dev.lastPublishTime}')
                continue
                
            # update value if command is get()
            if cmd == 'get':
                pv.update_value()

            #print(f'dev {cnsDevName}, pardict: {parDict}')
            devDict[':'.join((cnsDevName,parName))] = parDict
            #print(f'devDict: {devDict}')
            value = getattr(pv,propNames)
            #printv('value of %s %s=%s, timing=%.6f'%(type(value), parName,str(value)[:100],timer()-ts))
            vd = valueDict(propNames, value)
            #printv(croppedText(f'vd:{vd}'))
            parDict.update(vd)
            parDict['timestamp'] = getattr(pv,'timestamp')

        elif cmd == 'set':
            try:
                val = vals[idx]\
                  if len(parNames) > 1 else vals
            except:   raise NameError('set value missing')
            if not isinstance(val,(list,array.array)):
                val = [val]
            if True:#try:
                pv.set(val)
            else:#except Exception as e:
                msg = f'in set {parName}: {e}'
                printe(msg)
                raise ValueError(msg)
            devDict[parName] = {'value':pv.value}

        elif cmd == 'info':
            printv(f'info {parName,propNames}')
            devDict[parName] = parDict
            #if len(propNames[0]) == 0:
            if propNames[0] == '*':
                props = set(pv.info())
                props.discard('value')
            else:
                props = set(propNames)
            printvv(f'properties of {pv.name}: {props}')
            for propName in props:
                pv = dev.PV[parName]
                propVal = getattr(pv,propName)
                if propName == 'value':
                    vd = valueDict(propVal)
                    #printv(croppedText(f'value of {parName}:{vd}'))
                    parDict.update(vd)
                else:
                    parDict[propName] = propVal
        else:   raise ValueError(f'command "{cmd}" not accepted')
    #printv(f'devdict: {devDict}')
    return devDict

def _reply(cmd, sock, client_address=None):
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
    #printv(croppedText(f'reply_object={r}',100000))
    #ts.append(timer()); ts[-2] = round(ts[-1] - ts[-2],4)
    try:
        #reply = encoderDump(r, no_float32=False)# 75% time is spent here. no_float32 results in wrong timestamp
        reply = encoderDump(r)#
    except Exception as e:
        reply = encoderDump(f'ERR.LS. Exception in dumpb: {e}')
    #ts.append(timer()); ts[-2] = round(ts[-1] - ts[-2],4)
    #printv(f'reply {len(reply)} bytes, doubles={no_float32}')
    #printv(croppedText(f'sending back {len(reply)} bytes to {client_address}'))
    #ts.append(timer()); ts[-2] = round(ts[-1] - ts[-2],4)
    if UDP:
        host,port = client_address# the port here is temporary
        _send_UDP(reply, sock, client_address)# 25% time spent here
        # initiate the sending of EOD to that client
    else:
        sock.sendall(reply)
        printi(f'TCP reply sent {reply}')
    #ts.append(timer()); ts[-2] = round(ts[-1] - ts[-2],4)
    #print(f'reply times: {ts[:-1]}')
    return len(reply)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````The Request broker```````````````````````````````
def handle_socketData(data:str, sockAddr=None):
    global LastPID
    if UDP:
        sock,client_address = sockAddr
        if data == b'ACK':
            with send_UDP_Lock: # we need to wait when sending is done
                printvv(f'Got ACK from {client_address}')
                with ackCount_Lock:
                    if sockAddr in _myUDPServer.ackCounts:
                        printvv(f'deleting ackCount {sockAddr}')
                        del _myUDPServer.ackCounts[sockAddr]
                return
    
    data = data.strip()
    #printv(f'data: {data}')
    try:
        cmd = encoderLoad(data)
    except:
        msg = f'ERR.LS: Wrong command format (not {encoder.__name__}): {data}'
        printw(msg)
        return
    #printi((f'Client {client_address} wrote:\n{cmd}'))

    # retrieve previous source to server.lastPID LDO
    try:
        Device.server.PV['lastPID'].value[0] = LastPID
        # remember current source 
        LastPID = '%s;%i %s %s'%(*client_address\
        ,cmd['pid'], cmd['username'], )
        #print('lastPID now',LastPID)
    except Exception as e:
        #print(f'lastPID {LastPID}: {e}')
        pass

    printv(f'Got command {cmd} from {client_address}')
    cmdArgs = cmd.get('cmd')
    if cmdArgs is None:
        #raise  KeyError("'cmd' key missing in request")
        printw("'cmd' key missing in request")
        return

    if cmdArgs[0] == 'unsubscribe':
        #print(f'cmdArgs: {cmdArgs} from {client_address}')
        for devName,dev in Server.DevDict.items():
            #printi(f'unsubscribing {client_address} from {devName}')
            dev.unsubscribe(client_address)
        return

    if cmdArgs[0] == 'retransmit':
        Server.Perf['Retransmits'] += 1
        printv(f'Retransmit {cmdArgs} from {sockAddr}, ackCount:{_myUDPServer.ackCounts.keys()}')
        if not sockAddr in _myUDPServer.ackCounts:
                printw(f'sockaddr wrong\n{sockAddr}')
                return
                
        #printw(croppedText(f'Retransmitting: {cmd}'))#: {_myUDPServer.ackCounts[sockAddr][0],_myUDPServer.ackCounts[sockAddr][1].keys()}'))
        offsetSize = tuple(cmdArgs[1])
        try:
            chunk = _myUDPServer.ackCounts[sockAddr][1][offsetSize]
        except Exception as e:
            msg = f'in LDO_Handle: {e}, sa:{sockAddr[1]}, os:{offsetSize}'
            printe(msg)
            raise RuntimeError(msg)
        #DNTprint(f'sending {len(chunk)} bytes of chunk {offsetSize} to {sockAddr[1]}')
        sock.sendto(chunk, sockAddr[1])
        return

    try:
        devName= cmdArgs[1][0][0].split(NSDelimiter)[1]
        #print('subscriber for device '+devName)
        if devName != '*':
            dev = Server.DevDict[devName]
    except KeyError:
        printe(f'Device not supported: {devName}')
    except:
        printe(f'unexpected exception, cmdArgs: {cmdArgs}')
        raise NameError(('Subscription should be of the form:'\
        "[['host,dev1', [parameters]]]\ngot: "+str(cmdArgs[1])))

    if  cmdArgs[0] == 'subscribe':
        printv(f'>register_subscriber {client_address} for cmd {cmdArgs}, sock: {sock}')
        dev.register_subscriber(client_address, sock, cmdArgs[1])                
        return

    r = _reply(cmdArgs, *sockAddr)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
if UDP:
  #````````````````````````````Server```````````````````````````````````````````
  class _myUDPServer():
    ackCounts = {}
    def __init__(self, hostPort):#, handler):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1)
        # Bind the socket to the port
        print(f'starting UDP on port {hostPort}')
        self.sock.bind(hostPort)

    def service_actions(self):
        """Service_actions() called by server periodically with AckInterval."""
        # Don't do anything
        return

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
                sock, request, itemsLost, lastDelivered = value
                dt = round(currentTime - lastDelivered, 6)
                d[devName][hostPort] = dt,request
        self.value = [pformat(d)]
        self.timestamp = currentTime

class ServerDev(Device):
    """Unique server device"""
    PollingInterval = 1.
    def __init__(self, name):
        # create parameters
        pars = {
            'version':LDO('','liteServer',[__version__]),
            'host':   LDO('','Host name',[socket.gethostname()]),
            'status': LDO('R','Messages from liteServer',['']),
            'debug':  LDO('RWE','Debugging level', [Server.Dbg],
              opLimits=[0,10], setter=self._debug_set),
            'devsPollingInterval': LDO('RWE',('Time interval of calling'
            ' poll() method for all devices'), [ServerDev.PollingInterval],
              units='s'),
            'Reset':  LDO('WE','Reset all devices on the server',[None],
              setter=self._reset),
            'lastPID': LDO('','report source of the last request ',['?']),
            'perf':   LDO('R'\
            ,'Performance: RQ,MBytes,MBytes/s,Retransmits,Losts,Dropped'\
            ,[0., 0., 0., 0, 0, 0]),
            'statistics': LDO('R','Number of items and subscriptions in circulations',[0,0]),
            'clientsInfo': LDO_clientsInfo('R','Info on all subscriptions',['']),
        }
        super().__init__(name, pars)
        self.heartbeatPrevs = [0.,0.]
        thread = threading.Thread(target=self._heartbeat, daemon=True)
        thread.start()

    def _debug_set(self, *_):
        par_debug =self.PV['debug'].value
        printi(f'par_debug: {par_debug}')
        Server.Dbg = par_debug[0]
        printi('Debugging level set to '+str(Server.Dbg))

    def _heartbeat(self):
        printi('Heartbeat thread started')
        while not Device.EventExit.is_set():
            Device.EventExit.wait(10)
            #print(f'HB_proc {time.time()}')
            ts = time.time()
            subscriptions = 0
            nItems = 0
            nSockets = 0
            for devName,dev in Server.DevDict.items():
                ns,ni,*_ = dev.get_statistics()
                #printi(f'dev {devName}, has {ns} subscriptions for for total of {ni} items')
                nItems += ni
                nSockets += ns
            self.PV['statistics'].set_valueAndTimestamp([nItems,nSockets], ts)
            try:
                dt = Server.Perf['Seconds'] - self.heartbeatPrevs[1]
                mbps = round((Server.Perf['MBytes'] - self.heartbeatPrevs[0])/dt, 1)
            except:
                mbps = 0.
            self.PV['perf'].set_valueAndTimestamp([Server.Perf['Sends'],
                round(Server.Perf['MBytes'],3), mbps,
                Server.Perf['Retransmits'], Server.Perf['ItemsLost'],
                Server.Perf['Dropped']], ts)
            self.heartbeatPrevs = Server.Perf['MBytes'], Server.Perf['Seconds']
            self.publish()
        printi('Heartbeat stopped')

    def _reset(self):
        """Execute reset on all devices"""
        for name,dev in Server.DevDict.items():
            if name != 'server':
                #dev.reset()# We should quickly return
                thread = threading.Thread(target=dev.reset, daemon=True)
                thread.start()
                time.sleep(.10)# just in case

class Server():
    """The Server"""
    #``````````````Attributes`````````````````````````````````````````````````
    #TODO: Make most of the items as class attributes.
    Dbg = 0
    DevDict = {}
    Perf= {'Sends': 0, 'MBytes': 0., 'Seconds': 0., 'Retransmits': 0,
        'ItemsLost': 0, 'Dropped':0}
    Timestamp = time.time()
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #``````````````Instantiation`````````````````````````````````````````````
    def __init__(self, devices=[], interface='', port=defaultServerPort
    , serverPars=True):
        printi(f'Server.Dbg: {Server.Dbg}')
        # create Device 'server'
        if serverPars:
            self.DevDict['server'] = ServerDev('server')
        
        for dev in devices:
            self.DevDict[dev.name] = dev

        self.host = ip_address(interface)
        self.port = port
        s = _myUDPServer if UDP else SocketServer.TCPServer
        s.allow_reuse_address = True
        self.socketServer = s((self.host, self.port))#, _LDO_Handler)#, False)
        #self.server.allow_reuse_address = True
        #if UDP:
        #    self.server.server_bind()
        #self.server.server_activate()
        printi(f'Server for {self.host}:{self.port} is serving devices:')
        print(f'{list(self.DevDict.keys())}')
        if UDP:#TODO: move it to the loop
            threadDevsPoll = threading.Thread(target=self._devsPoll, daemon=True)
            threadDevsPoll.start()

    if UDP:
      def _devsPoll(self):
        # periodically call poll() method on all devices except server
        time.sleep(.5)# Give time for devices to settle
        printv('Device polling started')
        prevs = [0.,0.]
        lasttime = time.time()
        interval = 0.
        while not Device.EventExit.is_set():
            newInterval = Device.server.PV['devsPollingInterval'].value[0]
            if interval != newInterval:
                printi(f'Polling interval changed from {interval} to {newInterval}')
            interval = newInterval
            waitTime = interval - (time.time() - lasttime)
            if waitTime > 0.:
                Device.EventExit.wait(waitTime)
            lasttime = time.time()
            Server.Timestamp = lasttime
            for name,dev in self.DevDict.items():
                if name != 'server':
                    dev.poll()
        printv('Device polling stopped')

    def loop(self):
        """Processing of the network requests, should be called after instantiation"""
        Device.server = self.DevDict['server']
        printi(__version__+'. Waiting for %s messages at %s'%(('TCP','UDP')[UDP],self.host+';'+str(self.port)))
        serviceActionTime = time.time()
        if UDP: 
            pollingInterval = AckInterval
            sock = self.socketServer.sock
        else:
            pollingInterval = 0.5
        while not Device.EventExit.is_set():
            try:
                if UDP:
                    data, address = sock.recvfrom(4096)
                else:
                    address = '?',0
                    data =  sock.recv(4096)
                printvv(f'data[{len(data)}], from: {address}')
                handle_socketData(data, (sock, address))
            except socket.timeout:
                printvv(f'No requests')
            except KeyboardInterrupt:
                printe('KeyboardInterrupt in server loop')
                Device.EventExit.set()
                return
            except Exception as e:
                print(f'Exception in the loop: {e}: {traceback.format_exc()}')
                continue

            #self.server.serve_forever(poll_interval=pollingInterval)
            ctime = time.time()
            if ctime - serviceActionTime > pollingInterval:
                #printi(f'>service_action. {printTime()}')
                serviceActionTime = ctime
                self.socketServer.service_actions()

def isHostPortSubscribed(hostPort):
    """For testing purposes"""
    for dev in Server.DevDict.values():
        if hostPort in dev.subscribers:
            return True
    return False
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
