#!/usr/bin/env python3
"""Process Variables Server of the Gaussmeter VGM from AlphaLab Inc.
The Device Communication Protocol is described in 
https://www.alphalabinc.com/wp-content/uploads/2018/02/alphaapp_comm_protocol.pdf
"""
#__version__ = 'v01 2018-12-27'# created
#__version__ = 'v02 2018-05-07'# better error handling
#__version__ = 'v03 2018-05-08'# longer (0.5s) time.sleep on opening, it helps
#__version__ = 'v04 2011-11-07'# support new liteServer 
#__version__ = 'v05 2011-11-09'# parent abandoned, global serialDev
#__version__ = 'v06 2011-11-10'# parent is back, it is simplest way to provide PVD with the proper serial device
#__version__ = 'v07 2011-11-22'# IMPORTANT: _serialDev replaces serialDev, non-underscored members are treated as parameters
__version__ = 'v08 2011-11-26'# 

import sys, serial, time
#Python3 = sys.version_info.major == 3
import liteServer

PV = liteServer.PV
Device = liteServer.Device
EventExit = liteServer.EventExit

#`````````````````````````````Helper methods```````````````````````````````````
def printe(msg):
    print('ERROR '+msg)
def printw(msg):
    print('WARNING '+msg)
#def printd(msg): pass#print('DBG: '+msg)
def printd(msg):
    if liteServer.Server.Dbg: print('dbgVGM:'+str(msg))
    
def decode_data_point(dp):
    """Decode 6 bytes of a data point"""
    r = {}
    if dp[0] &  0x40:
        return r
    r['F'] = (dp[0] >> 4) & 0x3
    r['H'] = (dp[0] >> 2) & 0x3
    negative = dp[1] & 0x08
    r['D'] = dp[1] & 0x07
    scale = 1./(10**(r['D']))
    n = dp[2]<<24 | dp[3]<<16 | dp[4]<<8 | dp[5]
    r['N'] = -n if negative else n
    r['N'] *= scale
    return round(r['N'],4)

def vgm_command(cmd,serDev):
    """execute command on a gaussmeter with serial interface ser"""
    printd('>vgm_command: '+str(cmd))
    serDev.write(cmd)
    dps = serDev.read(100)
    ldps = len(dps)
    printd('read %d'%ldps+' bytes')

    if ldps == 0:
        print('No data')
        return []
        
    if dps[-1] != 8:
        print('ERR: Last byte of %d'%ldps+' is '+str(dps[-1])+' expect 08')
        return []

    r = []
    for ip in range(int(ldps/6)):
        r.append(decode_data_point(dps[ip*6:(ip+1)*6]))
    return r

#````````````````````````````Process Variables````````````````````````````````
class PVD(PV):
    # override data updater
    def update_value(self):
        r = vgm_command(b'\x03'*6,self._parent._serialDev)
        printd('getv:'+str(r))
        self.value = r
        
class Gaussmeter(Device):
    #``````````````Attributes, same for all class instances```````````````````    Dbg = False
    Dbg = False
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #``````````````Instantiation``````````````````````````````````````````````
    def __init__(self,name,comPort='COM1'):
    
        #device specific initialization
        def open_serial():
            return serial.Serial(comPort, 115200, timeout = pargs.timeout)
        self._serialDev = None
        for attempt in range(2):
            try:
                self._serialDev = open_serial()
                break
            except Exception as e:
                printw('attempt %i'%attempt+' to open '+comPort+':'+str(e))
            time.sleep(0.5*(attempt+1))
        if self._serialDev is None:
            #printe('could not open '+comPort)
            raise IOError('could not open '+comPort)
        else:
            print('Succesfully open '+name+' at '+comPort)

        # create parameters
        pars = {'DP': PVD('R','Data Points',[0.]*5,parent=self)}
        super().__init__(name,pars)
        
        # test
        #pars['DP'].update_values()
    #``````````````Overridables```````````````````````````````````````````````
    def start(self):        
        print('Gaussmeter %s started.'%self._name)
        r = vgm_command(b'\x04'*6,self._serialDev)
        print('response:'+repr(r))
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# parse arguments
import argparse
parser = argparse.ArgumentParser(description=\
  'Process Variable liteServer for Gaussmeters from AlphaLab Inc')
parser.add_argument('-d','--dbg', action='store_true', help='debugging')
#parser.add_argument('-H','--host',help='host IP address',default='localhost')
#parser.add_argument('-p','--port',type=int,help='IP port',default=9700)
parser.add_argument('-t','--timeout',type=float,default=.5\
,help='serial port timeout')
parser.add_argument('comPorts',nargs='*',default=['/dev/ttyUSB0'])#['COM1'])
pargs = parser.parse_args()

liteServer.Server.Dbg = pargs.dbg
#devices = [Gaussmeter('Gaussmeter%d'%i,comPort=p) for i,p in enumerate(pargs.comPorts)]
devices = []
for i,p in enumerate(pargs.comPorts):
    try:    devices.append(Gaussmeter('Gaussmeter%d'%i,comPort=p))
    except Exception as e:  printw('opening serial: '+str(e))

server = liteServer.Server(devices)#,host=pargs.host, port=pargs.port)

try:
    server.loop()
except KeyboardInterrupt:
    print('Stopped by KeyboardInterrupt')
