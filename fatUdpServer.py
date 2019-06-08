#!/usr/bin/env python3
import socketserver, socket
import ubjson
import numpy as np
from timeit import default_timer as timer
import time

MaxChunk = 60000 # UDP max is 65000,
#MaxChunk = 1500 # UDP max is 65000,
ChunkSleep = 0.01 # sleep time between chunks, python receiving socket max out at ~5MB/s

def ip_address():
    """Platform-independent way to get local host IP address"""
    return [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close())\
      for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]

def ip_address():
    """Platform-independent way to get local host IP address"""
    return [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close())\
      for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]

class MyUDPHandler(socketserver.BaseRequestHandler):
    """UDP server for sending large data objects (numpy arrays). 
    Data are encoded using ubjson, splitted into chunks and
    prefixed with the reversed chunk number."""
    
    def handle(self):
        data = self.request[0].strip()
        self.socket = self.request[1]
        #self.last_client_address = self.client_address
<<<<<<< HEAD
        print("%s wrote %d bytes"%(self.client_address[0],len(data)))
=======
        print("%s wrote %d bytes:%s"%(self.client_address[0],len(data),str(data)))
        if data == b'ACK':
            print('Got acknowledge from %s'%self.client_address[0])
            self.server.last_client_address = None
            return
>>>>>>> 42df0eeb51ba0c1b7159911411b27eaed103b593
        
        #h,w,d = 2,4,3
        #h,w,d = 300,400,3 # OK with RPi
        #h,w,d = 480,640,3
        h,w,d = 1100,1600,3 # OK, 5.28MB, avg transfer speed 26.1 MB/s
        #h,w,d = 1200,1600,3 # 5.76MB lost chunks at the end
        #h,w,d = 3000,4000,3 # missing packets after 6MB, need 10ms delay
        dout = (np.arange(h*w*d)%256).reshape(h,w,d).astype('uint8')
        #print(dout.max())
        #doutl = dout.tolist()
        #print('doutl',len(doutl),type(doutl[0][0][0]))
        
        doutb = {'ts':self.timestamp(),'v':bytes(dout),'shape':[h,w,d],'type':'uint8'}

        #````````````````````prepare array for transfer```````````````````````
        ts = timer()
        
        # this section is very inefiicient with doutl, 1.4s for 360K on RPi 
        # 6s for 960k with ubjson 0.8, 0.6s with 0.13
        # the better way to serialize shape, type and bytes
        # encoding of the doutb is fast! 15ms/for 36MB
        enc = ubjson.dumpb(doutb)
        
        dt = timer()-ts
        print('encoding time of array [%d,%d,%d]'%dout.shape\
        +' = %.6f s'%dt+'. %.1f MB/s'%(1e-6*len(enc)/dt))
        #,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
        ts = timer()
        print('array shape: [%d,%d,%d]'%dout.shape+', %d bytes'%len(enc))
        nChunks = (len(enc)-1)//MaxChunk + 1
        ts = timer()
        for iChunk in range(nChunks):
            chunk = enc[iChunk*MaxChunk:min((iChunk+1)*MaxChunk,len(enc))]
            prefixInt = nChunks-iChunk - 1
            prefixBytes = (prefixInt).to_bytes(2,'big')
            prefixed = b''.join([prefixBytes,chunk])
            #txt = str(chunk)
            #if len(txt) > 100:
            #    txt = txt[:100]+'...'
            #print('sending prefix %i'%prefixInt+' %d bytes:'%len(prefixed),txt)
            self.socket.sendto(prefixed, self.client_address)
<<<<<<< HEAD
            #time.sleep(.01) #10ms is safe for localhost
=======
            time.sleep(ChunkSleep) #10ms is safe for localhost
>>>>>>> 42df0eeb51ba0c1b7159911411b27eaed103b593
        dt = timer()-ts
        print('sending performance: %.1f MB/s'%(1e-6*len(enc)/dt))
        self.server.last_client_address = self.client_address
        print('lc',self.server.last_client_address)
            
    def timestamp(self):
        t = time.time()
        return [int(t),int(1e9*(t%1))]

class Server(socketserver.UDPServer):
    def __init__(self,hostPort, handler):
        super().__init__(hostPort, handler)
        self.handler = handler
        self.last_client_address = None
    
    def service_actions(self):
<<<<<<< HEAD
        #print('service_action')
        try:
            #print('last client',self.last_client_address)
            if self.last_client_address is not None:
=======
        try:
            #print('last client',self.last_client_address)
            if self.last_client_address is not None:
                print('waiting for ACK from '+str(self.last_client_address))
>>>>>>> 42df0eeb51ba0c1b7159911411b27eaed103b593
                self.socket.sendto(b'EOD', self.last_client_address)
        except Exception as e:
            print(e)

if __name__ == "__main__":
<<<<<<< HEAD
    HOST, PORT = ip_address(), 9999
=======
    HOST, PORT = ip_address(), 9998
>>>>>>> 42df0eeb51ba0c1b7159911411b27eaed103b593
    print('serving at ',HOST, PORT)
    
    #with Server((HOST, PORT), MyUDPHandler) as server:
    server = Server((HOST, PORT), MyUDPHandler)
    server.serve_forever()
    
