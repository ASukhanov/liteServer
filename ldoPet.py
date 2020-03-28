#!/usr/bin/env python3
"""Spreadsheet view of process variables from a remote liteServer."""
#__version__ = 'v35 2020-02-16'# LS revision3
#__version__ = 'v36 2020-02-22'# error handling for aggr. response
#__version__ = 'v37 2020-02-24'# err handling for missed chunks
#__version__ = 'v38 2020-02-24'# default localhost
#__version__ = 'v39 2020-03-05'# 
#__version__ = 'v40 2020-03-24'# --server option
#__version__ = 'v41 2020-03-26'# spinbox reacts on editingFinished, not valueChanged
__version__ = 'v42 2020-03-27'# lineEditLDO widget for writable text parameters

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
    """Spinbox associated with DataAccess""" 
    def __init__(self,ldo):
        super().__init__()
        self.ldo = ldo
        ss = 1
        opl = (0.,100.)
        try:    opl = self.ldo.opLimits['values']
        except:
            #printw(' no oplimits for '+self.ldo.name) 
            pass
        else:
            #self.setRange(*opl)
            ss = (opl[1]-opl[0])/100.
            #ss = round(ss,12)# trying to fix deficit 1e-14, not working
        self.setRange(*opl)
        self.setSingleStep(ss)
        #self.valueChanged.connect(self.handle_value_changed)
        self.editingFinished.connect(self.handle_value_changed)
        #print('instantiated %s'%self.ldo.title())
        
    def handle_value_changed(self):
        #print('handle_value_changed to '+str(self.value()))
        try:
            #TODO:something is not right here
            self.ldo.set(self.value())
            pass
        except Exception as e:
            printw('in handle_value_changed :'+str(e))
            
    def contextMenuEvent(self,event):
        # we don't need its contextMenu (activated on right click)
        print('RightClick at spinbox with DataAccess %s'%self.ldo.name)
        mainWidget.rightClick(self.ldo)
        pass

class QComboBoxLDO(QtWidgets.QComboBox):
    """ComboBox associated with DataAccess""" 
    def __init__(self,ldo):
        super().__init__()
        self.setEditable(True)
        self.ldo = ldo
        lvs = ldo.attr['legalValues']
        #print('lvs',lvs)
        for lv in lvs:
            self.addItem(lv)
        self.activated[str].connect(self.onComboChanged)

    def onComboChanged(self,txt):
        #print('combo changed ',txt)
        self.ldo.set(txt)

    def setText(self,txt):
        self.lineEdit().setText(txt)

class QLineEditLDO(QtWidgets.QLineEdit):
    """LineEdit associated with DataAccess""" 
    def __init__(self,ldo):
        super().__init__()
        self.ldo = ldo
        self.returnPressed.connect(self.handle_value_changed)

    def handle_value_changed(self):
        print('lineedit changed ',self.text())
        self.ldo.set(self.text())

    #def setText(self,txt):
    #    print('lineedit setText '+txt)
    #    self.lineEdit().setText(txt)

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
                ldo = daTable.pos2obj[(row,col)][0]
                print('RightClick at LDO %s.'%ldo.name)
                mainWidget.rightClick(ldo)
            else:#except:
                pass
        else:
            super().mousePressEvent(*args)

