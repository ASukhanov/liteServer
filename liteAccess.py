#!/usr/bin/env python3
"""Base class for accessing Process Variables, served by a liteServer."""
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
#__version__ = 'v13 2019-06-07'# get(), set() ls()
#__version__ = 'v14 2019-06-09'# numpy array support
#__version__ = 'v15 2019-06-10'# socket timeout defaulted to None. Be carefull with this setting 
#__version__ = 'v16 2019-06-10'# UDP Acknowledge
__version__ = 'v17 2019-06-11'# chunking OK

import sys, os, pwd, time, socket, traceback
from timeit import default_timer as timer
Python3 = sys.version_info.major == 3
import ubjson

UDP = True
PrefixLength = 4

#````````````````````````````Globals``````````````````````````````````````````
socketSize = 1024*64 # 1K ints need 2028 bytes
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
        print('received %i bytes in %.3fs, assembled in %.6fs'\
        %(len(data),ts1-ts,tf-ts1))
    printd('assembled %i bytes'%len(data))
    #print(str(data)[:200]+'...'+str(data)[-60:])
    return data, addr

class LiteAccess():
    def __init__(self, server, dbg = False, timeout = None):
        global Dbg
        Dbg = dbg
        self.sHost = server[0]
        self.sPort = server[1]
        self.lHost = ip_address()
        self.lPort = self.sPort
        self.recvMax = 1024*1024*4
        self.username = pwd.getpwuid(os.getuid()).pw_name
        self.program = sys.argv[0]
        if UDP:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            #self.sock.bind((self.lHost,self.lPort)) #we can live without bind
            
        self.timeout = timeout
        self.sock.settimeout(self.timeout)
        print('%s client of %s, timeout %s'
        %(('TCP','UDP')[UDP],str(server),str(timeout)))

    def __del__(self):
        self.sock.close()

    def _recvfrom(self):
        if UDP:
            #data, addr = self.sock.recvfrom(socketSize)
            data, addr = recvUdp(self.sock,socketSize)
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
            parDict = list(decoded.values())[0]
        except:
            return decoded
        if not isinstance(parDict,dict):
            return decoded
        #print('parDict',str(parDict)[:200])
        try: # assume it is numpy array
            shape,dtype = parDict['numpy']
        except Exception as e: # it is not numpy array, 
            #print('not np',e)
            return decoded # standard stuff timestamp and values, no further conversion
        
        # additional decoding of numpy arrays.
        import numpy as np
        # this section is fast, 18us for 56Kbytes
        #shape,dtype = parDict['numpy']
        parName = list(decoded)[0]
        ndarray = np.frombuffer(parDict['values'],dtype)
        # replace values in the decoded dict
        #converted = {parName}
        #try: converted = {parName:{'timestamp':parDict['timestamp']}
        #except: pass
        #converted['values'] = ndarray.reshape(shape)}}
        decoded[parName]['values'] = ndarray.reshape(shape)
        return decoded

    def execute_cmd(self, cmd):
        cmd['username'] = self.username
        cmd['program'] = self.program
        printd('executing: '+str(cmd))
        encoded = ubjson.dumpb(cmd)
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
        if True:#try
            decoded = self._recvfrom()
        else:#except Exception as e:
            # that could happen if timeout was too small, try once more
            sleepTime= 0.5
            time.sleep(sleepTime)
            if True:#try:
                decoded = self._recvfrom()
            else:#except:
                #msg = 'ERROR: Data lost (no data in %f'%sleepTime+' s).'\
                #  +traceback.format_exc()
                msg = 'no response for '+str(cmd)+' in %.2f'%sleepTime+' s.'
                printe(msg)
                #raise BrokenPipeError('ERROR: '+msg)
                return
            print('WARNING: timeout %f'%self.timeout+' too small')
        isText = isinstance(decoded,str) if Python3 else isinstance(decoded,unicode)
        if isText:
            msg = 'from liteServer: ' + decoded
            printe(msg)
            raise Exception(msg)
        if Dbg:
            txt = str(decoded)
            print('decoded:'+txt[:200]+'...'+txt[-40:])
        return decoded

    def get(self,arg):
        return self.execute_cmd({'cmd':('get',arg)})

    def set(self,arg):
        return self.execute_cmd({'cmd':('set',arg)})
    
    def ls(self,arg):
        return self.execute_cmd({'cmd':('ls',arg)})

    def monitor(self, pvName, callback):
        """Calls the callback() each time parameter changes"""
        return 'Not implemented yet'

#````````````````````````````Test program`````````````````````````````````````
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=\
      'Test of the LiteAccess')
    parser.add_argument('-d','--dbg', action='store_true', help='debugging')
    parser.add_argument('-p','--port',help='Port number',type=int,default=9999)
    parser.add_argument('-H','--host',default=ip_address(),nargs='?',
      help='Hostname')
    parser.add_argument('-l','--ls',action='store_true',help='List of devices,parameters or features')
    parser.add_argument('-s','--set',action='store_true',help='Set parameter')
    parser.add_argument('-t','--timeout',type=float,default=None,
      help='timeout of the receiving socket')
    parser.add_argument('par',help='',nargs='*')
    pargs = parser.parse_args()
    prefix = 'Reply from '+pargs.host+':'+str(pargs.port)+': '

    liteAccess = LiteAccess((pargs.host,pargs.port), pargs.dbg, pargs.timeout)

    if len(pargs.par) == 0:
        pargs.ls = True

    ts = timer()
    if pargs.ls:
        print(prefix+str(liteAccess.ls(pargs.par)))
        print('Execution time: %.4f'%(timer()- ts))
        sys.exit()
    for parval in pargs.par:
        print('parval',parval)
        try:
            par,val = parval.split('=')
        except:
            # get() action
            d = liteAccess.get(pargs.par)
            txt = str(d)
            if len(txt)>200: txt = txt[:200]+'...'+txt[-40:]
            print(txt)
        else:
            # set() action
            try:    val = float(val)
            except: pass
            print(prefix+str(liteAccess.set((par,val))))
    print('Execution time: %.4f'%(timer()- ts))

