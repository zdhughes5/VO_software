package main

import (
	"crypto/rand"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math"
	"net"
	"os"

	//"sync"
	//"os/exec"
	"strconv"
	"time"
)

var extractEventNumber = parseDWord0
var dataSaveDir string = "/home/zdhughes/optical_data/"

func parseWordUint32(event []byte, i int, j int, littleEndian bool) uint32 {

	if littleEndian {
		dataWord := binary.LittleEndian.Uint32(event[i:j])
		return dataWord
	} else {
		dataWord := binary.BigEndian.Uint32(event[i:j])
		return dataWord
	}

}

func parseDWord0(event []byte, littleEndian bool) uint32 {
	return parseWordUint32(event, 0, 4, littleEndian)
}

// Convert a 32-bit word to a decimal number with 16 integer bits and 16 fractional bits
func convertToDecimal(word uint32) float64 {
	// Extract the integer part (first 16 bits)
	integerPart := uint16(word >> 16)

	// Extract the fractional part (last 16 bits)
	fractionalPart := word & 0xFFFF

	// Convert the fractional part to decimal
	fractionalDecimal := 0.0
	for i := 0; i < 16; i++ {
		if fractionalPart&(1<<uint(15-i)) != 0 {
			fractionalDecimal += math.Pow(2, float64(-1-i))
		}
	}

	// Combine the integer and fractional parts
	return float64(integerPart) + fractionalDecimal
}

// Convert a byte array of length 280 to an array of 70 decimal values
func convertByteArrayToDecimals(data []byte) []float64 {
	if len(data) != 280 {
		panic("Input byte array must be of length 280")
	}

	decimals := make([]float64, 70)
	for i := 0; i < 70; i++ {
		// Extract the 32-bit word from the byte array
		word := binary.BigEndian.Uint32(data[i*4 : (i+1)*4])
		// Convert the 32-bit word to a decimal value
		decimals[i] = convertToDecimal(word)
	}

	return decimals
}

// Extract relevant pixel values from a padded array to a new array of 500 pixels
func extractRelevantPixels(pixelValuesPadded [560]float64) [500]float64 {
	if len(pixelValuesPadded) != 560 {
		panic("Input pixel array must be of length 560")
	}

	pixelValues := [500]float64{}
	copy(pixelValues[0:130], pixelValuesPadded[0:130])
	copy(pixelValues[130:250], pixelValuesPadded[140:260])
	copy(pixelValues[250:380], pixelValuesPadded[280:410])
	copy(pixelValues[380:500], pixelValuesPadded[420:540])

	return pixelValues
}

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

// Function to get the IP address of a specific telescope and harvester position
func getHarvesterIP(telescopeNumber int, harvesterPosition int) (string, error) {
	for _, telescope := range globalState.Telescopes {
		if telescope.Telescope == telescopeNumber {
			for _, harvester := range telescope.Harvesters {
				if harvester.TelescopePosition == harvesterPosition {
					return harvester.IP, nil
				}
			}
		}
	}
	return "", fmt.Errorf("harvester with telescope position %d not found in telescope %d", harvesterPosition, telescopeNumber)
}

// To send and event to the GUI we need:
// 8 UDP packets of the same event from 1 telescope.
// func extractBlockNumber()
// func extractEventNumber()

// Define the struct to hold the state of each harvester, including its IP address, channel, and pixel index
type HarvesterState struct {
	ArrayPosition     int    `json:"arrayPosition"`
	TelescopePosition int    `json:"telescopePosition"`
	Missing           bool   `json:"missing"`
	IP                string `json:"ip"`
	Channel           [2]int `json:"channel"`
	PixelIndex        [2]int `json:"pixelIndex"`
}

// Define the struct to hold the state of each telescope, including its number and harvesters
type TelescopeState struct {
	Telescope  int              `json:"telescope"`
	Missing    bool             `json:"missing"`
	Harvesters []HarvesterState `json:"harvesters"`
}

// Define the struct to hold the state of the entire system, including its telescopes
type SystemState struct {
	Telescopes []TelescopeState `json:"telescopes"`
}

// Declare the global variable
var globalState SystemState

// Function to load the state from a JSON file
func loadStateFromFile(filename string) error {
	file, err := os.Open(filename)
	if err != nil {
		return err
	}
	defer file.Close()

	bytes, err := io.ReadAll(file)
	if err != nil {
		return err
	}

	err = json.Unmarshal(bytes, &globalState)
	if err != nil {
		return err
	}

	return nil
}

