package state

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"sync"
)

//OLD BUT EQUIVALENT CODE
/*// Define the struct to hold the state of each harvester, including its IP address, channel, and pixel index
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
}*/

// Define the state structure
type SystemState struct {
	sync.RWMutex
	Telescopes []struct {
		Telescope  int
		Missing    bool
		Harvesters []struct {
			ArrayPosition int
			LocalPosition int
			Missing       bool
			IP            string
			Channel       [2]int
			PixelIndex    [2]int
		}
	}
}

// Loads the state from a JSON file and returns the state struct
func LoadStateFromFile(filename string) (*SystemState, error) {
	file, err := os.Open(filename)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	bytes, err := io.ReadAll(file)
	if err != nil {
		return nil, err
	}

	var state SystemState
	err = json.Unmarshal(bytes, &state)
	if err != nil {
		return nil, err
	}

	return &state, nil
}

func GetStateFileContents(filename string) ([]byte, error) {
	stateFileContent, err := os.ReadFile(filename)
	if err != nil {
		fmt.Println("Error reading state.json:", err)
		return nil, err
	}

	return stateFileContent, nil
}

// Prints the state for debugging
func PrintState(state *SystemState) {
	state.RLock()
	defer state.RUnlock()
	for i, telescope := range state.Telescopes {
		fmt.Printf("Telescope %d: Telescope=%d, Missing=%v\n", i+1, telescope.Telescope, telescope.Missing)
		for j, harvester := range telescope.Harvesters {
			fmt.Printf("  Harvester %d: ArrayPosition=%d, TelescopePosition=%d, Missing=%v, IP=%s, Channel=%v, PixelIndex=%v\n", j+1, harvester.ArrayPosition, harvester.LocalPosition, harvester.Missing, harvester.IP, harvester.Channel, harvester.PixelIndex)
		}
	}
}

// Gets the numbers of telescopes present
func GetTelescopesPresentInt(state *SystemState) []int {
	state.RLock()
	defer state.RUnlock()

	var telescopeNumbers []int
	for _, telescope := range state.Telescopes {
		if !telescope.Missing {
			telescopeNumbers = append(telescopeNumbers, telescope.Telescope)
		}
	}
	return telescopeNumbers
}

// Function to get a boolean array indicating missing telescopes
func GetTelescopesMissingBool(state *SystemState) ([4]bool, error) {
	state.RLock()
	defer state.RUnlock()

	missingTelescopes := [4]bool{}
	for i, telescope := range state.Telescopes {
		missingTelescopes[i] = telescope.Missing
	}
	return missingTelescopes, nil
}

func GetHarvesterLocalPositionFromIP(state *SystemState, ipAddress string) (int, error) {
	state.RLock()
	defer state.RUnlock()

	for _, telescope := range state.Telescopes {
		for _, harvester := range telescope.Harvesters {
			if harvester.IP == ipAddress {
				return harvester.LocalPosition, nil
			}
		}
	}
	return 0, fmt.Errorf("harvester with IP address %s not found", ipAddress)
}

func GetHarvesterArrayPositionFromIP(state *SystemState, ipAddress string) (int, error) {
	state.RLock()
	defer state.RUnlock()

	for _, telescope := range state.Telescopes {
		for _, harvester := range telescope.Harvesters {
			if harvester.IP == ipAddress {
				return harvester.ArrayPosition, nil
			}
		}
	}
	return 0, fmt.Errorf("harvester with IP address %s not found", ipAddress)
}

// Gets the IP of a specific harvester. Maybe I will rewrite the calling code subtract 1 from the telescope number.
func GetHarvesterIPFuture(state *SystemState, telescopeIndex int, harvesterIndex int) (string, error) {
	state.RLock()
	defer state.RUnlock()

	if telescopeIndex < 0 || telescopeIndex >= len(state.Telescopes) {
		return "", fmt.Errorf("invalid telescope index")
	}
	if harvesterIndex < 0 || harvesterIndex >= len(state.Telescopes[telescopeIndex].Harvesters) {
		return "", fmt.Errorf("invalid harvester index")
	}

	return state.Telescopes[telescopeIndex].Harvesters[harvesterIndex].IP, nil
}

// Gets the IP of a specific harvester using telescope number and harvester position
func GetHarvesterIP(state *SystemState, telescopeNumber int, harvesterPosition int) (string, error) {
	state.RLock()
	defer state.RUnlock()

	for _, telescope := range state.Telescopes {
		if telescope.Telescope == telescopeNumber {
			for _, harvester := range telescope.Harvesters {
				if harvester.LocalPosition == harvesterPosition {
					return harvester.IP, nil
				}
			}
		}
	}
	return "", fmt.Errorf("harvester with telescope position %d not found in telescope %d", harvesterPosition, telescopeNumber)
}

// Function to get the channel array for a given telescope number and harvester position
func GetHarvesterChannel(state *SystemState, telescopeNumber int, harvesterPosition int) ([2]int, error) {
	state.RLock()
	defer state.RUnlock()

	for _, telescope := range state.Telescopes {
		if telescope.Telescope == telescopeNumber {
			for _, harvester := range telescope.Harvesters {
				if harvester.LocalPosition == harvesterPosition {
					return harvester.Channel, nil
				}
			}
		}
	}
	return [2]int{}, fmt.Errorf("harvester with telescope position %d not found in telescope %d", harvesterPosition, telescopeNumber)
}

func GetHarvestersPresentIPs(state *SystemState, telescopeNumber int) ([]string, error) {
	state.RLock()
	defer state.RUnlock()

	var ips []string
	for _, telescope := range state.Telescopes {
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

// Function to get the local positions of present harvesters for a given telescope number
func GetHarvestersPresentInt(state *SystemState, telescopeNumber int) ([]int, error) {
	state.RLock()
	defer state.RUnlock()

	var positions []int
	for _, telescope := range state.Telescopes {
		if telescope.Telescope == telescopeNumber {
			for _, harvester := range telescope.Harvesters {
				if !harvester.Missing {
					positions = append(positions, harvester.LocalPosition)
				}
			}
			return positions, nil
		}
	}
	return nil, fmt.Errorf("telescope %d not found", telescopeNumber)
}

func GetHarvestersMissingBool(state *SystemState, telescopeNumber int) ([8]bool, error) {
	state.RLock()
	defer state.RUnlock()

	for _, telescope := range state.Telescopes {
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

func AllHarvesters(arr [8]bool) bool {
	for _, v := range arr {
		if !v {
			return false
		}
	}
	return true
}

func AllTelescopes(arr [4]bool) bool {
	for _, v := range arr {
		if !v {
			return false
		}
	}
	return true
}

func AllTrue(arr []bool) bool {
	for _, v := range arr {
		if !v {
			return false
		}
	}
	return true
}
