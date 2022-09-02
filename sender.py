from socket import *
import sys
from packet import *
import threading

def handle_command_line_arguments():
    # Handle and maps command line arguments
    n = len(sys.argv)
    if n < 6: 
        sys.exit("The sender needs at least five command line argument")

    # emulator port, sender port, timeout interval need to be integers
    try:
        emulator_host = sys.argv[1]
        emulator_port = int(sys.argv[2])
        sender_port = int(sys.argv[3])
        timeout = int(sys.argv[4])
        input_file = sys.argv[5]
    except ValueError:
        sys.exit("Incorrect command line argument types")
    
    return emulator_host, emulator_port, sender_port, timeout, input_file

# Variables used for the two threads
timer = None
windowsize = 1 # Initial window size
seqnum = 0     # Initial next sequence number to send
lastAck = 31   # Initial base number
notyetAck = [None] * 32 # Packets that have been sent but not acked
lock = threading.Lock()
fseq = open("seqnum.log", "w")
fack = open("ack.log", "w")
fn = open("N.log", "w")
timestamp = 0  # Current timestamp
finish = 0

def send_thread(timeout, input_file, emulator_host, emulator_port):
    global timer
    global windowsize
    global seqnum
    global lastAck
    global notyetAck
    global lock
    global timestamp
    global fseq
    global fn
    global finish

    data = None
    length = -1

    # Opens the file
    try:
        infile = open(input_file, "rb")
    except FileNotFoundError:
        sys.exit("File does not exist")
    
    # Starts sending data
    try: 
        # Creates the UDP socket
        clientSocket = socket(AF_INET, SOCK_DGRAM)
        while True:
            if data == None:
                # We don't have a previous packet that needs to be sent, can read more data
                data = infile.read(500)
                data = data.decode()
                length = len(data)

            if length == 0: # No more data to send
                data = "random"
                lock.acquire()
                if ((lastAck + 1) % 32) == seqnum:
                    # All data ACKs are receieved, issue EOT packet
                    if timer != None:
                        timer.cancel()

                    packetEOT = Packet(2, seqnum, 0, "")
                    clientSocket.sendto(packetEOT.encode(), (emulator_host, emulator_port))

                    # Log sequence number
                    timestamp += 1
                    fseq.write("t=" + str(timestamp) + " EOT\n")

                    finish = 1
                    lock.release()

                    clientSocket.close()
                    infile.close()
                    break
                lock.release()
                continue   
            
            # We have data to send and window is not full, we can send packets
            lock.acquire()
            if ((seqnum - lastAck - 1) % 32) < windowsize:
                newPacket = Packet(1, seqnum, length, data)
                clientSocket.sendto(newPacket.encode(), (emulator_host, emulator_port))

                # Log sequence number
                timestamp += 1
                fseq.write("t=" + str(timestamp) + " " + str(seqnum) + "\n")
                
                # Start the timer if not started
                if timer == None:
                    timer = threading.Timer(timeout / 1000, timeout_func)
                    timer.start()

                # Updates variables
                notyetAck[seqnum] = newPacket
                seqnum = (seqnum + 1) % 32
                data = None
            lock.release()
    
    except error:
        sys.exit("UDP connection fails")