class Window(QtWidgets.QWidget):
    bottomLine = None
    def __init__(self, rows, columns):
        QtWidgets.QWidget.__init__(self)
        self.table = myTableWidget(rows, columns, self)
        self.table.setShowGrid(False)
        print('```````````````````````Processing table`````````````````````')
        self.process_daTable(rows,columns)
        print(',,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,')
        self.table.cellClicked.connect(self.handleCellClicked)
        
        Window.bottomLine = QtWidgets.QLabel(self)
        Window.bottomLine.setText('Lite Object Viewer version '+__version__)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addWidget(Window.bottomLine)
        self._list = []
        monitor = LDOMonitor()

    def process_daTable(self,rows,columns):
        for row in range(rows):
          self.table.setRowHeight(row,20)
          try:  
            if daTable.pos2obj[(row,0)][0] is None:
                    continue
          except:   continue
          for col in range(columns):
            try: obj,cellFeature = daTable.pos2obj[(row,col)]
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
            if not isinstance(obj,DataAccess):
                if isinstance(obj,str):
                    item = QtWidgets.QTableWidgetItem(str(obj))
                    self.setItem(row,col, item,cellFeature,fgColor='darkBlue')
                elif isinstance(obj,list):
                    #print('####rowCol(%i,%i) is list: '%(row,col) + str(obj))
                    self.setItem(row,col,obj, cellFeature, fgColor='darkBlue')
                continue
                
            #``````the object is DataAccess```````````````````````````````````
            dataAccess = obj
            #print('DA object',dataAccess.name)
            if dataAccess.guiType: cellFeature['widget'] = dataAccess.guiType
            #initialValue = dataAccess.initialValue[0]
            daTable.par2pos[dataAccess.name] = dataAccess,(row,col)
            try:
                item = QtWidgets.QTableWidgetItem(dataAccess.title())
            except Exception as e:
                printw('could not define Table[%i,%i]'%(row,col))
                print(str(e))
                print('Traceback: '+repr(traceback.format_exc()))
                continue
            #print('daTable [%i,%i] is %s %s'%(row,col,dataAccess.title(),type(dataAccess)))
            # deduct the cell type from LDO
            self.setItem(row, col, item, cellFeature, dataAccess)
            #print('table row set',row, col, item)
        #print('par2pos ',daTable.par2pos)

    def setItem(self,row,col,item,features,dataAccess=None,fgColor=None):
        if dataAccess: 
            iValue = dataAccess.initialValue
            #print('ivalue',iValue)
        if isinstance(item,list):
            # Take the first item, the last one is cellFeature
            cellName = str(item[0])
            item = QtWidgets.QTableWidgetItem(cellName)
        elif dataAccess: # this section is valid only for non-scalar ldoPars 
            try:    item = QtWidgets.QTableWidgetItem(str(iValue))
            except Exception as e: 
                printw('in re-item(%i,%i): '%(row,col)+str(e))
                pass
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
                    printw('Format error in cell(%i,%i): '%(row,col)+str(e))
                #print('pushButton created with cmd:%s'%value)
                self.table.setCellWidget(row, col, pbutton)
                return
            elif feature == 'widget':
                #print('widget feature: "%s"'%value)
                if value == 'spinbox':
                    #print('it is spinbox:'+dataAccess.title())
                    spinbox = QDoubleSpinBoxLDO(dataAccess)
                    try:    v = int(iValue[0])#DNW with QDoubleSpinBox 
                    except: v = float(iValue[0])
                    spinbox.setValue(v)
                    self.table.setCellWidget(row, col, spinbox)
                    #print('table set for spinbox',row, col, spinbox)
                    return
                elif value == 'combo':
                    #print('>combo')
                    combo = QComboBoxLDO(dataAccess)
                    self.table.setCellWidget(row, col, combo)
                elif value == 'bool':
                    #print( 'DA %s is boolean:'%dataAccess.name+str(iValue))
                    item.setText(dataAccess.name.rsplit(',')[-1])
                    item.setFlags(QtCore.Qt.ItemIsUserCheckable |
                                  QtCore.Qt.ItemIsEnabled)
                    state = QtCore.Qt.Checked if iValue[0]\
                      else QtCore.Qt.Unchecked
                    item.setCheckState(state)
                    continue
                elif value == 'lineEdit':
                    #print('>lineEdit',row,col)
                    lineEdit = QLineEditLDO(dataAccess)
                    lineEdit.setText(iValue[0])
                    self.table.setCellWidget(row, col, lineEdit)
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
        dataAccess = daTable.pos2obj[row,column][0]
        if isinstance(dataAccess,str):
            return
        try:
            if dataAccess.guiType =='bool':
                checked = item.checkState() == QtCore.Qt.Checked
                print('bool clicked '+dataAccess.name+':'+str(checked))
                dataAccess.set(checked) # change server's dataAccess
            else:
                d = QtWidgets.QDialog(self)
                d.setWindowTitle("Info")
                pname = dataAccess.title()
                #ql = QtWidgets.QLabel(pname,d)
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
            
    def rightClick(self,dataAccess):
        print('mainWidget. RightClick on %s'%dataAccess.name)
        d = QtWidgets.QDialog(self)
        pname = dataAccess.title()
        d.setWindowTitle("Info on LDO %s"%pname)
        attributes = dataAccess.attributes()
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
    errMsg = ''
    if LDOMonitor.Perf: ts = timer()
    for da,rowCol in daTable.par2pos.values():
        #print('updating DA(%i,%i): '%rowCol, da.name, da.currentValue)
        if 'R' not in da.attr['features']:
            continue
        if isinstance(da,str):
            printw('logic error')
            continue
        try:
            val = da.currentValue['v']
            printd('val:%s'%str(val)[:100])
            if val is None:
                try:
                    window.table.item(*rowCol).setText('none')
                except:  pass
                continue
            if da.guiType == 'spinbox':
                printd('LDO '+da.name+' is spinbox '+str(val[0]))
                #print(str(window.table.cellWidget(*rowCol).value()))
                try:    v = int(val[0])#DNW with QDoubleSpinBox
                except: v = float(val[0])
                window.table.cellWidget(*rowCol).setValue(v)
                continue
            elif da.guiType =='bool':
                printd('LDO '+da.name+' is bool')
                state = window.table.item(*rowCol).checkState()
                printd('LDO '+da.name+' is bool = '+str(val)+', state:'+str(state))
                if val[0] != (state != 0):
                    #print('flip')
                    window.table.item(*rowCol).setCheckState(val[0])
                continue
            #print('LDO '+da.name+' is '+str(type(val)))
            if isinstance(val,np.ndarray):
                printd('LDO '+da.name+' is ndarray')
                txt = '%s: %s'%(val.shape,str(val))
            else:
                if len(val) > 1:
                    printd('LDO '+da.name+' is list')
                    txt = str(val)
                else:
                    val = val[0]
                    printd('LDO '+da.name+' is '+str(type(val)))
                    if type(val) in (float,int,str):
                        txt = str(val)
                    else:
                        txt = 'Unknown type of '+da.name+'='+str(type(val))
                        printw(txt+':'+str(val))
                        txt = str(val)
            #print('settext(%i,%i) %s'%(*rowCol,txt))
            widget =  window.table.cellWidget(*rowCol)
            if not widget:
                widget = window.table.item(*rowCol)
            widget.setText(txt)
        except Exception as e:
            errMsg = 'MySlot ' + str(e)
            printw(errMsg)
            #print('Traceback: '+repr(traceback.format_exc()))
            break
    if LDOMonitor.Perf: print('GUI update time: %.4f'%(timer()-ts))    
    myslotBusy = False
    if errMsg:  Window.bottomLine.setText('WARNING: '+errMsg) #Issue, it could be long delay here
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
#````````````````````````````Data provider
class LDOMonitor(QtCore.QThread):
    Perf = False
    # inheritance from QtCore.QThread is needed for qt signals
    SignalSourceDataReady = QtCore.pyqtSignal(object)
    def __init__(self):
        # for signal/slot paradigm we need to call the parent init
        super(LDOMonitor,self).__init__()

        # create list of aggregated LDOs for each host
        self.hostLdos = {}
        for host,longListOfLNames in daTable.hostRequest.items():
            self.hostLdos[host] = LA.LdoPars(longListOfLNames)
            
        # start the receiving thread 
        thread = threading.Thread(target=self.thread_proc)
        thread.start()
        self.SignalSourceDataReady.connect(MySlot)

    def thread_proc(self):
        printd('>thread_proc')
        while not EventExit.isSet():
            # collect data from all hosts and fill daTable with data
            dataReceived = True
            for host,aggregatedLdo in self.hostLdos.items():
                
                # get values of all parameters from the host
                #print('host,ldo',host,aggregatedLdo.name)
                if LDOMonitor.Perf: ts = timer()
                try:
                    r = aggregatedLdo.get()
                except Exception as e:
                    msg = 'ERR.LP '+str(e)[:80]
                    #print(msg)
                    Window.bottomLine.setText(msg)
                    dataReceived = False
                    break
                if not isinstance(r,dict):
                    print('ERR.LP. unexpected response: '+str(r)[:80])
                    break
                if LDOMonitor.Perf: print('retrieval time from %s = %.4fs'\
                %(host,timer()-ts))
                
                # update GUI elements
                #pprint('got from %s \n'%host+str(r))
                for hostDev,parDict in r.items():
                    #print('update GUI objects of %s :'% hostDev + str(parDict))
                    for par,valDict in parDict.items():
                        hostDevPar = hostDev+','+par
                        dataAccess = daTable.par2pos[hostDevPar][0]
                        dataAccess.currentValue = valDict
            if dataReceived:    self.SignalSourceDataReady.emit(None)
            EventExit.wait(2)
        print('<thread_proc')