// Function to print the state for debugging
func printState() {
	for i, telescope := range globalState.Telescopes {
		fmt.Printf("Telescope %d: Telescope=%d, Missing=%v\n", i+1, telescope.Telescope, telescope.Missing)
		for j, harvester := range telescope.Harvesters {
			fmt.Printf("  Harvester %d: ArrayPosition=%d, TelescopePosition=%d, Missing=%v, IP=%s, Channel=%v, PixelIndex=%v\n", j+1, harvester.ArrayPosition, harvester.TelescopePosition, harvester.Missing, harvester.IP, harvester.Channel, harvester.PixelIndex)
		}
	}
}

var (
	//jobIsRunning   bool
	//JobIsrunningMu sync.Mutex
	runReady      bool   = true
	controlConnIP string = "127.0.0.1:31250"
	guiIP         string = "127.0.0.1:31255"
)

func UNUSED(x ...interface{}) {}

func getTelescopesPresent() []int {
	var telescopeNumbers []int
	for _, telescope := range globalState.Telescopes {
		if !telescope.Missing {
			telescopeNumbers = append(telescopeNumbers, telescope.Telescope)
		}
	}
	return telescopeNumbers
}

func main() {

	UNUSED(getHarvesterIP)
	UNUSED(getMissingTelescopes)
	UNUSED(getHarvesterPositionFromIP)

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
	udpControlConn, err := establishUDPConnection(controlConnIP)
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

			runNumber := uint64(receivedMap["runNumber"].(float64))
			runNumberString := strconv.FormatUint(runNumber, 10)
			runDuration := uint64(receivedMap["duration"].(float64))
			//telescopes := receivedMap["telescopes"].([]interface{})
			//telescopeInts := make([]int, len(telescopes))
			if stateContent, ok := receivedMap["state"].(string); ok {
				err := json.Unmarshal([]byte(stateContent), &globalState)
				if err != nil {
					log.Printf("Error unmarshaling state.json content: %v", err)
					return
				}
				log.Printf("Successfully loaded state from state.json")
			}
			//fmt.Printf("globalState: %v\n", globalState)
			telescopeInts := getTelescopesPresent()
			fmt.Printf("globalState: %v\n", telescopeInts)
			/*for i, val := range telescopes {
				telescopeInts[i] = int(val.(float64))
			}*/
			sendInterval := uint32(receivedMap["sendInterval"].(float64))

			log.Printf("Got start run command with run number %d and duration %d:", runNumber, runDuration)
			if runReady {
				runReady = false
				log.Println("Starting data logging...")
				go startHarvestersForRun(runDuration, runNumberString, telescopeInts, sendInterval)

			} else {
				log.Println("Data run already running.")
			}

		case startDataForwardingCmd:
			listenIP := receivedMap["listenIP"].(string)
			forwardIP := receivedMap["forwardIP"].(string)
			log.Printf("Got start data forwarding command with listen IP %s and forward IP %s:", listenIP, forwardIP)
			go startDataForwarding(listenIP, forwardIP, stopForwarding)

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

func resetStart() {
	runReady = true
}

// createRunFile is a function that creates a run file for a given run number and telescope.
// It takes the run number as a string and the telescope number as an integer.
// The function returns a pointer to the created file and an error, if any.
// If the file already exists, it appends a random string to the file name and creates a new file.
// If there is an error creating the output file, it panics with the error message.
func createRunFile(runNumber string, telescope int) (*os.File, error) {
	telescopeString := strconv.Itoa(telescope)
	outputFileName := dataSaveDir + runNumber + "_" + telescopeString + ".bin"
	randomString, _ := generateRandomString(16)

	if _, existsErr := os.Stat(outputFileName); os.IsNotExist(existsErr) {
		outputFile, createErr := os.Create(outputFileName)
		if createErr != nil {
			log.Panicf("Got error creating output file: %v", createErr)
		}
		return outputFile, nil
	} else {
		log.Println("File already exists:", outputFileName, "Check you're run number!")
		outputFileName = dataSaveDir + runNumber + "_" + telescopeString + "_" + randomString + ".bin"
		log.Println("Shunting data to:", outputFileName)
		outputFile, createErr := os.Create(outputFileName)
		if createErr != nil {
			log.Panicf("Got error creating output file: %v", createErr)
		}
		return outputFile, nil
	}
}

func getHarvesterIPArray(telescopeNumber int) ([]string, error) {
	var ips []string
	for _, telescope := range globalState.Telescopes {
		if telescope.Telescope == telescopeNumber {
			for _, harvester := range telescope.Harvesters {
				ips = append(ips, harvester.IP)
			}
			return ips, nil
		}
	}
	return nil, fmt.Errorf("telescope %d not found", telescopeNumber)
}

// Function to get the channel array for a given telescope number and telescope position
func getHarvesterChannel(telescopeNumber int, telescopePosition int) ([2]int, error) {
	//fmt.Println("globalState.Telescopes %v", globalState.Telescopes)
	for _, telescope := range globalState.Telescopes {
		if telescope.Telescope == telescopeNumber {
			for _, harvester := range telescope.Harvesters {
				if harvester.TelescopePosition == telescopePosition {
					return harvester.Channel, nil
				}
			}
		}
	}
	return [2]int{}, fmt.Errorf("harvester with telescope position %d not found in telescope %d", telescopePosition, telescopeNumber)
}

func getTelescopePositionFromIP(ipAddress string) (int, error) {
	for _, telescope := range globalState.Telescopes {
		for _, harvester := range telescope.Harvesters {
			if harvester.IP == ipAddress {
				return harvester.TelescopePosition, nil
			}
		}
	}
	return 0, fmt.Errorf("harvester with IP address %s not found", ipAddress)
}

func getPresentHarvesterIPArray(telescopeNumber int) ([]string, error) {
	var ips []string
	for _, telescope := range globalState.Telescopes {
		if telescope.Telescope == telescopeNumber {
			for _, harvester := range telescope.Harvesters {
				if !harvester.Missing {
					ips = append(ips, harvester.IP)
				}
			}
			return ips, nil
		}
	}
	return nil, fmt.Errorf("telescope %d not found", telescopeNumber)
}

func startHarvestersForRun(duration uint64, runNumber string, telescopes []int, sendInterval uint32) {

	defer resetStart()

	startListening := make(chan struct{})
	listeningTimer := time.NewTimer(time.Duration(duration) * time.Second)
	stopListening := make(chan struct{})
	eventBuilderChannels := make([]chan eventBuilderData, len(telescopes)) // One per telescope.
	for i := range eventBuilderChannels {
		eventBuilderChannels[i] = make(chan eventBuilderData, 100000)
	}
	guiChannel := make(chan telescopeData, 10000)

	// NEED TO CREATE CONNECTIONS HERE AND CLOSE THEM WHEN TIMER ENDS TO PREVENT HANGING.
	// MAKE SHUNT FILENAME HERE AND PASS SO THEY ALL SHARE IT.
	for i, telescope := range telescopes {
		harvesterIPs, err := getPresentHarvesterIPArray(telescope)
		if err != nil {
			log.Panic("Got error in getting harvester IP array:", err)
		}
		telescopeRunFile, runErr := createRunFile(runNumber, telescope)
		if runErr != nil {
			log.Panic("Got error in creating run file:", runErr)
		}

		for _, harvesterIP := range harvesterIPs {
			udpHarvesterConn, udpErr := establishUDPConnection(harvesterIP)
			if udpErr != nil {
				log.Panic("Got error in establishing control connection:", udpErr)
			}
			defer udpHarvesterConn.Close()

			harvesterPosition, err := getTelescopePositionFromIP(harvesterIP)
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

	udpGUIConn, udpErr := establishUDPConnectionForWrite(guiIP)
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

func allTrue(arr []bool) bool {
	for _, v := range arr {
		if !v {
			return false
		}
	}
	return true
}

func allHarvesters(arr [8]bool) bool {
	for _, v := range arr {
		if !v {
			return false
		}
	}
	return true
}

func allTelescopes(arr [4]bool) bool {
	for _, v := range arr {
		if !v {
			return false
		}
	}
	return true
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
	harvestersPresent, presentErr := getMissingHarvesters(telescope)
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
				harvestersPresent, _ = getMissingHarvesters(telescope)
				j = 0
			}
			/*if i%1000 == 0 {
				log.Printf("event builder: I haven't sent in %d events\n", i)
			}*/
			eventBuilderData = <-eventBuilderChannel
			//log.Printf("Got event from harvester %d on telescope %d\n", eventBuilderData.Source.Harvester, eventBuilderData.Source.Telescope)
			harvesterChannels, _ = getHarvesterChannel(eventBuilderData.Source.Telescope, eventBuilderData.Source.Harvester)
			//log.Printf("Harvester channels: %v\n", harvesterChannels)
			//log.Printf("harvestersPresent: %v\n", harvestersPresent)
			harvestersPresent[eventBuilderData.Source.Harvester] = true
			copy(pixelValuesPadded[harvesterChannels[0]:harvesterChannels[1]], convertByteArrayToDecimals(eventBuilderData.Data[28:308]))
			if allHarvesters(harvestersPresent) {
				//fmt.Printf("loop is at %d\n", i)
				pixelValues := extractRelevantPixels(pixelValuesPadded)
				guiData := telescopeData{Telescope: eventBuilderData.Source.Telescope, Data: pixelValues}
				guiChannel <- guiData
				fmt.Printf("Sent data to GUI\n")
				pixelValuesPadded = [560]float64{}
				harvestersPresent, _ = getMissingHarvesters(telescope)
				j = 0
			}

		}
	}

}

func guiListener(udpGUIConn *net.UDPConn, guiChannel <-chan telescopeData) {

	outGoingData := make([]byte, 8000)
	udpGUIConn.Write(outGoingData)
	telescopesPresent, presentErr := getMissingTelescopes()
	if presentErr != nil {
		log.Panic("Got error in getting missing harvesters:", presentErr)
	}

	for i := 0; ; i++ {
		thisData := <-guiChannel
		fmt.Printf("Got data from telescope %d\n", thisData.Telescope)
		thisTelescope := thisData.Telescope
		thisTelescopeOffset, offsetErr := getTelescopeSendByteOffset(thisTelescope)
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
		if allTelescopes(telescopesPresent) {
			//fmt.Printf("Sending this data to the GUI: %v\n", thisData)
			_, _ = udpGUIConn.Write(outGoingData)
			telescopesPresent, _ = getMissingTelescopes()
			// Drain/flush/clear the channel
			for len(guiChannel) > 0 {
				<-guiChannel
			}

		}
		//fmt.Printf("Got data from telescope %d\n", thisData.Telescope)
	}

}

/*func guiListener(guiConn *net.UDPConn, guiChannels []chan guiData) {

	buf := make([]byte, 308)

	for {
		n, _, _ := guiConn.ReadFromUDP(buf)
		guiChannel <- guiData{Harvester: 0, Data: buf}
	}

}*/

func getMissingHarvesters(telescopeNumber int) ([8]bool, error) {
	for _, telescope := range globalState.Telescopes {
		if telescope.Telescope == telescopeNumber {
			missingHarvesters := [8]bool{}
			for i, harvester := range telescope.Harvesters {
				missingHarvesters[i] = harvester.Missing
			}
			return missingHarvesters, nil
		}
	}
	return [8]bool{}, fmt.Errorf("telescope %d not found", telescopeNumber)
}

// Function to get a boolean array indicating missing telescopes
func getMissingTelescopes() ([4]bool, error) {
	missingTelescopes := [4]bool{}
	for i, telescope := range globalState.Telescopes {
		missingTelescopes[i] = telescope.Missing
	}
	return missingTelescopes, nil
}

func getTelescopeSendByteOffset(telescope int) (int, error) {
	if telescope == 1 {
		return 0, nil
	} else if telescope == 2 {
		return 2000, nil
	} else if telescope == 3 {
		return 4000, nil
	} else if telescope == 4 {
		return 6000, nil
	} else {
		return 0, fmt.Errorf("telescope %d not found", telescope)
	}
}

// Function to get the telescopePosition for a given IP address
func getHarvesterPositionFromIP(ipAddress string) (int, error) {
	for _, telescope := range globalState.Telescopes {
		for _, harvester := range telescope.Harvesters {
			if harvester.IP == ipAddress {
				return harvester.TelescopePosition, nil
			}
		}
	}
	return 0, fmt.Errorf("harvester with IP address %s not found", ipAddress)
}

func startHarvesterListener(udpHarvesterConn *net.UDPConn, thisHarvester harvesterID, outputFile *os.File, startListening <-chan struct{}, stopListening <-chan struct{}, sendInterval uint32, eventBuilderChannel chan<- eventBuilderData) {

	buf := make([]byte, 308)
	bufIn := [308]byte{}
	thisIP := udpHarvesterConn.LocalAddr().String()

	// Wait for calling routine to say go.
	<-startListening
	if sendInterval > 0 {
		for i := 0; ; i++ {
			select {
			case <-stopListening:
				log.Printf("Stopping harvester listener at IP %s.\nGot %d events on harvester listener\n", thisIP, i)
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
				log.Printf("Stopping harvester listener at IP %s.\nGot %d events on harvester listener\n", thisIP, i)
				return
			default:
				n, _, _ := udpHarvesterConn.ReadFromUDP(buf)
				_, _ = outputFile.Write(buf[:n])
			}
		}
	}

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

func generateRandomString(length int) (string, error) {
	// Calculate the number of bytes needed
	numBytes := length / 2

	// Generate random bytes
	randomBytes := make([]byte, numBytes)
	_, err := rand.Read(randomBytes)
	if err != nil {
		return "", err
	}

	// Convert bytes to hexadecimal string
	randomString := hex.EncodeToString(randomBytes)

	// Trim the string to the desired length
	if len(randomString) > length {
		randomString = randomString[:length]
	}

	return randomString, nil
}