def recACK_thread(timeout, emulator_host, emulator_port, sender_port):
    global timer
    global lastAck
    global windowsize
    global seqnum
    global notyetAck
    global lock
    global timestamp
    global fseq
    global fack
    global fn
    global finish

    duplicateNum = 0

    try: 
        # Creates the UDP socket to receive ACKs
        serverSocket = socket(AF_INET, SOCK_DGRAM)
        serverSocket.bind(("", sender_port))

        while True:
            packet, clientAddress = serverSocket.recvfrom(1024)
            typ, recAck, length, data = Packet(packet).decode()

            # Check if EOT packet
            if typ == 2:
                lock.acquire()
                if timer != None:
                    timer.cancel()
                
                # Log ack file
                timestamp += 1
                fack.write("t=" + str(timestamp) + " EOT\n")
                fseq.close()
                fack.close()
                fn.close()
                lock.release()

                serverSocket.close()
                break

            lock.acquire()
            # Log ACK file
            timestamp += 1
            fack.write("t=" + str(timestamp) + " " + str(recAck) + "\n")

            if finish == 1:
                if timer != None:
                    timer.cancel()
                lock.release()
                continue

            # Check for duplicate ACKs 
            if recAck == lastAck:
                lock.release()
                duplicateNum += 1
                if duplicateNum == 3: 
                    duplicateNum = 0
                    # Enter fast retransmit
                    lock.acquire()
                    windowsize = 1
                    # Log N file
                    fn.write("t=" + str(timestamp) + " 1\n")
                        
                    # Retransmits the packet if not none
                    newpacket = notyetAck[(recAck + 1) % 32]
                    lock.release()

                    if newpacket != None:
                        serverSocket.sendto(newpacket.encode(), (emulator_host, emulator_port))
                        # Restarts the timer
                        lock.acquire()
                        # Log the seq file
                        fseq.write("t=" + str(timestamp) + " " + str((recAck+1) % 32) + "\n")

                        if timer != None:
                            timer.cancel()
                        timer = threading.Timer(timeout / 1000, timeout_func)
                        timer.start()
                        lock.release()
            # Check if it is a new ACK
            else:
                if seqnum == ((recAck + 1) % 32):
                    duplicateNum = 0
                    lastAck = recAck
                    # No outstanding packets
                    if timer != None:
                        timer.cancel()
                    timer = None
                    if windowsize < 10:
                        windowsize += 1
                        # Log N file
                        fn.write("t=" + str(timestamp) + " " + str(windowsize) + "\n")

                elif (recAck > lastAck or (seqnum < lastAck and recAck < seqnum)):
                    # NEW ACK (have outsanding packets)
                    duplicateNum = 0
                    lastAck = recAck
                    if timer != None:
                        timer.cancel()
                    timer = threading.Timer(timeout / 1000, timeout_func)
                    timer.start()
                    if windowsize < 10:
                        windowsize += 1
                        # Log N file
                        fn.write("t=" + str(timestamp) + " " + str(windowsize) + "\n")
                lock.release()

    except error:
        sys.exit("UDP connection fails")

emulator_h = None
emulator_p = None
timeoutt = None
def timeout_func():
    global windowsize
    global lastAck
    global notyetAck
    global timer
    global lock
    global timestamp
    global fseq
    global fn
    global emulator_h
    global emulator_p
    global timeoutt

    lock.acquire()
    windowsize = 1

    # Log N File
    timestamp += 1
    fn.write("t=" + str(timestamp) + " 1\n")

    # retransmits the packet
    newpacket = notyetAck[(lastAck + 1) % 32]
    
    if newpacket != None:
        serverSocket = socket(AF_INET, SOCK_DGRAM)
        serverSocket.sendto(newpacket.encode(), (emulator_h, emulator_p))
        # Log seq file
        fseq.write("t=" + str(timestamp) + " " + str((lastAck+1) % 32) + "\n")
        
    # Restarts the timer
    if timer != None:
        timer.cancel()
    timer = threading.Timer(timeoutt / 1000, timeout_func)
    timer.start()
    lock.release()

def main():
    global emulator_h
    global emulator_p
    global timeoutt

    # Gets the command line arguments
    emulator_host, emulator_port, sender_port, timeout, input_file = handle_command_line_arguments()
    
    # Set variables for timeout func
    emulator_h = emulator_host
    emulator_p = emulator_port
    timeoutt = timeout

    # Writes the initialization files
    fn.write("t=0 1\n")

    # Calls the two threads together
    t1 = threading.Thread(target=send_thread, args={timeout: timeout, input_file: input_file, emulator_host: emulator_host, emulator_port: emulator_port})
    t2 = threading.Thread(target=recACK_thread, args={timeout: timeout, emulator_host: emulator_host, emulator_port: emulator_port, sender_port: sender_port})
    t1.setDaemon(True)
    t1.start()
    t2.start()

# Runs the main function
if __name__=="__main__":
    main()
