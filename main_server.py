#!/Python3.4
from bluetooth import *
from select import *
import irnet_bluetooth_server as irnet
import re
import argparse

import sys, os, struct, array
from time import *
from fcntl import ioctl
import select
import threading

from can2RNET import *

help_msg = '''i-rnet chair server. This server acts as the main controller for
           the i-rnet phone app. '''

parser = argparse.ArgumentParser(description=help_msg)
parser.add_argument("--test", help="Test mode for bluetooth apps", action="store_true")
args = parser.parse_args()

joyX = 0
joyY = 0

STX = 2
ETX = 3

can_active = False


def dec2hex(dec, hexlen):  # convert dec to hex with leading 0s and no '0x'
    h = hex(int(dec))[2:]
    l = len(h)
    if h[l - 1] == "L":
        l -= 1  # strip the 'L' that python int sticks on
    if h[l - 2] == "x":
        h = '0' + hex(int(dec))[1:]
    return ('0' * hexlen + h)[l:l + hexlen]


def valid_dataframe(raw_data):
    global STX
    global ETX

    if len(raw_data) < 2:
        return False

    first_byte = int(raw_data[0])
    second_byte = int(raw_data[len(raw_data) - 1])

    if (raw_data[0] == STX) and (raw_data[len(raw_data) - 1] == ETX):
        # print ("True")
        return True

    return False


def read_move_dataframe(raw_data):

    global joyX
    global joyY

    #print(str(len(data)))

    # <STX  "Joy_X + 200"  "Joy_Y + 200"  ETX>
    # STX stands for an 0x02 byte
    # ETX is the byte 0x03

    # the "Joy_X + 200" stands for an integer value in ASCII,
    # so e.g. 300 is the bytes "300" (0x33 0x30 0x30)
    joyX = (raw_data[1] - 48) * 100 + \
            (raw_data[2] - 48) * 10 + (raw_data[3] - 48)
    joyY = (raw_data[4] - 48) * 100 + \
            (raw_data[5] - 48) * 10 + (raw_data[6] - 48)

    # all the values are exactly 3 decimal digits so that its
    # unambiguous (thats why 200 is added)

    # we need to subtract 200 afterwards...
    joyX = joyX - 200
    joyY = joyY - 200

    # this maps (-100 to 100) to be
    # (1, (128 center, but in our case 0 is center), 255)
    # as defined in Linux gamepad kernel api
    joyX = 0x100 + int(joyX * 255) >> 8 & 0xFF
    joyY = 0x100 - int(joyY * 255) >> 8 & 0xFF

    if joyX == 1:
        joyX = 0
    if joyY == 1:
        joyY = 0

def read_button_dataframe(raw_data, can_socket):

    button = chr(raw_data[1])
    print(button)

    if button == 'A': # on
        print("horn")
        cansend(can_socket,"0C040101#")
        cansend(can_socket,"0C040100#")
    if button == 'B': # off
        cansend(can_socket,"0C040101#")
        cansend(can_socket,"0C040100#")

    # Button 2 (Flood lights)
    if button == 'E':
        cansend(can_socket, "0C000404#")
    if button == 'F':
        cansend(can_socket, "0C000404#")

    # Button 3 (Left Blinker)
    if button == 'C':
        cansend(can_socket, "0C000401#")
    if button == 'D':
        cansend(can_socket, "0C000401#")

    # Button 5 (Right Blinker)
    if button == 'I':
        cansend(can_socket, "0C000402#")
    if button == 'J':
        cansend(can_socket, "0C000402#")

def read_bluetooth_data(bluetooth_chair_sock, can_socket=''):

    if bluetooth_chair_sock == None:
        print("Unexpected bluetooth socket error")

    global rnet_threads_running


    try:
        while True:
            data = bluetooth_chair_sock.recv(1024)
            data_len = len(data)

            # print("received [%s]" % data)
            if valid_dataframe(data) == False:
                print ("Bad dataframe")
                continue

            if data_len == 8:
                read_move_dataframe(data)
            elif data_len == 3:
                if can_socket != '':
                    read_button_dataframe(data, can_socket)
            else:
                continue

    except Exception as e:
        print("I/O error({0}): {1}".format(e.errno, e.strerror))
        kill_rnet_threads()
        joyX = 0
        joyY = 0

        pass


