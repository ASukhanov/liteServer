#!/usr/bin/env python3
"""LiteServer for an USB camera using pyuvc"""
__version__ = '3.1.0 2023-08-23'# from .. import liteserver
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
printd = liteserver.printd

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
          'subscribe': LDO('RWE','Subscribe to image', ['On'],legalValues\
            = ['On','Off']),
        }
        super().__init__(name,pars)

        dev_list = uvc.device_list()
        print(dev_list)
        self._cap = uvc.Capture(dev_list[0]["uid"])
        print(f'available modes: {self._cap.avaible_modes}')
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
        v = Device.server.version.value[0]
        Device.server.version.value[0] = 'UVC'+v
        Device.server.version.timestamp = time.time()

        periodic_update = time.time()
        periodic_count = 0
        while not EventExit.is_set():
            EventExit.wait(self.sleep.value[0])
            try:
                frame = self._cap.get_frame_robust()
            except Exception as e:
                printe(f'in get_frame: {e}')
                continue
            timestamp = time.time()
            self.count.value[0] += 1
            self.count.timestamp = timestamp
            dt = timestamp - periodic_update
            if dt > 1.:
                periodic_update = timestamp
                #print(f'periodic update: {dt}')
                di = self.count.value[0] - periodic_count
                periodic_count = self.count.value[0]
                self.imgps.value[0] = round(di/dt,4)
                self.imgps.timestamp = timestamp
                #print(f'periodic update: {di/dt}')
            img = frame.img
            #print(f'img.shape {img.shape}, data: {str(img)[:200]}...\n')
            if self.shape.value[0] == 0:
                self.shape.value = img.shape
                self.shape.timestamp = timestamp
            self.image.value = img
            if self.subscribe.value[0] == 'On':
                self.image.timestamp = timestamp
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
pargs = parser.parse_args()

devices = [
  Camera('cam1'),
]

print('Serving:'+str([dev.name for dev in devices]))

liteserver.Server.Dbg = pargs.dbg
server = liteserver.Server(devices, interface=pargs.interface)
server.loop()
#print(f'loop finished threads: {threading.enumerate()}')



