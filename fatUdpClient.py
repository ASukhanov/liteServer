#!/usr/bin/env python3
""" Client of the udpFatServer """
import socket
import sys
import ubjson
import numpy as np
from timeit import default_timer as timer

__version__ = 'v01 2019-06-05'# works at 5 MB/s for 36MB object
#TODO: keep track of lost chunks and re-request them

HOST, PORT = "localhost", 9990
data = " ".join(sys.argv[1:])
PrefixLength = 2

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

sock.sendto(bytes(data + "\n", "utf-8"), (HOST, PORT))
print('Sent %s'%data)

prefix = 1
buff = b''
prevPrefix = None

ts = timer()
while prefix:
    received, addr = sock.recvfrom(65000)
    prefix = int.from_bytes(received[:PrefixLength],'big')
    if prevPrefix is None:
        prevPrefix = prefix + 1
    if prefix != prevPrefix - 1:
        msg = 'buff#%d follows %d'%(prefix,prevPrefix)
        print(msg)
        prevPrefix = None
        #raise BufferError(msg)        
    prevPrefix = prefix   
    data = received[PrefixLength:]
    #print('received %i bytes from %s'%(len(data),addr))
    #print(prefix)
    buff = b''.join([buff,data])
dt = timer()-ts

l = len(buff)
print('received %d bytes in %.3fs. %.1f MB/s'%(l,dt,l*1.e-6/dt))

dec = ubjson.loadb(buff)
txt = str(dec)
if len(txt) > 100:
    txt = txt[:100]+'...'
print('decoded %d:%s'%(len(dec),txt))

shape,dtype,buf = dec['v'].values()
print('data shape,type ',shape,dtype)

nda = np.frombuffer(buf,dtype).reshape(shape)
print(nda)

