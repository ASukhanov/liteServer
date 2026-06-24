#!/usr/bin/env python3
"""liteserver for Labjack U3, supports 5 ADCs, 2 DACs, 2 Counter/Timers, 
1 Digital IOs"""
# pylint: disable=invalid-name
__version__ = '3.4.0 2026-06-24'# PWM added with 1MHz clock

import sys, time, threading
from timeit import default_timer as timer
from functools import partial
import numpy as np

import u3
from .. import liteserver

#````````````````````````````Globals``````````````````````````````````````````
LDO = liteserver.LDO
Device = liteserver.Device
ModBusAddr={'DAC0':5000, 'DAC1':5002}

ConfigFIO = {'FIO':'AAAAaDTC', 'EIO':'aaaaDDDD'}
ConfigFIO_desc = 'Configuration of FIO and EIO ports. Codes: A:AIN_HV, a:AIN_LV, D-digital, T-timer, C-counter'
"""The above ConfigFIO means FIO0-3 are ADC_HV, FIO4 is ADC_LV,
FIO5 is digital IO, FIO6 is timer, and FIO7 is counter. 
The EIO ports: EIO0-3 are ADC_LV, and EIO4-7 are digital IOs.
Note: Changing configFIO at runtime is not supported yet.
"""
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

def isLV(i):# U3-HV analog inputs after AIN3 are low-voltage
    return i > 3

def pulse(ioNumber=5, duration=1, delay=0, positive=True):
    """Pulse a digital IO. duration and delay are in s128 us intervals,
    positive is the state of the pulse, default is True (high).
    If duration < 0, it will be a step instead of a pulse. Note: the actual.
    """
    wDel = divmod(delay,256)
    wDur = divmod(duration,256)
    cmdlist = [ u3.WaitLong(wDel[0]*2),u3.WaitShort(wDel[1]),
                u3.BitStateWrite(ioNumber, positive)]
    if duration >= 0:
        cmdlist += [u3.WaitLong(wDur[0]*2),u3.WaitShort(wDur[1]),
                    u3.BitStateWrite(ioNumber, not positive)]
    C_.D.getFeedback(*cmdlist)

#````````````````````````````
class C_:
    D = None# labjack device, will be initialized later after the class definition
    AIN_HVs = []
    AIN_LVs = []
    DIOs = []
    Counters = []
    timerCounterPinOffset = 0
    numberOfTimersEnabled = 0

def parseConfigFIO(configFIO):
    # The FIO0-3 can be configured as ADCs, the FIO4-7 can be configured as ADCs or digital IOs, and the EIO0-7 can be configured as digital IOs or timer/counters. For example, if ConfigFIO is set to 'AAAAaDTC', then FIO0-3 are ADC_HV, FIO4 is ADC_LV, FIO5 is digital IO, FIO6 is timer, and FIO7 is counter. The EIO ports are not used in this example.
    fioAinMask, eioAinMask = 0,0
    enableCounter = [False, False]
    nCounters = 0
    C_.timerCounterPinOffset = 0
    C_.numberOfTimersEnabled = 0

    # configure FIO and EIO ports based on ConfigFIO
    for i,char in enumerate(configFIO['FIO']):
        if char == 'a':
            fioAinMask |= 1<<i
            C_.AIN_LVs.append(u3.AIN(i, NegativeChannel=31, LongSettling=False, QuickSample=True))
        elif char == 'A':
            fioAinMask |= 1<<i
            C_.AIN_HVs.append(u3.AIN(i, NegativeChannel=31, LongSettling=False, QuickSample=True))
        elif char in 'T':
            C_.timerCounterPinOffset = i if C_.timerCounterPinOffset == 0 else C_.timerCounterPinOffset
            C_.numberOfTimersEnabled += 1
        elif char == 'C':
            enableCounter[C_.numberOfTimersEnabled+nCounters] = True
            C_.Counters.append(u3.Counter(i, Reset = True))
            nCounters += 1
        elif char == 'D':
           C_.DIOs.append(u3.BitStateRead(i))
    for i,char in enumerate(configFIO['EIO']):
        if char == 'a':
            eioAinMask |= 1<<i
            C_.AIN_LVs.append(u3.AIN(i+8, NegativeChannel=31, LongSettling=False, QuickSample=True))
        elif char == 'D':
            C_.DIOs.append(u3.BitStateRead(i+8))
    print(fioAinMask, eioAinMask, C_.timerCounterPinOffset, C_.numberOfTimersEnabled, enableCounter)

    configIO = C_.D.configIO(FIOAnalog=fioAinMask, EIOAnalog=eioAinMask,
                        TimerCounterPinOffset=C_.timerCounterPinOffset, 
                        NumberOfTimersEnabled=C_.numberOfTimersEnabled,
                        EnableCounter0=enableCounter[0], EnableCounter1=enableCounter[1])
    return configIO
    
