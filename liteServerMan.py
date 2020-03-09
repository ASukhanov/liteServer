#!/usr/bin/env python3
'''Bridge from a liteServer to ADO.
ADO manager, which accepts all variables of a given liteServer and post them
in an ADO.
'''
#__version__ = 'v21 2019-12-10'# if not measurements: return
#__version__ = 'v22 2020-02-21'# for liteServer rev3
#__version__ = 'v23 2020-03-03'# do not set shape for 1-dimensional numpy array, otherwise right click in PET kills the manager
__version__ = 'v24 2020-03-07'# Retrieve data asynchronously

import time, argparse
from cad import ampy
import liteAccess as LA
import sys

Subscription = True# Retrieve data asynchronously
#````````````````````````````Helper methods```````````````````````````````````
def printi(msg): print('info: '+msg)
def printw(msg): print('WARNING: '+msg)
def printe(msg): print('ERROR: '+msg)
def printd(msg): 
    if pargs.dbg: print('DBG_LS :'+msg) 

# maps for parameter conversions from Lite to ADO 
ldo2parFeatureMap = {'R':ampy.CNSF_R,'W':ampy.CNSF_WE,'A':ampy.CNSF_ARCHIVE}
ldo2parTypeMap = {type('0'):'StringType',type(u'0'):'StringType'\
    ,type(0):'IntType',type(0.):'DoubleType',type(True):'VoidType'\
    ,'uint8':'UCharType', 'float32':'DoubleType', 'float64':'DoubleType'}
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Manager object```````````````````````````````````
class Mgr(ampy.ampyClass): # inherits from ampyClass
    def add_more_parameters(self):
        
        self.updatePeriodS = self.add_par('updatePeriodS','DoubleType',1,0,\
          ampy.CNSF_ARCHIVE,pargs.update)
        self.updatePeriodS.set = self.updatePeriodS_set
                
        # create ADO parameters, based on received allLdo parameters
        self.par2ldo = {}# mapping of ado parameters to allLdo PVs
        self.ldo2par = {}# reversed
        LA.LdoPars.Dbg = pargs.dbg
        ldo = pargs.ldo.split(',')
        self.allLdo = LA.LdoPars([[ldo,'*']]\
        ,timeout=pargs.timeout)
        allLdoInfo = list(self.allLdo.info().values())[0]
        allLdoVals = list(self.allLdo.get().values())[0]
        print('Bridged parameters:\n'+str(allLdoVals.keys()))
        for lParName,parVal in allLdoVals.items():
            parInfo = allLdoInfo[lParName]
            initialValue,ts = parVal['v'],parVal['t']
            
            # convert Lite features to ADO features
            ldoFeatures = parInfo['features']
            adoFeatures = 0
            for c in ldoFeatures:
                try:
                    adoFeatures |=  ldo2parFeatureMap[c]
                except:
                    printw('unknown features '+ldoFeatures)
            if 'legalValues' in parInfo:
                adoFeatures |= ampy.CNSF_D
            
            # make type of the ado parameter from first element of initialValue
            shape = None

            #print('par',lParName,initialValue,type(initialValue[0]))  
            try:
                ptype = ldo2parTypeMap[type(initialValue[0])]
            except Exception as e:
                ndarray = initialValue
                if 'numpy' in str(type(ndarray)):
                    shape = ndarray.shape
                    #print('ndarray',ndarray.shape,str(ndarray.dtype))
                    if len(shape) == 1: shape = None# otherwise issue in Pet
                    #initialValue = tuple(ndarray.flatten())
                    initialValue = ndarray.flatten().tolist()
                    ptype = ldo2parTypeMap[str(ndarray.dtype)]
                else:
                    printw('unknown type of %s:'%lParName+str(initialValue))
                    print(str(e))
                    continue
            
            # create ADO parameter and add it to par2ldo and ldo2par maps
            parName = lParName# ADO Name is the same as LDO parName
            l = len(initialValue) 
            iv = initialValue if l > 1 else  initialValue[0]
            #print('adding par '+str((parName,ptype,l,0,adoFeatures,iv))[:150])
            par = self.add_par(parName,ptype,l,0,adoFeatures,iv)
            if 'legalValues' in parInfo:
                par.add('legalValues',str(','.join(parInfo['legalValues'])))
            if shape:
                #par.add('shape',str(shape))
                par.addProperty( "shape", 'IntType', 3, 0, 0, shape)
            self.par2ldo[par] = LA.LdoPars([[ldo,lParName]])
            self.ldo2par[lParName] = par
            
            # establish the setting action
            if 'W' in ldoFeatures:
                #par.set = lambda _: self.par_set(par)# that does not work

                # define setting function for parameter
                def f(ppmIndex,mgr=self,par=par):
                    return mgr.par_set(par)
                par.set = f # override set() for farameter
        #print('ldo2par',self.ldo2par)

        if Subscription:
            # subscribe to all LDO parameters
            print('subscribing to '+str(self.allLdo.name))
            self.allLdo.subscribe(self.callback)
                        
    def run_startx(self):
        self.updatePeriodS_set()
    
    def par_set(self,par):
        """Setter for an ado parameter"""
        v = par.value.value
        #print('par_set %s, '%str(par) + str(v))
        # make the value a list
        ldo = self.par2ldo[par]
        print('assigning %s='%str(ldo.name)+str(v))
        ldo.value = [v]
        return 0
    
    def _update_pars(self,measurements):
        """update ADO parameters from measurements"""
        oldStatus = self.adoStatus.value.value
        self.adoStatus.value.value = 'OK'
        printd('msmnts\n'+str(measurements))
        for item,value in measurements.items():
            #print('measure par %s, keys=%s'%(item,str(value.keys())))
            par = self.ldo2par[item]
            v = value['v']
            ts = value['t']
            parTS = par.timestampSeconds.value + par.timestampNanoSeconds.value*1e-9
            #print('lts,pts',item,ts,parTS)
            if abs(ts - parTS) < 0.01:
                #print('timestamp of %s did not cnange'%item)
                continue
            lv = len(v)   
            if lv == 1: 
                v = v[0]
            else:
                # check if it is numpy array, just try to flatsten it
                try:
                    flatArray = v.flatten()
                    v = flatArray.tolist()
                    #print('update numpy array '+par.name)
                except:
                    #print('not numpy '+par.name)
                    pass
            #print('update_par %s,%s ='%(par.name,type(v))+str(v))
            try:
                self.update_par(par,v,timestamp=ts)
            except Exception as e:
                #msg = 'in update_par %s,%s:'%(par.name,str(v))+str(e)
                msg = 'in update_par %s:'%par.name+str(e)
                printe(msg)
                self.update_adoStatus('ERR:'+msg)
                continue         
        if oldStatus != 'OK' and self.adoStatus.value.value == 'OK':
            self.update_adoStatus()

    if Subscription:
      def callback(self,reply):
        printd('>callback(%s)'%str(reply.values()))
        self._update_pars(list(reply.values())[0])
    else:
      def periodic_update(self):
        
        # get all measurable data from server using measurements() method
        measurements = self.allLdo.read()
        if not isinstance(measurements,dict):
            raise RuntimeError('measurements: '+str(measurements))
        #print('measurements: '+str(measurements))

        # update ADO parameters with measurements
        measDict = list(measurements.values())[0]
        self._update_pars(measDict)        
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #````````````````````````Setters``````````````````````````````````````````
    def updatePeriodS_set(self,*args,**kwargs):
        self.periodicUpdateSleep = self.updatePeriodS.value.value
        print('update period changed to %.2f'%self.periodicUpdateSleep)
        return 0
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Main`````````````````````````````````````````````
#if __name__ == "__main__":
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-d','--dbg', action='store_true', 
  help='turn on debugging')
