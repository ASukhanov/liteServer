#!/usr/bin/env python3
"""Spreadsheet view of process variables from a remote liteServer."""

#__version__ = 'v00 2019-05-06' # it is just sceleton, pvview.pvv is not processed
#__version__ = 'v01 2019-05-06' # using pg.TableWidget()
#__version__ = 'v02 2019-05-20' # using QTableWidget, with checkboxes
#__version__ = 'v03 2019-05-21' # PVTable,
#__version__ = 'v04 2019-05-22' # bool PVs treated as checkboxes
#__version__ = 'v05 2019-05-29' # spinboxes in table
#__version__ = 'r06 2019-05-29' # first release
#__version__ = 'r07 2019-05-30' # cell spanning is OK
#__version__ = 'r08 2019-05-31' # release 08
#__version__ = 'v09 2019-05-31' # detection of right click
#__version__ = 'v10 2019-06-01' # pargs.file
#__version__ = 'v11 2019-06-02' # automatic generation of the pvsheet.tmp
#__version__ = 'v12 2019-06-02' # boolean action is OK: don't set checkbox to the same state 
#TODO 1) discrete parameters, set array
__version__ = 'v13 2019-06-03' # is_spinbox check for writable, is_bool

import threading, socket, subprocess
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
class QDoubleSpinBoxPV(QtGui.QDoubleSpinBox):
    """Spinbox, which stores associated PV""" 
    def __init__(self,pv):
        super().__init__()
        self.pv = pv
        opl = self.pv.opLimits
        if opl is not None:
            self.setRange(*opl)
            ss = (opl[1]-opl[0])/100.
            #ss = round(ss,12)# trying to fix deficit 1e-14, not working
            #print('ss',ss)
            self.setSingleStep(ss)
        self.valueChanged.connect(self.handle_value_changed)
        print('instantiated',self.pv.title())
        
    def handle_value_changed(self):
        #print('handle_value_changed')
        print('changing %s to '%self.pv.title()+str(self.value()))
        try:
            self.pv.v = self.value()
        except Exception as e:
            print(e)
            
    def contextMenuEvent(self,event):
        # we don't need its contextMenu (activated on right click)
        #print('RightClick at spinbox with PV %s'%self.pv.name)
        mainWidget.rightClick(self.pv)
        pass

class myTableWidget(QtGui.QTableWidget):
    def mousePressEvent(self,*args):
        button = args[0].button()
        item = self.itemAt(args[0].pos())
        try:
            row,col = item.row(),item.column()
        except:
            return
        if button == 2: # right button
            try:
                pv = pvTable.pos2obj[(row,col)]
                #print('RightClick at PV %s.'%pv.name)
                mainWidget.rightClick(pv)
            except:
                pass
        else:
            super().mousePressEvent(*args)

