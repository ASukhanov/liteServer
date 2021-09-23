#!/usr/bin/env python3
"""This script provide conversion of LDO name to (host:port,device)"""
# If CNSHostPort is defined, then the name will be resolved using a dedicated
#liteCNSServer. If it is not defined then the name will be resolved using 
#liteCNS.yaml file.
__version__='v01 2021-04-19'#
print(f'liteCNS version {__version__}')

# Comment the following line for file-based name resolution
#CNSHostPort = 'acnlin23;9699'# host;port of the liteServer

#`````````````````````````````````````````````````````````````````````````````
def hostPort(cnsName):
  #print('>liteCNS.hostPort(%s)'%cnsName)
  try:
    CNSHostPort
    # CNSHostPort is defined, use liteCNSServer
    raise NameError('ERROR:CNS, liteCNSServer is not supported yet')
    
  except NameError: # file-based name resolution
    # CNSHostPort is not defined, use liteCNS.yaml
    import yaml
    fname = '/operations/app_store/liteServer/liteCNS.yaml'
    f = open(fname,'r')
    print('INFO.CNS: File-base name resolution using '+fname)
    y = yaml.load(f,Loader=yaml.BaseLoader)
    #print(f'liteCNS: {y}')
    try:
        r = y['hosts'][cnsName]
    except Exception as e:
        raise NameError('ERROR:CNS '+str(e))
    return r

