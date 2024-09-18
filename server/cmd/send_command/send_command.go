package main

import (
	"crypto/rand"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"server/pkg/netutils"
	"server/pkg/state"
	"strconv"
	"sync"
	"time"

	"github.com/spf13/cobra"
)

// Change these to test things.
var (
	controlConnIP string = "127.0.0.1:31250"
	configFile    string = "../internal/state.json"
)

type ctrlCmd uint32

const (
	nothing ctrlCmd = iota
	startRunCmd
	exitCmd
	testCmd
	// Add more enum values here
)

func main() {

	pGlobalState, _ := state.LoadStateFromFile(configFile)

	var rootCmd = &cobra.Command{Use: "send_command"}

	var cmd1 = &cobra.Command{
		Use:   "generate [maxPackets] [packetInterval]",
		Short: "Starts generating and sending N=[maxPackets] fake (zeroed) 308-byte packets at [packetInterval] microseconds",
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

			sendTestDataToHarvesters(pGlobalState, maxPackets, packetInterval)

		},
	}

	var cmd2 = &cobra.Command{
		Use:   "listen [duration] [runID] [sendInterval] [dataSaveDir]",
		Short: "Requests the server start listen for [duration] seconds and saving to file [runID] with a [sendInterval] of events",
		Args:  cobra.ExactArgs(4),
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
			dataSaveDir := args[3]

			requestListen(duration, runID, sendInterval, dataSaveDir)

		},
	}

	var cmd3 = &cobra.Command{
		Use:   "scan [maxPackets] [packetIntervalStart] [packetIntervalStop] [packetIntervalStep] [dataSaveDir]",
		Short: "Scans through a ([packetIntervalStart], [packetIntervalStop]) range of packet speeds by using the [generate] command in [packetIntervalStep] steps.",
		Args:  cobra.ExactArgs(5),
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
			dataSaveDir := args[4]

			duration := 30
			runID := 1
			sendInterval := 0
			for i := packetIntervalStart; i <= packetIntervalStop; i += packetIntervalStep {

				requestListen(duration, runID, sendInterval, dataSaveDir)
				time.Sleep(time.Duration(3) * time.Second)
				sendTestDataToHarvesters(pGlobalState, maxPackets, i)
				time.Sleep(time.Duration(duration) * time.Second)
			}

		},
	}

	rootCmd.AddCommand(cmd1)
	rootCmd.AddCommand(cmd2)
	rootCmd.AddCommand(cmd3)
	rootCmd.Execute()

}

func requestListen(duration int, runID int, sendInterval int, dataSaveDir string) {
	dataMap := map[string]interface{}{
		"command":      startRunCmd,
		"runNumber":    uint64(runID),
		"duration":     uint64(duration),
		"sendInterval": uint64(sendInterval),
		"dataSaveDir":  dataSaveDir,
	}

	// Read the state.json file
	stateFileContent, _ := state.GetStateFileContents(configFile)

	// Add the state.json content to the data map
	dataMap["state"] = string(stateFileContent)

	// Convert map to JSON
	jsonData, err := json.Marshal(dataMap)
	if err != nil {
		fmt.Println("Error marshaling JSON:", err)
		return
	}

	fmt.Printf("command is type %T\n", dataMap["command"])

	udpControlConn, err := netutils.EstablishUDPConnectionForWrite(controlConnIP)
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

func sendTestDataToHarvesters(pGlobalState *state.SystemState, maxPackets int, packetInterval int) {
	var wg sync.WaitGroup

	for _, telescope := range state.GetTelescopesPresentInt(pGlobalState) {
		harvesters, _ := state.GetHarvestersPresentInt(pGlobalState, telescope)
		for _, harvester := range harvesters {
			wg.Add(1)
			ip, _ := state.GetHarvesterIP(pGlobalState, telescope, harvester)
			gHarvester, _ := state.GetHarvesterArrayPositionFromIP(pGlobalState, ip)
			fmt.Printf("Starting data send for harvester %v. Sending data to %s\n", gHarvester, ip)
			go func(ip string, telescope int, harvester int) {
				defer wg.Done()
				sendDataToIP(ip, gHarvester, maxPackets, packetInterval)
			}(ip, telescope, harvester)
		}
	}
	wg.Wait()
	log.Println("Data send ended.")
}

func sendDataToIP(ip string, harvester int, maxPackets int, packetInterval int) {

	harvesterUDPConn, _ := netutils.EstablishUDPConnectionForWrite(ip)
	defer harvesterUDPConn.Close()

	j := 1
	buf := make([]byte, 308)
	iterationBytes := make([]byte, 4)

	ticker := time.NewTicker(time.Duration(packetInterval) * time.Microsecond)
	fmt.Printf("Sending data to %s at %v ticker time.\n", ip, time.Duration(packetInterval)*time.Microsecond)
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

		harvesterUDPConn.Write(buf)
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
