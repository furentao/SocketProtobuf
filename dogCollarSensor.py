import socket
import threading
import sys
import message_pb2
import struct
import time

from myconfig import BUFFSIZE
from myconfig import TIMEOUT
from myconfig import MULTICAST_GROUP_IP
from myconfig import MULTICAST_GROUP_PORT

# MARK: Classes definitions
# ********************************** MulticastReceiver **********************************
class MulticastReceiver(object):
    # MARK: Constructor
    def __init__(self, ip, port, ip_group):
        self.ip = ip
        self.port = port
        self.ip_group = ip_group

        try:
            self.serverSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # [Errno 98] Address already in use
            # the SO_REUSEADDR flag tells the kernel to reuse a local socket in TIME_WAIT state, 
            # without waiting for its natural timeout to expire.
            self.serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except socket.error as e:
            print("Failed to create socket: %s"%(e))
            sys.exit()

        try:
            # Bind to the server address
            self.serverSocket.bind((self.ip, self.port))
            # Server's up
            print("Lamp Sensor Multicast Server is up and ready to receive connections in UDP MODE! IP '%s' and PORT '%s'"%(self.ip, self.port))
        except socket.error as e:
            print("Failed to bind: %s"%(e))
            sys.exit()

        # Tell the operating system to add the socket to the multicast group
        # on all interfaces.
        group = socket.inet_aton(ip_group)
        mreq = struct.pack('4sL', group, socket.INADDR_ANY)
        self.serverSocket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    # MARK: Methods
    def waitForServerFinderSignal(self):
        threading.Thread(target = self.handleMulticastUDPMessages).start()

    def handleMulticastUDPMessages(self):
        while True:
            # Get server's message
            messageFromServer, serverAddress = self.serverSocket.recvfrom(BUFFSIZE)
            if messageFromServer:
                print("MESSAGE FROM IP %s: %s"%(serverAddress[0], parseSerializedStringIntoMessageObj(messageFromServer)))

                # Handle the message according to received signal and send a response to server
                stayInTouch, response = handleMessageAndGetResponse(messageFromServer)

                # Reply server
                self.serverSocket.sendto(response, serverAddress)
# ********************************** MulticastReceiver **********************************

# ********************************** ThreadedServer **********************************
class ThreadedServer(object):
    # MARK: Constructor
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port

        try:
            self.serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # [Errno 98] Address already in use
            # the SO_REUSEADDR flag tells the kernel to reuse a local socket in TIME_WAIT state, 
            # without waiting for its natural timeout to expire.
            self.serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except socket.error as e:
            print("Failed to create socket: %s"%(e))
            sys.exit()

        try:
            self.serverSocket.bind((self.ip, self.port))
            # Server's up
            print("Lamp Sensor is up and ready to receive connections in TCP MODE! IP '%s' and PORT '%s'"%(self.ip, self.port))
        except socket.error as e:
            print("Failed to bind: %s"%(e))
            sys.exit()

    # MARK: Methods
    def startTCPServer(self):
        # Listen for connections made to the socket. The backlog argument specifies the maximum number of 
        # queued connections and should be at least 0; the maximum value is system-dependent (usually 5), 
        # the minimum value is forced to 0.
        self.serverSocket.listen(5)

        while True:
            # Wait until a client connects
            clientConnection, clientAddress = self.serverSocket.accept()
            clientConnection.settimeout(TIMEOUT)

            # Throw a thread in order to handle simultaneous clients
            threading.Thread(target = self.handleTCPClientConnection,args = (clientConnection, clientAddress)).start()

    def handleTCPClientConnection(self, clientConnection, clientAddress):
		messageFromServer = clientConnection.recv(BUFFSIZE)
		if messageFromServer:
			print("MESSAGE FROM IP %s: %s"%(clientAddress[0], parseSerializedStringIntoMessageObj(messageFromServer)))

			# Handle the message according to received signal and send a response to server
			stayInTouch, response = handleMessageAndGetResponse(messageFromServer)

			# Reply client
			clientConnection.send(response)
			
		# Close connection
		clientConnection.close()
# ********************************** ThreadedServer **********************************

