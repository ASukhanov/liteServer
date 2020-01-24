#!/usr/bin/env python3
'''Bridge from a liteServer to ADO.
ADO manager, which accepts all variables of a given liteServer and post them
in an ADO.
'''
#__version__ = 'v01 2018-12-31'# created
#__version__ = 'v02 2018-12-31'# reaction to returned string in periodic_update
#__version__ = 'v03 2019-01-02'# 'features' handled
#__version__ = 'v04 2019-01-03'# timestamp stripped out from data
#__version__ = 'v05 2019-01-03'# set method is working, it is implemented using Setter class, which keeps the parameter and manager objects
#__version__ = 'v06 2019-01-04'# action parameter is OK,
#__version__ = 'v07 2019-01-05'# check in line 110
#__version__ = 'v08 2019-01-06'# default timeout = 0.1
#__version__ = 'v09 2019-01-15'# shrinked printout for lengthy parameters
#__version__ = 'v10 2019-01-17'# floating length of all vector parameters
#__version__ = 'v11a 2019-03-14'# better error handling
#__version__ = 'v12 2019-04-25'# better exception handling if server is dead 
#__version__ = 'v13 2019-04-30'# updatePeriodS added
#__version__ = 'v14 2019-11-26'# re-designed for new liteServer,liteAccess
#__version__ = 'v15 2019-11-26'# srict check of server reply, debugging
#__version__ = 'v16 2019-11-27'# exception handling for pvAccess.firstValue(), adoStatus cleanup
#__version__ = 'v17 2019-11-30'# establish the setting action, 'W' translates to 'CNSF_WE'
#__version__ = 'v18 2019-12-03'# legal values handled, shebang for python3
#__version__ = 'v19 2019-12-09'# numpy arrays supported, they have 'shape' feature
#__version__ = 'v20 2019-12-09'# PV['host'].info() now returns info on all PVs 
__version__ = 'v21 2019-12-10'# if not measurements: return

#TODO: discrete parameters
#TODO: test counters

import time, argparse, traceback
from cad import ampy
import liteAccess
import sys
import numpy as np

#````````````````````````````Helper methods```````````````````````````````````
def printi(msg): print('info: '+msg)
def printw(msg): print('WARNING: '+msg)
def printe(msg): print('ERROR: '+msg)
def printd(msg): 
    if pargs.dbg: print('DBG_LS :'+msg) 

