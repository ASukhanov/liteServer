#!/usr/bin/env python3
"""Base class for accessing Process variables, served by a liteServer."""
#__version__ = 'v01 2018-12-17'# created
#__version__ = 'v02 2018-12-17'# python3 compatible
#__version__ = 'v03 2018-12-19'#
__version__ = 'v04 2018-12-26'# release

import sys, socket
Python3 = sys.version_info.major == 3
import ubjson

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
    def __init__(self, server, dbg = False):
        global Dbg
        Dbg = dbg
        self.sHost = server[0]
        self.sPort = server[1]
        self.lHost = ip_address()
        self.lPort = self.sPort
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.lHost,self.lPort))
        self.sock.settimeout(1)

    def _execute_cmd(self, cmd):
        encoded = ubjson.dumpb(cmd)
        #encoded = cmd.encode()
        #encoded = cmd
        self.sock.sendto(encoded, (self.sHost, self.sPort))
        data, addr = self.sock.recvfrom(1024)
        if Dbg:
            print('received '+str(type(data))+' from '+str(addr)+':')
            print(str(data))
        r = ubjson.loadb(data)
        isText = isinstance(r,str) if Python3 else isinstance(r,unicode)
        if isText:
            raise Exception('liteServer.'+r)
        return r
    
    def ls(self,pvName=[]):
        if not isinstance(pvName,list): pvName = [pvName]
        return self._execute_cmd(('ls',pvName))

    def get(self, pvName):
        """Returns timestamp, followed by the parameter values"""
        if not isinstance(pvName,list): pvName = [pvName]
        return self._execute_cmd(('get',pvName))

    def set(self, pvName, vals):
        return self._execute_cmd(('set',pvName,vals))

    def monitor(self, pvName, callback):
        """Calls the callback() each time parameter changes"""
        return 'Not implemented yet'

#````````````````````````````Test program`````````````````````````````````````
if __name__ == "__main__":
    # parse arguments
    import argparse
    parser = argparse.ArgumentParser(description=\
      'Test of the LiteAccess')
    parser.add_argument('-d','--dbg', action='store_true', help='debugging')
    parser.add_argument('-p','--port',help='Port number',type=int,default=9999)
    parser.add_argument('-H','--host',help='Hostname',default='acnlinec',nargs='?')
    parser.add_argument('-l','--ls',action='store_true',help='List of devices,parameters or features')
    parser.add_argument('-s','--set',action='store_true',help='Set parameter')
    parser.add_argument('par',help='',nargs='*')
    pargs = parser.parse_args()
    suffix = 'Reply from '+pargs.host+':'+str(pargs.port)+': '

    liteAccess = LiteAccess((pargs.host,pargs.port),pargs.dbg)

    if len(pargs.par) == 0:
        pargs.ls = True
        
    from timeit import default_timer as timer
    ts = timer()
    if pargs.ls:
        print(suffix+str(liteAccess.ls(pargs.par)))
        
    elif pargs.set:
        vals = [float(i) for i in pargs.par[1:]]
        print(suffix+str(liteAccess.set(pargs.par[0],vals)))
        
    else:
        print(suffix+str(liteAccess.get(pargs.par)))
    print('Execution time: %.4f'%(timer() - ts))

