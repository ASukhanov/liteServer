#!/usr/bin/env python3
"""Table view of process variables from a remote liteServer."""

#__version__ = 'v00 2019-05-06' # it is just sceleton, pvview.pvv is not processed
#__version__ = 'v01 2019-05-06' # using pg.TableWidget()
#__version__ = 'v02 2019-05-06' # using QTableWidget, with checkboxes
__version__ = 'v03 2019-05-06' # PVTable,

import threading, socket
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui
import numpy as np
from collections import OrderedDict as OD

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
        for row in range(rows):
            for column in range(columns):
                #print('row,col',(row,column))
                try: obj = pvTable.pos2obj[(row,column)]
                except: continue
                try:
                    item = QtGui.QTableWidgetItem(obj.title())
                except Exception as e:
                    printw('could not define Table[%i,%i]'%(row,column))
                    print(str(e))
                    continue
                #print('ok')
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
            d = QtGui.QDialog(self)
            d.setWindowTitle("Info")
            pname = pvTable.pos2obj[item.row(),item.column()].title()
            ql = QtGui.QLabel(pname,d)
            qte = QtGui.QTextEdit(item.text(),d)
            qte.move(0,20)
            #d.setWindowModality(Qt.ApplicationModal)
            d.show()

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
        #pv = pvTable.pos2obj[(row,col)]
        #print('rowCol',rowCol)
        if isinstance(pv,str):
            print('txt')
            continue
        try:
            #print('pv',pv.name)
            #txt = pv.v if isinstance(pv.v,str) else str(pv.v)[1:-1]
            window.table.item(*rowCol).setText(str(pv.v)[1:-1]) #remove brackets
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
        self._v = None
        self.name = name
        self.access = access

    def title(self): return self.name

    @property
    def v(self):
        # return just values, ignore key and timestamp
        #print('getter of %s called'%self.name)
        r = self.access.get(self.name)
        return list(r.values())[0][1:]

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
                        obj = ''
                    elif txt[0] in ('"',"'"):
                        obj = txt[1:-1]
                    else:
                        obj = PV(txt,access)
                        self.par2pos[obj] = row,col
                    self.pos2obj[(row,col)] = obj
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
    ,pargs.dbg, pargs.timeout)

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

