
import sys
import threading
import time
import numpy as np
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QMessageBox
from PyQt5.QtCore import pyqtSignal, QObject, QThread
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from MainWindow import Ui_MainWindow
from PyQt5.QtWidgets import QDialog, QFileDialog
import pandas as pd
from datetime import datetime

import seabreeze.spectrometers
from seabreeze.spectrometers import Spectrometer as sm

print(seabreeze.spectrometers.list_devices()[0].serial_number)


doAverage = False
numAverage = 10
integrationTime = 1000
subBackground = False
ContSave = False
running = True

#moving average without padding
def movingaverage(interval, window_size):
    window= np.ones(int(window_size))/float(window_size)
    return np.convolve(interval, window, 'same')

# Worker class to handle fetching data from the spectrometer in the background
class Worker(QObject):
    data_fetched = pyqtSignal(np.ndarray, np.ndarray)
    def __init__(self, spectrometer):
        super().__init__()  
        self.spectromter = spectrometer
        self.running = True
        
    def run(self):
        global running
        # Simulate data fetching
        print("worker run started")
        while self.running:
            self.spectromter.integration_time_micros(integrationTime)
            time.sleep(0.05)  #if there is no sleep, it will crash if it is not triggered
            wavelengths_spec = self.spectromter.wavelengths()[30:] #cut the first 30 values because the spectrometer gives out a weird artifacat there
            intensities_spec = self.spectromter.intensities()[30:]
            self.data_fetched.emit(wavelengths_spec, intensities_spec)



