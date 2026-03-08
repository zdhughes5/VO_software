import struct
import matplotlib.pyplot as plt
import numpy as np

def read_passthrough_binary_file_in_chunks(filename, chunk_size=588):
    with open(filename, 'rb') as file:
        while True:
            chunk = file.read(chunk_size)
            if len(chunk) < chunk_size:
                break  # End of file or incomplete chunk
            yield chunk

def extract_passthrough_data_from_chunk(chunk):
    # Offsets for the required data
    number_offset = 0
    timestamp_seconds_offset = 4
    timestamp_nanoseconds_offset = 8
    extra_reg_offset = 12
    window_size_offset = 18
    ch_mask_bits_offset = 20
    variance_offset = 0x1c

    # Extract the 32-bit number (4 bytes) at offset 0
    number = struct.unpack_from('>I', chunk, number_offset)[0]

    # Extract the UNIX timestamp seconds (4 bytes) at offset 4
    timestamp_seconds = struct.unpack_from('>I', chunk, timestamp_seconds_offset)[0]

    # Extract the UNIX nanosecond timestamp (4 bytes) at offset 8
    timestamp_nanoseconds = struct.unpack_from('>I', chunk, timestamp_nanoseconds_offset)[0]

    # Combine the seconds and nanoseconds to form a complete timestamp
    timestamp = timestamp_seconds + timestamp_nanoseconds * 1e-9

    # Extract the extra registers (6 bytes) at offset 12
    extra_reg1 = struct.unpack_from('>H', chunk, extra_reg_offset)[0]
    extra_reg2 = struct.unpack_from('>H', chunk, extra_reg_offset + 2)[0]
    extra_reg3 = struct.unpack_from('>H', chunk, extra_reg_offset + 4)[0]

    # Extract the window size (3 bits) and part of the channel mask (13 bits) at offset 18
    window_size_and_mask = struct.unpack_from('>H', chunk, window_size_offset)[0]
    window_size = window_size_and_mask >> 13
    ch_mask_bits_high = window_size_and_mask & 0x3F

    # Extract the 64-bit channel mask at offset 20
    ch_mask_bits_low = struct.unpack_from('>Q', chunk, ch_mask_bits_offset)[0]

    # Combine the 6 bits with the 64-bit number to form the full channel mask
    ch_mask_bits = (ch_mask_bits_high << 64) | ch_mask_bits_low

    # Extract the sum and sum-of-squared-samples (560 bytes) starting at offset 28
    # Each channel: 8 bytes (2 dwords)
    # dword 1: sum[26:11] (16 bits) | {sum[10:0] (11 bits), 2'b00, sum_sq[34:32] (3 bits)}
    # dword 2: sum_sq[31:0] (32 bits)
    sums = []
    sums_sq = []
    data_offset = 0x1c
    
    for i in range(70):
        # Read 8 bytes for this channel
        offset = data_offset + i * 8
        
        # First dword (4 bytes)
        dword1 = struct.unpack_from('>I', chunk, offset)[0]
        
        # Second dword (4 bytes)
        dword2 = struct.unpack_from('>I', chunk, offset + 4)[0]
        
        # Extract sum (27 bits total)
        # Upper 16 bits: sum[26:11] from dword1[31:16]
        sum_upper = (dword1 >> 16) & 0xFFFF
        # Lower 11 bits: sum[10:0] from dword1[15:5]
        sum_lower = (dword1 >> 5) & 0x7FF
        sum_value = (sum_upper << 11) | sum_lower
        
        # Extract sum_sq (35 bits total)
        # Upper 3 bits: sum_sq[34:32] from dword1[2:0]
        sum_sq_upper = dword1 & 0x7
        # Lower 32 bits: sum_sq[31:0] from dword2
        sum_sq_lower = dword2
        sum_sq_value = (sum_sq_upper << 32) | sum_sq_lower
        
        sums.append(sum_value)
        sums_sq.append(sum_sq_value)

    return {
        'number': number,
        'timestamp': timestamp,
        'extra_reg1': extra_reg1,
        'extra_reg2': extra_reg2,
        'extra_reg3': extra_reg3,
        'window_size': window_size,
        'ch_mask_bits': ch_mask_bits,
        'sums': sums,
        'sums_sq': sums_sq
    }


WINDOW_SIZE = 499968

