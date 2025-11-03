#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Oct  4 07:35:09 2023

@author: zdhughes
"""

from PyQt5 import QtCore
from PyQt5.QtNetwork import QUdpSocket, QHostAddress, QNetworkDatagram
import sys
import struct
from scapy.all import ARP, Ether, srp
import time

IP_RANGE = "10.0.10.175/24"
HOST = '10.0.10.175'
PORT = 5000
send_type = 1
colors = True

def get_hex_timestamp():
    timestamp = int(time.time())
    return hex(timestamp)[2:]

class BaseEventLoop(QtCore.QObject):

    # Signals to send to the BEL's threads.

    def __init__(self, HOST, PORT):

        # init superclass and create a text color object.
        super().__init__()

        self.host = QHostAddress(HOST)
        print('Address is broadcast: ', QHostAddress.isBroadcast(self.host))
        self.port = PORT

        self.socket = QUdpSocket()
        
        while True:
            big_send = False  
            n1 = 0
            print(c.yellow('Choose UDP payload:'))
            print(c.yellow('1: 0xc001\t2: 0xc002\t3: 0xc003\t4: 0xc004 (UNIX time)'))
            print(c.yellow('5: 0xc004 (Custom time)\t6: Custom\ts: arp scan\tx: Exit'))
            keystoke = input('Command: ')
            if keystoke == '1':
                c1 = 'c001'
            elif keystoke == '2':
                c1 = 'c002'
            elif keystoke == '3':
                c1 = 'c003'
            elif keystoke == '4':
                hex_timestamp = get_hex_timestamp()
                c1 = 'c004'# + hex_timestamp
                big_send = True  
            elif keystoke == '5':
                hex_timestamp = input('Enter custom GPS time: ')
                c1 = 'c004'# + hex_timestamp
                big_send = True           
            elif keystoke == '6':
                c1 = input('Enter hex int without 0x for payload: ')
            elif keystoke == 's':
                try:
                    arp = ARP(pdst=IP_RANGE)
                    eth = Ether(dst="ff:ff:ff:ff:ff:ff")
                    packet = eth / arp
                    result = srp(packet, timeout=3, verbose=0)[0]
                    print('')
                    for sent, received in result:
                        print(f"IP: {received.psrc} | MAC: {received.hwsrc}", flush=True)
                    print('')
                    continue
                except Exception as e:
                    print(c.red('Failed with error:'))
                    print(e)
                    continue
            elif keystoke == 'x':
                c1 = keystoke
            else:
                continue
            if c1 == 'x':
                print('Exiting...')
                break
            try:
                command = int(c1, 16)
                print('Command was ', c.blue(c1),' (', command, ')', sep='')
            except Exception as e:
                print(c.red('Failed with error:'))
                print(e)
            print('...')
            if big_send == True:
                hex_timestamp = int(hex_timestamp, 16)
                datum = struct.pack('>HI', command, hex_timestamp)
            else:
                datum = struct.pack('>HI', command, 0)
            datagram = QNetworkDatagram()
            datagram.setDestination(self.host, self.port)
            datagram.setHopLimit(255)
            datagram.setData(datum)
            nSent = self.socket.writeDatagram(datagram)
            print('Sent datagram of size: ' + c.orange(str(nSent)) + '\nand contents: ')
            print(c.ORANGE, datum.hex(), c.ENDC)
            print('----------')
        sys.exit()
        
class colors():
	
	"""This class will color console text output using ANSI codes."""

	RED = ''
	ORANGE = ''
	YELLOW = ''
	GREEN = ''
	BLUE = ''
	INDIGO = ''
	VIOLET = ''
	PINK = ''                                                                        
	BLACK = ''
	CYAN = ''
	PURPLE = ''
	BROWN = ''
	GRAY = ''
	DARKGRAY = ''
	LIGHTBLUE = ''
	LIGHTGREEN = ''
	LIGHTCYAN = ''
	LIGHTRED = ''
	LIGHTPURPLE = ''
	WHITE = ''
	BOLD = ''
	UNDERLINE = ''
	ENDC = ''
    
	def enableColors(self):

		self.RED = '\033[0;31m'
		self.ORANGE = '\033[38;5;166m'
		self.YELLOW = '\033[1;33m'
		self.GREEN = '\033[0;32m'
		self.BLUE = '\033[0;34m'
		self.INDIGO = '\033[38;5;53m'
		self.VIOLET = '\033[38;5;163m'
		self.PINK =  '\033[38;5;205m'
		self.BLACK = '\033[0;30m'
		self.CYAN = '\033[0;36m'
		self.PURPLE = '\033[0;35m'
		self.BROWN = '\033[0;33m'
		self.GRAY = '\033[0;37m'
		self.DARKGRAY = '\033[1;30m'
		self.LIGHTBLUE = '\033[1;34m'
		self.LIGHTGREEN = '\033[1;32m'
		self.LIGHTCYAN = '\033[1;36m'
		self.LIGHTRED = '\033[1;31m'
		self.LIGHTPURPLE = '\033[1;35m'
		self.WHITE = '\033[1;37m'
		self.BOLD = '\033[1m'
		self.UNDERLINE = '\033[4m'
		self.ENDC = '\033[0m'

        
	def disableColors(self):
        
		self.RED = ''        
		self.ORANGE = ''
		self.YELLOW = ''
		self.GREEN = ''
		self.BLUE = ''
		self.INDIGO = ''
		self.VIOLET = ''
		self.PINK = ''
		self.BLACK = ''
		self.CYAN = ''
		self.PURPLE = ''
		self.BROWN = ''
		self.GRAY = ''
		self.DARKGRAY = ''
		self.LIGHTBLUE = ''
		self.LIGHTGREEN = ''
		self.LIGHTCYAN = ''
		self.LIGHTRED = ''
		self.LIGHTPURPLE = ''
		self.WHITE = ''
		self.BOLD = ''
		self.UNDERLINE = ''
		self.ENDC = ''

	def getState(self):
		if self.ENDC:
			return True
		elif not self.ENDC:
			return False
		else:
			return -1

	def flipState(self):
		if self.getState():
			self.disableColors()
		elif not self.getState():
			self.enableColors()
		else:
			sys.exit("Can't flip ANSI state, exiting.")

	def confirmColors(self):
		if self.getState() == True:
			print('Colors are '+self.red('e')+self.orange('n')+self.yellow('a')+self.green('b')+self.blue('l')+self.indigo('e')+self.violet('d'))
		elif self.getState() == False:
			print('Colors are off!')
		elif self.getState() == -1:
			print('Error: Can\'t get color state.')

	def confirmColorsDonger(self):
		if self.getState() == True:
			print('Colors are '+self.pink('(ﾉ')+self.lightblue('◕')+self.pink('ヮ')+self.lightblue('◕')+self.pink('ﾉ')+self.red('☆')+self.orange('.')+self.yellow('*')+self.green(':')+self.blue('･ﾟ')+self.indigo('✧')+self.violet(' enabled!'))    
		elif self.getState() == False:
			print('Colors are off!')
		elif self.getState() == -1:
			print('Error: Can\'t get color state.')

	def orange(self, inString):
		inString = str(self.ORANGE+str(inString)+self.ENDC)
		return inString
	def indigo(self, inString):
		inString = str(self.INDIGO+str(inString)+self.ENDC)
		return inString
	def violet(self, inString):
		inString = str(self.VIOLET+str(inString)+self.ENDC)
		return inString
	def pink(self, inString):
		inString = str(self.PINK+str(inString)+self.ENDC)
		return inString
	def black(self, inString):
		inString = str(self.BLACK+str(inString)+self.ENDC)
		return inString
	def blue(self, inString):
		inString = str(self.BLUE+str(inString)+self.ENDC)
		return inString
	def green(self, inString):
		inString = str(self.GREEN+str(inString)+self.ENDC)
		return inString
	def cyan(self, inString):
		inString = str(self.CYAN+str(inString)+self.ENDC)
		return inString
	def red(self, inString):
		inString = str(self.RED+str(inString)+self.ENDC)
		return inString
	def purple(self, inString):
		inString = str(self.PURPLE+str(inString)+self.ENDC)
		return inString
	def brown(self, inString):
		inString = str(self.BROWN+str(inString)+self.ENDC)
		return inString
	def gray(self, inString):
		inString = str(self.GRAY+str(inString)+self.ENDC)
		return inString
	def darkgray(self, inString):
		inString = str(self.DARKGRAY+str(inString)+self.ENDC)
		return inString
	def lightblue(self, inString):
		inString = str(self.LIGHTBLUE+str(inString)+self.ENDC)
		return inString
	def lightgreen(self, inString):
		inString = str(self.LIGHTGREEN+str(inString)+self.ENDC)
		return inString
	def lightcyan(self, inString):
		inString = str(self.LIGHTCYAN+str(inString)+self.ENDC)
		return inString
	def lightred(self, inString):
		inString = str(self.LIGHTRED+str(inString)+self.ENDC)
		return inString
	def yellow(self, inString):
		inString = str(self.YELLOW+str(inString)+self.ENDC)
		return inString
	def white(self, inString):
		inString = str(self.WHITE+str(inString)+self.ENDC)
		return inString
	def bold(self, inString):
		inString = str(self.BOLD+str(inString)+self.ENDC)
		return inString
	def underline(self, inString):
		inString = str(self.UNDERLINE+str(inString)+self.ENDC)
		return inString

if __name__ == '__main__':

    #ROOTIZE
    #cwd = os.getcwd()
    #os.chdir('/root/PADS')
    c = colors()
    c.enableColors()
    c.confirmColorsDonger()
    app = QtCore.QCoreApplication(sys.argv)
    bel = BaseEventLoop(HOST, PORT)
    sys.exit(app.exec_())
    
