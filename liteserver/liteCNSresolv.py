"""Example of device name resolution module for LiteServer infrastructure
""" 

#SiteCNShost = 'sitecns'
""" If the SiteCNShost is defined, then the name resolution will be re-directed
 to LDO SiteCNShost;9700:liteCNS.
The rest of the module will be ignored.
"""

import socket
host = socket.gethostname()# hostname on network
deviceMap = {
'PeakSimLocal': ('localhost;9701:dev1','PealSimulator, running on the localhost'),
'PeakSimGlobal': (f'{host};9701:dev1',f'PealSimulator, running on the {host}'),
}