#,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
class DataAccess():
    """Process Variable object, provides getter and setter"""
    def __init__(self,cnsNameDev,parName='*',attribute='value'):
        self.cnsNameDev = cnsNameDev
        self.name = ','.join(cnsNameDev+[parName])
        #print('DA name: '+self.name)
        self.ldo = LA.LdoPars([(self.cnsNameDev,parName)])

        # process ldo info
        info = self.ldo.info()
        #print('DA info for %s: '%self.name+str(info))
        # we don't care about cnsNameDev key, as only one entry expected
        info = list(info.values())[0]
        # creating attributes from remote ones
        self.key = list(info)[0]
        self.attr = info[self.key]

        # process initial value
        v = self.ldo.value
        self.initialValue = self.ldo.value[0]
        self.latestValueTS = None
        #print('iv of ',self.name,str(self.initialValue)[:60])
        self.guiType = self._guiType()
        #print('guiType of %s: '%self.name+str(self.guiType))
        #self.t = 0.

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
            if type(iv[0]) == str:
                return 'lineEdit'
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

class DataAccessTable():
    """DataAccess table maps: parameter to (row,col) and (row,col) to object"""
    def __init__(self,fileName):
        
        self.par2pos = OD()
        self.pos2obj = OD()
        maxcol = 0
        self.hostRequest = {}# holds combined requests for each host
        with open(fileName,'r') as infile:
            config = yaml.load(infile,Loader=yaml.FullLoader) 
            #pprint(('config:',config))
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
                    # it should be of the form: [['$...
                    try:    cellIsLdo = cell[0][0][0] == '$'
                    except: cellIsLdo = False
                    if not cellIsLdo:
                        if isinstance(cell[0],str):
                            #print('merged non-ldo cells: '+str(cell))
                            self.pos2obj[(row,col)] = cell,cellFeatures
                        else:
                            print("cell[%i,%i] must be a ['host;port',dev]: "\
                            %(row,col)+str(cell[0]))
                            print('Not supported yet')
                        continue

                    # cell is a data access object
                    # cell[:2] is LDO,par, optional cell[2] is cell property
                    #print('cell[%i,%i] is DA: '%(row,col)+str(cell))
                    try:    cnsNameDev,par = cell[0],cell[1]
                    except: raise NameError('expect DA,par, got: '+str(cell))
                    #remove $ from the cnsName
                    cnd = cnsNameDev.copy()
                    cnd[0] = cnd[0][1:]
                    #print( 'the cell[%i,%i] is cnd: %s,%s'%(row,col,str(cnd),par))
                    if True:# Do not catch exception here!#try:
                        da = DataAccess(cnd,par)
                        self.pos2obj[(row,col)] = da,cellFeatures
                        # add to host request list
                        #only one item expected
                        chlist = list(da.ldo.channelMap.items())
                        host = chlist[0][0]
                        if host in self.hostRequest:
                           self.hostRequest[host].append([cnd,par])
                        else: self.hostRequest[host] = [[cnd,par]]
                        continue
                    else:#except Exception as e:
                        txt = 'Cannot create DataAccess %s:'%cell+str(e)
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
        #pprint(self.pos2obj)
        #print('hostRequest',self.hostRequest)

