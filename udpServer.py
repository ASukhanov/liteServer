#!/usr/bin/env python3
import socketserver
import ubjson
import numpy as np
from timeit import default_timer as timer

MaxChunk = 60000 # UDP max is 65000,

class MyUDPHandler(socketserver.BaseRequestHandler):
    """Sending large data using UDP"""

    def handle(self):
        data = self.request[0].strip()
        socket = self.request[1]
        print("%s wrote %d bytes"%(self.client_address[0],len(data)))
        
        h,w,d = 300,400,3
        dout = (np.arange(h*w*d)%256).reshape(h,w,d)
        doutl = dout.tolist()
        
        ts = timer()
        # this section is very inefiicient, 1.4s for 360K
        # the better way to serialize shape, type and bytes
        enc = ubjson.dumpb(doutl)
        print('encoding of array [%d,%d,%d]'%dout.shape+' took %.6f s'%(timer()-ts)) 
        
        print('array shape: [%d,%d,%d]'%dout.shape+', %d bytes'%len(enc))
        nChunks = (len(enc)-1)//MaxChunk + 1
        for iChunk in range(nChunks):
            chunk = enc[iChunk*MaxChunk:min((iChunk+1)*MaxChunk,len(enc))]
            prefixInt = nChunks-iChunk - 1
            prefixBytes = (prefixInt).to_bytes(2,'big')
            prefixed = b''.join([prefixBytes,chunk])
            txt = str(chunk)
            if len(txt) > 100:
                txt = txt[:100]+'...'
            print('sending prefix %i'%prefixInt+' %d bytes:'%len(prefixed),txt)
            socket.sendto(prefixed, self.client_address)

if __name__ == "__main__":
    HOST, PORT = "localhost", 9990
    #with socketserver.UDPServer((HOST, PORT), MyUDPHandler) as server:
    server = socketserver.UDPServer((HOST, PORT), MyUDPHandler)
    print('server',server)
    server.serve_forever()
