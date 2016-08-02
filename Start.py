import sys
import os
import thread
import time
import PIL
import pygame
import pygame.camera
from pygame.locals import *
import string
import math, random, sys
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from shutil import copyfile
from PySide.QtCore import QObject, Signal, Slot
from PySide.QtGui import QImage, QImageReader, QLabel, QPixmap, QApplication
from PyQt4 import QtCore, QtGui
from PyQt4.QtGui import QPixmap
from StopMotion import Ui_SMpp
import threading
#my class that's holding project specific data:
from projectclass import SMData


#Lock for writing and reading and moving the "grab" file "data/latest.png"
#FileLock = fasteners.InterProcessLock('filelockfile')

#the name of this project, for example "MyStopmotion part 7"
ProjectName = ""

#where our scripts live (we start at this dir)
BaseDir =""

#where all the project-specific data lives (for example C:\Prog\PC\StopMotion\data\MyStopmotion part 7)
ProjectDir =""

#The capture camera
CaptureCamera = pygame.camera.Camera
#cameras's grab surface
GrabSurface = pygame.Surface
#It's delay (will be changed in TabSelector())
GrabFrameDelay = 0.500

#GrabData in raw format (so you can 'grab' it / display it)
#lock this data
GrabStringData = ""
#last grabbed image
LastGrabStringData = ""
LatestImage = QtGui.QImage(640, 480, QtGui.QImage.Format_ARGB32)

#set to true so thread can Grab an image (under lock)
PleaseGrabLatestImage = False

#TotalNumberOfFrames (only modified when you start a project or grab a new frame, or remove frames)
TotalNumberOfFrames = 0

#EDIT variables: (used to play and edit)
ActiveFrame = 0

#caches the image
PixMapCache = dict()

#playback variables
Playback_fps = 12
Playback_play = False

#use when copying images grabbing etc
lock = threading.Lock()


