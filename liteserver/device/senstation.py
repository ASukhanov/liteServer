#!/usr/bin/env python3
"""liteserver for Raspberry Pi.
Supported:
  - Two hardware PWMs 1Hz-300 MHz, (GPIO 12,13).
  - Temperature sensors DS18B20 (0.5'C resolution), (GPIO 4).
  - Temperature and Humidity sensors DHT11 and DHT22 (GPIO 23).
  - Digital IOs (GPIO 19,20).
  - Pulse Counter (GPIO 26).
  - Spark/fire detector (GPIO 26).
  - Buzzer (GPIO 13).
  - RGB LED indicator (GPIO 22,27,17).
  - I2C devices: ADS1x15, MMC5983MA, HMC5883, QMC5983.
  - I2C mutiplexers TCA9548, PCA9546.
  - OmegaBus serial sensors.
"""
__version__ = '3.3.3 2025-04-05'# Support for DHT using adafruit_dht, the pigpio_dht is not reliable

#TODO: take care of microsecond ticks in callback

print(f'senstation {__version__}')

import sys, time, threading, glob, struct
timer = time.perf_counter
from functools import partial
import numpy as np

from .. import liteserver
#````````````````````````````Globals``````````````````````````````````````````
MgrInstance = None
LDO = liteserver.LDO
Device = liteserver.Device
GPIO = {
    'Temp0': 4,
    'PWM0': 12,# 'PWM1':13,
    'Buzz': 13,
    'DI0':  19,
    'DI1':  20,
    'Counter0': 26,
    'RGB':  [22,27,17],
    'DO3':  25,
    'DO4':  24,
    'DHT':  23,
}
EventGPIO = {'Counter0':0.} # event-generated GPIOs, store the time when it was last published
#CallbackMinimalPublishPeiod = 0.01
MaxPWMRange = 1000000 # for hardware PWM0 and PWM1
Seldom_update_period = 10.# update period for slow-changing parameters like temperature and humidity

#`````````````````````````````Helper methods```````````````````````````````````
from . import helpers
def printi(msg):  helpers.printi(msg)
def printe(msg):
    helpers.printe(msg)
    if MgrInstance is not None: MgrInstance.set_status('ERROR: '+msg)
def printw(msg): 
    helpers.printw(msg)
    if MgrInstance is not None: MgrInstance.set_status('WARNING: '+msg)
def printv(msg):  helpers.printv(msg, pargs.verbose)
def printvv(msg): helpers.printv(msg, pargs.verbose, level=1)

#````````````````````````````Initialization
def init_gpio():
    global PiGPIO, pigpio, measure_temperature
    try:
        import pigpio
    except:
        print('ERROR. This server should run on Raspberry Pi and have the pipgpio module installed.')
        sys.exit(1)
    PiGPIO = pigpio.pi()

    # Configure 1Wire pin
    try:    PiGPIO.set_mode( GPIO['Temp0'], pigpio.INPUT)
    except:
        printe('Did you start the pigpio daemon? E.g. sudo pigpiod')
        sys.exit()
    PiGPIO.set_pull_up_down( GPIO['Temp0'], pigpio.PUD_UP)
    PiGPIO.set_glitch_filter( GPIO['Counter0'], 500)# require it stable for 500 us

    #````````````````````````Service for DS18B20 thermometer
    # Check if DS18B20 is connected
    OneWire_folder = None
    if pargs.oneWire:
        base_dir = '/sys/bus/w1/devices/'
        for i in range(10):
            try:
                OneWire_folder = glob.glob(base_dir + '28*')[0]
                break
            except IndexError:
                time.sleep(1)
                continue
    print(f'OneWire_folder: {OneWire_folder}')
    if OneWire_folder is None:
        print('WARNING: Thermometer sensor is not connected')
        def measure_temperature(): return None
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


