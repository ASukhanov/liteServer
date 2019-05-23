#!/usr/bin/env python3
"""Table view of process variables from a remote liteServer."""

#__version__ = 'v00 2019-05-06' # it is just sceleton, pvview.pvv is not processed
#__version__ = 'v01 2019-05-06' # using pg.TableWidget()
#__version__ = 'v02 2019-05-20' # using QTableWidget, with checkboxes
#__version__ = 'v03 2019-05-21' # PVTable,
__version__ = 'v04 2019-05-22' # bool PVs treated as checkboxes

import threading, socket
#import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui
#from PyQt5 import QtCore, QtGui
import numpy as np
from collections import OrderedDict as OD

EventExit = threading.Event()

#````````````````````````````Helper functions`````````````````````````````````
def printw(msg): print('WARNING: '+msg)
def printe(msg): print('ERROR: '+msg)
def printd(msg): 
    if pargs.dbg:
        print('DBG:'+str(msg))

def ip_address():
    """Platform-independent way to get local host IP address"""
    return [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close())\
        for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,

class Window(QtGui.QWidget):
    def __init__(self, rows, columns):
        QtGui.QWidget.__init__(self)
        self.table = QtGui.QTableWidget(rows, columns, self)
        for row in range(rows):
            for column in range(columns):
                #print('row,col',(row,column))
                try: pv = pvTable.pos2obj[(row,column)]
                except Exception as e:
                    #print('Exception',str(e))
                    continue
                try:
                    item = QtGui.QTableWidgetItem(pv.title())
                except Exception as e:
                    printw('could not define Table[%i,%i]'%(row,column))
                    print(str(e))
                    continue
                #print('ok')
                printd('pvTable [%i,%i] is '%(row,column)+pv.title())
                try:
                    if pv.is_bool():
                        printd('it is boolean:'+str(pv.v))
                        item.setFlags(QtCore.Qt.ItemIsUserCheckable |
                                      QtCore.Qt.ItemIsEnabled)
                        state = QtCore.Qt.Checked if pv.v[0] else QtCore.Qt.Unchecked
                        item.setCheckState(state)
                except Exception as e:
                    #printw('in is_bool '+pv.title()+':'+str(e))
                    pass
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
        pv = pvTable.pos2obj[item.row(),item.column()]
        if isinstance(pv,str):
            return
        try:
            if pv.is_bool():
                checked = item.checkState() == QtCore.Qt.Checked
                print('bool clicked '+pv.name+':'+str(checked))
                pv.v = checked # change server's pv
            else:
                d = QtGui.QDialog(self)
                d.setWindowTitle("Info")
                pname = pv.title()
                ql = QtGui.QLabel(pname,d)
                qte = QtGui.QTextEdit(item.text(),d)
                qte.move(0,20)
                #d.setWindowModality(Qt.ApplicationModal)
                d.show()
        except Exception as e:
            printe('exception in handleItemClicked: '+str(e))

    def update(self,a):
        print('mainWidget update',a)
        tableItem = self.table.item(2,1)
        try:
            tableItem.setText(str(a[0]))
        except Exception as e:
            printw('in tableItem.setText:'+str(e))

#`````````````````````````````````````````````````````````````````````````````
def MySlot(a):
    """Global redirector of the SignalSourceDataReady"""
    #print('MySlot received event:'+str(a))
    if mainWidget is None:
        printe('mainWidget not defined yet')
        return
    for pv,rowCol in pvTable.par2pos.items():
        printd('updating PV '+pv.name)
        if isinstance(pv,str):
            printw('logic error')
            continue
        try:
            #print('pv',str(rowCol),pv.name)
            #print(len(pv.v),type(pv.v))
            if isinstance(pv.v,list):
                if pv.is_bool():
                    printd('PV '+pv.name+' is bool = '+str(pv.v))
                    window.table.item(*rowCol).setCheckState(pv.v[0])
                    continue
                printd('PV '+pv.name+' is list[%i] of '%len(pv.v)\
                +str(type(pv.v[0])))
                txt = str(pv.v)[1:-1] #avoid brackets
            elif isinstance(pv.v,str):
                printd('PV '+pv.name+' is text')
                #txt = pv.v
                continue
            else:
                txt = 'Unknown type of '+pv.name+'='+str(type(pv.v))
            window.table.item(*rowCol).setText(txt)
        except Exception as e:
            printw('updating [%i,%i]:'%rowCol+str(e))
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
            #self.eventNumber += 1
            #a = self.eventNumber,self.eventNumber**2
            #print('proc',EventExit.isSet(),self.eventNumber,a)
            self.callback(None)
        print('<thread_proc')

    def callback(self,*args):
        #print('cb:',args)
        self.SignalSourceDataReady.emit(args)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
