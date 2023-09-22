#!/usr/bin/env python3
"""liteserver, simulating peaks"""
__version__ = '3.2.1 2023-09-21'# update timestamps for pv['x'] 

import sys, time, threading
timer = time.perf_counter
import numpy as np

from .. import liteserver
LDO = liteserver.LDO
Device = liteserver.Device

#````````````````````````````Helper functions`````````````````````````````````
def gaussian(x, sigma):
    """Function, representing gaussian peak shape"""
    try: r = np.exp(-0.5*(x/sigma)**2) 
    except: r = np.zeros(len(x))
    return r

RankBkg = 3
def func_sum_of_peaks(xx, *par):
    """Base and sum of peaks."""
    if RankBkg == 3:
        s = par[0] + par[1]*xx + par[2]*xx**2 # if RankBkg = 3
    elif RankBkg == 1:
        s = par[0] # if RankBkg = 1
    for i in range(RankBkg,len(par),3):
        s += par[i+2]*gaussian(xx-par[i],par[i+1])
    return s

def peaks(x, *par, noiseLevel=0.):
    """Generate multiple peaks and noise"""
    x = np.array(x)
    n = len(x)
    noise = np.random.rand(n)
    noise = noise * noiseLevel
    noise += noiseLevel*noiseLevel
    #print(f'peaks.par: {par}')
    v = func_sum_of_peaks(x, *par)
    return v + noise
