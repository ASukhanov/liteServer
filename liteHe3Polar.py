#!/usr/bin/env python3
"""liteServer for He3 Polarization Measurements"""
#__version__ = 'v01 2020-02-24'# adopted from he3PolarMan
__version__ = 'v02 2020-02-29'# 

import sys
import time
from collections import OrderedDict
from timeit import default_timer as timer
import numpy as np
from scipy.signal import argrelextrema
import threading

import liteServer
LDO = liteServer.LDO
Device = liteServer.Device
EventExit = liteServer.EventExit

#EventPocessingFinished = threading.Event()
#EventExit = threading.Event()
#EventCommand = threading.Event()

mgr = None
eventData = []

#````````````````````````````Readout channels`````````````````````````````````
'''
# List of all available channels in hardware (not all of them will be posted)
gDataSets = OrderedDict([
  ('responseM', {'cmd':'Q',  'features':ampy.CNSF_R,
    'desc':'Output of the Lock-In Amplifier [V]'}),
  ('ADC0M',     {'cmd':'X1', 'features':ampy.CNSF_R,  
    'desc':'ADC0 (backplane X1) input [V]'}),
  ('stimulusM', {'cmd':'X2', 'features':ampy.CNSF_R,
    'desc':'Applied to change laser frequency, (backplane X2 [V]'}),
  ('ADC2M',     {'cmd':'X3', 'features':ampy.CNSF_R,
    'desc':'ADC2 (backplane X3) input [V]'}),
  ('ADC3M',     {'cmd':'X4', 'features':ampy.CNSF_R,
    'desc':'ADC3 (backplane X4) input [V]'}),
  ('stimulGenS',     {'cmd':'X5', 'features':ampy.CNSF_RWE,
    'desc':'DAC output on backpLane X5, Internally generated stimulus'}),
  ('DAC1S',     {'cmd':'X6', 'features':ampy.CNSF_RWE,
    'desc':'DAC output on backpLane X6 [V]'}),
])

# ADO-served parameters
AnalysisChannels = {'x':'stimulGenS','y':'responseM'}
#InputChannels = ['responseM','stimulusM']
InputChannels = ['responseM',]
OutputChannels = ['stimulGenS']#,'DAC1S']

#````````````````````````````Necessary explicit globals```````````````````````
pargs = None# program arguments
'''
#````````````````````````````Helper functions and classes`````````````````````
def printi(msg): print('info: '+msg)
def printw(msg): print('WARNING: '+msg)
def printe(msg): print('ERROR: '+msg)
def printd(msg,level=10):
    if mgr is None or mgr.adoDebug.value.value <= level:
        print('dbg: '+msg)
def printd1(msg):
    printd(msg,level=9)
def printd2(msg):
    printd(msg,level=8)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````For fitting``````````````````````````````````````
from scipy.optimize import curve_fit
NPeaks = 2 
RankBckg = 0 # rank of the baseline polinom, 0: constant, 1:linear, 2: not recommended 
FGX = [RankBckg+1,RankBckg+4]# fitGuess index of X0,1
FGS = [RankBckg+2,RankBckg+5]# fitGuess index of Sigma0,1
FGY = [RankBckg+3,RankBckg+6]# fitGuess index of Y0,1
#          base, X0,  S0,  Y0,    X1,  S1,  Y1,
simulPars = [0.0, 0.0, 0.2, 0.002, 0.0, 0.2, 0.002] # guess parameters
#fitBounds = [[-np.inf,np.inf]*len(fitGuess)]

def peak_shape(xx, halfWidth):
    """Function, representing the peak shape,
    It should be in a performance-optimized form.
    The halfWidth = sqrt(2)*sigma.
    """
    try: r = np.exp(-(xx/halfWidth)**2) 
    except: r = np.zeros(len(x))
    return r
def peak_shape(xx, halfWidth):
    """Function, representing the peak shape,
    It should be in a performance-optimized form.
    """
    try: r = np.exp(-0.5*(xx/halfWidth)**2) 
    except: r = np.zeros(len(xx))
    return r
