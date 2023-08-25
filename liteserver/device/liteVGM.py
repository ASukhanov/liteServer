#!/usr/bin/env python3
"""Lite Data Object server for Gaussmeters VGM and GM-2 from AlphaLab Inc.
The Device Communication Protocol is described in 
https://www.alphalabinc.com/wp-content/uploads/2018/02/alphaapp_comm_protocol.pdf
"""
__version__ = 'v3.1.0 2023-03-23'# from .. import liteserver
#TODO, issue: the vgm_command lasts timeout time, it should finish after transfer

import sys, time, threading

from serial import Serial
from serial.tools.list_ports import comports

from .. import liteserver

LDO = liteserver.LDO
Server = liteserver.Server
Device = liteserver.Device
ServerDev = liteserver.ServerDev
device_Lock = threading.Lock()
MaxNWords = 5# The VGM generates 5 words, GM2 - 2 words.
VGMCMD_RESET_TIMESTAMP = b'\x04'*6
VGMCMD_STREAM_DATA = b'\x03'*6
PAUSE_AFTER_WRITE = 0.05# with 0.02 there are some communication errors
#`````````````````````````````Helper methods```````````````````````````````````
def printTime(): return time.strftime("%m%d:%H%M%S")
def printe(msg):
    print(f'ERROR_VGM@{printTime()}: {msg}')
def printw(msg):
    print(f'WARNING_VGM@{printTime()}: {msg}')
#def printd(msg): pass#print('DBG: '+msg)
def printi(msg): 
    print(f'INFO_VGM@{printTime()}: '+msg)
def printd(msg):
    if Server.Dbg >=1 : print(f'dbgVGM_VGM@{printTime()}: {msg}')
def printdd(msg):
    if Server.Dbg >=2 : print(f'ddbgVGM_VGM@{printTime()}: {msg}')
    
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

def vgm_command(cmd, serDev):
    """execute command on a gaussmeter with serial interface ser"""
    with device_Lock:
        printdd('>vgm_command for %s :'%serDev.name+str(cmd))
        try:
            serDev.write(cmd)
            time.sleep(PAUSE_AFTER_WRITE)
            dps = serDev.read(100)
        except Exception as e:
            msg = f'ERROR: Communication with {serDev.name}: {e}'
            printe(msg)
            sys.exit(1)

        ldps = len(dps)
        printdd(f'Read {ldps} bytes: {dps}')
    
        if ldps == 0:
            msg = f'WARNING: No data from '+serDev.name
            return msg
            
        if dps[-1] != 8:
            msg ='ERROR: Last byte of %d'%ldps+' is '+str(dps[-1])+' expect 08'
            return msg
    
        r = []
        for ip in range(int(ldps/6)):
            r.append(decode_data_point(dps[ip*6:(ip+1)*6]))
        return r

def open_VGM(port):
    try:
        serdev = Serial(port, 115200, timeout = 0.1)
    except Exception as e:
        printw(f'attempt to open {port}: {e}')
        pass
    vgm_command(VGMCMD_RESET_TIMESTAMP, serdev)
    return serdev

def list_VGM_serials(ports=[]):
    """List available serial devices for Gaussmeters"""
    serdevs = []
    sysFS = comports()
    for port, desc, hwid in sorted(sysFS):
        if len(ports) > 0 and port not in ports:
            continue
        printd(f'port:{port}, desc:{desc}, hwid:{hwid}')
        try:    u,vid,sn,loc = hwid.split()
        except:    continue
        sn = sn.split('=')[1]
        if vid != 'VID:PID=0403:6001':
            printd(f'not supported USB chipset: {vid}')
            continue
        serdev = open_VGM(port)
        serdev.SN = sn
        serdevs.append(serdev)
    #print(f'serdevs: {serdevs}')
    return serdevs
