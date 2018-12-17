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

import math
from qgis.core import QgsMessageLog
from qgis.core import QgsField
from qgis.core import QgsProcessingAlgRunnerTask   # ok
from qgis.core import QgsApplication   # ok
from processing.tools import dataobjects
from time import sleep
from qgis.core import QgsProcessingOutputLayerDefinition
from qgis.core import QgsProcessingUtils
from qgis.core import QgsProcessingContext  # thread manipulation?
# QGIS 3
from qgis.PyQt import QtCore
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtCore import QThread

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
            Worker.status.emit(er_msg)

        def setPercentage(self, percent):
            Worker.status.emit(str(percent))

        def setText(self, text):
            Worker.status.emit(text)

        def setCommand(self, comd):
            Worker.status.emit(comd)

    def __init__(self, inputvectorlayer, refvectorlayer,
                 pluginctx,
                 radii=[10, 20],
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
        self.plugincontext = pluginctx
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
        # Number of steps in the process - used by
        # calculate_progress (set when needed)
        self.step_count = 1
        # The number of steps that is needed to increment the
        # progressbar (set when needed)
        self.increment = 0

    def run(self):
        # mycontext knyttes til denne tråden
        # mycontext = QgsProcessingContext()   # Not used currently
        # mycontext = processing.context() # finnes ikke!!!
        # mycontext.pushToThread(QThread.currentThread())
        # self.status.emit('context thread: ' + str(mycontext.thread())
        #                  + ' ID: ' +
        #                  str(mycontext.thread().currentThreadId()))
        # Create a dictionary for the area statistics
        areastatistics = {}
        polycount = {}
        completeness = {}
        miscodings = {}
        oscillations = {}
        # Testing threads
        # self.status.emit('Worker thread: ' + str(QThread.currentThread()) +
        #                  ' ID: ' + str(QThread.currentThreadId()))
        try:
            # Check if the layers look OK
            if self.inpvl is None or self.refvl is None:
                self.status.emit('Layer is missing!')
                self.finished.emit(False, None)
                return
            # Check if there are features in the layers abort if not
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
            # Calculate the total length of lines - abort if 0
            inpgeomlength = 0
            for f in self.inpvl.getFeatures():
                inpgeomlength = inpgeomlength + f.geometry().length()
            if inpgeomlength == 0:
                self.status.emit('Total line length of input layer is 0!')
                self.finished.emit(False, None)
                return
            refgeomlength = 0
            for f in self.refvl.getFeatures():
                refgeomlength = refgeomlength + f.geometry().length()
            if refgeomlength == 0:
                self.status.emit('Total line length of reference layer is 0!')
                self.finished.emit(False, None)
                return

            if self.selectedinonly:
                feats = self.inpvl.getSelectedFeatures()
            else:
                feats = self.inpvl.getFeatures()
            # Check the geometry type (not used!)
            self.inputmulti = False
            if feats is not None:
                testfeature = next(feats)
                feats.rewind()
                feats.close()
                if testfeature is not None:
                    if testfeature.geometry() is not None:
                        if testfeature.geometry().isMultipart():
                            self.inputmulti = True
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

            # Find the intersection of the bounding boxes of the
            # input and reference layer
            # extenttolayer returns a layer with one polygon containing
            # the bounding box with one attribute - "id" with the value
            # of 1.
            inpext = processing.run("native:extenttolayer",
                                    {'INPUT': self.inpvl,
                                     'OUTPUT': 'memory:'})
            refext = processing.run("native:extenttolayer",
                                    {'INPUT': self.refvl,
                                     'OUTPUT': 'memory:'})
            commonext = processing.run("qgis:intersection",
                                    {'INPUT': inpext['OUTPUT'],
                                     'OVERLAY': refext['OUTPUT'],
                                     'OUTPUT': 'memory:'})

            # Do the BOS!
            self.step_count = len(self.radii)
            # The number of steps that is needed to increment the
            # progressbar - set early in run()
            self.increment = self.step_count // 1000

            buffsize = 10.0

            def on_complete(ok, results):
                    if ok:
                        i = 1
                    else:
                        i = 0

            # layer name, distance, segments, dissolve,
            # output /tmp/test -> /tmp/test.shp - use None to return the
            # (memory) layer.
            for radius in self.radii:
                self.status.emit('Radius ' + str(radius))
                # Buffer the input and reference layers and add attributes
                # that identifies them
                # First, the input buffer:
                # outputldf = QgsProcessingOutputLayerDefinition('memory:')

                bufferparams = {'INPUT': self.inpvl,
                                'DISTANCE': radius,
                                'SEGMENTS': 5,
                                'END_CAP_STYLE': 0,
                                'JOIN_STYLE': 0,
                                'MITER_LIMIT': 1,
                                'DISSOLVE': True,
                                # 'OUTPUT': outputldf}
                                'OUTPUT': 'memory:'}
                inpbuff = processing.run("native:buffer", bufferparams)
                #            context=None, feedback=None)
                #            context=mycontext, onFinish=None, feedback=None)
                # Drop all attributes?
                # Add a distinguishing attribute
                # inpblayer=QgsProcessingUtils.mapLayerFromString(inpbuff['OUTPUT'])
                inpblayer = inpbuff['OUTPUT']
                provider = inpblayer.dataProvider()
                # Remove all attributes (done here in case the input
                # layer is not editable):
                for f in provider.fields():
                    provider.deleteAttributes([0])
                # inpblayer.updateFields()
                provider.addAttributes([QgsField('InputB', QVariant.String)])
                inpblayer.updateFields()
                inpblayer.startEditing()
                new_field_index = inpblayer.fields().lookupField('InputB')
                # Calculate the total area of the buffer:
                inptotarea = 0
                # for f in processing.features(inpblayer):
                for f in provider.getFeatures():
                    inptotarea = inptotarea + f.geometry().area()
                    inpblayer.changeAttributeValue(f.id(),
                                                   new_field_index, 'I')
                inpblayer.commitChanges()

                # Reuse the parameters from the input layer buffering
                bufferparams['INPUT'] = self.refvl
                refbuff = processing.run("native:buffer", bufferparams)
                # Drop all attributes?
                # Add a distinguising attribute
                refblayer = refbuff['OUTPUT']
                provider = refblayer.dataProvider()
                # Remove all attributes (done here in case the input
                # layer is not editable):
                for f in provider.fields():
                    provider.deleteAttributes([0])
                provider.addAttributes([QgsField('RefB', QVariant.String)])
                refblayer.updateFields()
                refblayer.startEditing()
                new_field_index = refblayer.fields().lookupField('RefB')
                # Calculate the total area of the buffer:
                reftotarea = 0
                for f in provider.getFeatures():
                    reftotarea = reftotarea + f.geometry().area()
                    refblayer.changeAttributeValue(f.id(),
                                                   new_field_index, 'R')
                refblayer.commitChanges()

                # Calculate completeness and miscodings using line-polygon
                # overlays and line length measurements
                # First, completeness:
                # Line overlay (input buffer + reference lines):
                intersectoutput = 'memory:'
                intersectparams = {
                                   'INPUT': self.refvl,
                                   'OVERLAY': inpbuff['OUTPUT'],
                                   'OUTPUT': intersectoutput
                }
                intersect = processing.run('qgis:intersection',
                                           intersectparams)
                interslayer = intersect['OUTPUT']
                provider = interslayer.dataProvider()
                # Calculate the total length of reference lines inside
                # the input buffer
                reflinelength = 0
                for f in provider.getFeatures():
                    reflinelength = reflinelength + f.geometry().length()
                # Calculate completeness
                if refgeomlength > 0:
                    BOScompleteness = reflinelength / refgeomlength
                else:
                    BOScompleteness = 0
                completeness[radius] = BOScompleteness

                # Then, miscodings:
                # The reference buffer is used to remove parts of the
                # input layer
                differenceoutput = 'memory:'
                diffparams = {
                  'INPUT': self.inpvl,
                  'OVERLAY': refbuff['OUTPUT'],
                  'OUTPUT': differenceoutput
                }
                difference = processing.run('qgis:difference', diffparams)
                difflayer = difference['OUTPUT']
                provider = difflayer.dataProvider()
                # Calculate the total length of input lines outside the
                # reference buffer
                inplinelength = 0
                for f in provider.getFeatures():
                    inplinelength = inplinelength + f.geometry().length()
                # Calculate miscodings
                if inpgeomlength > 0:
                    BOSmiscodings = inplinelength / inpgeomlength
                else:
                    BOSmiscodings = 0
                miscodings[radius] = BOSmiscodings
                unionparameters = {'INPUT': inpbuff['OUTPUT'],
                              'OVERLAY': refbuff['OUTPUT'],
                              'OUTPUT': "memory:"}
                firstunion = processing.run("native:union", unionparameters)

                # Do union with a "background" layer to be able to
                # identify the polygons that are outside both the
                # input buffer and ref buffer
                unionparameters = {'INPUT': firstunion['OUTPUT'],
                                   'OVERLAY': commonext['OUTPUT'],
                                   'OUTPUT': "memory:"}
                union = processing.run("native:union", unionparameters)

                # Do a multipart to single operation
                multitosingle = processing.run("native:multiparttosingleparts",
                                               {'INPUT': union['OUTPUT'],
                                                'OUTPUT': "memory:"})

                # Calculate areas:
                unionlayer = multitosingle['OUTPUT']
                provider = unionlayer.dataProvider()
                # Create a category field for statistics
                provider.addAttributes([QgsField('Combined', QVariant.String)])
                # Create an area field
                provider.addAttributes([QgsField('Area', QVariant.Double)])
                unionlayer.updateFields()
                unionlayer.startEditing()
                area_field_index = unionlayer.fields().lookupField('Area')
                comb_field_index = unionlayer.fields().lookupField('Combined')
                for f in provider.getFeatures():
                    area = f.geometry().area()
                    unionlayer.changeAttributeValue(f.id(), area_field_index,
                                                    area)
                    iidx = unionlayer.fields().lookupField('InputB')
                    ridx = unionlayer.fields().lookupField('RefB')
                    i = f.attributes()[iidx]
                    r = f.attributes()[ridx]
                    comb = ''
                    if i is not None:
                        if r is not None:
                            comb = i + r
                        else:
                            comb = i
                    else:
                        # comb = r
                        if r is not None:
                            comb = r
                        else:
                            comb = 'O'
                    unionlayer.changeAttributeValue(f.id(), comb_field_index,
                                                    comb)
                unionlayer.commitChanges()

                # Do the area statistics to get the area for the following:
                # I: Inside input buffer, outside reference buffer
                # IR: Inside input buffer, inside reference buffer
                # I: Outside input buffer, inside reference buffer
                # And the number of features for the following
                # O: Outside input buffer, outside reference buffer
                params = {
                     # 'INPUT': union['OUTPUT'],
                     'INPUT': multitosingle['OUTPUT'],
                     # 'INPUT': unionlayer,
                     'VALUES_FIELD_NAME': 'Area',
                     'CATEGORIES_FIELD_NAME': 'Combined',
                     'OUTPUT': 'memory:'
                }
                stats = processing.run('qgis:statisticsbycategories', params)
                statlayer = stats['OUTPUT']
                provider = statlayer.dataProvider()
                # extract from the statistics
                currstats = {}
                oscillations[radius] = 0
                # Get the indexes for the relevant fields
                # key:
                combidx = statlayer.fields().lookupField('Combined')
                # sum of areas:
                sumidx = statlayer.fields().lookupField('sum')
                # number of features:
                countidx = statlayer.fields().lookupField('count')
                # Got through the results (four rows, for I, IR, R and O)
                for f in provider.getFeatures():
                    # Area statistics
                    thesum = f.attributes()[sumidx]
                    count = f.attributes()[countidx]
                    first = f.attributes()[combidx]  # I, IR or R
                    currstats[first] = thesum
                    # Oscillation ((#outside both)/(length Inp Lines))
                    if first == "O" and inpgeomlength > 0:
                        oscillations[radius] = 1000 * count / inpgeomlength
                areastatistics[radius] = currstats
                self.calculate_progress()
        except Exception:
            import traceback
            self.error.emit(traceback.format_exc())
            self.finished.emit(False, None)
        else:
            if self.abort:
                self.finished.emit(False, None)
            else:
                self.status.emit('Delivering the statistics...')
                # Prepare the result
                result = []
                # Add the radii (first row)
                rec = ['radius']  # First value is an identifier
                rec.extend(list(areastatistics.keys()))
                result.append(rec)
                # Extract and add the ii, io and oo areas (four rows)
                for thekey in list(areastatistics[
                                    list(areastatistics.keys())[0]].keys()):
                    rec = [thekey]  # First value is an identifier
                    rec.extend([i[thekey] for i in
                        list(areastatistics.values())])
                    result.append(rec)
                # Add completeness (sixth row)
                rec = ['completeness']  # First value is identifier
                rec.extend(list(completeness.values()))
                result.append(rec)
                # Add miscodings (seventh row)
                rec = ['miscodings']  # First value is identifier
                rec.extend(list(miscodings.values()))
                result.append(rec)
                # Add average displacement (eighth row)
                rec = ['average_displacement']
                for i in list(areastatistics.keys()):
                    vals = areastatistics[i]
                    # pi() * radius * area inside q and outside i / area
                    # inside i buffer
                    avgdisp = math.pi * i * vals['R'] / (vals['IR'] +
                                                         vals['I'])
                    rec.extend([avgdisp])
                result.append(rec)
                # Add oscillations (nineth row)
                rec = ['oscillations']  # First value is identifier
                rec.extend(list(oscillations.values()))
                result.append(rec)

                self.finished.emit(True, result)

    def calculate_progress(self):
        '''Update progress and emit a signal with the percentage'''
        self.processed = self.processed + 1
        # update the progress bar at certain increments
        if (self.increment == 0 or
                self.processed % self.increment == 0):
            # Calculate percentage as integer
            perc_new = (100 * self.processed) / self.step_count
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
