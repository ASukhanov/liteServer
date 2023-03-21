#!/usr/bin/env python3
"""This script provide conversion of LDO name to (host:port,device).
Usage:
  from liteserver import liteCNS
  hostname = liteCNS.hostPort('pi108')
"""
# If CNSHostPort is defined, then the name will be resolved using a dedicated
__version__='v02 2023-03-17'# use python-based configuration

import sys

CNSHostPort = None#'hostName;9699'# host;port of the liteServer

#`````````````````````````````````````````````````````````````````````````````
def hostPort(cnsName='*', server=CNSHostPort):
    if server is not None:
        # CNSHostPort is defined, use liteCNSServer
        raise NameError('ERROR:CNS, liteCNSServer is not supported yet')

    #``````````read conguration file into the config dictionary```````````````
    configDir = '/operations/app_store/liteServer'
    moduleName = 'liteCNS_resolv'
    sys.path.append(configDir)
    from importlib import import_module#, reload
    #print(f'importing {moduleName}')
    ConfigModule = import_module(moduleName)
    #print(f'Imported: {configDir}/{moduleName}')
    if cnsName == '*':
        r = ConfigModule.hosts
    else:
        r = ConfigModule.hosts[cnsName]
    return r
