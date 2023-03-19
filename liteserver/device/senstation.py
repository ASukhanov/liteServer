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
  - I2C devices: ADS1115, MMC5983MA, HMC5883, QMC5983
  - OmegaBus serial sensors
"""
__version__ = '2.0.2 2023-03-14'# exception handling in HMC5883.read()

#TODO: take care of microsecond ticks in callback
#TODO: HMC5883 calibration

print(f'senstation {__version__}')

import sys, time, threading, glob, struct
from timeit import default_timer as timer
from functools import partial
import numpy as np

from liteserver import liteserver

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
    'RGB':  [16,6,5],
    'DO3':  25,
    'DO4':  24,
    'DHT':  21,
}
EventGPIO = {'Counter0':0.} # event-generated GPIOs, store the time when it was last published
#CallbackMinimalPublishPeiod = 0.01
MaxPWMRange = 1000000 # for hardware PWM0 and PWM1

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
    import pigpio
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

#`````````````````````````````I2C Devices``````````````````````````````````````
# For installation: Installationhttps://www.instructables.com/Raspberry-Pi-I2C-Python/
# I2C speed: https://www.raspberrypi-spy.co.uk/2018/02/change-raspberry-pi-i2c-bus-speed/
import ctypes
c_uint16 = ctypes.c_uint16
c_uint8 = ctypes.c_uint8

I2CBus = 1 # Rpi I2C bus is 1
I2CSMBus = True
# If False: use pigpio wrappers for accessing I2C, overhead ~0.5ms/transaction
if I2CSMBus:
    try:
        import smbus as I2CSMBus
    except:
        printw('I2C access package is not available. Will be using PiGPIO I2C wrapper, which has ~0.5 ms overhead per transaction')
        I2CSMBus = False

class I2CDev():
    i2cMux = None
    def __init__(self, devAddr):
        self.devAddr = devAddr
        self.devName,addr = devAddr.split('_')
        self.addr = int(addr)

        if I2CSMBus == False:
            I2CDev.i2cMux = PiGPIO.i2c_open(I2CBus, 0x70)
            if I2CDev.i2cMux == 0:
                printw('I2C mux not found at address 0x70')
            self.devPiGPIO = PiGPIO.i2c_open(I2CBus, self.addr)
            if self.devPiGPIO == 0:
                raise RuntimeError(f'Could not open I2C device {devAddr}')
        else:
            self.devSMBUS = I2CSMBus.SMBus(I2CBus)
            printi(f'I2CSMBus opened: {devAddr} using smbus package')
        try:    self.write_i2cMux(int(pargs.mux,2))
        except:
            printw('I2C mux not found.')

    if I2CSMBus == False:
        def write_i2cMux(self, value):
            if I2CDev.i2cMux != 0:
                PiGPIO.i2c_write_byte_data(I2CDev.i2cMux, 0, value)
        def read_byte_data(self, reg):
            return PiGPIO.i2c_read_byte_data(self.devPiGPIO, reg)
        def read_word_data(self, reg):
            return PiGPIO.i2c_read_word_data(self.devPiGPIO, reg)
        def write_byte_data(self, reg, value):
            PiGPIO.i2c_write_byte_data(self.devPiGPIO, reg, value)
        def write_word_data(self, reg, value):
            PiGPIO.i2c_write_word_data(self.devPiGPIO, reg, value)
        def read_block_data(self, reg):
            return list(PiGPIO.i2c_read_block_data(self.devPiGPIO, reg)[1])
        def read_i2c_block_data(self, reg, count):
            return list(PiGPIO.i2c_read_i2c_block_data(self.devPiGPIO, reg, count)[1])
    else:
        def write_i2cMux(self, value):
            self.devSMBUS.write_byte_data(0x70, 0, value)
        def read_byte_data(self, reg):
            return self.devSMBUS.read_byte_data(self.addr, reg)
        def read_word_data(self, reg):
            return self.devSMBUS.read_word_data(self.addr, reg)
        def write_byte_data(self, reg, value):
            self.devSMBUS.write_byte_data(self.addr, reg, value)
        def write_word_data(self, reg, value):
            self.devSMBUS.write_word_data(self.addr, reg, value)
        def read_block_data(self, reg):
            return self.devSMBUS.read_block_data(self.addr, reg)
        def read_i2c_block_data(self, reg, count):
            return self.devSMBUS.read_i2c_block_data(self.addr, reg, count)

    def read(self, timestamp):
        print(f'I2CDev.read() not implemented for {self.devName}')
        return

#```````````````````HMC5883 compass`````````````````````````````````````````````
class HMC5883_bits_ConfigRegA(ctypes.LittleEndianStructure):
    _fields_ = [
        ("MS", c_uint8, 2),# Measurement Configuration Bits.
        ("DO", c_uint8, 3),# Data Output Rate.
        ("MA", c_uint8, 2),]# Moving average. 0=1, 1=2, 2=4, 3=8.
class HMC5883_ConfigRegA(ctypes.Union):
    _fields_ = [("b", HMC5883_bits_ConfigRegA),
               ("B", c_uint8),]
    addr = 0
class HMC5883_bits_ConfigRegB(ctypes.LittleEndianStructure):
    _fields_ = [
        ("O",   c_uint8, 5),# Zeroes.
        ("FSR", c_uint8, 3),]# Gain,
class HMC5883_ConfigRegB(ctypes.Union):
    _fields_= [("b", HMC5883_bits_ConfigRegB),
               ("B", c_uint8),]
    addr = 1
class HMC5883_bits_ModeReg(ctypes.LittleEndianStructure):
    _fields_ = [
        ("Mode", c_uint8, 2),# Mode. 0=Continuous, 1=SingleShot, 2,3=Idle
        ("O",   c_uint8, 5),# Zeroes.
        ("HS",  c_uint8, 1),]# High Speed I2C, 3400 Hz 
class HMC5883_ModeReg(ctypes.Union):
    _fields_= [("b", HMC5883_bits_ModeReg),
               ("B", c_uint8),]
    addr = 2
class I2C_HMC5883(I2CDev):
    mode = 1# Measurement mode 0:continuous, 1:Single.
    def __init__(self, devAddr):
        super().__init__(devAddr)
        try:    devId = self.read_i2c_block_data(0x0a, 3)
        except:
            printe(f'There is no device with address {self.addr}')
            sys.exit()
        if devId != [0x48, 0x34, 0x33]:
            raise RuntimeError(f'Chip is not HMC5883L: {[hex(i) for i in devId]}')
        printi(f'Sensor detected: {self.devName,self.addr}')

        # Initialize HMC5883
        ##self.write_byte_data(0x00, 0xF8)  # CRA 75Hz.
        self.configRegA = HMC5883_ConfigRegA()
        #self.configRegA.B = self.read_byte_data(self.configRegA.addr)
        self.configRegA.b.DO = 4# Data rate 4: 15 Hz, 5:30, 6:75
        self.configRegA.b.MA = 3# Average window, 3: 8 samples
        self.write_byte_data(self.configRegA.addr, self.configRegA.B)
        #
        self.configRegB = HMC5883_ConfigRegB()
        self.configRegB.B = self.read_byte_data(self.configRegB.addr)
        self.configRegB.b.O = 0
        self.write_byte_data(self.configRegA.addr, self.configRegB.B)
        #
        self.modeReg = HMC5883_ModeReg()
        self.modeReg.B = self.read_byte_data(self.modeReg.addr)
        self.write_byte_data(self.modeReg.addr, I2C_HMC5883.mode)

        #SelfTest self.lastSelfTest = [0]*3# X,Y,Z of last calibration
        #SelfTest self.correction = [1.]*3# Correction, 

        lvFSR = (0.88, 1.3, 1.9, 2.5, 4.0, 4.7, 5.6, 8.1)
        self.pPV = {
        devAddr+'_FSR': LDO('WE','Full scale range is [-FSR:+FSR]',
            lvFSR[self.configRegB.b.FSR], legalValues=lvFSR, units='G',
            setter=self.set_FSR),
        #devAddr+'_DR': LDO('WE','Data rate', 75., units='G',
        #    legalValues=(0.75, 1.5, 3, 7.5, 15, 30, 75), setter=self.set_DR),
        #SelfTest devAddr+'_calibrate': LDO('WE','Calibrate sensor', None),
        devAddr+'_X': LDO('R','X-axis field', 0., units='G'),
        devAddr+'_Y': LDO('R','Y-axis field', 0., units='G'),
        devAddr+'_Z': LDO('R','Z-axis field', 0., units='G'),
        devAddr+'_M': LDO('R','Magnitude', 0., units='G'),
        }
        print(f'Created  MMC5983MA:{self.addr}')

    def set_FSR(self):
        pv = self.pPV[self.devAddr+'_FSR']
        self.fsr = pv.value[0]
        idx = pv.legalValues.index(self.fsr)
        self.configRegB.b.FSR = idx
        #print(f'configRegB: {self.configRegB.addr, self.configRegB.B}')
        self.write_byte_data(self.configRegB.addr, self.configRegB.B)

    def read(self, timestamp):
        if I2C_HMC5883.mode == 1:   # Single measurement
            self.write_byte_data(self.modeReg.addr, I2C_HMC5883.mode)
            ts = time.time()
            while self.read_byte_data(0x9) & 1 == 0:
                if time.time() - ts > 0.005:# should last ~1ms
                    printw('Timeout reading HMC5883')
                    return
        # 0x3 = X MSB, 0x4 = X LSB
        # 0x5 = Y MSB, 0x6 = Y LSB
        # 0x7 = Z MSB, 0x8 = Z LSB
        try:
            r = self.read_i2c_block_data(0x03, 6)
        except Exception as e:
            printw(f'in I2C_HMC5883.read: {e}')
            return
        x,y,z = struct.unpack('>3h', bytearray(r))
        ovf = -4096
        g = self.fsr/2048
        x = 10. if x == ovf else round(x*g,6)
        y = 10. if y == ovf else round(y*g,6)
        z = 10. if z == ovf else round(z*g,6)
        m = 10. if max(x,y,z) == 10. else round(np.sqrt(x**2 + y**2 + z**2),6)
        da = self.devAddr
        self.pPV[da+'_X'].set_valueAndTimestamp(x, timestamp)
        self.pPV[da+'_Y'].set_valueAndTimestamp(y, timestamp)
        self.pPV[da+'_Z'].set_valueAndTimestamp(z, timestamp)
        self.pPV[da+'_M'].set_valueAndTimestamp(m, timestamp)

#```````````````````QMC5883L compass`````````````````````````````````````````````
class QMC5883_bits_ConfigRegA(ctypes.LittleEndianStructure):
    _fields_ = [
        ("MODE", c_uint8, 2),#Mode 0:StandBy, 1:Continuous
        ("DO", c_uint8, 2),  #Data Output Rate, 0:10 Hz, 1:50, 2:100, 3:200
        ("FSR", c_uint8, 2), #Full scale range, 0:2G, 1:8G
        ("OSR", c_uint8, 2),]#Over sample ratio, 512,256,128,64
class QMC5883_ConfigRegA(ctypes.Union):
    _fields_ = [("b", QMC5883_bits_ConfigRegA),
               ("B", c_uint8),]
    addr = 0x9
class I2C_QMC5883(I2CDev):
    mode = 1# Measurement mode 1:continuous
    def __init__(self, devAddr):
        super().__init__(devAddr)
        try:    devId = self.read_byte_data(0x0d)
        except:
            printe(f'There is no device with address {self.addr}')
            sys.exit()
        if devId != 0xff:
            raise RuntimeError(f'Chip is not QMC5883L: {[hex(i) for i in devId]}')
        printi(f'Sensor detected: {self.devName,self.addr}')

        # Initialize QMC5883
        self.configRegA = QMC5883_ConfigRegA()
        self.configRegA.b.MODE = I2C_QMC5883.mode
        self.configRegA.b.DO = 0# 10Hz. No effect.
        self.configRegA.b.FSR = 0# 2G
        self.configRegA.b.OSR = 0# OverSampling = 256. Less noise
        self.write_byte_data(self.configRegA.addr, self.configRegA.B)

        lvFSR = (2., 8.)
        self.pPV = {
        devAddr+'_FSR': LDO('WE','Full scale range is [-FSR:+FSR]',
            lvFSR[self.configRegA.b.FSR], legalValues=lvFSR, units='G',
            setter=self.set_FSR),
        devAddr+'_X': LDO('R','X-axis field', 0., units='G'),
        devAddr+'_Y': LDO('R','Y-axis field', 0., units='G'),
        devAddr+'_Z': LDO('R','Z-axis field', 0., units='G'),
        devAddr+'_M': LDO('R','Magnitude', 0., units='G'),
        devAddr+'_T': LDO('R','Relative temperature', 0., units='C'),
        }
        print(f'Created  MMC5983MA:{self.addr}')

    def set_FSR(self):
        pv = self.pPV[self.devAddr+'_FSR']
        self.fsr = pv.value[0]
        idx = pv.legalValues.index(self.fsr)
        self.configRegA.b.FSR = idx
        #print(f'fsr: {self.fsr,idx}')
        #print(f'configRegA: {self.configRegA.addr, self.configRegA.B}')
        self.write_byte_data(self.configRegA.addr, self.configRegA.B)

    def read(self, timestamp):
        pv = {'X':0., 'Y':0., 'Z':0., 'M':0.,'T':0.}
        # note: reading more than 6 bytes may give wrong result when cable is long
        try:
            r = self.read_i2c_block_data(0x00, 6)
        except Exception as e:
            printw(f'in I2C_QMC5883.read: {e}')
            return
        #printv(f'conf,status: {hex(r[0x9]), hex(r[0x6])}')
        #printv(f'read: {[hex(i) for i in r]}')
        g = self.fsr/32768.
        xyz = struct.unpack('<3h', bytearray(r[:6]))
        pv['X'],pv['Y'],pv['Z'] = [round(g*i,6) for i in xyz]
        pv['M'] = round(np.sqrt(pv['X']**2 + pv['Y']**2 +pv['Z']**2), 6)
        #t = self.read_word_data(0x07)
        r = self.read_i2c_block_data(0x07, 2)
        pv['T'] = round(struct.unpack('<h', bytearray(r))[0]/100. + 30.,2)
        #print(f"pvT: {pv['T']}")
        for suffix,value in pv.items():
            self.pPV[self.devAddr+'_'+suffix].set_valueAndTimestamp(value, timestamp)

#```````````````````MMC5983MA compass```````````````````````````````````````````
class I2C_MMC5983MA(I2CDev):
    cm_freq = 0x0# Continuous mode, frequency=1Hz
    FSR = 8# Full scale range in Gauss
    def __init__(self, devAddr):
        super().__init__(devAddr)
        devID = self.read_byte_data(0x2f)
        sensStatus = self.read_byte_data(0x8)
        print(f'sensStatus: {sensStatus}')
        if sensStatus&0x10 == 0:
            raise RuntimeError('Chip could not read its memory')
        if devID != 0x30:
            raise RuntimeError(f'MMC5983 has wrong address: {devID}')
        printi(f'MMC5983MA ID: {devID}')
        print(f'Sensor detected: {self.devName,self.addr}')
        self.write_byte_data(0x9, 0x0)
        self.write_byte_data(0xa, 0x3)
        self.write_byte_data(0xb, I2C_MMC5983MA.cm_freq)
        self.write_byte_data(0xc, 0x0)

        self.pPV = {
        devAddr+'_X': LDO('R','X-axis field', 0., units='G'),
        devAddr+'_Y': LDO('R','Y-axis field', 0., units='G'),
        devAddr+'_Z': LDO('R','Z-axis field', 0., units='G'),
        devAddr+'_M': LDO('R','Magnitude', 0., units='G'),
        devAddr+'_T': LDO('R','Sensor temperature', 0., units='C'),
        }
        print(f'Created  MMC5983MA:{self.addr}')

    def read(self, timestamp):
        pv = {'X':0., 'Y':0., 'Z':0., 'M':0.,'T':0.}
        da = self.devAddr
        if I2C_MMC5983MA.cm_freq == 0:
            self.write_byte_data(0x09,0x2)
            time.sleep(0.01)
        t = self.read_byte_data(0x7)
        #printv(f't: {hex(t)}')
        pv['T']= round(-75. + t*0.8,2)
        if I2C_MMC5983MA.cm_freq == 0:
            self.write_byte_data(0x09,0x1)
            time.sleep(0.01)
        v = self.read_byte_data(0x8)
        try:
            r = self.read_i2c_block_data(0x00, 7)
        except Exception as e:
            printw(f'in I2C_HMC5883.read: {e}')
            return
        #TODO: extract 18-bit precision from r[7]
        #printv(f'r: {[hex(i) for i in r]}')
        pv['X'],pv['Y'],pv['Z'] = [round((i/0x8000-1.)*I2C_MMC5983MA.FSR,6)\
            for i in struct.unpack('>3H', bytearray(r[:6]))]
        pv['M'] = round(np.sqrt(pv['X']**2 + pv['Y']**2 +pv['Z']**2), 6)
        #printv(f">read {da}, CTRL0: {hex(v)}, xyzmt:{pv.values()}")
        for suffix,value in pv.items():
            self.pPV[self.devAddr+'_'+suffix].set_valueAndTimestamp(value, timestamp)

#```````````````````ADS1115, ADS1015```````````````````````````````````````````
# 4-channel 16/12 bit ADC.
# Sampling time of 4 channels = 14ms.
class ADS1115_bits_ConfigReg(ctypes.LittleEndianStructure):
    _fields_ = [
        ("MODE", c_uint16, 1),
        ("FSR", c_uint16, 3),
        ("MUX",c_uint16, 3),
        ("OS",c_uint16, 1),
        ("COMP_QUE", c_uint16, 2),
        ("COMP_LAT", c_uint16, 1),
        ("COMP_POL", c_uint16, 1),
        ("COMP_MODE", c_uint16, 1),
        ("DR", c_uint16, 3),]
class ADS1115_ConfigReg(ctypes.Union):
    _fields_ = [("b", ADS1115_bits_ConfigReg),
               ("W", c_uint16),]
ADS1115_SingleShot = 1# 1: Single-shot, 0: Continuous conversion
class I2C_ADS1115(I2CDev):
    def __init__(self, devAddr, model='ADS1115'):
        super().__init__(devAddr)
        self.config = ADS1115_ConfigReg()
        self.config.W = self.read_word_data(1)
        self.config.b.MODE = ADS1115_SingleShot
        self.write_word_data( 1, self.config.W )
        lvFSR = (6.144,4.096,2.048,1.024,0.512,0.256)
        lvDR = {'ADS1115': (8,     16,   32,   64,  128,  250,  475,  860),
                'ADS1015': (128,  250,  490,  920, 1600, 2400, 3300, 3300)}
        self.pPV = {
        devAddr+'_rlength': LDO('RWE', 'Record length, ', 1),
        devAddr+'_tAxis': LDO('R', 'Time axis for samples', [0.], units='s'),
        devAddr+'_nCh': LDO('RWE', 'Number of active ADC channels. Select 1 for faster performance.',
            4, legalValues=[4,1]),
        devAddr+'_diff': LDO('RWE', 'Differential mode, Ch0=AIN0-AIN1, Ch1=AIN2-AIN3', 'Single-ended', legalValues=['Single-ended','Diff']),
        devAddr+'_Ch0': LDO('R', 'ADC channel 0', [0.], units='V'),
        devAddr+'_Ch1': LDO('R', 'ADC channel 1', [0.], units='V'),
        devAddr+'_Ch2': LDO('R', 'ADC channel 2', [0.], units='V'),
        devAddr+'_Ch3': LDO('R', 'ADC channel 3', [0.], units='V'),
        devAddr+'_FSR': LDO('RWE', 'FSR, Full scale range is [-FSR:+FSR]',
            lvFSR[self.config.b.FSR], legalValues=lvFSR, units='V',
            setter=partial(self.set_pv,'FSR')),
        devAddr+'_DR': LDO('RWE', 'Data rate',
            lvDR[model][self.config.b.DR], units='SPS',
            legalValues=lvDR[model], setter=partial(self.set_pv, 'DR')),
        }
        '''The following parts are handled internally
        devAddr+'_MODE': LDO('RWE', 'Device operating mode', self.config.b.MODE,
            opLimits=(0,1), setter=partial(self.set_pv, 'MODE')),
        devAddr+'_MUX': LDO('RWE', 'Input multiplexer config', self.config.b.MUX,
            opLimits=(0,7), setter=partial(self.set_pv,'MUX')),
        devAddr+'_OS': LDO('RWE', 'Operational status, 0:conversion in progress',
            self.config.b.OS,
            opLimits=(0,1), setter=partial(self.set_pv, 'OS')),
        devAddr+'_COMP_QUE': LDO('RWE', 'Comparator queue',
            self.config.b.COMP_QUE,
            opLimits=(0,2), setter=partial(self.set_pv, 'COMP_QUE')),
        devAddr+'_COMP_LAT': LDO('RWE', 'Latching comparator',
            self.config.b.COMP_LAT,
            opLimits=(0,1), setter=partial(self.set_pv, 'COMP_LAT')),
        devAddr+'_COMP_POL': LDO('RWE', 'Comparator polarity, active high',
            self.config.b.COMP_POL,
            opLimits=(0,1), setter=partial(self.set_pv, 'COMP_POL')),
        devAddr+'_COMP_MODE': LDO('RWE', 'Window comparator',
            self.config.b.COMP_MODE,
            opLimits=(0,1), setter=partial(self.set_pv, 'COMP_MODE')),
        '''
        printi(f'Created  {model}_{self.addr}')

    def read(self, timestamp):
        def wait_conversion():
            tswc = time.time()
            if self.config.b.MODE == 1:# in Single-shot mode: wait when OS bit = 1
                while True:
                    self.config.W = self.read_word_data(1)
                    if self.config.b.OS == 1:
                        break
                    if time.time() - tswc > .2:
                        raise TimeoutError('Timeout in I2C_ADS1115')
            else:
                # in continuous mode the OS is always 1, wait approximately one conversion period. 
                sleepTime = max(0, 1./(self.pPV[self.devAddr+'_DR'].value[0])\
                 - 0.0013)# 1.3ms is correction for transaction time
                time.sleep(sleepTime)
            v = self.read_word_data(0)
            v = int(((v&0xff)<<8) + ((v>>8)&0xff))# swap bytes
            if v & 0x8000:  v = v - 0x10000
            v = v/0x10000*self.pPV[da+'_FSR'].value[0]*2.
            return v

        self.config.W = self.read_word_data(1)
        da = self.devAddr
        nCh = self.pPV[da+'_nCh'].value[0]
        if self.pPV[da+'_diff'].value[0].startswith('Diff'):
            listCmd = [(0,'_Ch0'), (3,'_Ch1')]
        else:
            listCmd = [(4,'_Ch0'), (5,'_Ch1'), (6,'_Ch2'), (7,'_Ch3')]
        # set mux for first item of the list
        self.config.b.MUX = listCmd[0][0]
        self.config.b.MODE = 0 if nCh == 1 else ADS1115_SingleShot
        self.write_word_data( 1, self.config.W )

        # init the sample data
        nSamples = self.pPV[self.devAddr+'_rlength'].value[0]
        self.pPV[da+'_tAxis'].value = [0.]*nSamples
        for mux,ch in listCmd[:nCh]:
            self.pPV[da+ch].value = [0.]*nSamples
        t0 = time.time()
        #ts = timer(), #tt = []

        # collect samples
        for sample in range(nSamples):
            for mux,ch in listCmd[:nCh]:
                if nCh > 1:
                    self.config.b.MUX = mux
                    self.write_word_data( 1, self.config.W)
                #tt.append(round(timer()-ts,6))
                v = wait_conversion()
                self.pPV[da+ch].value[sample] = v
            self.pPV[da+'_tAxis'].value[sample] = round(time.time() - t0,6)

        # invalidate timestamps to schedule PVs for publishing
        for mux,ch in listCmd[:nCh]:
            self.pPV[da+ch].timestamp = timestamp
        self.pPV[da+'_tAxis'].timestamp = timestamp
        #tt.append(round(timer()-ts,6))
        #print(f'read time: {tt}')

    def set_pv(self, field):
        pv = self.pPV[self.devAddr+'_'+field]        
        #print(f'>set_config {pv.name} = {pv.value[0]}')
        self.config.W = self.read_word_data(1)
        #print(f'current: {hex(self.config.W)}')
        try:    v = pv.legalValues.index(pv.value[0])
        except: v = pv.value[0]
        setattr(self.config.b, field, v)
        #print(f'new: {hex(self.config.W)}')
        self.write_word_data( 1, self.config.W)

class I2C_ADS1015(I2C_ADS1115):
    def __init__(self, devAddr):
        print(f'>I2C_ADS1015')
        super().__init__(devAddr, 'ADS1015')

#````````````````````````````liteserver methods````````````````````````````````
class SensStation(Device):
    """ Derived from liteserver.Device.
    Note: All class members, which are not process variables should 
    be prefixed with _"""
    def __init__(self,name):
        pars = {}
        self.i2cDev = {}
        if pargs.I2C is not None: # create I2C devices and adopt their PVs
            devClassMap = {'MMC5983MA':I2C_MMC5983MA,
                'ADS1115':I2C_ADS1115, 'ADS1015':I2C_ADS1015,
                'HMC5883':I2C_HMC5883, 'QMC5883':I2C_QMC5883
                }
            for devAddr in pargs.I2C.split(','):
                devName,address = devAddr.split('_')
                devClass = devClassMap.get(devName)
                if devClass is None:
                    raise RuntimeError(f'I2C device {devName} not supported')
                dev = devClass(devAddr)
                self.i2cDev[devAddr] = dev
                devPars = dev.pPV
                pars.update(self.i2cDev[devAddr].pPV)
            printv(f'I2C pars: {pars.keys()}')
        pars.update({
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
          'Buzz':       LDO('RWE', f'Buzzer at GPIO {GPIO["Buzz"]}, activates when the Counter0 changes',
            '0', legalValues=['0','1'], setter=self.set_Buzz),
          'BuzzDuration': LDO('RWE', f'Buzz duration', 5., units='s'),
        })
        if pargs.oneWire:
            pars['Temp0'] = LDO('R','Temperature of the DS18B20 sensor', 0.,     units='C'),
        if 'OmegaBus' in pargs.serial:
            pars['OmegaBus'] = LDO('R','OmegaBus reading', 0., units='V')
        
        super().__init__(name,pars)

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
        periodic_update = timestamp
        self.prevCPUTempTime = 0.
        while not Device.EventExit.is_set():
            if self.PV['run'].value[0][:4] == 'Stop':
                break
            waitTime = self.PV['cyclePeriod'].value[0] - (time.time() - timestamp)
            Device.EventExit.wait(waitTime)
            timestamp = time.time()
            for i2cDev in self.i2cDev.values():
                if True:#try:
                    i2cDev.read(timestamp)
                else:#except Exception as e:
                    printw(f'Exception in threadRun: {e}')
                    continue
            self.PV['cycle'].value[0] += 1
            self.PV['cycle'].timestamp = timestamp
            if self.PV['RGBControl'].value[0] == 'RGBCycle':
                self.PV['RGB'].set_valueAndTimestamp(\
                    [self.PV['cycle'].value[0] & 0x7], timestamp)
                self.set_RGB()
            self.publish()# publish all fresh parameters

            # do a less frequent tasks in a thread
            dt = timestamp - periodic_update
            if dt > 10.:
                periodic_update = timestamp
                thread = threading.Thread(target=self.seldomThread)
                thread.start()
        printi('threadRun stopped')
        self.stop()

    def seldomThread(self):
        #print(f'>seldomThread: {timestamp}')
        #ts = timer()
        ctime = time.time()
        try:
            if ctime - self.prevCPUTempTime > 60.:
                self.prevCPUTempTime = ctime
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
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#``````````````````Man````````````````````````````````````````````````````````
if __name__ == "__main__":
    # parse arguments
    import argparse
    parser = argparse.ArgumentParser(description=__doc__
    ,formatter_class=argparse.ArgumentDefaultsHelpFormatter
    ,epilog=f'senstation: {__version__}')
    parser.add_argument('-i','--interface', default = '', help=\
    'Network interface. Default is the interface, which connected to internet')
    n = 12000# to fit liteScaler volume into one chunk
    parser.add_argument('-I','--I2C', help=\
    ('Comma separated list of I2C device_address, e.g. MMC5983MA_48,'
    'ADS1115_72, ADS1015_72, HMC5883_30, QMC5883_13')),
    parser.add_argument('-m','--mux', default='11111111', help=\
    'I2C mutiplexer setting, mask of channels to enable')
    parser.add_argument('-p','--port', type=int, default=9700, help=\
    'Serving port, default: 9700')
    parser.add_argument('-s','--serial', default = '', help=\
    'Comma separated list of serial devices to support, e.g.:OmegaBus')
    parser.add_argument('-1','--oneWire', action='store_true', help=\
    'Support OneWire device, DS18B20')
    parser.add_argument('-u','--update', type=float, default=1.0, help=\
    'Updating period')
    parser.add_argument('-v','--verbose', nargs='*', help=\
        'Show more log messages, (-vv: show even more).')
    pargs = parser.parse_args()
    pargs.verbose = 0 if pargs.verbose is None else len(pargs.verbose)+1
    print(f'pargs.I2C: {pargs.I2C}')

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
