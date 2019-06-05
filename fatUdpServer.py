#!/usr/bin/env python3
import socketserver
import ubjson
import numpy as np
from timeit import default_timer as timer
import time

MaxChunk = 60000 # UDP max is 65000,
#MaxChunk = 1500 # UDP max is 65000,

class MyUDPHandler(socketserver.BaseRequestHandler):
    """UDP server for sending large data objects (numpy arrays). 
    Data are encoded using ubjson, splitted into chunks and
    prefixed with the reversed chunk number."""

    def handle(self):
        data = self.request[0].strip()
        socket = self.request[1]
        print("%s wrote %d bytes"%(self.client_address[0],len(data)))
        
        #h,w,d = 2,4,3
        #h,w,d = 300,400,3
        h,w,d = 1100,1600,3 # OK, 5.28MB, avg transfer speed 26.1 MB/s
        #h,w,d = 1200,1600,3 # 5.76MB lost chanks at the end
        #h,w,d = 3000,4000,3 # missing packets after 6MB, nedd 10ms delay
        dout = (np.arange(h*w*d)%256).reshape(h,w,d).astype('uint8')
        #print(dout.max())
        #doutl = dout.tolist()
        #print('doutl',len(doutl),type(doutl[0][0][0]))
        
        doutb = {'ts':self.timestamp(),'v':{'shape':[h,w,d],'type':'uint8'\
        ,'b':bytes(dout)}}

        #````````````````````prepare array for transfer```````````````````````
        ts = timer()
        
        # this section is very inefiicient with doutl, 1.4s for 360K on RPi 
        # 6s for 960k with ubjson 0.8, 0.6s with 0.13
        # the better way to serialize shape, type and bytes
        # encoding of the doutb is fast! 15ms/for 36MB
        enc = ubjson.dumpb(doutb)
        
        print('encoding of array [%d,%d,%d]'%dout.shape+' took %.6f s'%(timer()-ts)) 
        #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
        
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
            #print('sending prefix %i'%prefixInt+' %d bytes:'%len(prefixed),txt)
            socket.sendto(prefixed, self.client_address)
            #time.sleep(.010) #10ms is safe for localhost
            
    def timestamp(self):
        t = time.time()
        return [int(t),int(1e9*(t%1))]

if __name__ == "__main__":
    HOST, PORT = "localhost", 9990
    with socketserver.UDPServer((HOST, PORT), MyUDPHandler) as server:
        server.serve_forever()
