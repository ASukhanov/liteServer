#!/usr/bin/env python3
"""LiteServer for MCUFEC devices"""
__version__ = '3.1.0 2023-08-23'# from .. import liteserver
 
import sys, time, threading
timer = time.perf_counter
import numpy as np
import serial
import json
from functools import partial

from .. import liteserver

#get_data_lock = threading.Lock()
ExecLock = threading.Lock()
LDO = liteserver.LDO
Device = liteserver.Device
SerDev = None
SerObjectEvent = threading.Event()# informs that new SerObject was detected 
Event = threading.Event()
#````````````````````````````Helper functions`````````````````````````````````
programStartTime = time.time()
def croppedText(txt, limit=200):
    if len(txt) > limit:
        txt = txt[:limit]+'...'
    return txt
def timeInProgram():
    return round(time.time() - programStartTime,6)
def printi(msg): print(f'inf@{timeInProgram()}: '+msg)
def printw(msg): print(f'wrn@{timeInProgram()}: '+msg)
def printe(msg): print(f'ERR@{timeInProgram()}: '+msg)
def _printv(msg, level=0):
    if pargs.verbose is None:
        return
    if len(pargs.verbose) >= level:
        print(f'dbg{level}@{timeInProgram()}: '+msg)
def printv(msg):   _printv(msg, 0)
def printvv(msg):  _printv(msg, 1)

def write_serdev(msg):
    #printv(f'cmd:`{msg}`')
    msgb = msg.encode('utf-8')
    l = len(msgb)
    msgb += (lframe - l)*b'\r'
    printvv(f'msgb[{len(msgb)}]: {msgb}')
    SerDev.write(msgb)

def b2i(buf):
    return int.from_bytes(buf, 'little')

lastheader = None
feod = b'\x04\x00\x00E' #EndOfData, l=4, id='E'
lframe = 80 # length of the TTY transmission packet

# Parameters for minor smoothing of waveforms
SmoothingKernelSize = 4
SmoothingKernel = np.ones(SmoothingKernelSize)/SmoothingKernelSize

def resync():
    """Re-synchronize serial input"""
    ts = time.time()
    while 1:
        if time.time() - ts > 1:
            printw(f'Resync failed.')
            return False
        try:
            f = SerDev.read(1)
            #print(f'rs:{b}, {feod[0]}')
            if f[0] != feod[0]:    continue
            e = SerDev.read(1)
            if e[0] != feod[1]:    continue
            o = SerDev.read(1)
            if o[0] != feod[2]:    continue
            #print(f'feo match: {f,e,o}')
            d = SerDev.read(1)
            if d[0] != feod[3]:    continue
            break
        except Exception as e:
            msg = f'Exception in resync: {e}'
            printw(msg)
    printw(f'Resync OK.')
    return True

def get_data():
    """Read data from the serial interface"""
    global lastheader
    #with get_data_lock:
    Event.set()
    printvv('>get_data')
    while 1:
        header = SerDev.read(4)
        if len(header) != 4:
            printvv(f'<No data: {header}')
            #SerDev.flush()
            return None,None
        if header ==  feod:
            printv('EndOfData message')
            continue
        if lastheader is not None and header != lastheader:
            printw(f'Data shape changed: {header}')
            lastheader = header
        l = b2i(header[:2])
        if header[3] == 0:
            printe(f'<Header wrong: {header}')
            if resync():
                continue
            return None,None
        try:
            hdrID = header[3:4]
        except:
            printe(f'<In get_data: Number of bits is wrong: {header}')
            if resync():
                continue
            return None,None
        payload = SerDev.read(l-4)
        printvv(f'<get_data[{len(payload)}], header: {header}')
        return header, payload