class PV():
    """Process Variable object, provides getter and setter"""
    def __init__(self,name,access):
        self.name = name
        self.access = access
        self._v = self.v # use getter to store initial value
        self.t = 0.

    def title(self): return self.name
    
    def is_bool(self):
        #print('>is_bool',self.name)
        if isinstance(self._v,list):
            if len(self._v) == 1: # the first one is timestamp
                #print('pv.v',pv.v)
                if isinstance(self._v[0],bool):
                    return True
        return False

    @property
    def v(self):
        # return just values, ignore key and timestamp
        #print('getter of %s called'%self.name)
        r = self.access.get(self.name)# +'.values')
        t = list(r.values())[0][0] # first item is timestamp
        return list(r.values())[0][1:] # the rest are data

    @v.setter
    def v(self, value):
        print('setter of %s'%self.name+' called to change PV to '+str(value))
        r = self.access.set(self.name,value)
        if r:
            printw('could not set %s'%self.name+' to '+str(value))

    @v.deleter
    def v(self):
        print("deleter of v called")
        del self._v

class PVTable():
    """PV table maps: parameter to (row,col) and (row,col) to object"""
    def __init__(self,fileName,access):
        self.par2pos = OD()
        self.pos2obj = OD()
        maxcol = 0
        with open('pvview.pvv','r') as infile:
            row = 0
            for line in infile:
                line = line[:-1]# remove eol
                if len(line) == 0:  continue
                if line[0] == '#':  continue
                #print('%3i:'%row+line)
                cols = line.split(',')
                #print('cols',cols)
                maxcol = max(maxcol,len(cols))
                for col,txt in enumerate(cols):
                    if len(txt) == 0:
                        pv = ''
                    elif txt[0] in ('"',"'"):
                        pv = txt[1:-1]
                    else:
                        pv = PV(txt,access)
                        self.par2pos[pv] = row,col
                    self.pos2obj[(row,col)] = pv
                    #print(row,col,type(pv))
                row += 1
        self.shape = row,maxcol
        print('table:',self.shape)

    def print_PV_at(self,row,col):
        try:
            pv = self.pos2obj[row,col]
            v = pv.v
            print('pv',pv.name,len(v))
            txt = str(v) if len(v) <= 10 else str(v[:10])[:-1]+',...]'
            print('Table[%i,%i]:'%(row,col)+pv.name+' = '+txt)
        except Exception as e:
            printw('in print_PV:'+str(e))

    def print_loc_of_PV(self,pv):
        try:
            row,col = self.par2pos[pv]
            print('Parameter '+pv.name+' is located at Table[%i,%i]:'%(row,col))
        except Exception as e:
            printw('in print_loc:'+str(e))

#`````````````````````````````````````````````````````````````````````````````
if __name__ == '__main__':
    global mainWidget
    mainWidget = None
    import sys
 
    import argparse
    parser = argparse.ArgumentParser(
      description = 'Process Variable viewer')
    parser.add_argument('-d','--dbg', action='store_true', help='debugging')
    parser.add_argument('-p','--port',type=int,default=9999,
      help='Port number')
    parser.add_argument('-H','--host',default=ip_address(),nargs='?',
      help='Hostname')
    parser.add_argument('-t','--timeout',type=float,default=0.1,
      help='timeout of the receiving socket')
    parser.add_argument('pvfile', default='pvview.pvv', nargs='?', 
      help='PV list description file')
    pargs = parser.parse_args()
    print('Monitoring of PVs at '+pargs.host+':%i'%pargs.port)

    import liteAccess
    liteAccess = liteAccess.LiteAccess((pargs.host,pargs.port)\
    ,dbg=False, timeout=pargs.timeout)

    # read config file
    pvTable = PVTable(pargs.pvfile,liteAccess)
	
    # test some fields
    pvTable.print_PV_at(6,1)
    pvTable.print_PV_at(4,1)
    pv = pvTable.pos2obj[2,1]
    pvTable.print_loc_of_PV(pv)

    # define GUI
    app = QtGui.QApplication(sys.argv)
    window = Window(*pvTable.shape)
    title = 'PVs from '+socket.gethostbyaddr(pargs.host)[0].split('.')[0]
    print(title)
    window.setWindowTitle(title)
    window.resize(350, 300)
    window.show()
    mainWidget = window

    # arrange keyboard interrupt to kill the program
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
	
    # start GUI
    try:
        app.instance().exec_()
        #sys.exit(app.exec_())
    except KeyboardInterrupt:
        # This exception never happens
        print('keyboard interrupt: exiting')
        EventExit.set()
    print('Application exit')

