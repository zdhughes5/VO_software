package main

import (
	"encoding/binary"
	"encoding/json"
	"errors"
	"io"
	"log"
	"math"
	"net"
	"os"
	"server/pkg/data_parsing"
	"server/pkg/ioutils"
	"server/pkg/netutils"
	"server/pkg/state"

	//"os/exec"
	"strconv"
	"sync"
	"sync/atomic"
	"time"
)

var extractEventNumber = data_parsing.ParseDWord0

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
	hearbeatCmd
	// Add more enum values here
)

// To send and event to the GUI we need:
// 8 UDP packets of the same event from 1 telescope.
// func extractBlockNumber()
// func extractEventNumber()

// Declare the global variable
var ErrChannelAlreadyClosed = errors.New("channel already closed")
var globalState state.SystemState

// runActive is written by the control loop (on start) and by the run goroutine
// (on exit), so it must be atomic.
var runActive atomic.Bool
var configFileName string = "../internal/server.json"
var config state.Config

func safeClose(ch chan struct{}) (thing error) {
	log.Println("Closing channel")
	thing = nil
	defer func() {
		if r := recover(); r != nil {
			log.Printf("Recovered from panic: %v", r)
			log.Printf("Error: %v", thing)
			thing = ErrChannelAlreadyClosed
			log.Printf("Post Error: %v", thing)
		}
	}()
	close(ch)
	return thing
}

func UNUSED(x ...interface{}) {}

