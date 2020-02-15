#!/usr/bin/env python3
"""Spreadsheet view of process variables from a remote liteServer."""
#__version__ = 'v25 2020-02-09'# replaced PV with LDO, need adjustments for new liteAccess
#__version__ = 'v25 2020-02-10'# most of the essential suff is working
#TODO: drop $ substitution, leave it for YAML
#__version__ = 'v26 2020-02-10'# spinboxes OK
__version__ = 'v27b 2020-02-11'# lite cleanup, decoding in mySlot improved, better timout handling
#TODO: discard LDOTable, do table creation in Window
#__version__ = 'v28 2020-02-11'# merged cell supported
#__version__ = 'v29 2020-02-12'# cell features, merging supported
#__version__ = 'v30 2020-02-13'# shell commands added
#__version__ = 'v31 2020-02-14'# comboboxes, set fixed, color for widgets
__version__ = 'v32 2020-02-15'# added Window.bottomLabel for messages

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
    """Spinbox associated with LDO""" 
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
            self.ldo.set(self.value())
            pass
        except Exception as e:
            printw('in handle_value_changed :'+str(e))
            
    def contextMenuEvent(self,event):
        # we don't need its contextMenu (activated on right click)
        print('RightClick at spinbox with LDO %s'%self.ldo.name)
        mainWidget.rightClick(self.ldo)
        pass

class QComboBoxLDO(QtWidgets.QComboBox):
    """ComboBox associated with LDO""" 
    def __init__(self,ldo):
        super().__init__()
        self.ldo = ldo
        lvs = ldo.attr['legalValues']
        print('lvs',lvs)
        for lv in lvs:
            self.addItem(lv)
        self.activated[str].connect(self.onComboChanged) 

    def onComboChanged(self,txt):
        self.ldo.set(txt)

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
                ldo = pvTable.pos2obj[(row,col)][0]
                print('RightClick at LDO %s.'%ldo.name)
                mainWidget.rightClick(ldo)
            else:#except:
                pass
        else:
            super().mousePressEvent(*args)

