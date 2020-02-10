#!/usr/bin/env python3
"""Spreadsheet view of process variables from a remote liteServer."""
__version__ = 'v25 2020-02-09'# replaced PV with LDO, need adjustments for new liteAccess
#TODO: drop $ substitution, leave it for YAML

import threading, socket, subprocess, sys, time
from timeit import default_timer as timer
from collections import OrderedDict as OD
from PyQt5 import QtCore, QtGui, QtWidgets
import yaml
from pprint import pprint
import numpy as np
import traceback
import liteAccess as LA

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
class QDoubleSpinBoxLDO(QtWidgets.QDoubleSpinBox):
    """Spinbox, which stores associated LDO""" 
    def __init__(self,pv):
        super().__init__()
        self.pv = pv
        try:    opl = self.pv.opLimits['values']
        except: pass
        else:
            self.setRange(*opl)
            ss = (opl[1]-opl[0])/100.
            #ss = round(ss,12)# trying to fix deficit 1e-14, not working
            self.setSingleStep(ss)
        self.valueChanged.connect(self.handle_value_changed)
        #print('instantiated %s'%self.pv.title())
        
    def handle_value_changed(self):
        #print('handle_value_changed')
        #print('changing %s to '%self.pv.title()+str(self.value()))
        try:
            self.pv.v = self.value()
        except Exception as e:
            print(e)
            
    def contextMenuEvent(self,event):
        # we don't need its contextMenu (activated on right click)
        print('RightClick at spinbox with LDO %s'%self.pv.name)
        mainWidget.rightClick(self.pv)
        pass

class myTableWidget(QtWidgets.QTableWidget):
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
                #print('RightClick at LDO %s.'%pv.name)
                mainWidget.rightClick(pv)
            except:
                pass
        else:
            super().mousePressEvent(*args)

class Window(QtWidgets.QWidget):
    def __init__(self, rows, columns):
        QtWidgets.QWidget.__init__(self)
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

            # check if not a LDO object
            #print('obj[%i,%i]:'%(row,col)+str(type(obj)))
            if not isinstance(obj,LDO):
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
                    item = QtWidgets.QTableWidgetItem(str(obj))
                    item.setForeground(QtGui.QBrush(QtGui.QColor('darkBlue')))
                    self.table.setItem(row, colOut, item)
                elif isinstance(obj,QPushButtonCmd):
                    printd('pushButton at [%i,%i]'%(row, colOut))
                    self.table.setCellWidget(row, colOut, obj)
                continue
            
            if spanStart is not None:
                spanStart = None
                
            # the object is LDO
            pv = obj
            #val = pv.v
            printd('pv.initialValue of %s:'%pv.name+str(pv.initialValue))
            initialValue = pv.initialValue['value'][0]
            #print( 'initialValue',initialValue)
            pvTable.par2pos[pv] = row,colOut
            try:
                item = QtWidgets.QTableWidgetItem(pv.title())
            except Exception as e:
                printw('could not define Table[%i,%i]'%(row,colOut))
                print(str(e))
                print('Traceback: '+repr(traceback.format_exc()))
                continue
            #print('ok',item)
            #print('pvTable [%i,%i] is %s %s'%(row,colOut,pv.title(),type(pv)))
            try:
                if pv.guiType == 'bool':
                    #print( 'LDO %s is boolean:'%pv.name+str(initialValue))
                    #item.setText(pv.name.split(':')[1])
                    item.setText(pv.name.split(':',1)[1])
                    item.setFlags(QtCore.Qt.ItemIsUserCheckable |
                                  QtCore.Qt.ItemIsEnabled)
                    state = QtCore.Qt.Checked if initialValue else QtCore.Qt.Unchecked
                    item.setCheckState(state)
                    self.table.setCellWidget(row, colOut, item)
                    continue
                    
                elif pv.guiType == 'spinbox':
                    printd('it is spinbox:'+pv.title())
                    spinbox = QDoubleSpinBoxLDO(pv)
                    # using other ways is more complicated as it is not trivial
                    # to transfer argument to the method
                    #spinbox = QtWidgets.QDoubleSpinBox(self\
                    #,valueChanged=self.value_changed)
                    
                    spinbox.setValue(float(initialValue))
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
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.table)
        self._list = []
        monitor = LDOMonitor()

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
        printd('cell clicked[%i,%i]:'%(row,column))
        pv = pvTable.pos2obj[row,column]
        if isinstance(pv,str):
            return
        try:
            if pv.guiType =='bool':
                checked = item.checkState() == QtCore.Qt.Checked
                printd('bool clicked '+pv.name+':'+str(checked))
                pv.v = checked # change server's pv
            else:
                d = QtWidgets.QDialog(self)
                d.setWindowTitle("Info")
                pname = pv.title()
                ql = QtWidgets.QLabel(pname,d)
                qte = QtWidgets.QTextEdit(item.text(),d)
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
        d = QtWidgets.QDialog(self)
        pname = pv.title()
        d.setWindowTitle("Info on LDO %s"%pname)
        attributes = pv.attributes()
        #print('attributes:%s'%str(attributes)[:100])
        txt = '    Attributes:\n'
        for attr,v in attributes.items():
            #vv = v if isinstance(v,str) else list(v)[0]
            vv = v if isinstance(v,str) else list(v)
            if vv is None:
                continue
            if isinstance(vv,list):
                vv = vv[:100]
            txt += attr+':\t'+str(vv)+'\n'
        qte = QtWidgets.QLabel(txt,d)
        qte.setWordWrap(True)
        d.resize(300,150)
        d.show()

