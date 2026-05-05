"""liteserver for sensors at Raspberry Pi.
Supported:
  - 1-wire Temperature sensors DS18B20 (0.5'C resolution), (GPIO 4).
  - Temperature and Humidity sensors DHT11 and DHT22 (GPIO 23).
  - Digital IOs (in: 19,20, out: 25,24).
  - Pulse Counter (GPIO 26).
  - Spark/fire detector (GPIO 26).
  - Buzzer (GPIO 13).
  - RGB LED indicator (GPIO 22,27,17).
  - I2C devices: ADS1x15, MMC5983MA, HMC5883, QMC5983.
  - I2C mutiplexers TCA9548, PCA9546.
  - OmegaBus serial sensors.
"""
__version__ = '4.1.0 2026-05-04'# using lgpio instead of pigpio, which is more efficient and does not require a daemon.
# pylint: disable=invalid-name


print(f'senstation {__version__}')

import sys, time, threading, glob
timer = time.perf_counter
from functools import partial
#import numpy as np

from .. import liteserver
#`````````````````````````````Immutable Variables`````````````````````````````
Lock = threading.Lock()# for synchronizing access to shared variables in callbacks and threads
MgrInstance = None
LDO = liteserver.LDO
Device = liteserver.Device
GPIO = {
    'Temp0': (4,'in'),# 1-wire temperature sensor
    'eventOut': [12,'out'],# Generated when Event is detected
    'buzz': (13,'out'),
    'DI1':  (19,'in'),
    'DI0':  (20,'in'),
    'event': (26,'alert'),
    'rgb0': (22,'out'),
    'rgb1': (27,'out'),
    'rgb2': (17,'out'),
    'DO0':  (21,'out'),
    'DO1':  (25,'out'),
    'DO2':  (24,'out'),
    'DHT':  (23,'in'),
    'pulse': (16,'out'),# soft pulse generator
}
EventGPIO = {'event'} # event-generated GPIOs, store the time when it was last published
#CallbackMinimalPublishPeiod = 0.01
#MaxPWMRange = 1000000 # for hardware PWM0 and PWM1
Seldom_update_period = 10.# update period for slow-changing parameters like temperature and humidity

#``````````````````Mutable variables``````````````````````````````````````````
class _C:
    sbc = None
    GPIOchip = None
    omegaBus = None
