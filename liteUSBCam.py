#!/usr/bin/env python3
"""LiteServer for USB camera"""
__version__ = 'v01 2019-06-03'# created

import sys, threading
Python3 = sys.version_info.major == 3
import numpy as np
try:
    import cv2
except ImportError:
    print("ERROR python-opencv must be installed")
    exit(1)

import liteServer
PV = liteServer.PV
Device = liteServer.Device
EventExit = liteServer.EventExit
printd = liteServer.printd

#````````````````````````````Helper functions`````````````````````````````````
def printw(msg): print('WARNING: '+msg)
def printe(msg): print('ERROR: '+msg)
def printd(msg): 
    if pargs.dbg:
        print('DBG:'+str(msg))
#````````````````````````````Process Variables````````````````````````````````
# We create two instances of a Scalers device and one instance of 'passive'
class Camera(Device):
    """ Derived from liteServer.Device.
    Note: All class members, which are not process variables should 
    be prefixed with _"""
    def __init__(self,name):
        pars = {
          'count':  PV('R','Image count',[0]),
          'flatImg':    PV('R','image',[0,0]),
          'pause':  PV('RW','Pause capturing',[False]), 
        }
        if Python3:
            super().__init__(name,pars)
        else:
            Device.__init__(self,name,pars)
        #print('n,p',self._name,pars)
        thread = threading.Thread(target=self._state_machine)
        thread.daemon = True
        thread.start()

        #````````````````````camera initialization
        # capture from the LAST camera in the system
        # presumably, if the system has a built-in webcam it will be the first
        for i in reversed(range(10)):
            print("Testing for presense of camera #{0}...".format(i))
            cv2_cap = cv2.VideoCapture(i)
            if cv2_cap.isOpened():
                break
        
        if not cv2_cap.isOpened():
            print("Camera not found!")
            exit(1)

        self._cv2_cap = cv2_cap
        cv2.namedWindow("lepton", cv2.WINDOW_NORMAL)
        
    def _state_machine(self):
        while not EventExit.is_set():
            EventExit.wait(1.)
            if self.pause.values[0]:
                continue
                
            ret, img = self._cv2_cap.read()
            if not ret:
                printw("Error reading image")
                continue
            print('img.shape',img.shape)
            flatImg = img.flatten().tolist()[:30000]
            print('cap.read',len(flatImg),flatImg[:10],type(flatImg[0]))
            self.flatImg.values = flatImg
            
            self.count.values[0] += 1
        print('liteUSBCam '+self._name+' exit')
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# parse arguments
import argparse
parser = argparse.ArgumentParser(description=\
  'Simple Process Variable server.')
parser.add_argument('-d','--dbg', action='store_true', help='debugging')
parser.add_argument('-n','--nCounters', type=int, default=1100,
  help='Number of counters in each scaler')
  #default liteAcces accepts 1100 doubles, 9990 int16s
  #the UDP socket size is limited to 64k bytes
pargs = parser.parse_args()

devices = [
  Camera('cam1'),
]

print('Serving:'+str([dev._name for dev in devices]))

server = liteServer.Server(devices,dbg=pargs.dbg)
server
server.loop()