class Window(QtGui.QWidget):
    def __init__(self, rows, columns):
        QtGui.QWidget.__init__(self)
        self.table = myTableWidget(rows, columns, self)
        self.table.setShowGrid(False)
        for row in range(rows):
          spanStart,spanFilled = None, False
          self.table.setRowHeight(row,20)
          if pvTable.pos2obj[(row,0)] is None:
            continue
          colSkip = 0
          for col in range(columns):
            #print('row,col',(row,col))
            try: obj = pvTable.pos2obj[(row,col)]
            except Exception as e:
                printd('Not an object:'+str(e))
                continue
            colOut = col - colSkip

            # check if not a PV object
            #print('obj[%i,%i]:'%(row,col)+str(type(obj)))
            if not isinstance(obj,PV):
                if isinstance(obj,str):
                    if len(obj) == 0: continue
                    if obj[0] == '[':
                        spanStart = col
                        #print('span starts at [%i,%i]:%s'%(row,spanStart,obj))
                        continue
                    elif obj[0] == ']':
                        colSkip += 1
                        #print('span ends at [%i,%i]'%(row, col))
                        self.table.setSpan(row,spanStart,1,col-spanStart)
                        continue
                    if spanStart is not None and not spanFilled:
                        spanFilled = True
                        colOut = spanStart
                    item = QtGui.QTableWidgetItem(str(obj))
                    item.setForeground(QtGui.QBrush(QtGui.QColor('darkBlue')))
                    self.table.setItem(row, colOut, item)
                elif isinstance(obj,QPushButtonCmd):
                    printd('pushButton at [%i,%i]'%(row, colOut))
                    self.table.setCellWidget(row, colOut, obj)
                continue
            
            if spanStart is not None:
                spanStart = None
                
            # the object is PV
            pv = obj
            val = pv.v
            pvTable.par2pos[pv] = row,colOut
            try:
                item = QtGui.QTableWidgetItem(pv.title())
            except Exception as e:
                printw('could not define Table[%i,%i]'%(row,colOut))
                print(str(e))
                continue
            #print('ok',item)
            #print('pvTable [%i,%i] is %s %s'%(row,colOut,pv.title(),type(pv)))
            try:
                if pv.is_bool():
                    #print('PV %s is boolean:'%pv.name+str(val))
                    item.setText(pv.name.split(':')[1])
                    item.setFlags(QtCore.Qt.ItemIsUserCheckable |
                                  QtCore.Qt.ItemIsEnabled)
                    state = QtCore.Qt.Checked if val[0] else QtCore.Qt.Unchecked
                    item.setCheckState(state)
                    self.table.setCellWidget(row, colOut, item)
                    continue
                    
                elif pv.is_spinbox():
                    printd('it is spinbox:'+pv.title())
                    spinbox = QDoubleSpinBoxPV(pv)
                    # using other ways is more complicated as it is not trivial
                    # to transfer argument to the method
                    #spinbox = QtGui.QDoubleSpinBox(self\
                    #,valueChanged=self.value_changed)
                    
                    spinbox.setValue(float(val[0]))
                    self.table.setCellWidget(row, colOut, spinbox)
                    continue
            except Exception as e:
                #printw('in is_bool '+pv.title()+':'+str(e))
                pass
            self.table.setItem(row, col, item)

        #self.table.itemClicked.connect(self.handleItemClicked)
        #self.table.itemPressed.connect(self.handleItemPressed)
        #self.table.itemDoubleClicked.connect(self.handleItemDoubleClicked)
        self.table.cellClicked.connect(self.handleCellClicked)
        #self.table.cellDoubleClicked.connect(self.handleCellDoubleClicked)
        
        layout = QtGui.QVBoxLayout(self)
        layout.addWidget(self.table)
        self._list = []
        monitor = PVMonitor()

    def closeEvent(self,*args):
        # Called when the window is closed
        print('>closeEvent')
        EventExit.set()

    def handleItemPressed(self, item):
        print('pressed[%i,%i]'%(item.row(),item.column()))

    def handleItemDoubleClicked(self, item):
        print('DoubleClicked[%i,%i]'%(item.row(),item.column()))

    def handleItemClicked(self, item):
        print('clicked[%i,%i]'%(item.row(),item.column()))
        self.handleCellClicked(item.row(),item.column())

    def handleCellDoubleClicked(self, x,y):
        print('cell DoubleClicked[%i,%i]'%(x,y))

    def handleCellClicked(self, row,column):
        item = self.table.item(row,column)
        print('cell clicked[%i,%i]:'%(row,column))#+str(item.text()))
        pv = pvTable.pos2obj[row,column]
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
            printe('exception in handleCellClicked: '+str(e))

    def update(self,a):
        print('mainWidget update',a)
        tableItem = self.table.item(2,1)
        try:
            tableItem.setText(str(a[0]))
        except Exception as e:
            printw('in tableItem.setText:'+str(e))
            
    def rightClick(self,pv):
        #print('mainWidget. RightClick on %s'%pv.name)
        d = QtGui.QDialog(self)
        pname = pv.title()
        d.setWindowTitle("Info on PV %s"%pname)
        attributes = pv.attributes()
        #print('attributes',attributes)
        txt = '    Attributes:\n'
        for attr,v in attributes.items():
            vv = list(v)[0]
            if vv is None:
                continue
            if isinstance(vv,list):
                vv = vv[:100]
            txt += attr+':\t'+str(vv)+'\n'
        qte = QtGui.QLabel(txt,d)
        qte.setWordWrap(True)
        d.resize(300,150)
        d.show()

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
            val = pv.v
            if isinstance(val,list):
                if pv.is_bool():
                    #print('PV '+pv.name+' is bool = '+str(val))
                    state = window.table.item(*rowCol).checkState()
                    if val[0] != (state != 0):
                        print('flip')
                        window.table.item(*rowCol).setCheckState(val[0])
                    continue
                elif pv.is_spinbox():
                    continue
                # standard PV
                #print('PV '+pv.name+' is list[%i] of '%len(val)\
                #+str(type(val[0])))
                txt = str(val)[1:-1] #avoid brackets
            elif isinstance(val,str):
                printd('PV '+pv.name+' is text')
                txt = val
                #continue
            else:
                txt = 'Unknown type of '+pv.name+'='+str(type(val))
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
        printd('>thread_proc')
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
        self._spinbox, self._bool = None,None
        
        # creating standard attributes from remote ones
        attributes = ['count', 'features', 'opLimits']
        try:
            for attribute in attributes:
                r = self.access.get(self.name+'.'+attribute)
                v = list(r.values())[0]
                #print('Creating attribute %s.%s = '%(name,attribute)+str(v))
                setattr(self,attribute,v)
        except:
            #print('opLimit = None for '+self.name)
            self.opLimits = None
            
    @property
    def v(self):
        # return values and timestamp
        #print('getter of %s called'%self.name)
        r = self.access.get(self.name)# +'.values')
        if r is None:
            return
        ret = list(r.values())[0]
        if not isinstance(ret,str):
            self.t,ret = ret[0], ret[1:]# first item is timestamp
        return ret # the rest are data

    @v.setter
    def v(self, value):
        #print('setter of %s'%self.name+' called to change PV to '+str(value))
        r = self.access.set(self.name,value)
        if r:
            printw('could not set %s'%self.name+' to '+str(value))

    @v.deleter
    def v(self):
        print("deleter of v called")
        del self._v

    def title(self): return self.name
    
    def is_bool(self):
        if self._bool is not None:
            return self._bool
        self._bool = False
        if isinstance(self._v,list):
            if len(self._v) == 1: # the first one is timestamp
                if isinstance(self._v[0],bool):
                     self._bool = True
        return self._bool
        
    def is_writable(self):
        r = list(self.access.get('%s.features'%self.name).values())
        return ('W' in r)
    
    def is_spinbox(self):
        if self._spinbox is not None:
            return self._spinbox
        self._spinbox = False
        if self.is_writable():
            try:        
                if len(self._v) == 1:
                    if type(self._v[0]) in (float,int):
                        self._spinbox = True
            except: pass
        return self._spinbox
        
    def attributes(self):
        """Returns a dictionary of all attributes"""
        r = self.access.ls(self.name)
        listOfAttr = list(r.values())[0]
        d = OD()
        for attr in listOfAttr:
            r = self.access.get('%s.%s'%(self.name,attr))
            d[attr] = r.values()
        return d