class Window(QtWidgets.QWidget):
    bottomLabel = ''
    def __init__(self, rows, columns):
        QtWidgets.QWidget.__init__(self)
        self.table = myTableWidget(rows, columns, self)
        self.table.setShowGrid(False)
        print('```````````````````````Processing table`````````````````````')
        self.process_pvTable(rows,columns)
        print(',,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,')
        self.table.cellClicked.connect(self.handleCellClicked)
        
        Window.bottomLable = QtWidgets.QLabel(self)
        Window.bottomLable.setText('Lite Objet Viewer version '+__version__)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(Window.bottomLable)
        self._list = []
        monitor = LDOMonitor()

    def process_pvTable(self,rows,columns):
        for row in range(rows):
          self.table.setRowHeight(row,20)
          try:  
            if pvTable.pos2obj[(row,0)][0] is None:
                    continue
          except:   continue
          for col in range(columns):
            #print('row,col',(row,col))
            try: obj,cellFeature = pvTable.pos2obj[(row,col)]
            except Exception as e:
                printd('Not an object,{}:'+str(e))
                continue

            if isinstance(cellFeature,dict):
                #print('handle cellFeatures(%i,%i) '%(row,col)+str(cellFeature))
                for feature,value in cellFeature.items():
                    if feature == 'span':
                        try: spanCol,spanRow = value
                        except: spanRow,spanCol = 1,value
                        #print('merging %i,%i cells starting at %i,%i'%(*value,row,col))
                        self.table.setSpan(row,col,spanRow,spanCol)

            #print('obj[%i,%i]:'%(row,col)+str(type(obj)))
            if not isinstance(obj,LDO):
                if isinstance(obj,str):
                    item = QtWidgets.QTableWidgetItem(str(obj))
                    self.setItem(row,col, item,cellFeature,fgColor='darkBlue')
                elif isinstance(obj,list):
                    #print('####rowCol(%i,%i) is list: '%(row,col) + str(obj))
                    self.setItem(row,col,obj, cellFeature, fgColor='darkBlue')
                continue
                
            #``````the object is LDO``````````````````````````````````````````
            ldo = obj
            if ldo.guiType: cellFeature['widget'] = ldo.guiType
            #initialValue = ldo.initialValue[0]
            pvTable.par2pos[ldo] = row,col
            try:
                item = QtWidgets.QTableWidgetItem(ldo.title())
            except Exception as e:
                printw('could not define Table[%i,%i]'%(row,col))
                print(str(e))
                print('Traceback: '+repr(traceback.format_exc()))
                continue
            #print('pvTable [%i,%i] is %s %s'%(row,col,ldo.title(),type(ldo)))
            # deduct the cell type from LDO
            self.setItem(row, col, item, cellFeature, ldo)
            #print('table row set',row, col, item)

    def setItem(self,row,col,item,features,ldo=None,fgColor=None):
        if ldo: iValue = ldo.initialValue[0]        
        if isinstance(item,list):
            # Take the first item, the last one is cellFeature
            cellName = str(item[0])
            item = QtWidgets.QTableWidgetItem(cellName)
        elif ldo: # this section is valid only for non-scalar ldoPars 
            try:    item = QtWidgets.QTableWidgetItem(iValue)
            except Exception as e: 
                pass#printw('in re-item(%i,%i): '%(row,col)+str(e))
        if fgColor:
            item.setForeground(QtGui.QBrush(QtGui.QColor(fgColor)))
        for feature,value in features.items():
            if feature == 'span': continue # span was served above
            if feature == 'color':
                color = QtGui.QColor(*value) if isinstance(value,list)\
                      else QtGui.QColor(value)
                #print('color of (%i,%i) is '%(row,col)+str(value))
                item.setBackground(color)
            elif feature == 'launch':
                pbutton = QPushButtonCmd(cellName,value)
                try: 
                    color = features['color']
                    color = 'rgb(%i,%i,%i)'%tuple(color)\
                      if isinstance(color,list) else str(color)
                    pbutton.setStyleSheet('background-color:'+color)
                except Exception as e:
                    printw('in color '+str(e))
                #print('pushButton created with cmd:%s'%value)
                self.table.setCellWidget(row, col, pbutton)
                return
            elif feature == 'widget':
                print('widget feature: "%s"'%value)
                if value == 'spinbox':
                    print('it is spinbox:'+ldo.title())
                    spinbox = QDoubleSpinBoxLDO(ldo)                
                    spinbox.setValue(float(iValue))
                    self.table.setCellWidget(row, col, spinbox)
                    print('table set for spinbox',row, col, spinbox)
                    return
                elif value == 'combo':
                    print('>combo')
                    combo = QComboBoxLDO(ldo)
                    self.table.setCellWidget(row, col, combo)
                elif value == 'bool':
                    print( 'LDO %s is boolean:'%ldo.name+str(iValue))
                    #item.setText(ldo.name.split(':')[1])
                    item.setText(ldo.name.split(':',1)[1])
                    item.setFlags(QtCore.Qt.ItemIsUserCheckable |
                                  QtCore.Qt.ItemIsEnabled)
                    state = QtCore.Qt.Checked if iValue\
                      else QtCore.Qt.Unchecked
                    item.setCheckState(state)
                    continue
                else:
                    print('not supported widget(%i,%i):'%(row,col)+value)
                    return                  
            else:
                print('not supported feature(%i,%i):'%(row,col)+feature)
        #print('setting item(%i,%i): '%(row,col)+str(item))
        self.table.setItem(row, col, item)

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
        ldo = pvTable.pos2obj[row,column][0]
        if isinstance(ldo,str):
            return
        try:
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
        except Exception as e:
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
        #print('updating LDO '+ldo.name)
        if 'R' not in ldo.attr['features']:
            continue
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
    def __init__(self,ldoName,parName='*',attribute='value'):
        self.name = ldoName+':'+parName
        print('ldo name: '+str(self.name))
        self.ldo = LA.LdoPars((ldoName,parName))
        info = self.ldo.info()
        print('ldo info for %s: '%self.name+str(info))
        self.key = list(info)[0]
        printd('key:'+str(self.key))
        #print('ldo vars:'+str(vars(self.ldo)))
        self.initialValue = self.ldo.value[0]
        print('iv',self.name,str(self.initialValue)[:60])
        #self.t = 0.
        # creating attributes from remote ones
        self.attr = info[self.key]
        self.guiType = self._guiType()
        print('type of %s: '%self.name+str(self.guiType))

    def set(self,val):
        r = self.ldo.set([val])
        #print('<set',r)

    def get(self):
        return self.ldo.value[0]

    def title(self): return self.name

    def _guiType(self):
        iv = self.initialValue
        if len(iv) != 1:
            return None
            
        if isinstance(iv[0],bool):
            return 'bool'

        if self.is_writable():
            if type(iv[0]) in (float,int):
                return 'spinbox'                
            if 'legalValues' in self.attr:
                return 'combo'
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
        print('launching `%s`'%str(self.cmd))
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
                  cellFeatures = {}
                  try:
                    #print( 'cell:'+str(cell))
                    if isinstance(cell,str):
                        self.pos2obj[(row,col)] = cell,cellFeatures
                        continue
                    if not isinstance(cell,list):
                        # print('accepting only strings and lists')
                        continue
                        
                    # cell is a list
                    # The last item could be a cell features
                    if isinstance(cell[-1],dict):
                        cellFeatures = cell[-1]
                    # is the cell LDO?
                    try:    cellIsLdo = cell[0][0] == '$'
                    except: cellIsLdo = False
                    if not cellIsLdo:
                        if isinstance(cell[0],str):
                            #print('merged non-ldo cells: '+str(cell))
                            self.pos2obj[(row,col)] = cell,cellFeatures
                        else:
                            print("cell[0] must be a ['host;port',dev]: ")\
                            +str(cell[0])
                            print('Not supported yet')
                        continue

                    # cell is LDO
                    #print('cell[0][0]',cell[0][0])
                    # cell[:2] is LDO,par, optional cell[2] is cell property 
                    try:    ldo,par = cell[0][1:],cell[1]
                    except: NameError('expect LDO,par, got: '+str(cell))
                    #print( 'the cell[%i,%i] is ldo: %s,%s'%(row,col,ldo,par))
                    if True:# Do not catch exception here!#try:
                        self.pos2obj[(row,col)] = LDO(ldo,par),cellFeatures
                        continue
                    else:#except Exception as e:
                        txt = 'Cannot create LDO %s:'%cell+str(e)
                        raise NameError(txt)
                    continue
                    #printe('cell[%i,%i]=%s not recognized'%(row,col,str(cell))) 
                  except RuntimeError as e:
                    printe('Could not create table due to '+str(e))
                    sys.exit() 
                    #self.pos2obj[(row,col)] = '?'

                maxcol = max(maxcol,nCols)
                row += 1
        self.shape = row,maxcol
        print('table created, shape: '+str(self.shape))

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

