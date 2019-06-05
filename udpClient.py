#!/usr/bin/env python3
import socket
import sys
import ubjson
import numpy as np

HOST, PORT = "localhost", 9990
data = " ".join(sys.argv[1:])


# SOCK_DGRAM is the socket type to use for UDP sockets
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# As you can see, there is no connect() call; UDP has no connections.
# Instead, data is directly sent to the recipient via sendto().
sock.sendto(bytes(data + "\n", "utf-8"), (HOST, PORT))
print('Sent %s'%data)

prefix = 1
msg = b''
while prefix:
    received, addr = sock.recvfrom(65000)
    prefix = int.from_bytes(received[:2],'big')
    data = received[2:]
    print('received %i bytes from %s'%(len(received),addr))
    print(prefix)
    msg = b''.join([msg,data])

dec = ubjson.loadb(msg)
txt = str(dec)
if len(txt) > 100:
    txt = txt[:100]+'...'
print('decoded %d:%s'%(len(dec),txt))