class StartQT4(QtGui.QMainWindow):
    punched = Signal()
    ProjectData = SMData()

    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.ui = Ui_SMpp()
        self.ui.setupUi(self)
        QtCore.QObject.connect(self.ui.pbSetProjectPath,QtCore.SIGNAL("clicked()"), self.SetProjectPath)
        QtCore.QObject.connect(self.ui.sProjectName,QtCore.SIGNAL("returnPressed()"), self.SetProjectPath)
        
        QtCore.QObject.connect(self.ui.pbSaveProject,QtCore.SIGNAL("clicked()"), self.SaveProject)
        
        QtCore.QObject.connect(self.ui.pbGrab,QtCore.SIGNAL("clicked()"), self.GrabFrame)
        QtCore.QObject.connect(self.ui.pbRemovetLastImage,QtCore.SIGNAL("clicked()"), self.RemovetLastImage)
        QtCore.QObject.connect(self.ui.pbExport,QtCore.SIGNAL("clicked()"), self.ExportAVI)
        
        self.ui.tabWidget.currentChanged.connect(self.TabSelector)
        
        QtCore.QObject.connect(self.ui.horizontalSlider, QtCore.SIGNAL('valueChanged(int)'), self.SliderChanged)

        #connect worker thread with main
        self.connect(self, SIGNAL("cameraStreamUpdated"), self.cameraStreamUpdated)
        self.connect(self, SIGNAL("frameGrabbed"), self.GrabFrameBackSignal)
        
        
        
        #Tab3
        QtCore.QObject.connect(self.ui.pbPlay,QtCore.SIGNAL("clicked()"), self.PlayButton)
        

    #use like this:
    #pix = QtGui.QPixmap.fromImage(diffimage)
    #self.ui.labelLiveStream.setPixmap(pix)
    def MakeDiffImage(self, input, last): #input is the video stream, last is the last grabbed frame
        #make a QImage with the diff from these two QImages
        import numpy as np
        import qimage2ndarray
        
        npinput = qimage2ndarray.rgb_view(input)
        nplast = qimage2ndarray.rgb_view(last)
        
        #nplast = nplast/2 + npinput/2
        #print type(npinput)
        
        qImage = qimage2ndarray.array2qimage(npinput, normalize = False) # create QImage from ndarray
        return qImage
        #success = qImage.save("tmp.png") # use Qt's image IO functions for saving PNG/JPG/..

    def LoadConfiguration(self):
        import json
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
            global ProjectName
            ProjectName = config['ProjectName']
            print "Projectname:" , ProjectName
            self._SetProjectPath(ProjectName)
            
            self.ui.cbCacheModeOnEdit.setChecked( config['cbCacheModeOnEdit'] == 'True' )
            self.ui.cbCacheModeOnStartup.setChecked( config['cbCacheModeOnStartup'] == 'True' )
            self.ui.cbRenameDeletedfiles.setChecked( config['cbRenameDeletedfiles'] == 'True' )
            
            print "checked: ", config['cbRenameDeletedfiles']
            print ( config['cbRenameDeletedfiles'] == 'True' )
            
        except IOError, e:
            print "Load config error (if it is the first time you run the program, no worries)"
            print e.errno
            print e

    def SaveConfiguration(self):
        import json
        config = {}
        #config['key3'] = 'value3'   #example
        config['ProjectName'] = ProjectName
        if self.ui.cbCacheModeOnEdit.isChecked():
            config['cbCacheModeOnEdit']= 'True'
        else:
            config['cbCacheModeOnEdit']= 'False'
        if self.ui.cbCacheModeOnStartup.isChecked():
            config['cbCacheModeOnStartup']= 'True'
        else:
            config['cbCacheModeOnStartup']= 'False'
            
            
        print "save cfg", self.ui.cbRenameDeletedfiles.isChecked()

        if self.ui.cbRenameDeletedfiles.isChecked():
            config['cbRenameDeletedfiles']= 'True'
        else:
            config['cbRenameDeletedfiles']= 'False'
        
        print "save checked:", self.ui.cbRenameDeletedfiles.isChecked()
        
        try:
            with open('config.json', 'w') as f:
                json.dump(config, f)
        except IOError, e:
            print "Save config error"
            print e.errno
            print e

    #external version, connected to button
    def SetProjectPath(self):
        qText = self.ui.sProjectName.text()
        if qText != "":
            self._SetProjectPath(qText)
    
    #internal version with all the code so we can call it with parameters
    def _SetProjectPath(self, folder):
        
        global PixMapCache
        global ProjectName
        global ProjectDir
        global BaseDir
        
        PixMapCache.clear()
        
        if BaseDir == "":
            BaseDir = os.getcwd()
        os.chdir(BaseDir)
        
        if folder == "":
            folder = "DefaultProjectFolder"
        
        print folder
        self.setWindowTitle('Project:' + folder + ' StopMotion++')
    
        #as folder is a QString
        ProjectName = str(folder)
        
        if not os.path.exists("data"):
            os.makedirs("data")
        
        os.chdir("data")
        if not os.path.isdir(ProjectName):
            os.makedirs(ProjectName)
            os.chdir(ProjectName)
            ProjectDir=os.getcwd()
            #print ProjectDir
        
        #always go back to base directory
        os.chdir(BaseDir)
        
        pixmap = QtGui.QPixmap("waitingforcamera.jpg")
        self.ui.labelLiveStream.setPixmap(pixmap)
        self.ui.labelLastGrabNr.setText("No frames grabbed")
        
        global TotalNumberOfFrames
        TotalNumberOfFrames = 0
        
        frames = self.ScanFiles(ProjectName)
        if frames > 0:
            print "Found frames in old projeck, keeping them:"
            print frames
            TotalNumberOfFrames = frames
            
            #load up last image:
            filename = self.MakeFilename(frames)
            print filename
            pixmap = QtGui.QPixmap(filename)
            self.ui.labelLastGrab.setPixmap(pixmap)            
            
            global LatestImage
            LatestImage = pixmap.toImage()
            
            self.ui.labelLastGrabNr.setText("Last grab: "+str(frames))
            if self.ui.cbCacheModeOnStartup.isChecked():
                self.CacheupImages()

        self.SaveConfiguration()
        #enable all tabs
        for i in range(1,4):
            myapp.ui.tabWidget.setTabEnabled(i, True)
        self.ui.tabWidget.setCurrentIndex(1)

    def SaveProject(self):
        print "save", self.ui.cbRenameDeletedfiles.isChecked()

        global ProjectName
        self.ProjectData.Save(ProjectName)

    def MakeFilename(self, frame):
        global ProjectName
        return 'data/'+ProjectName+'/img' + '{0:0{width}}'.format(frame, width=5) + '.png'

    def GrabFrame(self):
        global PleaseGrabLatestImage
        PleaseGrabLatestImage = True
        # the '1' here is the length in frames, maybe it won't be used
        
        self.ProjectData.frames.append(TotalNumberOfFrames)
        #self.ProjectData.frames[TotalNumberOfFrames]=({TotalNumberOfFrames, 1})
        print self.ProjectData.frames

    
    #when thread have seen PleaseGrabLatestImage==True, grabbed, and set
    #PleaseGrabLatestImage=False, it emits this signal so we can update
    #GUI, framenumber and last grabbed image
    def GrabFrameBackSignal(self):
        #print "Grab callback from grab-thread"
        global LatestImage
        global TotalNumberOfFrames
        filename = self.MakeFilename(TotalNumberOfFrames)
        pixmap = QtGui.QPixmap(filename)
        self.ui.labelLastGrab.setPixmap(pixmap)
        LatestImage = pixmap.toImage()
        self.ui.labelLastGrabNr.setText("Last grab: "+str(TotalNumberOfFrames))

    def RemovetLastImage(self):
        global lock
        lock.acquire()
        global TotalNumberOfFrames
        if TotalNumberOfFrames > 0:
            filename = self.MakeFilename(TotalNumberOfFrames)
            if self.ui.cbRenameDeletedfiles.isChecked():
                n = 1
                done = False
                newname =""
                while done == False:
                    newname=filename[:-4]+'_old'+str(n)+'.png'
                    done = True
                    print "chech if old file exists:" , newname
                    if os.path.isfile(newname):
                        done = False
                        n=n+1
                os.rename(filename, newname)
            else:
                os.remove(filename)
            TotalNumberOfFrames = TotalNumberOfFrames - 1
        lock.release()
        self.emit(SIGNAL("frameGrabbed"))
        
    def ExportAVI(self):
        global ProjectName
        print "export movie"
        import subprocess
        
        outputfile = 'output/'+ProjectName+'.mp4'
        #check if output already exists:
        doexport = True
        if os.path.isfile(outputfile):
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Video export")
            msg.setText("The file\n"+outputfile+'\ndoes already exist.\n\nOverwrite?')
            #msg.setInformativeText("This is additional information")
            #msg.setDetailedText("The details are as follows:")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
            retval = msg.exec_()
            if retval != QtGui.QMessageBox.Yes:
                doexport = False
           
        
        if doexport == True:
            #                                     fps      5 zero padding
            subprocess.call('ffmpeg -f image2 -r 5 -i data/'+ProjectName+'/img%05d.png -vcodec mpeg4 -y '+outputfile, shell=True)
            
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Video export")
            msg.setText("Video was probably exported")
            #msg.setInformativeText("This is additional information")
            #msg.setDetailedText("The details are as follows:")
            msg.setStandardButtons(QMessageBox.Ok ) # | QMessageBox.Cancel)
            retval = msg.exec_()

    #the Grab signal
    def cameraStreamUpdated(self ):
        #SLOOOOW
        #pixmap = QtGui.QPixmap("data/latest.png")
        #self.ui.labelLiveStream.setPixmap(pixmap)
        
        # now try to update labelLiveRawStream with the raw data (GrabStringData) instead
        global GrabStringData
        
        global lock
        lock.acquire()
        #print "GrabLock aquired"
        GrabStringData=GrabStringData+'0'
        image = QtGui.QImage(GrabStringData[1:], 640, 480, QtGui.QImage.Format_ARGB32)
        lock.release()
        #print "GrabLock released"
        
        pix = QtGui.QPixmap.fromImage(image)
        self.ui.labelLiveStream.setPixmap(pix)

        #make the diff image
        global LatestImage
        diffimage = self.MakeDiffImage(image, LatestImage) # <- todo)
        pix = QtGui.QPixmap.fromImage(diffimage)
        self.ui.labelGrabDiff.setPixmap(pix)
        
        
    def PlayButton(self):
        global Playback_play
        if Playback_play == True:
            Playback_play = False
        else:
            Playback_play = True
            global ActiveFrame
            ActiveFrame=self.ui.horizontalSlider.value()
            print "Play"
            print "start at frame:" + str(ActiveFrame)

    #handles playback (ie. updates images periodically when "Play" id 'on')
    def ThreadFuncMovie(self):
        global Playback_fps
        global Playback_play
        global TotalNumberOfFrames
        global ActiveFrame
        
        play = False
        
        while 1 == 1:
            if play == True:
                #next image plz
                #filename = self.MakeFilename(frame)
                #pixmap = self.CacheLoadImage(filename)
                #self.ui.labelFilmStream.setPixmap(pixmap)
                ActiveFrame = ActiveFrame + 1
                print "Play: show frame:" + str(ActiveFrame)
                self.ui.horizontalSlider.valueChanged.emit(ActiveFrame)
                if ActiveFrame == TotalNumberOfFrames:
                    play = False
                    Playback_play = False
                    ActiveFrame = 0
                #else:
                
                    
                time.sleep(1.0 / Playback_fps)
            else:
                time.sleep(0.10)
            
            if Playback_play != play:
                play = Playback_play
                if play == True:
                    #start movie
                    play=True
                    frame=ActiveFrame
                else:
                    #stop movie
                    play=False

                   
    
    #Handles the camera stream
    def ThreadFunc(self, threadName, msecdelay):
        print "ThreadFunc starts"
        time.sleep(0.05)
        global CaptureCamera
        global GrabSurface
        global GrabStringData
        global GrabFrameDelay
        GrabFrameDelay=msecdelay/1000.0 
        
        #bag = StartQT4()
        # Connect the bag's punched signal to the say_punched slot
        #bag.punched.connect(testfunc)
        
        while 1 == 1:
            global lock
            CaptureCamera.get_image(GrabSurface)
            locked = False
            sleep = 0.001
            while locked == False:
                locked = lock.acquire(False)
                if locked == False:
                    print "missed trylock, tries again"
                    time.sleep(sleep)
                    sleep=sleep+0.001
                    if sleep == 0.020:
                        print "#Warning: Can't aquire lock (Thread Func)"

            #print "locked!"
            GrabStringData = pygame.image.tostring(
                pygame.transform.flip(GrabSurface, 1, 0), 'RGBA', True)[::-1]  + '0'
            
            
            global PleaseGrabLatestImage
            if PleaseGrabLatestImage == True:
                #self.ui.button_save.setEnabled(True)
                global ProjectName
                print "grab (in thread)"
                global TotalNumberOfFrames
                TotalNumberOfFrames = TotalNumberOfFrames + 1
                filename = self.MakeFilename(TotalNumberOfFrames)
                                
                pygame.image.save(GrabSurface, filename)
                
                #copyfile("data/latest.png", filename)
                
                PleaseGrabLatestImage = False
                
                #todo: send signal so main thread can update GUI:
                self.emit(SIGNAL("frameGrabbed"))

            
            
            
            lock.release()
            #print "released"

            self.emit(SIGNAL("cameraStreamUpdated"))
            time.sleep(GrabFrameDelay)

    def ScanFiles(self, project):
        #project is the foldername for the project (for example "LudvigLest")
        global BaseDir
        import glob
        os.chdir(BaseDir+'/data/'+project+'/')
        frames=0
        for file in glob.glob("*.png"):
            if len(file) == 12:
                file = file[3:][:-4]
                number = int(file)
                if number > frames:
                    frames = number
        #change back
        os.chdir(BaseDir)
        
        return frames

    def TabSelector(self, index):
        print "tab clicked"
        print index
        
        global GrabFrameDelay
        if index == 0:
            GrabFrameDelay = 0.500
            
        
        if index == 1: #Grab
            GrabFrameDelay = 0.050
        
        if index == 2:
            global TotalNumberOfFrames
            print "TotalNumberOfFrames="+str(TotalNumberOfFrames)
            #set grab to really slow, otherwise we'll have lock problems (yes, even with the try-locks)
            GrabFrameDelay = 0.500
            
            #quickly preload images (if not too many) TODO make this a configurable parameter
            #if TotalNumberOfFrames < 1000: #a 640*480 img takes around 1.2MB so 1000 excededes slightly the GB
            #cache files
            if self.ui.cbCacheModeOnEdit.isChecked():
                self.CacheupImages()
            
            self.StartEdit()

        if index == 3:
            GrabFrameDelay = 0.500
            
    def CacheupImages(self):
        global TotalNumberOfFrames
        #cache files
        for i in range(1,TotalNumberOfFrames+1):
            self.CacheLoadImage(self.MakeFilename(i))
    
    
    def CacheLoadImage(self, filename):
        from os.path import basename
        global PixMapCache
        #so abx/img0001.png is the same as img001.png (because we scan files in the beginning, so without folder)
        basefilename = basename(filename)
        if basefilename in PixMapCache:
            #Already loaded
            return PixMapCache[basefilename]
        else:
            #Load up
            print "Load up and cache image: "+filename
            pixmap = QtGui.QPixmap(filename)
            print "loaded file:"+filename
            print "store in:"+basefilename
            PixMapCache[basefilename] = pixmap
            return pixmap
            
    
