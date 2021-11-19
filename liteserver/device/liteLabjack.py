#!/usr/bin/env python3
"""liteserver for Labjack U3, supports 5 ADCs, 2 DACs, 2 Counter/Timers, 
9 Digital IOs"""
#__version__ = 'v02 2021-05-01'# DAC supported
#__version__ = 'v03 2021-05-03'# Counters supported, QuickSampling provides ~350 readouts/s
#__version__ = 'v04 2021-05-05'# set_DO(), softPulsing, RGB LEDs
__version__ = '1.0.6 2021-11-19'# do not call aborted()

print(f'liteLabjack {__version__}')

import sys, time, threading
from timeit import default_timer as timer
from functools import partial
import numpy as np

from liteserver import liteserver

#````````````````````````````Globals``````````````````````````````````````````
LDO = liteserver.LDO
Device = liteserver.Device
ModBusAddr={'DAC0':5000, 'DAC1':5002}

#````````````````````````````Initialization
import u3
D = u3.U3()
ConfigFIO = 'FIO:aaaaAOCC,EIO:xxxxxxxx'
#The following is implementation of the above ConfigIO 
config = D.configIO(FIOAnalog=0x1f, TimerCounterPinOffset=6,
    EnableCounter0=True, EnableCounter1=True)
print(config)

NHVs = 4
NLVs = 1
NDINs = 1
NCounters = 2
IsLV = [False]*NHVs + [True]*NLVs

# Sensors/Actuators
AINs = [u3.AIN(i, NegativeChannel=31, LongSettling=False, QuickSample=True)
            for i in range(NHVs+NLVs)]
DINs = [u3.BitStateRead(i) for i in range(NHVs+NLVs, NHVs+NLVs+NDINs)]
Counters = [u3.Counter(i, Reset = True) for i in range(NCounters)]
def RGB(rgb):# RGB LED connected to EIO7, EIO5, EIO3
    if rgb < 8: rgb += 8
    threeBits = bin(rgb)[-3:]
    ch = (15, 13, 11)
    return [u3.BitStateWrite(ch[i],int(threeBits[i])) for i in range(3)]

#````````````````````````````Helper functions`````````````````````````````````
def printi(msg): print('LLJ:INFO: '+msg)
def printw(msg): print('LLJ:WARNING: '+msg)
def printe(msg): print('LLJ:ERROR: '+msg)
def printd(msg): 
    if pargs.dbg:
        print('LLJ:dbgScaler: '+str(msg))