def func_sum_of_peaks(xx, *par):
    # Fitting function: baseline and sum of peaks.
    RankBckg = 1 # linear baseline
    s = np.zeros(len(xx)) + par[0]
    # RankBckg = 3 # for quadratic baseline
    #s = par[0] + par[1]*xx + par[2]*xx**2
    for i in range(RankBckg,len(par),3):
        s += par[i+2]*peak_shape(xx-par[i],par[i+1])
    return s    
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#`````````````````````````````Wavelength Meater readout```````````````````````
'''
wlmHost,wlmPort = '130.199.85.188',9999
wlmPV = 'WLM1:frequency'
import liteAccess_v07 as liteAccess
access = liteAccess.LiteAccess((wlmHost,wlmPort))
def read_wavelength_meter():
    try:
        r = access.get(wlmPV)[wlmPV]
    except Exception as e:
        r = []
    return r
'''
#````````````````````````````Device interface`````````````````````````````````
import serial # RS232 interface
class Interface():
    def open(self):
        rt = 0.04 # 0.2 have the same issues
        self.ser = serial.Serial('/dev/ttyS0', 19200, timeout=rt,\
          stopbits = serial.STOPBITS_TWO, #inter_byte_timeout=0.1,
          xonxoff=False, rtscts=True, dsrdtr=True)
        print(self.ser.name+', '+str(self.ser.bytesize)\
          +', '+str(self.ser.stopbits)+', timeout:'+str(self.ser.timeout))
        self.connected = False

    def close(self):
        self.ser.close()
        
    #def printRts(self):
    #    print('rts,cts,dtr,dsr:'+str([int(i) \
    #      for i in (self.ser.rts,self.ser.cts,self.ser.dtr,self.ser.dsr)]))

    def write(self,data):
        #self.printRts()
        printd1('serial: writing:'+str(data))
        encoded = (data+'\r\n').encode()
        self.ser.write(encoded)

    def readline(self):
        #self.printRts()
        try:
            r = self.ser.readline()
        except Exception as e:
            printe('SRS: in readline:'+str(e))
            return ''
        #print('serial: reading:\n'+str(r))
        if len(r) < 2:
            printd2('No response from SRS:'+str(r))
        return r
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Hardware abstraction`````````````````````````````
class Plant():
    """Base class for hardware access. it simulates response.
    All methods, except state_machine should be overridded by derived classes.
    """
    def __init__(self):
        self.data = None
        self.timestamp = None

    def send_value(self,value):
        y = func_sum_of_peaks([value], simulPars)
        # add 10% of noise
        y += 0.1*simulPars[FGY[0]]*np.random.random()
        self.v = round(float(y[0]),9)
        
    def read_back(self):
        return self.v

#````````````````````````````Hardware specific````````````````````````````````
class Plant_SRS_Lock_In_AMplifier(Plant):
    """SRS-510 Lock-In Amplifier"""
    def __init__(self):
        #super(Plant_SRS_Lock_In_AMplifier, self).__init__()
        print('initializing SRS_Lock_In_AMplifier')
        self.iface = Interface()
        self.iface.open();
        self.lastWritten = None
        
        r = self.iface.readline()
        if len(r):
            print('unread data:'+str(r))
            
        cmd = 'W0;W' # set RS232 to minimal delay 
        self.iface.write(cmd)
        r = self.iface.readline()
        print('response to command '+cmd+':'+str(r))
        
    def send_value(self,value,channel='stimulGenS'):
        self.lastWritten = gDataSets[channel]['cmd']+',%.3f'%value
        self.iface.write(self.lastWritten)
        
    def readBack(self,channels=('ADC0',)):
        """ Read several channels, [1,2,3] translates to 'X1;X2;X3'
        returns list of values."""
        cmd = ';'.join([gDataSets[i]['cmd'] for i in channels])
        self.iface.write(cmd)# request new data
        r = self.iface.readline()
        #print('cmd,readline',cmd,r)
        reread = False
        if len(r) == 0:
            printd2('rereading '+cmd+', last written: '+str(self.lastWritten))
            self.iface.write(cmd)
            r = self.iface.readline()
            if len(r) > 0:
                reread = True
            else:
                if self.lastWritten is not None:
                    printd2('reread failed, repeating the command')
                    self.iface.write(self.lastWritten)
                    self.iface.write(cmd)
                    r = self.iface.readline()
                    if len(r) == 0:
                        printe('rewriting failed')
                        r = 0
                    else:
                        printd2('rewrite ok:'+str(r))
        # we may get \x8d at the end, strip it out
        line = r[:-1]
        try:
            v = [float(i) for i in line.split()] 
        except Exception as e:
            printe('float conversion of "'+str(line)+'"')
            v = []
        if reread:
            printd2('reread OK:'+str(v))
        #self.iface.write(cmd)# request new data
        return v

    def execute_command(self,cmd):
        printd('executing "'+str(cmd)+'"')
        self.iface.write(cmd)
        return self.iface.readline()
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#`````````````````````````````````````````````````````````````````````````````
class Mgr(Device):
    def __init__(self,name):
        nPoints = 100
        pars = {
        'nSteps':     LDO('RW','Number of steps/cycle',[nPoints]),
        'sleep':      LDO('W','Delay between cycles [s]', [1.]),
        'stimulus':   LDO('RW','Applied signal', [0.]*nPoints),
        'stimulRange':LDO('RW','Lower and upper limits of the local stimulus'\
        , [.0, 3.]),
        'response':   LDO('R','Response', [0.]*nPoints),
        'devCommand': LDO('W','Command to Lock-In Amplifier', ['X5']),
        'devReply':   LDO('R','Reply from Lock-In Amplifier', ['']),
        #'perf':       LDO('R','Performance counters', [0]*5),
        'guess':      LDO('W',('Guess of fit parameters: base, stimulus'\
        ' value, sigma, amplitude of two peaks'), simulPars),
        'guessMode':  LDO('W',('Guess of fit parameters, manually provided'\
        ' or automatic'),['Auto'], legalValues=['Auto','Fixed']),
        'peakPosMode':LDO('W','Peak position treatment: Auto/Fixed'\
        , legalValues=['Auto','Fixed']),
        'localStimulus':LDO('W','Enable local stimulus on X5 output'\
        , ['Triangular'], legalValues=['Disabled','Triangular','Sawtooth']),
        'analysis':   LDO('W','Enable/disable analysis',['Off']\
        , legalValues=['Off','On']),
        'polarMeasure':LDO('W','Reference,Hold,Polarization',['Reference']\
        , legalValues=['Reference','Hold','Polarization']),
        'polarRef':   LDO('R','Polarization reference',[0.]),
        #'waveMeter':  LDO('W','',['Disabled']\
        #, legalValues=['Disabled','Enabled']),
        #'frequency':  LDO('R','Frequency from remote WLM',[0.]),
        #'wlmTDiff':   LDO('R','Timestamp difference of Amp and WLM',[0.]),
        #'wlmRoundTripTime': LDO('R','Readout time of the WaveLength Meter'\
        #, [0.]),
        'responseScale': LDO('W','Scaling factor for response signal',[1.]),
        }
        '''
        'fittedPars': LDO('R','Fitted parameters',[0.]*len(self.fitGuess)),
        self.fittedParsM = []
        self.ratioM = []
        d = 'Frequency-based','DAC-based'
        for i in range(2):
            self.fittedParsM.append(self.add_par('fittedParsM'+str(i),
              'DoubleType',len(self.fitGuess), 0, ampy.CNSF_R,[0]*len(self.fitGuess)))
            self.fittedParsM[i].add('desc',d[i]+' Fitted parameters: base. '\
              +'stimulus value, sigma, amplitude of two peaks')
              
            self.ratioM.append(self.add_par('ratioM'+str(i),
              'DoubleType',1,0,ampy.CNSF_R,0))
            self.ratioM[i].add('desc','Amplitude ratio of two peaks, '+d[i])
        self.ratioSlidingWindow = np.zeros(5)
        self.localStimulS_set()
        self.polarS.set = self.polarS_set

        self.polarM = []
        for i in range(2):
            self.polarM.append(self.add_par('polarM'+str(i),'DoubleType',1,0,
              ampy.CNSF_R,0))
            self.polarM[i].add('desc','Measured polarization. '+d[i])

        self.wlmRoundTripTimeM = self.add_par('wlmRoundTripTimeM','DoubleType',1,0,ampy.CNSF_R,0)
        self.wlmRoundTripTimeM.add('desc','Readout time of the WaveLength Meter')
  
        self.responseScaleS = self.add_par('responseScaleS','DoubleType',1,0,
          ampy.CNSF_ARCHIVE,1.)
        self.responseScaleS.add('desc','Scaling factor for response signal')
        
        self.signS = self.add_par('signS','StringType',1,0,
          ampy.CNSF_D | ampy.CNSF_ARCHIVE,'Positive')
        self.signS.add('legalValues', 'Positive,Negative')
        
        self.averBox = np.ones(4)/4.# averaging box
        
        self.cropBorders = (10,5)# remove number of points at the (beginning,end) from analysis
        }
        '''
        super().__init__(name,pars)
        
        self.plant = Plant()
        
        #print('n,p',self._name,pars)
        thread = threading.Thread(target=self._state_machine)
        thread.daemon = True
        thread.start()

    #````````````````````````overloaded methods```````````````````````````````
    def _state_machine(self):
        time.sleep(.2)# give time for server to startup
        self._cycle = 0
        
        print('State machine started')
        while not EventExit.is_set():
            EventExit.wait(self.sleep.v[0])
            idling = self.serverState()[:5] != 'Start'
            if idling:
                continue

            if self._cycle%100 == 0:#Status report through server.status
                self.setServerStatusText('Cycle %i on '%self._cycle+self._name)
            self._cycle += 1

            for backward in (0,1):
                self.stimulus.v = self.generate_localStimulus(backward)
                self.stimulus.t = time.time()

                for i,x in enumerate(self.stimulus.v):
                    self.plant.send_value(x)
                    y = self.plant.read_back()
                    self.response.v[i] = y
                self.response.t = time.time()
                    
                EventExit.wait(self.sleep.v[0])
        print('state_machine'+self._name+' exit')

    def generate_localStimulus(self,backward):
        rng = self.stimulRange.v
        stimulShape = self.localStimulus.v[0]
        if rng[0] < -5. or rng[1] > 5.:
            self.setServerStatusText("ERR: Range should be in [-5,5]")
            return
        self.rampPtr = 0
        nPoints = int(self.nSteps.v[0])
        if  stimulShape == 'Triangular':
            x = np.linspace(rng[0], rng[1], nPoints + 1)
            if backward:
                x = np.flip(x)
        elif strimulShape == 'Sawtooth':
            x = np.linspace(rng[0], rng[1], nPoints+1)
            if backward:
                x = np.linspace(rng[1], rng[0], 3)
        return [round(float(i),3) for i in x[:nPoints]]

        '''
            if self.localStimulS.value.value != 'Disabled':
                v = self.rampForm[self.rampPtr]
                self.plant.send_value(v,'stimulGenS')
                self.rampPtr += 1
                if self.rampPtr >= len(self.rampForm):
                    self.rampFinished = True
                    self.rampPtr = 0
                self.update_par(self.par['stimulGenS'],v)
                
            # all updated parameters will have this timestamp
            self.timestamp = time.time()

            #self.event.wait(self.sleepS.value.value)
            self.eventExit.wait(self.sleepS.value.value)
            if self.eventExit.isSet():
                break
            
            # read the lock-in amplifier data
            self.data = self.plant.get_data()
            
            # read the laser wavemeter
            if self.waveMeterS.value.value == 'Enabled':
                ts = timer()
                r = read_wavelength_meter()
                self.update_par(self.wlmRoundTripTimeM,timer()-ts)
                if len(r) == 0:
                    if not wlmReported:
                        wlmReported = True
                        self.update_par(self.adoStatus,'ERR: No waivemeter data')
                else:
                    if wlmReported:
                        wlmReported = False
                        self.update_par(self.adoStatus,'Wavemeter is back')
                    wlmTs,self.frequencyM.value.value = r
                    self.wlmTDiffM.value.value = wlmTs - time.time()
                    #print('wlm',self.frequencyM.value.value,self.wlmTDiffM.value.value)
                    self.update_par(self.frequencyM)
                    self.update_par(self.wlmTDiffM)

            # process data
            if len(self.data):
                self.process_data()
            EventExit.wait(self.sleep.v[0])
            if self._pause:
                continue
            '''
    '''
    def periodic_update(self):
        printd1('sm stopped='+str(self.stopped)+', event:'+str(self.event.is_set()))

    def run_startx(self):
        print('>startx')
        try:
            self.plant
        except:
            # 
            self.plant = Plant_SRS_Lock_In_AMplifier()
            stateMachineThread = threading.Thread(target=self.stateMachine)
            try:
                stateMachineThread.start()
            except Exception as e:
                printe('stateMachine:'+str(e))
            print('plant:',self.plant)
            return
        printe('plant already exist')
        return

    def run_stopx(self):
        printi('>stopx')
        #self.event.set()
        try:
            del self.plant
        except:
            printe('deleting plant')
        self.update_par(self.adoStatus,'Run stopped, RS232 closed')
    
    #````````````````````````Set methods``````````````````````````````````````
    def devCommandS_set(self,*args):
        if not self.stopped:# we need idle the state machine during command execution
            printi('idle the state machine for a second')
            self.idle = True
            time.sleep(.5)
        self.plant.readline()# to purge a buffer
        r = self.plant.execute_command(self.devCommandS.value.value)
        if self.idle:
            self.idle = False
            printi('un-idle the state machine')            
        self.update_par(self.devReplyM,str(r.split()))
        return 0
        
        
    def polarS_set(self,*args):
        if self.polarS.value.value == 'Reference':
            lsw = len(self.ratioSlidingWindow)
            self.ratioSlidingWindow = np.zeros(lsw)
            self.update_par(self.polarRefM,0.)
            for par in self.polarM:
                self.update_par(par,0.)
        self.update_par(self.cycleNM,0)
        return 0
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #````````````````````````State machine````````````````````````````````````
    def stateMachine(self):
        """ The manager's state machine"""
        print('state machine started')
        wlmReported = False
        self.rampFinished = False
        self.halfRampCrossed = False
        while not self.eventExit.isSet():
            if self.stopped:
                break
            if self.idle:
                self.eventExit.wait(1)
                continue

            # change stimulus
            if self.localStimulS.value.value != 'Disabled':
                v = self.rampForm[self.rampPtr]
                self.plant.send_value(v,'stimulGenS')
                self.rampPtr += 1
                if self.rampPtr >= len(self.rampForm):
                    self.rampFinished = True
                    self.rampPtr = 0
                self.update_par(self.par['stimulGenS'],v)
                
            # all updated parameters will have this timestamp
            self.timestamp = time.time()

            #self.event.wait(self.sleepS.value.value)
            self.eventExit.wait(self.sleepS.value.value)
            if self.eventExit.isSet():
                break
            
            # read the lock-in amplifier data
            self.data = self.plant.get_data()
            
            # read the laser wavemeter
            if self.waveMeterS.value.value == 'Enabled':
                ts = timer()
                r = read_wavelength_meter()
                self.update_par(self.wlmRoundTripTimeM,timer()-ts)
                if len(r) == 0:
                    if not wlmReported:
                        wlmReported = True
                        self.update_par(self.adoStatus,'ERR: No waivemeter data')
                else:
                    if wlmReported:
                        wlmReported = False
                        self.update_par(self.adoStatus,'Wavemeter is back')
                    wlmTs,self.frequencyM.value.value = r
                    self.wlmTDiffM.value.value = wlmTs - time.time()
                    #print('wlm',self.frequencyM.value.value,self.wlmTDiffM.value.value)
                    self.update_par(self.frequencyM)
                    self.update_par(self.wlmTDiffM)

            # process data
            if len(self.data):
                self.process_data()
                                
        printi('state machine stopped')
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #````````````````````````Data processing methods``````````````````````````
    def ramp_is_finished(self):
        if self.rampFinished:
            self.rampFinished = False
            self.halfRampCrossed = False
            return True
        elif not self.halfRampCrossed and self.rampPtr >= self.halfRamp:
            self.halfRampCrossed = True
            return True
        return False

    def process_data(self):
        printd1('processing: '+str(self.data))
        for i,val in enumerate(self.data):
            if InputChannels[i] == 'responseM':
                val = val * self.responseScaleS.value.value
            self.update_par(self.par[InputChannels[i]],val)
        rampV = self.par[AnalysisChannels['x']].value.value
        y = self.par[AnalysisChannels['y']].value.value
        
        # check if data OK for analysis
        if self.analysiS.value.value != 'On':
            self.anList = [[],[]]
            self.cycleNM.value.value = 0
            return
            
        # fill the analysis arrays
        i = 0
        if self.waveMeterS.value.value == 'Enabled':
            self.anList[0].append((self.frequencyM.value.value,y))
            i = 1
        self.anList[i].append((rampV,y))

        if not self.ramp_is_finished():
            return
        # ramp is finished, disregard the first sweep
        if self.cycleNM.value.value <= 0:
            self.cycleNM.value.value = 1
            return
        if len(self.anList[0]) < 10:
            printw('Too few points in the ramp: %d'%len(self.anList[0]))
            return
        
        # data are OK for analysis
        print('ramp Point:%d'%self.rampPtr+', analysis list:%d'%len(self.anList[0]))
        #for iFit in range(2): # Nobody interested in second analysis
        for iFit in range(1):
            if len(self.anList[iFit]) == 0:
                continue
            
            if self.waveMeterS.value.value == 'Enabled' and iFit == 0:     
                # expected peak width in frequency domain is 0.02 (THz)
                for i in FGS:
                   self.fitGuess[i] = 0.0015
            else:
                # expected peak width in stimulus domain is 0.2V
                for i in FGS:
                    try:
                        self.fitGuess[i] = 0.2
                    except:
                        printe('changing self.fitGuess:',self.fitGuess)
                        continue
                
            fp = self.analyze(np.array(self.anList[iFit]))
            if len(fp) == 0:
                continue
            #````````````````````update all parameters
            self.update_par(self.fittedParsM[iFit],fp)
            ratio = fp[3]/fp[6]
            self.update_par(self.ratioM[iFit],ratio)
            #if iFit == 0:
            if self.polarS.value.value == 'Polarization':
                # update polarization
                r0 = self.polarRefM.value.value
                #polar = abs((ratio - r0))/(ratio + r0)*100.
                try:
                    sign = {'Positive':1.,'Negative':-1.}[self.signS.value.value]
                except Exception as e:
                    printe('in sign:'+str(e))
                    sign = 1.
                polar = sign*(ratio - r0)/(ratio + r0)*100.
                self.update_par(self.polarM[iFit],polar)
            elif self.polarS.value.value == 'Reference':
                if iFit == 0:
                    # accumulate reference
                    sw = self.ratioSlidingWindow
                    sw[:-1] = sw[1:]
                    sw[-1] = ratio
                    self.update_par(self.polarRefM,sw.sum()/np.count_nonzero(sw))            
            
        self.anList = [[],[]]
        self.cycleNM.value.value +=1
        self.update_par(self.cycleNM)
        print('cycle:%d'%self.cycleNM.value.value)      
        #EventPocessingFinished.set()        
                
    def analyze(self,ar):
        #print('>analysis of %d points'%len(ar)+', shape:'+str(ar.shape))
        left,right = self.cropBorders
        xr = ar[left:-right,0]
        yr = ar[left:-right,1]
        printd('xr:'+repr(xr))
        printd('yr:'+repr(yr))
        
        #````````````````````find peaks
        try: # smooth data slightly for peak finding
            yrSmoothed = np.convolve(yr, self.averBox, mode='same')
        except:
            printe('in convolve: array length = %d'%len(yr))
            return []
        
        # find extrema
        piDirty = argrelextrema(yrSmoothed,np.greater_equal,order=10)[0]# 20 is too wide
        printd('dirty:'+repr(piDirty))
        # remove flattops
        try:
            peakIdx = np.array([i for i in piDirty if yrSmoothed[i] != yrSmoothed[i+1]])
        except:
            peakIdx = np.array(piDirty)
        printd('extrema:'+repr((xr[peakIdx],yrSmoothed[peakIdx])))
        if len(peakIdx) < 2:
            printw('Failed to find 2 extrema')
            return []
        
        # keep 2 highest peaks and arrange peaks along X    
        h2Ysorted = np.argsort(yrSmoothed[peakIdx])[-2:]
        printd('h2Ysorted:'+repr((peakIdx[h2Ysorted],xr[peakIdx[h2Ysorted]],yrSmoothed[peakIdx[h2Ysorted]])))
        xrYsorted = xr[peakIdx[h2Ysorted]]
        yrYsorted = yrSmoothed[peakIdx[h2Ysorted]]
        printd('x,y Ysorted:'+repr((xrYsorted,yrYsorted)))
        axs = np.argsort(xrYsorted)
        printd('axs:'+repr(axs))
        xr2h = xrYsorted[axs]
        yr2h = yrYsorted[axs]
        printd('x,y, 2h:'+repr((xr2h,yr2h)))
        
        # adjust guess peak positions
        if self.guessModeS.value.value == 'Auto':
            for ip in range(NPeaks):
               self.fitGuess[FGX[ip]] = xr2h[ip]
               self.fitGuess[FGY[ip]] = yr2h[ip]
            self.update_par(self.guessS,self.fitGuess)
        else:
            self.fitGuess = list(self.guessS.value.value)
        print('fg :'+''.join(['%.5f, '%i for i in self.fitGuess]))
        
        #````````````````````Fit with base and two gaussian
        try:
            if self.peakPositionS.value.value == 'Auto':
                fp,pcov = curve_fit(func_sum_of_peaks,xr,yr,self.fitGuess)
                relStdevs = np.sqrt(np.diag(pcov))/abs(fp)
            else:
                # Fix parameters.
                # remove parameters from function and self.fitGuess
                # reduced guess:
                fgr = [i for i in self.fitGuess if self.fitGuess.index(i) not in FGX]
                # reduced function, assuming RankBckg=1
                fpr,pcov = curve_fit(lambda x,p0,p2,p3,p5,p6:\
                  func_sum_of_peaks(x,p0,self.fitGuess[1],p2,p3,self.fitGuess[4],p5,p6),
                  xr,yr,fgr)
                relStdevs = list(np.sqrt(np.diag(pcov))/abs(fpr))
                # inflate the fp with fixed parameters
                fp = list(fpr)
                fp.insert(FGX[0],self.fitGuess[FGX[0]])
                fp.insert(FGX[1],self.fitGuess[FGX[1]])
                # the same with relStdevs
                relStdevs.insert(FGX[0],0.)
                relStdevs.insert(FGX[1],0.)
                
            if True in np.isinf(relStdevs) or True in np.isnan(relStdevs):
                printw('Fit failed')
                return []
        except Exception as e:
            printw('Fit exception:'+str(e))
            return []
        print('fp :'+''.join(['%.6f, '%i for i in fp]))
        print('err:'+''.join(['%.6f, '%i for i in relStdevs]))
        if max(relStdevs) >= 1.:
            badParIdx = np.argmax(relStdevs)
            if abs(fp[badParIdx]) > 1.e-4:
                printw('High standard deviation of parameter '+str(badParIdx))
                return []
        return fp
        
        #yf = func_sum_of_peaks(xr,*fp)
        #self.plotDataItems['Fit'].setData(xr,yf,pen='r',symbol=None)
    '''
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Program``````````````````````````````````````````
import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-d','--dbg', action='store_true', help='Debugging mode')
pargs = parser.parse_args()

liteServer.Server.Dbg = pargs.dbg
devices = [Mgr('He3Polar')]

print('Serving:'+str([dev._name for dev in devices]))

server = liteServer.Server(devices)
server
server.loop()

