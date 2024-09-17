package data_parsing

import (
	"encoding/binary"
	"fmt"
	"math"
)

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
