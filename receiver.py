from socket import *
import sys
from packet import *

def handle_command_line_arguments():
    # Handle and maps command line arguments
    n = len(sys.argv)
    if n < 5: 
        sys.exit("The receiver needs at least four command line argument")

    # emulator port and receiver port need to be integers
    try:
        emulator_host = sys.argv[1]
        emulator_port = int(sys.argv[2])
        receiver_port = int(sys.argv[3])
        output_file = sys.argv[4]
    except ValueError:
        sys.exit("Incorrect command line argument types")
    
    return emulator_host, emulator_port, receiver_port, output_file

def receive_packets(emulator_host, emulator_port, receiver_port, output_file):
    buffer = [None] * 32
    expect_seqnum = 0

    # Open files
    f = open(output_file, "w")
    f2 = open("arrival.log", "w")

    # Create UDP sockets
    try:
        receiveSocket = socket(AF_INET, SOCK_DGRAM)
        receiveSocket.bind(("", receiver_port))
        sendSocket = socket(AF_INET, SOCK_DGRAM)
    except error:
        sys.exit("UDP connection fails")
    
    while True:
        packet, clientAddress = receiveSocket.recvfrom(1024)
        typ, seqnum, length, data = Packet(packet).decode()

        if typ == 2:   # EOT packet 
            # Records the event
            f2.write("EOT\n")
            # Sends an EOT back and exit
            EOTpacket = Packet(2, expect_seqnum, 0, "")
            sendSocket.sendto(EOTpacket.encode(), (emulator_host, emulator_port))
            sendSocket.close()
             # Close the files
            f.close()
            f2.close()
            break
        
        f2.write(str(seqnum)+ '\n')
        
        if seqnum == expect_seqnum:
            f.write(data) # Data is of string type
            expect_seqnum = (expect_seqnum + 1) % 32 # Increment the expect_seqnum

            while buffer[expect_seqnum] != None:
                f.write(buffer[expect_seqnum])
                buffer[expect_seqnum] = None
                expect_seqnum = (expect_seqnum + 1) % 32
        else:
            # Check if sequence number is within the next 10 sequence numbers
            flag = 0
            if expect_seqnum <= 22:
                if seqnum in range(expect_seqnum, expect_seqnum+10): 
                    flag = 1
            else:
                n = 9 - (31 - expect_seqnum) 
                if (seqnum in range(expect_seqnum, 32)) or (seqnum in range(0, n)):
                    flag = 1
            
            if flag == 1 and buffer[seqnum] == None:
                 # Store the packet's data
                buffer[seqnum] = data
            
        # Send an ACK packet for the last wrote to disk
        ackPacket = Packet(0, (expect_seqnum-1) % 32, 0, "")
        sendSocket.sendto(ackPacket.encode(), (emulator_host, emulator_port))

def main():
    # Gets the command line arguments
    emulator_host, emulator_port, receiver_port, output_file = handle_command_line_arguments()

    # Calls the receive program
    receive_packets(emulator_host, emulator_port, receiver_port, output_file)

# Runs the main function
if __name__=="__main__":
    main()
