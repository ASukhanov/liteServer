"""`````````````````````````````Access to I2C bus``````````````````````````
For installation: https://www.instructables.com/Raspberry-Pi-I2C-Python/
I2C speed: https://www.raspberrypi-spy.co.uk/2018/02/change-raspberry-pi-i2c-bus-speed/
"""
__version__ = 'v3.2.0 2023-09-04'# Major refactoring. User-defined device classes could be added.
print(f'i2c: {__version__}')
#TODO: display errors and warnings in device status
#TODO: the DevClassMap should be incorporated into I2C class

import sys, time
timer = time.perf_counter
import struct
from functools import partial
import numpy as np
import ctypes
c_uint16 = ctypes.c_uint16
c_uint8 = ctypes.c_uint8

#import smbus as I2CSMBus
from smbus2 import SMBus as I2CSMBus

from liteserver.liteserver import LDO

def printi(msg): print(f'inf_i2c: {msg}')
def printw(msg): print(f'WARNING_i2c: {msg}')
def printe(msg): print(f'ERROR_i2c: {msg}')
def printv(msg):
    if I2C.verbosity>0: print(f'i2cDbg{I2C.verbosity}: {msg}')
def printvv(msg):
    if I2C.verbosity>1: print(f'i2cDbg{I2C.verbosity}: {msg}')
def tosigned12(n:int):
    n = n & 0xfff
    return (n ^ 0x800) - 0x800