#````````````````````````````Lite Data Objects````````````````````````````````
class MCUFEC(Device):
    """ Derived from liteserver.Device.
    Note: All class members, which are not process variables should 
    be prefixed with _"""
    def __init__(self,name, bigImage=False):
        self.initialized = False
        self._perfPrevs = 0., 0.
        self._pars = {
        # Diagnostic parameters
        #'polltime':   LDO('RWEI','Polling time',1.3\
        #                ,units='s', opLimits=(0.001,1001.)),
        'fecVersion': LDO('RI','FEC Version',['']),
        'fecClock':   LDO('RI','FEC Clock',0., units='MHz'),
        'fecTime':    LDO('RI','Current time',0., getter=self.get_time),
        'cycle':      LDO('R','Cycle number',0),
        'rps':        LDO('R','Cycles per second',[0.],units='Hz'),
        'publishingSpeed': LDO('RI', 'Instanteneous publishing speed of published data', 0., units='MB/s'),
        'dataSize':   LDO('RI', 'Size of published data', 0., units='KB'),
        'chunks':     LDO('RI', 'Number of chunks in UDP transfer, for lowest latency it should be 1', 0.),
        'udpSpeed':   LDO('RI', 'Instanteneous socket.send spped', 0., units='MB/s'),
        'send':       LDO('RWEI','Send command to device','info',
                            setter=self.set_send),
        'reply':      LDO('RI','Reply from device',['']),}

        thread = threading.Thread(target=self.seriaListener, daemon = True)
        thread.start()
        if not Event.wait(.2):
            printe('Listener did not start')
            sys.exit(1)

        #if pargs.stop:
        reply = self.execute_command('set fec stop')
        time.sleep(.5)

        #TODO check if it stopped, exit if not
        # parameters, retrieved from device
        pars = self.adopt_PVs()
        if pars is None:
            printe('Could not extract parameters from device.')
            sys.exit(1)
        self._pars.update(pars)

        # derived parameters
        self._pars.update({'adcs':   LDO('R','Multi-dimensional array of all ADC channels',
          [], ptype='numpy.ndarray')})
        print(f"nadcs: {self._pars['nADC'].value[0]}")
        for i in range(self._pars['nADC'].value[0]):
            print(f'creating ADC{i+1}')
            self._pars.update({f'adc{i+1}':LDO('R','ADC channel',
              [], ptype='numpy.ndarray')})

        self._pars.update({'xscale': LDO('R','Scale, converting samples to time',
            1., units='ms', ptype='numpy.ndarray')})
        nADCs = self._pars['nADC'].value[0]
        self._pars.update({'peak2peak': LDO('R','Peak-to-Peak amplitudes of ADC channels',
          [0.]*nADCs, units='V')}),
        self._pars.update({'mean': LDO('R','Average of all samples of ADC channels',
          [0.]*nADCs, units='V')}),
        self._pars.update({'gain': LDO('R','Conversion of ADC counts to Volts, if 0 then it will be returned in ADC counts',
          [1., 1., 2./2450, 2./2450, 2./690, 2./700], units='V')})
        self._pars.update({'offset': LDO('R','ADC offset',
          [0, 0, 168, 168, 1792, 1785])})
        super().__init__(name, self._pars)

        self.update_xscale()
        self.initialized = True
        printi('Initialization finished')
        time.sleep(.1)

    #``````````````Overridables````````````````````````````````````````````````        
    def start(self):
        printi('>start')
    def stop(self):
        printi('>stop')
    def poll(self):
        #printvv(f'poll @{timeInProgram()}')
        return
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,

    def get_time(self):
        self.PV['fecTime'].value = time.time()

    def set_send(self):
        printv(f"send: {self.PV['send'].value[0]}")
        cmd = self.PV['send'].value[0]
        self.PV['send'].value[0] = ''
        self.execute_command(cmd)
        #printv(f'reply: {reply}')
        #self.PV['reply'].value[0] = reply

    def handle_devPacket(self, header, payload):
        timestamp = time.time()
        printvv(croppedText(f'hdr:{header}, payload: {payload}'))
        hdrNB = (header[2]&0x3) + 1
        hdrNCh = ((header[2]>>2)&0xf) + 1
        l = b2i(header[:2])
        printvv(f'hdr:{header}, l:{l}, NB:{hdrNB}, NChannels: {hdrNCh}')
        hdrID = header[3:4]
        if hdrID == b'A':# binary ADC data
            #if self.PV['run'].value[0] != 'Running':
            #    printv(f'ADC data{len(payload)} skipped')
            #    return
            dtype = {1:np.uint8, 2:np.uint16, 4:np.uint32}.get(hdrNB)
            if dtype is None:
                printe(f'3-byte word is not supported: {header}')
                resync()
                return
            #print(f'dt: {dtype}')
            samplesPerChannel = l//hdrNB//hdrNCh
            try:
                arr = np.frombuffer(payload,dtype\
                  = dtype).reshape(samplesPerChannel,hdrNCh).T
            except:
                printe(f'data[{len(payload)}] shape is wrong, channels: {hdrNCh}, width: {samplesPerChannel}')
                resync()
                return
            if not self.initialized:
                printv('ADC data ignored since parameters are not created yet')
                return
            printv(f'ADC array[{arr.shape}] accepted')
            pv_ADCs = self.PV['adcs']
            # update multidimensional parameter adcs
            pv_ADCs.set_valueAndTimestamp(arr, timestamp)

            # update waveforms, peak2peaks and means of individual ADC channels
            peak2peak = []
            mean = []
            for i,a in enumerate(arr):
                printvv(f'setting adc{i+1} to {a}')
                try:
                    self._pars['adc'+str(i+1)].set_valueAndTimestamp(a, timestamp)
                except KeyError:
                    #printw(f'ADC {i+1} not required')
                    continue
                gain = self.PV['gain'].value[i]
                offset = self.PV['offset'].value[i]
                b = np.convolve(a, SmoothingKernel, 'valid')
                peak2peak.append(round((b.max() - b.min())*gain,5))
                mean.append(round((a.mean()-offset)*gain,5))
            self._pars['peak2peak'].set_valueAndTimestamp(peak2peak, timestamp)
            self._pars['mean'].set_valueAndTimestamp(mean, timestamp)

        elif hdrID == b'<':# JSON formatted reply
            #printv('updating pv_reply')
            self._pars['reply'].set_valueAndTimestamp([payload.decode()],
              timestamp)
            if not payload.startswith(b'{'):
                printi(f'msg: {payload}')
                if payload.startswith(b'ERR'):
                    self._pv_reply = payload.decode()
                    SerObjectEvent.set()
                return
            try:
                self._pv_reply = json.loads(payload)
            except Exception as e:
                printe(f'Error {e} in JSON decoding of:\n{payload}')
                return
            printvv(f'Object received: {self._pv_reply}')

            #TODO: interpret the object
            if self.initialized:
                self.interpret_reply(self._pv_reply)

            SerObjectEvent.set()
        else:
            printe(f'ID {header[3]} not supported, header: {header}')
            if resync():
                return

    def seriaListener(self):
        printi('``````````Listener Started``````````````````````````````')
        #time.sleep(.2)# give time for server to startup

        prevCycle = 0
        self._timestamp = time.time()
        periodic_update = time.time()
        maxChunks = 0
        pv_cycle = self._pars['cycle']
        pv_chunks = self._pars['chunks']
        while not Device.EventExit.is_set():
            #TODO: with liteserver-v76 we have to use value[0]
            try:
                if self.run.value[0][:4] == 'Stop':
                    break
            except: pass

            dt = self._timestamp - periodic_update
            if dt > 10.:
                ts = time.time()# something funny with the binding, cannot use self._timestamp directly
                #pv_cycle.timestamp = ts
                periodic_update = ts
                #printv(f'cycle of {self.name}:{pv_cycle.value}')
                #printv(f'periodic update: {ts,self._timestamp}')
                if maxChunks > 1:
                    msg = 'WARNING: published data are chopped, latency will increase'
                    maxChunks = 0
                else:
                    msg = f'periodic update {self.name} @{round(self._timestamp,3)}'
                #Device.setServerStatusText('Cycle %i on '%pv_cycle.value[0]+self.name)
                self.PV['rps'].set_valueAndTimestamp\
                  ((pv_cycle.value[0] - prevCycle)/dt, ts)
                prevCycle = pv_cycle.value[0]

            #waitTime = self._pars['polltime'].value[0] - (time.time() - self._timestamp)
            #Device.EventExit.wait(waitTime)
            self._timestamp = time.time()

            # Wait/Receive data from device and handle binary stream of ADC data
            try:
                hdrID,payload = get_data()
                if hdrID is None:
                    continue
            except KeyboardInterrupt:
                print(' Interrupted')
                SerDev.close()
                sys.exit(1)
            except serial.SerialException as e:
                printe(f'ERR: serialException: {e}')
                SerDev.close()
                sys.exit(1)

            self.handle_devPacket(hdrID, payload)

            if not self.initialized:
                printvv('Initialization not finished')
                # __init__() did not finish, no sense to proceed further
                continue

            #print('publish all modified parameters of '+self.name)
            pv_cycle.value[0] += 1
            try:
                dt = server.Perf['Seconds'] - self._perfPrevs[1]
                if dt == 0.:
                    mbps = 0.
                else:
                    mbps = round((server.Perf['MBytes'] - self._perfPrevs[0])/dt, 3)
                self._perfPrevs = server.Perf['MBytes'],server.Perf['Seconds']
            except Exception as e:
                printw(f'Server has not been initialized yet: {e}')
                mbps = 0.
            self.PV['udpSpeed'].set_valueAndTimestamp(mbps, self._timestamp)

            # invalidate timestamps for changing variables, otherwise the
            # publish() will ignore them
            pv_cycle.timestamp = self._timestamp
            for i in [
                self.PV['publishingSpeed'], self.PV['dataSize'],
                pv_chunks, self.PV['fecTime']]:
                i.timestamp = self._timestamp

            ts = timer()
            shippedBytes = self.publish()

            if shippedBytes:
                ss = round(shippedBytes / (timer() - ts) / 1.e6, 3)
                #print(f'sb: {shippedBytes}')            
                self.PV['publishingSpeed'].value = ss,
                #printd(f'publishing speed of {self.name}: {ss}')
                self.PV['dataSize'].value = round(shippedBytes/1000.,1)
                pv_chunks.value = (shippedBytes-1)//liteserver.ChunkSize + 1
                maxChunks = max(maxChunks, pv_chunks.value)
        print('########## listener exit ##########')

    def execute_command(self, command:str):
      """Send command to FEC, filter out binary data"""
      if ExecLock.locked():
          # This only may happen during set{} for a subscrived pv.
          # The publish() is calling the getter.
          # ther right way is to bail out.
          printv(f'########## execute_command({command}) locked! ##########')
          return
      with ExecLock:
        printvv(f'>exec_cmd({command})')
        ntries = 6
        for ntry in range(ntries):
            SerObjectEvent.clear()
            write_serdev(command)
            ok = SerObjectEvent.wait(1)
            if not ok:
                printw(f'Timeout during `{command}`. Trying {ntries-ntry-1} more times')
                continue
            reply = self._pv_reply
            if isinstance(reply,dict):
                printvv(f'<exec_cmd({command}) successfull:\n{reply}')
                return reply
            if reply.startswith('ERR'):
                printw(f'`{reply}` During `{command}`. Trying {ntries-ntry-1} more times')
                continue
        printe(f'Command `{command}` failed')
        return

    def adopt_PVs(self):
        """Adopt PVs from MCUFEC"""
        reply = self.execute_command('info')
        if reply is None:
            return
        #printi(f"pv reply: {reply}")
        pvs = self._pv_reply['PVs']
        printi(f'Device PVs: {pvs}')
        pars = {}
        for pv in pvs:
            time.sleep(0.1)
            cmd = f'info {pv}'
            reply = self.execute_command(cmd)
            if reply is None:
                sys.exit(1)
            pvinfo = reply[pv]
            printv(f'info of {pv}: {pvinfo}')

            if pv == 'fecversion':
                self._pars['fecVersion'].value = [pvinfo['value']['soft']]
                self._pars['fecClock'].value = [round(float(pvinfo['value']['clock'])/1e6,3)]
                continue
            else:
                v = pvinfo['value']
            if isinstance(v,str):
                v = [v]
            printv(f'value of {pv} = {v}')

            # decode fbits
            fbits = pvinfo['fbits']
            features = ''
            for letter in 'WRDACIsrE':
                if fbits&1:
                    features += letter
                fbits = fbits >> 1

            ptype = pvinfo['type']
            if isinstance(ptype,int):
                ptype = ['int8','uint8','uint16','int16','int32','uint32','str'][ptype]

            units = pvinfo.get('units')

            opLimits = pvinfo.get('opLow'), pvinfo.get('opHigh')
                
            legalValues = pvinfo.get('legalValues')
            if legalValues:
                legalValues = legalValues .split(',')
                #if isinstance(v,float):
                #    legalValues = [float(i) for i in legalValues]
                #elif isinstance(v,int):
                #    legalValues = [int(i) for i in legalValues]
            
            printi(f'creating {pv}={v}, {features}, units:{units}, opLimits:{opLimits}, lv:{legalValues}')
            pars.update({pv:LDO(features, pvinfo['desc'], v, units,
              opLimits, legalValues, ptype=ptype,
              setter=partial(self.set_pv, pv),
              getter=partial(self.get_pv, pv))})
        return pars

    def update_xscale(self):
        self.PV['xscale'].set_valueAndTimestamp(\
          [1000./self.PV['adc_srate'].value[0]], time.time())
        #printi(f'xcale: {pv_xscale.value[0]}')

    def interpret_reply(self, reply):
        if reply is None:
            return
        printv(f'interpret: {reply}')
        for pvname, value in reply.items():
            pv = self._pars[pvname]
            ts = time.time()
            try:
                pv.value[0] = reply[pvname]
                pv.timestamp = ts
            except Exception as e:
                printe(f'Unexpected reply: {e}')
            if pvname == 'adc_srate':
                self.update_xscale()

    def set_pv(self, pvname):
        pv = self.PV[pvname]
        cmd = f'set {pvname} {pv.value[0]}'
        printi(f'>set {cmd}')
        self.execute_command(cmd)

    def get_pv(self, pvname):
        cmd = f'get {pvname}'
        printi(f'>get {cmd}')#, prev: {pv.value}')
        self.execute_command(cmd)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#``````````````````Main function``````````````````````````````````````````````
