# -*- coding: utf-8 -*-
"""
/***************************************************************************
 BOS
                                 A QGIS plugin
 Implements the BOS method for assessing the accuracy of geographical lines
                             -------------------
        begin                : 2018-12-18
        copyright            : (C) 2018 by Håvard Tveite
        email                : havard.tveite@nmbu.no
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load BOS class from file bos.py.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .bos import BOS
    return BOS(iface)