# maps for parameter conversions from Lite to ADO 
pv2parFeatureMap = {'R':ampy.CNSF_R,'W':ampy.CNSF_WE,'A':ampy.CNSF_ARCHIVE}
pv2parTypeMap = {type('0'):'StringType',type(u'0'):'StringType'\
    ,type(0):'IntType',type(0.):'DoubleType',type(True):'VoidType'\
    ,'uint8':'UCharType',}
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Manager object```````````````````````````````````
class Mgr(ampy.ampyClass): # inherits from ampyClass
    def add_more_parameters(self):
        
        self.updatePeriodS = self.add_par('updatePeriodS','DoubleType',1,0,\
          ampy.CNSF_ARCHIVE,pargs.update)
        self.updatePeriodS.set = self.updatePeriodS_set
                
        # create ADO parameters, based on received liteServer parameters
        self.par2pv = {}# mapping of ado parameters to liteServer PVs
        hostPort = pargs.host+';%i'%pargs.port
        liteAccess.PV.Dbg = pargs.dbg
        self.pvServer = liteAccess.PV([hostPort], timeout=pargs.timeout)
        pvServerInfo = self.pvServer.info()
        deviceSet = {i.split(':')[0] for i in pvServerInfo.keys()}
        print('Devices on host '+self.pvServer.name+' :\n'+str(deviceSet))

        print('Bridged parameters:')
        for devParName,pardict in pvServerInfo.items():
            adoParName = devParName.replace(':','_')
            devName,parName = devParName.split(':')
            pvAccess = liteAccess.PV([hostPort,devName,parName])
            initialValue,ts = pvAccess.value
            #print('initValue of %s[%i]:%s...'%(adoParName,len(initialValue),str(initialValue)[:120]))
            
            # convert Lite features to ADO features
            pvFeatures = pardict['features']
            adoFeatures = 0
            for c in pvFeatures:
                try:
                    adoFeatures |=  pv2parFeatureMap[c]
                except:
                    printw('unknown features '+pvFeatures)
    
            if 'legalValues' in pardict:
                #print('legalValues in ',devParName)
                adoFeatures |= ampy.CNSF_D
            
            # make type of the ado parameter from first element of initialValue
            shape = None
            try:
                ptype = pv2parTypeMap[type(initialValue[0])]
            except Exception as e:
                ndarray = initialValue
                if 'numpy' in str(type(ndarray)):
                    shape = ndarray.shape
                    #print('ndarray',ndarray.shape,str(ndarray.dtype))
                    initialValue = tuple(ndarray.flatten())
                    ptype = pv2parTypeMap[str(ndarray.dtype)]
                else:
                    printw('unknown type of %s:'%devParName+str(initialValue))
                    print(str(e))
                    continue
            
            # create ADO parameter and add it to par2pv map
            l = len(initialValue) 
            iv = initialValue if l > 1 else  initialValue[0]
            print('adding par '+str((adoParName,ptype,l,0,adoFeatures,iv))[:150])
            par = self.add_par(adoParName,ptype,l,0,adoFeatures,iv)
            if 'legalValues' in pardict:
                par.add('legalValues',str(','.join(pardict['legalValues'])))
            if shape:
                #par.add('shape',str(shape))
                par.addProperty( "shape", 'IntType', 3, 0, 0, shape)
            self.par2pv[par] = pvAccess
            
            # establish the setting action
            if 'W' in pvFeatures:
                #par.set = lambda _: self.par_set(par)# that does not work

                # define setting function for parameter
                def f(ppmIndex,mgr=self,par=par):
                    return mgr.par_set(par)
                par.set = f # override set() for farameter
        self.pv2par = {v.devs[0]+':'+v.pars[0]: k for k, v in self.par2pv.items()}# reversed dict
        #print('pv2par',self.pv2par)
    
    def par_set(self,par):
        """Setter for an ado parameter"""
        v = par.value.value
        #print('par_set %s, '%str(par) + str(v))
        # make the value a list
        try:    l = len(v)
        except:
            v = [v]
            l = 1
        pv = self.par2pv[par]
        if isinstance(v,str): v = unicode(v)
        print('assigning %s='%str(pv.name)+str(v))
        pv.value = v
        return 0

    def periodic_update(self):
        oldStatus = self.adoStatus.value.value
        self.adoStatus.value.value = 'OK'
        
        # get all measurable data from server using measurements() method
        measurements = self.pvServer.measurements()
        if not measurements:
            return
        #print('measurements:')
        for item,value in list(measurements.items()):
            #print('measure pv '+item)#+': '+str(value))
            par = self.pv2par[item]
            v,ts = value['value'],value['timestamp']
            lv = len(v)   
            if lv == 1: 
                v = v[0]
            else:
                if lv != len(par.value.value):
                    # check if it is numpy array, just try to flatten it
                    try:
                        flatArray = v.flatten()
                        v = tuple(flatArray)
                        lv = len(v)
                        if lv != len(par.value.value):
                            raise ValueError('Bad, numpy array changed length')
                    except: # not numpy, something wrong
                        msg = 'length changed in %s: %s, was %s'%\
                        (par.name,repr(v),repr(par.value.value))
                        printe(msg)
                        self.update_adoStatus('ERR:'+msg)
                        continue
            if v != par.value.value:
                #print('update_par %s ='%par.name)#+str(v))
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
                
    def run_startx(self):
        self.updatePeriodS_set()
    #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
    #````````````````````````Setters``````````````````````````````````````````
    def updatePeriodS_set(self,*args,**kwargs):
        self.periodicUpdateSleep = self.updatePeriodS.value.value
        print('update period changed to %.2f'%self.periodicUpdateSleep)
        return 0
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Main`````````````````````````````````````````````
#if __name__ == "__main__":
description = 'Bridge from a liteServer to ADO.'
parser = argparse.ArgumentParser(description=description)
parser.add_argument('-d','--dbg', action='store_true', 
  help='turn on debugging')
parser.add_argument('-i','--instance', 
  help='instance of the manager')
parser.add_argument('-H','--host', default='acnlin23',
  help='IP address of a remote liteServer')
parser.add_argument('-p','--port', type=int, default=9700, 
  help='IP port of the remote liteServer')
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
    #iface = pyado.useDirect(), # useDirect() is default
    adoName = pargs.adoName,
    version = __version__,
    description = description,
    # optional arguments:
    #perfMon = True, # add parameters for performance monitoring
    #sourceName = 'simple.test:sinM', # add external input parameter
    periodicUpdate = pargs.update, # period of calling the periodic_update()
    #allowedHosts = AllowedHosts,# host restriction is enforced for all hosts except acnmcr* 
    #password = None,
    #loto = None,
   )
#````````````````````````Manager event loop```````````````````````````````
try:
    mgr.loop()
except KeyboardInterrupt:
    print('KeyboardInterrupt exception, cleanup and exit.')
    mgr.eventExit.set()
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,