func main() {

	/*pwd, err := os.Getwd()
	if err != nil {
		fmt.Println(err)
		os.Exit(1)
	}
	fmt.Println(pwd)*/

	/////////////////// Start Logger //////////

	logFile, err := os.OpenFile("../log/server.log", os.O_CREATE|os.O_APPEND|os.O_RDWR, 0666)
	if err != nil {
		panic(err)
	}
	mw := io.MultiWriter(os.Stdout, logFile)
	log.SetOutput(mw)
	//log.SetOutput(logFile)
	log.Println("Server started.")

	///////////////////////////////////////////

	//////////////// Load Config //////////////

	pConfig, err := state.LoadConfig(configFileName)
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}
	config = *pConfig
	//log.Printf("Loaded config: %+v", config)

	///////////////////////////////////////////

	////////// Establish Connections //////////

	// For receiving commands to this server.
	udpControlConn, err := netutils.EstablishUDPConnection(config.ServerControlConnIP)
	if err != nil {
		log.Panic("Got error in establishing control connection:", err)
	}
	defer udpControlConn.Close()

	///////////////////////////////////////////

	udpHeartbeatConn, err := netutils.EstablishUDPConnectionForWrite(config.GuiHeartbeatConnIP)
	if err != nil {
		log.Panic("Got error in establishing heartbeat connection:", err)
	}
	defer udpHeartbeatConn.Close()

	udpStatusConn, err := netutils.EstablishUDPConnectionForWrite(config.GuiStatusConnIP)
	if err != nil {
		log.Panic("Got error in establishing status connection:", err)
	}
	defer udpStatusConn.Close()

	ctrlBuf := make([]byte, 8000)
	var cmd int

	stopForwarding := make(chan struct{})

	// One buffered stop channel per run. Buffered so that a stop arriving
	// before the run goroutine reaches its select is still seen, rather than
	// being lost the way a Stop()/Reset() on a shared timer could be.
	var stopRun chan struct{}

	for {

		n, addr, err := udpControlConn.ReadFromUDP(ctrlBuf)
		if err != nil {
			log.Println("Error in reading packet from control connection:", err)
			continue
		}
		if n > 20 {
			log.Printf("Got %d bytes from UDP control packet from address %v \n", n, addr)
		}
		// A fresh map each time: unmarshalling into a reused map merges, so
		// keys from an earlier command would leak into this one.
		receivedMap := map[string]interface{}{}
		err = json.Unmarshal(ctrlBuf[:n], &receivedMap)
		if err != nil {
			log.Printf("Ignoring control packet from %v, bad JSON: %v", addr, err)
			continue
		}

		cmdFloat, ok := receivedMap["command"].(float64)
		if !ok {
			log.Printf("Ignoring control packet from %v, no numeric \"command\" field", addr)
			continue
		}
		cmd = int(cmdFloat)

		switch cmd {
		case config.Commands.StartRunCmd:
			// Check before touching globalState: a start that arrives during a
			// run must not replace the state the running goroutines read.
			if runActive.Load() {
				log.Println("Data run already running; ignoring start.")
				break
			}

			runDuration, ok1 := receivedMap["duration"].(float64)
			runNumber, ok2 := receivedMap["runNumber"].(float64)
			sendInterval, ok3 := receivedMap["sendInterval"].(float64)
			dataSaveDir, ok4 := receivedMap["dataSaveDir"].(string)
			if !(ok1 && ok2 && ok3 && ok4) || runDuration < 0 || runNumber < 0 || sendInterval < 0 {
				log.Println("Ignoring start: duration, runNumber, sendInterval and dataSaveDir must all be present and non-negative.")
				_ = netutils.SendStatusCode(udpStatusConn, config.Status.Aborted)
				break
			}
			runNumberString := strconv.FormatUint(uint64(runNumber), 10)

			if stateContent, ok := receivedMap["state"].(string); ok {
				var newState state.SystemState
				if err := json.Unmarshal([]byte(stateContent), &newState); err != nil {
					log.Printf("Ignoring start, bad state content: %v", err)
					_ = netutils.SendStatusCode(udpStatusConn, config.Status.Aborted)
					break
				}
				globalState.Lock()
				globalState.Telescopes = newState.Telescopes
				globalState.Unlock()
				log.Printf("Successfully loaded state from state.json")
			}

			runActive.Store(true)
			stopRun = make(chan struct{}, 1)
			log.Println("Starting data logging...")
			go startHarvestersForRun(uint64(runDuration), runNumberString, uint32(sendInterval), dataSaveDir, udpStatusConn, stopRun)

		case config.Commands.StopRunCmd:
			if runActive.Load() && stopRun != nil {
				log.Println("StopRunCmd: Stopping data logging...")
				select {
				case stopRun <- struct{}{}:
				default: // A stop is already pending.
				}
			} else {
				log.Println("StopRunCmd: No run to stop.")
			}

			/*log.Println("StopRunCmd: Hola!")
			if !runReady {
				log.Println("StopRunCmd: Stopping data logging...")
				err := safeClose(stopListening)
				log.Println("Got this error:", err)
				if err != nil {
					log.Println("StopRunCmd: Channel already closed.")
				} else {
					netutils.SendStatusCode(udpStatusConn, config.Status.Ended_manually)
				}
			} else {
				log.Println("StopRunCmd: No run to stop.")
			}*/

		case config.Commands.StartDataForwardingCmd:
			listenIP, ok1 := receivedMap["listenIP"].(string)
			forwardIP, ok2 := receivedMap["forwardIP"].(string)
			if !(ok1 && ok2) {
				log.Println("Ignoring start data forwarding: listenIP and forwardIP are required.")
				break
			}
			log.Printf("Got start data forwarding command with listen IP %s and forward IP %s:", listenIP, forwardIP)
			go netutils.StartDataForwarding(listenIP, forwardIP, stopForwarding)

		case config.Commands.StopDataForwardingCmd:
			// Non-blocking: with no forwarder running, a plain send would
			// block this loop forever and the heartbeat would stop.
			select {
			case stopForwarding <- struct{}{}:
				log.Println("Stopping data forwarding...")
			default:
				log.Println("No data forwarding to stop.")
			}

		case config.Commands.ExitCmd:
			log.Println("Exiting server...")
			return
		case config.Commands.TestCmd:
			log.Println("Got Test!!")
		case config.Commands.HearbeatCmd:
			//fmt.Println("Got Heartbeat!!")
			_, _ = udpHeartbeatConn.Write([]byte("Heartbeat"))
		default:
			log.Println("What!?")

		}

	}
}

// harvesterSetup is everything one harvester listener needs, gathered before
// any goroutine starts so that a setup failure can be undone cleanly.
type harvesterSetup struct {
	conn    *net.UDPConn
	id      harvesterID
	file    *os.File
	builder chan eventBuilderData
}

