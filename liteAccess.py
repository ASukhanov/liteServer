#!/usr/bin/env python3
"""Base class for accessing multiple Process Variables, served by a liteServer.
Usage:

Create access to multiple PVs:
  pvs = liteAccess.PV(['host;port',['dev1','dev2'...],['par1','par2'...]])
  # This will create an access object for PVs: dev1,par1; dev2,par2,; etc...
  # Note 1, the bracket can be omitted when accessing single item.
  # Note 2, all elements can be addressed using empty string: ''
  # The 'host;port'='' refers to the local host.
  # Examples:
  liteAccess.PV(['hostname']): list of all devices on a host
  liteAccess.PV(['']):  list of all devices on local host
  single_PV_on_local_host = liteAccess.PV(['','server','version'])
  versions_of dev1_and_dev2_on_acnlin23 = liteAccess.PV(['acnlinec23',['dev1','dev2'],'version'])
  all_PVs_of_the_dev1_and_dev2 = liteAccess.PV(['acnlinec23',['dev1','dev2'],''])

Information about PVs:
  pvs.info(): returns dictionary with properties of associated PVs
  pvs.info(['prop1','prop2',...]): returns dictionary with particualr properties
                                  of associated PVs
  # Note, the info() does not returns values.
  # Examples:
  pvs.info(['count','features'])
  
Get values of the associated PVs:
  pvs.value: represent values of the associated PVs.
  Supported types: int, float, str, list, dict and numpy.ndarray
  
  # Example:
  print(str(multiple_PV_on_acnlin23.value))
  
Change value of a PV:
  pvs.value = new_value

Command line usage examples:
liteAccess.py -i            # list all device and parameters on local host
liteAccess.py -i ::         # same
liteAccess.py -i acnlin23:: # same on host 'acnlin23'
liteAccess.py -i :server:   # show info of all parameter os device 'server'
liteAccess.py -i :dev1:     # show info of all parameter os device 'dev1'
liteAccess.py :dev1:frequency # get dev1:frequency
liteAccess.py :dev2:counters # get array of counters of dev1
liteAccess.py :dev2:image   # get numpy array of an image
liteAccess.py :dev1:frequency=2 # set frequency of dev2 to 2

"""
#__version__ = 'v01 2018-12-17'# created
#__version__ = 'v02 2018-12-17'# python3 compatible
#__version__ = 'v03 2018-12-19'#
#__version__ = 'v04 2018-12-26'# release
#__version__ = 'v05 2018-12-31'# timeout interception for sock.recvfrom
#__version__ = 'v06 2019-01-04'# socketSize increased
#__version__ = 'v07 2019-01-04'# -t timeout argument
#__version__ = 'v08 2019-01-06'# more detailed printing on timeout
#__version__ = 'v09 2019-01-17'# socket size set to UDP max (64k), timeout 0.1,
#__version__ = 'v10 2019-02-04'# bug fixed in main
#__version__ = 'v11 2019-05-21'# abridged printing
#__version__ = 'v12 2019-06-07'# TCP OK, debugging OK
#__version__ = 'v13 2019-06-07'# get(), set() info()
#__version__ = 'v14 2019-06-09'# numpy array support
#__version__ = 'v15 2019-06-10'# socket timeout defaulted to None. Be carefull with this setting 
#__version__ = 'v16 2019-06-10'# UDP Acknowledge
#__version__ = 'v17 2019-06-11'# chunking OK
#__version__ = 'v18 2019-06-17'# release, generic access to multiple or single items
#__version__ = 'v19 2019-06-28'# Dbg behavior fixed 
#__version__ = 'v20 2019-09-18'# try/except on pwd, avoid exception on default start
#__version__ = 'v21 2019-09-23'#
#__version__ = 'v22 2019-11-07'# --period
__version__ = 'v23 2019-11-10'# reconnection

import sys, os, time, socket, traceback
from timeit import default_timer as timer
Python3 = sys.version_info.major == 3
import ubjson

