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
__version__ = 'v13 2019-06-07'# get(), set() ls()

import sys, os, pwd, time, socket, traceback
Python3 = sys.version_info.major == 3
import ubjson

UDP = True

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
            
        #self.timeout = timeout
        #self.sock.settimeout(self.timeout)
        print('%s client of %s'%(('TCP','UDP')[UDP],str(server)))

    def __del__(self):
        self.sock.close()

    def _recvfrom(self):
        if UDP:
            data, addr = self.sock.recvfrom(socketSize)
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
        r = ubjson.loadb(data)
        printd(str(r))
        return r

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
            r = self._recvfrom()
        else:#except Exception as e:
            # that could happen if timeout was too small, try once more
            sleepTime= 0.5
            time.sleep(sleepTime)
            if True:#try:
                r = self._recvfrom()
            else:#except:
                #msg = 'ERROR: Data lost (no data in %f'%sleepTime+' s).'\
                #  +traceback.format_exc()
                msg = 'no response for '+str(cmd)+' in %.2f'%sleepTime+' s.'
                printe(msg)
                #raise BrokenPipeError('ERROR: '+msg)
                return
            print('WARNING: timeout %f'%self.timeout+' too small')
        isText = isinstance(r,str) if Python3 else isinstance(r,unicode)
        if isText:
            msg = 'from liteServer: ' + r
            printe(msg)
            raise Exception(msg)
        printd('decoded: '+str(r)[:200])
        return r

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
    parser.add_argument('-t','--timeout',type=float,default=0.1,
      help='timeout of the receiving socket')
    parser.add_argument('par',help='',nargs='*')
    pargs = parser.parse_args()
    prefix = 'Reply from '+pargs.host+':'+str(pargs.port)+': '

    liteAccess = LiteAccess((pargs.host,pargs.port), pargs.dbg, pargs.timeout)

    if len(pargs.par) == 0:
        pargs.ls = True

    from timeit import default_timer as timer
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
            # get action
            d = liteAccess.get(pargs.par)
            for item,val in d.items():
                l = len(val)
                suffix = '} length='+str(l)
                txt = str(val) if l <= 20 else str(val[:20])[:-1]+',...]'
                print(prefix+'{'+item+':'+txt+suffix)
        else:
            # set action
            try:    val = float(val)
            except: pass
            print(prefix+str(liteAccess.set((par,val))))
    print('Execution time: %.4f'%(timer()- ts))

