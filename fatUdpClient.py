#!/usr/bin/env python3
""" Client of the udpFatServer """
import socket
import sys
import ubjson
import numpy as np
from timeit import default_timer as timer

__version__ = 'v01 2019-06-05'# works at 5 MB/s for 36MB object
#TODO: keep track of lost chunks and re-request them
__version__ = 'v02 2019-06-06'# Acknowledge after EOD

<<<<<<< HEAD
def ip_address():
    """Platform-independent way to get local host IP address"""
    return [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close())\
      for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]

#HOST, PORT = ip_address(), 9999
HOST, PORT = '192.168.1.145', 9999

data = " ".join(sys.argv[1:])
PrefixLength = 2

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#sock.settimeout(0.5)
=======
PrefixLength = 2

def ip_address():
    """Platform-independent way to get local host IP address"""
    return [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close())\
      for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]

import argparse
parser = argparse.ArgumentParser(
  description = 'Reciving client of a fatUdpServer')
parser.add_argument('-p','--port',type=int,default=9998,
  help='Port number')
parser.add_argument('-H','--host',default=ip_address(),nargs='?',
  help='Hostname')
parser.add_argument('request', nargs='?', 
  help='Request to server')
pargs = parser.parse_args()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#sock.settimeout(0.5)
#sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,1)
#sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,10*1024*1024)
#print(sock.getsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF))
>>>>>>> 42df0eeb51ba0c1b7159911411b27eaed103b593

prefix = 1
buff = b''
prevPrefix = None
chunkSize = 65000
<<<<<<< HEAD
=======
ichunk = 0
>>>>>>> 42df0eeb51ba0c1b7159911411b27eaed103b593
'''recvfrom_into()
maxChunks = 1000
chunks = bytearray(maxChunks*chunkSize)
chunkNBytes = [0]*maxChunks
bufptr = 0
'''
<<<<<<< HEAD
sock.sendto(bytes(data + "\n", "utf-8"), (HOST, PORT))
print('Sent %s'%data)

ts = timer()

ichunk = 0
while prefix:
    received, addr = sock.recvfrom(chunkSize)
    if len(received) <= 3:
        print('EOD')
        break 
=======
print('Request sent to '+pargs.host+':%i'%pargs.port)
data = bytes(pargs.request, "utf-8")
sock.sendto(data, (pargs.host, pargs.port))
print('Sent %s'%data)

ts = timer()
nTries = 1
while prefix:
    received, addr = sock.recvfrom(chunkSize)
    if len(received) == 3: # and received == b'EOD':
        print('EOD',prefix,nTries)
        if prefix and nTries:
            print('got EOD, but %i packets are missed, tries#%i'%(prefix,nTries))
            nTries -= 1
            continue
        sock.sendto(b'ACK',(pargs.host, pargs.port))
        break 
    ichunk += 1
>>>>>>> 42df0eeb51ba0c1b7159911411b27eaed103b593
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
<<<<<<< HEAD
    ichunk += 1
=======

if prefix == 0:
    print('Success')
    sock.sendto(b'ACK',(pargs.host, pargs.port))
>>>>>>> 42df0eeb51ba0c1b7159911411b27eaed103b593

'''recvfrom_into()
# The recvfrom_into() is surprisingly Very slow
for ichunk in range(maxChunks):
    nbytes,addr = sock.recvfrom_into(chunks[bufptr:],chunkSize)
    #buf,addr = sock.recvfrom(chunkSize)
    nbytes = len(buf)
    print('nbytes',nbytes)
    if nbytes <= 3:
        print('EOD')
        break
    chunkNBytes[ichunk] = nbytes
    bufptr += chunkSize
print('receiving finished after %d chunks: '%ichunk)#+str(e))

dt = timer()-ts
s = sum(chunkNBytes)
print('Received %d chunks %d bytes, %.1fMB/s.'%(ichunk,s,1e-6*s/dt))
sys.exit()
'''    

dt = timer()-ts

l = len(buff)
print('received %d chunks, %d bytes in %.3fs. %.1f MB/s'\
%(ichunk,l,dt,l*1.e-6/dt))

decoded = ubjson.loadb(buff)
txt = str(decoded)
if len(txt) > 100:
    txt = txt[:100]+'...'
print('decoded %d:%s'%(len(decoded),txt))

ts,v,shape,dtype = [decoded[i] for i in ['ts','v','shape','type']]
print('data shape,type ',shape,dtype)

nda = np.frombuffer(v,dtype).reshape(shape)
print(nda)
00
