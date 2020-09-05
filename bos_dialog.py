# -*- coding: utf-8 -*-
"""
/***************************************************************************
 BOSDialog
                                 A QGIS plugin
 Implements the BOS method for assessing the accuracy of geographical lines
                             -------------------
        begin                : 2019-03-12
        git sha              : $Format:%H$
        copyright            : (C) 2019 by Håvard Tveite
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
import os
import csv
import math

import matplotlib as mpl
from matplotlib.figure import Figure
from matplotlib import ticker
# from matplotlib import axes
from matplotlib.backends.backend_qt5agg import FigureCanvas
from matplotlib.backends.backend_qt5agg import (NavigationToolbar2QT as
                                                NavigationToolbar)
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtCore import QCoreApplication, QObject, QThread

from qgis.PyQt.QtCore import QPointF, QLineF, QRectF, QPoint, QSettings
from qgis.PyQt.QtCore import QSizeF, QSize, QRect
# from qgis.PyQt.QtCore import QCoreApplication, QUrl
from qgis.PyQt.QtCore import QUrl

from qgis.PyQt.QtWidgets import (QGraphicsLineItem, QGraphicsEllipseItem,
                                 QGraphicsTextItem)
from qgis.PyQt.QtGui import QFont
# from qgis.PyQt import Qwt5  # Does not seem to be available

# from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox
from qgis.PyQt.QtWidgets import QFileDialog
from qgis.PyQt.QtWidgets import QPushButton, QProgressBar, QMessageBox
from qgis.PyQt.QtWidgets import QGraphicsScene
from qgis.PyQt.QtWidgets import QGraphicsView
#
from qgis.PyQt.QtGui import QBrush, QPen, QColor
from qgis.PyQt.QtGui import QPainter
from qgis.PyQt.QtPrintSupport import QPrinter
from qgis.PyQt.QtSvg import QSvgGenerator
from qgis.PyQt.QtGui import QDesktopServices

# from qgis.PyQt.QtGui import QApplication, QImage, QPixmap


from qgis.core import Qgis
# from qgis.core import QgsMapLayer
from qgis.gui import QgsMessageBar
from qgis.core import QgsProcessingContext

from qgis.core import QgsMessageLog, QgsProject
# , QgsWkbTypes
# from qgis.core import QgsVectorFileWriter, QgsVectorLayer
# from qgis.utils import showPluginHelp

# from sys.path import append
# append(dirname(__file__))

from processing.tools import dataobjects


from .bos_engine import Worker

FORM_CLASS, _ = uic.loadUiType(join(
    dirname(__file__), 'bos_dialog_base.ui'))


class BOSDialog(QDialog, FORM_CLASS):
    def __init__(self, iface, parent=None):
        """Constructor."""
        self.iface = iface
        self.plugin_dir = dirname(__file__)
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
        self.COMPLETENESS = self.tr('Completeness')
        self.OSCILLATIONS = self.tr('Oscillations')
        self.DISPLACEMENT = self.tr('Displacement')
        self.AVERAGEDISPLACEMENT = self.tr('Average displacement')
        self.COMBINED = self.tr('Combined')
        self.results = None
        self.plott = None
        self.figure = None
        self.plotsizex = 0
        self.plotsizey = 0

        # Variables for the X and Q line layers
        self.Xlayer = None
        self.Qlayer = None

        # Variables for the selected checkboxes
        self.selectedinputonly = False
        self.selectedrefonly = False
        okButton = self.button_box.button(QDialogButtonBox.Ok)
        okButton.setText(self.OK)
        cancelButton = self.button_box.button(QDialogButtonBox.Cancel)
        cancelButton.setText(self.CANCEL)
        helpButton = self.helpButton
        helpButton.setText(self.HELP)
        self.BOSscene = QGraphicsScene(self)
        self.BOSGraphicsView.setScene(self.BOSscene)
        self.graphtypeCB.addItem(self.DISPLACEMENT, self.DISPLACEMENT)
        self.graphtypeCB.addItem(self.AVERAGEDISPLACEMENT,
                                 self.AVERAGEDISPLACEMENT)
        self.graphtypeCB.addItem(self.OSCILLATIONS, self.OSCILLATIONS)
        self.graphtypeCB.addItem(self.COMPLETENESS, self.COMPLETENESS)
        self.graphtypeCB.addItem(self.COMBINED, self.COMBINED)
        self.savepdfPB.clicked.connect(self.saveAsPDF)
        self.savesvgPB.clicked.connect(self.saveAsSVG)
        self.savecsvPB.clicked.connect(self.saveAsCSV)
        self.graphtypeCB.currentIndexChanged.connect(self.selectGraphType)
        self.savepdfPB.setEnabled(False)
        self.savesvgPB.setEnabled(False)
        self.savecsvPB.setEnabled(False)
        # Connect signals
        okButton.clicked.connect(self.startWorker)
        helpButton.clicked.connect(self.help)
        self.ringcolour = QColor(153, 153, 255)

    def startWorker(self):
        if Qgis.QGIS_VERSION_INT < 30405:
            self.showError('The plugin requires QGIS 3.4.5 or later '
                           'to run. Your QGIS version is ' +
                           Qgis.QGIS_VERSION +
                           ' - sorry about that!')
            return
        # plugincontext = QgsProcessingContext().copyThreadSafeSettings()
        plugincontext = QgsProcessingContext()
        plugincontext.setProject(QgsProject.instance())
        # self.showInfo("Context: " + str(plugincontext.project().title()))
        """Initialises and starts the worker thread."""
        try:
            layerindex = self.inputLayer.currentIndex()
            layerId = self.inputLayer.itemData(layerindex)
            self.Xlayer = QgsProject.instance().mapLayer(layerId)
            if self.Xlayer is None:
                self.showError(self.tr('No input layer defined'))
                return
            refindex = self.referenceLayer.currentIndex()
            reflayerId = self.referenceLayer.itemData(refindex)
            self.Qlayer = QgsProject.instance().mapLayer(reflayerId)
            # not meaningful for the layers to be identical
            # should the provider be checked for equality?
            if layerId == reflayerId:
                self.showInfo('The reference layer must be different'
                              ' from the input layer!')
                return
            if self.Qlayer is None:
                self.showError(self.tr('No reference layer defined'))
                return
            if (self.Qlayer is not None and
                    self.Qlayer.sourceCrs().isGeographic()):
                self.showWarning('Geographic CRS used for the reference'
                                 ' layer - computations will be in decimal'
                                 ' degrees!')
            steps = self.stepsSB.value()
            startradius = self.startRadiusSB.value()
            endradius = self.endRadiusSB.value()
            radii = []
            self.logarithmic = self.logCheckBox.isChecked()
            if self.logarithmic:
                startl = math.log(startradius)
                endl = math.log(endradius)
                deltal = (endl - startl) / (steps - 1)
                for step in range(steps):
                    radii.append(math.exp(startl + step * deltal))
            else:
                delta = (endradius - startradius) / (steps - 1)
                for step in range(steps):
                    radii.append(startradius + step * delta)

            self.showInfo("Radii: " + str(radii))
            self.selectedinputonly = self.selectedFeaturesCheckBox.isChecked()
            self.selectedrefonly = self.selectedRefFeaturesCheckBox.isChecked()
            plugincontext = dataobjects.createContext()
            # create a new worker instance
            worker = Worker(self.Xlayer, self.Qlayer, plugincontext, radii,
                            self.selectedinputonly, self.selectedrefonly)
            # # configure the QgsMessageBar
            # msgBar = self.iface.messageBar().createMessage(
            #                                    self.tr('Starting'), '')
            # self.aprogressBar = QProgressBar()
            # self.aprogressBar.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            acancelButton = QPushButton()
            acancelButton.setText(self.CANCEL)
            acancelButton.clicked.connect(self.killWorker)
            # msgBar.layout().addWidget(self.aprogressBar)
            # msgBar.layout().addWidget(acancelButton)
            # Has to be popped after the thread has finished (in
            # workerFinished).
            # self.iface.messageBar().pushWidget(msgBar,
            #                                   Qgis.Info)
            # self.messageBar = msgBar
            # self.showInfo('GUI thread: ' + str(QThread.currentThread()) +
            #               ' ID: ' + str(QThread.currentThreadId()))
            # start the worker in a new thread
            thread = QThread(self)
            worker.moveToThread(thread)
            worker.finished.connect(self.workerFinished)
            worker.error.connect(self.workerError)
            worker.status.connect(self.workerInfo)
            worker.progress.connect(self.progressBar.setValue)
            worker.algprogress.connect(self.algProgressBar.setValue)
            worker.phase.connect(self.setPhase)
            # worker.progress.connect(self.aprogressBar.setValue)
            thread.started.connect(worker.run)
            thread.start()
            self.thread = thread
            self.worker = worker
            self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)
            self.button_box.button(QDialogButtonBox.Close).setEnabled(False)
            self.button_box.button(QDialogButtonBox.Cancel).setEnabled(True)
            self.savepdfPB.setEnabled(False)
            self.savesvgPB.setEnabled(False)
            self.savecsvPB.setEnabled(False)
        except Exception:
            import traceback
            self.showError(traceback.format_exc())
        else:
            pass
        # End of startworker

    def workerFinished(self, ok, ret):
        """Handles the output from the worker and cleans up after the
           worker has finished."""
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(True)
        self.button_box.button(QDialogButtonBox.Close).setEnabled(True)
        self.button_box.button(QDialogButtonBox.Cancel).setEnabled(False)
        # clean up the worker and thread
        self.worker.deleteLater()
        self.thread.quit()
        self.thread.wait()
        self.thread.deleteLater()
        # # remove widget from message bar (pop)
        # self.iface.messageBar().popWidget(self.messageBar)
        self.progressBar.setValue(0.0)
        self.algProgressBar.setValue(0.0)
        self.algProgressLabel.setText("")
        # self.showInfo("showinfo - ret: " + str(ret))
        if ok and ret is not None:
            # report the result
            self.results = ret
            self.showInfo('BOS finished, results: ' + str(self.results))
            # QgsMessageLog.logMessage(self.tr('BOS finished'),
            #                          self.BOS, Qgis.Info)
        else:
            self.results = None
            # notify the user that something went wrong
            if not ok:
                self.showError(self.tr('Aborted') + '!')
            else:
                self.showError(self.tr('No sensible statistics') + '!')
            return
        self.savepdfPB.setEnabled(True)
        self.savesvgPB.setEnabled(True)
        self.savecsvPB.setEnabled(True)

        # Do the plotting
        # self.showInfo("Try to plot - " + str(ok) + " ret: " + str (ret))
        if ok and ret is not None:
            self.showPlotsmpl()
    # End of workerFinished

    # Benytter matplotlib til grafene.
    def showPlotsmpl(self):
        if mpl.__version__ < '2.0':
            self.showWarning(self.tr('Matplotlib version 2 or higher is'
                             'required for plotting!'))
            return
        defaultmpldpi = 100
        # self.showInfo("Showplots matplotlib")
        radii = self.results[0][1:]
        # self.showInfo("radii: " + str(radii))
        compl = self.results[5][1:]
        # self.showInfo("compl: " + str(compl))
        misc = self.results[6][1:]
        # self.showInfo("misc: " + str(misc))
        avgdisp = self.results[7][1:]
        # self.showInfo("avgdisp: " + str(avgdisp))
        oscillations = self.results[8][1:]
        # self.showInfo("oscillations: " + str(oscillations))
        outiinr = []
        iniinr = []
        inioutr = []
        outioutr = []  # not used
        for i in range(1, 5):
            if self.results[i][0] == 'I':
                inioutr = self.results[i][1:]
                # self.showInfo("I: " + str(inioutr))
            elif self.results[i][0] == 'IR':
                iniinr = self.results[i][1:]
                # self.showInfo("IR: " + str(iniinr))
            elif self.results[i][0] == 'R':
                outiinr = self.results[i][1:]
                # self.showInfo("R: " + str(outiinr))
            elif self.results[i][0] == 'O':
                outioutr = self.results[i][1:]
                # self.showInfo("R: " + str(outioutr))
            else:
                self.showError("Strange statistics type: " +
                               str(self.results[i][0]))
        graphtype = self.graphtypeCB.itemData(self.graphtypeCB.currentIndex())

        maxdispval = 0  # For storing the largest value
        maxavgdispval = 0  # For storing the largest avgdisp value
        maxsize = 0  # For storing the largest buffer size
        sizes = []
        normoiirsizes = []
        normiiirsizes = []
        normiiorsizes = []
        sums = []
        for i in range(len(radii)):
            size = float(radii[i])
            sizes.append(size)
            oiir = outiinr[i]
            iiir = iniinr[i]
            iior = inioutr[i]
            sum = oiir + iiir + iior
            normoiirsizes.append(oiir / sum)
            normiiirsizes.append(iiir / sum)
            normiiorsizes.append(iior / sum)
            # self.showInfo("OIIR: " + str(oiir) + " IIIR: " +
            #               str(iiir) + " IIOR: " + str(iior))
            if maxdispval < oiir:
                maxdispval = oiir
            if maxdispval < iiir:
                maxdispval = iiir
            if maxdispval < iior:
                maxdispval = iior
            if maxsize < size:
                maxsize = size
            # Calcultate the average displacement
            avgdisp[i] = math.pi * size * oiir / (oiir + iiir + iior)
            if avgdisp[i] > maxavgdispval:
                maxavgdispval = avgdisp[i]
        # self.showInfo("Maxval (Displacement): " + str(maxdispval) +
        #               " Maxsize: " + str(maxsize) + " Steps: " +
        #               str(len(sizes)))

        # Matplotlib (qwt does not seem to be available in standard installs)
        self.BOSscene.clear()
        viewprect = QRectF(self.BOSGraphicsView.viewport().rect())
        self.BOSGraphicsView.setSceneRect(viewprect)
        bottom = self.BOSGraphicsView.sceneRect().bottom()
        top = self.BOSGraphicsView.sceneRect().top()
        left = self.BOSGraphicsView.sceneRect().left()
        right = self.BOSGraphicsView.sceneRect().right()
        height = bottom - top
        width = right - left
        # Find the size of the plot area in inches
        self.plotsizex = width / defaultmpldpi
        self.plotsizey = height / defaultmpldpi
        self.BOSscene.clear()
        # figure = Figure(figsize=(5, 3), dpi=300)
        self.figure = Figure(figsize=(self.plotsizex, self.plotsizey))
        static_canvas = FigureCanvas(self.figure)
        # Create a group of subplot containing only one plot area
        axisscale = 1.02
        if graphtype == self.COMPLETENESS:
            static_ax = static_canvas.figure.subplots()
            # Crash: 'Figure' object has no attribute 'subplots'
            # (requires matplotlib version 2.?)
            static_ax.set_title('BOS - Completeness / Miscodings')
            static_ax.set_xlabel('Buffer size')
            static_ax.set_xlim([0, max(radii) * axisscale])
            static_ax.set_ylim([0, 100])
            static_ax.set_yticks([i * 10 for i in range(11)])
            # Add (0, 0)
            static_ax.plot([0] + radii,
                           [0] + [percent * 100 for percent in compl],
                           ".-", color='black', fillstyle='none',
                           label="Completeness of X relative to Q",
                           linewidth=0.2)
            # Add (0, 100)
            static_ax.plot([0] + radii,
                           [100] + [percent * 100 for percent in misc],
                           "+-", color='black', fillstyle='none',
                           label="Miscodings in X relative to Q",
                           linewidth=0.2)
            # vals = static_ax.get_yticks()
            static_ax.grid(which='both')
            fmt = '%.0f%%'
            yticks = ticker.FormatStrFormatter(fmt)
            static_ax.yaxis.set_major_formatter(yticks)
            static_ax.legend()
        elif graphtype == self.DISPLACEMENT:
            # Calculate the total length of the lines in the X data set
            inplength = 0
            if self.selectedinputonly:
                for f in self.Xlayer.getSelectedFeatures():
                    inplength = inplength + f.geometry().length()
            else:
                for f in self.Xlayer.getFeatures():
                    inplength = inplength + f.geometry().length()
            # Calculate the total length of the lines in the Q data set
            reflength = 0
            if self.selectedrefonly:
                for f in self.Qlayer.getSelectedFeatures():
                    reflength = reflength + f.geometry().length()
            else:
                for f in self.Qlayer.getFeatures():
                    reflength = reflength + f.geometry().length()
            static_ax = static_canvas.figure.subplots()
            static_ax.set_title('BOS - Displacement information')
            static_ax.set_xlabel('Buffer size')
            static_ax.set_xlim([0, max(radii) * axisscale])
            static_ax.set_ylim([0, 100])
            static_ax.set_yticks([i * 10 for i in range(11)])
            # Add data points for 0
            static_ax.plot([0] + radii,
                           [0] + [percent * 100 for percent in normiiirsizes],
                           ".-", color='black', fillstyle='none',
                           label="Inside X and inside Q",
                           linewidth=0.5)
            static_ax.plot([0] + radii,
                           [100 * inplength / (inplength + reflength)] +
                           [percent * 100 for percent in normiiorsizes],
                           "+-", color='black', fillstyle='none',
                           label="Inside X and Outside Q",
                           linewidth=0.5)
            static_ax.plot([0] + radii,
                           [100 * reflength / (inplength + reflength)] +
                           [percent * 100 for percent in normoiirsizes],
                           "s-", color='black', fillstyle='none',
                           label="Outside X and Inside Q",
                           linewidth=0.5)
            # vals = static_ax.get_yticks()
            static_ax.grid(which='both')
            fmt = '%.0f%%'
            yticks = ticker.FormatStrFormatter(fmt)
            static_ax.yaxis.set_major_formatter(yticks)
            static_ax.legend()
        elif graphtype == self.AVERAGEDISPLACEMENT:
            static_ax = static_canvas.figure.subplots()
            static_ax.set_title('BOS - Average displacement information')
            static_ax.set_xlabel('Buffer size')
            static_ax.set_xlim([0, max(radii) * axisscale])
            static_ax.set_ylim([0, max(avgdisp) * axisscale])
            static_ax.set_ylabel('Map units')
            # Add (0, 0)
            static_ax.plot([0] + radii, [0] + avgdisp, ".-",
                           color='black', fillstyle='none',
                           label="Average displacement of Q relative to X",
                           linewidth=0.5)
            static_ax.grid(which='both')
            # vals = static_ax.get_yticks()
            # fmt = '%.0f%%'
            # yticks = ticker.FormatStrFormatter(fmt)
            # static_ax.yaxis.set_major_formatter(yticks)
            static_ax.legend()
        elif graphtype == self.OSCILLATIONS:
            static_ax = static_canvas.figure.subplots()
            static_ax.set_title('BOS - Oscillations')
            static_ax.set_xlabel('Buffer size')
            static_ax.set_xlim([0, max(radii) * axisscale])
            static_ax.set_ylim([0, max(oscillations) * axisscale])
            static_ax.set_ylabel('#polygons/1k map units')
            static_ax.plot(radii, oscillations, ".-", color='black',
                           fillstyle='none',
                           label="Number of polygons / 1k length units"
                                 "  in the combined data set",
                           linewidth=0.5)
            static_ax.grid(which='both')
            static_ax.legend()
        elif graphtype == self.COMBINED:
            # Calculate the total length of the lines in the X data set
            inplength = 0
            if self.selectedinputonly:
                for f in self.Xlayer.getSelectedFeatures():
                    inplength = inplength + f.geometry().length()
            else:
                for f in self.Xlayer.getFeatures():
                    inplength = inplength + f.geometry().length()
            # Calculate the total length of the lines in the Q data set
            reflength = 0
            if self.selectedrefonly:
                for f in self.Qlayer.getSelectedFeatures():
                    reflength = reflength + f.geometry().length()
            else:
                for f in self.Qlayer.getFeatures():
                    reflength = reflength + f.geometry().length()
            tsize = 12
            labsize = 10
            legsize = 8
            ticsize = 8
            static_ax = static_canvas.figure.subplots(2, 2)
            # static_ax[1][0].rcParams.update({'font.size': 4})
            static_ax[1][0].set_title('BOS - Oscillation', fontsize=tsize)
            static_ax[1][0].set_xlabel('Buffer size', fontsize=labsize)
            static_ax[1][0].set_ylabel('#polygons/1k u', fontsize=labsize)
            static_ax[1][0].set_xlim([0, max(radii) * axisscale])
            static_ax[1][0].set_ylim([0, max(oscillations) * axisscale])
            static_ax[1][0].xaxis.set_tick_params(labelsize=ticsize)
            static_ax[1][0].yaxis.set_tick_params(labelsize=ticsize)
            static_ax[1][0].plot(radii, oscillations, ".-", color='black',
                                 fillstyle='none',
                                 label="#Polygons",
                                 linewidth=0.5,
                                 markersize=5)
            static_ax[1][0].grid(which='both')
            static_ax[1][0].legend(fontsize=legsize)

            static_ax[0][1].set_title('BOS - Avg displ', fontsize=tsize)
            static_ax[0][1].set_xlabel('Buffer size', fontsize=labsize)
            static_ax[0][1].set_ylabel('Map units', fontsize=labsize)
            static_ax[0][1].set_xlim([0, max(radii) * axisscale])
            static_ax[0][1].set_ylim([0, max(avgdisp) * axisscale])
            static_ax[0][1].xaxis.set_tick_params(labelsize=ticsize)
            static_ax[0][1].yaxis.set_tick_params(labelsize=ticsize)
            # Add a data point for 0
            static_ax[0][1].plot([0] + radii, [0] + avgdisp, ".-",
                                 color='black', fillstyle='none',
                                 label="Avg displ",
                                 linewidth=0.5,
                                 markersize=5)
            static_ax[0][1].grid(which='both')
            static_ax[0][1].legend(fontsize=legsize)

            static_ax[0][0].set_title('BOS - Displacement', fontsize=tsize)
            static_ax[0][0].set_xlabel('Buffer size', fontsize=tsize)
            static_ax[0][0].set_xlim([0, max(radii) * axisscale])
            static_ax[0][0].set_ylim([0, 100])
            # static_ax[0][0].set_yticks([i * 10 for i in range(11)])
            static_ax[0][0].xaxis.set_tick_params(labelsize=ticsize)
            static_ax[0][0].yaxis.set_tick_params(labelsize=ticsize)
            # Add data points for 0
            static_ax[0][0].plot([0] + radii,
                                 [0] + [percent * 100 for percent in
                                 normiiirsizes],
                                 ".-", color='black', fillstyle='none',
                                 label="IX & IQ",
                                 linewidth=0.5,
                                 markersize=5)
            static_ax[0][0].plot([0] + radii,
                                 [100 * inplength / (inplength + reflength)] +
                                 [percent * 100 for percent in normiiorsizes],
                                 "+-", color='black', fillstyle='none',
                                 label="IX & OQ",
                                 linewidth=0.5,
                                 markersize=5)
            static_ax[0][0].plot([0] + radii,
                                 [100 * reflength / (inplength + reflength)] +
                                 [percent * 100 for percent in normoiirsizes],
                                 "s-", color='black', fillstyle='none',
                                 label="OX & IQ",
                                 linewidth=0.5,
                                 markersize=5)
            # vals = static_ax[0][0].get_yticks()
            static_ax[0][0].grid(which='both')
            fmt = '%.0f%%'
            yticks = ticker.FormatStrFormatter(fmt)
            static_ax[0][0].yaxis.set_major_formatter(yticks)
            static_ax[0][0].legend(fontsize=legsize)

            static_ax[1][1].set_title('BOS - Compl/Misc', fontsize=tsize)
            static_ax[1][1].set_xlabel('Buffer size', fontsize=tsize)
            static_ax[1][1].set_xlim([0, max(radii) * axisscale])
            static_ax[1][1].set_ylim([0, 100])
            # static_ax[1][1].set_yticks([i * 10 for i in range(11)])
            static_ax[1][1].xaxis.set_tick_params(labelsize=ticsize)
            static_ax[1][1].yaxis.set_tick_params(labelsize=ticsize)
            # Add data points for 0
            static_ax[1][1].plot([0] + radii,
                                 [0] + [percent * 100 for percent in compl],
                                 ".-", color='black', fillstyle='none',
                                 label="Completeness",
                                 linewidth=0.5,
                                 markersize=5)
            static_ax[1][1].plot([0] + radii,
                                 [100] + [percent * 100 for percent in misc],
                                 "+-", color='black', fillstyle='none',
                                 label="Miscodings",
                                 linewidth=0.5,
                                 markersize=5)
            # vals = static_ax[1][1].get_yticks()
            static_ax[1][1].grid(which='both')
            fmt = '%.0f%%'
            yticks = ticker.FormatStrFormatter(fmt)
            static_ax[1][1].yaxis.set_major_formatter(yticks)
            static_ax[1][1].legend(fontsize=legsize)
        else:
            self.showWarning("unsupported graphtype: " + str(graphtype))
            return
        # static_ax.set_yticklabels(['{}{}'.format(int(x),'%') for x in vals])
        self.figure.tight_layout(pad=0.5)
        self.plott = static_canvas
        self.BOSscene.addWidget(static_canvas)
        return
    # end showPlotsmpl

    # Select the type of graph (when the user makes a choice)
    def selectGraphType(self, index):
        if self.results is not None:
            self.showPlotsmpl()
    # end selectGraphType

    # Save to PDF
    def saveAsPDF(self):
        settings = QSettings()
        key = '/UI/lastShapefileDir'
        outDir = settings.value(key)
        filter = 'PDF (*.pdf)'
        # Two elements are returned (not documented in the pyqt5 docs
        savename, _filter = QFileDialog.getSaveFileName(self, "Save File",
                                                        outDir, filter)
        # Check if empty (cancelled)
        # if savename.isEmpty():
        if savename == '':
            return
        savename = unicode(savename)
        if savename:
            outDir = os.path.dirname(savename)
            settings.setValue(key, outDir)
        currsize = self.figure.get_size_inches()
        # self.showInfo("Current size: " + str(currsize))
        self.figure.set_size_inches(self.widthmmDSB.value() / 25.4,
                                    self.heightmmDSB.value() / 25.4)
        self.figure.tight_layout(pad=0.5)
        graphtype = self.graphtypeCB.itemData(self.graphtypeCB.currentIndex())
        plottitle = ''
        if graphtype == self.COMPLETENESS:
            plottitle = 'BOS - Completeness / Miscodings'
        elif graphtype == self.DISPLACEMENT:
            plottitle = 'BOS - Displacement information'
        elif graphtype == self.AVERAGEDISPLACEMENT:
            plottitle = 'BOS - Average displacement information'
        elif graphtype == self.OSCILLATIONS:
            plottitle = 'BOS - Oscillations'
        elif graphtype == self.COMBINED:
            plottitle = 'BOS - Combined plot'
        try:
            self.figure.savefig(savename, dpi=300, format='pdf',
                                metadata={'Creator': 'BOS QGIS Plugin',
                                          'Author': 'H Tveite, NMBU',
                                          'Title': plottitle})
        except Exception:
            import traceback
            self.showError(traceback.format_exc())
        return
    # End of Save to PDF

    # Save to SVG
    def saveAsSVG(self):
        settings = QSettings()
        key = '/UI/lastShapefileDir'
        outDir = settings.value(key)
        filter = 'SVG (*.svg)'
        # Two elements are returned (not documented in the pyqt5 docs
        savename, _filter = QFileDialog.getSaveFileName(self, "Save to SVG",
                                                        outDir, filter)
        # Check if empty (cancelled)
        # if savename.isEmpty():
        if savename == '':
            return
        savename = unicode(savename)
        if savename:
            outDir = os.path.dirname(savename)
            settings.setValue(key, outDir)
        currsize = self.figure.get_size_inches()
        self.figure.set_size_inches(self.widthmmDSB.value() / 25.4,
                                    self.heightmmDSB.value() / 25.4)
        self.figure.tight_layout(pad=0.5)
        graphtype = self.graphtypeCB.itemData(self.graphtypeCB.currentIndex())
        plottitle = ''
        if graphtype == self.COMPLETENESS:
            plottitle = 'BOS - Completeness / Miscodings'
        elif graphtype == self.DISPLACEMENT:
            plottitle = 'BOS - Displacement information'
        elif graphtype == self.AVERAGEDISPLACEMENT:
            plottitle = 'BOS - Average displacement information'
        elif graphtype == self.OSCILLATIONS:
            plottitle = 'BOS - Oscillations'
        elif graphtype == self.COMBINED:
            plottitle = 'BOS - Combined plot'
        try:
            self.figure.savefig(savename, dpi=300, format='svg',
                                metadata={'Creator': 'BOS QGIS Plugin',
                                          'Author': 'H Tveite, NMBU',
                                          'Title': plottitle})
        except Exception:
            import traceback
            self.showError(traceback.format_exc())
        return
    # End Save to SVG

    # Save to CSV
    def saveAsCSV(self):
        if self.results is None:
            return
        settings = QSettings()
        key = '/UI/lastShapefileDir'
        outDir = settings.value(key)
        filter = 'CSV (*.csv)'
        savename, _filter = QFileDialog.getSaveFileName(self, "Save File",
                                                        outDir, filter)
        # Check if empty (cancelled)
        # if savename.isEmpty():
        if savename == "":
            return
        savename = unicode(savename)
        if savename[-4:] != ".csv":
            savename = savename + ".csv"
        if savename:
            outDir = os.path.dirname(savename)
            settings.setValue(key, outDir)
        self.showInfo("savename: " + str(savename))
        try:
            with open(savename, 'w') as csvfile:
                csvwriter = csv.writer(csvfile, delimiter=';',
                                       quotechar='"',
                                       quoting=csv.QUOTE_MINIMAL)
                colnames = [item[0] for item in self.results]
                csvwriter.writerow(colnames)
                for i in range(len(self.results[0]) - 1):
                    therow = [item[i + 1] for item in self.results]
                    csvwriter.writerow(therow)
            with open(savename + 't', 'w') as csvtfile:
                therow = '"String"' + ', "Real"' * 10
                csvtfile.write(therow)
        except IOError as e:
                    self.showInfo("Trouble writing the CSV file: " + str(e))
    # End of saveascsv

    def setPhase(self, phase):
        # self.showInfo("Phase changed to: " + str(phase))
        self.algProgressLabel.setText(phase + ":")

    def help(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(
                         self.plugin_dir + "/help/html/index.html"))
        # showPluginHelp(None, "help/html/index")

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
        # self.iface.messageBar().pushMessage(self.tr('Error'), text,
        #                                     level=Qgis.Critical,
        #                                     duration=3)
        QgsMessageLog.logMessage('Error: ' + text, self.BOS,
                                 Qgis.Critical)

    def showWarning(self, text):
        """Show info."""
        # self.iface.messageBar().pushMessage(self.tr('Info'), text,
        #                                     level=Qgis.Warning,
        #                                     duration=2)
        QgsMessageLog.logMessage('Info: ' + text, self.BOS,
                                 Qgis.Warning)

    def showInfo(self, text):
        """Show info."""
        # self.iface.messageBar().pushMessage(self.tr('Info'), text,
        #                                     level=Qgis.Info,
        #                                     duration=2)
        QgsMessageLog.logMessage('Info: ' + text, self.BOS,
                                 Qgis.Info)

    # Overriding
    def resizeEvent(self, event):
        if self.results is None:
            return
        else:
            self.showPlotsmpl()

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
