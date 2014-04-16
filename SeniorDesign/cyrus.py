from twisted.internet import stdio, reactor
from twisted.internet.protocol import Factory, Protocol
from twisted.internet.serialport import SerialPort
from twisted.protocols import basic

serial_client = None
io_client = None

class MainHandler(object):

	def __init__(self):
		self.state = "INIT"

	def processInput(self, line):
		pass
			
	def processSerial(self, line):
		pass

	def processIO(self, line):
		pass

class SerialInterface(basic.LineReceiver):

	def __init__(self):
		global serial_client
		serial_client = self
		self.delimiter = '#!#'

	def connectionMade(self):
		print 'Device: ', self, ' is connected.'
	#	self.sendLine("boot_complete()")

	def cmdReceived(self, cmd):
		self.transport.write(cmd)
		print cmd, ' = sent to device.'
		pass

	def lineReceived(self, line):
		print 'SerialInterface.lineReceived called with:'
		print repr(line)

		# do some sort of processing here to determine
		# the data type/command being received. use this
		# to call the proper MainHandler command
	

class StdioInterface(basic.LineReceiver):

	def __init__(self):
		global io_client
		io_client = self
		self.delimiter = '#!#'

	def connectionMade(self):
		print 'Command line parser: ', self, ' is connected.'

	def lineReceived(self, line):
		global serial_client
		print 'StdioInterface.lineReceived called with:'
		print repr(line)
		serial_client.sendLine(line)


if __name__ == '__main__':
	SerialPort(SerialInterface(), '/dev/ttyAMA0', reactor, baudrate='9600')
	stdio.StandardIO(StdioInterface())
	reactor.run()
