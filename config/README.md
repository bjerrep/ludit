
##Server miscelaneous

    ./modules-load.d/

The files should be copied into /etc/modules-load.d/. Then snd-aloop is loaded which is used for getting audio from a spotifyd daemon, and the card numbers will be fixed (the loopback will be card number 1)

    spotifyd.conf
    
The standard spotifyd configuration defining the aloop loopback as soundcard. Modify it and copy it somewhere appropiate according to the [spotifyd](https://github.com/Spotifyd/spotifyd) instructions.

    write_spotifyd_fifo.sh
 
The ./systemd/ludit_spotifyd.service expects this script to be located here.
    