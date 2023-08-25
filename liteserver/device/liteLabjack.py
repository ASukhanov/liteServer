#!/usr/bin/env python3
"""liteserver for Labjack U3, supports 5 ADCs, 2 DACs, 2 Counter/Timers, 
1 Digital IOs"""
__version__ = '3.1.0 2023-08-23'# from .. import liteserver

print(f'liteLabjack {__version__}')

import sys, time, threading
from timeit import default_timer as timer
from functools import partial
import numpy as np

from .. import liteserver

#````````````````````````````Globals``````````````````````````````````````````
LDO = liteserver.LDO
Device = liteserver.Device
ModBusAddr={'DAC0':5000, 'DAC1':5002}
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

#````````````````````````````Initialization
import u3
D = u3.U3()
ConfigFIO = 'FIO:aaaaAOCC,EIO:xxxxxxxx'
#The following is implementation of the above ConfigIO 
config = D.configIO(FIOAnalog=0x1f, TimerCounterPinOffset=6,
    EnableCounter0=True, EnableCounter1=True)
print(config)

# Sensors/Actuators
ChDef = [*['ADC_HV']*4, *['ADC_LV']*1, *['DIO']*1,*['Count']*2]
IsLV = [i=='ADC_LV' for i in ChDef]
n = len(ChDef)
AIN_HVs = [u3.AIN(i, NegativeChannel=31, LongSettling=False, QuickSample=True)
            for i in range(n) if ChDef[i] == 'ADC_HV']
AIN_LVs = [u3.AIN(i, NegativeChannel=31, LongSettling=False, QuickSample=True)
            for i in range(n) if ChDef[i] == 'ADC_LV']
NHVs = len(AIN_HVs)
NLVs = len(AIN_LVs)
DINs = [u3.BitStateRead(i) for i in range(n) if ChDef[i] == 'DIO']
Counters = [u3.Counter(i, Reset = True) for i in range(ChDef.count('Count'))]
def RGB(rgb):# RGB LED connected to EIO7, EIO5, EIO3
    if rgb < 8: rgb += 8
    threeBits = bin(rgb)[-3:]
    ch = (15, 13, 11)
    return [u3.BitStateWrite(ch[i],int(threeBits[i])) for i in range(3)]

