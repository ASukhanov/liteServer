#!/usr/bin/env python3
"""Process Variables Server of the Gaussmeters VGM and GM-2 from AlphaLab Inc.
The Device Communication Protocol is described in 
https://www.alphalabinc.com/wp-content/uploads/2018/02/alphaapp_comm_protocol.pdf
"""
__version__ = 'v14 2021-09-21'# 
print(f'version: {__version__}')
#TODO, issue: the vgm_command lasts timeout time, it should finish after transfer

import sys, serial, time
from liteserver import liteserver

LDO = liteserver.LDO
Device = liteserver.Device

#`````````````````````````````Helper methods```````````````````````````````````
def printe(msg):
    print('ERROR '+msg)
def printw(msg):
    print('WARNING '+msg)
#def printd(msg): pass#print('DBG: '+msg)
def printd(msg):
    if liteserver.Server.Dbg: print('dbgVGM:'+str(msg))
    
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
    printd('>vgm_command for %s :'%serDev.name+str(cmd))
    serDev.write(cmd)
    dps = serDev.read(100)
    ldps = len(dps)
    printd(f'Read {ldps} bytes: {dps}')

    if ldps == 0:
        print('No data from '+serDev.name)
        return []
        
    if dps[-1] != 8:
        print('ERR: Last byte of %d'%ldps+' is '+str(dps[-1])+' expect 08')
        return []

    r = []
    for ip in range(int(ldps/6)):
        r.append(decode_data_point(dps[ip*6:(ip+1)*6]))
    return r

#````````````````````````````Process Variables````````````````````````````````
class LDOmy(LDO):
    # override data updater
    def __init__(self, f, d, v, serialDev='/dev/ttyUSB0'):
        super().__init__(f, d, v)
        self._serialDev = serialDev

    def update_value(self):
        r = vgm_command(b'\x03'*6,self._serialDev)
        printd('getv:'+str(r))
        self.value = r
        self.timestamp = time.time()
        printd(f'v,t = {r,self.timestamp}')
        
class Gaussmeter(Device):
    #``````````````Attributes, same for all class instances```````````````````    Dbg = False
    Dbg = False
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #``````````````Instantiation``````````````````````````````````````````````
    def __init__(self, name, comPort='COM1'):
    
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
        pars = {
        #'DP':   LDOmy('R','Data Points',[0.]*5,parent=self),
        'DP':   LDOmy('R', 'Data Points', [0.]*5, serialDev=self._serialDev),
        'Reset':LDO('W','Start new streaming session',[False]\
                ,setter=self.reset_VGM_timestamp),
        }
        super().__init__(name,pars)
        self.reset_VGM_timestamp()

    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #``````````````Device-specific methods````````````````````````````````````
    def reset_VGM_timestamp(self):
        print('Reset timestamp on '+self.name)
        r = vgm_command(b'\x04'*6, self._serialDev)
        print('reply:'+repr(r))
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# parse arguments
import argparse
parser = argparse.ArgumentParser(description = __doc__
,formatter_class=argparse.ArgumentDefaultsHelpFormatter
,epilog=f'liteVGM: {__version__}, liteserver: {liteserver.__version__}')
parser.add_argument('-d','--dbg', action='store_true', help='debugging')
parser.add_argument('-p','--port',type=int, help='IP port', default=9700)
defaultIP = liteserver.ip_address('')
parser.add_argument('-i','--interface', default = defaultIP, help=\
'Network interface.')
parser.add_argument('-t','--timeout',type=float,default=0.2\
,help='serial port timeout')# 0.1 is too fast for reading from VGM 
parser.add_argument('comPorts',nargs='*',default=['/dev/ttyUSB0'])#['COM1'])
pargs = parser.parse_args()
print(f'comports: {pargs.comPorts}')

liteserver.Server.Dbg = pargs.dbg
#devices = [Gaussmeter('Gaussmeter%d'%i,comPort=p) for i,p in enumerate(pargs.comPorts)]
devices = []
for i,p in enumerate(pargs.comPorts):
    if True:#try:
        devices.append(Gaussmeter('Gaussmeter%d'%i, comPort=p))
    #except Exception as e:  printw('opening serial: '+str(e))

if len(devices) == 0:
    printe('No devices to serve')
    sys.exit(1)
print('Serving:'+str([dev.name for dev in devices]))
server = liteserver.Server(devices, interface=pargs.interface,
    port=pargs.port)

try:
    server.loop()
except KeyboardInterrupt:
    print('Stopped by KeyboardInterrupt')