X,Y,Z = 0,1,2

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
        self.lastSlowUpdate = 0.
        self.devLDOs = {
            self.name+'_sensor': LDO('R','Sensor model and type',
              f'{model} {sensorType}'),
            self.name+'_readout': LDO('R','Readout time', 0., units='s'),
        }

    def read(self, timestamp):
        print(f'I2CDev.read() not implemented for {self.name}')
        return

    def calibration(self, option:str):
        printw(f'Calibration is not implemented for {self.name, self.model}')

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
        self.xyzSumCount = 0
        self.xyzSum = np.zeros(3)

        self.devLDOs.update({
            self.name+'_FSR': LDO('WE','Full scale range is [-FSR:+FSR]',
                [lvFSR[self.configRegB.b.FSR]], legalValues=lvFSR, units='G',
                setter=self.set_FSR),
            self.name+'_X': LDO('R','X-axis field', 0., units='G'),
            self.name+'_Y': LDO('R','Y-axis field', 0., units='G'),
            self.name+'_Z': LDO('R','Z-axis field', 0., units='G'),
            self.name+'_M': LDO('R','Magnitude', 0., units='G'),
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
        pv = self.devLDOs[self.name+'_FSR']
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
        printvv(f'read {self.name}: {[hex(i) for i in r]}')
        xyz = struct.unpack('>3h', bytearray(r[3:9]))
        if r[0] & 1:# Internal field is excited, collect statistics
            printv(f'xyz.max: {max(xyz)}, {self.xyzSumCount}')
            if max(xyz) < self.dataRange[1]*0.8 and self.xyzSumCount != None:
                printv(f'self.xyzSumCount {self.xyzSumCount}, {self.xyzSum}')
                self.xyzSumCount += 1
                self.xyzSum += xyz
            else:
                self.xyzSumCount = None
                self.xyzSum = np.zeros(3)
                printe(f'Correction processing failed for {self.name}')
        return xyz
        
    def read(self, timestamp):
        ts = timer()
        try:    xyz = list(self.read_xyz(timestamp))
        except Exception:# as e:
            #printw(f'Exception in read_xyz: {e}')
            return
        rtime = round(timer()-ts,6)
        self.devLDOs[self.name+'_readout'].set_valueAndTimestamp(rtime, timestamp)
        ovf = -4096# Hardware indication of the overflow
        g = self.fsr/self.dataRange[1]
        gc = self.gainCorrection if self.correct else (1.,1.,1.)
        for i in (X,Y,Z):
            v = xyz[i]
            xyz[i] = 10. if v == ovf else round(v*g*gc[i],6)
        x,y,z = xyz
        m = 10. if max(x,y,z) == 10. else round(float(np.sqrt(x**2 + y**2 + z**2)),6)
        printv(f'xyzm {self.name}: {x,y,z,m}')
        da = self.name
        self.devLDOs[da+'_X'].set_valueAndTimestamp(x, timestamp)
        self.devLDOs[da+'_Y'].set_valueAndTimestamp(y, timestamp)
        self.devLDOs[da+'_Z'].set_valueAndTimestamp(z, timestamp)
        self.devLDOs[da+'_M'].set_valueAndTimestamp(m, timestamp)

    def calibration(self, calibMode:str):
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
        self.devLDOs.update({
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
        pv = self.devLDOs[self.name+'_FSR']
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
        self.devLDOs[self.name+'_readout'].set_valueAndTimestamp(rtime, timestamp)
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
            self.devLDOs[self.name+'_'+suffix].set_valueAndTimestamp(value, timestamp)

#```````````````````MMC5983MA compass```````````````````````````````````````````
MMC5983_bandwidth = {100:0, 200:1, 400:2, 800:3}# Bandwidth of the decimation filter in Hz, it controls the duration of each measurement
class I2C_MMC5983MA(I2CDev):
    cm_freq = 0x0# Continuous mode off
    FSR = 8.# Full scale range in Gauss
    Bandwidth = 100# Hz
    def __init__(self, devAddr):
        super().__init__(devAddr, 'Magnetometer', 'MMC5983MA')
        devID = I2C.read_i2c_byte(self.addr, 0x2f)
        sensStatus = I2C.read_i2c_byte(self.addr, 0x8)
        printv(f'sensStatus: {sensStatus}')
        if sensStatus&0x10 == 0:
            raise RuntimeError('Chip could not read its memory')
        if devID != 0x30:
            raise RuntimeError(f'MMC5983 has wrong address: {devID}')
        printv(f'MMC5983MA ID: {devID}')
        I2C.write_i2c_byte(self.addr, 0x9, 0x0)
        I2C.write_i2c_byte(self.addr, 0xa, MMC5983_bandwidth[self.Bandwidth])
        I2C.write_i2c_byte(self.addr, 0xb, I2C_MMC5983MA.cm_freq)
        I2C.write_i2c_byte(self.addr, 0xc, 0x0)

        self.devLDOs.update({
        self.name+'_X': LDO('R','X-axis field', 0., units='G'),
        self.name+'_Y': LDO('R','Y-axis field', 0., units='G'),
        self.name+'_Z': LDO('R','Z-axis field', 0., units='G'),
        self.name+'_M': LDO('R','Magnitude', 0., units='G'),
        self.name+'_T': LDO('R','Sensor temperature', 0., units='C'),
        })
        printv(f'Sensor MMC5983MA created: {self.name, self.addr}')

    def read(self, timestamp):
        pv = {'X':0., 'Y':0., 'Z':0., 'M':0.}
        da = self.name
        ts = timer()
        integrationTime = 1./self.Bandwidth
        if I2C_MMC5983MA.cm_freq == 0:
            # ask to measure field
            I2C.write_i2c_byte(self.addr, 0x09,0x1)
        # wait for measurement to complete
        for ntry in range(3):
            time.sleep(integrationTime)
            status = I2C.read_i2c_byte(self.addr, 0x8)
            if status&0x1:
                break
        printv(f'MStatus = {hex(status)}')
        try:
            r = I2C.read_i2c_data(self.addr, 0x00, 7)
        except Exception as e:
            printw(f'reading {self.name}: {e}')
            return
        rtime = round(timer()-ts,6)        
        self.devLDOs[self.name+'_readout'].set_valueAndTimestamp(rtime, timestamp)
        printv(f'regs: {[hex(i) for i in r]}')
        # decode 18-bit values xyz18
        xyz17_2 = [i for i in struct.unpack('>3H', bytearray(r[:6]))]
        xyzOut2 = ((r[6]>>6)&3, (r[6]>>4)&3,(r[6]>>2)&3)
        xyz18 = [((xyz17_2[i])<<2) + xyzOut2[i] for i in range(3)]
        printv(f'xyz18: {[hex(i) for i in xyz18]}')
        # calculate signed 18-bit values
        pv['X'],pv['Y'],pv['Z'] = [round((i/0x20000-1.)*I2C_MMC5983MA.FSR,6)\
            for i in xyz18]
        # calculate magnitude
        pv['M'] = round(float(np.sqrt(pv['X']**2 + pv['Y']**2 +pv['Z']**2)), 6)
        printv(f"xyzm {self.name}: {pv['X'],pv['Y'],pv['Z'],pv['M']}")
        for suffix,value in pv.items():
            self.devLDOs[self.name+'_'+suffix].set_valueAndTimestamp(value, timestamp)

        # force the temperature update once per 10s
        tm = time.time()
        if tm - self.lastSlowUpdate > 10.:
            self.lastSlowUpdate = tm
            # ask to measure temperature
            I2C.write_i2c_byte(self.addr, 0x09,0x2)
            # wait for measurement to complete
            for ntry in range(3):
                
                status = I2C.read_i2c_byte(self.addr, 0x8)
                if status&0x2:
                    break
            temp = I2C.read_i2c_byte(self.addr, 0x7)
            printv(f'TStatus = {hex(status)}, temp: {temp}')
            temp = round(-75. + temp*0.8,2)
            self.devLDOs[self.name+'_T'].set_valueAndTimestamp(temp, timestamp)

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
        self.devLDOs.update({# Add LDOs
            self.name+'_X': LDO('R','X-axis field', 0., units='G'),
            self.name+'_Y': LDO('R','Y-axis field', 0., units='G'),
            self.name+'_Z': LDO('R','Z-axis field', 0., units='G'),
            self.name+'_M': LDO('R','Magnitude', 0., units='G'),
            self.name+'_T': LDO('R','Temperature', 0., units='C'),
        })
        regs = I2C.read_i2c_data(self.addr, 0x0, 7)
        printv(f'regs: {[hex(i) for i in regs]}')

        # Set device to Low-power mode, all other modes can hangup ADC and cause I2C bus locks.
        I2C.write_i2c_byte(self.addr, 1, 0x1)# Low-power mode
        #ISSUE#I2C.write_i2c_byte(self.addr, 1, 0x7)# Master Controlled Mode
        printv(f'Sensor TLV493D created: {self.name, self.addr}')

    def read(self, timestamp):
        # For low power mode we might need to turn Low Power On, wait for DP bit, readout, then set Low Power Off
        m1 = self.UDataMax
        m2 = m1*2
        ts = timer()
        # The waiting for conversion does not improve anything
        #while timer()-ts < 0.09:
        r = I2C.read_i2c_data(self.addr, 0x0, 7)
        #    if (r[5])&0x10:# Conversion completed
        #        break
        #printv(f'r5: {hex(r[5]), round(timer()-ts,6)}')
        rtime = round(timer()-ts,6)
        self.devLDOs[self.name+'_readout'].set_valueAndTimestamp(rtime, timestamp)
        printv(f'read: {[hex(i) for i in r]}, {rtime}')
        x = tosigned12((r[0]<<4) + ((r[4]>>4)&0xF))
        y = tosigned12((r[1]<<4) + (r[4]&0xF))
        z = tosigned12((r[2]<<4) + (r[5]&0xF))
        printv(f'xyz: {x,y,z}')
        m = round(float(np.sqrt(x**2 + y**2 + z**2)), 6)

        # update parameters
        for suffix,v in zip('XYZM', (x,y,z,m)):
            v*= self.LSB
            self.devLDOs[self.name+'_'+suffix].set_valueAndTimestamp(v, timestamp)
        # force the temperature update once per 10s
        tm = time.time()
        if tm - self.lastSlowUpdate > 10.:
            self.lastSlowUpdate = tm
            t7_0 = r[6]#I2C.read_i2c_byte(self.addr, 6)
            t11_8 = r[3]#I2C.read_i2c_byte(self.addr, 3)
            tbits = ((t11_8&0xF0)<<4) + t7_0
            t = (tbits - 340.)*self.LSBT + 25.
            printv(f'(tempTLV: {hex(t7_0), hex(t11_8), hex(tbits), t}')
            self.devLDOs[self.name+'_T'].set_valueAndTimestamp(t, timestamp)

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
        self.devLDOs.update({
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
                sleepTime = max(0, 1./(self.devLDOs[self.name+'_DR'].value[0])\
                 - 0.0013)# 1.3ms is correction for transaction time
                time.sleep(sleepTime)
            v = I2C.read_i2c_word(self.addr, 0)
            v = int(((v&0xff)<<8) + ((v>>8)&0xff))# swap bytes
            if v & 0x8000:  v = v - 0x10000
            v = v/0x10000*float(self.devLDOs[da+'_FSR'].value[0])*2.
            return v

        self.config.W = I2C.read_i2c_word(self.addr, 1)
        da = self.name
        nCh = int(self.devLDOs[da+'_nCh'].value[0])
        if self.devLDOs[da+'_diff'].value[0].startswith('Diff'):
            listCmd = [(0,'_Ch0'), (3,'_Ch1')]
        else:
            listCmd = [(4,'_Ch0'), (5,'_Ch1'), (6,'_Ch2'), (7,'_Ch3')]
        # set mux for first item of the list
        self.config.b.MUX = listCmd[0][0]
        self.config.b.MODE = 0 if nCh == 1 else ADS1115_SingleShot
        I2C.write_i2c_word(self.addr, 1, self.config.W )

        # init the sample data
        nSamples = self.devLDOs[self.name+'_rlength'].value[0]
        self.devLDOs[da+'_tAxis'].value = [0.]*nSamples
        for mux,ch in listCmd[:nCh]:
            self.devLDOs[da+ch].value = [0.]*nSamples
        t0 = timer()

        # collect samples
        for sample in range(nSamples):
            for mux,ch in listCmd[:nCh]:
                if nCh > 1:
                    self.config.b.MUX = mux
                    I2C.write_i2c_word(self.addr, 1, self.config.W)
                #tt.append(round(timer()-ts,6))
                v = wait_conversion()
                self.devLDOs[da+ch].value[sample] = v
            self.devLDOs[da+'_tAxis'].value[sample] = round(timer() - t0,6)
        rtime = round(timer()-t0,6)
        self.devLDOs[self.name+'_readout'].set_valueAndTimestamp(rtime, timestamp)

        # invalidate timestamps to schedule LDOs for publishing
        for mux,ch in listCmd[:nCh]:
            self.devLDOs[da+ch].timestamp = timestamp
        self.devLDOs[da+'_tAxis'].timestamp = timestamp
        #tt.append(round(timer()-ts,6))
        #print(f'read time: {tt}')

    def set_pv(self, field):
        pv = self.devLDOs[self.name+'_'+field]        
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
    0x30:   I2C_MMC5983MA,
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
    printi(f'I2CSMBus opened: using smbus package, busMask={I2C.busMask}')
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
            try:
                h = I2C.read_i2c_byte((subbus,devAddr),0)
                if devAddr < 0x70:# if it is not a multiplexer
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
    printi(f'I2C devices detected: {[(dclass.name, addr, type(dclass).__name__)  for addr,dclass in devMap.items()]}')
    I2C.DeviceMap = devMap
    I2C.CurrentMuxCh = None

    # Fill I2C.LDOMap
    for devInstance in I2C.DeviceMap.values():
        I2C.LDOMap.update(devInstance.devLDOs)
    printv(f'I2C parameters added: {I2C.LDOMap.keys()}')
