package main

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math"
	"net"
	"os"
	"server/pkg/data_parsing"
	"server/pkg/ioutils"
	"server/pkg/netutils"
	"server/pkg/state"

	//"sync"
	//"os/exec"
	"strconv"
	"time"
)

var extractEventNumber = data_parsing.ParseDWord0
var dataSaveDir string = "/home/zdhughes/optical_data/"

type ctrlCmd uint32

type harvesterID struct {
	Harvester int
	Telescope int
}

type eventBuilderData struct {
	Source harvesterID
	Data   [308]byte
}

type telescopeData struct {
	Telescope int
	Data      [500]float64
}

const (
	nothing ctrlCmd = iota
	startRunCmd
	continousRunCmd
	exitCmd
	testCmd
	startDataForwardingCmd
	stopDataForwardingCmd
	// Add more enum values here
)

// To send and event to the GUI we need:
// 8 UDP packets of the same event from 1 telescope.
// func extractBlockNumber()
// func extractEventNumber()

// Declare the global variable
var globalState state.SystemState

var (
	//jobIsRunning   bool
	//JobIsrunningMu sync.Mutex
	runReady      bool   = true
	controlConnIP string = "127.0.0.1:31250"
	guiIP         string = "127.0.0.1:31255"
)

func UNUSED(x ...interface{}) {}

func main() {

	/////////////////// Start Logger //////////
	logFile, err := os.OpenFile("log.txt", os.O_CREATE|os.O_APPEND|os.O_RDWR, 0666)
	if err != nil {
		panic(err)
	}
	mw := io.MultiWriter(os.Stdout, logFile)
	log.SetOutput(mw)
	log.Println("Server started.")
	///////////////////////////////////////////

	////////// Load State /////////////////////
	// Load the state from the JSON file
	/*err = loadStateFromFile("state.json")
	if err != nil {
		log.Fatalf("Failed to load state: %v", err)
	}*/
	//printState()
	///////////////////////////////////////////

	////////// Establish Connections //////////
	// For receiving commands to this server.
	udpControlConn, err := netutils.EstablishUDPConnection(controlConnIP)
	if err != nil {
		log.Panic("Got error in establishing control connection:", err)
	}
	defer udpControlConn.Close()
	///////////////////////////////////////////

	ctrlBuf := make([]byte, 8000)
	var receivedMap map[string]interface{}
	var cmd ctrlCmd

	stopForwarding := make(chan struct{})

	for {

		n, addr, err := udpControlConn.ReadFromUDP(ctrlBuf)
		if err != nil {
			log.Println("Error in reading packet from control connection:", err)
			continue
		}
		log.Printf("Got %d bytes from UDP control packet from address %v \n", n, addr)
		receivedJSON := ctrlBuf[:n]
		err = json.Unmarshal(receivedJSON, &receivedMap)
		if err != nil {
			fmt.Println("Error unmarshaling JSON:", err)
			return
		}

		cmd = ctrlCmd(receivedMap["command"].(float64))

		switch cmd {
		case startRunCmd:

			runDuration := uint64(receivedMap["duration"].(float64))
			runNumber := uint64(receivedMap["runNumber"].(float64))
			runNumberString := strconv.FormatUint(runNumber, 10)
			sendInterval := uint32(receivedMap["sendInterval"].(float64))
			dataSaveDir = receivedMap["dataSaveDir"].(string)
			if stateContent, ok := receivedMap["state"].(string); ok {
				err := json.Unmarshal([]byte(stateContent), &globalState)
				if err != nil {
					log.Printf("Error unmarshaling state.json content: %v", err)
					return
				}
				log.Printf("Successfully loaded state from state.json")
			}

			log.Printf("Got start run command with run number %d and duration %d:", runNumber, runDuration)
			if runReady {
				runReady = false
				log.Println("Starting data logging...")
				go startHarvestersForRun(runDuration, runNumberString, sendInterval, dataSaveDir)

			} else {
				log.Println("Data run already running.")
			}

		case startDataForwardingCmd:
			listenIP := receivedMap["listenIP"].(string)
			forwardIP := receivedMap["forwardIP"].(string)
			log.Printf("Got start data forwarding command with listen IP %s and forward IP %s:", listenIP, forwardIP)
			go netutils.StartDataForwarding(listenIP, forwardIP, stopForwarding)

		case stopDataForwardingCmd:
			stopForwarding <- struct{}{}
			log.Println("Stopping data forwarding...")

		case exitCmd:
			fmt.Println("Exiting server...")
			return
		case testCmd:
			fmt.Println("Got Test!!")
		default:
			fmt.Println("What!?")

		}

	}
}

func resetStart() {
	runReady = true
}

