package state

import (
	"encoding/json"
	"io"
	"os"
)

type Config struct {
	ControlConnIP string `json:"controlConnIP"`
	GuiIP         string `json:"guiIP"`
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
