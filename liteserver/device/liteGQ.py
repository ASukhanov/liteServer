#!/usr/bin/env python3
"""Lite Data Object server for Geiger Counter GMC-500 from GQ Electronics.
The Device Communication Protocol is described in
https://www.gqelectronicsllc.com/download/GQ-RFC1201.txt
"""
__version__ = '3.1.0 2023-08-23'# from .. import litesrver

import sys, serial, time, threading

from .. import liteserver

LDO = liteserver.LDO
Server = liteserver.Server
Device = liteserver.Device
ServerDev = liteserver.ServerDev
device_Lock = threading.Lock()
MgrInstance = None

#`````````````````````````````Helper methods```````````````````````````````````
from.helpers import find_serialDevice
from . import helpers
def printi(msg):  helpers.printi(msg)
def printe(msg):
    helpers.printe(msg)
    if MgrInstance is not None: MgrInstance.set_status('ERR: '+msg)
def printw(msg):
    helpers.printw(msg)
    if MgrInstance is not None: MgrInstance.set_status('WAR: '+msg)
def printv(msg):  helpers.printv(msg, pargs.verbose)
def printvv(msg): helpers.printv(msg, pargs.verbose, level=1)

def query(cmd):
    return helpers.serial_command(GeigerCounterGQ.SerialDev, cmd)

class GeigerCounterGQ(Device):
    #``````````````Attributes, same for all class instances```````````````````    Dbg = False
    Dbg = False
    SerialDev = None
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #``````````````Instantiation``````````````````````````````````````````````
    def __init__(self, name):
        # create parameters
        pars = {
        #'frequency':  LDO('RWE', 'Device readout frequency',
        #    pargs.frequency, units='Hz', opLimits=(0.01,101.)),
        'frequency':  LDO('R', 'Device readout frequency', 
            pargs.frequency, units='Hz'),
        'cycle':    LDO('R','Cycle number', [0]),
        'CPM':      LDO('R','Counts per minute (device-specific)', [0]),
        'mR_h':     LDO('R','milliRoentgen per hour', [0.],
            units='mR/h'),
        'Gyro':     LDO('R','Gyroscopic data, X, Y, Z', [0, 0, 0]),
        'errors':   LDO('RI', 'Errors detected', [0]),
        'warnings': LDO('RI', 'Warnings detected', [0]),
        }
        super().__init__(name, pars)
        self.PV.update(pars)
        self.start()

    def start(self):
        printi(f'>start')
        try:    GeigerCounterGQ.SerialDev.close()
        except: pass
        self.stopped = False
        dev,r = find_serialDevice('<GETVER>>,GMC-500', 115200,
            timeout=pargs.timeout, verbose=pargs.verbose)
        if dev is None:
            printe(f'Could not find GMC-500 device')
            sys.exit(1)
        printi(f'GMC-500 version: {r}')
        GeigerCounterGQ.SerialDev = dev
        #device specific initialization
        query(b'<POWERON>>')
        self.set_status('Device started')

    def stop(self):
        printi(f'>stop')
        self.stopped = True

    def poll(self):
        """Called periodically from server."""
        if self.stopped:
            return
        printv(f'>poll')
        prevRunStatus = self.PV['run'].value[0]
        if Device.server.PV['run'].value[0][:4] =='Stop':
            self.PV['run'].value[0] = 'Stopped'
        else:
            self.PV['run'].value[0] = 'Started'

        #TODO the following does not update the parameter
        if self.PV['run'].value[0] != prevRunStatus:
            printi(f"run {self.name} changed to {self.PV['run'].value}")
            self.PV['run'].timestamp = time.time()
            self.publish()

        if self.PV['run'].value[0][:4] == 'Stop':
            #print(f'dev {self.name} Stopped')
            return
        timestamp = Server.Timestamp
        #printi(f'Dev {self.name} polled at {time.time()}, serverTS:{timestamp}')

        try:
            r = query(b'<GETCPM>>')
        except Exception as e:
            printw(f'getting data: {e}')
            #self.exit()
            return
        if len(r) != 4:
            self.set_status(f'ERROR: GETCPM={r}')
            self.PV['errors'].value[0] += 1
            return
        self.PV['CPM'].value[0] = int.from_bytes(r,'big')
        self.PV['CPM'].timestamp = timestamp
        printv(f"CPM: {self.PV['CPM'].value[0],timestamp}")
        self.PV['mR_h'].value[0] = self.PV['CPM'].value[0]*0.000650# device-spicific
        self.PV['mR_h'].timestamp = timestamp

        r = query(b'<GETGYRO>>')
        if len(r) != 7:
            self.set_status(f'WARNING: GETGYRO={r}')
            self.PV['warnings'].value[0] += 1
            return
        self.PV['Gyro'].value = [int.from_bytes(r[0:2],'big'),
          int.from_bytes(r[2:4],'big'),
          int.from_bytes(r[4:6],'big')]
        self.PV['Gyro'].timestamp = timestamp
        printv(f"Gyro: = {self.PV['Gyro'].value}")

        self.PV['cycle'].value[0] += 1
        self.PV['cycle'].timestamp = timestamp
        # publish is actually needed only for last device
        shippedBytes = self.publish()
        #print(f'Magn({self.name})={self.Magn.value}, shipped:{shippedBytes}')

    def reset(self):
        """Called when Reset is clicked on server"""
        self.PV['run'].value[0] = 'Stopped'
        self.PV['errors'].value[0] = 0
        self.PV['errors'].timestamp = time.time()
        self.PV['warnings'].value[0] = 0
        self.PV['warnings'].timestamp = time.time()
        time.sleep(.1)
        # Read hardware model and version, wait for long response to purge buffer
        r = query(b'<GETVER>>')
        #print(f'<GETVER>>L {r}')
        if r[:4] != b'GMC-':
            msg = f'WARNING: Reset unsuccessful: {r}, try once more'
        else:
            msg = 'OK'
        self.set_status(msg)
        time.sleep(.1)
        self.PV['run'].value[0] = 'Started'
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #``````````````Device-specific methods````````````````````````````````````
    def set_status(self, msg):
        tt = time.time()
        try:
            parts = msg.split(':',1)
            if len(parts) == 2:
                spar = {'ERR':self.PV['errors'], 'WAR':self.PV['warnings']}.get(parts[0][:3])
                if spar:
                    spar.value[0] += 1
                    spar.timestamp = tt
                    parts[0] += f'{spar.value}: '
                msg = parts[0]+parts[1]
        except Exception as e:
            #printw(f'exception in set_status "{msg}": {e}')
            pass
        self.PV['status'].value = msg
        self.PV['status'].timestamp = tt
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
    ,help='serial port timeout')
    parser.add_argument('-v','--verbose', nargs='*', help=\
        'Show more log messages, (-vv: show even more).')
    pargs = parser.parse_args()
    ServerDev.PollingInterval = 1./pargs.frequency
    pargs.verbose = 0 if pargs.verbose is None else len(pargs.verbose)+1
    Server.Dbg = pargs.verbose
    MgrInstance = GeigerCounterGQ('dev1')
    server = Server([MgrInstance], interface=pargs.interface,
        port=pargs.port)#, serverPars = False)
    print('`'*79)
    print(f"To monitor, use: pvplot 'L:{server.host};{pargs.port}:dev1:mR_h'")
    print(','*79)
    try:
        server.loop()
    except KeyboardInterrupt:
        print('Stopped by KeyboardInterrupt')
