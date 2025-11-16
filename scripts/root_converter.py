import struct
import ROOT
from ROOT import TFile, TTree
import sys
from array import array
import argparse

def convert_to_decimal(word):
    # Extract the integer part (first 16 bits)
    integer_part = word >> 16

    # Extract the fractional part (last 16 bits)
    fractional_part = word & 0xFFFF

    # Convert the fractional part to decimal
    fractional_decimal = 0.0
    for i in range(16):
        if fractional_part & (1 << (15 - i)):
            fractional_decimal += 2 ** (-1 - i)

    # Combine the integer and fractional parts
    return integer_part + fractional_decimal

def extract_data(event):
    # Offsets for the required data
    number_offset = 0
    timestamp_seconds_offset = 4
    timestamp_nanoseconds_offset = 8
    extra_reg_offset = 12
    window_size_offset = 18
    ch_mask_offset = 20
    variance_offset = 0x1c

    # Extract the 32-bit number (4 bytes) at offset 0
    number = struct.unpack_from('>I', event, number_offset)[0]

    # Extract the UNIX timestamp seconds (4 bytes) at offset 4
    timestamp_seconds = struct.unpack_from('>I', event, timestamp_seconds_offset)[0]

    # Extract the UNIX nanosecond timestamp (4 bytes) at offset 8
    timestamp_nanoseconds = struct.unpack_from('>I', event, timestamp_nanoseconds_offset)[0]

    # Combine the seconds and nanoseconds to form a complete timestamp
    timestamp = timestamp_seconds + timestamp_nanoseconds * 1e-9

    # Extract the extra registers (6 bytes) at offset 12
    extra_reg1 = struct.unpack_from('>H', event, extra_reg_offset)[0]
    extra_reg2 = struct.unpack_from('>H', event, extra_reg_offset + 2)[0]
    extra_reg3 = struct.unpack_from('>H', event, extra_reg_offset + 4)[0]

    # Extract the window size (3 bits) and part of the channel mask (13 bits) at offset 18
    window_size_and_mask = struct.unpack_from('>H', event, window_size_offset)[0]
    window_size = window_size_and_mask >> 13
    ch_mask_high = window_size_and_mask & 0x3F

    # Extract the 64-bit channel mask at offset 20
    ch_mask_low = struct.unpack_from('>Q', event, ch_mask_offset)[0]

    # Combine the 6 bits with the 64-bit number to form the full channel mask
    ch_mask = (ch_mask_high << 64) | ch_mask_low

    # Extract the variances (280 bytes) starting at offset 28
    variances = []
    for i in range(70):
        variance_word = struct.unpack_from('>I', event, variance_offset + i * 4)[0]
        variances.append(convert_to_decimal(variance_word))

    # Convert ch_mask to a 70-element array of bits
    ch_mask_bits = [(ch_mask >> i) & 1 for i in range(69, -1, -1)]

    return {
        'number': number,
        'timestamp': timestamp,
        'extra_reg1': extra_reg1,
        'extra_reg2': extra_reg2,
        'extra_reg3': extra_reg3,
        'window_size': window_size,
        'ch_mask_bits': ch_mask_bits,
        'variances': variances
    }

def read_events_from_file(input_filename, event_size=308):
    try:
        with open(input_filename, 'rb') as file:
            while True:
                event = file.read(event_size)
                if len(event) < event_size:
                    break  # End of file or incomplete event
                yield event
    except IOError as e:
        print(f"Error reading file {input_filename}: {e}")
        sys.exit(1)

def process_file_to_root(input_filename, output_filename):
    # Create a ROOT file and a TTree to store the data
    root_file = TFile(output_filename, 'RECREATE')
    tree = TTree('event_tree', 'Event Data Tree')

    # Define branches
    number = array('I', [0])
    timestamp = array('d', [0.0])
    extra_reg1 = array('H', [0])
    extra_reg2 = array('H', [0])
    extra_reg3 = array('H', [0])
    window_size = array('H', [0])
    ch_mask_bits = array('B', [0] * 70)
    variances = array('d', [0.0] * 70)

    tree.Branch('number', number, 'number/i')
    tree.Branch('timestamp', timestamp, 'timestamp/D')
    tree.Branch('extra_reg1', extra_reg1, 'extra_reg1/s')
    tree.Branch('extra_reg2', extra_reg2, 'extra_reg2/s')
    tree.Branch('extra_reg3', extra_reg3, 'extra_reg3/s')
    tree.Branch('window_size', window_size, 'window_size/s')
    tree.Branch('ch_mask_bits', ch_mask_bits, 'ch_mask_bits[70]/b')
    tree.Branch('variances', variances, 'variances[70]/D')

    # Read and process the binary file
    for event in read_events_from_file(input_filename):
        data = extract_data(event)

        # Fill branch data
        number[0] = data['number']
        timestamp[0] = data['timestamp']
        extra_reg1[0] = data['extra_reg1']
        extra_reg2[0] = data['extra_reg2']
        extra_reg3[0] = data['extra_reg3']
        window_size[0] = data['window_size']
        for i in range(70):
            ch_mask_bits[i] = data['ch_mask_bits'][i]
            variances[i] = data['variances'][i]

        # Fill the tree with the current event
        tree.Fill()

    # Write the ROOT file
    root_file.Write()
    root_file.Close()

def open_root_file(filename):
    try:
        root_file = TFile(filename, 'READ')
        return root_file
    except IOError as e:
        print(f"Error opening ROOT file {filename}: {e}")
        sys.exit(1)

def read_root_tree(root_file, tree_name='event_tree'):
    tree = root_file.Get(tree_name)
    if not tree:
        print(f"Error: Tree '{tree_name}' not found in ROOT file.")
        sys.exit(1)
    return tree

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process binary event data into a ROOT file.')
    parser.add_argument('input_filename', type=str, help='Path to the input binary file')
    parser.add_argument('output_filename', type=str, help='Path to the output ROOT file')
    args = parser.parse_args()

    process_file_to_root(args.input_filename, args.output_filename)
