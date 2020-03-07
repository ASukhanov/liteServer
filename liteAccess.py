"""Base class for accessing multiple Process Variables, served by a liteServer.
#``````````````````Usage:`````````````````````````````````````````````````````
import liteAccess as LA
from pprint import pprint
    #``````````````Info```````````````````````````````````````````````````````
    # list of devices on a server
pprint(list(LA.LdoPars([[['Scaler1','*'],'*']]).info()))
    # info on all paremeters of the 'Scaler1','server'
pprint(LA.LdoPars([[['Scaler1','server'],'*']]).info())    
pprint(LA.LdoPars([[['set#1 of counters & image','server'],'*']]).info())
    # info on single parameter
pprint(LA.LdoPars([[['Scaler1','server'],'time']]).info())
    # info on multiple parameters
pprint(LA.LdoPars([[['Scaler1','server'],['time','perf']]]).info())
    #``````````````Get````````````````````````````````````````````````````````
    # simplified get: returns (value,timestamp) of a parameter (frequency)\
    # from a ldo Scaler1,server. 
pprint(LA.LdoPars([[['Scaler1','server'],'perf']]).value)
    # get single parameter from ldo scaler0.dev0, 
pprint(LA.LdoPars([[['Scaler1','server'],'perf']]).get())
    # get multiple parameters from an ldo 
pprint(LA.LdoPars([[['Scaler1','server'],['time','perf']]]).get())
    # get multiple parameters from multiple ldos 
pprint(LA.LdoPars([[['Scaler1','dev1'],['time','frequency']],[['Scaler1','dev2'],['time','command']]]).get())
    # test for timeout, should timeout in 10s:
LA.LdoPars([[['Scaler1','dev0'],'*']]).value
    #``````````````Read```````````````````````````````````````````````````````
    # get all readable parameters from an ldo
print(LA.LdoPars([[['Scaler1','dev1'],'*']]).read())  
    #``````````````Set````````````````````````````````````````````````````````
    # explicit set
LA.LdoPars([[['Scaler1','dev1'],'frequency']]).set([7.])
    # simple set, equivalent to explicit set
LA.LdoPars([[['Scaler1','dev1'],'frequency']]).value = [9.]
pprint(LA.LdoPars([[['Scaler1','dev1'],'frequency']]).value)
    # multiple set
LA.LdoPars([[['Scaler1','dev1'],['frequency','coordinate']]]).set([8.,[3.,4.]])
LA.LdoPars([[['Scaler1','dev1'],['frequency','coordinate']]]).get()
    #``````````````Subscribe``````````````````````````````````````````````````
ldo = LA.LdoPars([[['localhost','dev1'],'image']])
ldo.sunscribe()# it will print image data periodically
ldo.unsubscribe()# cancel subscruption

#``````````````````TODO``````````````````````````````````````````````````````` 
#ldo = LA.LdoPars([[['localhost','dev1'],'*']])
#ldo.sunscribe()
#LA.LdoPars(['Scaler1.dev1','frequency']).set(property=('oplimits',[-1,11])
#``````````````````Observations```````````````````````````````````````````````
    # Measured transaction time is 1.8ms for:
LA.LdoPars([[['Scaler1','dev1'],['frequency','command']]]).get()
    # Measured transaction time is 6.4ms per 61 KBytes for:
LA.LdoPars([[['Scaler1','dev1'],'*']]).read() 
#``````````````````Tips```````````````````````````````````````````````````````
To enable debugging: LA.LdoPars.Dbg = True
To enable transaction timing: LA.Channel.Perf = True  
"""
#__version__ = 'v42 2020-02-21'# liteServer-rev3.
#__version__ = 'v43 2020-02-24'# noCNS, err nandling in retransmission
__version__ = 'v44 2020-03-06'# subscription supported

print('liteAccess '+__version__)

import sys, time, socket
from os import getuid,getpid
from timeit import default_timer as timer
from pprint import pformat, pprint
from numpy import frombuffer
import ubjson

