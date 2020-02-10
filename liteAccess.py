"""Base class for accessing multiple Process Variables, served by a liteServer.
#``````````````````Low level usage:```````````````````````````````````````````
import liteAccess as LA
from pprint import pprint
hostPort = '' # empty for local, or IP:port: '130.199.105.240;9700'
llch = LA.Channel(hostPort)
llTrans = llch._llTransaction
    # get short list of devices on the hostPort
pprint(llTrans({'cmd':['info']}))
    # info on all devices, parameters and properties on hostPort
#DNW#pprint(llTrans({'cmd':['info',[['',['']]]]}))
    # info on server device at the hostPort:
pprint(llTrans({'cmd':['info',[['server','*']]]}))
    # info on server.status data obj at the hostPort:
pprint(llTrans({'cmd':['info',[['server',[['status']]]]]}))
    # info on server.status.desc property at the hostPort:
pprint(llTrans({'cmd':['info',[['server',[['status'],['desc']]]]]}))
    # the get command returns timestamped property:
pprint(llTrans({'cmd':['get',[['server'],['status'],['desc']]]}))
    # info of multiple devices and parameters:
pprint(llTrans({'cmd':['info',[('server',[['status','version']]),('dev1',[['frequency']])]]}))
    # get server.version value from the hostPort:
pprint(llTrans({'cmd':['get',[['server',[['version']]]]]}))
    # get all data objects of the server at the hostPort:
pprint(llTrans({'cmd':['get',[['server',['*']]]]}))
    # get multiple parameters from multiple devices on the hostPort
pprint(llTrans({'cmd':['get',[('server',[['status','version']]),('dev1',[['frequency']])]]}))
    # get all readable data objects from a device:
pprint(llTrans({'cmd':['read',[['dev1','*']]]}))
    # get all readable data objects from all devices the the hostPort
#pprint(llTrans({'cmd':['read']}))

    # set:
pprint(llTrans({'cmd':['set',[['dev1',[['frequency'],['value'],[4.]]]]]}))
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#``````````````````Test of LdoPar _transaction, no name service involved``````
ch = LA.Channel(hostPort,{'dev1': [['time','frequency']]})
pprint(ch._transaction('get'))
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#``````````````````High level, using LdoPars and name service`````````````````
    #``````````````Info```````````````````````````````````````````````````````
    # info on single parameter
pprint(LA.LdoPars(['scaler0.dev0','time']).info())
    # info on multiple parameters
pprint(LA.LdoPars(['scaler0.dev0',['time','frequency']]).info())
    # info on all parameters of an ldo
pprint(LA.LdoPars(['scaler0.dev0','*']).info())
    # list of devices on accociated server
pprint(LA.LdoPars(['scaler0.dev0','*']).devices())
    #``````````````Get````````````````````````````````````````````````````````
    # simplified get: returns (value,timestamp) of a parameter (frequency)\
    # from a ldo (scaler0.dev0). 
pprint(LA.LdoPars(['scaler0.dev0','frequency']).value)
    # get single parameter from ldo scaler0.dev0, 
pprint(LA.LdoPars(['scaler0.dev0','frequency']).get())
    # get multiple parameters from an ldo 
pprint(LA.LdoPars(['scaler0.dev0',['time','frequency']]).get())
    # get multiple parameters from multiple ldos 
pprint(LA.LdoPars([['scaler0.dev0',['time','frequency']],['scaler0.dev1',['frequency','time']]]).get())
    #``````````````Read```````````````````````````````````````````````````````
    # get all readable parameters from an ldo
pprint(LA.LdoPars(['scaler0.dev0','*']).read())
    #``````````````set````````````````````````````````````````````````````````
LA.LdoPars(['scaler0.dev0','frequency']).set([6.])
LA.LdoPars(['scaler0.dev0','frequency']).value
    # multiple set
LA.LdoPars([['scaler0.dev0','frequency'],['scaler0.dev1','frequency']]).set([[7.],[8.]])
LA.LdoPars([['scaler0.dev0','frequency'],['scaler0.dev1','frequency']]).get()
    # test for timeout, should timeout in 10s:
LA.LdoPars(['scaler1.dev0','frequency']).value

#v38
    #TODO: test with two servers, what happens if devices have same name?
LA.LdoPars([['scaler0.dev0','frequency'],['scaler1.dev0','frequency']]).get()
    #TODO: 
LA.LdoPars(['scaler0.dev0','frequency']).set(property=('oplimits',[-1,11])
#``````````````````Observations```````````````````````````````````````````````
transaction time of LdoPars is ~3 ms
#``````````````````Tips```````````````````````````````````````````````````````
To enable debugging: LA.LdoPars.Dbg = True
"""
#__version__ = 'v36 2020-02-06'# full re-design
#__version__ = 'v37 2020-02-09'# LdoPars info(), get(), read() set() are good.
__version__ = 'v38 2020-02-10 '# set() raising exceptions on failures

print('liteAccess '+__version__)

import sys, time, socket
from os import getuid
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
def printw(msg): print('WARNING: '+msg)
def printe(msg): print('ERROR: '+msg)
def printd(msg):
    if LdoPars.Dbg: print('LADbg: '+msg)

def ip_address():
    """Platform-independent way to get local host IP address"""
    return [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close())\
        for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]

import liteCNS
CNSMap = {}# local map of ldo to (host:port,dev)
def hostPortDev(ldo):
    global CNSMap
    try:  hpd = CNSMap[ldo]# check if ldo name is in local map
    except  KeyError:
        try:    hpd = liteCNS.hostPortDev(ldo)
        except: raise   NameError('cannot resolve ldo name '+str(ldo))
        # register externally resolved ldo in local map
        print('ldo %s is locally registered: '%ldo+str(hpd))
        CNSMap[ldo] = hpd[0],hpd[1]
    return hpd