# MARK: Functions
# ********************************** sendLampSensorData **********************************
def sendLampSensorData(ip, port):
	try:
		serverConnection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		serverConnection.settimeout(TIMEOUT)
	except socket.error as e:
		print("Failed to create socket: %s"%(e))
		sys.exit()

	try:
		serverConnection.connect((ip, port))
	except socket.error as e:
		print("Failed to connect: %s"%(e))
		sys.exit()
	
	stayInTouch = True
	while stayInTouch:
		# Send a Lamp Sensor Status to server
		serverConnection.send(generateLampSensorDataMessage())

		# Receive a response
		responseFromServer = serverConnection.recv(BUFFSIZE)

		print ("SERVER SAID: %s"%(parseSerializedStringIntoMessageObj(responseFromServer)))

		stayInTouch, response = handleMessageAndGetResponse(responseFromServer)
		# TODO analyse response

		time.sleep(10)

	# Close connection
	serverConnection.close()

def generateLampSensorDataMessage():
	# TODO
    message = message_pb2.Message()
    message.body.description = "description"
    message.type = message_pb2.Message.MessageType.DEFAULT
    message.sender.ip = "localhost"
    message.sender.port = 5050
    return message.SerializeToString()
# ********************************** sendLampSensorData **********************************

# ********************************** findServerOnTheInternet **********************************
def findServerOnTheInternet(ip, port):
	try:
		serverConnection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		serverConnection.settimeout(TIMEOUT)
		# Set the time-to-live for messages to 1 so they do not go past the
		# local network segment.
		ttl = struct.pack('b', 1)
		serverConnection.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
	except socket.error as e:
		print("Failed to create socket: %s"%(e))
		sys.exit()
	
	# Send a message to server
	serverConnection.sendto(generateSensorFinderMessage(), (ip, port))

	# Receive a response
	response, server = serverConnection.recvfrom(BUFFSIZE)
	print ("SERVER SAID: %s"%(parseSerializedStringIntoMessageObj(response)))

	saveServerIPAndPort(response)

	# Close connection
	serverConnection.close()

def saveServerIPAndPort(serialized_message_string):
	# TODO
    message = message_pb2.Message()
    message.ParseFromString(serialized_message_string)
    return message

def generateSensorFinderMessage(description="teste"):
	message = message_pb2.Message()
	message.body.description = description
	message.type = message_pb2.Message.MessageType.DEFAULT
	message.sender.ip = "localhost"
	message.sender.port = 5050
	return message.SerializeToString()
# ********************************** findServerOnTheInternet **********************************

def handleMessageAndGetResponse(serialized_message_string):
	message = message_pb2.Message()
	message.ParseFromString(serialized_message_string)
	stayInTouch = message.type != message_pb2.Message.MessageType.CLOSE_CONNECTION_REQUEST

	if message.type == message_pb2.Message.MessageType.CHANGE_SENSOR_STATUS_REQUEST:
		# Used by app and server to request sensor status
		return stayInTouch, changeSensorStatus()
	if message.type == message_pb2.Message.MessageType.READ_SENSOR_DATA_REQUEST:
		# Used by app and server to request sensor data
		return stayInTouch, readSensorData()
	if message.type == message_pb2.Message.MessageType.MULTICAST_SENSOR_FINDER:
		# Used by server to find sensors on the internet
		return stayInTouch, findSensor()

	return stayInTouch, getProtoMessage("Invalid message type.")

def changeSensorStatus():
	# TODO
	return getProtoMessage()

def readSensorData():
	# TODO
	return getProtoMessage()

def findSensor():
	# TODO
	return getProtoMessage()

def getProtoMessage(description="teste"):
	message = message_pb2.Message()
	message.body.description = description
	message.type = message_pb2.Message.MessageType.DEFAULT
	message.sender.ip = "localhost"
	message.sender.port = 5050
	return message.SerializeToString()

def parseSerializedStringIntoMessageObj(serialized_message_string):
    message = message_pb2.Message()
    message.ParseFromString(serialized_message_string)
    return message

def main():
	# 1 svr-cli
	# MulticastReceiver("" , MULTICAST_GROUP_PORT, MULTICAST_GROUP_IP).waitForServerFinderSignal()
	
	# 2 cli-svr
	# findServerOnTheInternet(MULTICAST_GROUP_IP, MULTICAST_GROUP_PORT)

	# 3 cli-svr
	try:
		ip = raw_input("Enter an ip address to send data continuously (Ex.: 'localhost', '127.0.0.1', ''): ")
		port = int(raw_input("Enter a port: "))
		sendLampSensorData(str(ip), int(port))
	except ValueError as e:
		print(e)

print("\n** Welcome to my SocketProtobuf app! Send a message using Protobuffer in TCP/UDP mode! **\n\n")
main()
print("** This is the end! **")