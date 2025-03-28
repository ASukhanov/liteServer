# I2C devices on RPi
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
# UVC Camera
For camera installation refer:<br>
https://docs.arducam.com/UVC-Camera/Quick-Start-Guide%28USB2%29/Linux/

If camera fails to open with error message:<br>
uvc_bindings.OpenError: Could not open device. Error: Access denied<br>
Then you need to setup udev rules and add the target user to the plugdev group to avoid the privileged access requirement:
```
echo 'SUBSYSTEM=="usb",  ENV{DEVTYPE}=="usb_device", GROUP="plugdev", MODE="0664"' | sudo tee /etc/udev/rules.d/10-libuvc.rules > /dev/null
sudo udevadm trigger
sudo usermod -a -G plugdev $USER
# logout and back in
```
To change camera setting use following program: ```qv4l2```.

# LabJack U3
```
pip install LabJackPython# probably need sudo
```
Disconnect and reconnect the LabJack
```
python
>>> import u3
>>> d = u3.U3()
>>> d.configU3()
{'FirmwareVersion': '1.46', 'BootloaderVersion': '0.27', 'HardwareVersion': '1.30', 'SerialNumber': 320097467, 'ProductID': 3, 'LocalID': 1, 'TimerCounterMask': 64, 'FIOAnalog': 15, 'FIODirection': 0, 'FIOState': 0, 'EIOAnalog': 0, 'EIODirection': 0, 'EIOState': 0, 'CIODirection': 0, 'CIOState': 0, 'DAC1Enable': 1, 'DAC0': 0, 'DAC1': 0, 'TimerClockConfig': 2, 'TimerClockDivisor': 256, 'CompatibilityOptions': 0, 'VersionInfo': 18, 'DeviceName': 'U3-HV'}
```
