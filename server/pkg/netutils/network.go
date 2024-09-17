package network

import (
	"log"
	"net"
)

func establishUDPConnection(ipPort string) (*net.UDPConn, error) {

	// Configure UDP listening address
	udpAddr, err := net.ResolveUDPAddr("udp", ipPort)
	if err != nil {
		return nil, err
	}

	// Create UDP connection
	udpConn, err := net.ListenUDP("udp", udpAddr)
	if err != nil {
		return nil, err
	}
	return udpConn, nil
}

func establishUDPConnectionForWrite(ipPort string) (*net.UDPConn, error) {

	// Configure UDP address to write to
	udpAddr, err := net.ResolveUDPAddr("udp", ipPort)
	if err != nil {
		return nil, err
	}

	// Create UDP connection for writing
	udpConn, err := net.DialUDP("udp", nil, udpAddr)
	if err != nil {
		return nil, err
	}
	return udpConn, nil
}

// startDataForwarding starts forwarding data from a listening IP address to a forwarding IP address.
// It listens for incoming UDP packets on the listenIP address and forwards them to the forwardIP address.
// The function stops forwarding when a signal is received on the stopForwarding channel.
//
// Parameters:
// - listenIP: The IP address to listen for incoming UDP packets.
// - forwardIP: The IP address to forward the received packets to.
// - stopForwarding: A channel to receive a signal for stopping the data forwarding.
func startDataForwarding(listenIP string, forwardIP string, stopForwarding <-chan struct{}) {

	buf := make([]byte, 308)

	udpListenConn, udpErr := establishUDPConnection(listenIP)
	if udpErr != nil {
		log.Printf("Got error in establishing listening connection at %v. Error %v:", listenIP, udpErr)
	}
	defer udpListenConn.Close()

	udpForwardConn, udpErr := establishUDPConnection(forwardIP)
	if udpErr != nil {
		log.Printf(`Got error in establishing forwarding connection at %v. Error %v:`, forwardIP, udpErr)
	}
	defer udpForwardConn.Close()

	select {
	case <-stopForwarding:
		log.Printf("Stopping data fowarding to %v\n", forwardIP)
		return
	default:
		_, _, _ = udpListenConn.ReadFromUDP(buf)
		_, err := udpForwardConn.Write(buf)
		if err != nil {
			log.Panic("Got error sending packet:", err)
		}
	}

}