#````````````````````````````liteserver methods````````````````````````````````
class SensStation(Device):
    """ Derived from liteserver.Device.
    Note: All class members, which are not process variables should 
    be prefixed with _"""

    def __init__(self,name):
        ldos = {}

        # Add I2C devices
        if pargs.muxAddr is not None:
            from liteserver.device import i2c
            self.I2C = i2c.I2C
            self.I2C.verbosity = pargs.verbose
            i2c.init(pargs.muxAddr, pargs.muxMask)
            ldos.update(self.I2C.LDOMap)

        ldos.update({
          'boardTemp':  LDO('R','Temperature of the Raspberry Pi', 0., units='C'),
          'cycle':      LDO('R', 'Cycle number', 0),
          'cyclePeriod':LDO('RWE', 'Cycle period', pargs.update, units='s'),
          'period':     LDO('R', 'Measured period', pargs.update, units='s'),
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
          'Buzz':       LDO('RWE', f'Buzzer at GPIO {GPIO["Buzz"]}, activates when the Counter0 changes',
            '0', legalValues=['0','1'], setter=self.set_Buzz),
          'BuzzDuration': LDO('RWE', f'Buzz duration', 5., units='s'),
        })
        if pargs.oneWire:
            ldos['Temp0'] = LDO('R','Temperature of the DS18B20 sensor', 0.,
                units='C')
        if 'OmegaBus' in pargs.serial:
            ldos['OmegaBus'] = LDO('R','OmegaBus reading', 0., units='V')

        if pargs.dht is not None:
            import adafruit_dht
            import board
            if pargs.dht == '11':
                pargs.dht = adafruit_dht.DHT11(board.D23)
            elif pargs.dht == '22':
                pargs.dht = adafruit_dht.DHT22(board.D23)
            else:
                printw('Wrong option value for --dht, should be DHT11/22')
                pargs.dht = None
            if pargs.dht is not None:
                ldos['Temperature'] = LDO('R',
                'Temperature, provided by the DHT sensor, connected to IO23', 0., units='C')
                ldos['Humidity'] = LDO('R',
                'Humidity, provided by the DHT sensor, connected to IO23', 0.)

        super().__init__(name,ldos)

        # connect callback function to a GPIO pulse edge
        for eventParName in EventGPIO:
            PiGPIO.callback(GPIO[eventParName], pigpio.RISING_EDGE, callback)
        self.start()

    #``````````````Overridables```````````````````````````````````````````````
    def start(self):
        printi('Senstation started')
        # invoke setters of all parameters, except 'run'
        for par,ldo in self.PV.items():
            setter = ldo._setter
            if setter is not None:
                if str(par) == 'run':  continue
                setter()
        thread = threading.Thread(target=self._threadRun, daemon=False)
        thread.start()

    def stop(self):
        printi(f"Senstation stopped {self.PV['cycle'].value[0]}")
        prev = self.PV['PWM0_Duty'].value[0]
        self.PV['PWM0_Duty'].value[0] = 0.
        self.PV['PWM0_Duty']._setter()
        self.PV['PWM0_Duty'].value[0] = prev
        self.PV['RGB'].value[0] = 0
        self.PV['RGB']._setter()
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    def publish1(self, parName, value=None):
        # publish a parameter timestamped with current time
        if value is not None:
            try:
                self.PV[parName].value[0] = value
            except:
                self.PV[parName].value = value
        self.PV[parName].timestamp = time.time()
        self.publish()

    def gpiov(self, parName):
        v = self.PV[parName].value[0]
        key = parName.split('_')[0]
        gpio = GPIO[key]
        printv(f'gpiov {gpio,v}')
        return gpio,v

    def set_PWM_frequency(self, pwm):
        parName = pwm + '_Freq'
        gpio, v = self.gpiov(parName)
        #r = PiGPIO.hardware_PWM(gpio, int(v))
        dutyCycle = int(MaxPWMRange*self.PV[pwm+'_Duty'].value[0])
        r = PiGPIO.hardware_PWM(gpio, int(v), dutyCycle)
        r = PiGPIO.get_PWM_frequency(gpio)
        self.publish1(parName, r)

    def set_PWM_dutycycle(self, pwm):
        parName = pwm + '_Duty'
        gpio, v = self.gpiov(parName)
        f = int(self.PV[pwm + '_Freq'].value[0])
        printv(f'set_PWM_dutycycle: {f, int(v*MaxPWMRange)}')
        r = PiGPIO.hardware_PWM(gpio, f, int(v*MaxPWMRange))
        r = PiGPIO.get_PWM_dutycycle(gpio)
        self.publish1(parName, r/MaxPWMRange)

    def set_DO(self, parName):
        gpio,v = self.gpiov(parName)
        PiGPIO.write(gpio, int(v))

    def set_Buzz(self):
        printv('>set_Buss')
        if self.PV['Buzz'].value == '0':
            PiGPIO.write(GPIO['Buzz'], 0)
        else:
            thread = threading.Thread(target=buzzThread, daemon=False)
            thread.start()

    def set_RGB(self):
        v = int(self.PV['RGB'].value[0])
        for i in range(3):
            PiGPIO.write(GPIO['RGB'][i], v&1)
            v = v >> 1

    def _threadRun(self):
        printi('threadRun started')
        timestamp = time.time()
        prevcurtime = timestamp
        last_seldom_update = 0
        self.prevCPUTempTime = 0.
        while not Device.EventExit.is_set():
            if self.PV['run'].value[0][:4] == 'Stop':
                break
            #printv(f"cycle {self.PV['cycle'].value[0]}")
            # do a less frequent tasks in a thread
            dt = timestamp - last_seldom_update
            if dt > Seldom_update_period:
                last_seldom_update = timestamp
                thread = threading.Thread(target=self.seldomThread)
                thread.start()

            # wait for next time interval
            curtime = time.time()
            period = round(curtime - prevcurtime,6)
            prevcurtime = curtime
            dt = curtime - timestamp
            waitTime = self.PV['cyclePeriod'].value[0] - dt
            Device.EventExit.wait(waitTime)
            timestamp = time.time()

            # collect data
            if pargs.muxAddr is not None:
                for i2cDev in self.I2C.DeviceMap.values():
                    if True:#try:
                        i2cDev.read(timestamp)
                    else:#except Exception as e:
                        printw(f'Exception in threadRun: {e}')
                        continue
            self.PV['cycle'].value[0] += 1
            self.PV['cycle'].timestamp = timestamp
            self.PV['period'].set_valueAndTimestamp([period])
            if self.PV['RGBControl'].value[0] == 'RGBCycle':
                self.PV['RGB'].set_valueAndTimestamp(\
                    [self.PV['cycle'].value[0] & 0x7], timestamp)
                self.set_RGB()
            self.publish()# publish all fresh parameters

        printi('threadRun stopped')
        self.stop()

    def seldomThread(self):
        #print(f'>seldomThread: {timestamp}')
        try:
            with open(r"/sys/class/thermal/thermal_zone0/temp") as f:
                r = f.readline()
                temperature = float(r.rstrip()) / 1000.
                self.PV['boardTemp'].set_valueAndTimestamp([temperature])
        except Exception as e:
            printw(f'Could not read CPU temperature `{r}`: {e}')
        temp = measure_temperature()# 0.9s spent here
        #print(f'Temp0 time: {round(timer()-ts,6)}')
        if temp is not None:
            self.PV['Temp0'].set_valueAndTimestamp([temp])
        if 'OmegaBus' in pargs.serial:
            OmegaBus.write(b'$1RD\r\n')
            r = OmegaBus.read(100)
            #print(f'OmegaBus read: {r}')
            if len(r) != 0:
                self.PV['OmegaBus'].set_valueAndTimestamp([float(r.decode()[2:])/1000.])
        #print(f'<seldomThread time: {round(timer()-ts,6)}')
        if pargs.dht is not None:
            try:
                self.PV['Temperature'].set_valueAndTimestamp(pargs.dht.temperature)
                self.PV['Humidity'].set_valueAndTimestamp(pargs.dht.humidity)
                printv(f'T: {pargs.dht.temperature}, H: {pargs.dht.humidity}')
            except Exception as e:
                printw(f'in reading DHT: {e}')

    def set_status(self, msg):
        self.PV['status'].set_valueAndTimestamp(msg)

