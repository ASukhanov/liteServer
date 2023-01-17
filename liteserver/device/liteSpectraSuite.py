"""Wait for new SpectraSuite file in a folder and publish
spectrum from it."""
__version__ = '0.0.1 2023-01-14'#

import sys, time, os, threading
timer = time.perf_counter
import numpy as np
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
Threadlock = threading.Lock()
EventNewFile = threading.Event()
#Event_ready_for_next_file = threading.Event()
#Event_ready_for_next_file.set()
FileSet = set()

from liteserver import liteserver
LDO = liteserver.LDO
Device = liteserver.Device

#````````````````````````````Helper functions`````````````````````````````````
programStartTime = time.time()
def croppedText(txt, limit=200):
    if len(txt) > limit:
        txt = txt[:limit]+'...'
    return txt
def timeInProgram():
    return round(time.time() - programStartTime,6)
def printi(msg): print(f'inf_LSS@{timeInProgram()}: '+msg)
def printw(msg): print(f'WAR_LSS@{timeInProgram()}: '+msg)
def printe(msg): print(f'ERR_LSS@{timeInProgram()}: '+msg)
def _printv(msg, level=0):
    if pargs.verbose is None:
        return
    if len(pargs.verbose) >= level:
        print(f'dbg@{timeInProgram()}: '+msg)
def printv(msg):   _printv(msg, 0)
def printvv(msg):  _printv(msg, 1)

class FileCreateHandler(FileSystemEventHandler):
    def on_created(self, event):
        printv("Created: " + event.src_path)
        #Event_ready_for_next_file.wait()
        with Threadlock:
            FileSet.add(event.src_path)
        EventNewFile.set()

#````````````````````````````Lite Data Objects````````````````````````````````
class Publisher(Device):
    def __init__(self,name, bigImage=False):
        super().__init__(name)
        pars = {
          'y':          LDO('R','',[0.]),
          'x':          LDO('R','',[0.]),
          '_udpSpeed':  LDO('RI','Instanteneous socket.send speed', 0., units='MB/s'),
          '_cycle':     LDO('RI','Cycle counter',0),
          '_rps':       LDO('R','Cycles per second',0.,units='Hz'),
        }
        self.PV.update(pars)

        self.start()
    #``````````````Overridables```````````````````````````````````````````````        
    def start(self):
        printi('liteSpectraSuite started')
        thread = threading.Thread(target=self._thread)
        thread.daemon = False
        thread.start()

        event_handler = FileCreateHandler()

        # Create an observer.
        self.observer = Observer()

        # Attach the observer to the event handler.
        self.observer.schedule(event_handler, f'{pargs.folder}', recursive=True)

        # Start the observer.
        self.observer.start()

        '''
        try:
            while self.observer.is_alive():
                self.observer.join(1)
        finally:
            self.observer.stop()
            self.observer.join()
        '''
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,

    def handle_newFile(self):
        fileSet = FileSet.copy()
        for fn in fileSet:
            with Threadlock:
                FileSet.remove(fn)
            try:
                f = open(fn,'r')
            except:
                printw(f'File lost: {fn}')
                continue
            lines = f.readlines()
            f.close()

            # process the file
            print(f'File {fn}')#:\n{lines}')
            x,y = [],[]
            preamble = True
            for line in lines:
                line = line.rstrip()
                token = line.split(maxsplit=1)
                #printv(f'tokens: {token}')
                if preamble:
                    if token[0] == 'Date:':
                        tstruct = time.strptime(token[1],
                            "%a %b %d %H:%M:%S %Z %Y")
                        timestamp = time.mktime(tstruct)
                        print(f'timestamp: {timestamp}')
                    elif 'Begin' in token[0]:
                        preamble = False
                    continue
                try:
                    x.append(float(token[0]))
                    y.append(float(token[1]))
                except Exception as e:
                    #printv(f'exc: {e}')
                    pass
            #print(f'x: {x}')
            self.PV['x'].value = x
            self.PV['x'].timestamp = timestamp
            self.PV['y'].value = y
            self.PV['y'].timestamp = timestamp

    def _thread(self):
        time.sleep(.2)# give time for server to startup
        pv_status = self.PV['status']
        pv_cycle = self.PV['_cycle']
        pv_cycle.value = 0
        prevCycle = 0
        pv_run = self.PV['run']
        pv_udpSpeed = self.PV['_udpSpeed']
        periodic_update = time.time()
        while not Device.EventExit.is_set():
            if pv_run.value[0][:4] == 'Stop':
                break

            # check if new file have arrived
            EventNewFile.wait(1)
            if EventNewFile.isSet():
                self.handle_newFile()
                EventNewFile.clear()

            # periodic update of diagnostic parameters
            printv(f'cycle of {self.name}:{pv_cycle.value}')
            timestamp = time.time()
            dt = timestamp - periodic_update
            if dt > 10.:
                periodic_update = timestamp
                msg = f'periodic update {self.name} @{round(timestamp,3)}'
                #printv(msg)
                pv_status.set_valueAndTimestamp(msg, timestamp)
                self.PV['_rps'].set_valueAndTimestamp(\
                  (pv_cycle.value - prevCycle)/dt, timestamp)
                prevCycle = pv_cycle.value     
            pv_cycle.value += 1

            # print('publish all modified parameters of '+self.name)
            try:
                dt = server.Perf['Seconds'] - self._prevs[1]
                mbps = round((server.Perf['MBytes'] - self._prevs[0])/dt, 3)
            except:
                mbps = 0.
            self._prevs = server.Perf['MBytes'],server.Perf['Seconds']
            pv_udpSpeed.value = mbps

            # invalidate timestamps for changing variables, otherwise the
            # publish() will ignore them
            for i in [pv_cycle, pv_udpSpeed]:
                i.timestamp = timestamp

            ts = timer()
            shippedBytes = self.publish()

            if shippedBytes:
                ss = round(shippedBytes / (timer() - ts) / 1.e6, 3)
        print('Program '+self.name+' exit')
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,S,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# parse arguments
import argparse
parser = argparse.ArgumentParser(description=__doc__
    ,formatter_class=argparse.ArgumentDefaultsHelpFormatter
    ,epilog=f'liteScaler version {__version__}, liteserver {liteserver.__version__}')
parser.add_argument('-f','--folder', default='./data', help=\
'Folder to watch for new files')
defaultIP = liteserver.ip_address('')
parser.add_argument('-i','--interface', default = defaultIP, help=\
'Network interface. Default is the interface, which connected to internet.')
parser.add_argument('-p','--port', type=int, default=9700, help=\
'Serving port.') 
parser.add_argument('-v','--verbose', nargs='*', help='Show more log messages.')
pargs = parser.parse_args()
if not os.path.exists(pargs.folder):
    print(f'ERR: folder `{pargs.folder}` does not exist')
    sys.exit(1)

liteserver.Server.Dbg = 0 if pargs.verbose is None else len(pargs.verbose)+1
devices = [Publisher('dev1')]

print('Serving:'+str([dev.name for dev in devices]))

server = liteserver.Server(devices, interface=pargs.interface,
    port=pargs.port)
server.loop()
