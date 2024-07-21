"""`````````````````````````````Access to I2C bus``````````````````````````
For installation: https://www.instructables.com/Raspberry-Pi-I2C-Python/
I2C speed: https://www.raspberrypi-spy.co.uk/2018/02/change-raspberry-pi-i2c-bus-speed/
"""
__version__ = 'v3.2.6 2024-05-09'# MMC5983 more efficient sampling, PSD added, continuous mode
print(f'i2c: {__version__}')
#TODO: display errors and warnings in device status
#TODO: the DevClassMap should be incorporated into I2C class
#TODO: deal with overflows

import sys, time
timer = time.perf_counter
import struct
from functools import partial
import numpy as np
from scipy import signal
import ctypes
c_uint16 = ctypes.c_uint16
c_uint8 = ctypes.c_uint8

#import smbus as I2CSMBus
from smbus2 import SMBus as I2CSMBus

from liteserver.liteserver import LDO

#`````````````````````````````Helper methods```````````````````````````````````
from . import helpers
def printi(msg):    helpers.printi(msg)
def printe(msg):    helpers.printe(msg)
def printw(msg):    helpers.printw(msg)
def printv(msg):    helpers.printv(msg, I2C.verbosity)
def printvv(msg):   helpers.printv(msg, I2C.verbosity, level=1)

def tosigned12(n:int):
    n = n & 0xfff
    return (n ^ 0x800) - 0x800

X,Y,Z,M = 0,1,2,3
seldomUpdate = 60.# period for slow-changing parameters. e.g. temperature

class I2C():
    """Static class with I2C access methods."""
    verbosity = 0# 1: Show log messages, 2: show even more.
    DeviceClassMap = {}# Map of device classes: {addr: DeviceClass,,,,}
    # filled by add_deviceClasses()
    DeviceMap = {}# Map of existing devices: {(muxCh,addr): DeviceClass,...}
    LDOMap = {}# Map of Process Variables of I2C devices, filled by init()
    # filled by init()
    muxAddr = 0x77# address of the multiplexer on I2C bus
    busMask = 0xFF# bit-mask of enabled sub-busses
    I2CBus = 1 # Rpi I2C bus is 1
    CurrentMuxCh = None
    # Note: pigpio wrappers for accessing I2C have overhead ~0.5ms/transaction
    SMBus = I2CSMBus(I2CBus)

    def write_i2cMux(value):
        if I2C.muxAddr is None:
            return
        try:
            printv(f'write_i2cMux: {value}')
            I2C.SMBus.write_byte_data(I2C.muxAddr, 0, value)
            if value == 0:
                printi('Mux is Reset (set to 0).')
        except Exception as e:
            printw((f'There is no I2C mux at {I2C.muxAddr}: {e},\n'
            ' Only directly visible devices will be served'))
            I2C.muxAddr = None
    def enable_i2cMuxChannel(ch:int):
        #print(f'enable_i2c mux {ch}, current: {I2C.CurrentMuxCh}')
        if ch == 0:
            I2C.write_i2cMux(0)
        elif ch != I2C.CurrentMuxCh:
            I2C.write_i2cMux(1<<(ch-1))
        I2C.CurrentMuxCh = ch
    def read_i2c_byte(addr:tuple, reg:int):
        #print(f'read_i2c_byte: {addr, reg}')
        I2C.enable_i2cMuxChannel(addr[0])
        return I2C.SMBus.read_byte_data(addr[1], reg)
    def read_i2c_word(addr:tuple, reg:int):
        #print(f'read_i2c_word: {addr, reg}')
        I2C.enable_i2cMuxChannel(addr[0])
        return I2C.SMBus.read_word_data(addr[1], reg)
    def write_i2c_byte(addr:tuple, reg:int, value:int):
        #print(f'write_i2c_byte: {addr,reg,value}')
        I2C.enable_i2cMuxChannel(addr[0])
        I2C.SMBus.write_byte_data(addr[1], reg, value)
    def write_i2c_word(addr:tuple, reg, value):
        #print(f'write_i2c_word: {addr,reg,value}')
        I2C.enable_i2cMuxChannel(addr[0])
        I2C.SMBus.write_word_data(addr[1], reg, value)
    def read_i2c_data(addr:tuple, reg:int, count=None):
        #print(f'read_i2c_data: {addr, reg, count}')
        I2C.enable_i2cMuxChannel(addr[0])
        if count is None:
            return I2C.SMBus.read_block_data(addr[1], reg)
        else:
            return I2C.SMBus.read_i2c_block_data(addr[1], reg, count)

class I2CDev():
    """Base class for I2C devices"""
    def __init__(self, addr:tuple, sensorType:str, model):
        # addr is (mux channel, address on mux channel) 
        #self.name = self.__class__.__name__+'_'+'.'.join([str(i) for i in addr])
        self.name = f'I2C{addr[0]}'
        self.addr = addr
        self.model = model
        self.lastSeldomUpdate = 0.
        self.devLDO = {
            self.name+'_sensor': LDO('R','Sensor model and type',
              f'{model} {sensorType}'),
            self.name+'_readout': LDO('R','Readout time', 0., units='s'),
        }

    def read(self, timestamp):
        print(f'I2CDev.read() not implemented for {self.name}')
        return

    def ldoValue(self, name):
        # return value of the ldo
        return self.devLDO[self.name+name].value