def callback(gpio, level, tick):
    #print(f'callback: {gpio, level, tick}')
    timestamp = time.time()
    for gName in ['Counter0']:
        if gpio == GPIO[gName]:
            # increment Counter0
            MgrInstance.PV[gName].value[0] += 1
            MgrInstance.PV[gName].timestamp = timestamp
            # start buzzer
            MgrInstance.PV['Buzz'].set_valueAndTimestamp(['1'], timestamp)
            MgrInstance.set_Buzz()
    MgrInstance.publish()

def buzzThread():
    # buzzing for a duration
    duration = MgrInstance.PV['BuzzDuration'].value[0]
    PiGPIO.write(GPIO['Buzz'], 1)
    time.sleep(duration)
    MgrInstance.publish1('Buzz', '0')
    PiGPIO.write(GPIO['Buzz'], 0)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#``````````````````Main````````````````````````````````````````````````````````
if __name__ == "__main__":
    # parse arguments
    import argparse
    parser = argparse.ArgumentParser(description=__doc__
    ,formatter_class=argparse.ArgumentDefaultsHelpFormatter
    ,epilog=f'senstation: {__version__}')
    parser.add_argument('-H','--dht', choices=['11','22'], help=\
    'Type of connected DHT sensor (humidity and temperature sensor)')
    parser.add_argument('-i','--interface', default = '', help=\
    'Network interface. Default is the interface, which connected to internet')
    n = 12000# to fit liteScaler volume into one chunk
    #parser.add_argument('-I','--I2C', help=\
    #('Comma separated list of I2C device_address, e.g. MMC5983MA_48,'
    #'ADS1115_72, ADS1015_72, HMC5883_30, QMC5883_13')),
    parser.add_argument('-m','--muxMask', default='11111111', help=\
    ('Mask of enabled channels of I2C multiplexer (if it is present).'
    'If 0 then all channels will be enabled but not processed'))
    parser.add_argument('-M','--muxAddr', type=int, help=\
    'I2C address of the multiplexer. If None then I2C will be disabled. If it did not find mux, then it will scan I2C bus for recognizable devices')
    parser.add_argument('-p','--port', type=int, default=9700, help=\
    'Serving port, default: 9700')
    parser.add_argument('-s','--serial', default = '', help=\
    'Comma separated list of serial devices to support, e.g.:OmegaBus')
    parser.add_argument('-1','--oneWire', action='store_true', help=\
    'Support OneWire device, DS18B20')
    parser.add_argument('-u','--update', type=float, default=1.0, help=\
    'Updating period')
    parser.add_argument('-v', '--verbose', action='count', default=0, help=\
      'Show more log messages (-vv: show even more).')
    pargs = parser.parse_args()
    pargs.muxMask = int(pargs.muxMask,2)
    liteserver.Server.Dbg = pargs.verbose
    init_gpio()

    if pargs.serial != '':
        import serial
        init_serial()

    MgrInstance = SensStation('dev1')
    devices = [MgrInstance]

    printi('Serving:'+str([dev.name for dev in devices]))

    server = liteserver.Server(devices, interface=pargs.interface,
        port=pargs.port)
    server.loop()