func startHarvestersForRun(duration uint64, runNumber string, sendInterval uint32, dataSaveDir string) {

	defer resetStart()

	startListening := make(chan struct{})
	listeningTimer := time.NewTimer(time.Duration(duration) * time.Second)
	stopListening := make(chan struct{})
	telescopes := state.GetTelescopesPresentInt(&globalState)
	eventBuilderChannels := make([]chan eventBuilderData, len(telescopes)) // One per telescope.
	for i := range eventBuilderChannels {
		eventBuilderChannels[i] = make(chan eventBuilderData, 100000)
	}
	guiChannel := make(chan telescopeData, 10000)

	// NEED TO CREATE CONNECTIONS HERE AND CLOSE THEM WHEN TIMER ENDS TO PREVENT HANGING.
	// MAKE SHUNT FILENAME HERE AND PASS SO THEY ALL SHARE IT.
	for i, telescope := range telescopes {
		harvesterIPs, err := state.GetHarvestersPresentIPs(&globalState, telescope)
		if err != nil {
			log.Panic("Got error in getting harvester IP array:", err)
		}
		telescopeRunFile, runErr := ioutils.CreateRunFile(dataSaveDir, runNumber, telescope)
		if runErr != nil {
			log.Panic("Got error in creating run file:", runErr)
		}

		for _, harvesterIP := range harvesterIPs {
			udpHarvesterConn, udpErr := netutils.EstablishUDPConnection(harvesterIP)
			if udpErr != nil {
				log.Panic("Got error in establishing control connection:", udpErr)
			}
			defer udpHarvesterConn.Close()

			harvesterPosition, err := state.GetHarvesterLocalPositionFromIP(&globalState, harvesterIP)
			if err != nil {
				log.Panicf("Got error getting harvester position: %v", err)
			}
			thisHarvester := harvesterID{Harvester: harvesterPosition, Telescope: telescope}
			go startHarvesterListener(udpHarvesterConn, thisHarvester, telescopeRunFile, startListening, stopListening, sendInterval, eventBuilderChannels[i])
		}
		if sendInterval > 0 {
			go eventBuilder(eventBuilderChannels[i], guiChannel, startListening, stopListening, telescope)
		}
	}

	udpGUIConn, udpErr := netutils.EstablishUDPConnectionForWrite(guiIP)
	if udpErr != nil {
		log.Panic("Got error in establishing GUI connection:", udpErr)
	}
	defer udpGUIConn.Close()
	go guiListener(udpGUIConn, guiChannel)
	time.Sleep(1 * time.Second)
	close(startListening)
	<-listeningTimer.C
	close(stopListening)
	//for _, ch := range eventBuilderChannels {
	//	close(ch)
	//}
	// close(guiChannel) // Seems to be causing a panic. When I close the channel, the GUI listener panics.

	log.Println("Data logging ended.")

}

func eventBuilder(eventBuilderChannel <-chan eventBuilderData, guiChannel chan<- telescopeData, startListening <-chan struct{}, stopListening <-chan struct{}, telescope int) {

	// I don't know why this happens: "panic: runtime error:
	/*defer func() {
		if r := recover(); r != nil {
			log.Printf("Recovered from panic: %v", r)
		}
	}()*/

	fmt.Printf("Starting event builder for telescope %d\n", telescope)
	pixelValuesPadded := [560]float64{} // This has 60 empty channels spread throughout the array.
	emptyBuf := [308]byte{}
	eventBuilderData := eventBuilderData{Source: harvesterID{Harvester: 0, Telescope: 0}, Data: emptyBuf}
	harvesterChannels := [2]int{0, 0}
	//harvestersPresent := make([]bool, 8) // Need to make a function to get the number of actual harvesters present. And a harvesterNotPresent function.
	harvestersPresent, presentErr := state.GetHarvestersMissingBool(&globalState, telescope)
	if presentErr != nil {
		log.Panic("Got error in getting missing harvesters:", presentErr)
	}

	// Wait for calling routine to say go.
	j := 0
	<-startListening
	for i := 0; ; i++ {
		select {
		case <-stopListening:
			log.Printf("Stopping event builder for telescope %d.\nGot %d events on event builder\n", telescope, i)
			UNUSED(j)
			return
		default:
			j += 1
			// Fix this hacky way of resetting the data.
			// Since I do not check event numbers, it may be that
			// I overwrite a harvester event with a new one from the same harvester.
			// This induces an error in the GUI data. You could imagine a scenario where
			// one harvester lags behind the others, resulting in stale data being displayed.
			// Resetting the data every 32 events makes sure that it doesn't get too out of sync.
			if j > 32 {
				pixelValuesPadded = [560]float64{}
				harvestersPresent, _ = state.GetHarvestersMissingBool(&globalState, telescope)
				j = 0
			}
			/*if i%1000 == 0 {
				log.Printf("event builder: I haven't sent in %d events\n", i)
			}*/
			eventBuilderData = <-eventBuilderChannel
			//log.Printf("Got event from harvester %d on telescope %d\n", eventBuilderData.Source.Harvester, eventBuilderData.Source.Telescope)
			harvesterChannels, _ = state.GetHarvesterChannel(&globalState, eventBuilderData.Source.Telescope, eventBuilderData.Source.Harvester)
			//log.Printf("Harvester channels: %v\n", harvesterChannels)
			//log.Printf("harvestersPresent: %v\n", harvestersPresent)
			harvestersPresent[eventBuilderData.Source.Harvester] = true
			copy(pixelValuesPadded[harvesterChannels[0]:harvesterChannels[1]], data_parsing.ConvertByteArrayToDecimals(eventBuilderData.Data[28:308]))
			if state.AllHarvesters(harvestersPresent) {
				//fmt.Printf("loop is at %d\n", i)
				pixelValues := data_parsing.ExtractRelevantPixels(pixelValuesPadded)
				guiData := telescopeData{Telescope: eventBuilderData.Source.Telescope, Data: pixelValues}
				guiChannel <- guiData
				//fmt.Printf("Sent data to GUI\n")
				pixelValuesPadded = [560]float64{}
				harvestersPresent, _ = state.GetHarvestersMissingBool(&globalState, telescope)
				j = 0
			}

		}
	}

}