class QPushButtonCmd(QtGui.QPushButton):
    def __init__(self,text,cmd):
        self.cmd = cmd
        super().__init__(text)
        self.clicked.connect(self.handleClicked)
        
    def handleClicked(self):
        #print('clicked',self.cmd)
        p = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, shell=True)

class PVTable():
    """PV table maps: parameter to (row,col) and (row,col) to object"""
    def __init__(self,fileName,access):
        self.par2pos = OD()
        self.pos2obj = OD()
        maxcol = 0
        if pargs.pvfile is None:
            pargs.pvfile = self.build_temporary_pvfile(access)
        with open(pargs.pvfile,'r') as infile:
            row = 0
            for line in infile:
                #line = line[:-1]# remove eol
                line = line.rstrip()
                if len(line) == 0:  continue
                if line[0] == '#':  continue
                if line[0] == '!':
                    self.pos2obj[(row,0)] = None
                    row += 1  
                    continue
                #print('%3i:'%row+line)
                cols = line.split(',')
                nCols = len(cols)
                for col,token in enumerate(cols):
                    if len(token) == 0:
                        obj = ''
                    elif token in '[]':
                        obj = token
                        #nCols -= 1
                        #print('bracket %s at '%token+str((row,col)))
                    elif token[0] in ('"',"'"):
                        blank,txt,attributeString = token.split(token[0],2)
                        if len(attributeString) == 0:
                            obj = txt
                        else: # the cell is text with attributes
                            action,cmd = attributeString.split(':',1)
                            action = action[1:]
                            if action == 'launch':
                                #print('pushButton created with cmd:%s'%cmd)
                                #does not work in dynamic
                                #obj = QtGui.QPushButton(txt)
                                #obj.clicked.connect(lambda: launch(cmd))
                                obj = QPushButtonCmd(txt,cmd)
                    elif '`' in token: # PV's attribute
                        #print('check for attribute')
                        pvname,attrib = token.split('`')
                        pv = PV(pvname,access)
                        #print('temporary PV %s created'%pvname)
                        obj = str(getattr(pv,attrib))
                        if obj[0] == '[': obj = obj[1:]
                        if obj[-1] == ']': obj = obj[:-1]
                    else: # the cell is PV
                        #print('the "%s" is pv'%token)
                        try:
                            obj = PV(token,access)
                        except Exception as e:
                            printe('Cannot create PV %s'%token)
                            continue
                    self.pos2obj[(row,col)] = obj
                    #print(row,col,type(obj))
                maxcol = max(maxcol,nCols)
                row += 1
        self.shape = row,maxcol
        print('table created, shape: '+str(self.shape))

    def print_PV_at(self,row,col):
        try:
            pv = self.pos2obj[row,col]
            v = pv.v
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

    def build_temporary_pvfile(self,access):
        fname = 'pvsheet.tmp'
        #print('>build_temporary_pvfile')
        devices = list(access.ls([]).values())[0]
        f = open(fname,'w')
        for dev in devices:
            f.write("[,'____Device: %s____',]\n"%dev)
            pars = list(access.ls([dev]).values())[0]
            for par in pars:
                devPar = dev+':'+par
                #print(devPar)
                f.write("'%s',%s\n"%(par,devPar))
        f.close()
        print('PV spreadsheet config file generated: %s'%fname)
        return fname
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
    #parser.add_argument('pvfile', default='pvsheet.pvs', nargs='?', 
    parser.add_argument('pvfile', nargs='?', 
      help='PV list description file')
    pargs = parser.parse_args()
    printd('Monitoring of PVs at '+pargs.host+':%i'%pargs.port)

    import liteAccess
    liteAccess = liteAccess.LiteAccess((pargs.host,pargs.port)\
    ,dbg=False, timeout=pargs.timeout)

    app = QtGui.QApplication(sys.argv)

    # read config file
    pvTable = PVTable(pargs.pvfile,liteAccess)

    # define GUI
    window = Window(*pvTable.shape)
    title = 'PVs from '+socket.gethostbyaddr(pargs.host)[0].split('.')[0]
    #print(title)
    window.setWindowTitle(title)
    window.resize(350, 300)
    window.show()
    mainWidget = window
	
    # test some fields
    #pvTable.print_PV_at(6,1)
    #pvTable.print_PV_at(4,1)
    #pv = pvTable.pos2obj[3,1]
    #printd('pv31:'+pv.title())
    #pvTable.print_loc_of_PV(pv)

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
