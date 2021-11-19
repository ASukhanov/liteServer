#!/usr/bin/env python3
"""Lite Data Object server for Geiger Counter GMC-500 from GQ Electronics.
The Device Communication Protocol is described in
https://www.gqelectronicsllc.com/download/GQ-RFC1201.txt
"""
__version__ = 'v1.0.4 2021-11-12'# 

import sys, serial, time, threading
try: # to import development version of the liteserver
    from liteserv import liteserver
except:
    from liteserver import liteserver

LDO = liteserver.LDO
Server = liteserver.Server
Device = liteserver.Device
ServerDev = liteserver.ServerDev
device_Lock = threading.Lock()

#`````````````````````````````Helper methods```````````````````````````````````
def printTime(): return time.strftime("%m%d:%H%M%S")
def printe(msg):
    print(f'ERROR_GQ@{printTime()}: {msg}')
def printw(msg):
    print(f'WARNING_GQ@{printTime()}: {msg}')
def printi(msg): 
    print(f'INFO_GQ@{printTime()}: '+msg)
def printd(msg):
    if Server.Dbg: print(f'dbgGQ@{printTime()}: {msg}')

def serial_command(cmd, expectBytes=100):
    """Send serial command to device and return reply."""
    serDev = GeigerCounterGQ.SerialDev
    with device_Lock:
        printd('>serial_command for %s :'%serDev.name+str(cmd))
        serDev.write(cmd)
        time.sleep(.1)
        r = serDev.read(expectBytes)
        lr = len(r)
        printd(f'Read {lr} bytes: {r}')
    
        if lr == 0 and expectBytes > 0:
            msg = f'WARNING: No data from '+serDev.name
            return msg
        return r