func guiListener(udpGUIConn *net.UDPConn, guiChannel <-chan telescopeData) {

	outGoingData := make([]byte, 8000)
	udpGUIConn.Write(outGoingData)
	telescopesPresent, presentErr := state.GetTelescopesMissingBool(&globalState)
	if presentErr != nil {
		log.Panic("Got error in getting missing harvesters:", presentErr)
	}

	for i := 0; ; i++ {
		thisData := <-guiChannel
		//fmt.Printf("Got data from telescope %d\n", thisData.Telescope)
		thisTelescope := thisData.Telescope
		thisTelescopeOffset, offsetErr := data_parsing.GetTelescopeSendByteOffset(thisTelescope)
		if offsetErr != nil {
			log.Panic("Got error in getting telescope send byte offset:", offsetErr)
			//log.Printf("Got error in getting telescope send byte offset: %v\n", offsetErr)
		}
		offset := 0
		for _, pixelValue := range thisData.Data {
			//fmt.Printf("Pixel value: %f\n", pixelValue)
			binary.LittleEndian.PutUint32(outGoingData[thisTelescopeOffset+offset:], math.Float32bits(float32(pixelValue)))
			offset += 4
		}
		telescopesPresent[thisTelescope-1] = true
		if state.AllTelescopes(telescopesPresent) {
			//fmt.Printf("Sending this data to the GUI: %v\n", thisData)
			_, _ = udpGUIConn.Write(outGoingData)
			telescopesPresent, _ = state.GetTelescopesMissingBool(&globalState)
			// Drain/flush/clear the channel
			for len(guiChannel) > 0 {
				<-guiChannel
			}

		}
	}

}

func startHarvesterListener(udpHarvesterConn *net.UDPConn, thisHarvester harvesterID, outputFile *os.File, startListening <-chan struct{}, stopListening <-chan struct{}, sendInterval uint32, eventBuilderChannel chan<- eventBuilderData) {

	buf := make([]byte, 308)
	bufIn := [308]byte{}
	thisIP := udpHarvesterConn.LocalAddr().String()
	arrayPosition, _ := state.GetHarvesterArrayPositionFromIP(&globalState, thisIP)

	// Wait for calling routine to say go.
	<-startListening
	if sendInterval > 0 {
		for i := 0; ; i++ {
			select {
			case <-stopListening:
				log.Printf("Stopping harvester listener at IP %s.\nGot %d events on harvester %v listener\n", thisIP, i, arrayPosition)
				return
			default:
				n, _, _ := udpHarvesterConn.ReadFromUDP(buf)
				_, _ = outputFile.Write(buf[:n])
				if extractEventNumber(buf, true)%sendInterval == 0 { // Maybe change this to just i%sendInterval
					copy(bufIn[:], buf[:308])
					eventBuilderChannel <- eventBuilderData{Source: thisHarvester, Data: bufIn}
				}
			}
		}
	} else {
		for i := 0; ; i++ {
			select {
			case <-stopListening:
				log.Printf("Stopping harvester listener at IP %s.\nGot %d events on harvester %v listener\n", thisIP, i, arrayPosition)
				return
			default:
				n, _, _ := udpHarvesterConn.ReadFromUDP(buf)
				_, _ = outputFile.Write(buf[:n])
			}
		}
	}

}
