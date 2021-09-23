#!/usr/bin/env python3
"""LiteServer for USB cameras"""
#__version__ = 'v01 2019-06-03'# created
#__version__ = 'v02 2019-06-10'# using latest liteServer
#__version__ = 'v03 2021-04-21'# pause parameter not needed, timestamping before publishing is not necessary
__version__ = 'v04 2021-09-21'# argparse 

#TODO: sometimes it does not start/stop nicely, Action required: disconnect camera, then run guvcview

import sys, time, threading
from timeit import default_timer as timer

import numpy as np
try:
    import cv2
except ImportError:
    print("ERROR python-opencv must be installed using following command:\n"
    "    pip3 install opencv-python-headless")
    exit(1)

from liteserver import liteserver
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
        print(f'Camera is opened {i}') 
        if not cv2_cap.isOpened():
            print("Camera not found!")
            exit(1)

        self._cv2_cap = cv2_cap
        #cv2.namedWindow("lepton", cv2.WINDOW_NORMAL)

        thread = threading.Thread(target=self._state_machine)
        thread.daemon = False
        thread.start()
        #print(f'thread started: {threading.enumerate()}')
        
    def _state_machine(self):
        while not self.aborted():
            EventExit.wait(self.sleep.value[0])
            ret, img = self._cv2_cap.read()
            if not ret:
                printw("Error reading image")
                continue
            timestamp = time.time()
            printd(f'img.shape {img.shape}, data: {str(img)[:200]}...\n')            
            if self.shape.value[0] == 0:
                self.shape.value = img.shape
                self.shape.timestamp = timestamp
            self.image.value = img
            if self.subscribe.value[0] == 'On':
                self.image.timestamp = timestamp
            self.count.value[0] += 1
            self.count.timestamp = timestamp
            #msg=f'Ready to publish@{timestamp}'
            #self.status.value[0] = msg
            #self.status.timestamp = timestamp
            shippedBytes = self.publish()

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



