package ioutils

import (
	"crypto/rand"
	"encoding/hex"
	"log"
	"os"
	"path/filepath"
	"strconv"
)

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

// createUniqueFile creates <dataSaveDir>/<baseName>.bin. It never overwrites:
// if that file exists it logs a warning and creates
// <dataSaveDir>/<baseName>_<random hex>.bin instead.
//
// The directory is joined with filepath.Join, so dataSaveDir works with or
// without a trailing slash (plain concatenation used to turn
// "/data" + "123_1.bin" into "/data123_1.bin").
//
// If the output file cannot be created, the error is returned (it used to
// panic, which from the run goroutine took the whole server down).
func createUniqueFile(dataSaveDir string, baseName string) (*os.File, error) {
	outputFileName := filepath.Join(dataSaveDir, baseName+".bin")

	if _, existsErr := os.Stat(outputFileName); os.IsNotExist(existsErr) {
		outputFile, createErr := os.Create(outputFileName)
		if createErr != nil {
			return nil, createErr
		}
		log.Println("Saving data to:", outputFileName)
		return outputFile, nil
	}

	randomString, _ := generateRandomString(16)
	log.Println("File already exists:", outputFileName, "Check your run number!")
	outputFileName = filepath.Join(dataSaveDir, baseName+"_"+randomString+".bin")
	log.Println("Shunting data to:", outputFileName)
	outputFile, createErr := os.Create(outputFileName)
	if createErr != nil {
		return nil, createErr
	}
	return outputFile, nil
}

// CreateRunFile creates the per-telescope run file <run>_<telescope>.bin,
// which every harvester of the telescope writes into (runFileLayout
// "perTelescope").
func CreateRunFile(dataSaveDir string, runNumber string, telescope int) (*os.File, error) {
	return createUniqueFile(dataSaveDir, runNumber+"_"+strconv.Itoa(telescope))
}

// CreateHarvesterRunFile creates the per-harvester run file
// <run>_<telescope>_h<localPosition>.bin (runFileLayout "perHarvester").
// The records are the same 308-byte packets as in CreateRunFile's files,
// just one board per file, so the offline scripts read either.
func CreateHarvesterRunFile(dataSaveDir string, runNumber string, telescope int, localPosition int) (*os.File, error) {
	return createUniqueFile(dataSaveDir, runNumber+"_"+strconv.Itoa(telescope)+"_h"+strconv.Itoa(localPosition))
}