class LLJ(Device):
    """ Derived from liteserver.Device.
    Note: All class members, which are not process variables should 
    be prefixed with _"""
    def __init__(self,name):
        dac = [round(D.readRegister(ModBusAddr[i]),4) for i in ModBusAddr]
        fioDesc = 'Flexible IO, It can be configured as Digital IO or Analog (0.:2.5V) input'
        self.par = {
          'AIN':    LDO('R', '12-bit ADCs. First 4 are -10:+10 V, rest are 0:2.44V', [0.]*NHVs, units='V', getter=partial(self.getter,'AIN')),
          'DAC0':   LDO('RWE', 'DAC 0.04-4.95V, 10-bit PWM-based', dac[0],
            units='V', opLimits=[0.,4.95], setter=partial(self.set_DAC,'DAC0')),
          'DAC1':   LDO('RWE', 'DAC 0.04-4.95V, 10-bit PWM-based',dac[1],
            units='V', opLimits=[0.,4.95], setter=partial(self.set_DAC,'DAC1')),
          'FIO4':   LDO('R', fioDesc, 0.),
          'FIO5':   LDO('RWE', fioDesc, 0, setter=partial(self.set_DO,5)),
          'FIO6':   LDO('R', fioDesc, 0),
          'FIO7':   LDO('R', fioDesc, 0),
          'softPulsing': LDO('RWE', 'Continuous pulsing of a digital channel, capable channels are 4:15',
            0, opLimits=[0,15]),
          'configFIO':  LDO('RWE','Configuration of FIO and EIO ports. Codes: I-digital input, O-digital Output, A-analog input, C-counter, P-period',
            ConfigFIO, setter=self.set_configFIO),
          'hardPoll':    LDO('RWE', 'Hardware polling period', 1., units='s'),
          'cycle':  LDO('R','Cycle number', 1),
          'tempU3': LDO('R', 'Temperature of the U3 box', 0., units='C'),
          'rps':  LDO('R','Cycles per second', 0., units='Hz'),
        }
        super().__init__(name, self.par)
        #self._locals = locals()
        thread = threading.Thread(target=self._state_machine)
        thread.daemon = False
        thread.start()

    def _state_machine(self):
        time.sleep(.2)# give time for server to startup
        self.cycle.value = 0
        prevCycle = 0
        timestamp = time.time()
        periodic_update = timestamp

        while not self.EventExit.is_set():
            #printi(f'cycle of {self.name}:{self.cycle.value}')
            waitTime = self.hardPoll.value[0] - (time.time() - timestamp)
            if waitTime > 0:
                #print(f'wt {waitTime}')
                Device.EventExit.wait(waitTime)
            timestamp = time.time()
            dt = timestamp - periodic_update
            if dt > 10.:
                periodic_update = timestamp
                #print(f'periodic update: {dt}')
                self.tempU3.value = D.getTemperature() - 273.
                self.rps.value = round((self.cycle.value - prevCycle)/dt,2)
                prevCycle = self.cycle.value
            self.cycle.value += 1

            # softPulsing
            pc = int(self.softPulsing.value[0])
            if pc > 3:
                toggle = int(self.cycle.value & 1)
                D.getFeedback(u3.BitStateWrite(pc,toggle))

            # invalidate timestamps for changing variables, otherwise the
            # publish() will ignore them
            for i in [self.tempU3, self.rps, self.cycle, self.AIN,
                self.FIO4, self.FIO5, self.FIO6, self.FIO7]:
                i.timestamp = timestamp

            shippedBytes = self.publish()# 1ms

            #ts3 = timer(); print(f'pub: {ts3-ts2}')
        print('Labjack '+self.name+' exit')

    def set_DAC(self, parName):
        #print(f'set_DAC: {parName}')
        p = {'DAC0':self.DAC0, 'DAC1':self.DAC1}[parName]
        D.writeRegister(ModBusAddr[parName], p.value[0]) 

    def set_DO(self, channel):
        v = self.par[f'FIO{channel}'].value[0]
        #print(f'v: {channel,v}')
        D.getFeedback(u3.BitStateWrite(channel, v))

    def getter(self, parName):
        #print(f'getter: {parName}')
        #ts0 = timer()
        bits = D.getFeedback(*(AINs + DINs + Counters + RGB(self.cycle.value)))
        #ts1 = timer(); print(f'getFeedback: {ts1-ts0}')
        #print(f'bits: {bits}')
        nAINs = len(AINs)
        ainValues = [round(D.binaryToCalibratedAnalogVoltage(bits[i],
            isLowVoltage=IsLV[i], isSingleEnded=True,
            isSpecialSetting=False, channelNumber=i),5) for i in range(nAINs)]
        #ts2 = timer(); print(f'b2cal: {ts2-ts1}')
        #print(f'values: {values}')
        self.AIN.value = ainValues[:NHVs]
        self.FIO4.value = ainValues[4]
        self.FIO5.value = bits[5]
        self.FIO6.value = bits[6]
        self.FIO7.value = bits[7]

    def set_configFIO(self):
        msg = f'Changing configFIO is not supported yet {self.configFIO.value}'
        print(msg)
        raise ValueError(msg)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,S,,,,,,,,,,,,,,,,,,,,,,,,,,,,
# parse arguments
import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-d','--dbg', action='store_true', help='Debugging mode')
parser.add_argument('-b','--bigImage', action='store_true', help=\
'Generate big image >64kB')
parser.add_argument('-i','--interface', default = '', help=\
'Network interface. Default is the interface, which connected to internet')
n = 12000# to fit liteScaler volume into one chunk
parser.add_argument('-p','--port', type=int, default=9700, help=\
'Serving port, default: 9700') 
pargs = parser.parse_args()

liteserver.Server.Dbg = pargs.dbg
devices = [LLJ('dev1')]

print('Serving:'+str([dev.name for dev in devices]))

server = liteserver.Server(devices, interface=pargs.interface,
    port=pargs.port)
server.loop()
