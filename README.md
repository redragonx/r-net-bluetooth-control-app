sudo apt-get update
sudo apt-get install python-pip python-dev ipython

sudo apt-get install bluetooth libbluetooth-dev
sudo pip install pybluez


#sudo hciconfig hci0 up   #enables bt on computer
#hcitool scan  # gets UUID of devices in pairing mode
#hcitool dev # get BT adapter uuid

bluetoothctl -a  #starts interactive prompt
scan on          #scans for UUID of device (BT and BLE) in pairing mode
pair uuid        # where "uuid" is what you found with scan
trust uuid

https://raspberrypi.stackexchange.com/questions/41776/failed-to-connect-to-sdp-server-on-ffffff000000-no-such-file-or-directory


https://stackoverflow.com/questions/18657427/ioexception-read-failed-socket-might-closed-bluetooth-on-android-4-3
