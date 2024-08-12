#!/usr/bin/env python3
"""LiteServer for an USB camera using pyuvc"""
__version__ = '3.2.0 2024-08-10'# Camera selection.
print(f'liteUvcCam {__version__}')

import sys, time, threading
timer = time.perf_counter
import numpy as np

try:
    import uvc
except ImportError as e:
    print(f"ERROR pyuvc not installed: {e}")
    exit(1)

from .. import liteserver
LDO = liteserver.LDO
Device = liteserver.Device
EventExit = Device.EventExit

#````````````````````````````Helper functions`````````````````````````````````
def printw(msg): print('WARNING: '+msg)
def printe(msg): print('ERROR: '+msg)
def printd(msg): 
    if pargs.dbg:
        print('DBG:'+str(msg))
#````````````````````````````Process Variables````````````````````````````````
class Camera(Device):
    def __init__(self,name):
        """Note: All class members, which are not process variables should 
        be prefixed with _"""
        # initial image, the heght, width and number of plane could be approxiamate
        h,w,p = 4,3,3
        image = np.arange(h*w*p).astype('uint8').reshape(h,w,p)

        pars = {
          'count':  LDO('R','Image count', [0]),
          'image':  LDO('R','Image', image),
          'sleep':  LDO('RWE','Sleep time between image acquisitions',[1.],
            units='s', opLimits=(0.02,10)),
          'shape':  LDO('R','Frame shape Y,X,Planes', [0,0,0]),
          'fps':    LDO('R','Frames/s', [0]),
          'imgps':  LDO('R','Images/s', [0], units='img/s'),
          'subscribe': LDO('RWE','Enablw subscribtion to image', ['On'],legalValues\
            = ['On','Off']),
        }
        super().__init__(name,pars)

        dev_list = uvc.device_list()
        print(dev_list)
        idx = int(name[-1]) - 1
        usbDev = dev_list[idx]["uid"]
        print(f'Opening USB capture device: {usbDev}')
        if True:#try:
            self._cap = uvc.Capture(usbDev)
        else:#except:
            printe(f'Could not open camera {name}, try another one')
            sys.exit(1)
        print(f'available modes: {self._cap.available_modes}')
        frame_mode = (640, 480, 30)
        try:
            self._cap.frame_mode = (640, 480, 30)
            #self._cap.frame_mode = (960, 720, 15)
            self.fps.value[0] = self._cap.frame_mode[2]
        except Exception as e:
            printw(f'Failed to setup frame mode {frame_mode}: {e}')

        thread = threading.Thread(target=self._state_machine)
        thread.daemon = False
        thread.start()
        #print(f'thread started: {threading.enumerate()}')
        
    def _state_machine(self):
        time.sleep(0.1)# give time for Device to initialize

        periodic_update = time.time()
        periodic_count = 0
        while not EventExit.is_set():
            EventExit.wait(self.PV['sleep'].value[0])
            try:
                frame = self._cap.get_frame_robust()
            except Exception as e:
                printe(f'in get_frame: {e}')
                continue
            timestamp = time.time()
            self.PV['count'].value[0] += 1
            self.PV['count'].timestamp = timestamp
            dt = timestamp - periodic_update
            if dt > 1.:
                periodic_update = timestamp
                #print(f'periodic update: {dt}')
                di = self.PV['count'].value[0] - periodic_count
                periodic_count = self.PV['count'].value[0]
                self.PV['imgps'].value[0] = round(di/dt,4)
                self.PV['imgps'].timestamp = timestamp
                #print(f'periodic update: {di/dt}')
            img = frame.img
            #print(f'img.shape {img.shape}, data: {str(img)[:200]}...\n')
            if self.PV['shape'].value[0] == 0:
                self.PV['shape'].value = img.shape
                self.PV['shape'].timestamp = timestamp
            self.PV['image'].value = img
            if self.PV['subscribe'].value[0] == 'On':
                self.PV['image'].timestamp = timestamp
            #msg=f'Ready to publish@{timestamp}'
            #self.status.value[0] = msg
            #self.status.timestamp = timestamp
            shippedBytes = self.publish()

        self._cap = None
        print('liteUSBCam2 '+self.name+' exit')
        #print(f'exit threads: {threading.enumerate()}')
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# parse arguments
import argparse
parser = argparse.ArgumentParser(description = __doc__
,formatter_class=argparse.ArgumentDefaultsHelpFormatter
,epilog=f'liteUvcCam: {__version__}, liteserver: {liteserver.__version__}')
parser.add_argument('-d','--dbg', action='store_true', help='debugging')
defaultIP = liteserver.ip_address('')
parser.add_argument('-i','--interface', default = defaultIP, help=\
'network interface')
parser.add_argument('camera', default = 'cam1', help=\
'Selected camera, eg cam1/cam2/...')
pargs = parser.parse_args()

devices = [
  Camera(pargs.camera),
]

print('Serving:'+str([dev.name for dev in devices]))

liteserver.Server.Dbg = pargs.dbg
server = liteserver.Server(devices, interface=pargs.interface)
server.loop()
#print(f'loop finished threads: {threading.enumerate()}')



