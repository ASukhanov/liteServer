#!/usr/bin/env python3
"""liteserver for Raspberry Pi.
Supported:
  - Two hardware PWMs 1Hz-300 MHz, GPIO 12,13
  - Temperature sensors DS18B20 (0.5'C resolution), GPIO 4
  - Digital IOs (GPIO 19,20)
  - Pulse Counter (GPIO 26)
  - Spark detector (GPIO 26)
  - Buzzer (GPIO 13)
  - RGB LED indicator (GPIO 16,6,5)
  - OmegaBus serial sensors

TODO: connection to RPi Pico RP2040 MCU which will provide:
  - 4 of 12-bit ADC 500 kS/s
  - 1 us timestamping
  - real time
"""

#__version__ = 'v01 2021-05-22'# adopted from liteserver/litePigpio
#__version__ = 'v02 2021-05-28'# Fixed bug in 'buzz'
#__version__ = 'v03 2021-05-31'# publish1 can accept iterable values now
#__version__ = 'v04 2021-06-09'# seldomThread starts after publish! setters activated in add_more_parameters
#__version__ = 'v05 2021-06-09'# Omegabus was not published because of lagging timestamp.
#__version__ = 'v06 2021-06-10'# don't read_temperature after opening 1Wire it could be not ready
__version__ = 'v07 2021-11-19'

#TODO: take care of microsecond ticks in callback
print(f'senstation {__version__}')

import sys, time, threading, glob
from timeit import default_timer as timer
from functools import partial
#import numpy as np

from gpiozero import CPUTemperature
from liteserver import liteserver

#````````````````````````````Globals``````````````````````````````````````````
LDO = liteserver.LDO
Device = liteserver.Device
GPIO = {
    'Temp0': 4,
    'PWM0': 12,# 'PWM1':13,
    'Buzz': 13,
    'DI0':  19,
    'DI1':  20,
    'Counter0': 26,
    'RGB':  [16,6,5],
    'DO3':  25,
    'DO4':  24,
    'DHT':  21,
}

EventGPIO = {'Counter0':0.} # event-generated GPIOs, store the time when it was last published
#CallbackMinimalPublishPeiod = 0.01
MaxPWMRange = 1000000 # for hardware PWM0 and PWM1

#````````````````````````````Helper functions`````````````````````````````````
def printTime(): return time.strftime("%m%d:%H%M%S")
def printi(msg): print(f'SS:INFO@{printTime()}: '+msg)
def printw(msg): print(f'SS:WARNING@{printTime()}: '+msg)
def printe(msg): print(f'SS:ERROR@{printTime()}: '+msg)
def printd(msg): 
    if pargs.dbg:
        print('SS:dbg: '+str(msg))

#````````````````````````````Initialization
def init_gpio():
    global PiGPIO, pigpio, measure_temperature
    import pigpio
    PiGPIO = pigpio.pi()

    # Configure 1Wire pin 
    PiGPIO.set_mode( GPIO['Temp0'], pigpio.INPUT)
    PiGPIO.set_pull_up_down( GPIO['Temp0'], pigpio.PUD_UP)
    PiGPIO.set_glitch_filter( GPIO['Counter0'], 500)# require it stable for 500 us

    #````````````````````````Service for DS18B20 thermometer
    # Check if DS18B20 is connected
    base_dir = '/sys/bus/w1/devices/'
    OneWire_folder = None
    for i in range(10):
        try:
            OneWire_folder = glob.glob(base_dir + '28*')[0]
            break
        except IndexError:
            time.sleep(1)
            continue
    if OneWire_folder is None:
        print('WARNING: Thermometer sensor is not connected')
        def measure_temperature(): return 0
    else:
        device_file = OneWire_folder + '/w1_slave'
        print(f'Thermometer driver is: {device_file}')
         
        def read_temperature():
            f = open(device_file, 'r')
            lines = f.readlines()
            f.close()
            return lines
        #read_temperature()

        def measure_temperature():
            temp_c = None
            try:
                lines = read_temperature()
                if len(lines) != 2:
                    printw(f'no data from temperature sensor')
                    return temp_c
                #print(f'>mt: {lines}')
                #['80 01 4b 46 7f ff 0c 10 67 : crc=67 YES\n', '80 01 4b 46 7f ff 0c 10 67 t=24000\n']
                while lines[0].strip()[-3:] != 'YES':
                    time.sleep(0.2)
                    lines = read_temperature()
                equals_pos = lines[1].find('t=')
                if equals_pos != -1:
                    temp_string = lines[1][equals_pos+2:]
                    temp_c = float(temp_string) / 1000.0
            except Exception as e:
                printe(f'Exception in measure_temperature: {e}')
            return temp_c
#````````````````````````````Initialization of serial devices
OmegaBus = None
def init_serial():
    global OmegaBus
    try:
        if 'OmegaBus' in pargs.serial:
            OmegaBus = serial.Serial('/dev/ttyUSB0', 300)
            #OmegaBus.bytesize = 8
            OmegaBus.timeout = 1
            OmegaBus.write(b'$1RD\r\n')
            s = OmegaBus.read(100)
            print(f'OmegaBus read: "{s}"')
    except Exception as e:
        printe(f'Could not open communication to OmegaBus: {e}')
        sys.exit(1)
