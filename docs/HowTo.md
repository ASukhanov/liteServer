## I2C devices on RPi

### Installation
http://www.instructables.com/id/Raspberry-Pi-I2C-Python

### Configuration of the Adafruit PCA9546A multiplexer board
Note, running `i2cdetect -y 1` when the PCA9546A is not configured may hang the RPi.
```python
import smbus
I2CBus = smbus.SMBus(1)
address = 0x70
# Enable Mux0:
I2CBus.write_byte_data(address,0x0,1)
# Enable Mux0 and Mux1:
I2CBus.write_byte_data(address,0x0,3)
```
