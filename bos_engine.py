# -*- coding: utf-8 -*-
"""
/***************************************************************************
 bos_engine
                          bosEngine of the BOS plugin
 Line accuracy and completeness statistics
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

import collections
import math  # to get pi
# from qgis.core import QgsMessageLog
from qgis.core import QgsField  # Adding new fields to tables
# from qgis.core import QgsApplication   # ok
# from processing.tools import dataobjects
# from time import sleep
# from qgis.core import QgsProcessingOutputLayerDefinition
# from qgis.core import QgsProcessingUtils
# from qgis.core import QgsProcessingContext  # thread manipulation?
# QGIS 3
from qgis.core import QgsFeatureRequest
from qgis.PyQt import QtCore   # QObject and pyqtSignal()
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import QgsProcessingFeedback
# from qgis.PyQt.QtCore import QThread

import processing  # run()


class Worker(QtCore.QObject):
    '''The worker that does the heavy lifting.
    /* QGIS offers spatial indexes to make spatial search more
     *
    */
    '''
    # Define the signals used to communicate back to the application
    progress = QtCore.pyqtSignal(float)  # For reporting progress
    algprogress = QtCore.pyqtSignal(float)  # For reporting algorithm progress
    phase = QtCore.pyqtSignal(str)  # For reporting phase
    status = QtCore.pyqtSignal(str)      # For reporting status
    error = QtCore.pyqtSignal(str)       # For reporting errors
    # Signal for sending over the result:
    finished = QtCore.pyqtSignal(bool, object)

    def __init__(self, inputvectorlayer, refvectorlayer,
                 pluginctx,
                 radii=[10, 20],
                 selectedinputonly=True,
                 selectedrefonly=True,
                 logarithmic=False):
        """Initialise.

        Arguments:
        inputvectorlayer -- (QgsVectorLayer) The base vector layer
                            for the join
        refvectorlayer -- (QgsVectorLayer) the ref layer
        outputlayername -- (string) the name of the output memory
                           layer
        pluginctx -- plugin context
        radii -- list of radii (doubles)
        selectedinputonly -- flag (default True)
        selectedrefonly -- flag (default True)
        """

        QtCore.QObject.__init__(self)  # Essential!
        # Creating instance variables from the parameters
        self.inputvl = inputvectorlayer
        self.Xvl = None
        self.referencevl = refvectorlayer
        self.Qvl = None
        self.plugincontext = pluginctx   # Not used
        self.radii = radii
        self.selectedinonly = selectedinputonly
        self.selectedjoonly = selectedrefonly
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
        # Some constants
        self.XFLAG = 'I'
        self.QFLAG = 'R'
        self.OUTSIDEFLAG = 'O'

    def run(self):
        # Create a dictionary for the area statistics
        areastatistics = collections.OrderedDict()
        # areastatistics = {}
        # Create a dictionary for the count of polygons
        polycount = collections.OrderedDict()
        # polycount = {}
        # Create a dictionary for the completeness
        completeness = collections.OrderedDict()
        # completeness = {}
        # Create a dictionary for the miscodings
        miscodings = collections.OrderedDict()
        # miscodings = {}
        # Create a dictionary for the oscillation
        oscillations = collections.OrderedDict()
        # oscillations = {}
        fb = QgsProcessingFeedback()
        fb.progressChanged.connect(self.alg_progress_changed)
        #processing.run(...., feedback=fb)
        # Testing threads
        try:
            # Check if the layers look OK
            if self.inputvl is None or self.referencevl is None:
                self.status.emit('Missing layer(s)!')
                self.finished.emit(False, None)
                return
            # Check if only selected features should be used
            if self.selectedinonly:
                self.Xvl = self.inputvl.materialize(
                    QgsFeatureRequest().setFilterFids(
                       self.inputvl.selectedFeatureIds()))
            else:
                self.Xvl = self.inputvl
            if self.selectedjoonly:
                self.Qvl = self.referencevl.materialize(
                    QgsFeatureRequest().setFilterFids(
                        self.referencevl.selectedFeatureIds()))
            else:
                self.Qvl = self.referencevl

            # Check if there are features in the layers, and abort if not
            incount = self.Xvl.featureCount()
            refcount = self.Qvl.featureCount()
            if incount == 0 or refcount == 0:
                self.status.emit('Layer without features!')
                self.finished.emit(False, None)
                return

            # Calculate the total length of lines - abort if 0
            inpgeomlength = 0
            for f in self.Xvl.getFeatures():
                inpgeomlength = inpgeomlength + f.geometry().length()
            if inpgeomlength == 0:
                self.status.emit('Total line length of input layer is 0!')
                self.finished.emit(False, None)
                return
            refgeomlength = 0
            for f in self.Qvl.getFeatures():
                refgeomlength = refgeomlength + f.geometry().length()
            if refgeomlength == 0:
                self.status.emit('Total line length of reference layer is 0!')
                self.finished.emit(False, None)
                return
            # Retrieve the features of the input layer
            feats = self.Xvl.getFeatures()
            # Check if for multi-geometry (not used!)
            self.inputmulti = False
            if feats is not None:
                # Get the first feature
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
            self.status.emit('Starting BOS engine')

            # Find the intersection of the bounding boxes of the
            # input and reference layer and buffer to get a polygon
            # that will cover all buffers for both datasets
            # extenttolayer returns a layer with one polygon containing
            # the bounding box with one attribute - "id" (with the value
            # of 1).
            self.phase.emit('prep')
            inpext = processing.run("native:extenttolayer",
                                    {'INPUT': self.Xvl,
                                     'OUTPUT': 'memory:'},
                                    context=self.plugincontext,
                                    is_child_algorithm=True)
            inpextlayer = self.plugincontext.temporaryLayerStore().mapLayer(inpext['OUTPUT'])
            refext = processing.run("native:extenttolayer",
                                    {'INPUT': self.Qvl,
                                     'OUTPUT': 'memory:'},
                                    context=self.plugincontext,
                                    is_child_algorithm=True)
            refextlayer = self.plugincontext.temporaryLayerStore().mapLayer(refext['OUTPUT'])
            commonext = processing.run("qgis:intersection",
                                    {'INPUT': inpextlayer,
                                     'OVERLAY': refextlayer,
                                     'OUTPUT': 'memory:'},
                                    context=self.plugincontext,
                                    is_child_algorithm=True)
                                    # {'INPUT': inpext['OUTPUT'],
                                    # 'OVERLAY': refext['OUTPUT'],
            commonextlayer = self.plugincontext.temporaryLayerStore().mapLayer(commonext['OUTPUT'])
            commonextbuf = processing.run("native:buffer",
                                    {'INPUT': commonextlayer,
                                     'DISTANCE': 1.1 *
                                     self.radii[len(self.radii) - 1],
                                     'OUTPUT': 'memory:'},
                                    context=self.plugincontext,
                                    is_child_algorithm=True)
                                    # {'INPUT': commonext['OUTPUT'],
            commonextbuflayer = self.plugincontext.temporaryLayerStore().mapLayer(commonextbuf['OUTPUT'])

            # Do the BOS!
            self.step_count = len(self.radii)
            # The number of steps that is needed to increment the
            # progressbar - set early in run()
            self.increment = self.step_count // 1000
            # Go through all the steps and collect statistics for each step
            for radius in self.radii:
                # self.status.emit('Radius ' + str(radius))

                # Buffer the input and reference layers and add attributes
                # that identify them
                # First, the input buffer:
                # outputldf = QgsProcessingOutputLayerDefinition('memory:')
                bufferparams = {'INPUT': self.Xvl,
                                'DISTANCE': radius,
                                'SEGMENTS': 5,
                                'END_CAP_STYLE': 0,
                                'JOIN_STYLE': 0,
                                'MITER_LIMIT': 1,
                                'DISSOLVE': True,
                                # 'OUTPUT': outputldf}
                                'OUTPUT': 'memory:'}
                self.phase.emit('inpb (1/8)')
                inpbuff = processing.run("native:buffer", bufferparams,
                                         context=self.plugincontext,
                                         feedback=fb,
                                         is_child_algorithm=True)
                inpblayer = self.plugincontext.temporaryLayerStore().mapLayer(inpbuff['OUTPUT'])

                #            context=None, feedback=None)
                #            context=mycontext, onFinish=None, feedback=None)
                # inpblayer=QgsProcessingUtils.mapLayerFromString(inpbuff['OUTPUT'])
                #inpblayer = inpbuff['OUTPUT']
                #inpblayer  = inpbufflayer
                provider = inpblayer.dataProvider()
                # Remove all attributes (done here in case the input
                # layer is not editable):
                for f in provider.fields():
                    provider.deleteAttributes([0])
                # Add a distinguishing attribute
                provider.addAttributes([QgsField('InputB', QVariant.String)])
                inpblayer.updateFields()
                inpblayer.startEditing()
                # Calculate the total area of the buffer and set
                # the distinguishing attribute:
                inptotarea = 0
                new_field_index = inpblayer.fields().lookupField('InputB')
                for f in provider.getFeatures():
                    inptotarea = inptotarea + f.geometry().area()
                    inpblayer.changeAttributeValue(f.id(),
                                                   new_field_index,
                                                   self.XFLAG)
                inpblayer.commitChanges()

                # Then, the reference buffer:
                # Reuse the parameters from the input layer buffering
                bufferparams['INPUT'] = self.Qvl
                self.phase.emit('refb (2/8)')
                refbuff = processing.run("native:buffer", bufferparams,
                                         context=self.plugincontext,
                                         feedback=fb,
                                         is_child_algorithm=True)
                refblayer = self.plugincontext.temporaryLayerStore().mapLayer(refbuff['OUTPUT'])
                #refblayer = refbuff['OUTPUT']
                provider = refblayer.dataProvider()
                # Remove all attributes (done here in case the input
                # layer is not editable):
                for f in provider.fields():
                    provider.deleteAttributes([0])
                # Add a distinguising attribute
                provider.addAttributes([QgsField('RefB', QVariant.String)])
                refblayer.updateFields()
                refblayer.startEditing()
                # Calculate the total area of the buffer and set
                # the distinguishing attribute:
                reftotarea = 0
                new_field_index = refblayer.fields().lookupField('RefB')
                for f in provider.getFeatures():
                    reftotarea = reftotarea + f.geometry().area()
                    refblayer.changeAttributeValue(f.id(),
                                                   new_field_index, self.QFLAG)
                refblayer.commitChanges()
                # self.status.emit('Buffers finished')


                # Calculate completeness and miscodings using line-polygon
                # overlays and line length measurements
                # First, completeness:
                # Clip the reference lines using the input buffer:
                output = 'memory:'
                clipparams = {
                              'INPUT': self.Qvl,
                              'OVERLAY': inpblayer,
                              'OUTPUT': output
                }
                              # 'INPUT': self.Qvl,
                self.phase.emit('clip (3/8)')
                refclip = processing.run('native:clip', clipparams,
                                         context=self.plugincontext,
                                         feedback=fb,
                                         is_child_algorithm=True)
                refcliplayer = self.plugincontext.temporaryLayerStore().mapLayer(refclip['OUTPUT'])
                #refcliplayer = refclip['OUTPUT']
                provider = refcliplayer.dataProvider()
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
                # self.status.emit('Clip finished')


                # Then, miscodings:
                # The reference buffer is used to remove parts of the
                # input layer
                differenceoutput = 'memory:'
                diffparams = {
                  'INPUT': self.Xvl,
                  'OVERLAY': refblayer,
                  'OUTPUT': differenceoutput
                }
                  # 'OVERLAY': refbuff['OUTPUT'],
                self.phase.emit('diff (4/8)')
                difference = processing.run('native:difference', diffparams,
                                         context=self.plugincontext,
                                         feedback=fb,
                                         is_child_algorithm=True)
                difflayer = self.plugincontext.temporaryLayerStore().mapLayer(difference['OUTPUT'])
                #difference = processing.run('qgis:difference', diffparams)
                #difflayer = difference['OUTPUT']
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
                # self.status.emit('Diff finished')



                #testparams = {
                #  'INPUT': self.Xvl,
                #  'OVERLAY': refbuff['OUTPUT'],
                #  'OUTPUT': "memory:"
                #}
                #test = processing.run('native:union', testparams)
                #testlayer = test['OUTPUT']
                #self.status.emit('Testl, #: ' + str(testlayer.featureCount()))
                #testlayer.selectByExpression("\"RefB\" = self.QFLAG")
                #testvl = testlayer.materialize(
                #    QgsFeatureRequest().setFilterFids(
                #       testlayer.selectedFeatureIds()))
                #self.status.emit('Test, #: ' + str(testvl.featureCount()))




                # Calculate displacement information from the areas of
                # the polygons resulting from an overlay of the two
                # buffer datasets
                unionparameters = {
                                   'INPUT': inpblayer,
                                   'OVERLAY': refblayer,
                                   'OUTPUT': "memory:"
                }
                                   # 'INPUT': inpbuff['OUTPUT'],
                                   # 'OVERLAY': refbuff['OUTPUT'],
                self.phase.emit('union1 (5/8)')
                firstunion = processing.run("native:union", unionparameters,
                                         context=self.plugincontext,
                                         feedback=fb,
                                         is_child_algorithm=True)
                firstunionlayer = self.plugincontext.temporaryLayerStore().mapLayer(firstunion['OUTPUT'])
                # Do union with a "background" layer to be able to
                # identify the polygons that are outside both the
                # input buffer and ref buffer
                unionparameters = {
                                   'INPUT': firstunionlayer,
                                   'OVERLAY': commonextbuflayer,
                                   'OUTPUT': "memory:"}
                                   # 'INPUT': firstunion['OUTPUT'],
                                   # 'OVERLAY': commonextbuf['OUTPUT'],
                self.phase.emit('union2 (6/8)')
                union = processing.run("native:union", unionparameters,
                                         context=self.plugincontext,
                                         feedback=fb,
                                         is_child_algorithm=True)
                unionlayer = self.plugincontext.temporaryLayerStore().mapLayer(union['OUTPUT'])
                # Do a multipart to single parts operation
                self.phase.emit('tosingle (7/8)')
                multitosingle = processing.run("native:multiparttosingleparts",
                                               {
                                                'INPUT': unionlayer,
                                                'OUTPUT': "memory:"},
                                                # 'INPUT': union['OUTPUT'],
                                               context=self.plugincontext,
                                               feedback=fb,
                                               is_child_algorithm=True)
                multitosinglelayer = self.plugincontext.temporaryLayerStore().mapLayer(multitosingle['OUTPUT'])
                # Calculate areas:
                # multitosinglelayer = multitosingle['OUTPUT']
                provider = multitosinglelayer.dataProvider()
                # Create a category field for statistics
                provider.addAttributes([QgsField('Combined', QVariant.String)])
                # Create an area field
                provider.addAttributes([QgsField('Area', QVariant.Double)])
                multitosinglelayer.updateFields()
                multitosinglelayer.startEditing()
                area_field_index = multitosinglelayer.fields().lookupField('Area')
                comb_field_index = multitosinglelayer.fields().lookupField('Combined')
                for f in provider.getFeatures():
                    # Calculate the area and update the area attribute
                    area = f.geometry().area()
                    multitosinglelayer.changeAttributeValue(f.id(), area_field_index,
                                                    area)
                    # Determine and set the combination attribute
                    # If neither inside X or Q, set it to self.OUTSIDEFLAG
                    iidx = multitosinglelayer.fields().lookupField('InputB')
                    ridx = multitosinglelayer.fields().lookupField('RefB')
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
                            comb = self.OUTSIDEFLAG
                    multitosinglelayer.changeAttributeValue(f.id(), comb_field_index,
                                                    comb)
                unionlayer.commitChanges()
                # self.status.emit('Unions finished')


                # Do the area statistics to get the area for the following:
                # I: Inside input buffer, outside reference buffer
                # IR: Inside input buffer, inside reference buffer
                # I: Outside input buffer, inside reference buffer
                # And the number of features for the following
                # O: Outside input buffer, outside reference buffer
                statparams = {
                     # 'INPUT': union['OUTPUT'],
                     'INPUT': multitosinglelayer,
                     # 'INPUT': unionlayer,
                     'VALUES_FIELD_NAME': 'Area',
                     'CATEGORIES_FIELD_NAME': 'Combined',
                     'OUTPUT': 'memory:'
                }
                     # 'INPUT': multitosingle['OUTPUT'],
                self.phase.emit('stat (8/8)')
                stats = processing.run('qgis:statisticsbycategories', statparams,
                                       context=self.plugincontext,
                                       is_child_algorithm=True)
                statlayer = self.plugincontext.temporaryLayerStore().mapLayer(stats['OUTPUT'])
                #statlayer = stats['OUTPUT']
                provider = statlayer.dataProvider()
                # extract from the statistics
                currstats = collections.OrderedDict()
                # currstats = {}
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
                # rec.extend(sorted(areastatistics)) # ??
                # rec.extend(self.radii)  # ???
                result.append(rec)
                # Extract and add the ii, io and oo areas (four rows)
                for thekey in list(areastatistics[
                                    list(areastatistics.keys())[0]].keys()):
                                    # self.radii[0]].keys()):  # ???
                                    # self.radii[0]].keys()):  # ???
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
                #for i in self.radii:  # ???
                    vals = areastatistics[i]
                    # pi() * radius * area inside q and outside i / area
                    # inside i buffer
                    avgdisp = (math.pi * i * vals[self.QFLAG] /
                               (vals[self.XFLAG + self.QFLAG] +
                                vals[self.XFLAG]))
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

    def alg_progress_changed(self, algprogress):
        #self.status.emit("Algprogress: " + str(algprogress))
        self.algprogress.emit(algprogress)

    def kill(self):
        '''Kill the thread by setting the abort flag'''
        self.abort = True

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