#````````````````````````````Lite Data Objects````````````````````````````````
class Dev(Device):
    """ Derived from liteserver.Device.
    Note: All class members, which are not process variables should 
    be prefixed with _"""
    def __init__(self, name, no_float32=False):
        pars = {
          'frequency':  LDO('RWE','Update frequency of all counters',
            pargs.frequency, units='Hz', opLimits=(0.001,1001.)),
          'nPoints':    LDO('RWE','Number of points in the waveform'
          ,pargs.nPoints, setter=self.set_peaks),
          'background': LDO('RWE','3 Coefficients for quadratic background'
          , pargs.background, setter=self.set_peaks),
          'noise':      LDO('RWE','Nose level'
          ,pargs.noise, setter=self.set_peaks),
          'peakPars':   LDO('RWE','Peak parameters'
          ,pargs.peaks, setter=self.set_peaks),
          'swing':      LDO('RWE','Horizontal peak oscillations',
                      				pargs.swing, units='%'),
          'x':          LDO('R','X-values',np.arange(pargs.nPoints)),
          'y':          LDO('R','Y-Values',np.zeros(pargs.nPoints)),
          'yMin':       LDO('R','',0.),
          'yMax':       LDO('R','',0.),
          'rps':        LDO('R','Cycles per second',0.,units='Hz'),
          'cycle':      LDO('R','Cycle number',0),
        }
        super().__init__(name, pars)

        self.set_peaks()

        thread = threading.Thread(target=self._state_machine)
        thread.daemon = False
        thread.start()

    def update_peaks(self):
        pars = self.PV['background'].value + self.PV['peakPars'].value
        return peaks(self.PV['x'].value, *pars, noiseLevel=self.PV['noise'].value[0])

    def set_peaks(self):
        n = self.PV['nPoints'].value[0]
        pp = generate_pars(n)
        self.PV['background'].value = pp[:3]
        self.PV['peakPars'].value = pp[3:]
        pars={i.name:(type(i.value[0]),i.value) for i in (self.PV['nPoints']
        ,self.PV['background'], self.PV['peakPars'], self.PV['noise'])}
        self.PV['x'].value = np.arange(n)
        self.PV['y'].value = self.update_peaks()
        #print(f'y:{self.PV['y'].value}')

    def swing_peaks(self):
        n = self.PV['nPoints'].value[0]
        deviation = np.sin(self.PV['cycle'].value/10*np.pi)*self.PV['swing'].value[0]/100*n
        for i in range(0,len(self.PV['peakPars'].value),3):
            self.PV['peakPars'].value[i] += deviation

    def _state_machine(self):
        time.sleep(.2)# give time for server to startup

        self.PV['cycle'].value = 0
        prevCycle = 0
        timestamp = time.time()
        periodic_update = timestamp
        while not self.EventExit.is_set():
            waitTime = 1./self.PV['frequency'].value[0] - (time.time() - timestamp)
            Device.EventExit.wait(waitTime)
            timestamp = time.time()
            dt = timestamp - periodic_update
            if dt > 10.:
                periodic_update = timestamp
                if server.Dbg > 0:
                    print(f"cycle of {self.name}:{self.PV['cycle'].value}, wt:{round(waitTime,4)}")
                #print(f'periodic update: {dt}')
                msg = f'periodic update {self.name} @{round(timestamp,3)}'
                self.PV['status'].value = msg
                self.PV['status'].timestamp = timestamp
                self.PV['rps'].value = (self.PV['cycle'].value - prevCycle)/dt
                self.PV['rps'].timestamp = timestamp
                prevCycle = self.PV['cycle'].value
            self.PV['cycle'].value += 1

            if self.PV['swing'].value[0] != 0.:
                self.swing_peaks()
            self.PV['y'].value = self.update_peaks().round(3)
            self.PV['yMin'].value = float(self.PV['y'].value.min())
            self.PV['yMax'].value = float(self.PV['y'].value.max())
            # invalidate timestamps for changing variables, otherwise the
            # publish() will ignore them
            for i in [self.PV['cycle'], self.PV['x'], self.PV['y'],
              self.PV['yMin'], self.PV['yMax']]:
                i.timestamp = timestamp

            shippedBytes = self.publish()

        print('liteSimPeaks '+self.name+' exit')
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
if __name__ == "__main__":
    import argparse

    #default coeffs for --background
    n = 1000
    linmin = 1.
    linmax = 30.
    quadmax = 20.
    def generate_pars(n):
        a = -4*quadmax/n**2
        b = -a*n + (linmax-linmin)/n
        bckPars = [linmin, round(b,6), round(a,9)]
        peakPars = [0.3*n,0.015*n,10, 0.5*n,0.020*n,40, 0.7*n,0.025*n,15]
        return bckPars + peakPars
    def str_of_numbers(numbers:list):
        return ','.join([f'{i}' for i in numbers])
    pp = generate_pars(n)

    parser = argparse.ArgumentParser(description=__doc__
        ,formatter_class=argparse.ArgumentDefaultsHelpFormatter
        ,epilog=f'litePeakSimulator version {__version__}, liteserver {liteserver.__version__}')
    parser.add_argument('-b', '--background', default=str_of_numbers(pp[:3])
    , help=('Three coefficients (comma-separated) of the quadratic background'))
    parser.add_argument('-d','--doubles', action='store_true'
    , help='Encode floats as doubles, use it when you need precision higher than 7 digits')
    parser.add_argument('-F','--frequency', type=float, default=1000., help=\
        'Update frequency [Hz]')
    parser.add_argument('-i','--interface', default = '', help=\
    'Network interface. Default is the interface, which is connected to internet')
    parser.add_argument('-n','--nPoints', type=int, default=n)
    parser.add_argument('-N','--noise', type=float, default=10.)
    parser.add_argument('-P','--peaks', default=str_of_numbers(pp[3:]), help=
        ('Comma-separated peak parameters, 3 parameters per peak: '
        f'position,sigma,amplitude'))
    parser.add_argument('-p','--port', type=int, default=9700, help=\
        'Serving port, default: 9700')
    parser.add_argument('-s','--swing', type=float, default=1., help=\
        'Relative amplitude in %% of the horizontal peak oscillations')
    parser.add_argument('-v','--verbose', nargs='*', help='Show more log messages.')
    pargs = parser.parse_args()

    pargs.background = [float(i) for i in pargs.background.split(',')]
    pargs.peaks = [float(i) for i in pargs.peaks.split(',')]

    liteserver.Server.Dbg = 0 if pargs.verbose is None else len(pargs.verbose)+1
    devices = [Dev('dev1', no_float32=pargs.doubles)]

    server = liteserver.Server(devices, interface=pargs.interface,
        port=pargs.port)

    print('`'*79)
    print(f"To monitor, use: pvplot -s.01 -a'L:{server.host};{pargs.port}:dev1' 'x,y'")
    print(','*79)
    server.loop()
