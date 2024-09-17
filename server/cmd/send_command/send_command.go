package main

import (
	"crypto/rand"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"os"
	"strconv"
	"sync"
	"time"

	"github.com/spf13/cobra"
)

// Change these to test things.
var (
	controlConnIP string = "127.0.0.1:31250"
	telescopt1IP  string = "127.0.0.1:31261"
	telescopt2IP  string = "127.0.0.1:31262"
	telescopt3IP  string = "127.0.0.1:31263"
	telescopt4IP  string = "127.0.0.1:31264"
	harvester1IP  string = "127.0.0.1:30001"
	harvester2IP  string = "127.0.0.1:30002"
	harvester3IP  string = "127.0.0.1:30003"
	harvester4IP  string = "127.0.0.1:30004"
	harvester5IP  string = "127.0.0.1:30005"
	harvester6IP  string = "127.0.0.1:30006"
	harvester7IP  string = "127.0.0.1:30007"
	harvester8IP  string = "127.0.0.1:30008"
	harvester9IP  string = "127.0.0.1:30009"
	harvester10IP string = "127.0.0.1:30010"
	harvester11IP string = "127.0.0.1:30011"
	harvester12IP string = "127.0.0.1:30012"
	harvester13IP string = "127.0.0.1:30013"
	harvester14IP string = "127.0.0.1:30014"
	harvester15IP string = "127.0.0.1:30015"
	harvester16IP string = "127.0.0.1:30016"
	harvester17IP string = "127.0.0.1:30017"
	harvester18IP string = "127.0.0.1:30018"
	harvester19IP string = "127.0.0.1:30019"
	harvester20IP string = "127.0.0.1:30020"
	harvester21IP string = "127.0.0.1:30021"
	harvester22IP string = "127.0.0.1:30022"
	harvester23IP string = "127.0.0.1:30023"
	harvester24IP string = "127.0.0.1:30024"
	harvester25IP string = "127.0.0.1:30025"
	harvester26IP string = "127.0.0.1:30026"
	harvester27IP string = "127.0.0.1:30027"
	harvester28IP string = "127.0.0.1:30028"
	harvester29IP string = "127.0.0.1:30029"
	harvester30IP string = "127.0.0.1:30030"
	harvester31IP string = "127.0.0.1:30031"
	harvester32IP string = "127.0.0.1:30032"
)

type ctrlCmd uint32

const (
	nothing ctrlCmd = iota
	startRunCmd
	exitCmd
	testCmd
	// Add more enum values here
)

// And this.
var telescopes = [...]int{1, 2, 3, 4}

var harvesters = [...]int{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32}

//var harvesters = [...]int{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16}

func getTelescopeIP(telescope int) string {
	switch telescope {
	case 1:
		return telescopt1IP
	case 2:
		return telescopt2IP
	case 3:
		return telescopt3IP
	case 4:
		return telescopt4IP
	}
	return "0"
}

func getHarvesterIP(harvester int) string {
	switch harvester {
	case 1:
		return harvester1IP
	case 2:
		return harvester2IP
	case 3:
		return harvester3IP
	case 4:
		return harvester4IP
	case 5:
		return harvester5IP
	case 6:
		return harvester6IP
	case 7:
		return harvester7IP
	case 8:
		return harvester8IP
	case 9:
		return harvester9IP
	case 10:
		return harvester10IP
	case 11:
		return harvester11IP
	case 12:
		return harvester12IP
	case 13:
		return harvester13IP
	case 14:
		return harvester14IP
	case 15:
		return harvester15IP
	case 16:
		return harvester16IP
	case 17:
		return harvester17IP
	case 18:
		return harvester18IP
	case 19:
		return harvester19IP
	case 20:
		return harvester20IP
	case 21:
		return harvester21IP
	case 22:
		return harvester22IP
	case 23:
		return harvester23IP
	case 24:
		return harvester24IP
	case 25:
		return harvester25IP
	case 26:
		return harvester26IP
	case 27:
		return harvester27IP
	case 28:
		return harvester28IP
	case 29:
		return harvester29IP
	case 30:
		return harvester30IP
	case 31:
		return harvester31IP
	case 32:
		return harvester32IP
	}
	return "0"
}

