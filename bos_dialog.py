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

from PyQt4 import uic
from PyQt4.QtCore import QThread, Qt
#QObject, 
#from PyQt4.QtCore import QCoreApplication, QUrl
from PyQt4.QtGui import QDialog, QDialogButtonBox
from PyQt4.QtGui import QProgressBar
from PyQt4.QtGui import QMessageBox
from PyQt4.QtGui import QPushButton


from PyQt4.QtCore import QPointF, QLineF, QRectF, QPoint, QSettings
from PyQt4.QtCore import QSizeF, QSize, QRect, Qt
from PyQt4.QtCore import QVariant
from PyQt4.QtGui import QDialog, QDialogButtonBox, QFileDialog
from PyQt4.QtGui import QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsTextItem, QFont
from PyQt4.QtGui import QGraphicsScene, QBrush, QPen, QColor
from PyQt4.QtGui import QGraphicsView
from PyQt4.QtGui import QPrinter, QPainter
from PyQt4.QtGui import QApplication, QImage, QPixmap



from qgis.core import QgsMessageLog, QgsMapLayerRegistry
#from qgis.core import QGis
#from qgis.core import QgsMapLayer
from qgis.gui import QgsMessageBar

#from sys.path import append
#append(dirname(__file__))

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
        self.BOSscene = QGraphicsScene(self)
        self.BOSGraphicsView.setScene(self.BOSscene)

        # Connect signals
        okButton.clicked.connect(self.startWorker)
        self.ringcolour = QColor(153, 153, 255)

    def startWorker(self):
        """Initialises and starts the worker thread."""
        try:
            layerindex = self.inputLayer.currentIndex()
            layerId = self.inputLayer.itemData(layerindex)
            inputlayer = QgsMapLayerRegistry.instance().mapLayer(layerId)
            if inputlayer is None:
                self.showError(self.tr('No input layer defined'))
                return
            refindex = self.referenceLayer.currentIndex()
            reflayerId = self.referenceLayer.itemData(refindex)
            reflayer = QgsMapLayerRegistry.instance().mapLayer(reflayerId)
            # not meaningful to 
            if layerId == reflayerId:
                self.showInfo('The reference layer must be different'
                              ' from the input layer!')
                return

            if reflayer is None:
                self.showError(self.tr('No reference layer defined'))
                return
            if reflayer is not None and reflayer.crs().geographicFlag():
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
            #self.showInfo(str(radii))
            #radii = [10,30,50]
            #self.showInfo(str(radii))
            selectedinputonly = self.selectedFeaturesCheckBox.isChecked()
            selectedrefonly = self.selectedRefFeaturesCheckBox.isChecked()
            # create a new worker instance
            worker = Worker(inputlayer, reflayer, radii,
                            selectedinputonly, selectedrefonly)
            # configure the QgsMessageBar
            #msgBar = self.iface.messageBar().createMessage(
            #                                    self.tr('Starting'), '')
            self.aprogressBar = QProgressBar()
            self.aprogressBar.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            acancelButton = QPushButton()
            acancelButton.setText(self.CANCEL)
            acancelButton.clicked.connect(self.killWorker)
            #msgBar.layout().addWidget(self.aprogressBar)
            #msgBar.layout().addWidget(acancelButton)
            # Has to be popped after the thread has finished (in
            # workerFinished).
            #self.iface.messageBar().pushWidget(msgBar,
            #                                   self.iface.messageBar().INFO)
            #self.messageBar = msgBar
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
        #self.showInfo("Worker finished")
        # clean up the worker and thread
        self.worker.deleteLater()
        self.thread.quit()
        self.thread.wait()
        self.thread.deleteLater()
        # remove widget from message bar (pop)
        #self.iface.messageBar().popWidget(self.messageBar)
        if ok and ret is not None:
            # report the result
            stats = ret
            self.showInfo("Returned object: " + str(ret))
            QgsMessageLog.logMessage(self.tr('BOS finished'),
                                     self.BOS, QgsMessageLog.INFO)
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
        self.showPlots(ret)
        # End of workerFinished

    # Very incomplete!
    def showPlots(self, stats):
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
        padleft = 20
        padright = 3

        minx = padleft
        maxx = width - padding
        xsize = maxx - minx
        miny = padding
        maxy = height - padding
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
        boundingbox = QRect(padding,padding,xsize,ysize)
        #rectangle = QRectF(self.BOSGraphicsView.mapToScene(boundingbox))
        #rectangle = self.BOSGraphicsView.mapToScene(boundingbox)
        #self.BOSscene.addRect(rectangle)
        # Add vertical lines
        startx = padleft
        starty = padding
        frompt = QPoint(startx, starty)
        start = QPointF(self.BOSGraphicsView.mapToScene(frompt))
        endx = startx
        endy = padding + ysize
        topt = QPoint(endx, endy)
        end = QPointF(self.BOSGraphicsView.mapToScene(topt))
        line = QGraphicsLineItem(QLineF(start, end))
        line.setPen(QPen(QColor(204, 204, 204)))
        self.BOSscene.addItem(line)
        for i in range(len(sizes)):
            size = sizes[i]
            startx = padleft + xsize * size / maxsize
            starty = padding
            frompt = QPoint(startx, starty)
            start = QPointF(self.BOSGraphicsView.mapToScene(frompt))
            endx = startx
            endy = padding + ysize
            topt = QPoint(endx, endy)
            end = QPointF(self.BOSGraphicsView.mapToScene(topt))
            line = QGraphicsLineItem(QLineF(start, end))
            line.setPen(QPen(QColor(204, 204, 204)))
            self.BOSscene.addItem(line)
        # Add horizontal lines
        for i in range(11):
            startx = padleft
            starty = padding + i * ysize/10.0
            frompt = QPoint(startx, starty)
            start = QPointF(self.BOSGraphicsView.mapToScene(frompt))
            endx = padding + xsize
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
            label.setPos(0,ysize-starty-4)
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
              starty = padding + ysize * (1-prevy)
              frompt = QPoint(startx, starty)
              start = QPointF(self.BOSGraphicsView.mapToScene(frompt))
              endx = padleft + xsize * size / maxsize
              endy = padding + ysize * (1-value)
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
              starty = padding + ysize * (1-prevy)
              frompt = QPoint(startx, starty)
              start = QPointF(self.BOSGraphicsView.mapToScene(frompt))
              endx = padleft + xsize * size / maxsize
              endy = padding + ysize * (1-value)
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
              starty = padding + ysize * (1-prevy)
              frompt = QPoint(startx, starty)
              start = QPointF(self.BOSGraphicsView.mapToScene(frompt))
              endx = paleft + xsize * size / maxsize
              endy = padding + ysize * (1-value)
              topt = QPoint(endx, endy)
              end = QPointF(self.BOSGraphicsView.mapToScene(topt))
              line = QGraphicsLineItem(QLineF(start, end))
              self.BOSscene.addItem(line)
            prevx = size
            prevy = value
            
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
                                 self.BOS, QgsMessageLog.INFO)

    def showError(self, text):
        """Show an error."""
        #self.iface.messageBar().pushMessage(self.tr('Error'), text,
        #                                    level=QgsMessageBar.CRITICAL,
        #                                    duration=3)
        QgsMessageLog.logMessage('Error: ' + text, self.BOS,
                                 QgsMessageLog.CRITICAL)

    def showInfo(self, text):
        """Show info."""
        #self.iface.messageBar().pushMessage(self.tr('Info'), text,
        #                                    level=QgsMessageBar.INFO,
        #                                    duration=2)
        QgsMessageLog.logMessage('Info: ' + text, self.BOS,
                                 QgsMessageLog.INFO)

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