"""
#````````````````````````````Lite Data Objects````````````````````````````````
class LDOmy(LDO):
    # Override data updater, to deliver immediate data.
    def __init__(self, f, d, v, gaussmeter):
        super().__init__(f, d, v)
        self._serialDev = gaussmeter._serialDev
        self._gaussmeter = gaussmeter

    def update_value(self):
        r = vgm_command(VGMCMD_STREAM_DATA, self._serialDev)
        printd('getv:'+str(r))
        if isinstance(r,str):
            self._gaussmeter.set_status(r)
            return
        self.value = r
        self.timestamp = time.time()
        printd(f'v,t = {r,self.timestamp}')
"""
class Gaussmeter(Device):
    #``````````````Attributes, same for all class instances```````````````````    Dbg = False
    Dbg = False
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #``````````````Instantiation``````````````````````````````````````````````
    def __init__(self, name, serialDev):
    
        #device specific initialization
        self._serialDev = None
        self._timestamp = time.time()
        self._serialDev = serialDev

        # create parameters
        pars = {
        'FTDI_SN':    LDO('','Serial number of USB chip', [serialDev.SN]),
        #'frequency':  LDO('RWE', 'Update frequency ', 1.\
        #    ,units='Hz', opLimits=(0.01,101.)),
        'cycle':LDO('R','Cycle number', [0]),
        'X':    LDO('R', 'X-component of the field', [0.], units='G'),
        'Y':    LDO('R', 'Y-component of the field', [0.], units='G'),
        'Z':    LDO('R', 'Z-component of the field', [0.], units='G'),
        'Magn': LDO('R', 'Magnitude = sqrt(X**2 + Y**2 + Z***2', [0.],
          units='G'),
        'Time': LDO('R', 'Device time', [0.], units='s'),
        'errors':   LDO('RI', 'Errors detected', [0]),
        'warnings': LDO('RI', 'Warnings detected', [0]),
        #'DP':   LDOmy('RI', 'Data Points', [0.]*MaxNWords, self),
        }
        super().__init__(name, pars)
        self.reset_VGM_timestamp()
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #``````````````Device-specific methods````````````````````````````````````
    def set_status(self, msg):
        parts = msg.split(':',1)
        ts = time.time()
        if len(parts) == 2:
            spar = {'ERR':self.errors, 'WAR':self.warnings}.get(parts[0][:3])
            if spar:
                spar.value[0] += 1
                spar.timestamp = ts
                msg = f'{parts[0]}{spar.value}:{parts[1]}'
        self.status.value = msg
        self.status.timestamp = ts
        self.publish()
        
    def reset_VGM_timestamp(self):
        printd('Reset timestamp on '+self.name)
        self.cycle.value[0] = 0
        r = vgm_command(VGMCMD_RESET_TIMESTAMP, self._serialDev)
        if isinstance(r,str):
            self.set_status(r)

    def reset(self):
        """Called when Reset is clicked on server"""
        self.run.value[0] = 'Stopped'
        time.sleep(.1)
        self.reset_VGM_timestamp()
        time.sleep(.1)
        self.run.value[0] = 'Running'
        printi(f'set_status(Reset) for {self.name}')
        self.set_status('Reset')
        ts = time.time()
        self.errors.value[0] = 0
        self.errors.timestamp = ts
        self.warnings.value[0] = 0
        self.warnings.timestamp = ts

    def poll(self):
        """Called periodically from server."""
        serverRun = Device.server.run.value[0][:4]
        myRun = self.run.value[0]
        if self.run.value[0][:4] != serverRun:
            printi(f'State of {self.name} changed to {serverRun}')
            if serverRun == 'Stop':
                self.run.value[0] = 'Stopped'
            else:
                self.run.value[0] = 'Running'
            self.run.timestamp = time.time()
            self.publish()
        if self.run.value[0][:4] == 'Stop':
            return

        timestamp = Server.Timestamp
        printdd(f'Dev {self.name} polled at {time.time()}, serverTS:{timestamp}')
        r = vgm_command(VGMCMD_STREAM_DATA, self._serialDev)
        if isinstance(r,str):
            printd(r)
            self.set_status(r)
            return
        printd(f'sm.{self.name}.v,t = {r,timestamp}')
        if len(r) < 2:
            r = [0.]*MaxNWords
        self.Time.value[0] = r[0]
        #print(f'Time {self.name}: {self.Time.value[0]}')
        self.Magn.value[0] = r[-1]
        self.Magn.timestamp = timestamp
        #print(f'Magn({self.name})={self.Magn.value}')
        try:
            self.X.value[0] = r[-4]
            self.X.timestamp = timestamp
            self.Y.value[0] = r[-3]
            self.Y.timestamp = timestamp
            self.Z.value[0] = r[-2]
            self.Z.timestamp = timestamp
        except:
            pass
        self.cycle.value[0] += 1
        self.cycle.timestamp = timestamp
        shippedBytes = self.publish()
        #print(f'Magn({self.name})={self.Magn.value}, shipped:{shippedBytes}')