func main() {

	var rootCmd = &cobra.Command{Use: "send_command"}

	var cmd1 = &cobra.Command{
		Use:   "generate [maxPackets] [packetInterval]",
		Short: "Starts generating and sending N=[maxPackets] fake (zeroed) 377-byte packets at [packetInterval] microseconds",
		Args:  cobra.ExactArgs(2),
		Run: func(cmd *cobra.Command, args []string) {
			maxPackets, err := strconv.Atoi(args[0])
			if err != nil {
				fmt.Println("Error parsing option2Cmd1:", err)
				os.Exit(1)
			}
			packetInterval, err := strconv.Atoi(args[1])
			if err != nil {
				fmt.Println("Error parsing option2Cmd1:", err)
				os.Exit(1)
			}

			sendFakeDataArray(maxPackets, packetInterval)

		},
	}

	var cmd2 = &cobra.Command{
		Use:   "listen [duration] [runID] [sendInterval]",
		Short: "Requests the server start listen for [duration] seconds and saving to file [runID] with a [sendInterval] of events",
		Args:  cobra.ExactArgs(3),
		Run: func(cmd *cobra.Command, args []string) {
			duration, err := strconv.Atoi(args[0])
			if err != nil {
				fmt.Println("Error parsing option2Cmd1:", err)
				os.Exit(1)
			}
			runID, err := strconv.Atoi(args[1])
			if err != nil {
				fmt.Println("Error parsing option2Cmd1:", err)
				os.Exit(1)
			}
			sendInterval, err := strconv.Atoi(args[2])
			if err != nil {
				fmt.Println("Error parsing option2Cmd1:", err)
				os.Exit(1)
			}

			requestListen(duration, runID, sendInterval)

		},
	}

	var cmd3 = &cobra.Command{
		Use:   "scan [maxPackets] [packetIntervalStart] [packetIntervalStop] [packetIntervalStep]",
		Short: "Scans through a ([packetIntervalStart], [packetIntervalStop]) range of packet speeds by using the [generate] command in [packetIntervalStep] steps.",
		Args:  cobra.ExactArgs(4),
		Run: func(cmd *cobra.Command, args []string) {
			maxPackets, err := strconv.Atoi(args[0])
			if err != nil {
				fmt.Println("Error parsing maxPackets:", err)
				os.Exit(1)
			}
			packetIntervalStart, err := strconv.Atoi(args[1])
			if err != nil {
				fmt.Println("Error parsing packetIntervalStart:", err)
				os.Exit(1)
			}
			packetIntervalStop, err := strconv.Atoi(args[2])
			if err != nil {
				fmt.Println("Error parsing packetIntervalStop:", err)
				os.Exit(1)
			}
			packetIntervalStep, err := strconv.Atoi(args[3])
			if err != nil {
				fmt.Println("Error parsing packetIntervalStep:", err)
				os.Exit(1)
			}

			duration := 30
			runID := 1
			sendInterval := 0
			for i := packetIntervalStart; i <= packetIntervalStop; i += packetIntervalStep {

				requestListen(duration, runID, sendInterval)
				time.Sleep(time.Duration(3) * time.Second)
				sendFakeDataArray(maxPackets, i)
				time.Sleep(time.Duration(duration) * time.Second)
			}

		},
	}

	var cmd4 = &cobra.Command{
		Use:   "generateH [maxPackets] [packetInterval]",
		Short: "Starts generating and sending N=[maxPackets] fake (zeroed) 308-byte packets at [packetInterval] microseconds",
		Args:  cobra.ExactArgs(2),
		Run: func(cmd *cobra.Command, args []string) {
			maxPackets, err := strconv.Atoi(args[0])
			if err != nil {
				fmt.Println("Error parsing option2Cmd4:", err)
				os.Exit(1)
			}
			packetInterval, err := strconv.Atoi(args[1])
			if err != nil {
				fmt.Println("Error parsing option2Cmd4:", err)
				os.Exit(1)
			}

			sendFakeDataArrayH(maxPackets, packetInterval)

		},
	}

	rootCmd.AddCommand(cmd1)
	rootCmd.AddCommand(cmd2)
	rootCmd.AddCommand(cmd3)
	rootCmd.AddCommand(cmd4)
	rootCmd.Execute()

}

func requestListen(duration int, runID int, sendInterval int) {
	dataMap := map[string]interface{}{
		"command":      startRunCmd,
		"runNumber":    uint64(runID),
		"duration":     uint64(duration),
		"telescopes":   telescopes,
		"sendInterval": uint64(sendInterval),
	}

	// Read the state.json file
	stateFileContent, err := os.ReadFile("../state.json")
	if err != nil {
		fmt.Println("Error reading state.json:", err)
		return
	}

	// Add the state.json content to the data map
	dataMap["state"] = string(stateFileContent)

	// Convert map to JSON
	jsonData, err := json.Marshal(dataMap)
	if err != nil {
		fmt.Println("Error marshaling JSON:", err)
		return
	}

	fmt.Printf("command is type %T\n", dataMap["command"])

	udpControlConn, err := establishUDPConnection(controlConnIP)
	if err != nil {
		log.Panic("Got error in establishing control connection:", err)
	}
	defer udpControlConn.Close()

	_, err = udpControlConn.Write(jsonData)
	if err != nil {
		fmt.Println("Error sending JSON over UDP:", err)
		return
	}
}