#```````````````````HMC5883 compass````````````````````````````````````````````
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
    mode = 0# Measurement mode 0:continuous, 1:Single.
    def __init__(self, devAddr):
        super().__init__(devAddr, 'Magnetometer', 'HMC5883L')
        self.dataRange = (-2048,2047)#
        try:
            devId = I2C.read_i2c_data(self.addr, 0x0a, 3)
        except:
            printe(f'There is no device with address {self.addr}')
            sys.exit()
        if devId != [0x48, 0x34, 0x33]:
            raise RuntimeError(f'Chip is not HMC5883L: {[hex(i) for i in devId]}')

        # Initialize HMC5883
        self.configRegA = HMC5883_ConfigRegA()
        self.configRegA.b.DO = 4# Data rate 4: 15 Hz, 5:30, 6:75
        self.configRegA.b.MA = 3# Average window, 3: 8 samples
        self.configRegA.b.MS = 0# Normal Measurements
        I2C.write_i2c_byte(self.addr, self.configRegA.addr, self.configRegA.B)
        #
        self.configRegB = HMC5883_ConfigRegB()
        self.configRegB.B = I2C.read_i2c_byte(self.addr, self.configRegB.addr)
        self.configRegB.b.O = 0
        self.configRegB.b.FSR = 7
        I2C.write_i2c_byte(self.addr, self.configRegB.addr, self.configRegB.B)
        #
        self.modeReg = HMC5883_ModeReg()
        self.modeReg.B = I2C.read_i2c_byte(self.addr, self.modeReg.addr)
        I2C.write_i2c_byte(self.addr, self.modeReg.addr, I2C_HMC5883.mode)

        gain = (1370, 1090, 820, 660, 440, 390, 330, 230) #Lsb/Gauss
        lvFSR = [str(round(self.dataRange[1]/g,3)) for g in gain]
        # field strength of the excitation strap on X,Y,Z axes
        self.testField = (1.16, 1.16, 1.08)
        self.gainCorrection = [1., 1., 1.]
        self.correct = False
        self.xzySumCount = 0
        self.xzySum = np.zeros(3)

        n = self.name
        self.devLDO.update({
            n+'_FSR': LDO('WE','Full scale range is [-FSR:+FSR]',
                [lvFSR[self.configRegB.b.FSR]], legalValues=lvFSR, units='G',
                setter=self.set_FSR),
            n+'_Calibration':LDO('RWE', 'Calibrate attached sensor.', ['Off'],
                legalValues=['On','Off','Periodic','SelfTest'],
                setter=self.set_calibration),
            n+'_samples': LDO('RWE','Number of samples', [1]),
            n+'_X': LDO('R','X-axis field', 0., units='G'),
            n+'_Y': LDO('R','Y-axis field', 0., units='G'),
            n+'_Z': LDO('R','Z-axis field', 0., units='G'),
            n+'_M': LDO('R','Magnitude', 0., units='G'),
        })
        printv(f'CRA: {hex(I2C.read_i2c_byte(self.addr, self.configRegA.addr))}')
        printv(f'Sensor HMC5883 detected: {self.name,self.addr}')

    def _set_FSR(self, idx:int):
        self.configRegB.b.FSR = idx
        #print(f'>configRegB: {self.configRegB.addr, self.configRegB.B}')
        I2C.write_i2c_byte(self.addr, self.configRegB.addr, self.configRegB.B)
        r = I2C.read_i2c_byte(self.addr, self.configRegB.addr)
        printi(f'configRegB: {hex(r)}')

    def set_FSR(self):
        #print(f'>set_FSR')
        pv = self.devLDO[self.name+'_FSR']
        fsrTxt = pv.value[0]
        printv(f'fsr: {fsrTxt, type(fsrTxt)}, lv: {pv.legalValues}')
        self.fsr = float(fsrTxt)
        idx = pv.legalValues.index(fsrTxt)
        self._set_FSR(idx)

    def read_xyz(self, timestamp):
        ts = timer()
        if I2C_HMC5883.mode == 1:   # Single measurement
            I2C.write_i2c_byte(self.addr, self.modeReg.addr, I2C_HMC5883.mode)
            while I2C.read_i2c_byte(self.addr, 0x9) & 1 == 0:
                if timer() - ts > 0.010:# should last ~1ms
                    printw(f'Timeout reading {self.name, self.addr}')
                    return
        try:
            r = I2C.read_i2c_data(self.addr, 0x00, 10)
        except Exception as e:
            printw(f'reading_xyz {self.name,self.addr}: {e}')
            return
        printv(f'read {self.name}: {[hex(i) for i in r]}')
        xzy = struct.unpack('>3h', bytearray(r[3:9]))
        if r[0] & 1:# Internal field is excited, collect statistics
            printv(f'xzy.max: {max(xzy)}, {self.xzySumCount}')
            if max(xzy) < self.dataRange[1]*0.8 and self.xzySumCount != None:
                printv(f'self.xzySumCount {self.xzySumCount}, {self.xzySum}')
                self.xzySumCount += 1
                self.xzySum += xzy
            else:
                self.xzySumCount = None
                self.xzySum = np.zeros(3)
                printe(f'Correction processing failed for {self.name}')
        return xzy[0],xzy[2],xzy[1]
        
    def read(self, timestamp):
        pv = {'X':[], 'Y':[], 'Z':[], 'M':[]}
        ts = time.time()
        samples = self.ldoValue('_samples')[0]
        for sample in range(samples):
            try:    xyz = list(self.read_xyz(timestamp))
            except Exception as e:
                printw(f'Exception in read_xyz: {e}')
                return
            ovf = -4096# Hardware indication of the overflow
            g = self.fsr/self.dataRange[1]
            gc = self.gainCorrection if self.correct else (1.,1.,1.)
            for i in (X,Y,Z):
                v = xyz[i]
                xyz[i] = 10. if v == ovf else round(v*g*gc[i],6)
            printv(f'xyz {self.name}: {xyz}')
            m2 = 0.
            for axis,value in zip('XYZ',xyz):
                pv[axis].append(round(value,6))
                m2 += value**2
            # calculate magnitude
            magn = round(float(np.sqrt(m2)),6) if max(xyz) < 10. else 3*10.
            pv['M'].append(magn)
            printv(f"xyzm {self.name}: {pv['X'][-1],pv['Y'][-1],pv['Z'][-1],pv['M'][-1]}")
        rtime = round(time.time()-ts,6)
        self.devLDO[self.name+'_readout'].set_valueAndTimestamp(rtime, timestamp)
        for suffix,value in pv.items():
            self.devLDO[self.name+'_'+suffix].set_valueAndTimestamp(value, timestamp)

    def set_calibration(self):
        calibMode = self.ldoValue('_Calibration')[0]
        if calibMode == 'Off':
            printi(f'Calibration is disabled for {self.name}')
            self.correct = False
        elif calibMode == 'SelfTest':
            self.xyzSumCount = 0.
            # exite the strap (add ~1.1G) and read
            I2C.write_i2c_byte(self.addr, self.configRegA.addr, 0x71)# 8-average, 15 Hz default, positive self test measurement
            printi(f'Sensor {self.name} is excited with internal field ({self.testField})')
            self.correct = False
            return
        elif calibMode == 'On':
            if self.xyzSumCount is None:
                printe(f'Calibration of {self.name} was un-successfull')
                self.correct = False
            elif self.xyzSumCount == 0:
                printw(f'No prior SelfTest. Old calibration will be use: {self.gainCorrection}')
                self.correct = True
            else:
                xyzMean = self.xyzSum/self.xyzSumCount
                print(f'old correction: {self.gainCorrection}')
                g = self.fsr/self.dataRange[1]
                self.gainCorrection =\
                  [self.testField[i]/g/xyzMean[i] for i in (X,Y,Z)]
                print(f'new correction: {self.gainCorrection}')
                self.xyzSumCount = 0.
                self.xyzSum = np.zeros(3)
                printw(f'Fresh calibration is applied {self.gainCorrection}')
                self.correct = True
        else:
            printw(f'Un-supported calibration mode {calibMode}, of {self.name}')
        # restore_configRegA
        I2C.write_i2c_byte(self.addr, self.configRegA.addr, self.configRegA.B)
        return
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
    #TODO: add samples as in MMC5983MA
    mode = 1# Measurement mode 1:continuous
    def __init__(self, devAddr):
        super().__init__(devAddr, 'Magnetometer', 'QMC5883L')
        try:    devId = I2C.read_i2c_byte(self.addr, 0x0d)
        except:
            printe(f'There is no device with address {self.addr}')
            sys.exit()
        if devId != 0xff:
            raise RuntimeError(f'Chip is not QMC5883L: {devId}')

        # Initialize QMC5883
        self.configRegA = QMC5883_ConfigRegA()
        self.configRegA.b.MODE = I2C_QMC5883.mode
        self.configRegA.b.DO = 0# 10Hz. No effect.
        self.configRegA.b.FSR = 0# 2G
        self.configRegA.b.OSR = 0# OverSampling = 256. Less noise
        I2C.write_i2c_byte(self.addr, self.configRegA.addr, self.configRegA.B)

        lvFSR = ('2.', '8.')
        self.devLDO.update({
        self.name+'_FSR': LDO('WE','Full scale range is [-FSR:+FSR]',
            lvFSR[self.configRegA.b.FSR], legalValues=lvFSR, units='G',
            setter=self.set_FSR),
        self.name+'_X': LDO('R','X-axis field', 0., units='G'),
        self.name+'_Y': LDO('R','Y-axis field', 0., units='G'),
        self.name+'_Z': LDO('R','Z-axis field', 0., units='G'),
        self.name+'_M': LDO('R','Magnitude', 0., units='G'),
        self.name+'_T': LDO('R','Relative temperature', 0., units='C'),
        })
        printv(f'Sensor QMC5883 created: {self.name, self.addr}')

    def set_FSR(self):
        pv = self.devLDO[self.name+'_FSR']
        self.fsr = pv.value[0]
        idx = pv.legalValues.index(str(self.fsr))
        self.configRegA.b.FSR = idx
        #print(f'fsr: {self.fsr,idx}')
        #print(f'configRegA: {self.configRegA.addr, self.configRegA.B}')
        I2C.write_i2c_byte(self.addr, self.configRegA.addr, self.configRegA.B)

    def read(self, timestamp):
        ts = timer()
        pv = {'X':0., 'Y':0., 'Z':0., 'M':0.,'T':0.}
        # note: reading more than 6 bytes may give wrong result when cable is long
        try:
            r = I2C.read_i2c_data(self.addr, 0x00, 6)
        except Exception as e:
            printw(f'reading {self.name,self.addr}: {e}')
            return
        rtime = round(timer()-ts,6)
        self.devLDO[self.name+'_readout'].set_valueAndTimestamp(rtime, timestamp)
        #printv(f'conf,status: {hex(r[0x9]), hex(r[0x6])}')
        printvv(f'read {self.name}: {[hex(i) for i in r]}')
        g = self.fsr/32768.
        xyz = struct.unpack('<3h', bytearray(r[:6]))
        pv['X'],pv['Y'],pv['Z'] = [round(g*i,6) for i in xyz]
        pv['M'] = round(float(np.sqrt(pv['X']**2 + pv['Y']**2 +pv['Z']**2)), 6)
        r = I2C.read_i2c_data(self.addr, 0x07, 2)
        pv['T'] = round(struct.unpack('<h', bytearray(r))[0]/100. + 30.,2)
        printv(f"xyzm {self.name}: {pv['X'],pv['Y'],pv['Z'],pv['M'],pv['T']}")
        for suffix,value in pv.items():
            self.devLDO[self.name+'_'+suffix].set_valueAndTimestamp(value, timestamp)