#````````````````````````````Globals``````````````````````````````````````````
UDP = True
PrefixLength = 4
socketSize = 1024*64 # max size of UDP transfer
Dev,Par = 0,1
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Helper functions`````````````````````````````````
def printi(msg): print('info: '+msg)
def printw(msg): print('LAWARNING: '+msg)
def printe(msg): print('LAERROR: '+msg)
def printd(msg):
    if LdoPars.Dbg: print('LADbg: '+msg)

def testCallback(args):
    print('>testCallback(%s)'%str(args))
import threading

def ip_address():
    """Platform-independent way to get local host IP address"""
    return [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close())\
        for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]

import liteCNS
CNSMap = {}# local map of cnsName to host:port
def _hostPort(cnsNameDev):
    """Return host;port of the cnsName,Dev try it first from already 
    registered recores, or from the name service"""
    global CNSMap
    cnsName,dev = cnsNameDev
    try:  
        hp,dev = CNSMap[cnsName]# check if cnsName is in local map
    except  KeyError:
        #print('cnsName '+str(cnsName)+' not in local map')
        try:    hp = liteCNS.hostPort(cnsName)
        except NameError:
            msg = 'WARNING. Cannot resolve cnsName %s, trying it as is.'%str(cnsName)
            #raise   NameError(msg)
            print(msg)
            hp = cnsName
        # register externally resolved cnsName in local map
        print('cnsName %s is locally registered as '%cnsName+str((hp,dev)))
        CNSMap[cnsName] = hp,dev
    return hp

def devices(info):
    """Return set of device names from LdoPars.info()"""
    return {i.split(':')[0] for i in info.keys()}

def _recvUdp(socket,socketSize):
    """Receive the chopped UDP data"""
    chunks = []
    tryMore = 5
    ts = timer()
    ignoreEOD = 2
    retransmitInProgress = False
    while tryMore:
        try:
            buf, addr = socket.recvfrom(socketSize)
        except Exception as e:
            msg = 'LATimeout'
            #printw('in recvfrom '+str(e))
            
            buf = None
        if buf is None:
            raise RuntimeError(msg)
        size = len(buf) - PrefixLength
        offset = int.from_bytes(buf[:PrefixLength],'big')# python3
        #print('prefix', repr(buf[:PrefixLength]))
        #print('offset',offset)
        
        #print('chunk received '+str((offset,size)))
        if size > 0:    chunks.append((offset,size,buf[PrefixLength:]))
        if offset > 0:
            continue

        if size == 0:
            ignoreEOD -= 1
            if ignoreEOD >= 0:
                #print('premature EOD received, ignore it')
                continue
            else:
                #print('ERR.LA. Looks like first chunk is missing')
                pass
        else:
            #print('First chunk received')
            pass
        # check for holes
        chunks = sorted(chunks)
        prev = [0,0]
        allAssembled = True
        for offset,size,buf in chunks:
            #print('check offset,size:'+str((offset,size)))
            if prev[0] + prev[1] == offset:
                prev = [offset,size]
                continue
            if retransmitInProgress:
                break
            retransmitInProgress = True
            prev[1] = offset
            cmd = {'cmd':('retransmit',prev)}
            print('Asking to retransmit '+str(cmd))
            socket.sendto(ubjson.dumpb(cmd),addr)
            allAssembled = False
            break
        if allAssembled:
            break
        tryMore -= 1
    ts1 = timer()
        
    if not allAssembled:
        raise BufferError('Partial assembly of %i frames'%len(chunks))

    data = bytearray()
    chunks = sorted(chunks)
    for offset,size,buf in chunks:
        printd('assembled offset,size '+str((offset,size)))
        data += buf
    tf = timer()
    if len(data) > 500000:
        printd('received %i bytes in %.3fs, assembled in %.6fs'\
        %(len(data),ts1-ts,tf-ts1))
    printd('assembled %i bytes'%len(data))
    #print(str(data)[:200]+'...'+str(data)[-60:])
    return data, addr

class Channel():
    Perf = False
    """Provides access to host;port"""#[(dev1,[pars1]),(dev2,[pars2]),...]
    def __init__(self,hostPort, devParDict={}, timeout=10):
        #print('>Channel',devParDict)
        self.devParDict = devParDict
        self.hostPort = hostPort
        hp = self.hostPort.split(';',1)
        self.sHost = hp[0]
        if self.sHost.lower() in ('','localhost'): self.sHost = ip_address()
        try:    self.sPort = int(hp[1])
        except: self.sPort = 9700
        self.lHost = ip_address()
        self.lPort = self.sPort
        self.name = ';'.join((str(self.lHost),str(self.lPort)))
        self.recvMax = 1024*1024*4
        try:
            import pwd
            self.username = pwd.getpwuid(getuid()).pw_name
        except:
            printe('getpwuid not supported')
            self.username = 'Unknown'
        self.program = sys.argv[0]
        if UDP:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            #self.sock.bind((self.lHost,self.lPort)) #we can live without bind
            self.sock.settimeout(timeout)
        #print('%s client of %s, timeout %s'
        #%(('TCP','UDP')[UDP],str((self.sHost,self.sPort)),str(timeout)))

    def _recvDictio(self):
        if UDP:
            #data, addr = self.sock.recvfrom(socketSize)
            printd('>_recvUdp')
            try:
                data, addr = _recvUdp(self.sock,socketSize)
            except RuntimeError as e:
                print('RuntimeError in _recvUdp: '+str(e))
                raise RuntimeError(str(e)+' waiting for reply for: '\
                +str(self.lastDictio))
            printd('<_recvUdp')
            # acknowledge the receiving
            self.sock.sendto(b'ACK', (self.sHost, self.sPort))
            printd('ACK sent to '+str((self.sHost, self.sPort)))
            #self.sock.sendto(b'ACK', (self.sHost, self.sPort))
            #printd('ACK2 sent to '+str((self.sHost, self.sPort)))
        else:
            if True:#try:
                data = self.sock.recv(self.recvMax)
                self.sock.close()
                addr = (self.lHost,self.lPort)
            else:#except Exception as e:
                printw('in sock.recv:'+str(e))
                return {}
        #print('received %i bytes'%(len(data)))
        #printd('received %i of '%len(data)+str(type(data))+' from '+str(addr)':')
        # decode received data
        # allow exception here, it willl be caught in execute_cmd
        if len(data) == 0:
            printw('empty reply for: '+str(self.lastDictio))
            return {}
        try:
            decoded = ubjson.loadb(data)
        except Exception as e:
            msg = 'exception in ubjson.load: %s'%str(e)
            print(msg+'. Data[%i]:'%len(data))
            print(str(data)[:150])
            #raise ValueError('in _recvDictio: '+msg)
            return {}
        
        printd('_recvDictio decoded:'+str(decoded)[:200]+'...')
        if not isinstance(decoded,dict):
            #print('decoded is not dict')
            return decoded
        for cnsDev in decoded:
            # items could by numpy arrays, the following should decode everything:
            parDict = decoded[cnsDev]
            for parName,item in list(parDict.items()):
                printd('parName:'+parName)
                try:# check if it is numpy array
                    shape,dtype = parDict[parName]['n']
                    v = parDict[parName]['v']
                    parDict[parName]['v'] = frombuffer(v,dtype).reshape(shape)
                    del parDict[parName]['n']
                except:# OK. it is not numpy.
                    pass
        return decoded

    def _sendDictio(self,dictio):
        """low level send"""
        self.lastDictio = dictio.copy()
        printd('executing: '+str(dictio))
        dictio['username'] = self.username
        dictio['program'] = self.program
        dictio['pid'] = getpid()
        encoded = ubjson.dumpb(dictio)
        if UDP:
            self.sock.sendto(encoded, (self.sHost, self.sPort))
        else:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                self.sock.connect((self.lHost,self.lPort))
            except Exception as e:
                printe('in sock.connect:'+str(e))
                sys.exit()
            self.sock.sendall(encoded)

    def _llTransaction(self,dictio):
        # low level transaction
        self._sendDictio(dictio)
        return  self._recvDictio()

    def _sendCmd(self,cmd,values=None):
        import copy
        devParDict = self.devParDict
        printd('devParDict %s, name %s'%(str(devParDict),self.name))
        if cmd == 'set':
            if len(devParDict) != 1:
                raise ValueError('Set is supported for single device only')
            devParDict = copy.deepcopy(devParDict)# that is IMPORTANT! otherwise setting in liteSceler.yaml is failing 
            #for key,value in zip(devParDict,values):
            #    devParDict[key] += 'v',value
            for key in devParDict:
                devParDict[key] += 'v',values
        devParList = list(devParDict.items())
        dictio = {'cmd':(cmd,devParList)}
        printd('sending cmd: '+str(dictio))
        self._sendDictio(dictio)

    def _transaction(self,cmd,value=None):
        # normal transaction: send command, receive response
        if Channel.Perf: ts = timer()
        self._sendCmd(cmd,value)
        r = self._recvDictio()
        if Channel.Perf: print('transaction time: %.5f'%(timer()-ts))
        #print('reply from channel %s:'%self.name+str(r))
        return r
    
class LdoPars(object): #inheritance from object is needed in python2 for properties to work
    """Access to multiple LDOs and parameters"""
    Dbg = False
    def __init__(self, ldoPars, timeout=5):
        self.timeout = timeout
        #print('ldoPars',ldoPars)
        if isinstance(ldoPars[0],str):
            ldoPars = [ldoPars]
            print('standardized ldoPars',ldoPars)
        self.name = ','.join(ldoPars[0][0])
        #print('lpname',self.name)
        
        # unpack arguments to hosRequest map
        self.channelMap = {}
        for ldoPar in ldoPars:
            #print('ldoPar',ldoPar)            
            ldo,pars = ldoPar
            if isinstance(pars,str): pars = [pars]
            ldoHost = _hostPort(ldo)
            cnsNameDev = ','.join(ldoPar[0])
            #print('ldoHost,cnsNameDev',ldoHost,cnsNameDev)
            if ldoHost not in self.channelMap:
                self.channelMap[ldoHost] = {cnsNameDev:[pars]}
                #print('created self.channelMap[%s]='%str(ldoHost)+ str(self.channelMap[ldoHost]))
            else:
                try:
                    #print(('appending old cnsNameDev %s%s with '%(ldoHost,cnsNameDev)+str(pars[0]))
                    self.channelMap[ldoHost][cnsNameDev][0].append(pars[0])
                except:
                    #print(('creating new cnsNameDev %s%s with '%(ldoHost,cnsNameDev)+str(pars))
                    self.channelMap[ldoHost][cnsNameDev] = [pars]
                #print(('updated self.channelMap[%s]='%ldoHost\
                #+ str(self.channelMap[ldoHost]))
        channelList = list(self.channelMap.items())
        printd('cnannelList constructed: '+pformat(channelList))
        self.channels = [Channel(*i) for i in channelList]
        return

    def devices(self):
        """Return list of devices on associated host;port"""
        return self.channels[0]._llTransaction({'cmd':['info']})

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
            printw('in _firstValueAndTime: '+str(e))
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
        """Request from server first item of the LdoPars and return its 
        value and timestamp,"""
        return self._firstValueAndTime()

    @value.setter
    def value(self,value):
        """Send command to set the value to the first item of the LdoPars"""
        return self.set(value)
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,

    def read(self):
        """Return only readable parameters"""
        for channel in self.channels:
            return channel._transaction('read')

    def set(self,value):
        r = self.channels[0]._transaction('set',value)
        if isinstance(r,str):
            raise RuntimeError(r)
        return r

    #``````````````subscription request```````````````````````````````````````
    def subscribe(self, callback=testCallback):
        """Calls the callback() each time the LdoPars changes"""
        #return 'Not implemented yet'
        thread = threading.Thread(target=self.subsThread, args = [callback])
        thread.daemon = True
        thread.start()

    def unsubscribe(self):
        channel = self.channels[0]
        try:
            channel.sock.settimeout(0.5)
            channel._sendCmd('unsubscribe')
        except: pass
        #channel.sock.close()
        self.subscriptionCancelled = True
        
    def subsThread(self,callback):
        if len(self.channels) > 1:
            raise NameError('subscription is supported only for single host;port')
        channel = self.channels[0]
        channel.sock.settimeout(None)# set the socket in blocking mode
        channel._sendCmd('subscribe')
        print('subscription thread started with callback '+str(callback))
        #while channel.sock.fileno() >= 0:
        self.subscriptionCancelled = False
        while not self.subscriptionCancelled:
            try:
                r = channel._recvDictio()
            except Exception as e:
                printw('in subscription thread socket closed: '+str(e))
                break
            callback(r)
        print('subscription thread finished')
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,