#````````````````````````````Device`````````````````````````````````````
class LLJ(Device):
    def __init__(self,name):
        dac = [round(D.readRegister(ModBusAddr[i]),4) for i in ModBusAddr]
        #fioDesc = 'Flexible IO, It can be configured as Digital IO or Analog (0.:2.5V) input'

        pars = {
'ADC_HV':    LDO('R', '12-bit ADCs. range -10:+10 V',
    [0.]*NHVs, units='V', getter=self.getter),
'ADC_LV':    LDO('R', '12-bit ADCs. range 0:+2.44 V',
    [0.]*NLVs, units='V', getter=self.getter),
'DAC0':   LDO('RWE', 'DAC 0.04-4.95V, 10-bit PWM-based',
    dac[0], units='V', opLimits=[0.,4.95],
    setter=partial(self.set_DAC,'DAC0')),
'DAC1':   LDO('RWE', 'DAC 0.04-4.95V, 10-bit PWM-based',
    dac[1], units='V', opLimits=[0.,4.95],
    setter=partial(self.set_DAC,'DAC1'))
        }
        for i in range(ChDef.count('DIO')):
            pars[f'DIO{i}'] = LDO('RWE', 'Digital IO', 0,
                setter=partial(self.set_DO, i))
        pars[f'Count'] = LDO('RWE', '32-bit counters',
            [0]*ChDef.count('Count'))
        pars.update({
'softPulsing':  LDO('RWE', 'Continuous pulsing of a digital channel, capable channels are 4:15',
    0, opLimits=[0,15]),
'configFIO':    LDO('RWE','Configuration of FIO and EIO ports. Codes: I-digital input, O-digital Output, A-analog input, C-counter, P-period',
    ConfigFIO, setter=self.set_configFIO),
'hardPoll': LDO('RWE',  'Hardware polling period', 1., units='s'),
'cycle':    LDO('R',    'Cycle number', 1),
'tempU3':   LDO('R',    'Temperature of the U3 box', 0., units='C'),
'rps':      LDO('R',    'Cycles per second', 0., units='Hz'),
        })
        super().__init__(name, pars)
        thread = threading.Thread(target=self._thread)
        thread.daemon = False
        thread.start()

    def _thread(self):
        time.sleep(.2)# give time for server to startup
        self.PV['cycle'].value = 0
        prevCycle = 0
        timestamp = time.time()
        periodic_update = timestamp

        while not self.EventExit.is_set():
            #printi(f'cycle of {self.name}:{self.PV['cycle'].value}')
            waitTime = self.PV['hardPoll'].value[0] - (time.time() - timestamp)
            if waitTime > 0:
                #print(f'wt {waitTime}')
                Device.EventExit.wait(waitTime)
            timestamp = time.time()
            dt = timestamp - periodic_update
            if dt > 10.:
                periodic_update = timestamp
                #print(f'periodic update: {dt}')
                self.PV['tempU3'].value = D.getTemperature() - 273.
                self.PV['rps'].value = round((self.PV['cycle'].value - prevCycle)/dt,2)
                prevCycle = self.PV['cycle'].value
            self.PV['cycle'].value += 1
            self.getter()

            # softPulsing
            pc = int(self.PV['softPulsing'].value[0])
            if pc > 3:
                toggle = int(self.PV['cycle'].value & 1)
                D.getFeedback(u3.BitStateWrite(pc,toggle))

            # invalidate timestamps for changing variables, otherwise the
            # publish() will ignore them
            for i in [self.PV['tempU3'], self.PV['rps'], self.PV['cycle'],
                self.PV['ADC_HV'], self.PV['ADC_LV'], self.PV['Count']]:
                i.timestamp = timestamp
            shippedBytes = self.publish()# 1ms
        print('Labjack '+self.name+' exit')

    def set_DAC(self, parName):
        #print(f'set_DAC: {parName}')
        p = {'DAC0':self.PV['DAC0'], 'DAC1':self.PV['DAC1']}[parName]
        D.writeRegister(ModBusAddr[parName], p.value[0]) 

    def set_DO(self, idx):
        v = self.PV[f'DIO{idx}'].value
        channel = idx + ChDef.index('DIO')
        print(f'v: {channel,v}')
        #D.getFeedback(u3.BitStateWrite(channel, v))

    def getter(self):
        ts0 = timer()
        bits = D.getFeedback(*(AIN_HVs + AIN_LVs + DINs + Counters))# + RGB(self.PV['cycle'].value)))
        ts1 = timer(); 
        printv(f'getFeedback: {round(ts1-ts0,6)}\nbits: {bits}')
        ainValues = [round(D.binaryToCalibratedAnalogVoltage(bits[i],
            isLowVoltage=IsLV[i], isSingleEnded=True,
            isSpecialSetting=False, channelNumber=i),5)\
            for i in range(NHVs+NLVs)]
        ts2 = timer();
        printv(f'values: {ainValues}, b2cal:{round(ts2-ts1,6)}')
        self.PV['ADC_HV'].value = ainValues[:NHVs]
        self.PV['ADC_LV'].value = ainValues[NHVs:NHVs+NLVs]

    def set_configFIO(self):
        msg = f"Changing configFIO is not supported yet {self.PV['configFIO'].value}"
        print(msg)
        raise ValueError(msg)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-i','--interface', default = '', help=\
    'Network interface. Default is the interface, which connected to internet')
    n = 12000# to fit liteScaler volume into one chunk
    parser.add_argument('-p','--port', type=int, default=9700, help=\
    'Serving port, default: 9700') 
    parser.add_argument('-v','--verbose', nargs='*', help='Show more log messages.')
    pargs = parser.parse_args()

    devices = [LLJ('dev1')]

    print('Serving:'+str([dev.name for dev in devices]))

    server = liteserver.Server(devices, interface=pargs.interface,
        port=pargs.port)

    print('`'*79)
    print((f"To monitor, use: pvplot -a'L:{server.host};{pargs.port}:dev1' "\
    "'tempU3 ADC_HV[0] ADC_HV[1] ADC_HV[2] ADC_HV[3] ADC_LV'"))
    print(','*79)

    server.loop()