def devices(info):
    """Return set of device names from LdoPars.info()"""
    return {i.split(':')[0] for i in info.keys()}

def _recvUdp(socket,socketSize):
    """Receive chopped UDP data"""
    chunks = []
    tryMore = 5
    ts = timer()
    while tryMore:
        buf, addr = socket.recvfrom(socketSize)        
        size = len(buf) - PrefixLength
        offset = int.from_bytes(buf[:PrefixLength],'big')# python3
        #print('prefix', repr(buf[:PrefixLength]))
        #print('offset',offset)
        
        if size > 0:
            printd('chunk received '+str((offset,size)))
            chunks.append((offset,size,buf[PrefixLength:]))
            continue
        printd('EOD detected')
        # check for holes
        chunks = sorted(chunks)
        prev = None
        allAssembled = True
        for offset,size,buf in chunks:
            printd('check offset,size:'+str((offset,size)))
            if prev == None:
                prev = offset,size
                continue
            if prev[0] + prev[1] == offset:
                prev = offset,size
                continue
            printw('hole [%i] in the assembly chain @%i, re-request'\
            %prev)
            cmd = {'cmd':('retransmit',prev)}
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
    """Provides access to host;port"""#[(dev1,[pars1]),(dev2,[pars2]),...]
    def __init__(self,hostPort, devParDict={}, timeout=10):
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
        printd('%s client of %s, timeout %s'
        %(('TCP','UDP')[UDP],str((self.sHost,self.sPort)),str(timeout)))

    def _recvDictio(self):
        if UDP:
            #data, addr = self.sock.recvfrom(socketSize)
            printd('>_recvUdp')
            data, addr = _recvUdp(self.sock,socketSize)
            printd('<_recvUdp')
            # acknowledge the receiving
            self.sock.sendto(b'ACK', (self.sHost, self.sPort))
            printd('ACK sent to '+str((self.sHost, self.sPort)))
        else:
            if True:#try:
                data = self.sock.recv(self.recvMax)
                self.sock.close()
                addr = (self.lHost,self.lPort)
            else:#except Exception as e:
                printw('in sock.recv:'+str(e))
                return None
        printd('received %i of '%len(data)+str(type(data))+' from '+str(addr)\
        +':')
        
        # decode received data
        # allow exception here, it willl be caught in execute_cmd
        decoded = ubjson.loadb(data)
        
        printd('_recvDictio decoded:'+str(decoded)[:200]+'...')
        if not isinstance(decoded,dict):
            #print('decoded is not dict')
            return decoded
        # items could by numpy arrays, the following should decode everything:
        for parName,item in list(decoded.items()):
            printd('parName:'+parName)
            try:# check if it is numpy array
                shape,dtype = decoded[parName]['numpy']
                v = decoded[parName]['value']
                decoded[parName]['value'] = frombuffer(v,dtype).reshape(shape)
                del decoded[parName]['numpy']
            except:# OK. it is not numpy.
                pass
        return decoded

    def _sendDictio(self,dictio):
        """for test purposes only"""
        printd('executing: '+str(dictio))
        dictio['username'] = self.username
        dictio['program'] = self.program
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

    def _sendCmd(self,cmd,values):
        devParDict = self.devParDict
        #print('devParDict',devParDict)
        if cmd == 'set':
            for key,value in zip(devParDict,values):
                devParDict[key] += ['value'],value
        devParList = list(devParDict.items())
        #print('devParList',devParList)
        dictio = {'cmd':(cmd,devParList)}
        dictio['username'] = self.username
        dictio['program'] = self.program
        printd('sending cmd: '+str(dictio))
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

    def _transaction(self,cmd,value=None):
        # normal transaction: send command, receive response
        ts = timer()
        self._sendCmd(cmd,value)
        r = self._recvDictio()
        #print('transaction time: %.5f'%(timer()-ts))
        return r
    
class LdoPars(object): #inheritance from object is needed in python2 for properties to work
    """Access to multiple LDOs and parameters"""
    Dbg = False
    def __init__(self, ldoPars, timeout=5):
        self.timeout = timeout
        #print('ldoPars',ldoPars)
        if isinstance(ldoPars[0],str):
            ldoPars = [ldoPars]
            #print('standardized ldoPars',ldoPars)
        
        # unpack arguments to hosRequest map
        channelMap = {}
        for ldoPar in ldoPars:
            #print('ldoPar',ldoPar)            
            ldo,pars = ldoPar
            if isinstance(pars,str): pars = [pars]
            ldoHost,dev = hostPortDev(ldo)
            if ldoHost not in channelMap:
                channelMap[ldoHost] = {dev:[pars]}
                #print('created channelMap[%s]='%ldoHost\
                #+ str(channelMap[ldoHost]))
            else:
                try:
                    #print(('appending old dev %s%s with '%(ldoHost,dev)+str(pars[0]))
                    channelMap[ldoHost][dev].append(pars[0])
                except:
                    #print(('creating new dev %s%s with '%(ldoHost,dev)+str(pars))
                    channelMap[ldoHost][dev] = [pars]
                #print(('updated channelMap[%s]='%ldoHost\
                #+ str(channelMap[ldoHost]))
        channelList = list(channelMap.items())
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
        firstDict = self.channels[0]._transaction('get')
        firstValsTDict = list(firstDict.values())[0]
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
        print('>set',value)
        r = self.channels[0]._transaction('set',value)
        #print('<set:',r)# do not print here
        if isinstance(r,str):
            raise RuntimeError(r)
        return r

    #``````````````subscribtion request```````````````````````````````````````
    def subscribe(self, callback):
        """Calls the callback() each time the LdoPars changes"""
        return 'Not implemented yet'
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,