def main(filename, channel):
    """Parse binary file and plot sum, sum-of-squared-samples, and variance vs timestamp for a specific channel"""
    timestamps = []
    event_numbers = []
    all_sums = []
    all_sums_sq = []
    
    print(f"Parsing {filename}...")
    
    for chunk in read_passthrough_binary_file_in_chunks(filename):
        data = extract_passthrough_data_from_chunk(chunk)
        timestamps.append(data['timestamp'])
        event_numbers.append(data['number'])
        all_sums.append(data['sums'])
        all_sums_sq.append(data['sums_sq'])
    
    print(f"Parsed {len(timestamps)} events")
    
    # Convert to numpy arrays for easier manipulation
    timestamps = np.array(timestamps)
    event_numbers = np.array(event_numbers)
    all_sums = np.array(all_sums)  # Shape: (n_events, 70)
    all_sums_sq = np.array(all_sums_sq)  # Shape: (n_events, 70)
    
    # Calculate software variances: var = (sum_sq / N) - (sum / N)^2
    all_variances = (all_sums_sq / WINDOW_SIZE) - (all_sums / WINDOW_SIZE) ** 2  # Shape: (n_events, 70)
    
    # Create time relative to first event
    rel_time = timestamps - timestamps[0]
    
    # Plot sum, sum_sq, and variance for the specified channel
    fig, axes = plt.subplots(3, 1, figsize=(12, 14), sharex=True)
    
    # Plot sum for the specified channel
    axes[0].plot(rel_time, all_sums[:, channel], linewidth=1.5, color='blue')
    axes[0].set_ylabel('Sum of Samples')
    axes[0].set_title(f'Sum of Samples vs Time (Channel {channel})')
    axes[0].grid(True, alpha=0.3)
    
    # Plot sum_sq for the specified channel
    axes[1].plot(rel_time, all_sums_sq[:, channel], linewidth=1.5, color='red')
    axes[1].set_ylabel('Sum of Squared Samples')
    axes[1].set_title(f'Sum of Squared Samples vs Time (Channel {channel})')
    axes[1].grid(True, alpha=0.3)
    
    # Plot software-calculated variance for the specified channel
    axes[2].plot(rel_time, all_variances[:, channel], linewidth=1.5, color='green')
    axes[2].set_xlabel('Time relative to first event (s)')
    axes[2].set_ylabel('Variance')
    axes[2].set_title(f'Software-Calculated Variance vs Time (Channel {channel}, N={WINDOW_SIZE})')
    axes[2].grid(True, alpha=0.3)
    
    plt.tight_layout()
    output_filename = f'passthrough_analysis_ch{channel}.png'
    plt.savefig(output_filename, dpi=150)
    print(f"Saved: {output_filename}")
    plt.show()
    
    # Check for discontinuities (large jumps between consecutive events)
    print("\n=== Checking for discontinuities ===")
    for ch in range(70):
        sum_diffs = np.diff(all_sums[:, ch])
        sum_sq_diffs = np.diff(all_sums_sq[:, ch])
        var_diffs = np.diff(all_variances[:, ch])
        
        # Flag large jumps (more than 3 std deviations from mean)
        sum_threshold = 3 * np.std(sum_diffs)
        sum_sq_threshold = 3 * np.std(sum_sq_diffs)
        var_threshold = 3 * np.std(var_diffs)
        
        sum_discontinuities = np.where(np.abs(sum_diffs) > sum_threshold)[0]
        sum_sq_discontinuities = np.where(np.abs(sum_sq_diffs) > sum_sq_threshold)[0]
        var_discontinuities = np.where(np.abs(var_diffs) > var_threshold)[0]
        
        if len(sum_discontinuities) > 0:
            print(f"Channel {ch}: {len(sum_discontinuities)} sum discontinuities detected")
            for idx in sum_discontinuities[:5]:  # Show first 5
                print(f"  Event {event_numbers[idx]} -> {event_numbers[idx+1]}: "
                      f"jump = {sum_diffs[idx]}")
        
        if len(sum_sq_discontinuities) > 0:
            print(f"Channel {ch}: {len(sum_sq_discontinuities)} sum_sq discontinuities detected")
            for idx in sum_sq_discontinuities[:5]:  # Show first 5
                print(f"  Event {event_numbers[idx]} -> {event_numbers[idx+1]}: "
                      f"jump = {sum_sq_diffs[idx]}")
        
        if len(var_discontinuities) > 0:
            print(f"Channel {ch}: {len(var_discontinuities)} variance discontinuities detected")
            for idx in var_discontinuities[:5]:  # Show first 5
                print(f"  Event {event_numbers[idx]} -> {event_numbers[idx+1]}: "
                      f"jump = {var_diffs[idx]:.6f}")
    
    print("\n=== Summary Statistics ===")
    print(f"Total events: {len(event_numbers)}")
    print(f"Time span: {rel_time[-1]:.3f} seconds")
    print(f"Window size (N): {WINDOW_SIZE}")
    print(f"Sum range: [{all_sums.min()}, {all_sums.max()}]")
    print(f"Sum_sq range: [{all_sums_sq.min()}, {all_sums_sq.max()}]")
    print(f"Variance range: [{all_variances.min():.6f}, {all_variances.max():.6f}]")


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print("Usage: python passthrough_test.py <binary_file> <channel_number>")
        print("  channel_number: 0-69")
        sys.exit(1)
    
    filename = sys.argv[1]
    channel = int(sys.argv[2])
    
    if channel < 0 or channel > 69:
        print("Error: channel_number must be between 0 and 69")
        sys.exit(1)
    
    main(filename, channel)