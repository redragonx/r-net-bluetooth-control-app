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


joyX = 0
joyY = 0

def dec2hex(dec, hexlen):  # convert dec to hex with leading 0s and no '0x'
    h = hex(int(dec))[2:]
    l = len(h)
    if h[l - 1] == "L":
        l -= 1  # strip the 'L' that python int sticks on
    if h[l - 2] == "x":
        h = '0' + hex(int(dec))[1:]
    return ('0' * hexlen + h)[l:l + hexlen]


def read_bluetooth_joystick(bluetooth_chair_sock):

    global joyX
    global joyY

    if bluetooth_chair_sock == None:
        print("wtf")

    try:
        while True:
            data = bluetooth_chair_sock.recv(1024)
            if len(data) == 0:
                break

            # print("received [%s]" % data)

            # <STX  "Joy_X + 200"  "Joy_Y + 200"  ETX>
            # STX stands for an 0x02 byte
            # ETX is the byte 0x03

            # the "Joy_X + 200" stands for an integer value in ASCII,
            # so e.g. 300 is the bytes "300" (0x33 0x30 0x30)
            joyX = (data[1] - 48) * 100 + \
                    (data[2] - 48) * 10 + (data[3] - 48)
            joyY = (data[4] - 48) * 100 + \
                    (data[5] - 48) * 10 + (data[6] - 48)

            # all the values are exactly 3 decimal digits so that its
            # unambiguous (thats why 200 is added)

            # we need to subtract 200 afterwards...
            joyX = joyX - 200
            joyY = joyY - 200

            # this maps (-100 to 100) to be (1, (128 center), 255)
            # as defined in Linux gamepad kernel api
            joyX = 0x100 + int(joyX * 100) >> 8 & 0xFF
            joyY = 0x100 - int(joyY * 100) >> 8 & 0xFF

            if joyX == 1:
                joyX = 0
            if joyY == 1:
                joyY = 0

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

    parser = argparse.ArgumentParser(description=help_msg)
    parser.add_argument("bt", action="store", type=str)
    args = parser.parse_args()

    print (args.bt)

    if args.bt.lower() == "test":
        bt_test(bluetooth_chair_sock, bluetooth_chair_sock_info)
    else:
        chair_mode(bluetooth_chair_sock, bluetooth_chair_sock_info)


def bt_test(bluetooth_chair_sock, bluetooth_chair_sock_info):
    print(bluetooth_chair_sock_info)

    if bluetooth_chair_sock is None:
        bluetooth_chair_sock.close()
        print("Found no bluetooth device")

    bluetooth_joystick_thread = threading.Thread(target=read_bluetooth_joystick, args=(bluetooth_chair_sock, ), daemon=True)
    bluetooth_joystick_thread.start()

    watch_and_wait()

    bluetooth_chair_sock.close()
    print("all done")


def chair_mode(bluetooth_chair_sock, bluetooth_chair_sock_info):
    # open can socket
    can_socket = opencansocket(0)

    if can_socket == '':
        bluetooth_chair_sock.close()
        kill_rnet_threads()
        print ("No can device found!")
    else:
        print(bluetooth_chair_sock_info, can_socket)

        if bluetooth_chair_sock is None:
                bluetooth_chair_sock.close()
                kill_rnet_threads()
                print("Found no bluetooth device")

        bluetooth_joystick_thread = threading.Thread(target=read_bluetooth_joystick, args=(bluetooth_chair_sock, ), daemon=True)
        bluetooth_joystick_thread.start()

        joy_id = RNET_JSMerror_exploit(can_socket)

        play_song_thread = threading.Thread(target=RNETplaysong,args=(can_socket,),daemon = True)

        speed_range = 00
        #RNETsetSpeedRange(can_socket,speed_range)

        sendjoyframethread = threading.Thread(target=send_joystick_canframe,args=(can_socket,joy_id,),daemon=True)
        sendjoyframethread.start()
        play_song_thread.start()

        watch_and_wait()

    print("disconnected")

    kill_rnet_threads()

    bluetooth_chair_sock.close()
    print("all done")


def send_joystick_canframe(s, joy_id):
    mintime = .01
    nexttime = time() + mintime
    priorjoyx = joyX
    priorjoyy = joyY

    while rnet_threads_running:
        joyframe = joy_id + '#' + dec2hex(joyX, 2) + dec2hex(joyY, 2)
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
    while frameid[0:3] != '020':
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

def watch_and_wait():

    global joyX
    global joyY

    while threading.active_count() > 0:
        sleep(0.5)
        print('X: '+ str(joyX) +'\tY: ' + str(joyY) + '\tThreads: '+str(threading.active_count()))

def kill_rnet_threads():
    global rnet_threads_running
    rnet_threads_running = False

    # device address check
    # if re.match("[0-9a-f]{2}([-:])[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", args.addr.lower()):

    # else:
    #    print("You provided a bad bluetooth address: {0} \n".format(args.addr))
    #    parser.print_help()


main()
