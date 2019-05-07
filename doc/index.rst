
Ludit
=====

.. toctree::
   :maxdepth: 2
   :titlesonly:
   :caption: Contents:

   quick_start
   system_overview
   software_installations
   client_types
   server_audio_source_setup
   rpi_setup

Introduction
============

Ludit is an audioplayer made for an wireless audio system using `Twitse <https://github.com/bjerrep/twitse/>`_ for time synchronisation. Twitse is standalone client/server applications for keeping track of time and it couldn't care less about Ludit or anybody else for that matter. Ludit on the other hand relies on a running Twitse to keep the various computers in time sync since Ludit does not know how to correct audio with regard to crystal drift.

Ludit is intended to get the best out of size constained loudspeakers in everyday setups. It is not too concerned about hifi but happily allows a heavy dose of electronic bass lift to get smaller loudspeakers play an acceptable bass on e.g. 3" or 4" bass drivers in closed 5 litres enclosures. The price to pay is that Ludit speakers in such a setup are not really suited for playing insanely loud since the bass lift burns away quite some power used to battle the small enclosure without giving a equivivalent high sound pressure. But its nice to get the bass drum back. Obviously Ludit can just as well play through speakers that need no bass lift at all.

The following image shows a speaker made for the kitchen. It is very much in Ludits dna to play on two way systems where an electronic crossover can use right and left channel for tweeter an woofer. The carrier board underneath the raspberry pi is part of the twitse project.

.. image:: ../artwork/kitchen_speaker.jpg
    :alt: kitchen_speaker.jpg
    :width: 300px
    