// startHarvestersForRun runs one data run from setup to teardown. Setup errors
// used to log.Panic, which in a goroutine kills the whole server; now they
// abort only this run and report status Aborted to the GUI.
func startHarvestersForRun(duration uint64, runNumber string, sendInterval uint32, dataSaveDir string, udpStatusConn *net.UDPConn, stopRun <-chan struct{}) {

	defer runActive.Store(false)

	var conns []*net.UDPConn
	var files []*os.File
	closeConns := func() {
		for _, c := range conns {
			c.Close()
		}
	}
	closeFiles := func() {
		for _, f := range files {
			f.Close()
		}
	}
	abort := func(format string, args ...interface{}) {
		log.Printf("Run %s aborted during setup: "+format, append([]interface{}{runNumber}, args...)...)
		closeConns()
		closeFiles()
		_ = netutils.SendStatusCode(udpStatusConn, config.Status.Aborted)
	}

	telescopes := state.GetTelescopesPresentInt(&globalState)
	eventBuilderChannels := make([]chan eventBuilderData, len(telescopes)) // One per telescope.
	for i := range eventBuilderChannels {
		eventBuilderChannels[i] = make(chan eventBuilderData, 100000)
	}
	guiChannel := make(chan telescopeData, 10000)

	var harvesters []harvesterSetup
	for i, telescope := range telescopes {
		if telescope < 1 || telescope > 4 {
			abort("telescope number %d is outside 1-4", telescope)
			return
		}
		harvesterIPs, err := state.GetHarvestersPresentIPs(&globalState, telescope)
		if err != nil {
			abort("getting harvester IPs: %v", err)
			return
		}
		telescopeRunFile, runErr := ioutils.CreateRunFile(dataSaveDir, runNumber, telescope)
		if runErr != nil {
			abort("creating run file: %v", runErr)
			return
		}
		files = append(files, telescopeRunFile)

		for _, harvesterIP := range harvesterIPs {
			harvesterPosition, err := state.GetHarvesterLocalPositionFromIP(&globalState, harvesterIP)
			if err != nil {
				abort("getting harvester position: %v", err)
				return
			}
			// The event builder indexes an [8]bool with this and slices a
			// [560] array with the channel range; bad values would panic there.
			if harvesterPosition < 0 || harvesterPosition > 7 {
				abort("harvester %s has localPosition %d, outside 0-7", harvesterIP, harvesterPosition)
				return
			}
			channels, err := state.GetHarvesterChannel(&globalState, telescope, harvesterPosition)
			if err != nil || channels[0] < 0 || channels[1] > 560 || channels[0] > channels[1] {
				abort("harvester %s has bad channel range %v (%v)", harvesterIP, channels, err)
				return
			}

			udpHarvesterConn, udpErr := netutils.EstablishUDPConnection(harvesterIP)
			if udpErr != nil {
				abort("listening on harvester %s: %v", harvesterIP, udpErr)
				return
			}
			conns = append(conns, udpHarvesterConn)

			harvesters = append(harvesters, harvesterSetup{
				conn:    udpHarvesterConn,
				id:      harvesterID{Harvester: harvesterPosition, Telescope: telescope},
				file:    telescopeRunFile,
				builder: eventBuilderChannels[i],
			})
		}
	}

	udpGUIConn, udpErr := netutils.EstablishUDPConnectionForWrite(config.GuiDataConnIP)
	if udpErr != nil {
		abort("establishing GUI connection: %v", udpErr)
		return
	}
	conns = append(conns, udpGUIConn)

	// Setup succeeded; only now start goroutines.
	startListening := make(chan struct{})
	stopListening := make(chan struct{})
	var listeners sync.WaitGroup
	for _, h := range harvesters {
		listeners.Add(1)
		go func(h harvesterSetup) {
			defer listeners.Done()
			startHarvesterListener(h.conn, h.id, h.file, startListening, stopListening, sendInterval, h.builder)
		}(h)
	}
	if sendInterval > 0 {
		for i, telescope := range telescopes {
			go eventBuilder(eventBuilderChannels[i], guiChannel, startListening, stopListening, telescope)
		}
	}
	go guiListener(udpGUIConn, guiChannel, stopListening)
	time.Sleep(1 * time.Millisecond)
	close(startListening)

	_ = netutils.SendStatusCode(udpStatusConn, config.Status.Started)

	runTimer := time.NewTimer(time.Duration(duration) * time.Second)
	manualEnd := false
	select {
	case <-runTimer.C:
	case <-stopRun:
		runTimer.Stop()
		manualEnd = true
	}

	close(stopListening)
	// Closing the sockets unblocks listeners sitting in ReadFromUDP; wait for
	// them before closing the files they write to.
	closeConns()
	listeners.Wait()
	closeFiles()

	if !manualEnd {
		_ = netutils.SendStatusCode(udpStatusConn, config.Status.Ended)
	} else {
		_ = netutils.SendStatusCode(udpStatusConn, config.Status.Ended_manually)
	}

	log.Println("Data logging ended.")

}