#````````````````````````````liteserver methods```````````````````````````````
class SensStation(Device):
    """ Derived from liteserver.Device.
    Note: All class members, which are not process variables should 
    be prefixed with _"""
    def __init__(self,name):
        self.par = {
          'boardTemp':    LDO('R','Temperature of the Raspberry Pi', 0., units='C'),
          'cycle':      LDO('R', 'Cycle number', 0),
          'cyclePeriod':LDO('RWE', 'Cycle period', pargs.update, units='s'),
          'PWM0_Freq':  LDO('RWE', f'Frequency of PWM at GPIO {GPIO["PWM0"]}',
            10, units='Hz', setter=partial(self.set_PWM_frequency, 'PWM0'),
            opLimits=[0,125000000]),
          'PWM0_Duty':  LDO('WE', f'Duty Cycle of PWM at GPIO {GPIO["PWM0"]}',
            .5, setter=partial(self.set_PWM_dutycycle, 'PWM0'),
            opLimits=[0.,1.]),
          'DI0':        LDO('R', f'Digital inputs of GPIOs {GPIO["DI0"]}',
            0),# getter=partial(self.getter,'DI0')),
          'DI1':        LDO('R', f'Digital inputs of GPIOs {GPIO["DI1"]}',
            0),# getter=partial(self.getter,'DI0')),
          'Counter0':   LDO('R', f'Digital counter of GPIO {GPIO["Counter0"]}',
            0),#, getter=partial(self.get_Cnt, 'Cnt0')),
          'RGB':        LDO('RWE', f'3-bit digital output',
            0, opLimits=[0,7], setter=self.set_RGB),
          'RGBControl':    LDO('RWE', 'Mode of RGB',
            ['RGBCycle'], legalValues=['RGBStatic','RGBCycle']),
          'DO3':        LDO('RWE', f'Digital outputs of GPIOs {GPIO["DO3"]}',
            '0', legalValues=['0','1'], setter=partial(self.set_DO, 'DO3')),
          'DO4':    LDO('RWE', f'Digital outputs of GPIOs {GPIO["DO4"]}',
            '0', legalValues=['0','1'], setter=partial(self.set_DO, 'DO4')),
          'Buzz':       LDO('RWE', f'Buzzer at GPIO {GPIO["Buzz"]}, activates when the Counter0 chganges',
            '0', legalValues=['0','1'], setter=self.set_Buzz),
          'BuzzDuration': LDO('RWE', f'Buzz duration', 5., units='s'),
          'Temp0':         LDO('R','Temperature of the DS18B20 sensor', 0., units='C'),
        }
        if 'OmegaBus' in pargs.serial:
            self.par['OmegaBus'] = LDO('R','OmegaBus reading', 0., units='V')
        
        super().__init__(name, self.par)

        # connect callback function to a GPIO pulse edge 
        for eventParName in EventGPIO:
            PiGPIO.callback(GPIO[eventParName], pigpio.RISING_EDGE, callback)
        self.start()

    #``````````````Overridables```````````````````````````````````````````````
    def start(self):
        printi('Senstation started')
        # invoke setters of all parameters
        for par,ldo in self.par.items():
            setter = ldo._setter
            if setter is not None:
                setter()
        thread = threading.Thread(target=self._state_machine, daemon=False)
        thread.start()

    def stop(self):
        printi(f"Senstation stopped {self.par['cycle'].value[0]}")
        prev = self.par['PWM0_Duty'].value[0]
        self.par['PWM0_Duty'].value[0] = 0.
        self.par['PWM0_Duty']._setter()
        self.par['PWM0_Duty'].value[0] = prev
        self.par['RGB'].value[0] = 0
        self.par['RGB']._setter()
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    def publish1(self, parName, value=None):
        # publish a parameter timestamped with current time
        if value is not None:
            try:
                self.par[parName].value[0] = value
            except:
                self.par[parName].value = value
        self.par[parName].timestamp = time.time()
        self.publish()

    def gpiov(self, parName):
        v = self.par[parName].value[0]
        key = parName.split('_')[0]
        gpio = GPIO[key]
        printd(f'gpiov {gpio,v}')
        return gpio,v
        
    def set_PWM_frequency(self, pwm):
        parName = pwm + '_Freq'
        gpio, v = self.gpiov(parName)
        #r = PiGPIO.hardware_PWM(gpio, int(v))
        dutyCycle = int(MaxPWMRange*self.par[pwm+'_Duty'].value[0])
        r = PiGPIO.hardware_PWM(gpio, int(v), dutyCycle)
        r = PiGPIO.get_PWM_frequency(gpio)
        self.publish1(parName, r)

    def set_PWM_dutycycle(self, pwm):
        parName = pwm + '_Duty'
        gpio, v = self.gpiov(parName)
        f = int(self.par[pwm + '_Freq'].value[0])
        printd(f'set_PWM_dutycycle: {f, int(v*MaxPWMRange)}')
        r = PiGPIO.hardware_PWM(gpio, f, int(v*MaxPWMRange))
        r = PiGPIO.get_PWM_dutycycle(gpio)
        self.publish1(parName, r/MaxPWMRange)

    def set_DO(self, parName):
        gpio,v = self.gpiov(parName)
        PiGPIO.write(gpio, int(v))

    def set_Buzz(self):
        if self.Buzz.value == '0':
            PiGPIO.write(GPIO['Buzz'], 0)
        else:
            thread = threading.Thread(target=buzzThread, daemon=False)
            thread.start()

    def set_RGB(self):
        v = int(self.par['RGB'].value[0])
        for i in range(3):
            PiGPIO.write(GPIO['RGB'][i], v&1)
            v = v >> 1

    def _state_machine(self):
        printi('State machine started')
        timestamp = time.time()
        periodic_update = timestamp
        #prevCounter0 = self.Counter0.value.value[0]
        while not Device.EventExit.is_set():
            if self.run.value[0][:4] == 'Stop':
                break
            waitTime = self.cyclePeriod.value[0] - (time.time() - timestamp)
            Device.EventExit.wait(waitTime)
            timestamp = time.time()
            self.cycle.value[0] += 1
            self.cycle.timestamp = timestamp
            if self.RGBControl.value[0] == 'RGBCycle':
                self.RGB.value[0] = self.cycle.value[0] & 0x7
                self.RGB.timestamp = timestamp
                self.set_RGB()
            self.publish()# publish all fresh parameters

            # do a less frequent tasks in a thread
            dt = timestamp - periodic_update
            if dt > 10.:
                periodic_update = timestamp
                thread = threading.Thread(target=self.seldomThread)
                thread.start()
        printi('State machine stopped')
        self.stop()

    def seldomThread(self):
        #print(f'>seldomThread: {timestamp}')
        #ts = timer()
        self.boardTemp.value[0] = CPUTemperature().temperature
        #print(f'CPUTemperature time: {round(timer()-ts,6)}')
        self.boardTemp.timestamp = time.time()
        temp = measure_temperature()# 0.9s spent here
        #print(f'Temp0 time: {round(timer()-ts,6)}')
        if temp is not None:
            self.Temp0.value[0] = temp
            self.Temp0.timestamp = time.time()
        if 'OmegaBus' in pargs.serial:
            OmegaBus.write(b'$1RD\r\n')
            r = OmegaBus.read(100)
            #print(f'OmegaBus read: {r}')
            if len(r) != 0:
                self.OmegaBus.value[0] = float(r.decode()[2:])/1000.
                self.OmegaBus.timestamp = time.time()
        #print(f'<seldomThread time: {round(timer()-ts,6)}')

