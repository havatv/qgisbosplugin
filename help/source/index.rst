.. BOS documentation master file, created by
   sphinx-quickstart on Sun Feb 12 17:11:03 2012.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to BOS's documentation!
============================================

Contents:

.. toctree::
   :maxdepth: 2

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

Assessing line quality using the BOS method
===========================================

The BOS Plugin compares the geometries of two line layers (the input
and the reference layer) by buffering and overlay for several buffer
sizes, collecting statistics and plotting the results for a visual
assessment of the quality (geometric accuracy, bias, completeness and
miscodings) of the input line data set with respect to the reference
line data set according to the BOS method (:ref:`Tveite and Langaas, 1999 <Tveite, H. and Langaas S., 1999>`).

The BOS method
--------------

The Buffer-Overlay-Statistics (BOS) method works on line data sets
and produces graphs that indicate spatial accuracy, bias,
completeness and miscodings for a line data set of unknown quality
with respect to a data set of better quality.

The core of the method is to build buffers around the lines of the
two data sets using a number of buffer sizes, and then combine the
two buffer data sets and the two line data sets in various ways to
produce statistics that can be plotted to reveal the characteristics
of the input line data set with respect to the reference data set.

The basic elements of the BOS method are illustrated below.

+------------------------------+--------------------+
| The elements of the BOS method                    |
+==============================+====================+
| Two line data sets (X and Q) | Buffer combination |
+------------------------------+--------------------+
| |elements1|                  | |elements2|        |
+------------------------------+--------------------+

  .. |elements1| image:: illustrations/explain1.png
   :height: 200
   :align: middle

  .. |elements2| image:: illustrations/explain2.png
   :height: 200
   :align: middle

For each of the chosen buffer sizes, buffers are created and combined using an overlay operation to produce the polygon layer illustrated in the right part
of the above illustration.

Output
======
Four types of graphs are produced, and the type of graph to be shown
is selected using the `Graph` combo box / menu.
The following graphs are offered:

- *Displacement* - Shows normalised (0%-100%) relative area sums for the
  polygons in the combined buffer data set, grouped according to the
  following combinations *Inside Q and Inside R*, *Inside Q and Outside R*,
  *Outside Q and Inside R*.

  |displacement|

  .. |displacement| image:: illustrations/displacement.png
   :height: 200
   :align: middle

- *Average displacement* - shows the average displacement as a function of
  buffer radius.  Is expected to flatten out when the average displacement
  is equal to the spatial accuracy.

  |avgdisp|

  .. |avgdisp| image:: illustrations/averagedisplacement.png
   :height: 200
   :align: middle

- *Oscillations* - can indicate bias and spatial accuracy.
  If the graph is not steadily decreasing, it can be taken as an
  indication of bias.

  |oscillations|

  .. |oscillations| image:: illustrations/oscillations.png
   :height: 200
   :align: middle


- *Completeness / Miscodings* - shows completeness and miscodings (two
  graphs in the same plot) as a function of buffer radius.

  |completeness|

  .. |completeness| image:: illustrations/completeness.png
   :height: 200
   :align: middle


Options
=======

- The number of steps (buffer sizes)

- The start buffer radius

- The end buffer radius.

If you would like to have 20 buffers with a spacing of 100, you
could specify 100 for the start radius, 2000 for the end radius
and 20 for the number of steps.

Export
======

Exporting graphs as PDF and SVG
-------------------------------

Options:

The width and height of the output graphics can be specified.

- Width in mm

- Height in mm

Exporting the data as CSV
-------------------------
The statistics data can be exported to CSV for further
processing or tailored visualisation.
The first (header) row contains identifiers / names for
the columns.
The exported CSV consists of nine columns, and as many
rows as there are steps (plus the header row).
The CSV-file looks like this (five steps in this example)::

    radius;IR;I;R;O;completeness;miscodings;average_displacement;oscillations
    200.0;28500509.552210856;91345651.61111134;113376990.93457934;6068139105.312706;0.19671702510313907;0.7601548286200464;594.4025546563738;0.1974226191819506
    400.0;106114289.65340048;134189530.21981135;173808986.21196535;5890899886.840816;0.3941682281114015;0.5284117923479394;908.9111184324876;0.11376896698620881
    600.0;207985731.5163426;153389969.1893688;208527378.02795056;5740443047.301017;0.5479680819839098;0.3559997748555806;1087.6903083504928;0.06692292175659341
    800.0;320066918.213234;162997040.60599986;231709138.4748819;5602226235.222582;0.6662973341813202;0.23494762857415086;1205.5310091551798;0.06023062958093407
    1000.0;438372775.45679665;166790573.15283233;247128084.98095602;5472587533.011159;0.7345931607936302;0.17208001554203864;1282.9193606248948;0.04349989914178572

A CSVT file (with the same prefix and a ``csvt`` suffix) specifying
the data types of the columns is also created, with the following
content::

    "String", "Real", "Real", "Real", "Real", "Real", "Real", "Real", "Real", "Real", "Real"
    
Warning
=======

The method involves a lot of computation and will therefore take a very
long time for datasets that are not very small.
The running time will increase with the number of steps.

Implementation
==============

The heavy work is performed in the background using a worker thread.
Most of the computation is performed in the worker thread using QGIS
processing algorithms (buffer, union, intersection, difference,
multipart to singleparts, statistics by categories).

Progress is only reported when a complete step has been finished
(algorithem progress is not forwarded to the user interface).

Versions
===============
The current version is 1.0.0

Citation
==========

Would you like to cite / reference this plugin?

Tveite, H. (2018). The QGIS BOS Plugin.
http://plugins.qgis.org/plugins/BOS/.

Bibtex:

.. code-block:: latex

  @misc{tveitebos,
    author = {Håvard Tveite},
    title = {The {QGIS} BOS Plugin},
    howpublished = {\url{http://plugins.qgis.org/plugins/BOS/}},
    year = {2018}
  }


References
==========

_`Tveite, H. and Langaas S., 1999`. An accuracy assessment method for
geographical line data sets based on buffering.  *International
Journal of Geographical Information Science*, 13, pp. 27-47.