#`````````````````````````````````````````````````````````````````````````````
myslotBusy = False
def MySlot(a):
    """Global redirector of the SignalSourceDataReady"""
    global myslotBusy
    printd('MySlot received event:'+str(a))
    if myslotBusy:
        print('Busy')
        return
    myslotBusy = True
    if mainWidget is None:
        printe('mainWidget not defined yet')
        return
    for pv,rowCol in pvTable.par2pos.items():
        printd('updating LDO '+pv.name)
        if isinstance(pv,str):
            printw('logic error')
            continue
        try:
            val = pv.v['value']
            printd('val:%s'%str(val)[:100])
            if isinstance(val,list):
                if pv.guiType =='bool':
                    #print('LDO '+pv.name+' is bool = '+str(val))
                    state = window.table.item(*rowCol).checkState()
                    if val[0] != (state != 0):
                        printd('flip')
                        window.table.item(*rowCol).setCheckState(val[0])
                    continue
                elif pv.guiType == 'spinbox':
                    continue
                # standard LDO
                #print('LDO '+pv.name+' is list[%i] of '%len(val)\
                #+str(type(val[0])))
                txt = str(val)[1:-1] #avoid brackets
            elif isinstance(val,str):
                printd('LDO '+pv.name+' is text')
                txt = val
                #continue
            elif isinstance(val,np.ndarray):
                txt = '%s: %s'%(val.shape,str(val))
            else:
                txt = 'Unknown type of '+pv.name+'='+str(type(val))
                printw(txt+':'+str(val))
            window.table.item(*rowCol).setText(txt)
        except Exception as e:
            printw('updating [%i,%i]:'%rowCol+str(e))
            print('Traceback: '+repr(traceback.format_exc()))
    myslotBusy = False
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Data provider
class LDOMonitor(QtCore.QThread): 
    # inheritance from QtCore.QThread is needed for qt signals
    SignalSourceDataReady = QtCore.pyqtSignal(object)
    def __init__(self):
        # for signal/slot paradigm we need to call the parent init
        super(LDOMonitor,self).__init__()
        #...
        thread = threading.Thread(target=self.thread_proc)
        thread.start()
        self.SignalSourceDataReady.connect(MySlot)

    def thread_proc(self):
        printd('>thread_proc')
        while not EventExit.isSet():
            self.callback(None)
            EventExit.wait(2)
        print('<thread_proc')

    def callback(self,*args):
        #print('cb:',args)
        self.SignalSourceDataReady.emit(args)
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
class LDO():
    """Process Variable object, provides getter and setter"""
    def __init__(self,name):
        self.name = name
        printd('pv name: '+str(name))
        self.pv = LA.LdoPars(name.split(':'))
        self.key = list(self.pv.info())[0]
        printd('key:'+str(self.key))
        #print('pv vars:'+str(vars(self.pv)))
        self.initialValue = self.v # use getter to store initial value
        self.t = 0.
        # creating attributes from remote ones
        self.attr = self.pv.info()[self.key]
        print('attrs %s'%self.attr)
        #for attribute,v in self.attr.items():
        #    if attribute not in ['count', 'features', 'opLimits']:                
        #        continue
        #    print('Creating attribute %s.%s = '%(name,attribute)+str(v))
        #    setattr(self,attribute,v)
        self.guiType = self.gui_type()
        print('type of %s:'%self.name+str(self.guiType))
            
    @property
    def v(self): # getter
        # return values and store timestamp
        #v = self.pv.value[self.key]['value']
        v = self.pv.value[self.key]
        printd('getter of %s called, value type:'%self.name+str(type(v)))
        return(v)

    @v.setter
    def v(self, value):
        printd('setter of %s'%self.name+' called to change LDO to '+str(value))
        self.pv.value = value

    @v.deleter
    def v(self):
        print("deleter of v called")
        del self.initialValue

    def title(self): return self.name

    def gui_type(self):
        iv = self.initialValue['value']
        print('iv',self.name,str(iv)[:60])
        if len(iv) != 1:
            return None
            
        if isinstance(iv[0],bool):
            return 'bool'

        if self.is_writable():
            if type(iv[0]) in (float,int):
                return 'spinbox'                
            if 'legalValues' in self.attr:
                return 'combobox'
        return None
        
    def is_writable(self):
        return 'W' in self.attr['features']
            
    def attributes(self):
        return self.attr

