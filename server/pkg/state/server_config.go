package state

import (
	"encoding/json"
	"io"
	"os"
)

type Config struct {
	ServerControlConnIP string `json:"serverControlConnIP"`
	GuiDataConnIP       string `json:"guiDataConnIP"`
	GuiHeartbeatConnIP  string `json:"guiHeartbeatConnIP"`
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