#````````````````````````````Device`````````````````````````````````````
class LLJ(Device):
    def __init__(self,name):

        C_.D = u3.U3()# connect to the first found U3
        configIO = parseConfigFIO(ConfigFIO)
        printi(f'Connected to Labjack U3 with serial number {C_.D.serialNumber}, firmware version {C_.D.firmwareVersion}, configIO: {configIO}') 

        dac = [round(C_.D.readRegister(ModBusAddr[i]),4) for i in ModBusAddr]
        #fioDesc = 'Flexible IO, It can be configured as Digital IO or Analog (0.:2.5V) input'

        pars = {
'version': LDO('R', 'Version of the device server', __version__),
'DAC0':   LDO('RWE', 'DAC 0.04-4.95V, 10-bit PWM-based',
    dac[0], units='V', opLimits=[0.,4.95],
    setter=partial(self.set_DAC,'DAC0')),
'DAC1':   LDO('RWE', 'DAC 0.04-4.95V, 10-bit PWM-based',
    dac[1], units='V', opLimits=[0.,4.95],
    setter=partial(self.set_DAC,'DAC1')),
'AIN_HV':    LDO('R', '12-bit ADCs. range -10:+10 V',
    [0.]*len(C_.AIN_HVs), units='V', getter=self.getter),
'AIN_LV':    LDO('R', '12-bit ADCs. range 0:+2.44 V',
    [0.]*len(C_.AIN_LVs), units='V', getter=self.getter),
        }

        # add DIOs, which will be controlled byy pulse() with parameters set by PulsePars{i}
        pars['pulseTick'] =  LDO('R', 'The time resolution of the pulse parameters', 0.000128, units='s')
        pulseLegalValues = []
        for i,dio in enumerate(C_.DIOs):
            ioNumber = dio.ioNumber
            pulseName = f'PulseFIO{ioNumber}' if ioNumber < 8 else f'PulseEIO{ioNumber-8}'
            #print(f'Adding DIO{ioNumber} as parameter {pulseName}')
            pars[f'{pulseName}Pars'] = LDO('RWE',
              f'Pulse parameters of DIO IO number {ioNumber}: ioNumber, duration (-1 for infinite), delay, positive',
              [ioNumber, 1000, 0, 1])#setter=partial(self.set_Pulse, pulseName))
            pulseLegalValues.append(pulseName)
        pars['Pulse'] = LDO('RWE', 'Trigger a pulse with the above parameters', 
                             pulseLegalValues[0], legalValues=pulseLegalValues, setter=self.set_Pulse)

        # add counters and PWM parameters
        pars[f'Count'] = LDO('RWE', '32-bit counters', [0]*len(C_.Counters))
        pars['PWM_period'] = LDO('R', 'Period of the Pulse-width modulation, 2^16/1.MHz', 65.535, units='ms')
        pars['PWM_multiplier'] = LDO('RWE', 'Multiplier of the PWM period', 1, opLimits=[0,255], setter=self.set_PWM)
        pars['PWM_pulseWidth'] = LDO('RWE', 'Pulse width of the PWM, if <=0 then PWM is off', 1.,
                                     units='ms', opLimits=[0,65535], setter=self.set_PWM)

        # add some other useful parameters
        pars.update({
'configFIO':    LDO('R',ConfigFIO_desc, str(ConfigFIO)),#, setter=self.set_configFIO),
'hardPoll': LDO('RWE',  'Hardware polling period', 1., units='s'),
'cycle':    LDO('R',    'Cycle number', 1),
'tempU3':   LDO('R',    'Temperature of the U3 box', 0., units='C'),
'rps':      LDO('R',    'Cycles per second', 0., units='Hz'),
        })
        super().__init__(name, pars)
        self.start()

    # Override the start and stop methods to print messages
    def start(self):
        """Start the device server."""
        thread = threading.Thread(target=self._thread)
        thread.daemon = False
        thread.start()    
    def stop(self):
        return
    
    def _thread(self):
        """The thread that updates the cycle number, reads the ADCs, and updates the counters."""
        time.sleep(.2)# give time for server to startup
        self.PV['cycle'].value = 0
        prevCycle = 0
        timestamp = time.time()
        periodic_update = timestamp
        printi(f'Labjack {self.name} thread started')

        while not self.EventExit.is_set():
            #printi(f'cycle of {self.name}:{self.PV['cycle'].value}')
            if self.PV['run'].value[0].startswith('Stop'):
                break;
            waitTime = self.PV['hardPoll'].value[0] - (time.time() - timestamp)
            if waitTime > 0:
                #print(f'wt {waitTime}')
                Device.EventExit.wait(waitTime)

            C_.D.getFeedback(u3.LED(self.PV['cycle'].value & 1))# blink the LED to show that the device is alive
            timestamp = time.time()
            dt = timestamp - periodic_update
            if dt > 10.:
                periodic_update = timestamp
                #print(f'periodic update: {dt}')
                self.PV['tempU3'].value = C_.D.getTemperature() - 273.
                self.PV['rps'].value = round((self.PV['cycle'].value - prevCycle)/dt,2)
                prevCycle = self.PV['cycle'].value
            self.PV['cycle'].value += 1
            self.getter()

            # invalidate timestamps for changed variables, otherwise the
            # publish() will ignore them
            for i in [self.PV['tempU3'], self.PV['rps'], self.PV['cycle'],
                self.PV['AIN_HV'], self.PV['AIN_LV'], self.PV['Count']]:
                i.timestamp = timestamp
            shippedBytes = self.publish()# 1ms
        C_.D.getFeedback(u3.LED(True))# turn on the LED to show that the device is powered
        printi(f'Labjack {self.name} thread exiting')

    def getter(self):
        """Get the ADC values and counter values."""
        ts0 = timer()
        bits = C_.D.getFeedback(*(C_.AIN_HVs + C_.AIN_LVs + C_.DIOs + C_.Counters))# + RGB(self.PV['cycle'].value)))
        ts1 = timer(); 
        printv(f'getFeedback time: {round(ts1-ts0,6)}\nbits: {bits}')
        ainValues = [round(C_.D.binaryToCalibratedAnalogVoltage(bits[i],
            isLowVoltage=isLV(i), isSingleEnded=True,
            isSpecialSetting=False, channelNumber=i),5)\
            for i in range(len(C_.AIN_HVs)+len(C_.AIN_LVs))]
        ts2 = timer();
        printv(f'values: {ainValues}, b2cal:{round(ts2-ts1,6)}')
        nHVs, nLVs = len(C_.AIN_HVs), len(C_.AIN_LVs)
        self.PV['AIN_HV'].value = ainValues[:nHVs]
        self.PV['AIN_LV'].value = ainValues[nHVs:nHVs+nLVs]

    def set_DAC(self, parName):
        #print(f'set_DAC: {parName}')
        p = {'DAC0':self.PV['DAC0'], 'DAC1':self.PV['DAC1']}[parName]
        C_.D.writeRegister(ModBusAddr[parName], p.value[0]) 

    def set_DO(self, idx):
        v = self.PV[f'DIO{idx}'].value
        channel = idx + ChDef.index('DIO')
        print(f'v: {channel,v}')
        #C_.D.getFeedback(u3.BitStateWrite(channel, v))
    
    def set_Pulse(self):
        parName = self.PV['Pulse'].value[0]
        #print(f'set_Pulse: {parName}')
        p = self.PV[parName+'Pars']
        #print(f'set_Pulse: {parName}, pars: {p.value}')
        pulse(ioNumber=p.value[0], duration=p.value[1], delay=p.value[2], positive=p.value[3])

    def set_configFIO(self):
        msg = f"Changing configFIO is not supported yet {self.PV['configFIO'].value}"
        print(msg)
        raise ValueError(msg)

    def set_PWM(self):
        multiplier = self.PV['PWM_multiplier'].value[0]
        pulseWidth = self.PV['PWM_pulseWidth'].value[0]*1000.
        baseValue = 65535# 16-bit timer
        if pulseWidth <= 0:
            printi('Turning off PWM')
            #TODO#C_.D.configIO(NumberOfTimersEnabled=0)
        else:
            #TODO#C_.D.configIO(NumberOfTimersEnabled=C_.numberOfTimersEnabled)
            C_.D.configTimerClock(TimerClockBase=3, TimerClockDivisor=multiplier)# 3 means 1MHz, so the timer tick is 1/1MHz = 1us, and the maximum period is 65535*1us = 65.535ms. The multiplier can be used to extend the period.
            ticks = round(pulseWidth*1./multiplier)# convert pulse width in us to timer ticks
            C_.D.getFeedback(u3.Timer0Config(TimerMode=0, Value=baseValue-ticks))
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=f'liteLabjack {__version__}, liteserver {liteserver.__version__}')
    parser.add_argument('-i','--interface', default = '',
        choices=liteserver.ip_choices() + ['','localhost'], help=\
'Network address. Default is the addrees, which is connected to internet')
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
    print((f"To plot: python -m pvplot -a'L:{server.host};{pargs.port}:dev1:' "\
    "'tempU3 AIN_HV[0] AIN_HV[1] AIN_HV[2] AIN_HV[3] AIN_LV[0] AIN_LV[1] AIN_LV[2] AIN_LV[3]'"))
    print(f"To control: python -m pypeto -aLITE '{server.host};{pargs.port}:dev1'")
    print(','*79)

    server.loop()
