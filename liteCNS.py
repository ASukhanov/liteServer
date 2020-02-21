#!/usr/bin/env python3
"""This script provide conversion of LDO name to (host:port,device)"""

# If CNSHostPort is defined, then the name will be resolved using a dedicated
#liteCNSServer. If it is not defined then the name will be resolved using 
#liteCNS.yaml file.

# Comment the following line for file-based name resolution
#CNSHostPort = 'acnlin23;9699'# host;port of the liteServer

#`````````````````````````````````````````````````````````````````````````````
def hostPort(cnsName):
  #print('>liteCNS.hostPort(%s)'%cnsName)
  try:
    CNSHostPort
    # CNSHostPort is defined, use liteCNSServer
    raise NameError('ERROR, liteCNSServer is not supported yet')
    
  except NameError: # file-based name resolution
    # CNSHostPort is not defined, use liteCNS.yaml
    import yaml
    fname = 'liteCNS.yaml'
    f = open(fname,'r')
    print('File-base name resolution using '+fname)
    y = yaml.load(f,Loader=yaml.BaseLoader)
    try:
        r = y['hosts'][cnsName]
    except Exception as e:
        raise NameError('ERROR in liteCNS.py '+str(e))
    return r

