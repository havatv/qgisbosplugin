# -*- coding: utf-8 -*-
"""
/***************************************************************************
 BOSDialog
                                 A QGIS plugin
 Implements the BOS method for assessing the accuracy of geographical lines
                             -------------------
        begin                : 2017-10-19
        git sha              : $Format:%H$
        copyright            : (C) 2017 by Håvard Tveite
        email                : havard.tveite@nmbu.no
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

from os.path import dirname
from os.path import join
#import os

#2# from PyQt4 import uic
#2# from PyQt4.QtCore import QThread
#2# from PyQt4.QtCore import Qt
#QObject, 
#from PyQt4.QtCore import QCoreApplication, QUrl
#2# from PyQt4.QtGui import QDialog, QDialogButtonBox
#2# from PyQt4.QtGui import QProgressBar
#2# from PyQt4.QtGui import QMessageBox
#2# from PyQt4.QtGui import QPushButton
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QCoreApplication, QObject, QThread
#from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox
from qgis.PyQt.QtWidgets import QPushButton, QProgressBar, QMessageBox
from qgis.PyQt.QtCore import Qt


#2# from qgis.core import QgsMessageLog, QgsMapLayerRegistry
from qgis.core import Qgis
#from qgis.core import QgsMapLayer
from qgis.gui import QgsMessageBar
from qgis.core import QgsProcessingContext

from qgis.core import QgsMessageLog, QgsProject
#, QgsWkbTypes
#from qgis.core import QgsVectorFileWriter, QgsVectorLayer
#from qgis.utils import showPluginHelp

#from sys.path import append
#append(dirname(__file__))

from processing.tools import dataobjects


from .bos_engine import Worker

FORM_CLASS, _ = uic.loadUiType(join(
    dirname(__file__), 'bos_dialog_base.ui'))


class BOSDialog(QDialog, FORM_CLASS):
    def __init__(self, iface, parent=None):
        """Constructor."""
        self.iface = iface
        super(BOSDialog, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)


        # Some constants for translated text
        self.BOS = self.tr('BOS')
        self.BROWSE = self.tr('Browse')
        self.CANCEL = self.tr('Cancel')
        self.HELP = self.tr('Help')
        self.CLOSE = self.tr('Close')
        self.OK = self.tr('OK')
        #self.NUMBEROFSTEPS = 10  # Number of steps

        okButton = self.button_box.button(QDialogButtonBox.Ok)
        okButton.setText(self.OK)
        cancelButton = self.button_box.button(QDialogButtonBox.Cancel)
        cancelButton.setText(self.CANCEL)
        helpButton = self.helpButton
        helpButton.setText(self.HELP)

        # Connect signals
        okButton.clicked.connect(self.startWorker)

    def startWorker(self):
        #plugincontext = QgsProcessingContext().copyThreadSafeSettings()
        plugincontext = QgsProcessingContext()
        plugincontext.setProject(QgsProject.instance())
        self.showInfo("Context: " + str(plugincontext.project().title()))
        """Initialises and starts the worker thread."""
        try:
            layerindex = self.inputLayer.currentIndex()
            layerId = self.inputLayer.itemData(layerindex)
            #2# inputlayer = QgsMapLayerRegistry.instance().mapLayer(layerId)
            inputlayer = QgsProject.instance().mapLayer(layerId)
            if inputlayer is None:
                self.showError(self.tr('No input layer defined'))
                return
            refindex = self.referenceLayer.currentIndex()
            reflayerId = self.referenceLayer.itemData(refindex)
            #2# reflayer = QgsMapLayerRegistry.instance().mapLayer(reflayerId)
            reflayer = QgsProject.instance().mapLayer(reflayerId)
            # not meaningful to 
            if layerId == reflayerId:
                self.showInfo('The reference layer must be different'
                              ' from the input layer!')
                return

            if reflayer is None:
                self.showError(self.tr('No reference layer defined'))
                return
            #if reflayer is not None and reflayer.crs().geographicFlag():
            if reflayer is not None and reflayer.sourceCrs().isGeographic():
                self.showWarning('Geographic CRS used for the reference layer -'
                                 ' computations will be in decimal degrees!')
            #outputlayername = self.outputDataset.text()
            #approximateinputgeom = self.approximate_input_geom_cb.isChecked()
            #joinprefix = self.joinPrefix.text()
            #useindex = True
            #useindex = self.use_index_nonpoint_cb.isChecked()
            #useindexapproximation = self.use_indexapprox_cb.isChecked()
            #distancefieldname = self.distancefieldname.text()
            steps = self.stepsSB.value()
            startradius = self.startRadiusSB.value()
            endradius = self.endRadiusSB.value()
            delta = (endradius - startradius) / (steps - 1)
            radii = []
            for step in range(steps):
                radii.append(startradius + step * delta)
            self.showInfo(str(radii))
            #radii = [10,20,50]
            self.showInfo(str(radii))
            selectedinputonly = self.selectedFeaturesCheckBox.isChecked()
            selectedrefonly = self.selectedRefFeaturesCheckBox.isChecked()
            plugincontext = dataobjects.createContext()
            # create a new worker instance
            worker = Worker(inputlayer, reflayer, plugincontext, radii,
                            selectedinputonly, selectedrefonly)
            # configure the QgsMessageBar
            msgBar = self.iface.messageBar().createMessage(
                                                self.tr('Starting'), '')
            self.aprogressBar = QProgressBar()
            self.aprogressBar.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            acancelButton = QPushButton()
            acancelButton.setText(self.CANCEL)
            acancelButton.clicked.connect(self.killWorker)
            msgBar.layout().addWidget(self.aprogressBar)
            msgBar.layout().addWidget(acancelButton)
            # Has to be popped after the thread has finished (in
            # workerFinished).
            self.iface.messageBar().pushWidget(msgBar,
                                               Qgis.Info)
            self.messageBar = msgBar
            self.showInfo('GUI thread: ' + str(QThread.currentThread()) + ' ID: ' + str(QThread.currentThreadId()))
            # start the worker in a new thread
            thread = QThread(self)
            worker.moveToThread(thread)
            worker.finished.connect(self.workerFinished)
            worker.error.connect(self.workerError)
            worker.status.connect(self.workerInfo)
            worker.progress.connect(self.progressBar.setValue)
            worker.progress.connect(self.aprogressBar.setValue)
            thread.started.connect(worker.run)
            thread.start()
            self.thread = thread
            self.worker = worker
            self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)
            self.button_box.button(QDialogButtonBox.Close).setEnabled(False)
            self.button_box.button(QDialogButtonBox.Cancel).setEnabled(True)
        except:
            import traceback
            self.showError(traceback.format_exc())
        else:
            pass
        # End of startworker

    def workerFinished(self, ok, ret):
        """Handles the output from the worker and cleans up after the
           worker has finished."""
        # clean up the worker and thread
        self.worker.deleteLater()
        self.thread.quit()
        self.thread.wait()
        self.thread.deleteLater()
        # remove widget from message bar (pop)
        self.iface.messageBar().popWidget(self.messageBar)
        self.showInfo("showinfo - ret: " + str(ret))
        if ok and ret is not None:
            # report the result
            stats = ret
            self.showInfo(str(ret))
            QgsMessageLog.logMessage(self.tr('BOS finished'),
                                     self.BOS, Qgis.Info)
        else:
            # notify the user that something went wrong
            if not ok:
                self.showError(self.tr('Aborted') + '!')
            else:
                self.showError(self.tr('No layer created') + '!')
        self.progressBar.setValue(0.0)
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(True)
        self.button_box.button(QDialogButtonBox.Close).setEnabled(True)
        self.button_box.button(QDialogButtonBox.Cancel).setEnabled(False)
        # Do the plotting
        #self.showInfo("Try to plot - " + str(ok) + " ret: " + str (ret))
        #QgsMessageLog.logMessage("Try to plot - " + str(ok) + " ret: " + str (ret),
        #                             self.BOS, Qgis.Info)
        if ok and ret is not None:
            self.showPlots(ret)
        # End of workerFinished


    # Very incomplete!
    def showPlots(self, stats):
      self.showInfo("Showplots")
      try:
        #BOSGraphicsView
        self.BOSscene.clear()
        viewprect = QRectF(self.BOSGraphicsView.viewport().rect())
        self.BOSGraphicsView.setSceneRect(viewprect)
        bottom = self.BOSGraphicsView.sceneRect().bottom()
        top = self.BOSGraphicsView.sceneRect().top()
        left = self.BOSGraphicsView.sceneRect().left()
        right = self.BOSGraphicsView.sceneRect().right()
        height = bottom - top
        width = right - left
        size = width
        self.showInfo("Top: " + str(top) + " Bottom: " + str(bottom) + " Left: " + str(left))
        if width > height:
            size = height
        padding = 3
        padleft = 23
        padright = 6
        padbottom = 10
        padtop = 6

        minx = padleft
        maxx = width - padright
        xsize = maxx - minx
        miny = padtop
        maxy = height - padbottom
        ysize = maxy - miny
        maxval = 0
        maxsize = 0
        sizes = []
        normoiirsizes = []
        normiiirsizes = []
        normiiorsizes = []
        sums = []
        for stat in stats:
            sizet, sizestats = stat
            size = float(sizet)
            sizes.append(size)
            oiir, iiir, iior = sizestats
            oiir = float(sizestats['NULLR'])
            iiir = float(sizestats['IR'])
            iior = float(sizestats['INULL'])
            sum = oiir + iiir + iior
            normoiirsizes.append(oiir/sum)
            normiiirsizes.append(iiir/sum)
            normiiorsizes.append(iior/sum)
            #self.showInfo("OIIR: " + str(oiir) + " IIIR: " + str(iiir) + " IIOR: " + str(iior))
            if maxval < oiir:
                maxval = oiir
            if maxval < iiir:
                maxval = iiir
            if maxval < iior:
                maxval = iior
            if maxsize < size:
                maxsize = size
        self.showInfo("Maxval: " + str(maxval) + " Maxsize: " + str(maxsize) + " Steps: " + str(len(sizes)))
        # Prepare the graph
        boundingbox = QRect(padleft,padtop,xsize,ysize)
        #rectangle = QRectF(self.BOSGraphicsView.mapToScene(boundingbox))
        #rectangle = self.BOSGraphicsView.mapToScene(boundingbox)
        #self.BOSscene.addRect(rectangle)

        # Add vertical lines
        startx = padleft
        starty = padtop
        frompt = QPoint(startx, starty)
        start = QPointF(self.BOSGraphicsView.mapToScene(frompt))
        endx = startx
        endy = padtop + ysize
        topt = QPoint(endx, endy)
        end = QPointF(self.BOSGraphicsView.mapToScene(topt))
        line = QGraphicsLineItem(QLineF(start, end))
        line.setPen(QPen(QColor(204, 204, 204)))
        self.BOSscene.addItem(line)
        for i in range(len(sizes)):
            size = sizes[i]
            startx = padleft + xsize * size / maxsize
            starty = padtop
            frompt = QPoint(startx, starty)
            start = QPointF(self.BOSGraphicsView.mapToScene(frompt))
            endx = startx
            endy = padtop + ysize
            topt = QPoint(endx, endy)
            end = QPointF(self.BOSGraphicsView.mapToScene(topt))
            line = QGraphicsLineItem(QLineF(start, end))
            line.setPen(QPen(QColor(204, 204, 204)))
            self.BOSscene.addItem(line)
            labeltext = str(sizes[i])
            label = QGraphicsTextItem()
            font = QFont()
            font.setPointSize(6)
            label.setFont(font)
            label.setPos(startx-6,ysize+padtop-4)
            label.setPlainText(labeltext)
            self.BOSscene.addItem(label)

        # Add horizontal lines
        for i in range(11):
            startx = padleft
            starty = padtop + i * ysize/10.0
            frompt = QPoint(startx, starty)
            start = QPointF(self.BOSGraphicsView.mapToScene(frompt))
            endx = padleft + xsize
            endy = starty
            topt = QPoint(endx, endy)
            end = QPointF(self.BOSGraphicsView.mapToScene(topt))
            line = QGraphicsLineItem(QLineF(start, end))
            line.setPen(QPen(QColor(204, 204, 204)))
            self.BOSscene.addItem(line)
            labeltext = str(i*10)+'%'
            label = QGraphicsTextItem()
            font = QFont()
            font.setPointSize(6)
            label.setFont(font)
            label.setPos(-2,ysize-starty+padtop-4)
            label.setPlainText(labeltext)
            self.BOSscene.addItem(label)
        # Plot Outside input, Inside reference
        first = True
        for i in range(len(sizes)):
            size = sizes[i]
            value = normoiirsizes[i]
            if first:
              first = False
            else:
              startx = padleft + xsize * prevx / maxsize
              starty = padtop + ysize * (1-prevy)
              frompt = QPoint(startx, starty)
              start = QPointF(self.BOSGraphicsView.mapToScene(frompt))
              endx = padleft + xsize * size / maxsize
              endy = padtop + ysize * (1-value)
              topt = QPoint(endx, endy)
              end = QPointF(self.BOSGraphicsView.mapToScene(topt))
              line = QGraphicsLineItem(QLineF(start, end))
              line.setPen(QPen(self.ringcolour))
              self.BOSscene.addItem(line)
            prevx = size
            prevy = value
        # Plot Inside input, Inside reference
        first = True
        for i in range(len(sizes)):
            size = sizes[i]
            value = normiiirsizes[i]
            if first:
              first = False
            else:
              startx = padleft + xsize * prevx / maxsize
              starty = padtop + ysize * (1-prevy)
              frompt = QPoint(startx, starty)
              start = QPointF(self.BOSGraphicsView.mapToScene(frompt))
              endx = padleft + xsize * size / maxsize
              endy = padtop + ysize * (1-value)
              topt = QPoint(endx, endy)
              end = QPointF(self.BOSGraphicsView.mapToScene(topt))
              line = QGraphicsLineItem(QLineF(start, end))
              self.BOSscene.addItem(line)
            prevx = size
            prevy = value
        # Plot Inside input, Outside reference
        first = True
        for i in range(len(sizes)):
            size = sizes[i]
            value = normiiorsizes[i]
            if first:
              first = False
            else: 
              startx = padleft + xsize * prevx / maxsize
              starty = padtop + ysize * (1-prevy)
              frompt = QPoint(startx, starty)
              start = QPointF(self.BOSGraphicsView.mapToScene(frompt))
              endx = padleft + xsize * size / maxsize
              endy = padtop + ysize * (1-value)
              topt = QPoint(endx, endy)
              end = QPointF(self.BOSGraphicsView.mapToScene(topt))
              line = QGraphicsLineItem(QLineF(start, end))
              self.BOSscene.addItem(line)
            prevx = size
            prevy = value
        # Do completeness
        #plotCompleteness()    

      except:
        import traceback
        #self.showInfo("Error plotting")
        self.showInfo(traceback.format_exc())






    def killWorker(self):
        """Kill the worker thread."""
        if self.worker is not None:
            self.showInfo(self.tr('Killing worker'))
            self.worker.kill()

    def workerError(self, exception_string):
        """Report an error from the worker."""
        self.showError(exception_string)

    def workerInfo(self, message_string):
        """Report an info message from the worker."""
        QgsMessageLog.logMessage(self.tr('Worker') + ': ' + message_string,
                                 self.BOS, Qgis.Info)

    def showError(self, text):
        """Show an error."""
        self.iface.messageBar().pushMessage(self.tr('Error'), text,
                                            level=Qgis.Critical,
                                            duration=3)
        QgsMessageLog.logMessage('Error: ' + text, self.BOS,
                                 Qgis.Critical)

    def showInfo(self, text):
        """Show info."""
        self.iface.messageBar().pushMessage(self.tr('Info'), text,
                                            level=Qgis.Info,
                                            duration=2)
        QgsMessageLog.logMessage('Info: ' + text, self.BOS,
                                 Qgis.Info)

    # Implement the accept method to avoid exiting the dialog when
    # starting the work
    def accept(self):
        """Accept override."""
        pass

    # Implement the reject method to have the possibility to avoid
    # exiting the dialog when cancelling
    def reject(self):
        """Reject override."""
        # exit the dialog
        QDialog.reject(self)



