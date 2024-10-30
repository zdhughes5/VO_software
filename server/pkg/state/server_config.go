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
}

type Config struct {
	ServerControlConnIP string   `json:"serverControlConnIP"`
	GuiDataConnIP       string   `json:"guiDataConnIP"`
	GuiHeartbeatConnIP  string   `json:"guiHeartbeatConnIP"`
	GuiStatusConnIP     string   `json:"guiStatusConnIP"`
	DataSavePath        string   `json:"dataSavePath"`
	SendInterval        int      `json:"sendInterval"`
	Commands            Commands `json:"commands"`
	Status              Status   `json:"status"`
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
