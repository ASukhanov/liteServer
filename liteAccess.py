#!/usr/bin/env python
"""Base class for accessing multiple Process Variables, served by a liteServer.
Usage:

Create access to multiple PVs:
  pvs = liteAccess.PV(['host;port',['dev1','dev2'...],['par1','par2'...]])
  # This will create an access object for PVs: dev1,par1; dev2,par2,; etc...
  # Note 1, the bracket can be omitted when accessing single item.
  # Note 2, all elements can be addressed using empty string: ''
  # The 'host;port'='' refers to the local host.

  # Examples: info on all PVs on all devices
pvHost = liteAccess.PV(['localhost'])# '' is for localhost
pvHostInfo = pvHost.info()
print('Info about all PVs on host '+pvHost.name+' :\n'+str(pvHostInfo))
deviceSet = {i.split(':')[0] for i in pvi.keys()}
print('Devices on host '+pvHost.name+' :\n'+str(deviceSet))
  
  # get dictionary of all PVs on the localhost:server device
pvServer = liteAccess.PV(['',['server']])
pvServerInfo = pvServer.info()
print('Info of PVs of %s :\n'%pvServer.name + str(pvServerInfo))
pvServerValues = pvServer.values()
print('Values of all PVs of %s :\n'%pvServer.name + str(pvServerValues))
  
  # get value and timestamp of a first PV of dev1
pvDev1 = liteAccess.PV(['',['dev1']])
pvDev1Info = pvDev1.info()
print('Info of PVs of %s :\n'%pvDev1.name + str(pvDev1Info))
v,t = pvDev1.value
print('Value of the first PV of %s :'%pvDev1.name + str(v))
print('Timestamp of the first PV of %s :'%pvDev1.name + str(t))

  # get values of all measurable PVs of dev1
pvDev1Measurement = pvDev1.measure()
print('Values of all measurable PVs of  %s :'%pvDev1.name)
for item,value in pvDev1Measurement.items():
    print(item+': '+str(value))

  # change value of a PV
pvFreq1 = liteAccess.PV(['',['dev1'],['frequency']])
v,t = pvFreq1.value
pvFreq1.value = [v+1]
print('dev1 frequency changed from %s to %s'%(str(v),str(pvFreq1.value[0])))
  
Command line usage examples:
liteAccess.py -i            # list all device and parameters on local host
liteAccess.py -i ::         # same
liteAccess.py -i acnlin23:: # same on host 'acnlin23'
liteAccess.py -i "acnlin23;9700::" # same for port 9700, 
liteAccess.py -i :server:   # show info of all parameter os device 'server'
liteAccess.py -i :dev1:     # show info of all parameter os device 'dev1'
liteAccess.py :dev1:frequency # get dev1:frequency
liteAccess.py :dev2:counters # get array of counters of dev1
liteAccess.py :dev2:image   # get numpy array of an image
liteAccess.py :dev1:frequency=2 # set frequency of dev2 to 2

"""
#``````````````````Python2/3 compatibility````````````````````````````````````
from __future__ import print_function
from __future__ import unicode_literals
import sys
Python2 = sys.version_info.major == 2
if not Python2:
    basestring = str
    unicode = str
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,

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
#__version__ = 'v23 2019-11-10'# reconnection
#__version__ = 'v24 2019-11-10'# Python2/3 compatible
#__version__ = 'v25 2019-11-10'# numpy array correctly decoded in multi-parameter requests
#__version__ = 'v26 2019-11-25'# get() returns {timestamp,value}, numpy decoding fixed 
#__version__ = 'v27a 2019-11-25'# firstValue()
#__version__ = 'v28 2019-11-27'# catch exception in execute_cmd
#__version__ = 'v29 2019-12-03'# firstValue python2/3 compatibility
#__version__ = 'v30 2019-12-06'# fix except: expectedArgWrong()
#__version__ = 'v31 2019-12-09'# socket timeout defaulted to 5
__version__ = 'v32a 2019-12-10'# measurements() method for requesting only measurable parameters