func sendFakeDataArray(maxPackets int, packetInterval int) {

	var wg sync.WaitGroup
	startSending := make(chan struct{})

	for _, telescope := range telescopes {
		wg.Add(1)
		go func(telescope int) {
			defer wg.Done()
			sendFakeData(telescope, maxPackets, packetInterval, startSending)
		}(telescope)
	}

	time.Sleep(1 * time.Second)
	close(startSending)
	wg.Wait()
	log.Println("Data send ended.")

}

func sendFakeDataArrayH(maxPackets int, packetInterval int) {

	var wg sync.WaitGroup
	startSending := make(chan struct{})

	for _, harvester := range harvesters {
		wg.Add(1)
		go func(harvester int) {
			defer wg.Done()
			sendFakeDataH(harvester, maxPackets, packetInterval, startSending)
		}(harvester)
	}

	time.Sleep(1 * time.Second)
	close(startSending)
	wg.Wait()
	log.Println("Data send ended.")

}

func sendFakeDataH(harvester int, maxPackets int, packetInterval int, startSending <-chan struct{}) {

	ip := getHarvesterIP(harvester)
	fmt.Printf("harvester %d starting\n", harvester)

	udpConn, udpErr := establishUDPConnection(ip)
	if udpErr != nil {
		log.Panic("Got error in establishing control connection:", udpErr)
	}
	defer udpConn.Close()
	j := 1
	buf := make([]byte, 308)
	iterationBytes := make([]byte, 4)

	ticker := time.NewTicker(time.Duration(packetInterval) * time.Microsecond)
	defer ticker.Stop()

	startTime := time.Now()
	for range ticker.C {
		if j >= maxPackets {
			break
		}
		binary.LittleEndian.PutUint32(iterationBytes, uint32(j))
		copy(buf[:4], iterationBytes)

		// Fill the last 280 bytes with random values
		_, err := rand.Read(buf[28:])
		if err != nil {
			log.Fatalf("Failed to generate random data: %v", err)
		}

		udpConn.Write(buf)
		j++
		/* 		if j%10000 == 0 {
			fmt.Printf("On packet %d\n", j)
		} */

	}

	endTime := time.Now()
	elapsedTime := endTime.Sub(startTime)
	pps := float64(maxPackets) / elapsedTime.Seconds()
	fmt.Printf("Elapsed Time on telescope %d: %v\n", harvester, elapsedTime)
	fmt.Printf("pps on telescope %d: %v\n", harvester, pps)

}

func sendFakeData(telescope int, maxPackets int, packetInterval int, startSending <-chan struct{}) {

	ip := getTelescopeIP(telescope)
	fmt.Printf("Telescope %d starting\n", telescope)

	udpConn, udpErr := establishUDPConnection(ip)
	if udpErr != nil {
		log.Panic("Got error in establishing control connection:", udpErr)
	}
	defer udpConn.Close()
	j := 1
	buf := make([]byte, 377)
	iterationBytes := make([]byte, 4)

	ticker := time.NewTicker(time.Duration(packetInterval) * time.Microsecond)
	defer ticker.Stop()

	startTime := time.Now()
	for range ticker.C {
		if j >= maxPackets {
			break
		}
		binary.LittleEndian.PutUint32(iterationBytes, uint32(j))
		copy(buf[:4], iterationBytes)
		udpConn.Write(buf)
		j++
		/* 		if j%10000 == 0 {
			fmt.Printf("On packet %d\n", j)
		} */

	}

	endTime := time.Now()
	elapsedTime := endTime.Sub(startTime)
	pps := float64(maxPackets) / elapsedTime.Seconds()
	fmt.Printf("Elapsed Time on telescope %d: %v\n", telescope, elapsedTime)
	fmt.Printf("pps on telescope %d: %v\n", telescope, pps)

}

func establishUDPConnection(ipPort string) (*net.UDPConn, error) {

	// Configure UDP listening address
	udpAddr, err := net.ResolveUDPAddr("udp", ipPort)
	if err != nil {
		return nil, err
	}

	// Create UDP connection
	udpConn, err := net.DialUDP("udp", nil, udpAddr)
	if err != nil {
		return nil, err
	}
	return udpConn, nil
}
