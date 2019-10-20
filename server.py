import socket
import threading
import datetime
import sys
import message_pb2
import struct

from myconfig import BUFFSIZE
from myconfig import TIMEOUT
from myconfig import MULTICAST_GROUP_IP
from myconfig import MULTICAST_GROUP_PORT

# MARK: Global variables
requestsReceived = 0
serverStartedSince = datetime.datetime.now()

# MARK: Classes definitions
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
            print("Server is up and ready to receive connections in TCP MODE! IP '%s' and PORT '%s'"%(self.ip, self.port))
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
        print("Client connected from IP %s"%(clientAddress[0]))

        # Stay in touch to client until he/she leaves
        stayInTouch = True

        while stayInTouch:
            # Get client's message
            messageFromClient = clientConnection.recv(BUFFSIZE)
            if messageFromClient:
                print("MESSAGE FROM IP %s: %s"%(clientAddress[0], parseMessage(messageFromClient)))

                # Handle the message according to received signal and send a response to client
                stayInTouch, response = handleMessageAndGetResponse(messageFromClient)

                # Reply client
                clientConnection.send(response)

        # Close connection when user sends a CLOSE signal
        clientConnection.close()
        print("Client disconnected from IP %s"%(clientAddress[0]))

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
            print("Multicast Server is up and ready to receive connections in UDP MODE! IP '%s' and PORT '%s'"%(self.ip, self.port))
        except socket.error as e:
            print("Failed to bind: %s"%(e))
            sys.exit()

        # Tell the operating system to add the socket to the multicast group
        # on all interfaces.
        group = socket.inet_aton(ip_group)
        mreq = struct.pack('4sL', group, socket.INADDR_ANY)
        self.serverSocket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    # MARK: Methods
    def waitForSensorFinderSignal(self):
        threading.Thread(target = self.handleMulticastUDPMessages).start()

    def handleMulticastUDPMessages(self):
        while True:
            # Get client's message
            messageFromClient, clientAddress = self.serverSocket.recvfrom(BUFFSIZE)
            if messageFromClient:
                print("MESSAGE FROM IP %s: %s"%(clientAddress[0], parseMessage(messageFromClient)))

                # Handle the message according to received signal and send a response to client
                stayInTouch, response = handleMessageAndGetResponse(messageFromClient)

                # Reply client
                self.serverSocket.sendto(response, clientAddress)

        print("Client disconnected from IP %s"%(clientAddress[0]))

# MARK: Functions
def findSensorsOnTheInternet(ip, port):
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
	message = raw_input("Enter a message: ")
	serverConnection.sendto(getProtoMessage(message), (ip, port))

	# Receive a response
	response, server = serverConnection.recvfrom(BUFFSIZE)
	print ("SERVER SAID: %s"%(parseMessage(response)))

	stayInTouch, handledResponse = handleResponse(response)
	# TODO ignore handledResponse unless you need to do smt

	# Close connection
	serverConnection.close()
	print ("You have just left the connection.")

def incrementNumberOfConnections():
    # Increment number of received connections
    global requestsReceived
    requestsReceived += 1

def handleMessageAndGetResponse(serialized_message_string):
    incrementNumberOfConnections()

    switcher =  {
        message_pb2.Message.MessageType.CHANGE_SENSOR_STATUS_REQUEST: change_sensor_status, # Used by app and server to request sensor status
        message_pb2.Message.MessageType.CHANGE_SENSOR_STATUS_RESPONSE: reply_sensor_status, # Used by sensor to send sensor status
       
        message_pb2.Message.MessageType.READ_SENSOR_DATA_REQUEST: read_sensor_data, # Used by app and server to request sensor data
        message_pb2.Message.MessageType.READ_SENSOR_DATA_RESPONSE: reply_sensor_data, # Used by sensor to send sensor data
      
        message_pb2.Message.MessageType.MULTICAST_SENSOR_FINDER: find_sensor, # Used by server to find sensors on the internet
        message_pb2.Message.MessageType.MULTICAST_SENSOR_FINDER_ACK: ack_sensor_up, # Used by sensor to show up it is alive
      
        message_pb2.Message.MessageType.MULTICAST_SERVER_FINDER: find_server, # Used by sensor to find server on the internet
        message_pb2.Message.MessageType.MULTICAST_SERVER_FINDER_ACK: ack_server_up, # Used by server to show up it is alive

        message_pb2.Message.MessageType.UPTIME_REQUEST: get_server_uptime, # Used by app to get datetime since server's up
        message_pb2.Message.MessageType.UPTIME_RESPONSE: reply_server_uptime, # Used by server to send datetime since it's up

        message_pb2.Message.MessageType.REQNUM_REQUEST: get_server_reqnum, # Used by app to get the number of requests since server's up
        message_pb2.Message.MessageType.REQNUM_RESPONSE: reply_server_reqnum, # Used by server to send the number of requests since it's up

        message_pb2.Message.MessageType.CLOSE_CONNECTION_REQUEST: close_connection, # Used by app to attempt closing connection
        message_pb2.Message.MessageType.CLOSE_CONNECTION_ACK: ack_close_connection # Used by server to acknowledge
    }

    message = message_pb2.Message()
    message.ParseFromString(serialized_message_string)
    response = switcher.get(message.type, getProtoMessage("Invalid message type."))
    stayInTouch = message.type != message_pb2.Message.MessageType.CLOSE_CONNECTION_REQUEST
    return stayInTouch, response

def change_sensor_status():
    return getProtoMessage()
def reply_sensor_status():
    return getProtoMessage()

def read_sensor_data():
    return getProtoMessage()
def reply_sensor_data():
    return getProtoMessage()

def find_sensor():
    return getProtoMessage()
def ack_sensor_up():
    return getProtoMessage()

def find_server():
    return getProtoMessage()
def ack_server_up():
    return getProtoMessage()

def get_server_uptime():
    return getProtoMessage("The server is running since %s. Total time up: %s"%(serverStartedSince, datetime.datetime.now() - serverStartedSince))
def reply_server_uptime():
    return getProtoMessage("The server is running since %s. Total time up: %s"%(serverStartedSince, datetime.datetime.now() - serverStartedSince))

def get_server_reqnum():
    return getProtoMessage("Number of requests received, including this one: %s"%(requestsReceived))
def reply_server_reqnum():
    return getProtoMessage("Number of requests received, including this one: %s"%(requestsReceived))

def close_connection():
    return getProtoMessage()
def ack_close_connection():
    return getProtoMessage()

def getProtoMessage(description="teste"):
    message = message_pb2.Message()
    message.body.description = description
    message.type = message_pb2.Message.MessageType.DEFAULT
    message.sender.ip = "localhost"
    message.sender.port = 5050
    return message.SerializeToString()

def parseMessage(serialized_message_string):
    message = message_pb2.Message()
    message.ParseFromString(serialized_message_string)
    return message

# MARK: Init main()
def main():
    MulticastReceiver("" , MULTICAST_GROUP_PORT, MULTICAST_GROUP_IP).waitForSensorFinderSignal()

    try:
        ip = raw_input("Enter an ip address to this server (Ex.: 'localhost', '127.0.0.1', ''): ")
        port = int(raw_input("Enter a port: "))
        ThreadedServer(str(ip), int(port)).startTCPServer()
    except ValueError as e:
        print(e)

print("\n** Welcome to my socket app! Send a message using TCP/UDP sockets! **\n\n")
main()
print("** This is the end! **")