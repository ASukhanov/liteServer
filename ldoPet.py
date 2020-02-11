#!/usr/bin/env python3
"""Spreadsheet view of process variables from a remote liteServer."""
#__version__ = 'v25 2020-02-09'# replaced PV with LDO, need adjustments for new liteAccess
#__version__ = 'v25 2020-02-10'# most of the essential suff is working
#__version__ = 'v26 2020-02-10'# spinboxes OK
__version__ = 'v27b 2020-02-11'# lite cleanup, decoding in mySlot improved, better timout handling

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
    def __init__(self,ldo):
        super().__init__()
        self.ldo = ldo
        ss = 1
        opl = (0.,100.)
        try:    opl = self.ldo.opLimits['values']
        except:
            printw(' no oplimits') 
            pass
        else:
            #self.setRange(*opl)
            ss = (opl[1]-opl[0])/100.
            #ss = round(ss,12)# trying to fix deficit 1e-14, not working
        self.setRange(*opl)
        self.setSingleStep(ss)
        self.valueChanged.connect(self.handle_value_changed)
        #print('instantiated %s'%self.ldo.title())
        
    def handle_value_changed(self):
        print('handle_value_changed to '+str(self.value()))
        #print('changing %s to '%self.ldo.title()+str(self.value()))
        try:
            #TODO:something is not right here
            #self.ldo.set(self.value())
            pass
        except Exception as e:
            printw('in handle_value_changed :'+str(e))
            
    def contextMenuEvent(self,event):
        # we don't need its contextMenu (activated on right click)
        print('RightClick at spinbox with LDO %s'%self.ldo.name)
        mainWidget.rightClick(self.ldo)
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
            if True:#try:
                ldo = pvTable.pos2obj[(row,col)]
                print('RightClick at LDO %s.'%ldo.name)
                mainWidget.rightClick(ldo)
            else:#except:
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
            ldo = obj
            initialValue = ldo.initialValue[0]
            printd('ldo.initialValue of %s:'%ldo.name+str(initialValue))
            pvTable.par2pos[ldo] = row,colOut
            try:
                item = QtWidgets.QTableWidgetItem(ldo.title())
            except Exception as e:
                printw('could not define Table[%i,%i]'%(row,colOut))
                print(str(e))
                print('Traceback: '+repr(traceback.format_exc()))
                continue
            #print('ok',item)
            #print('pvTable [%i,%i] is %s %s'%(row,colOut,ldo.title(),type(ldo)))
            try:
                if ldo.guiType == 'bool':
                    #print( 'LDO %s is boolean:'%ldo.name+str(initialValue))
                    #item.setText(ldo.name.split(':')[1])
                    item.setText(ldo.name.split(':',1)[1])
                    item.setFlags(QtCore.Qt.ItemIsUserCheckable |
                                  QtCore.Qt.ItemIsEnabled)
                    state = QtCore.Qt.Checked if initialValue else QtCore.Qt.Unchecked
                    item.setCheckState(state)
                    self.table.setCellWidget(row, colOut, item)
                    continue
                    
                elif ldo.guiType == 'spinbox':
                    print('it is spinbox:'+ldo.title())
                    spinbox = QDoubleSpinBoxLDO(ldo)
                    # using other ways is more complicated as it is not trivial
                    # to transfer argument to the method
                    #spinbox = QtWidgets.QDoubleSpinBox(self\
                    #,valueChanged=self.value_changed)
                    
                    spinbox.setValue(float(initialValue))
                    self.table.setCellWidget(row, colOut, spinbox)
                    #print('table set for spinbox',row, colOut, spinbox)
                    continue
            except Exception as e:
                #printw('in is_bool '+ldo.title()+':'+str(e))
                pass
            self.table.setItem(row, col, item)
            #print('table set',row, col, item)

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
        ldo = pvTable.pos2obj[row,column]
        if isinstance(ldo,str):
            return
        if True:#try:
            if ldo.guiType =='bool':
                checked = item.checkState() == QtCore.Qt.Checked
                print('bool clicked '+ldo.name+':'+str(checked))
                ldo.set(checked) # change server's ldo
            else:
                d = QtWidgets.QDialog(self)
                d.setWindowTitle("Info")
                pname = ldo.title()
                ql = QtWidgets.QLabel(pname,d)
                qte = QtWidgets.QTextEdit(item.text(),d)
                qte.move(0,20)
                #d.setWindowModality(Qt.ApplicationModal)
                d.show()
        else:#except Exception as e:
            printe('exception in handleCellClicked: '+str(e))

    def update(self,a):
        print('mainWidget update',a)
        tableItem = self.table.item(2,1)
        try:
            tableItem.setText(str(a[0]))
        except Exception as e:
            printw('in tableItem.setText:'+str(e))
            
    def rightClick(self,ldo):
        print('mainWidget. RightClick on %s'%ldo.name)
        d = QtWidgets.QDialog(self)
        pname = ldo.title()
        d.setWindowTitle("Info on LDO %s"%pname)
        attributes = ldo.attributes()
        print('attributes:%s'%str(attributes)[:200])
        txt = '    Attributes:\n'
        for attr,v in attributes.items():
            vv = str(v)[:100]
            txt += attr+':\t'+vv+'\n'
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
    for ldo,rowCol in pvTable.par2pos.items():
        printd('updating LDO '+ldo.name)
        if isinstance(ldo,str):
            printw('logic error')
            continue
        try:
            val = ldo.get()
            printd('val:%s'%str(val)[:100])
            if val is None:
                try:
                    window.table.item(*rowCol).setText('none')
                except:  pass
                continue
            if ldo.guiType == 'spinbox':
                printd('LDO '+ldo.name+' is spinbox '+str(val[0]))
                #print(str(window.table.cellWidget(*rowCol).value()))
                window.table.cellWidget(*rowCol).setValue(float(val[0]))
                continue
            elif ldo.guiType =='bool':
                printd('LDO '+ldo.name+' is bool')
                state = window.table.item(*rowCol).checkState()
                printd('LDO '+ldo.name+' is bool = '+str(val)+', state:'+str(state))
                if val[0] != (state != 0):
                    #print('flip')
                    window.table.item(*rowCol).setCheckState(val[0])
                continue
            #print('LDO '+ldo.name+' is '+str(type(val)))
            if isinstance(val,np.ndarray):
                printd('LDO '+ldo.name+' is ndarray')
                txt = '%s: %s'%(val.shape,str(val))
            else:
                if len(val) > 1:
                    printd('LDO '+ldo.name+' is list')
                    txt = str(val)
                else:
                    val = val[0]
                    printd('LDO '+ldo.name+' is '+str(type(val)))
                    if type(val) in (float,int,str):
                        txt = str(val)
                    else:
                        txt = 'Unknown type of '+ldo.name+'='+str(type(val))
                        printw(txt+':'+str(val))
                        txt = str(val)
            window.table.item(*rowCol).setText(txt)
        except Exception as e:
            printw('updating [%i,%i]:'%rowCol+str(e))
            #print('Traceback: '+repr(traceback.format_exc()))
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
        #print('ldo name: '+str(name))
        self.ldo = LA.LdoPars(name.split(':'))
        #print('ldo info for %s: '%name+str(self.ldo.info()))
        info = self.ldo.info()
        self.key = list(self.ldo.info())[0]
        printd('key:'+str(self.key))
        #print('ldo vars:'+str(vars(self.ldo)))
        self.initialValue = self.ldo.value[0]
        print('iv',self.name,str(self.initialValue)[:60])
        self.t = 0.
        # creating attributes from remote ones
        self.attr = self.ldo.info()[self.key]
        #print('attrs %s'%self.attr)
        #for attribute,v in self.attr.items():
        #    if attribute not in ['count', 'features', 'opLimits']:                
        #        continue
        #    print('Creating attribute %s.%s = '%(name,attribute)+str(v))
        #    setattr(self,attribute,v)
        self.guiType = self.gui_type()
        #print('type of %s:'%self.name+str(self.guiType)

    def set(self,value):
        r = self.ldo.set([value])
        #print('<set',r)

    def get(self):
        return self.ldo.value[0]

    def title(self): return self.name

    def gui_type(self):
        iv = self.initialValue
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
                #pprint(('row,rlist',row,rlist))
                nCols = len(rlist)
                for col,cell in enumerate(rlist):
                  try:
                    #print( 'cell:'+str(cell))
                    if not isinstance(cell,str):
                        self.pos2obj[(row,col)] = cell
                        continue
                    # process string cell
                    for old,new in config['dict'].items():
                        cell = cell.replace(old,new)
                    if cell[0] == '$':# the cell is LDO
                        printd( 'the "%s" is ldo'%cell[1:])
                        if True:# Do not catch exception here!#try:
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
                  except RuntimeError as e:
                    printe('Could not create table due to '+str(e))
                    sys.exit() 
                    #self.pos2obj[(row,col)] = '?'

                maxcol = max(maxcol,nCols)
                row += 1
        self.shape = row,maxcol
        print('table created, shape: '+str(self.shape))

    def print_LDO_at(self,row,col):
        try:
            ldo = self.pos2obj[row,col]
            v = ldo.get()
            txt = str(v) if len(v) <= 10 else str(v[:10])[:-1]+',...]'
            print('Table[%i,%i]:'%(row,col)+ldo.name+' = '+txt)
        except Exception as e:
            printw('in print_LDO:'+str(e))

    def print_loc_of_LDO(self,ldo):
        try:
            row,col = self.par2pos[ldo]
            print('Parameter '+ldo.name+' is located at Table[%i,%i]:'%(row,col))
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
    parser.add_argument('-t','--timeout',type=float,default=10,
      help='timeout of the receiving socket')
    parser.add_argument('ldo', nargs='?', 
      help='LDOs: lite data objects')
    pargs = parser.parse_args()
    LA.LdoPars.Dbg = pargs.dbg# transfer dbg flag to liteAccess

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
    #print(title)
    window.setWindowTitle('ldoPet')
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

