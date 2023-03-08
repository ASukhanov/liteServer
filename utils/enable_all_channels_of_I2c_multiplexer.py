#!/usr/bin/env python3
"""
Enable all four of I2C sub-busses of the PGA9546A multiplexer.
Important! Make sure that all connected devices have
different I2C addresses.

To check which devices are visible use following command:
i2cdetect -y 1
""" 
 
import smbus
I2CBus = smbus.SMBus(1)
address = 0x70
# Enable Mux0,1,2,3:
I2CBus.write_byte_data(address,0x0,0xf)