##############################################################
# EDIT

    def SliderChanged(self, value):
        print "Slider Changed: "+str(value+1)
        filename = self.MakeFilename(value)
        pixmap = self.CacheLoadImage(filename)
        self.ui.labelFilmStream.setPixmap(pixmap)
        global TotalNumberOfFrames
        text = "Frame "+str(value)+" / "+str(TotalNumberOfFrames)
        self.ui.labelFrameNumber.setText(text)
        self.ui.labelFrameNumber2.setText(str(value))
        #used for playback, TODO doesn't work
        self.ui.horizontalSlider.setValue(value)
    
    def StartEdit(self):
        print "Edit tab clicked"
        global ActiveFrame
        global TotalNumberOfFrames #<- if we have 4 frames (0,1,2,3), this one equals 4, "next grabframe"
        
        #set min max changes
        self.ui.horizontalSlider.setMinimum(1)
        self.ui.horizontalSlider.setMaximum(TotalNumberOfFrames)
        #we need to do this to apply the min/max changes
        self.SliderChanged(1)




    def StopEdit(self):
        print "if needed"

    def closeEvent(self, event):
        #catched exit signal, lets save off sonfig:
        self.SaveConfiguration()
        #later on save project (Yes/No?)






if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    myapp = StartQT4()
    myapp.setWindowTitle('StopMotion++')
    myapp.show()
    
    print "initializing camera"
    pygame.camera.init()
	
	#run through innput devices (cameras)and update cbInputDevice
    camlist = pygame.camera.list_cameras()
    print "Camlist: ",camlist
    if not camlist:
        raise ValueError("Sorry, no cameras detected.")
    
    for input in camlist:
        print "Camera detected:" + str(input)
    
    #for now, grab the first one, todo: do it in the tab "Grab"
    cam = pygame.camera.Camera(camlist[0],(640,480))
        
	#cbInputDevice
	
    print "create camera instance" # from selected cbInputDevice
    CaptureCamera = pygame.camera.Camera(0,(640,480),"RGB")
    print "start camera"
    CaptureCamera.start()
    print "create capture surface"
    GrabSurface = pygame.Surface((640,480))
    
    #startup:
    print "Checks for last project:"
    myapp.LoadConfiguration()
    
    #if there is no project, block tabs:
    if ProjectName=="":
        for i in range(1,4):
            myapp.ui.tabWidget.setTabEnabled(i, False)

    #start thread
    thread.start_new_thread( myapp.ThreadFunc, ("Thread-1", 50, ) )
    
    thread.start_new_thread( myapp.ThreadFuncMovie, ( ) )
    
    if myapp.ui.cbCacheModeOnStartup.isChecked():
        myapp.CacheupImages()
    
    
    #exit
    sys.exit(app.exec_())