# Matplotlib canvas class to create a plot
class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.ax = fig.add_subplot(111)
        super().__init__(fig)
        self.setParent(parent)
        # self.ax.set_xlim(900, 1100)
        self.line, = self.ax.plot([], [])        
        self.wavelengths  = []
        self.intensities = []

    def update_plot(self, wavelengths, intensities):
        self.ax.relim()
        self.ax.autoscale_view()
        if subBackground:
            intensities -= background
        if ContSave:
            df = pd.DataFrame()
            df.insert(0,"wavelength",wavelengths)
            df.insert(0,"intensity",intensities)
            df.to_csv(savePath+filePrefix + str(datetime.now()).replace(" ", "").replace(":", "-")+".dat", sep="\t")
        if doAverage:
            intensities = movingaverage(intensities, numAverage)
        self.wavelengths = wavelengths
        self.intensities = intensities
        self.line.set_data(wavelengths, intensities)
        self.draw()    


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.connectSignalsSlots()
        self.worker = None
        self.threadRef = None
        self.appRef = None
        self.setWindowTitle("Spectrometer Data Test")
        
        # self.canvas = MplCanvas()
        self.canvas = MplCanvas(self, width=5, height=4, dpi=100)
        self.plotLayout = QVBoxLayout(self.plotWidget)  # Assuming plotWidget is the name of the placeholder widget
        self.plotLayout.addWidget(self.canvas)
        
        
        self.spectrometers = list()
        self.initSpectrometerList()

    """
    HIER WERDEN DIE EINZELNEN SIGNALS MIT DEN SLOTS VERBUNDEN
    siehe QT5 Doc
    """
    def connectSignalsSlots(self):
       self.nAverage.valueChanged.connect(self.updateParams)
       self.IntTime.valueChanged.connect(self.updateParams)
       self.checkAverage.clicked.connect(self.updateParams)
       self.checkContSave.clicked.connect(self.updateParams)
       self.TriggerMode.currentIndexChanged.connect(self.updateParams)
       
       # self.SpecLowerBound.valueChanged.connect(self.updateParams)
       self.SpecLowerBound.valueChanged.connect(self.updateParams)
       self.SpecUpperBound.valueChanged.connect(self.updateParams)
       self.nAverage.valueChanged.connect(self.updateParams)

       self.lineEdit_file.textChanged.connect(self.updateParams)
       self.lineEdit_path.textChanged.connect(self.updateParams)
       self.browseButton.clicked.connect(self.browse)
       
       self.btnBackground.clicked.connect(self.save_background)
       self.btnSaveSpec.clicked.connect(self.save_current_spec)
       self.checkSub.clicked.connect(self.updateParams)

       self.btnExit.clicked.connect(self.close_application)
       self.listSpec.currentIndexChanged.connect(self.updateCurrentSpectrometer)
       
     
    
    def update_plot(self, wavelengths, intensities):
        self.canvas.update_plot(wavelengths, intensities)
        
    def updateCurrentSpectrometer(self):
        if self.worker is not None:
            self.stopCurrentSpektrometer()
        serial = self.spectrometers[self.listSpec.currentIndex()]
        self.openSpectrometer(serial)
        self.startSpektrometer()
        
    # functions for opening and closing a new spectrometer, when a new one is selected
    def openSpectrometer(self, serialNumber):
        print("opening new spectrometer")
        spec = sm.from_serial_number(serialNumber)
        spec.trigger_mode(0)
        self.spec = spec
    def startSpektrometer(self):
        self.worker = Worker(self.spec)
        thread = QThread()
        self.worker.moveToThread(thread)
        thread.started.connect(self.worker.run)
        thread.start()
        self.worker.data_fetched.connect(self.update_plot)
        self.setThreadReference(thread)
    def stopCurrentSpektrometer(self):
        print("closing current spectrometer")
        self.worker.running = False
        self.threadRef.terminate()
        time.sleep(1.05)  #sleep so the worker is always terminated before the spectrometer is closed
        self.spec.close() #close connection to spectrometer
        
        
    def setThreadReference(self, thread):
        self.threadRef = thread
        
    def setAppReference(self, app):
        self.appRef = app
        
   
    def initSpectrometerList(self):
        print("")
        for index, spectrometer in enumerate(seabreeze.spectrometers.list_devices()):
            serialNum = spectrometer.serial_number
            self.spectrometers.append(serialNum)
            self.listSpec.addItem(serialNum)
        
    def save_background(self):
        global background
        background = self.canvas.intensities
        print(background)
        
    def save_current_spec(self):
        df = pd.DataFrame()
        df.insert(0,"wavelength",self.canvas.wavelengths)
        df.insert(0,"intensity",self.canvas.intensities)
        df.to_csv(savePath+filePrefix + str(datetime.now()).replace(" ", "").replace(":", "-")+".dat", sep="\t")
        
    def set_axis_limits(self, xlim):
        self.canvas.ax.set_xlim(xlim)
        self.canvas.draw()
    
    def close_application(self):    
        self.close()
        self.stopCurrentSpektrometer()
        print("FinishedClosing Bye")
        
        if self.appRef is not None:
            self.appRef.quit()
        
    def browse(self):
        savePath = QFileDialog.getExistingDirectory() +"/"
        self.lineEdit_path.setText(savePath) 

    """
    Falls die Parameter geändert werden soll das aktualisiert werden
    """
    def updateParams(self):
        global doAlwaysWrite, subBackground, lowerBounds, upperBounds, doAverage, numAverage, integrationTime
        global averageSum,averageCount,writeContinu, ContSave, TriggerIndex
        global filePrefix, savePath, FFTlower, FFTupper, writeAllAv, windowFunction, doOffset, linOffset, doFFTRemoveAv
        # global doZeroPad
        

        # doAlwaysWrite = self.checkWrite.isChecked()
        subBackground = self.checkSub.isChecked()
        
        lowerBounds = self.SpecLowerBound.value()
        upperBounds = self.SpecUpperBound.value()
        
        
        doAverage = self.checkAverage.isChecked()
        numAverage = self.nAverage.value()
        
        integrationTime = self.IntTime.value() #in micro seconds
        
        TriggerIndex = self.TriggerMode.currentIndex()
        self.spec.trigger_mode(TriggerIndex)
        ContSave = self.checkContSave.isChecked()
        filePrefix = self.lineEdit_file.text()
        savePath = self.lineEdit_path.text()
        
        self.set_axis_limits((lowerBounds, upperBounds))
        
def main():
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.setAppReference(app)

    main_window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()








