import os, time, socket, traceback
from timeit import default_timer as timer
import numpy as np
import ubjson

#````````````````````````````Globals``````````````````````````````````````````
UDP = True
PrefixLength = 4
socketSize = 1024*64 # max size of UDP transfer
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Helper functions`````````````````````````````````
def printi(msg): print('info: '+msg)
def printw(msg): print('WARNING: '+msg)
def printe(msg): print('ERROR: '+msg)
def printd(msg):
    if PV.Dbg: print('dbg: '+msg)

def ip_address():
    """Platform-independent way to get local host IP address"""
    return [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close())\
        for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]

def devices(info):
    """Return set of device names from PV.info()"""
    return {i.split(':')[0] for i in info.keys()}

def _recvUdp(socket,socketSize):
    """Receive chopped UDP data"""
    chunks = []
    tryMore = 5
    ts = timer()
    while tryMore:
        buf, addr = socket.recvfrom(socketSize)        
        size = len(buf) - PrefixLength
        if Python2:
            import struct
            offset = struct.unpack(">I",buf[:PrefixLength])[0]
        else:
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

class _Channel():
    """Provides connection to host"""
    def __init__(self,hostPort,timeout=None):
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
            self.username = pwd.getpwuid(os.getuid()).pw_name
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

    def recvDictio(self):
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
        printd('received %i of '%len(data)+str(type(data))+' from '+str(addr)+':')
        #printd(str(data.decode())) # don't print it here, could be utf8 issue
        
        # allow exception here, it willl be caught in execute_cmd
        decoded = ubjson.loadb(data)
        
        printd('recvDictio decoded:'+str(decoded)[:200]+'...')
        if not isinstance(decoded,dict):
            printd('decoded is not dict')
            return decoded
        # items could by numpy arrays, the following should decode everything:
        for parName,item in list(decoded.items()):
            printd('parName:'+parName)
            try:# check if it is numpy array
                shape,dtype = decoded[parName]['numpy']
                v = decoded[parName]['value']
                decoded[parName]['value'] = np.frombuffer(v,dtype).reshape(shape)
                del decoded[parName]['numpy']
            except:# OK. it is not numpy.
                pass
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

class PV(object): #inheritance from object is needed in python2 for properties to work
    Dbg = False
    def __init__(self, hostDevsPars, timeout = 5):
        #print( '>PV',hostDevsPars)
        # check for argument validity
        hostDevsPars = list(hostDevsPars)
        expectedArg = "(['host;port',['dev1','dev2'...],[u'par1',u'par2'...]])"
        def expectedArgWrong(msg):
            raise NameError('Expected arg should be: '+expectedArg)
        if len(hostDevsPars) == 1:
            hostDevsPars += [[''],['']]
        if len(hostDevsPars) == 2:
            hostDevsPars += [['']]
        try:    hostPort, self.devs, self.pars = hostDevsPars
        except: expectedArgWrong('hostDevsPars')
        if not isinstance(hostPort,basestring): 
            expectedArgWrong()
        if not isinstance(self.devs,(list,tuple)):
            self.devs = [self.devs]
        #if not all(isinstance(i,basestring) for i in self.devs): 
        #    expectedArgWrong()
        # in case of python2 the strings should be unicode
        self.devs = [unicode(i) for i in self.devs]
        if not isinstance(self.pars,(list,tuple)):
            self.pars = [self.pars]
        #if not all(isinstance(i,basestring) for i in self.pars):
        #    expectedArgWrong()
        self.pars = [unicode(i) for i in self.pars]
        self.name = ':'.join([hostPort,str(self.devs),str(self.pars)])# used for diagnostics
        self.timeout = timeout
        try: self.channel = channels[hostPort,timeout]
        except:
             self.channel = _Channel(hostPort,timeout)
             channels[hostPort] = self.channel
        self.name = ':'.join([self.channel.name,str(self.devs),str(self.pars)])# used for diagnostics        

    #def __del__(self):
    #    self.sock.close()

    def execute_cmd(self, cmd):
        ts = time.time()
        self.channel.sendDictio(cmd)
        try:
            decoded = self.channel.recvDictio()
        except Exception as e:
            # that could happen if timeout was too small, try once more
            print('Exception in execute_cmd: '+str(e))
            sleepTime= 0.5
            time.sleep(sleepTime)
            try:
                decoded = self.channel.recvDictio()
            except Exception as e:
                #msg = 'ERROR: Data lost (no data in %f'%sleepTime+' s).'\
                #  +traceback.format_exc()
                msg = 'no response for '+str(cmd)+' in %.2f'%(time.time()-ts)\
                +'s. '+str(e)
                printe(msg)
                #raise BrokenPipeError('ERROR: '+msg)
                return None
            print('WARNING: timeout %f'%self.timeout+' too small')
        isText = isinstance(decoded,basestring)
        if isText:
            msg = 'from liteServer: ' + decoded
            printe(msg)
            raise Exception(msg)
        if PV.Dbg:
            txt = str(decoded)
            print('decoded:'+txt[:200]+'...'+txt[-40:])
        return decoded

    def info(self,props=['']):
        """Return information about requested PV on server"""
        if not isinstance(props,list):
           props = [props]
        return self.execute_cmd({'cmd':('info',(self.devs,self.pars\
        ,props))})

    def values(self):
        """Request from server all items of the PV, return dictionary of items""" 
        return self.execute_cmd({'cmd':('get',(self.devs,self.pars))})

    def measurements(self):
        """Request from server all measurable items of the PV, return 
        dictionary of items."""
        return self.execute_cmd({'cmd':('measure',(self.devs,self.pars))})

    def _firstValueAndTime(self):
        r = self.execute_cmd({'cmd':('get',([self.devs[0]],[self.pars[0]]))})
        v = list(r.values())[0]
        try:    ts = v['timestamp']
        except: ts = None
        return v['value'], ts

    #``````````````Property 'value````````````````````````````````````````````
    @property
    def value(self):
        """Request from server first item of the PV and return its 
        value and timestamp,"""
        return self._firstValueAndTime()

    @value.setter
    def value(self,value):
        """Send to server command to set the value to the first item of the PV"""
        #print('setter called '+self.name+' = '+str(value))
        r = self.execute_cmd({'cmd':\
            ('set',([self.devs[0]],[self.pars[0]],['value'],value))})
        return r
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #``````````````subscribtion request```````````````````````````````````````
    def subscribe(self, callback):
        """Calls the callback() each time the PV changes"""
        return 'Not implemented yet'
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
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
    PV.Dbg = pargs.dbg

    def printSmart(txt):
        print('reply:',end='')#flush=True
        if len(txt)>200: txt = txt[:200]+'...'+txt[-40:]
        print(txt)

    #print('pargs.pvs',pargs.pvs,pargs.period)
    def reconnect():
        pvPropVals = []
        for parval in pargs.pvs:
            val = None
            try:    pvname,val = parval.split('=',1)
            except: pvname = parval
            hdpe = parsePVname(pvname)
            pvPropVals.append((PV(hdpe[:3],timeout=pargs.timeout)\
            ,hdpe[3],val))
        return pvPropVals
    pvPropVals = reconnect()

    while True:
        for pv,prop,val in pvPropVals:
            try:
                if pargs.info:
                    v = pv.info(prop)
                    printSmart(str(v))
                    continue
                if val is not None: # set() action
                    try:    val = float(val)
                    except: pass
                    #print('pv.value = '+str(val))
                    pv.value = val
                else:   # get() action
                    ts = timer()
                    value = pv.value
                    print('Get time: %.4f'%(timer()- ts))
                    print('got values for: '+str(value.keys()))
                    printSmart(str(value))
            except socket.timeout as e:
                #exc_type, exc_obj, exc_tb = sys.exc_info()
                #printe('Exception %s: '%exc_type+str(e))
                printw('socket.timeout with %s, reconnecting.'%pv.name)
                pvPropVals = reconnect()
                continue
            
        if pargs.period == 0.:
            break
        else:
            time.sleep(pargs.period)