#```````````````````MMC5983MA compass```````````````````````````````````````````
class I2C_MMC5983MA(I2CDev):
    #TODO: simplify as 5603
    FSR = 8.# Full scale range in Gauss
    bandwidth = {'100':0, '200':1, '400':2, '800':3}# Bandwidth of the decimation filter in Hz, it controls the duration of each measurement
    ICR = [0x09,0x0a,0x0b,0x0c]# Internal control registers
    control = {'Degauss':None, 'AutoReset':None, 'Off':None, 'Set':(ICR[0],0x08),
      'Reset':(ICR[0],0x10),'SoftReset':(ICR[1],0x80),
      'St_enp':(ICR[3],0x02), 'St_enm':(ICR[3],0x04)}
    continuous_frequency = {'0':0, '1':1, '10':2, '20':3, '50':4, '100':5,
      '200':6}

    def __init__(self, devAddr):
        super().__init__(devAddr, 'Magnetometer', 'MMC5983MA')
        devID = I2C.read_i2c_byte(self.addr, 0x2f)
        sensStatus = I2C.read_i2c_byte(self.addr, 0x8)
        printv(f'MMC5983:sensStatus: {sensStatus}')
        if sensStatus&0x10 == 0:
            raise RuntimeError('Chip could not read its memory')
        if devID != 0x30:
            raise RuntimeError(f'MMC5983 has wrong address: {devID}')
        I2C.write_i2c_byte(self.addr, *I2C_MMC5983MA.control['SoftReset'])
        time.sleep(0.01)
        printv(f'MMC5983:MMC5983MA ID: {devID}')
        self.ICR2 = 0
        self.continuous_interval = 0.
        n = self.name
        self.devLDO.update({
        n+'_control': LDO('RWE','Degauss: auto compensation, AutoReset: seldom Set/Reset, Set/Reset: pulse the sensor coils, SoftReset clear all registers',
            ['AutoReset'], legalValues=list(I2C_MMC5983MA.control.keys()),
            setter=self.set_control),
        n+'_continuous': LDO('RWE','Continuous mode frequency', ['0'], 
            legalValues=list(I2C_MMC5983MA.continuous_frequency), units='Hz',
            setter=self.set_continuous),
        n+'_bandwidth': LDO('RWE','Bandwidth', ['100'], units='Hz',
            legalValues=list(I2C_MMC5983MA.bandwidth.keys()), setter=self.set_bandwidth),
        n+'_ICR2': LDO('RWE','Internal control register 2, defines continuous mode',
            [self.ICR2], setter=self.set_ICR2),
        n+'_samples': LDO('RWE','Number of samples per one poll', [1]),
        n+'_X': LDO('R','X-axis field', [0.], units='G'),
        n+'_Y': LDO('R','Y-axis field', [0.], units='G'),
        n+'_Z': LDO('R','Z-axis field', [0.], units='G'),
        n+'_M': LDO('R','Magnitude', [0.], units='G'),
        n+'_T': LDO('R','Sensor temperature', 0., units='C'),
        n+'_PSD': LDO('R','Power spectral density', [0.]),
        n+'_frequency': LDO('R','Frequency scale for PSD', [0.]),
        })
        self.init()
        printv(f'MMC5983:Sensor MMC5983MA created: {n, self.addr}')

    def init(self):
        # init sensor
        I2C.write_i2c_byte(self.addr, I2C_MMC5983MA.ICR[0], 0x0)
        I2C.write_i2c_byte(self.addr, I2C_MMC5983MA.ICR[2], self.ICR2)
        I2C.write_i2c_byte(self.addr, I2C_MMC5983MA.ICR[3], 0x0)
        self.set_bandwidth()

    def _measure(self, comment=''):
        if self.ICR2 & 0x7 == 0:# Continuous mode is Off
            # ask to measure field
            I2C.write_i2c_byte(self.addr, I2C_MMC5983MA.ICR[0],0x1)
        # wait for measurement to complete
        for ntry in range(20):
            #waittime = max(self.integrationTime, self.continuous_interval.continuous_interval)
            waittime = 0.0005
            time.sleep(waittime)
            status = I2C.read_i2c_byte(self.addr, 0x8)
            if status&0x1:
                break
        #if ntry > 0:    print(f'MMC5983:ntry,status: {ntry,hex(status)}')
        try:
            r = I2C.read_i2c_data(self.addr, 0x00, 7)
        except Exception as e:
            printw(f'reading {self.name}: {e}')
            return
        #printv(f'MMC5983:regs: {[hex(i) for i in r]}')
        # decode 18-bit values xyz18
        xyz17_2 = [i for i in struct.unpack('>3H', bytearray(r[:6]))]
        xyzOut2 = ((r[6]>>6)&3, (r[6]>>4)&3,(r[6]>>2)&3)
        xyz18 = [((xyz17_2[i])<<2) + xyzOut2[i] for i in range(3)]
        #printv(f'MMC5983:xyz18: {[hex(i) for i in xyz18]}')
        xyz = (np.array(xyz18)/0x20000-1.)*I2C_MMC5983MA.FSR
        #printv(f'MMC5603:xyz in Gauss after {comment}: {xyz}')
        return xyz

    def _measureCorrected(self, samples=1, degauss=False):
        """Sample magnetic field
        degauss: eliminate thermal variations, and residual magnetization
        """
        sample_xyzSet = np.zeros(3*samples).reshape((samples,3))
        sample_xyzReset = np.zeros(3*samples).reshape((samples,3))
        if degauss:
            I2C.write_i2c_byte(self.addr, I2C_MMC5983MA.ICR[0], 0x8)# Do Set, for offset compensation
            for sample in range(samples):
                sample_xyzSet[sample] = self._measure('Set')
            I2C.write_i2c_byte(self.addr, I2C_MMC5983MA.ICR[0], 0x10)# Do Reset
            for sample in range(samples):
                sample_xyzReset[sample] = self._measure('Reset')
            xyz = (sample_xyzSet.T - sample_xyzReset.T)/2.
        else:
            for sample in range(samples):
                sample_xyzSet[sample] = self._measure('Direct')
            xyz = sample_xyzSet.T
        return xyz

    def read(self, timestamp):
        nsamples = self.ldoValue('_samples')[0]
        ts = time.time()
        degauss = self.ldoValue('_control')[0] == 'Degauss'
        try:
            xyz_samples = self._measureCorrected(nsamples, degauss)
        except Exception as e:
            printw(f'MMC5983:Exception in read(): {e}')
            return
        rtime = round(time.time()-ts,6)
        printv(f'MMC5983:xyz_samples:{xyz_samples}')

        xyzMean = xyz_samples.mean(1)
        xyzSTD = xyz_samples.std(1)
        magnitude = round(np.sqrt(np.sum(xyzMean**2)),6)

        # update PVs
        self.devLDO[self.name+'_readout'].set_valueAndTimestamp(rtime, timestamp)
        if magnitude > 0.:
            self.devLDO[self.name+'_M'].set_valueAndTimestamp(magnitude, timestamp)
            for i,suffix in enumerate('XYZ'):
                self.devLDO[self.name+'_'+suffix].set_valueAndTimestamp(\
                    round(xyzMean[i],6), timestamp)

        # calculate PSD
        if nsamples >= 10:
            magnitudes = np.sqrt(np.sum(xyz_samples**2,0))
            #print(f'magn: {magnitudes}')
            if self.continuous_interval == 0.:
                sampling_frequency = nsamples/rtime
            else:
                sampling_frequency = 1./self.continuous_interval
            freq, psd = signal.periodogram(magnitudes, sampling_frequency)
            #print(f'psd: {psd}')
            #print(f'freq: {freq}')
            self.devLDO[self.name+'_frequency'].set_valueAndTimestamp(freq[1:], timestamp)
            self.devLDO[self.name+'_PSD'].set_valueAndTimestamp(psd[1:], timestamp)

        # temperature update
        if ts - self.lastSeldomUpdate > seldomUpdate:
            self.lastSeldomUpdate = ts
            # ask to measure temperature
            I2C.write_i2c_byte(self.addr, I2C_MMC5983MA.ICR[0],0x2)
            # wait for measurement to complete
            for ntry in range(3):
                status = I2C.read_i2c_byte(self.addr, 0x8)
                if status&0x2:
                    break
            temp = I2C.read_i2c_byte(self.addr, 0x7)
            printv(f'MMC5983:TStatus = {hex(status)}, temp: {temp}')
            temp = round(-75. + temp*0.8, 2)
            self.devLDO[self.name+'_T'].set_valueAndTimestamp(temp, timestamp)
            if self.ldoValue('_control')[0] == 'AutoReset':
                self.set_reset_coil()

    def set_bandwidth(self):
        v = self.ldoValue('_bandwidth')[0]
        I2C.write_i2c_byte(self.addr, I2C_MMC5983MA.ICR[1], I2C_MMC5983MA.bandwidth[v])
        self.integrationTime = round(1./float(v),6)
        printi(f'I2C_MMC5983MA:set_bandwidth {v}, integration time:{self.integrationTime}')

    def set_control(self):
        action = self.ldoValue('_control')[0]
        printi(f'Control set to {action}')
        rv = I2C_MMC5983MA.control.get(action)
        if rv is None:
            return
        reg,value = rv
        I2C.write_i2c_byte(self.addr, reg, value)
        if action == 'SoftReset':
            self.init()

    def set_reset_coil(self):
        printi('MMC5983:>set_reset_coil')
        I2C.write_i2c_byte(self.addr, *I2C_MMC5983MA.control['Set'])
        I2C.write_i2c_byte(self.addr, *I2C_MMC5983MA.control['Reset'])

    def update_ICR2(self):
        t = time.time()
        I2C.write_i2c_byte(self.addr, I2C_MMC5983MA.ICR[2], self.ICR2)
        self.devLDO[self.name+'_ICR2'].set_valueAndTimestamp([self.ICR2], t)

    def set_continuous(self):
        lv = self.ldoValue('_continuous')[0]
        self.continuous_interval = 0. if lv == '0' else 1./float(lv)
        v = I2C_MMC5983MA.continuous_frequency[lv]
        printi(f'MMC5983:>set_continuous {v}')
        cmm_en = 0 if v == 0 else 8
        self.ICR2 = self.ICR2&0xF0
        self.ICR2 = self.ICR2|(0xF&(cmm_en+v))
        self.update_ICR2()

    def set_ICR2(self):
        print(f'ICR2={self.ldoValue("_ICR2")}')
        self.ICR2 = self.ldoValue('_ICR2')[0]
        printi(f'MMC5983:>set_ICR2={self.ICR2}')
        self.update_ICR2()
        