class SysMon(Device):
    """RPi system monitor for CPU temperature an other things"""
    Dbg = False
    def __init__(self, name):
        self._tFile = open('/sys/class/thermal/thermal_zone0/temp')
        self.lastTime = 0.
        # create parameters
        pars = {
        'cpuTemp':LDO('R','CPU temperature, ', [0.], units="'C"),
        }
        super().__init__(name, pars)

    def poll(self):
        """Called periodically from server."""
        timestamp = Server.Timestamp
        if timestamp - self.lastTime < 10.:
            return
        self.lastTime = timestamp
        self._tFile.seek(0)
        r = self._tFile.read()
        self.cpuTemp.value[0] = float(r)/1000.
        printd(f'sysMon:cpuTemp = {self.cpuTemp.value[0]}')
        self.cpuTemp.timestamp = timestamp
        shippedBytes = self.publish()
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# parse arguments
import argparse
parser = argparse.ArgumentParser(description = __doc__
,formatter_class=argparse.ArgumentDefaultsHelpFormatter
,epilog=f'liteVGM: {__version__}, liteserver: {liteserver.__version__}')
parser.add_argument('-p','--port',type=int, help='IP port', default=9700)
defaultIP = liteserver.ip_address('')
parser.add_argument('-i','--interface', default = defaultIP, help=\
'Network interface.')
parser.add_argument('-f','--frequency', type=float, default = 1., help=\
'Readout frequency of Gaussmeters, (Hz)')
parser.add_argument('-t','--timeout',type=float,default=0.1\
,help='serial port timeout')# 0.05 is quite reliable
parser.add_argument('-v', '--verbose', nargs='*', help=\
'Show more log messages, (-vv: show even more)')
parser.add_argument('comPorts', nargs='*', default=[], help=\
'RS232 ports, if not specified, then all connected gaussmeters will be served')
pargs = parser.parse_args()

if pargs.verbose is not None:
    Server.Dbg = 1 if len(pargs.verbose) == 0\
    else len(pargs.verbose[0]) + 1

ServerDev.PollingInterval = 1./pargs.frequency

serdevs = list_VGM_serials(pargs.comPorts)
if len(serdevs) == 0:
    printe(f'No Gaussmeters {pargs.comPorts} found.')
    sys.exit(1)

devices = [SysMon('sysMon')]

printi('Gaussmeters found:')
for i,d in enumerate(serdevs):
    print(f'Gaussmeter{i} port:{d.name}, FTDI_SN:{d.SN}')
    try:
        devices.append(Gaussmeter('Gaussmeter%d'%i, d))
    except Exception as e:
        printe('opening serial: '+str(e))
        sys.exit(1)

if len(devices) == 0:
    printe('No devices to serve')
    sys.exit(1)

server = Server(devices, interface=pargs.interface,
    port=pargs.port)

try:
    server.loop()
except KeyboardInterrupt:
    print('Stopped by KeyboardInterrupt')