class QPushButtonCmd(QtWidgets.QPushButton):
    def __init__(self,text,cmd):
        self.cmd = cmd
        super().__init__(text)
        self.clicked.connect(self.handleClicked)
        
    def handleClicked(self):
        #print('clicked',self.cmd)
        p = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, shell=True)

class LDOTable():
    """LDO table maps: parameter to (row,col) and (row,col) to object"""
    def __init__(self,fileName):
        
        self.par2pos = OD()
        self.pos2obj = OD()
        maxcol = 0
        with open(fileName,'r') as infile:
            config = yaml.load(infile,Loader=yaml.FullLoader) 
            pprint(('config:',config))
            for row,rlist in enumerate(config['rows']):
                if rlist is None:
                    continue
                pprint(('row,rlist',row,rlist))
                nCols = len(rlist)
                for col,cell in enumerate(rlist):
                  if True:#try:
                    #print( 'cell:'+str(cell))
                    if not isinstance(cell,str):
                        self.pos2obj[(row,col)] = cell
                        continue
                    # process string cell
                    for old,new in config['dict'].items():
                        cell = cell.replace(old,new)
                    if cell[0] == '$':# the cell is LDO
                        printd( 'the "%s" is pv'%cell[1:])
                        if True:#try:
                            self.pos2obj[(row,col)] = LDO(cell[1:])
                            continue
                        else:#except Exception as e:
                            txt = 'Cannot create LDO %s:'%cell+str(e)
                            raise NameError(txt)
                    # the cell is string, separate attributes
                    txtlist =  cell.split(';')
                    if len(txtlist) == 1:
                        self.pos2obj[(row,col)] = txtlist[0]
                        continue
                    # the cell contains attribute
                    attrVal = txtlist[1].split(':')
                    if attrVal[0] == 'launch':
                        self.pos2obj[(row,col)]\
                        = QPushButtonCmd(txtlist[0],attrVal[1])
                        continue
                    printe('cell[%i,%i]=%s not recognized'%(row,col,str(cell))) 
                  else:#except Exception as e:
                    printw(str(e))
                    self.pos2obj[(row,col)] = '?'

                maxcol = max(maxcol,nCols)
                row += 1
        self.shape = row,maxcol
        print('table created, shape: '+str(self.shape))

    def print_LDO_at(self,row,col):
        try:
            pv = self.pos2obj[row,col]
            v = pv.v
            txt = str(v) if len(v) <= 10 else str(v[:10])[:-1]+',...]'
            print('Table[%i,%i]:'%(row,col)+pv.name+' = '+txt)
        except Exception as e:
            printw('in print_LDO:'+str(e))

    def print_loc_of_LDO(self,pv):
        try:
            row,col = self.par2pos[pv]
            print('Parameter '+pv.name+' is located at Table[%i,%i]:'%(row,col))
        except Exception as e:
            printw('in print_loc:'+str(e))

    def build_temporary_pvfile(self):
        fname = 'pvsheet.tmp'
        print('>build_temporary_pvfile')
        pvServerInfo = LA.LdoPars([pargs.host]).info()
        deviceSet = {i.split(':')[0] for i in pvServerInfo.keys()}
        printd('devs:'+str(deviceSet))
        f = open(fname,'w')
        #for dev in deviceSet:
        curDev = ''
        for devParName,pardict in pvServerInfo.items():
            dev,parName = devParName.split(':')
            if dev != curDev:
                curDev = dev
                f.write("[,'____Device: %s____',]\n"%dev)
            f.write("'%s',%s\n"%(parName,devParName))
        f.close()
        print('LDO spreadsheet config file generated: %s'%fname)
        return fname
#`````````````````````````````````````````````````````````````````````````````
if __name__ == '__main__':
    global mainWidget
    mainWidget = None
    import sys
 
    import argparse
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument('-d','--dbg', action='store_true', help='debugging')
    parser.add_argument('-f','--file', help=\
    'Config file')
    parser.add_argument('-t','--timeout',type=float,default=None,
      help='timeout of the receiving socket')
    parser.add_argument('ldo', nargs='?', 
      help='LDOs: lite data objects')
    pargs = parser.parse_args()
    if pargs.file:
        print('Monitoring LDO as defined in '+pargs.file)
    else:
        print('Monitoring LDOs: '+str(pargs.ldo))
        pargs.file = self.build_temporary_pvfile()
    app = QtWidgets.QApplication(sys.argv)

    # read config file
    pvTable = LDOTable(pargs.file)

    # define GUI
    window = Window(*pvTable.shape)
    try:
        title = 'LDOs from '+socket.gethostbyaddr(pargs.host)[0].split('.')[0]
    except:
        title = 'LDOs from '+pargs.host
    #print(title)
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