#```````````````````MMC5983MA compass```````````````````````````````````````````
class I2C_MMC5603(I2CDev):
    cm_freq = 0x0# Continuous mode off
    FSR = 30.# Full scale range in Gauss
    bandwidth = {'6.5':0, '3.5':1, '2.0':2, '1.2':3}# Bandwidth of the decimation filter in Hz, it controls the duration of each measurement
    #control = {'AutoReset':None, 'Off':None, 'Set':(MMC5983_ICR[0],0x08),
    #'Reset':(MMC5983_ICR[0],0x10),'SoftReset':(MMC5983_ICR[1],0x80),
    #'St_enp':(MMC5983_ICR[3],0x02), 'St_enm':(MMC5983_ICR[3],0x04)}

    def __init__(self, devAddr):
        super().__init__(devAddr, 'Magnetometer', 'MMC5603')
        n = self.name
        self.devLDO.update({
        #n+'_control': LDO('RWE','AutoReset is for normal operations, Set/Reset: pulse the sensor coils, SoftReset clear all registers',
        #    ['AutoReset'], legalValues=list(I2C_MMC5603.control.keys()),
        #    setter=self.set_control),
        n+'_status': LDO('R', 'Status register', 0),
        #n+'_ODR': LDO('WE', 'Defines frequency of continuous-mode measurements',
        #    0, setter=self.set_ODR),
        n+'_control': LDO('WEI','Control registers', [0]*3, setter=self.set_control),
        n+'_bandwidth': LDO('RWEI','Bandwidth, defines the length of decimation fiter',
            ['6.5'], units='ms', setter=self.set_bandwidth,
            legalValues=list(I2C_MMC5603.bandwidth.keys())),#setter=self.set_bandwidth),
        n+'_samples': LDO('RWE','Number of samples', 1),
        n+'_X': LDO('R','X-axis field', [0.], units='G'),
        n+'_Y': LDO('R','Y-axis field', [0.], units='G'),
        n+'_Z': LDO('R','Z-axis field', [0.], units='G'),
        n+'_M': LDO('R','Magnitude', [0.], units='G'),
        n+'_T': LDO('R','Sensor temperature', 0., units='C'),
        })
        self.set_bandwidth()
        print(f'MMC5603 Status1{self.readStatus()}')
        printv(f'MMC5603:Sensor created: {self.name, self.addr}')

    def set_bandwidth(self):
        v = self.ldoValue('_bandwidth')[0]
        I2C.write_i2c_byte(self.addr, 0x1C, I2C_MMC5603.bandwidth[v])
        self.integrationTime = round(0.001*float(v),6)
        printi(f'MMC5603:set_bandwidth {v}, integration time:{self.integrationTime}')

    def readStatus(self): 
        return I2C.read_i2c_byte(self.addr, 0x18)

    #def set_ODR(self):
    #    v = self.ldoValue('_ODR')
    #    I2C.write_i2c_byte(self.addr, 0x1A, v)
    #
    def set_control(self):
        v = self.ldoValue('_control')
        printi(f'MMC5603: Setting control to {v}')
        I2C.write_i2c_byte(self.addr, 0x1B, v[0])
        I2C.write_i2c_byte(self.addr, 0x1C, v[1])
        I2C.write_i2c_byte(self.addr, 0x1D, v[2])

    def _measure(self, comment=''):
        """Measure magnetic field"""
        # ask to measure field
        I2C.write_i2c_byte(self.addr, 0x1B,0x1)
        # wait for measurement to complete
        measurement_complete = False
        for ntry in range(3):
            #time.sleep(self.integrationTime)
            time.sleep(self.integrationTime)
            status = self.readStatus()
            if status&0x40:
                measurement_complete = True
                break
        printv(f'MMC5983:MStatus = {hex(status)}, tries:{ntry}')
        if not measurement_complete:
            txt = f'MMC5603:Measurement not complete'
            raise RuntimeError(txt)
        #Read XYZ
        try:
            r = I2C.read_i2c_data(self.addr, 0x00, 9)
        except Exception as e:
            txt = f'MMC5603:reading {self.name}: {e}'
            raise RuntimeError(txt)
        printv(f'MMC5603:regs: {[hex(i) for i in r]}')
        # decode 20-bit values xyz18
        xyz19_4 = [i for i in struct.unpack('>3H', bytearray(r[:6]))]
        xyzOut4 = ((r[6]>>4)&15, (r[7]>>4)&15,(r[8]>>4)&15)
        xyz20 = [((xyz19_4[i])<<4) + xyzOut4[i] for i in range(3)]
        printv(f'MMC5603:xyz20: {[hex(i) for i in xyz20]}')
        xyz = (np.array(xyz20)/0x80000-1.)*I2C_MMC5603.FSR
        printv(f'MMC5603:xyz in Gauss after {comment}: {xyz}')
        return xyz

    def _measureCorrected(self, samples=1, degauss=False):
        """Sample magnetic field
        degauss: eliminate thermal variations, and residual magnetization
        """
        sample_xyzSet = np.zeros(3*samples).reshape((samples,3))
        sample_xyzReset = np.zeros(3*samples).reshape((samples,3))
        if degauss:
            I2C.write_i2c_byte(self.addr, 0x1B, 0x8)# Do Set, for offset compensation
            for sample in range(samples):
                sample_xyzSet[sample] = self._measure('Set')
            I2C.write_i2c_byte(self.addr, 0x1B, 0x10)# Do Reset
            for sample in range(samples):
                sample_xyzReset[sample] = self._measure('Reset')
            xyz = (sample_xyzSet.T - sample_xyzReset.T)/2.
        else:
            for sample in range(samples):
                sample_xyzSet[sample] = self._measure('Direct')
            xyz = sample_xyzSet.T
        return xyz

    def read(self, timestamp):
        status = self.readStatus()
        self.devLDO[self.name+'_status'].set_valueAndTimestamp(status, timestamp)

        nsamples = self.ldoValue('_samples')[0]
        ts = time.time()
        try:
            xyz_samples = self._measureCorrected(nsamples, degauss = True)
        except Exception as e:
            printw(f'MMC5603:Exception in read(): {e}')
            return
        rtime = round(time.time()-ts,6)        
        printv(f'MMC5603:xyz_samples:{xyz_samples}')

        xyzMean = xyz_samples.mean(1)
        xyzSTD = xyz_samples.std(1)
        magnitude = round(np.sqrt(np.sum(xyzMean**2)),6)

        # update PVs
        self.devLDO[self.name+'_readout'].set_valueAndTimestamp(rtime, timestamp)
        if magnitude >0:
            self.devLDO[self.name+'_M'].set_valueAndTimestamp(magnitude, timestamp)
            for i,suffix in enumerate('XYZ'):
                self.devLDO[self.name+'_'+suffix].set_valueAndTimestamp(\
                    round(xyzMean[i],6), timestamp)

        # force the temperature update
        if ts - self.lastSeldomUpdate > seldomUpdate:
            self.lastSeldomUpdate = ts
            # ask to measure temperature
            I2C.write_i2c_byte(self.addr, 0x1B, 0x2)
            # wait for measurement to complete
            for ntry in range(3):
                status = self.readStatus()
                if status&0x2:
                    break
            printv(f'MMC5603:MStatus = {hex(status)}, tries:{ntry}')
            temp = I2C.read_i2c_byte(self.addr, 0x9)
            printv(f'MMC5603:T = {temp}')
            temp = round(-75. + temp*0.8,2)
            self.devLDO[self.name+'_T'].set_valueAndTimestamp(temp, timestamp)