parser.add_argument('-i','--instance', 
  help='instance of the manager')
parser.add_argument('-l','--ldo', default = 'Scaler1,dev1',
  help='source LDO, name service provided by liteCNS.py')
parser.add_argument('-u','--update',type=float, default=1.,
  help='Period (s) of the parameter updates')
parser.add_argument('-t','--timeout',type=float, default=0.1,
  help='Timeout for receiving socket')
parser.add_argument('mgrName', nargs='?', default='liteServerMan',
  help='manager name should be registered by the fecManager')
pargs = parser.parse_args()
aname = pargs.mgrName.replace('Man','')
pargs.adoName = aname + '.0'

if pargs.instance != None:
    pargs.adoName = aname + '.'+pargs.instance
    pargs.mgrName += '_'+pargs.instance

# instantiate the ampy object, generic ADO Manager
print('mgr,ado',pargs.mgrName,pargs.adoName)
from cad import pyado
mgr = Mgr(debug=10 if pargs.dbg else 12, 
    mgrName = pargs.mgrName,
    adoName = pargs.adoName,
    version = __version__,
    description = ' A'[Subscription]+'synchronous bridge to LDO '\
    +str(pargs.ldo),
    periodicUpdate = pargs.update, # period of calling the periodic_update()
   )
#````````````````````````Manager event loop```````````````````````````````
try:
    mgr.loop()
except KeyboardInterrupt:
    print('KeyboardInterrupt exception, cleanup and exit.')
    mgr.eventExit.set()
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,

