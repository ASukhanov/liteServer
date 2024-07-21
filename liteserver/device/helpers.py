import time
#```````````````````Helper functions``````````````````````````````````````````
def printTime(): return time.strftime("%m%d:%H%M%S")
def croppedText(txt, limit=200):
    if len(txt) > limit:
        txt = txt[:limit]+'...'
    return txt

def printi(msg): print(f'inf_@{printTime()}: {msg}')

def printw(msg, limit=200):
    msg = croppedText(msg, limit)
    print(f'WAR_@{printTime()}: {msg}')

def printe(msg, limit=200):
    msg = croppedText(msg, limit)
    print(f'ERR_@{printTime()}: {msg}')

def printv(msg, verbose=1, level=0):
    if verbose > level:
        print(f'DBG{level}: {msg}')

def serial_command(serDev, cmd, expectBytes=100, delay=0.):
    """Send serial command to device and return reply."""
    serDev.write(cmd)
    time.sleep(delay)
    r = serDev.read(expectBytes)
    return r

def find_serialDevice(writeCheck, baudrate, timeout=1, verbose=None):
    """The writeCheck is 'cmd,pattern'
    This method send cmd to all available serial devices and checks
    if reply starts with pattern.
    Returns the serial device wich responds as expected.
    """
    from serial import Serial
    from serial.tools import list_ports
    cmd,pattern = [i.encode() for i in writeCheck.split(',')]
    printv(f'cmd,pattern: {cmd,pattern}',verbose)
    for lp in list_ports.comports():
        devName,desc = str(lp).split(' - ')
        if 'n/a' in desc:
            continue
        printv(f'devName: {devName, baudrate, timeout}',verbose)
        try:    dev = Serial(devName, baudrate, timeout=timeout)
        except Exception as e:
            print(f'Could not open {devName}: {e}')
            continue
        try:
            r = serial_command(dev, cmd, delay=0.1)
            printv(f'Response of {devName} on {cmd}: {r}',verbose)
        except:
            continue
        if r.startswith(pattern):
            return dev,r
        continue
    return None,None
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
