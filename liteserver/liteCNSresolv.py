"""Example pf device name resolution module for LiteServer infrastructure
""" 
host = 'liteCNS'# hostname on internet
deviceMap = {
'PeakSimLocal': ('localhost,9701,dev1','PealSimulator, running on the localhost'),
'PeakSimGlobal': (f'{host},9701,dev1',f'PealSimulator, running on the {host}'),
}