def main():

    global rnet_threads_running
    rnet_threads_running = True

    global joyX
    global joyY
    joyX = 0
    joyY = 0

    # create irnet server
    bluetooth_main_server = irnet.IrnetBluetoothServer()
    bluetooth_chair_sock, bluetooth_chair_sock_info = bluetooth_main_server.run_bluetooth_setup()

    can_socket = opencansocket(0)

    if can_socket == '':
        bluetooth_chair_sock.close()
        kill_rnet_threads()
        print ("No can device found!")
        return
    
    #print(bluetooth_chair_sock_info, can_socket)

    if bluetooth_chair_sock is None:
          bluetooth_chair_sock.close()
          kill_rnet_threads()
          print("Found no bluetooth device")
          return

    bluetooth_joystick_thread = threading.Thread(target=read_bluetooth_data, args=(bluetooth_chair_sock, can_socket), daemon=True)
    bluetooth_joystick_thread.start()

    while True:
        chair_mode(bluetooth_chair_sock, bluetooth_chair_sock_info, can_socket)
        rnet_threads_running = False
        print("Waiting 5 seconds before restarting canbus activity")
        sleep(5)
        rnet_threads_running = True


def chair_mode(bluetooth_chair_sock, bluetooth_chair_sock_info, can_socket):
    joy_id = RNET_JSMerror_exploit(can_socket)
    play_song_thread = threading.Thread(target=RNETplaysong,args=(can_socket,),daemon = True)

    speed_range = 00
    send_joyframe_thread = threading.Thread(target=send_joystick_canframe,args=(can_socket,joy_id,),daemon=True)
    send_joyframe_thread.start()

    play_song_thread.start()

    watch_and_wait(can_socket)

    #kill_rnet_threads()

    #bluetooth_chair_sock.close()


def send_joystick_canframe(s, joy_id):
    mintime = .01
    nexttime = time() + mintime
    priorjoyx = joyX
    priorjoyy = joyY

    while rnet_threads_running:
        joyframe = joy_id + '#' + dec2hex(joyX, 2) + dec2hex(joyY, 2)
        #print (joyframe) #DEBUG only
        cansend(s, joyframe)
        nexttime += mintime
        t = time()

        if t < nexttime:
            sleep(nexttime - t)
        else:
            nexttime += mintime


def wait_joystickframe(cansocket, t):
    frameid = ''
    # just look for joystick frame ID (no extended frame)
    while frameid[0:3] != '020' and rnet_threads_running:
        cf, addr = cansocket.recvfrom(16)
        candump_frame = dissect_frame(cf)
        frameid = candump_frame.split('#')[0]
        if t > time():
             print("JoyFrame wait timed out ")
             return('02000100')
    return(frameid)


def induce_JSM_error(can_socket):
    for i in range(0, 3):
        cansend(can_socket, '0c000000#')


def RNET_JSMerror_exploit(can_socket):
    print("Waiting for JSM heartbeat")
    canwait(can_socket, "03C30F0F:1FFFFFFF")

    t = time() + 0.20
    print("Waiting for joy frame")
    joy_id = wait_joystickframe(can_socket, t)

    print("Using joy frame: " + joy_id)
    induce_JSM_error(can_socket)

    print("3 x 0c000000# sent")

    return(joy_id)


def RNETsetSpeedRange(can_socket, speed_range):
    if speed_range >= 0 and speed_range <= 0x64:
        cansend(can_socket,'0a040100#'+dec2hex(speed_range,2))
    else:
        print('Invalid RNET SpeedRange: ' + str(speed_range))

def RNETshortBeep(can_socket):
    cansend(can_socket,"181c0100#0260000000000000")

def RNETplaysong(can_socket):
    cansend(can_socket,"181C0100#2056080010560858")
    sleep(.77)
    cansend(can_socket,"181C0100#105a205b00000000")

def read_can(s, read_can_endtime):
    global can_active
    while (time()<read_can_endtime) and rnet_threads_running:
         canwait(s, "03C30F0F:1FFFFFFF")
         can_active = True
    

def watch_and_wait(s):

    global joyX
    global joyY
    global can_active
    watchdoginterval = 1.0
    while rnet_threads_running:
        can_active = False
        read_can_endtime = time() + watchdoginterval
        read_canTH = threading.Thread(target=read_can,args=(s,read_can_endtime,),daemon=True)
        read_canTH.start()
        sleep(watchdoginterval)
        if can_active == False:
            print("No activity seen on canbus")
            kill_rnet_threads()
        print('In Hex: X: '+ dec2hex(joyX, 2) +'\tY: ' + dec2hex(joyY, 2))

        print('In Dec: X: '+ str(joyX) +'\tY: ' + str(joyY) + '\tThreads: '+str(threading.active_count()))

def kill_rnet_threads():
    global rnet_threads_running
    rnet_threads_running = False

    # device address check
    # if re.match("[0-9a-f]{2}([-:])[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", args.addr.lower()):

    # else:
    #    print("You provided a bad bluetooth address: {0} \n".format(args.addr))
    #    parser.print_help()


main()