func eventBuilder(eventBuilderChannel <-chan eventBuilderData, guiChannel chan<- telescopeData, startListening <-chan struct{}, stopListening <-chan struct{}, telescope int) {

	//log.Printf("Starting event builder for telescope %d\n", telescope)
	pixelValuesPadded := [560]float64{} // This has 60 empty channels spread throughout the array.
	harvesterChannels := [2]int{0, 0}
	harvestersPresent, presentErr := state.GetHarvestersMissingBool(&globalState, telescope)
	if presentErr != nil {
		log.Printf("Event builder for telescope %d not started: %v", telescope, presentErr)
		return
	}

	// Wait for calling routine to say go.
	j := 0
	i := 0
	select {
	case <-startListening:
	case <-stopListening:
		return
	}
	for {
		// The receive sits in the select so that stopListening is seen even
		// when no data is arriving; otherwise this goroutine leaked every run.
		var eventBuilderData eventBuilderData
		select {
		case <-stopListening:
			log.Printf("Stopping event builder for telescope %d.\nGot %d events on event builder\n", telescope, i)
			return
		case eventBuilderData = <-eventBuilderChannel:
		}
		i++
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
		harvesterChannels, _ = state.GetHarvesterChannel(&globalState, eventBuilderData.Source.Telescope, eventBuilderData.Source.Harvester)
		harvestersPresent[eventBuilderData.Source.Harvester] = true
		copy(pixelValuesPadded[harvesterChannels[0]:harvesterChannels[1]], data_parsing.ConvertByteArrayToDecimals(eventBuilderData.Data[28:308]))
		if state.AllHarvesters(harvestersPresent) {
			pixelValues := data_parsing.ExtractRelevantPixels(pixelValuesPadded)
			guiData := telescopeData{Telescope: eventBuilderData.Source.Telescope, Data: pixelValues}
			select {
			case guiChannel <- guiData:
			case <-stopListening:
				return
			}
			pixelValuesPadded = [560]float64{}
			harvestersPresent, _ = state.GetHarvestersMissingBool(&globalState, telescope)
			j = 0
		}
	}

}

func guiListener(udpGUIConn *net.UDPConn, guiChannel <-chan telescopeData, stopListening <-chan struct{}) {

	outGoingData := make([]byte, 8000)
	udpGUIConn.Write(outGoingData)
	telescopesPresent, _ := state.GetTelescopesMissingBool(&globalState)

	for {
		var thisData telescopeData
		select {
		case <-stopListening:
			return
		case thisData = <-guiChannel:
		}
		thisTelescope := thisData.Telescope
		thisTelescopeOffset, offsetErr := data_parsing.GetTelescopeSendByteOffset(thisTelescope)
		if offsetErr != nil {
			// Telescope numbers are checked in run setup, so this is not
			// expected; drop the fragment rather than kill the server.
			log.Printf("Dropping GUI data for telescope %d: %v", thisTelescope, offsetErr)
			continue
		}
		offset := 0
		for _, pixelValue := range thisData.Data {
			binary.LittleEndian.PutUint32(outGoingData[thisTelescopeOffset+offset:], math.Float32bits(float32(pixelValue)))
			offset += 4
		}
		telescopesPresent[thisTelescope-1] = true
		if state.AllTelescopes(telescopesPresent) {
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
	select {
	case <-startListening:
	case <-stopListening:
		return
	}
	for i := 0; ; i++ {
		select {
		case <-stopListening:
			log.Printf("Stopping harvester listener at IP %s.\nGot %d events on harvester %v listener\n", thisIP, i, arrayPosition)
			return
		default:
			n, _, err := udpHarvesterConn.ReadFromUDP(buf)
			if err != nil {
				// Normally the socket being closed at the end of the run;
				// the select above then sees stopListening.
				continue
			}
			_, _ = outputFile.Write(buf[:n])
			if sendInterval > 0 && extractEventNumber(buf, true)%sendInterval == 0 { // Maybe change this to just i%sendInterval
				copy(bufIn[:], buf[:308])
				select {
				case eventBuilderChannel <- eventBuilderData{Source: thisHarvester, Data: bufIn}:
				case <-stopListening:
				}
			}
		}
	}

}
