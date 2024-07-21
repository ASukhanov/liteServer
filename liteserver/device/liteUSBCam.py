#!/usr/bin/env python3
"""LiteServer for USB cameras"""
__version__ = '3.2.6 2024-07-18'# start/stop

import sys, time, threading
timer = time.perf_counter

import numpy as np
try:
    import cv2
except ImportError:
    print("ERROR python-opencv must be installed using following command:\n"
    "    pip3 install opencv-python-headless")
    exit(1)

from .. import liteserver
LDO = liteserver.LDO
Device = liteserver.Device
EventExit = Device.EventExit

#````````````````````````````Helper functions`````````````````````````````````
def printw(msg): print('WARNING: '+msg)
def printe(msg): print('ERROR: '+msg)
def printd(msg): 
    if pargs.verbose:
        print('DBG:'+str(msg))
#````````````````````````````Process Variables````````````````````````````````
class Camera(Device):
    """ Derived from liteServer.Device.
    Note: All class members, which are not process variables should 
    be prefixed with _"""
    def __init__(self,name):

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
          'subscribe': LDO('RWE','Subscribe to image', ['On'],legalValues\
            = ['On','Off']),
        }
        super().__init__(name,pars)
        self.start()
        
    def start(self):
        #````````````````````camera initialization
        # capture from the LAST camera in the system
        # presumably, if the system has a built-in webcam it will be the first
        # for i in reversed(range(10)):
            # print(f"Testing for presence of camera #{i}...")
            # cv2_cap = cv2.VideoCapture(i)
            # if cv2_cap.isOpened():
                # break
        i = 0
        cv2_cap = cv2.VideoCapture(i)
        if not cv2_cap.isOpened():
            printe("Camera not found!")
            exit(1)

        self._cv2_cap = cv2_cap
        #cv2.namedWindow("lepton", cv2.WINDOW_NORMAL)
        thread = threading.Thread(target=self._state_machine, daemon = False)
        self.stopped = False
        thread.start()

    def stop(self):
        self.stopped = True

    def _state_machine(self):
        while not self.EventExit.is_set():
            if self.stopped:
                break
            EventExit.wait(self.PV['sleep'].value[0])
            ret, img = self._cv2_cap.read()
            if not ret:
                printw("Error reading image")
                continue
            timestamp = time.time()
            printd(f'img.shape {img.shape}{img.dtype}, data: {str(img)[:200]}...\n')
            if self.PV['shape'].value[0] == 0:
                self.PV['shape'].value = img.shape
                self.PV['shape'].timestamp = timestamp
            self.PV['image'].value = img
            if self.PV['subscribe'].value[0] == 'On':
                self.PV['image'].timestamp = timestamp
            self.PV['count'].value[0] += 1
            self.PV['count'].timestamp = timestamp
            #msg=f'Ready to publish@{timestamp}'
            #self.PV['status'].value[0] = msg
            #self.PV['status'].timestamp = timestamp
            shippedBytes = self.publish()
            printd(f'shippedBytes: {shippedBytes}')

        self._cv2_cap.release()
        #cv2.destroyAllWindows()
        print('liteUSBCam2 '+self.name+' exit')
        #print(f'exit threads: {threading.enumerate()}')
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# parse arguments
import argparse
parser = argparse.ArgumentParser(description = __doc__
,formatter_class=argparse.ArgumentDefaultsHelpFormatter
,epilog=f'liteUSBCam: {__version__}, liteServer: {liteserver.__version__}')
defaultIP = liteserver.ip_address('')
parser.add_argument('-i','--interface', default = defaultIP, help=\
'network interface')
parser.add_argument('-v','--verbose', nargs='*',help=\
'Print more logging info, (-vv even more)')

pargs = parser.parse_args()

devices = [
  Camera('cam1'),
]

print('Serving:'+str([dev.name for dev in devices]))

if pargs.verbose == None:
    dbg = 0
else:
    try:    dbg = len(pargs.verbose[0])+1
    except: dbg = 1
liteserver.Server.Dbg = dbg
server = liteserver.Server(devices, interface=pargs.interface)
server.loop()
#print(f'loop finished threads: {threading.enumerate()}')



