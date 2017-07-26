from bluetooth import *
from select import *
NAME_UUID = "00001101-0000-1000-8000-00805F9B34FB"
NAME = "BluetoothChairApp"

class IrnetBluetoothServer():

    def __init__(self):
        # setup bluetooth stuff
        self.server_sock = BluetoothSocket( RFCOMM )
        self.server_sock.setblocking(True)
        try:
            self.server_sock.bind(("", PORT_ANY))

        except IOError:
            print("Cannot bind...")

        self.chair_sock = ""
        self.chair_sock_info = ""

    def run_bluetooth_setup(self):
        print("Waiting for a RFCOMM connection...")
        self.server_sock.listen(1)

        advertise_service(self.server_sock, NAME,
        service_id =  NAME_UUID ,
        service_classes = [ NAME_UUID, SERIAL_PORT_CLASS ] ,
        profiles = [ SERIAL_PORT_PROFILE ])

        while True:

            readable, writable, excepts = select([self.server_sock], [], [], 1)

            if self.server_sock in readable:
                client_sock, client_info = self.server_sock.accept()
                client_sock.setblocking(True)
                self.chair_sock = client_sock
                self.chair_sock_info = client_info

                print ("Accepted connection from ", client_info)

                return self.chair_sock, self.chair_sock_info
