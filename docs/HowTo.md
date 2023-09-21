## I2C devices on RPi
### I2C speed
To veryfy the I2C speed:
:liteServer/utils/i2cspeed.sh

To set the speed:
* Open /boot/config.txt file<br>
sudo nano /boot/config.txt

* Find the line containing dtparam=i2c_arm=on

* Add i2c_arm_baudrate=<new speed> (Separate with a Comma)<br>
dtparam=i2c_arm=on,i2c_arm_baudrate=400000

* Reboot Raspberry Pi


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

### Scan available I2C devices, connected to I2C multiplexer with address 112
python3 liteServer/utils/i2cmux.py -M112
```
I2C devices detected: {(1, 30): 'HMC5883', (2, 48): 'MMC5983MA', (3, 72): 'ADS1115', (4, 94): 'TLV493D'}
```