#```````````````````TLV493D magnetometer```````````````````````````````````````
class I2C_TLV493D(I2CDev):
    UDataMax = 2048# Max unsigned readout value
    LSB = 0.98# Gauss per Low Significant Bit = 0.98
    LinearRange = (-1300.0, +1300.0)# Gauss
    LSBT = 1.1# Celsius Degree per LSB for temperature reading
    MaxRate = 1./3300# Fast update rate is automatic, 3.3 KHz
    def __init__(self, devAddr):
        printv(f'I2C_TLV493D {devAddr}')
        super().__init__(devAddr, 'Magnetometer', 'TLV493D')
        self.devLDO.update({# Add LDOs
            self.name+'_X': LDO('R','X-axis field', 0., units='G'),
            self.name+'_Y': LDO('R','Y-axis field', 0., units='G'),
            self.name+'_Z': LDO('R','Z-axis field', 0., units='G'),
            self.name+'_M': LDO('R','Magnitude', 0., units='G'),
            self.name+'_T': LDO('R','Temperature', 0., units='C'),
        })
        regs = I2C.read_i2c_data(self.addr, 0x0, 7)
        printv(f'TLV493:regs: {[hex(i) for i in regs]}')

        # Set device to Low-power mode, all other modes can hangup ADC and cause I2C bus locks.
        I2C.write_i2c_byte(self.addr, 1, 0x1)# Low-power mode
        #ISSUE#I2C.write_i2c_byte(self.addr, 1, 0x7)# Master Controlled Mode
        printv(f'TLV493:Sensor created: {self.name, self.addr}')

    def read(self, timestamp):
        # For low power mode we might need to turn Low Power On, wait for DP bit, readout, then set Low Power Off
        m1 = self.UDataMax
        m2 = m1*2
        ts = time.time()
        # The waiting for conversion does not improve anything
        #while timer()-ts < 0.09:
        r = I2C.read_i2c_data(self.addr, 0x0, 7)
        #    if (r[5])&0x10:# Conversion completed
        #        break
        #printv(f'TLV493:r5: {hex(r[5]), round(timer()-ts,6)}')
        rtime = round(time.time()-ts,6)
        self.devLDO[self.name+'_readout'].set_valueAndTimestamp(rtime, timestamp)
        printv(f'TLV493:read: {[hex(i) for i in r]}, {rtime}')
        x = tosigned12((r[0]<<4) + ((r[4]>>4)&0xF))
        y = tosigned12((r[1]<<4) + (r[4]&0xF))
        z = tosigned12((r[2]<<4) + (r[5]&0xF))
        printv(f'TLV493:xyz: {x,y,z}')
        magnitude = round(float(np.sqrt(x**2 + y**2 + z**2)), 6)

        # update parameters
        if magnitude > 0:
            for suffix,v in zip('XYZM', (x,y,z,magnitude)):
                v*= self.LSB
                self.devLDO[self.name+'_'+suffix].set_valueAndTimestamp(v, timestamp)

        # temperature update
        if ts - self.lastSeldomUpdate > seldomUpdate:
            self.lastSeldomUpdate = ts
            t7_0 = r[6]#I2C.read_i2c_byte(self.addr, 6)
            t11_8 = r[3]#I2C.read_i2c_byte(self.addr, 3)
            tbits = ((t11_8&0xF0)<<4) + t7_0
            t = (tbits - 340.)*self.LSBT + 25.
            printv(f'TLV493:(tempTLV: {hex(t7_0), hex(t11_8), hex(tbits), t}')
            self.devLDO[self.name+'_T'].set_valueAndTimestamp(t, timestamp)

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
        super().__init__(devAddr, 'ADC', model)
        self.config = ADS1115_ConfigReg()
        self.config.W = I2C.read_i2c_word(self.addr, 1)
        self.config.b.MODE = ADS1115_SingleShot
        I2C.write_i2c_word(self.addr, 1, self.config.W )
        lvFSR = ('6.144', '4.096', '2.048', '1.024', '0.512' , '0.256')
        lvDR = {'ADS1115': ('8',     '16',   '32',   '64',  '128',  '250',  '475',  '860'),
                'ADS1015': ('128',  '250',  '490',  '920', '1600', '2400', '3300', '300')}
        self.devLDO.update({
        self.name+'_rlength': LDO('RWE', 'Record length, ', 1),
        self.name+'_tAxis': LDO('R', 'Time axis for samples', [0.], units='s'),
        self.name+'_nCh': LDO('RWE', 'Number of active ADC channels. Select 1 for faster performance.',
            '4', legalValues=['4','1']),
        self.name+'_diff': LDO('RWE', 'Differential mode, Ch0=AIN0-AIN1, Ch1=AIN2-AIN3', 'Single-ended', legalValues=['Single-ended','Diff']),
        self.name+'_Ch0': LDO('R', 'ADC channel 0', [0.], units='V'),
        self.name+'_Ch1': LDO('R', 'ADC channel 1', [0.], units='V'),
        self.name+'_Ch2': LDO('R', 'ADC channel 2', [0.], units='V'),
        self.name+'_Ch3': LDO('R', 'ADC channel 3', [0.], units='V'),
        self.name+'_FSR': LDO('RWE', 'FSR, Full scale range is [-FSR:+FSR]',
            [lvFSR[self.config.b.FSR]], legalValues=lvFSR, units='V',
            setter=partial(self.set_pv,'FSR')),
        self.name+'_DR': LDO('RWE', 'Data rate',
            [lvDR[model][self.config.b.DR]], units='SPS',
            legalValues=lvDR[model], setter=partial(self.set_pv, 'DR')),
        })
        '''The following parts are handled internally
        self.name+'_MODE': LDO('RWE', 'Device operating mode', self.config.b.MODE,
            opLimits=(0,1), setter=partial(self.set_pv, 'MODE')),
        self.name+'_MUX': LDO('RWE', 'Input multiplexer config', self.config.b.MUX,
            opLimits=(0,7), setter=partial(self.set_pv,'MUX')),
        self.name+'_OS': LDO('RWE', 'Operational status, 0:conversion in progress',
            self.config.b.OS,
            opLimits=(0,1), setter=partial(self.set_pv, 'OS')),
        self.name+'_COMP_QUE': LDO('RWE', 'Comparator queue',
            self.config.b.COMP_QUE,
            opLimits=(0,2), setter=partial(self.set_pv, 'COMP_QUE')),
        self.name+'_COMP_LAT': LDO('RWE', 'Latching comparator',
            self.config.b.COMP_LAT,
            opLimits=(0,1), setter=partial(self.set_pv, 'COMP_LAT')),
        self.name+'_COMP_POL': LDO('RWE', 'Comparator polarity, active high',
            self.config.b.COMP_POL,
            opLimits=(0,1), setter=partial(self.set_pv, 'COMP_POL')),
        self.name+'_COMP_MODE': LDO('RWE', 'Window comparator',
            self.config.b.COMP_MODE,
            opLimits=(0,1), setter=partial(self.set_pv, 'COMP_MODE')),
        '''
        printi(f'Sensor {model} created {self.name, self.addr}')

    def read(self, timestamp):
        def wait_conversion():
            tswc = timer()
            if self.config.b.MODE == 1:# in Single-shot mode: wait when OS bit = 1
                while True:
                    self.config.W = I2C.read_i2c_word(self.addr, 1)
                    if self.config.b.OS == 1:
                        break
                    if timer() - tswc > .2:
                        raise TimeoutError('Timeout in I2C_ADS1115')
            else:
                # in continuous mode the OS is always 1, wait approximately one conversion period. 
                sleepTime = max(0, 1./(self.ldoValue('_DR')[0]- 0.0013))# 1.3ms is correction for transaction time
                time.sleep(sleepTime)
            v = I2C.read_i2c_word(self.addr, 0)
            v = int(((v&0xff)<<8) + ((v>>8)&0xff))# swap bytes
            if v & 0x8000:  v = v - 0x10000
            v = v/0x10000*float(self.ldoValue('_FSR')[0])*2.
            return v

        self.config.W = I2C.read_i2c_word(self.addr, 1)
        da = self.name
        nCh = int(self.ldoValue('_nCh')[0])
        if self.ldoValue('_diff')[0].startswith('Diff'):
            listCmd = [(0,'_Ch0'), (3,'_Ch1')]
        else:
            listCmd = [(4,'_Ch0'), (5,'_Ch1'), (6,'_Ch2'), (7,'_Ch3')]
        # set mux for first item of the list
        self.config.b.MUX = listCmd[0][0]
        self.config.b.MODE = 0 if nCh == 1 else ADS1115_SingleShot
        I2C.write_i2c_word(self.addr, 1, self.config.W )

        # init the sample data
        nSamples = self.ldoValue('_rlength')[0]
        self.devLDO[da+'_tAxis'].value = [0.]*nSamples
        for mux,ch in listCmd[:nCh]:
            self.devLDO[da+ch].value = [0.]*nSamples
        t0 = timer()

        # collect samples
        for sample in range(nSamples):
            for mux,ch in listCmd[:nCh]:
                if nCh > 1:
                    self.config.b.MUX = mux
                    I2C.write_i2c_word(self.addr, 1, self.config.W)
                #tt.append(round(timer()-ts,6))
                v = wait_conversion()
                self.devLDO[da+ch].value[sample] = v
            self.devLDO[da+'_tAxis'].value[sample] = round(timer() - t0,6)
        rtime = round(timer()-t0,6)
        self.devLDO[self.name+'_readout'].set_valueAndTimestamp(rtime, timestamp)

        # invalidate timestamps to schedule LDOs for publishing
        for mux,ch in listCmd[:nCh]:
            self.devLDO[da+ch].timestamp = timestamp
        self.devLDO[da+'_tAxis'].timestamp = timestamp
        #tt.append(round(timer()-ts,6))
        #print(f'read time: {tt}')

    def set_pv(self, field):
        pv = self.devLDO[self.name+'_'+field]        
        printv(f'>ADS1115.set_config {pv.name} = {pv.value[0]}')
        self.config.W = I2C.read_i2c_word(self.addr, 1)
        printv(f'current: {hex(self.config.W)}')
        printv(f'ADS1115.legalValues: {pv.legalValues}')
        try:    v = pv.legalValues.index(pv.value[0])
        except Exception as e:
            printv(f'exception in ADS1115.set_pv: {e}')
            v = pv.value[0]
        printv(f'set v: {v}')
        setattr(self.config.b, field, v)
        printv(f'new: {hex(self.config.W)}')
        I2C.write_i2c_word(self.addr, 1, self.config.W)

