package state

import (
	"encoding/json"
	"io"
	"os"
)

type Status struct {
	Started        int `json:"started"`
	Aborted        int `json:"aborted"`
	Ended          int `json:"ended"`
	Ended_manually int `json:"ended_manually"`
}

type Commands struct {
	Nothing                int `json:"nothing"`
	StartRunCmd            int `json:"startRunCmd"`
	ContinousRunCmd        int `json:"continousRunCmd"`
	ExitCmd                int `json:"exitCmd"`
	TestCmd                int `json:"testCmd"`
	StartDataForwardingCmd int `json:"startDataForwardingCmd"`
	StopDataForwardingCmd  int `json:"stopDataForwardingCmd"`
	HearbeatCmd            int `json:"hearbeatCmd"`
	StopRunCmd             int `json:"stopRunCmd"`
	HarvesterCmd           int `json:"harvesterCmd"`
}

// Run file layouts, chosen by the "runFileLayout" key in server.json.
const (
	// One <run>_<tel>.bin per telescope, every harvester of that telescope
	// interleaved into it. Only separable offline if the payload identifies
	// the board. This is the layout used up to 2026-11.
	RunFilePerTelescope = "perTelescope"
	// One <run>_<tel>_h<localPosition>.bin per harvester.
	RunFilePerHarvester = "perHarvester"
)

type Config struct {
	ServerControlConnIP    string   `json:"serverControlConnIP"`
	GuiDataConnIP          string   `json:"guiDataConnIP"`
	GuiHeartbeatConnIP     string   `json:"guiHeartbeatConnIP"`
	GuiStatusConnIP        string   `json:"guiStatusConnIP"`
	HarvesterControlConnIP string   `json:"harvesterControlConnIP"`
	DataSavePath           string   `json:"dataSavePath"`
	SendInterval           int      `json:"sendInterval"`
	RunFileLayout          string   `json:"runFileLayout"`
	Commands               Commands `json:"commands"`
	Status                 Status   `json:"status"`
}

func LoadConfig(filename string) (*Config, error) {
	file, err := os.Open(filename)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	bytes, err := io.ReadAll(file)
	if err != nil {
		return nil, err
	}

	var config Config
	if err := json.Unmarshal(bytes, &config); err != nil {
		return nil, err
	}

	return &config, nil
}
