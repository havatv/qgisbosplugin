# -*- coding: utf-8 -*-
"""
/***************************************************************************
 bos_engine
                          bosEngine of the BOS plugin
 Line accuracy and completeness statistics
                             -------------------
        begin                : 2017-10-26
        git sha              : $Format:%H$
        copyright            : (C) 2016 by Håvard Tveite
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

import csv

from qgis.core import QgsMessageLog
from qgis.core import QGis
#from qgis.core import QgsWkbTypes
from qgis.core import QgsVectorLayer, QgsFeature, QgsSpatialIndex
from qgis.core import QgsFeatureRequest, QgsField, QgsGeometry
from qgis.core import QgsRectangle, QgsCoordinateTransform

#QGIS 3
#from qgis.PyQt import QtCore
#from qgis.PyQt.QtCore import QCoreApplication, QVariant

#QGIS 2
from PyQt4 import QtCore
from PyQt4.QtCore import QCoreApplication, QVariant

import processing

class Worker(QtCore.QObject):
    '''The worker that does the heavy lifting.
    /* QGIS offers spatial indexes to make spatial search more
     *
    */
    '''
    # Define the signals used to communicate back to the application
    progress = QtCore.pyqtSignal(float)  # For reporting progress
    status = QtCore.pyqtSignal(str)      # For reporting status
    error = QtCore.pyqtSignal(str)       # For reporting errors
    # Signal for sending over the result:
    finished = QtCore.pyqtSignal(bool, object)

    class DummyProgress(object):
      def __init__(self):
        pass

      def error(self, er_msg):
        #print er_msg
        Worker.status.emit(er_msg)

      def setPercentage(self, percent):
        #print str(percent)
        Worker.status.emit(str(percent))

      def setText(self, text):
        #print text
        Worker.status.emit(text)

      def setCommand(self, comd):
        #print comd
        Worker.status.emit(comd)


    def __init__(self, inputvectorlayer, refvectorlayer,
                 #outputlayername, refprefix,
                 #distancefieldname="distance",
                 #approximateinputgeom=False,
                 #usereflayerapproximation=False,
                 #usereflayerindex=True,
                 radii=[10,20],
                 selectedinputonly=True,
                 selectedrefonly=True):
        """Initialise.

        Arguments:
        inputvectorlayer -- (QgsVectorLayer) The base vector layer
                            for the join
        refvectorlayer -- (QgsVectorLayer) the ref layer
        outputlayername -- (string) the name of the output memory
                           layer
        radii
        """

        QtCore.QObject.__init__(self)  # Essential!
        # Creating instance variables from the parameters
        self.inpvl = inputvectorlayer
        self.refvl = refvectorlayer
        self.selectedinonly = selectedinputonly
        self.selectedjoonly = selectedrefonly
        self.radii = radii
        # Creating instance variables for the progress bar ++
        # Number of elements that have been processed - updated by
        # calculate_progress
        self.processed = 0
        # Current percentage of progress - updated by
        # calculate_progress
        self.percentage = 0
        # Flag set by kill(), checked in the loop
        self.abort = False
        # Number of features in the input layer - used by
        # calculate_progress (set when needed)
        self.feature_count = 1
        # The number of elements that is needed to increment the
        # progressbar (set when needed)
        self.increment = 0

    def run(self):
        # Create a vector for the statistics
        statistics = []
        try:
            # Check if the layers look OK
            if self.inpvl is None or self.refvl is None:
                self.status.emit('Layer is missing!')
                self.finished.emit(False, None)
                return
            # Check if there are features in the layers
            incount = 0
            if self.selectedinonly:
                incount = self.inpvl.selectedFeatureCount()
            else:
                incount = self.inpvl.featureCount()
            refcount = 0
            if self.selectedjoonly:
                refcount = self.refvl.selectedFeatureCount()
            else:
                refcount = self.refvl.featureCount()
            if incount == 0 or refcount == 0:
                self.status.emit('Layer without features!')
                self.finished.emit(False, None)
                return
            # Check the geometry type and prepare the output layer
            geometryType = self.inpvl.geometryType()
            #geometrytypetext = 'Point'
            if geometryType == QGis.Point:
                self.status.emit('Point layer!')
                self.finished.emit(False, None)
                return
            elif geometryType == QGis.Line:
                geometrytypetext = 'LineString'
            elif geometryType == QGis.Polygon:
                self.status.emit('Polygon layer!')
                self.finished.emit(False, None)
                return
            # Does the input vector contain multi-geometries?
            # Try to check the first feature
            # This is not used for anything yet
            self.inputmulti = False
            if self.selectedinonly:
                feats = self.inpvl.selectedFeaturesIterator()
            else:
                feats = self.inpvl.getFeatures()
            if feats is not None:
                testfeature = next(feats)
                feats.rewind()
                feats.close()
                if testfeature is not None:
                    if testfeature.geometry() is not None:
                        if testfeature.geometry().isMultipart():
                            self.inputmulti = True
                            geometrytypetext = 'Multi' + geometrytypetext
                        else:
                            pass
                    else:
                        self.status.emit('No geometry!')
                        self.finished.emit(False, None)
                        return
                else:
                    self.status.emit('No input features!')
                    self.finished.emit(False, None)
                    return
            else:
                self.status.emit('getFeatures returns None for input layer!')
                self.finished.emit(False, None)
                return
            

            self.status.emit('Starting BOS')
            #crstext = "PROJ4:"+str(self.inpvl.crs().toProj4())
            # If the authid is valid (EPSG), use it.
            #if "EPSG" in str(self.inpvl.crs().authid()):
            #    crstext = self.inpvl.crs().authid()
            #if self.inpvl.crs() is not None:
            #    geomttext = (geomttext + "?crs=" +
            #                  crstext)
            # Do the BOS!
            # Number of features in the input layer - used by
            # calculate_progress
            #if self.selectedinonly:
            #    self.feature_count = self.inpvl.selectedFeatureCount()
            #else:
            #    self.feature_count = self.inpvl.featureCount()
            self.feature_count = len(self.radii)
            # The number of elements that is needed to increment the
            # progressbar - set early in run()
            self.increment = self.feature_count // 1000
            #self.calculate_progress()

            buffsize = 10.0

            # layer name, distance, segments, dissolve, 
            # output /tmp/test -> /tmp/test.shp - use None to return the (memory) layer.
            for radius in self.radii:
                #self.status.emit('Radius ' + str(radius))
                self.status.emit('Buffer (input) ' + str(radius))
                
                inpbuff = processing.runalg("qgis:fixeddistancebuffer",
                                        self.inpvl, radius, 10, True,
                                        None, progress=None)
                self.status.emit('Buffer (input) ' + str(radius) + " finished - " + str(inpbuff['OUTPUT']))
                # Drop all attributes?
                # Add a distinguishing attribute
                inpblayer=processing.getObject(inpbuff['OUTPUT'])
                provider=inpblayer.dataProvider()
                provider.addAttributes([QgsField('InputB', QVariant.String)])
                inpblayer.updateFields()
                self.status.emit('Attribute added for input ' + str(radius))

                inpblayer.startEditing()
                new_field_index = inpblayer.fieldNameIndex('InputB')
                for f in processing.features(inpblayer):
                    inpblayer.changeAttributeValue(f.id(), new_field_index, 'I')
                inpblayer.commitChanges()
                self.status.emit('Attribute set for input ' + str(radius))

            #myprogress = self.DummyProgress()
            #def setPercentage(self, percent):
            #    self.status.emit(str(percent))
            #myprogress.setPercentage = setPercentage
            #def setText(self, text):
            #    self.status.emit(str(text))
            #myprogress.setText = setText
            #def error(self, er_msg):
            #    self.status.emit(str(er_msg))
            #myprogress.error = error
            #def setCommand(self, comd):
            #    self.status.emit(str(comd))
            #myprogress.setCommand = setCommand

            #myprogress = type("MyProgress", (object,),
            #  { "setPercentage": lambda percent: self.status.emit(str(percent)),
            #    "setText": lambda text: self.status.emit(text),
            #    "error": lambda er_msg: self.status.emit(er_msg),
            #    "setCommand": lambda comd: self.status.emit(comd)
            #  })
            #inpbuff = processing.runalg("qgis:fixeddistancebuffer",
            #                            self.inpvl, 10, 10, True, None, progress=myprogress)
                #self.status.emit('Input buffer created')
                self.status.emit('Buffer (ref) ' + str(radius))
                refbuff = processing.runalg("qgis:fixeddistancebuffer", self.refvl, radius, 10, True, None, progress=None)
                self.status.emit('Buffer (ref) ' + str(radius) + ' created - ' + str(refbuff['OUTPUT']))

                # Drop all attributes?
                # Add a distinguishing attribute
                refblayer=processing.getObject(refbuff['OUTPUT'])
                provider=refblayer.dataProvider()
                provider.addAttributes([QgsField('RefB', QVariant.String)])
                refblayer.updateFields()
                self.status.emit('Attribute added for ref ' + str(radius))
                refblayer.startEditing()
                new_field_index = refblayer.fieldNameIndex('RefB')
                for f in processing.features(refblayer):
                    refblayer.changeAttributeValue(f.id(), new_field_index, 'R')
                refblayer.commitChanges()
                self.status.emit('Attributes set for ref ' + str(radius))

                #self.status.emit('Reference buffer created')
                union = processing.runalg("qgis:union", inpbuff['OUTPUT'], refbuff['OUTPUT'], None, progress=None)
                self.status.emit('Union finished ' + str(radius))
		#continue
                #self.status.emit('Union finished')

                # Calculate areas:
                # Create a category field for statistics
                unionlayer=processing.getObject(union['OUTPUT'])
                provider=unionlayer.dataProvider()
                provider.addAttributes([QgsField('Area', QVariant.Double)])
                provider.addAttributes([QgsField('Combined', QVariant.String)])
                unionlayer.updateFields()
                unionlayer.startEditing()
                area_field_index = unionlayer.fieldNameIndex('Area')
                combined_field_index = unionlayer.fieldNameIndex('Combined')
                self.status.emit('Preparing union layer ' + str(radius))
                for f in processing.features(unionlayer):
                    area = f.geometry().area()
                    unionlayer.changeAttributeValue(f.id(), area_field_index, area)
                    iidx = unionlayer.fieldNameIndex('InputB')
                    ridx = unionlayer.fieldNameIndex('RefB')
                    i = f.attributes()[iidx]
                    r = f.attributes()[ridx]
                    comb = ''
                    if i is not None:
                      if r is not None:
                        comb = str(i) + str(r)
                      else:
                        comb = str(i)
                    else:
                      if r is not None:
                        comb = str(r)
                      else:
                        comb = None
                    unionlayer.changeAttributeValue(f.id(), combined_field_index, comb)
                unionlayer.commitChanges()
                self.status.emit('Preparing union layer ' + str(radius) + ' finished')

                self.status.emit('Doing statistics ' + str(radius))
                # Do the statistics
                stats = processing.runalg('qgis:statisticsbycategories',
                                          union['OUTPUT'], 'Area', 'Combined',
                                          None, progress=None)
                self.status.emit('Statistics done ' + str(radius))
		continue

                currstats = {}
                with open(stats['OUTPUT'], 'rb') as csvfile:
                  spamreader = csv.DictReader(csvfile)
                  for row in spamreader:
                    currstats[row['category']] = row['sum']

                # stats['OUTPUT'] is the location of the CSV file containing the result
                #statistics.append([radius, stats['OUTPUT']])
                statistics.append([radius, currstats])
                self.status.emit('Statistics added ' + str(radius))
		continue
                self.calculate_progress()
            


            #self.status.emit('Worker finished')
        except:
            import traceback
            self.error.emit(traceback.format_exc())
            self.finished.emit(False, None)
            #if self.mem_refl is not None:
            #    self.mem_refl.rollBack()
        else:
            #self.mem_refl.commitChanges()
            if self.abort:
                self.finished.emit(False, None)
            else:
                self.status.emit('Delivering the results...')
                #self.finished.emit(True, self.mem_refl)
                #self.finished.emit(True, None)
                self.finished.emit(True, statistics)


    def calculate_progress(self):
        '''Update progress and emit a signal with the percentage'''
        self.processed = self.processed + 1
        # update the progress bar at certain increments
        if (self.increment == 0 or
                self.processed % self.increment == 0):
            # Calculate percentage as integer
            perc_new = (self.processed * 100) / self.feature_count
            if perc_new > self.percentage:
                self.percentage = perc_new
                self.progress.emit(self.percentage)

    def kill(self):
        '''Kill the thread by setting the abort flag'''
        self.abort = True

    def do_indexjoin(self, feat):
        '''Find the nearest neigbour using an index, if possible

        Parameter: feat -- The feature for which a neighbour is
                           sought
        '''
        infeature = feat

    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('BOSEngine', message)






