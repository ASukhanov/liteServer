#!/usr/bin/env python3
import threading, socket
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui
import numpy as np
from collections import OrderedDict as OD

#__version__ = 'v00 2019-05-06' # it is just sceleton, pvview.pvv is not processed
#__version__ = 'v01 2019-05-06' # using pg.TableWidget()
#__version__ = 'v02 2019-05-06' # using QTableWidget, with checkboxes
__version__ = 'v03 2019-05-06' # PVTable, 

EventExit = threading.Event()

#````````````````````````````Helper functions`````````````````````````````````
def printw(msg): print('WARNING: '+msg)   
def printe(msg): print('ERROR: '+msg)

def ip_address():
    """Platform-independent way to get local host IP address"""
    return [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close())\
        for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]


#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,

class Window(QtGui.QWidget):
    def __init__(self, rows, columns):
        QtGui.QWidget.__init__(self)
        self.table = QtGui.QTableWidget(rows, columns, self)
        for column in range(columns):
            for row in range(rows):
                item = QtGui.QTableWidgetItem('Text%d' % row)
                if row % 2:
                    item.setFlags(QtCore.Qt.ItemIsUserCheckable |
                                  QtCore.Qt.ItemIsEnabled)
                    item.setCheckState(QtCore.Qt.Unchecked)
                self.table.setItem(row, column, item)
        self.table.itemClicked.connect(self.handleItemClicked)
        layout = QtGui.QVBoxLayout(self)
        layout.addWidget(self.table)
        self._list = []
        
        monitor = PVMonitor()
        
    def closeEvent(self,*args):
        # Called when the window is closed
        print('>closeEvent')
        EventExit.set()

    def handleItemClicked(self, item):
        if item.checkState() == QtCore.Qt.Checked:
            print('"%s" Checked' % item.text())
            self._list.append(item.row())
            print(self._list)
        else:
            print('"%s" Clicked' % item.text())
            
    def update(self,a):
        print('mainWidget update',a)
        tableItem = self.table.item(0,2)
        tableItem.setText(str(a[0]))
        
#`````````````````````````````````````````````````````````````````````````````
def MySlot(a):
    """Global redirector of the SignalSourceDataReady"""
    #print('MySlot received event:'+str(a))
    if mainWidget:
        mainWidget.update(a)
    else:
        printe('mainWidget not defined yet')
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Data provider
class PVMonitor(QtCore.QThread): 
    # inheritance from QtCore.QThread is needed for qt signals
    SignalSourceDataReady = QtCore.pyqtSignal(object)
    def __init__(self):
        # for signal/slot paradigm we need to call the parent init
        super(PVMonitor,self).__init__()
        self.eventNumber = 0
        #...
        thread = threading.Thread(target=self.thread_proc)
        thread.start()
        self.SignalSourceDataReady.connect(MySlot)

    def thread_proc(self):
        print('>thread_proc')
        while not EventExit.isSet():
            EventExit.wait(1)
            self.eventNumber += 1
            a = self.eventNumber,self.eventNumber**2
            #print('proc',EventExit.isSet(),self.eventNumber,a)
            self.callback(a)
        print('<thread_proc')

    def callback(self,*args):
        #print('cb:',args)
        self.SignalSourceDataReady.emit(args)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
class PV():
    """Process Variable object, provides getter and setter"""
    def __init__(self,name):
        self._v = None
        self.name = name
        
    @property
    def v(self):
        print("getter of v called")
        return self._v
        
    @v.setter
    def v(self, value):
        print("setter of v called")
        self._v = value

    @v.deleter
    def v(self):
        print("deleter of v called")
        del self._v
    
class PVTable():
    """PV table maps: parameter to (row,col) and (row,col) to object"""
    def __init__(self,fileName):
        self.par2pos = OD()
        self.pos2obj = OD()
        maxcol = 0
        with open('pvview.pvv','r') as infile:
            row = 0
            for line in infile:
                if line[0] == '#':
                    continue
                print('%3i:'%row+line)
                cols = line.split(',')
                maxcol = max(maxcol,len(cols))
                for col,txt in enumerate(cols):
                    if txt[0] in ('"',"'"):
                        obj = txt[1:-1]
                    else:
                        obj = PV(txt)
                        self.par2pos[obj] = row,col
                    self.pos2obj[(row,col)] = obj                
                row += 1
        self.shape = row,maxcol
        #print('par2pos',self.par2pos)
        #print('pos2obj',self.pos2obj)
        print('table:',self.shape)
#`````````````````````````````````````````````````````````````````````````````
if __name__ == '__main__':
    global mainWidget
    mainWidget = None
    import sys
    
    import argparse
    parser = argparse.ArgumentParser(
      description = 'Process Variable viewer')
    parser.add_argument('-p','--port',type=int,default=9999,
      help='Port number')
    parser.add_argument('-H','--host',default=ip_address(),nargs='?',
      help='Hostname')
    parser.add_argument('pvfile', default='pvview.pvv', nargs='?', 
      help='PV list description file')
    pargs = parser.parse_args()
    print('Monitoring of PVs at '+pargs.host+':%i'%pargs.port)

    # read config file
    pvTable = PVTable(pargs.pvfile)
    print(pvTable.pos2obj[10,1].name)
    print(pvTable.pos2obj[4,1].v)
    
    app = QtGui.QApplication(sys.argv)
    window = Window(6, 3)
    window.resize(350, 300)
    window.show()
    mainWidget = window

    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)    
    try:
        app.instance().exec_()
        #sys.exit(app.exec_())
    except KeyboardInterrupt:
        # This exception never happens
        print('keyboard interrupt: exiting')
        EventExit.set()
    print('Application exit')