class GeigerCounterGQ(Device):
    #``````````````Attributes, same for all class instances```````````````````    Dbg = False
    Dbg = False
    SerialDev = None
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #``````````````Instantiation``````````````````````````````````````````````
    def __init__(self, name, comPort='COM1'):
    
        #device specific initialization
        def open_serial():
            return serial.Serial(comPort, 115200, timeout = pargs.timeout)
        for attempt in range(2):
            try:
                GeigerCounterGQ.SerialDev = open_serial()
                break
            except Exception as e:
                printw('attempt %i'%attempt+' to open '+comPort+':'+str(e))
            time.sleep(0.5*(attempt+1))
        if GeigerCounterGQ.SerialDev is None:
            raise IOError('could not open '+comPort)
        else:
            print('Succesfully open '+name+' at '+comPort)
        # get hardware model and version
        r = serial_command(b'<GETVER>>')
        print(f'<GETVER>> {r}')
        try:
            if r[:7] != b'GMC-500':
                raise
        except:
            printe(f'Wrong GETVER: {r}')
            sys.exit(1)
        serial_command(b'<POWERON>>', 0)

        # create parameters
        pars = {
        'frequency':  LDO('RWE', 'Device readout frequency', pargs.frequency\
            ,units='Hz', opLimits=(0.01,101.)),
        'cycle':LDO('R','Cycle number', [0]),
        'CPM':     LDO('R','Counts per minute', [0]),
        'Gyro':    LDO('R','Gyroscopic data, X, Y, Z', [0, 0, 0]),
        'errors':   LDO('RI', 'Errors detected', [0]),
        'warnings': LDO('RI', 'Warnings detected', [0]),
        }
        super().__init__(name, pars)

    def poll(self):
        """Called periodically from server."""
        #print(f'server run :{Device.server.run.value}')
        prevRunStatus = self.run.value[0]
        if Device.server.run.value[0][:4] =='Stop':
            self.run.value[0] = 'Stopped'
        else:
            self.run.value[0] = 'Running'

        #TODO the following does not update the parameter
        if self.run.value[0] != prevRunStatus:
            printi(f'run {self.name} changed to {self.run.value}')
            self.run.timestamp = time.time()
            self.publish()

        if self.run.value[0][:4] == 'Stop':
            #print(f'dev {self.name} Stopped')
            return
        timestamp = Server.Timestamp
        #printi(f'Dev {self.name} polled at {time.time()}, serverTS:{timestamp}')

        r = serial_command(b'<GETCPM>>')
        if len(r) != 4:
            self.set_status(f'ERROR: GETCPM={r}')
            self.errors.value[0] += 1
            return
        self.CPM.value[0] = int.from_bytes(r,'big')
        self.CPM.timestamp = timestamp
        printd(f'CPM: {self.CPM.value[0],timestamp}')

        r = serial_command(b'<GETGYRO>>')
        if len(r) != 7:
            self.set_status(f'WARNING: GETGYRO={r}')
            self.warnings.value[0] += 1
            return
        self.Gyro.value = [int.from_bytes(r[0:2],'big'),
          int.from_bytes(r[2:4],'big'),
          int.from_bytes(r[4:6],'big')]
        self.Gyro.timestamp = timestamp
        printd(f'Gyro: = {self.Gyro.value}')

        self.cycle.value[0] += 1
        self.cycle.timestamp = timestamp
        # publish is actually needed only for last device
        shippedBytes = self.publish()
        #print(f'Magn({self.name})={self.Magn.value}, shipped:{shippedBytes}')

    def reset(self):
        """Called when Reset is clicked on server"""
        self.run.value[0] = 'Stopped'
        self.errors.value[0] = 0
        self.errors.timestamp = time.time()
        self.warnings.value[0] = 0
        self.warnings.timestamp = time.time()
        time.sleep(.1)
        # Read hardware model and version, wait for long response to purge buffer
        r = serial_command(b'<GETVER>>')
        #print(f'<GETVER>>L {r}')
        if r[:4] != b'GMC-':
            msg = f'WARNING: Reset unsuccessful: {r}, try once more'
        else:
            msg = 'OK'
        self.set_status(msg)
        time.sleep(.1)
        self.run.value[0] = 'Running'
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #``````````````Device-specific methods````````````````````````````````````
    def set_status(self, msg):
        tt = time.time()
        try:
            parts = msg.split(':',1)
            if len(parts) == 2:
                spar = {'ERR':self.errors, 'WAR':self.warnings}.get(parts[0][:3])
                if spar:
                    spar.value[0] += 1
                    spar.timestamp = tt
                    parts[0] += f'{spar.value}: '
                msg = parts[0]+parts[1]
            printw(msg)
        except Exception as e:
            printw(f'exception in set_status "{msg}": {e}')
        self.status.value = msg
        self.status.timestamp = tt
        self.publish()
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
if __name__ == "__main__":
    # parse arguments
    import argparse
    parser = argparse.ArgumentParser(description = __doc__
    ,formatter_class=argparse.ArgumentDefaultsHelpFormatter
    ,epilog=f'liteGQ: {__version__}, liteserver: {liteserver.__version__}')
    parser.add_argument('-f','--frequency', type=float, default = 0.1, help=\
      'Device readout frequency, (Hz)')
    parser.add_argument('-p','--port',type=int, help='IP port', default=9701)
    defaultIP = liteserver.ip_address('')
    parser.add_argument('-i','--interface', default = defaultIP, help=\
    'Network interface.')
    parser.add_argument('-t','--timeout',type=float,default=0.2\
    ,help='serial port timeout')# 0.1 is too fast for reading from VGM 
    parser.add_argument('-v','--verbose', action='store_true', help=\
        'Show more log messages')
    parser.add_argument('comPorts', nargs='*', default=['/dev/ttyUSB0'],
      help='Serial port')
    pargs = parser.parse_args()
    ServerDev.PollingInterval = 1./pargs.frequency
    print(f'comports: {pargs.comPorts}')

    Server.Dbg = pargs.verbose
    devices = []
    for i,p in enumerate(pargs.comPorts):
        if True:#try:
            devices.append(GeigerCounterGQ('dev%d'%(i+1), comPort=p))
        else:#except Exception as e:
            printe('opening serial: '+str(e))
            sys.exit(1)

    if len(devices) == 0:
        printe('No devices to serve')
        sys.exit(1)
    print('Serving:'+str([dev.name for dev in devices]))
    server = Server(devices, interface=pargs.interface,
        port=pargs.port)#, serverPars = False)

    try:
        server.loop()
    except KeyboardInterrupt:
        print('Stopped by KeyboardInterrupt')