class I2C_ADS1015(I2C_ADS1115):
    def __init__(self, devAddr):
        printv(f'>I2C_ADS1015')
        super().__init__(devAddr, 'ADS1015')

# Predefined device classes
BuiltinDeviceMap = {
    0x48:   I2C_ADS1115,
    0x49:   I2C_ADS1015,
    0x30:   I2C_MMC5983MA,# and MMC5603
    0x1e:   I2C_HMC5883,
    0x0d:   I2C_QMC5883,
    0x5e:   I2C_TLV493D,
}
I2C.DeviceClassMap = BuiltinDeviceMap

def add_deviceClass(addr:int, devclass):
    """To add or replace item in deviceClassMap by user-defined I2C device. 
Should be called pior to scan()"""
    i2c.DeviceClassMap[addr] = devclass

def init(muxAddr:int, mask:int):
    """Scan multiplexed I2C bus and fill i2c.DeviceMap and initialize the I2C 
    for further use.
    muxAddr: address of the I2C multiplexer.
    mask: bitmask of enabled multiplexer channels
    """
    I2C.muxAddr = muxAddr
    I2C.busMask = mask
    I2C.CurrentMuxCh = 0
    printi(f'i2c.version: {__version__}, verbosity: {I2C.verbosity}')
    printi(f'I2CSMBus opened: using smbus package, busMask=0x{hex(I2C.busMask)}')
    if I2C.busMask == 0:
        I2C.DeviceMap = {}
        I2C.write_i2cMux(0)# reset the mux
        if I2C.muxAddr == None:
            sys.exit(1)
        printi('Mux reset')
        
    devMap = {}
    def scan(subbus:int):
        printv(f'scanning sub-bus {subbus}')
        r = {}
        for devAddr in range(128):
            devClass = None
            try:
                h = I2C.read_i2c_byte((subbus,devAddr),0)
                if devAddr < 0x70:# if it is not a multiplexer
                    if devAddr == 0x030:
                        productID =  I2C.read_i2c_byte((subbus,devAddr), 0x39)
                        printv(f'productID={productID}')
                        if productID == 16:
                            devClass = I2C_MMC5603
                    if devClass is None:
                        devClass = I2C.DeviceClassMap.get(devAddr, 'Unknown')
                    devInstance = devClass((subbus,devAddr))
                    r[(subbus,devAddr)] = devInstance
                    printv(f'Detected {devInstance.name}@{subbus,devAddr}')
            except OSError:
                pass# timeout
            #except Exception as e:
            #    printe(f'during scan: {devAddr,e}')
        return r
    for ch in range(8):
        chmask = 1<<ch
        if mask&chmask == 0:
            continue
        devMap.update(scan(ch+1))
        if I2C.muxAddr == None:
            break# There is no multiplexer on I2C bus. Work with one subbus
    printi(f'I2C devices detected: {[(dclass.name, addr, type(dclass).__name__)  for addr,dclass in devMap.items()]}')
    I2C.DeviceMap = devMap
    I2C.CurrentMuxCh = None

    # Fill I2C.LDOMap
    for devInstance in I2C.DeviceMap.values():
        I2C.LDOMap.update(devInstance.devLDO)
    printv(f'I2C parameters added: {I2C.LDOMap.keys()}')