def callback(gpio, level, tick):
    #print(f'callback: {gpio, level, tick}')
    timestamp = time.time()
    for gName in ['Counter0']:
        if gpio == GPIO[gName]:
            # increment Counter0
            SensStationDev1.par[gName].value[0] += 1
            SensStationDev1.par[gName].timestamp = timestamp
            # start buzzer
            SensStationDev1.par['Buzz'].value = '1'
            SensStationDev1.par['Buzz'].timestamp = timestamp
            SensStationDev1.set_Buzz()
    SensStationDev1.publish()

def buzzThread():
    # buzzing for a duration
    duration = SensStationDev1.BuzzDuration.value[0]
    PiGPIO.write(GPIO['Buzz'], 1)
    time.sleep(duration)
    SensStationDev1.publish1('Buzz', '0')
    PiGPIO.write(GPIO['Buzz'], 0)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#``````````````````Man````````````````````````````````````````````````````````
if __name__ == "__main__":
    # parse arguments
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser = argparse.ArgumentParser(description=__doc__
    ,formatter_class=argparse.ArgumentDefaultsHelpFormatter
    ,epilog=f'senstation: {__version__}')
    parser.add_argument('-d','--dbg', action='store_true', help='Debugging mode')
    parser.add_argument('-i','--interface', default = '', help=\
    'Network interface. Default is the interface, which connected to internet')
    n = 12000# to fit liteScaler volume into one chunk
    parser.add_argument('-p','--port', type=int, default=9700, help=\
    'Serving port, default: 9700')
    parser.add_argument('-s','--serial', default = '', help=\
    'Comma separated list of serial devices to support, e.g.:OmegaBus')
    parser.add_argument('-u','--update', type=float, default=1.0, help=\
    'Updating period')
    pargs = parser.parse_args()

    init_gpio()

    if pargs.serial != '':
        import serial
        init_serial()

    liteserver.Server.Dbg = pargs.dbg
    SensStationDev1 = SensStation('dev1')
    devices = [SensStationDev1]

    printi('Serving:'+str([dev.name for dev in devices]))

    server = liteserver.Server(devices, interface=pargs.interface,
        port=pargs.port)
    server.loop()
