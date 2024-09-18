package ioutils

import (
	"crypto/rand"
	"encoding/hex"
	"log"
	"os"
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

// createRunFile is a function that creates a run file for a given run number and telescope.
// It takes the run number as a string and the telescope number as an integer.
// The function returns a pointer to the created file and an error, if any.
// If the file already exists, it appends a random string to the file name and creates a new file.
// If there is an error creating the output file, it panics with the error message.
func CreateRunFile(dataSaveDir string, runNumber string, telescope int) (*os.File, error) {
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