#`````````````````````````````Helper methods``````````````````````````````````
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
    global measure_temperature
    try:
        import lgpio
        _C.sbc = lgpio
    except:
        print('ERROR. This server should run on Raspberry Pi and have the lgpio module installed.')
        sys.exit(1)
    _C.GPIOchip = _C.sbc.gpiochip_open(0) # open GPIO chip 0, which contains GPIOs 0-53

    # claim GPIOs direction
    for gpio,direction in GPIO.values():
        if direction == 'out':
            printi(f'claiming GPIO output for {gpio}')
            _C.sbc.gpio_claim_output(_C.GPIOchip, gpio)
        elif direction == 'in':
            printi(f'claiming GPIO input for {gpio}')
            _C.sbc.gpio_claim_input(_C.GPIOchip, gpio)
        elif direction == 'alert':
            printi(f'claiming GPIO alert for {gpio}')
            _C.sbc.gpio_claim_alert(_C.GPIOchip, gpio, _C.sbc.RISING_EDGE)
        else:
            print(f'Unknown direction {direction} for GPIO {gpio}')

    # Configure 1Wire pin
    #try:    _C.sbc.set_mode( GPIO['Temp0'][0], _C.sbc.INPUT)
    #except:
    #    printe('Did you start the pigpio daemon? E.g. sudo pigpiod')
    #    sys.exit()
    #_C.sbc.set_pull_up_down( GPIO['Temp0'][0], _C.sbc.PUD_UP)
    #_C.sbc.set_glitch_filter( GPIO['event'][0] , 500)# require it stable for 500 us

    #````````````````````````Service for DS18B20 thermometer
    # Check if OneWire (DS18B20) is connected
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
def init_serial():
    """ Initialize serial devices, e.g. OmegaBus. """
    try:
        if 'OmegaBus' in pargs.serial:
            _C.omegaBus = serial.Serial('/dev/ttyUSB0', 300)
            #_C.omegaBus.bytesize = 8
            _C.omegaBus.timeout = 1
            _C.omegaBus.write(b'$1RD\r\n')
            s = _C.omegaBus.read(100)
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
        self.pulseArgs = None
        self.buzzEvent = threading.Event()
        self.lastPublishedEvFreq = 0

        # Add I2C devices
        if pargs.muxAddr is not None:
            from liteserver.device import i2c
            self.I2C = i2c.I2C
            self.I2C.verbosity = pargs.verbose
            i2c.init(pargs.muxAddr, pargs.muxMask)
            ldos.update(self.I2C.LDOMap)

        lvDO = ['0','1','10','01','1010101010']
        ldos.update({
          'boardTemp':  LDO('R','Temperature of the Raspberry Pi', 0., units='C'),
          'cycle':      LDO('R', 'Cycle number', 0),
          'cyclePeriod':LDO('RWE', 'Cycle period', pargs.update, units='s'),
          'evFreqMean': LDO('R', f'Mean frequency of events, calculated averaged over {Seldom_update_period} s',
                            0., units='Hz'),
          #'evFreqStsd': LDO('R', f'Standard deviation of event frequency, calculated over {Seldom_update_period} s',
          #                  0., units='Hz'),        
          #'PWM0_Freq':  LDO('RWE', f'Frequency of PWM at GPIO {GPIO['PWM0'][0]}',
          #  10, units='Hz', setter=partial(self.set_PWM_frequency, 'PWM0'),
          #  opLimits=[0,125000000]),
          #'PWM0_Duty':  LDO('WE', f'Duty Cycle of PWM at GPIO {GPIO['PWM0'][0]}',
          #  .5, setter=partial(self.set_PWM_dutycycle, 'PWM0'),
          #  opLimits=[0.,1.]),
          'DI0':        LDO('R', f"Digital input GPIO {GPIO['DI0'][0]}",
            0),# getter=partial(self.getter,'DI0')),
          'DI1':        LDO('R', f"Digital input GPIO {GPIO['DI1'][0]}",
            0),# getter=partial(self.getter,'DI0')),
          'event':      LDO('R', f"Event counter of pulses on GPIO {GPIO['event'][0]}",
            0),
          'eventOut':   LDO('WE', f"GPIO to generate a pulse when event changes, currently {GPIO['eventOut'][0]}", 0,),
          'rgb':        LDO('RWE', f'3-bit digital output',
            0, opLimits=[0,7], setter=self.set_RGB),
          'rgbControl':    LDO('RWE', 'Mode of RGB',
            ['rgbCycle'], legalValues=['rgbStatic','rgbCycle']),
          'DO0':        LDO('RWE', f"Digital output GPIO {GPIO['DO0'][0]}, pattern of bits for multiple bits, e.g. 101 for 3 bits",
            '0', legalValues=lvDO, setter=partial(self.set_DO, 'DO0')),
          'DO1':    LDO('RWE', f"Digital output GPIO {GPIO['DO1'][0]}, pattern of bits for multiple bits, e.g. 101 for 3 bits",
            '0', legalValues=lvDO, setter=partial(self.set_DO, 'DO1')),
          'buzz':       LDO('RWE', f"Buzzer GPIO {GPIO['buzz'][0]}, activates when the event changes",
            'buzz_Off', legalValues=['buzz_On','buzz_Off'], setter=self.set_buzz),
          'buzzDuration': LDO('RWE', 'Buzz duration', 5., units='s'),
          'pulsePattern': LDO('RWE', f"Pattern of pulses at GPIO {GPIO['pulse'][0]}, e.g. [0.5, 0.4, 0.1] for 0.1s delay, 0.5s high, 0.4s low",
            [0.5, 0.4, 0.1], setter=partial(self.set_PulsePattern)),
          'nPulses': LDO('RWE', f"Number of pulses at GPIO {GPIO['pulse'][0]}", 1, setter=partial(self.set_PulsePattern)),
          'pulseTrigger': LDO('RWE', f"Trigger for pulse pattern at GPIO {GPIO['pulse'][0]}",
                              'OneShot', legalValues=['OneShot','Cyclic'], setter=partial(self.set_PulseTrigger)),
        })

        if pargs.oneWire:
            ldos['Temp0'] = LDO('R','Temperature of the DS18B20 sensor', 0.,
                units='C')
        if _C.omegaBus is not None:
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
            printi(f'setting callback for {eventParName} at GPIO {GPIO[eventParName][0]}')
            r = _C.sbc.callback(_C.GPIOchip, GPIO[eventParName][0], _C.sbc.RISING_EDGE, callback)
        self.start()

    #def self.pvv(parName):
    #    return self.PV[parName].value[0]

    #``````````````Overridables```````````````````````````````````````````````
    def start(self):
        printi('Senstation started')
        # invoke setters of all parameters, except 'run'
        for par,ldo in self.PV.items():
            setter = ldo._setter
            if setter is not None:
                if str(par) == 'run':
                    continue
                setter()
        thread = threading.Thread(target=self._threadRun, daemon=False)
        thread.start()

    def stop(self):
        printi(f"Senstation stopped {self.PV['cycle'].value[0]}")
        # prev = self.PV['PWM0_Duty'].value[0]
        # self.PV['PWM0_Duty'].value[0] = 0.
        # self.PV['PWM0_Duty']._setter()
        # self.PV['PWM0_Duty'].value[0] = prev
        self.PV['rgb'].value[0] = 0
        self.PV['rgb']._setter()# turn off RGB

    def set_clear(self):
        for parName,value in (('status',''), ('cycle',0), ('event',0)):
            self.PV[parName].value[0] = value
            self.PV[parName].timestamp = time.time()
        print('Clearing parameters')
        #self.publish()# Could deadlock
        #print('Parameters cleared')
        
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    def publish1(self, parName, value=None):
        """Publish a single parameter with an optional new value. If value is None, then the current value will be published.
        """
        if value is not None:
            try:
                self.PV[parName].value[0] = value
            except:
                self.PV[parName].value = value
        self.PV[parName].timestamp = time.time()
        self.publish()

    def gpiov(self, parName):
        """ Get GPIO number and value for a parameter name like 'DO0' or 'PWM0_Freq' """
        v = self.PV[parName].value[0]
        key = parName.split('_')[0]
        gpio = GPIO[key][0]
        printv(f'gpiov {gpio,v}')
        return gpio,v

    #``````````````Setters````````````````````````````````````````````````````
    # def set_PWM_frequency(self, pwm):
    #     parName = pwm + '_Freq'
    #     gpio, v = self.gpiov(parName)
    #     #r = _C.sbc.hardware_PWM(gpio, int(v))
    #     dutyCycle = int(MaxPWMRange*self.PV[pwm+'_Duty'].value[0])
    #     r = _C.sbc.hardware_PWM(gpio, int(v), dutyCycle)
    #     r = _C.sbc.get_PWM_frequency(gpio)
    #     self.publish1(parName, r)

    # def set_PWM_dutycycle(self, pwm):
    #     parName = pwm + '_Duty'
    #     gpio, v = self.gpiov(parName)
    #     f = int(self.PV[pwm + '_Freq'].value[0])
    #     printv(f'set_PWM_dutycycle: {f, int(v*MaxPWMRange)}')
    #     r = _C.sbc.hardware_PWM(gpio, f, int(v*MaxPWMRange))
    #     r = _C.sbc.get_PWM_dutycycle(gpio)
    #     self.publish1(parName, r/MaxPWMRange)

    def set_DO(self, parName):
        """ Set digital output GPIOs according to the parameter value, e.g. '101' for 3 bits. """
        gpio,v = self.gpiov(parName)
        for bit in v:
            #printv(f'set_DO {gpio,bit}')
            _C.sbc.gpio_write(_C.GPIOchip,gpio, int(bit))

    def set_buzz(self):
        """ Set the buzzer GPIO according to the parameter value. """
        printv(f'set_buzz: {self.PV["buzz"].value}')
        if self.PV['buzz'].value[0] == 'buzz_On':
            printv(f">set_buss for Buzz: {self.PV['buzzDuration'].value[0]} s")
            thread = threading.Thread(target=self.buzzThread, daemon=False)
            self.buzzEvent.clear()
            thread.start()
        else:
            self.buzzEvent.set()# in case it is still buzzing, stop it
    def buzzThread(self):
        """ Thread for buzzing, so that it does not block the main thread. """
        duration = self.PV['buzzDuration'].value[0]
        _C.sbc.gpio_write(_C.GPIOchip, GPIO['buzz'][0], 1)
        self.buzzEvent.wait(duration)
        self.publish1('buzz', 'buzz_Off')
        _C.sbc.gpio_write(_C.GPIOchip, GPIO['buzz'][0], 0)

    def set_RGB(self):
        """ Set RGB GPIOs according to the parameter value, e.g. 5 (0b101) for RGB0 and RGB2 on, RGB1 off. """
        v = int(self.PV['rgb'].value[0])
        for i in range(3):
            _C.sbc.gpio_write(_C.GPIOchip,GPIO[f'rgb{i}'][0], v&1)
            v = v >> 1

    def _trigger_PulsePattern(self):
        printv(f'>trigger_PulsePattern: {self.pulseArgs}')
        r = _C.sbc.tx_pulse(*self.pulseArgs)
        if r < 0:
            raise ResourceWarning('PWM queue full)')
    def set_PulseTrigger(self):
        self._trigger_PulsePattern()

    def set_PulsePattern(self):
        pattern = [int(i*1.e6) for i in self.PV['pulsePattern'].value]
        #printi(f'set_PulsePattern: {pattern}')
        if pattern[0] < 20 or pattern[1] < 20:
            raise ValueError('pulse pattern intervals should be at least 20 us')
        self.pulseArgs = [_C.GPIOchip, GPIO['pulse'][0]] + pattern + [self.PV['nPulses'].value[0]]
        self._trigger_PulsePattern()
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,

    def _threadRun(self):
        printi('threadRun started')
        timestamp = time.time()
        prevcurtime = timestamp
        last_seldom_update = 0
        self.prevCPUTempTime = 0.
        while not Device.EventExit.is_set():
            if self.PV['run'].value[0][:4] == 'Stop':
                break

            # check if it is time for seldom update, e.g. temperature and humidity, which do not need to be updated every cycle
            if  timestamp - last_seldom_update > Seldom_update_period:
                last_seldom_update = timestamp
                thread = threading.Thread(target=self.seldomThread)
                thread.start()

            # wait for next time interval
            curtime = time.time()
            dt = curtime - timestamp
            waitTime = self.PV['cyclePeriod'].value[0] - dt
            Device.EventExit.wait(waitTime)
            timestamp = time.time()

            # trigger pulse pattern if it is cyclic
            if self.PV['pulseTrigger'].value[0] == 'Cyclic':
                self._trigger_PulsePattern()

            # read GPIOs and I2C devices, update cycle counter and publish all fresh parameters
            if pargs.muxAddr is not None:
                for i2cDev in self.I2C.DeviceMap.values():
                    if True:#try:
                        i2cDev.read(timestamp)
                    else:#except Exception as e:
                        printw(f'Exception in threadRun: {e}')
                        continue
            self.PV['cycle'].value[0] += 1
            self.PV['cycle'].timestamp = timestamp
            if self.PV['rgbControl'].value[0] == 'rgbCycle':
                self.PV['rgb'].set_valueAndTimestamp(\
                    [self.PV['cycle'].value[0] & 0x7], timestamp)
                self.set_RGB()

            # publish all fresh parameters
            self.publish()

        printi('threadRun stopped')
        self.stop()

    def seldomThread(self):
        """ Thread for less frequent updates, e.g. temperature and humidity. """
        timestamp = time.time()

        # calculate mean frequency of events
        #print(f'>seldomThread: event count {self.PV["event"].value[0]}, lastPublishedEvFreq {self.lastPublishedEvFreq}')
        self.PV['evFreqMean'].value[0] = (self.PV['event'].value[0] - self.lastPublishedEvFreq) / Seldom_update_period
        self.PV['evFreqMean'].timestamp = timestamp
        self.lastPublishedEvFreq = self.PV['event'].value[0]

        # read CPU temperature, DHT sensor, OmegaBus, etc. and publish them
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

        # read OmegaBus if it is present
        if _C.omegaBus is not None:
            _C.omegaBus.write(b'$1RD\r\n')
            r = _C.omegaBus.read(100)
            #print(f'OmegaBus read: {r}')
            if len(r) != 0:
                self.PV['OmegaBus'].set_valueAndTimestamp([float(r.decode()[2:])/1000.])
        #print(f'<seldomThread time: {round(timer()-ts,6)}')

        # read DHT sensor if it is present
        if pargs.dht is not None:
            try:
                self.PV['Temperature'].set_valueAndTimestamp(pargs.dht.temperature)
                self.PV['Humidity'].set_valueAndTimestamp(pargs.dht.humidity)
                printv(f'T: {pargs.dht.temperature}, H: {pargs.dht.humidity}')
            except Exception as e:
                printw(f'in reading DHT: {e}')

    def set_status(self, msg):
        """ Set status message. """
        self.PV['status'].set_valueAndTimestamp(msg)

def write_eventOut(value):
    gpio = GPIO['eventOut'][0]
    if gpio >= 0:
        _C.sbc.gpio_write(_C.GPIOchip, gpio, value)

def callback(handle, gpio, level, tick):
    """ Callback function for GPIO events, e.g. pulse counter. """
    if True:#with Lock:
        write_eventOut(1)# generate a short pulse at eventOut GPIO to indicate that event was detected
        #print(f'callback: {gpio, level, tick}')
        timestamp = time.time()
        for gName in ['event']:
            if gpio == GPIO[gName][0]:
                # increment event counter and publish it
                MgrInstance.PV[gName].value[0] += 1
                MgrInstance.PV[gName].timestamp = timestamp
        MgrInstance.publish()
        write_eventOut(0)# generate a short pulse at eventOut GPIO to indicate that event was detected

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
    parser.add_argument('-i','--interface', default = '',
        choices=liteserver.ip_choices() + ['','localhost'], help=\
'Network address. Default is the addrees, which is connected to internet')
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
    liteserver.Server.Dbg = pargs.verbose-1
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