def build_temporary_pvfile(cnsName):
    fname = 'pvsheet.tmp'
    print('>build_temporary_pvfile')
    cnsInfo = LA.LdoPars([[[cnsName,'*'],'*']]).info()
    fname = 'ldoPet.yaml'
    f = open(fname,'w')
    f.write('rows:\n')
    # loop through all devices on the server
    for ldo,parDict in cnsInfo.items():
        print('ldo',ldo)
        host,device = ldo.split(',')
        print('hd',host,device)
        if not pargs.server and device == 'server':
            continue
        f.write("  - [['%s',{span: [3,1],color: cyan}]]\n"%ldo)
        for par,props in parDict.items():
            f.write("  - ['%s',[[$%s],%s]]\n"%(par,ldo,par))
    f.close()
    print('DataAccess spreadsheet config file generated: %s'%fname)
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
    parser.add_argument('-s','--server', action='store_true'\
    ,help='show server variables')
    parser.add_argument('-t','--timeout',type=float,default=10,
      help='timeout of the receiving socket')
    parser.add_argument('ldo', nargs='?', default='localhost',
      help='LDOs: lite data objects')
    pargs = parser.parse_args()
    LA.LdoPars.Dbg = pargs.dbg# transfer dbg flag to liteAccess

    if pargs.file:
        print('Monitoring DataAccess as defined in '+pargs.file)
    else:
        print('Monitoring LDOs: '+str(pargs.ldo))
        pargs.file = build_temporary_pvfile(pargs.ldo)
    app = QtWidgets.QApplication(sys.argv)

    # read config file
    daTable = DataAccessTable(pargs.file)

    # define GUI
    window = Window(*daTable.shape)
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