#````````````````````````````Globals``````````````````````````````````````````
UDP = True
PrefixLength = 4
#timeout = None # for socket operations. means blocking None
socketSize = 1024*64 # max size of UDP transfer
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Helper functions`````````````````````````````````
def printi(msg): print('info: '+msg)
def printw(msg): print('WARNING: '+msg)
def printe(msg): print('ERROR: '+msg)
Dbg = False
def printd(msg):
    if Dbg: print('dbg: '+msg)

def ip_address():
    """Platform-independent way to get local host IP address"""
    return [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close())\
        for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]

def recvUdp(socket,socketSize):
    """Receive chopped UDP data"""
    chunks = []
    tryMore = 5
    ts = timer()
    while tryMore:
        buf, addr = socket.recvfrom(socketSize)        
        size = len(buf) - PrefixLength
        offset = int.from_bytes(buf[:PrefixLength],'big')
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

def parsePVname(txt):
    #print('parsePVname',txt)
    try:    hostPort,dev,parProp = txt.split(':')
    except:
        raise NameError('PV access should be: "host;port:dev:par"')
    pp = parProp.split('.')
    try:    par,props = pp
    except: 
        par = pp[0]
        props = ''
    return  hostPort,dev,par,props  

class Channel():
    '''Provides connection to host'''
    def __init__(self,hostPort,timeout=None):
        self.hostPort = hostPort
        hp = self.hostPort.split(';',1)
        self.sHost = hp[0]
        if self.sHost == '': self.sHost = ip_address()
        try:    self.sPort = int(hp[1])
        except: self.sPort = 9700
        self.lHost = ip_address()
        self.lPort = self.sPort
        self.recvMax = 1024*1024*4
        try:
            import pwd
            self.username = pwd.getpwuid(os.getuid()).pw_name
        except:
            printe('getpwuid not supported')
            self.username = 'Unknown'
        self.program = sys.argv[0]
        if UDP:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            #self.sock.bind((self.lHost,self.lPort)) #we can live without bind
            self.sock.settimeout(timeout)
        print('%s client of %s, timeout %s'
        %(('TCP','UDP')[UDP],str((self.sHost,self.sPort)),str(timeout)))

    def recvDictio(self):
        if UDP:
            #data, addr = self.sock.recvfrom(socketSize)
            printd('>recvUdp')
            data, addr = recvUdp(self.sock,socketSize)
            printd('<recvUdp')
            # acknowledge the receiving
            self.sock.sendto(b'ACK', (self.sHost, self.sPort))
            printd('ACK sent to '+str((self.sHost, self.sPort)))
        else:
            if True:#try:
                r = ''
                data = self.sock.recv(self.recvMax)
                self.sock.close()
                addr = (self.lHost,self.lPort)
            else:#except Exception as e:
                printw('in sock.recv:'+str(e))
                r = ''
        printd('received %i of '%len(data)+str(type(data))+' from '+str(addr)+':')
        #printd(str(data.decode())) # don't print it here, could be utf8 issue
        decoded = ubjson.loadb(data)
        printd(str(decoded)[:200]+'...')
        try:
            # assume the dictionary is ordered, take the first value
            parDict = list(decoded.values())[0]
        except:
            return decoded
        if not isinstance(parDict,dict):
            return decoded
        try: # assume it is numpy array
            shape,dtype = parDict['numpy']
        except Exception as e: # it is not numpy array, 
            #print('not np',e)
            return decoded # standard stuff timestamp and value, no further conversion
        
        # additional decoding of numpy arrays.
        import numpy as np
        # this section is fast, 18us for 56Kbytes
        #shape,dtype = parDict['numpy']
        parName = list(decoded)[0]
        ndarray = np.frombuffer(parDict['value'],dtype)
        # replace value in the decoded dict
        #converted = {parName}
        #try: converted = {parName:{'timestamp':parDict['timestamp']}
        #except: pass
        #converted['value'] = ndarray.reshape(shape)}}
        decoded[parName]['value'] = ndarray.reshape(shape)
        return decoded

    def sendDictio(self,dictio):
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
    
channels = {} # map of channels

class PV():
    def __init__(self, hostDevsPars, timeout = None, dbg = False):
        global Dbg
        Dbg = dbg
        #print( '>PV',hostDevsPars)
        # check for argument validity
        hostDevsPars = list(hostDevsPars)
        expectedArg = "(['host;port',['dev1','dev2'...],['par1','par2'...]])"
        def expectedArgWrong():
            raise NameError('Expected arg should be: '+expectedArg)
        if len(hostDevsPars) == 1:
            hostDevsPars += [[''],['']]
        if len(hostDevsPars) == 2:
            hostDevsPars += [['']]
        try:    hostPort, self.devs, self.pars = hostDevsPars
        except: expectedArgWrong()
        if not isinstance(hostPort,str): 
            expectedArgWrong()
        if not isinstance(self.devs,(list,tuple)):
            self.devs = [self.devs]
        if not all(isinstance(i,str) for i in self.devs): 
            expectedArgWrong()
        if not isinstance(self.pars,(list,tuple)):
            self.pars = [self.pars]
        if not all(isinstance(i,str) for i in self.pars):
            expectedArgWrong()
                
        self.name = str(self.devs)+':'+str(self.pars) # used for diagnostics
        try: self.channel = channels[hostPort,timeout]
        except:
             self.channel = Channel(hostPort,timeout)
             channels[hostPort] = self.channel

    #def __del__(self):
    #    self.sock.close()

    def execute_cmd(self, cmd):
        self.channel.sendDictio(cmd)
        if True:#try
            decoded = self.channel.recvDictio()
        else:#except Exception as e:
            # that could happen if timeout was too small, try once more
            sleepTime= 0.5
            time.sleep(sleepTime)
            if True:#try:
                decoded = self.channel.recvDictio()
            else:#except:
                #msg = 'ERROR: Data lost (no data in %f'%sleepTime+' s).'\
                #  +traceback.format_exc()
                msg = 'no response for '+str(cmd)+' in %.2f'%sleepTime+' s.'
                printe(msg)
                #raise BrokenPipeError('ERROR: '+msg)
                return
            print('WARNING: timeout %f'%timeout+' too small')
        isText = isinstance(decoded,str) if Python3 else isinstance(decoded,unicode)
        if isText:
            msg = 'from liteServer: ' + decoded
            printe(msg)
            raise Exception(msg)
        if Dbg:
            txt = str(decoded)
            print('decoded:'+txt[:200]+'...'+txt[-40:])
        return decoded

    @property # to manipulate value
    def value(self): # getter
        '''Getter/setter of PV/property'''
        # return value and timestamp
        return self.execute_cmd({'cmd':('get',(self.devs,self.pars))})

    @value.setter
    def value(self,value):
        printd('setter called '+self.name+' = '+str(value))
        r = self.execute_cmd({'cmd':\
            ('set',(self.devs,self.pars,['value'],value))})
        return r
    
    @value.deleter
    def value(self):
        printd("deleter of v called")
        
    def info(self,props=['']):
        # returns information about remote parameter
        if not isinstance(props,list):
           props = [props]
        return self.execute_cmd({'cmd':('info',(self.devs,self.pars\
        ,props))})

    def monitor(self, pvName, callback):
        """Calls the callback() each time parameter changes"""
        return 'Not implemented yet'

#````````````````````````````Test program`````````````````````````````````````
if __name__ == "__main__":
    import argparse
    from argparse import RawTextHelpFormatter
    parser = argparse.ArgumentParser(description=__doc__\
      ,formatter_class=RawTextHelpFormatter)
    parser.add_argument('-d','--dbg', action='store_true', help='debugging')
    parser.add_argument('-i','--info',action='store_true',help=\
    'List of devices,parameters or features')
    parser.add_argument('-t','--timeout',type=float,default=10,
      help='timeout of the receiving socket')
    parser.add_argument('-p','--period',type=float,default=0.,
      help='repeat command every period (s)')
    pvsDefault = ['::']
    parser.add_argument('pvs',nargs='*',default=pvsDefault,help=\
    'Process Variables: host;port:device:parameter')
    pargs = parser.parse_args()
    if not pargs.info and pargs.pvs == pvsDefault:
        print('Please specify :device:parameter')
        sys.exit()

    def printSmart(txt):
        print('reply:',end='')#flush=True
        if len(txt)>200: txt = txt[:200]+'...'+txt[-40:]
        print(txt)

    print('pargs.pvs',pargs.pvs,pargs.period)
    def reconnect():
        pvProps = []
        for parval in pargs.pvs:
            try:    pvname,val = parval.split('=',1)
            except: pvname = parval
            hdpe = parsePVname(pvname)
            pvProps.append((PV(hdpe[:3],timeout=pargs.timeout,dbg=pargs.dbg)\
            ,hdpe[3]))
        return pvProps
    pvProps = reconnect()

    while True:
        for pv,prop in pvProps:
            val = None
            try:
                if pargs.info:
                    printSmart(str(pv.info(prop)))
                    continue
                if val: # set() action
                    try:    val = float(val)
                    except: pass
                    pv.value = val
                else:   # get() action
                    ts = timer()
                    value = pv.value
                    print('Get time: %.4f'%(timer()- ts))
                    printSmart(str(value))
            except socket.timeout as e:
                #exc_type, exc_obj, exc_tb = sys.exc_info()
                #printe('Exception %s: '%exc_type+str(e))
                printw('socket.timeout with %s, reconnecting.'%pv.name)
                pvProps = reconnect()
                continue
            
        if pargs.period == 0.:
            break
        else:
            time.sleep(pargs.period)