if __name__ == "__main__":
    # parse arguments
    import argparse
    parser = argparse.ArgumentParser(description=__doc__
        ,formatter_class=argparse.ArgumentDefaultsHelpFormatter
        ,epilog=f'LiteMCUFEC version {__version__}, liteserver {liteserver.__version__}')
    parser.add_argument('-b', '--baudrate', type=int, default=7372800,# 10000000,
      help='Baud rate for serial communications')
    parser.add_argument('-d', '--debug',  action='store_true',
      help='Debug session using pdb')
    defaultIP = liteserver.ip_address('')
    parser.add_argument('-i','--interface', default = defaultIP, help=\
    'Network interface. Default is the interface, which connected to internet.')
    n = 1100# to fit LiteMCUFEC volume into one chunk
    parser.add_argument('-p','--port', type=int, default=9700, help=\
    'Serving IP port.')
    parser.add_argument('-s','--stop', action='store_true', help=\
    'Stop device')
    parser.add_argument('-v','--verbose', nargs='*', help='Show more log messages.')
    parser.add_argument('tty', nargs='?', default='/dev/ttyACM0', help=\
      'Device for serial communication')
    pargs = parser.parse_args()
    printi(f"Receive data from {pargs.tty}.")
    if pargs.debug:
        breakpoint()

    if True:
        SerDev = serial.Serial(pargs.tty, pargs.baudrate,
              timeout=0.2)# timeout should be longer than polling period of the connected MCUFEC
    else:#except serial.SerialException as e:
        print(f'ERR: serialException: {e}')
        SerDev.close()
        sys.exit(1)
    print('SerDev opened')

    liteserver.Server.Dbg = 0 if pargs.verbose is None else len(pargs.verbose)+1
    devName = 'dev1'
    printi(f'````````````````````{devName}````````````````````')
    devices = [MCUFEC(devName)]
    printi(f'```````````````````server````````````````````')
    server = liteserver.Server(devices, interface=pargs.interface,
        port=pargs.port)
    printi(f'Server started: {server}')

    for dev in devices:
        dev.start()
    printi(f'Devices started: {devices}')

    server.loop()
