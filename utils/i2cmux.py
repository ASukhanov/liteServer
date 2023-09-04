"""Detect I2C devices on multiplexed I2C bus.
"""
__version__ = '3.2.0 2023-09-04'#

DeviceName = {# map of known address:deviceName
0x0d:'QMC5883',
0x30:'MMC5983MA',
0x1e:'HMC5883',
0x48:'ADS1115',
0x49:'ADS1015',
0x5e:'TLV493D',
}

I2CBus = 1 # Rpi I2C bus is 1
from smbus2 import SMBus as I2CSMBus
SMBus = I2CSMBus(I2CBus)
print(f'I2CSMBus opened: using smbus package')

def read_i2c_byte(addr:int, reg:int):
    return SMBus.read_byte_data(addr, reg)

def write_i2c_byte(addr:int, reg:int, value:int):
    SMBus.write_byte_data(addr, reg, value)

def write_i2cMux(value):
    if pargs.muxAddr is None:
        return
    try:
        print(f'write_i2cMux: {value}')
        write_i2c_byte(pargs.muxAddr, 0, value)
    except:
        print((f'There is no I2C mux at {pargs.muxAddr},'
        ' Only directly visible devices will be served'))
        pargs.muxAddr = None

def enable_i2cMuxChannel(ch:int):
    if ch:    write_i2cMux(1<<(ch-1))
    else:    write_i2cMux(0)

def i2cDeviceMap(mask=0xff):
    """Returns map of I2C devices. It detects devices on connected
    to multiplexed sub-busses.
    If pargs.muxAddr is None then the mux will be not touched"""
    devMap = {}
    def scan(subbus:int):
        # scan I2CBus with current setting of the mux
        r = {}
        for devAddr in range(128):
            try:
                h = read_i2c_byte(devAddr, 0)
                if devAddr < 0x70:# if it is not a multiplexer
                    devName = DeviceName.get(devAddr, 'Unknown')
                    r[(subbus,devAddr)] = devName
                    print(f'detected: {devAddr,devName}')
            except Exception as e:
                pass#print(f'exc: {devAddr,e}')
        return r

    if mask == 0:
        write_i2cMux(0)
        return scan(0)
    for ch in range(8):
        chmask = 1<<ch
        if mask&chmask == 0:
            continue
        print(f'scanning sub-bus {ch}')
        write_i2cMux(chmask)
        if pargs.muxAddr is None:
            return scan(0)
        devMap.update(scan(ch+1))
    return devMap

# parse arguments
import argparse
parser = argparse.ArgumentParser(description=__doc__
,formatter_class=argparse.ArgumentDefaultsHelpFormatter
,epilog=f'i2cmux: {__version__}')
parser.add_argument('-M','--muxAddr', type=int, default=0x77, help=\
'I2C address of the multiplexer') 
parser.add_argument('mask', default='11111111', nargs='?', help=\
('Mask of supported channels of I2C multiplexer.'
' If 0 then no channels selected, power-up/reset default state.'))
pargs = parser.parse_args()
pargs.mask = int(pargs.mask,2)
print(f'mask: {hex(pargs.mask)}')

print(f'muxAddr: {type(pargs.muxAddr), pargs.muxAddr}')
I2CDeviceMap = i2cDeviceMap(pargs.mask)
print(f'I2C devices detected: {I2CDeviceMap}')
