.. _rpi_setup:

#########
RPI setup
#########

config.txt
**********

Below is a starting point for a /boot/config.txt matching a Raspberry Pi 3 B+. Most importantly is enabling turbo mode to prevent the cpu from changing its frequency dynamically. This will have a negative effect on Twitse time measurements.

Next the RPI's are overclocked. They are not exactly speed kings and they can use a little boost. Common sense would dictate that overclocking must have a positive effect on the Twitse time measurements but this haven't really been verified.

/boot/config.txt::

	# See /boot/overlays/README for all available options
	
	gpu_mem=16
	
	dtparam=i2c1=on            # client only
	dtparam=i2c_arm=on         # client only
	dtparam=spi=on             # client only
	dtoverlay=hifiberry-dac    # client only
	
	force_turbo=1
	arm_freq=1200
	core_freq=500
	sdram_freq=500
	over_voltage=2
	over_voltage_sdram=2
	
	initramfs initramfs-linux.img followkernel



/boot/cmdline.txt



Disable the 'audit' kernel logs:
audit=0

Watch for processes writing to disk:
iotop -o -b -d 10



(This is from an Arch installation)
​

