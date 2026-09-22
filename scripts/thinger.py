import sys
import numpy as np
import matplotlib.pyplot as plt
from utility_functions import read_events_from_binary_file, parse_data_from_event

def load_data(bin_filename):
    event_numbers = []
    timestamps = []
    extra_reg1 = []
    extra_reg2 = []
    extra_reg3 = []
    window_sizes = []
    ch_mask_bits = []
    variances = []

    for chunk in read_events_from_binary_file(bin_filename):
        parsed = parse_data_from_event(chunk)
        event_numbers.append(parsed['event_number'])
        timestamps.append(parsed['timestamp'])
        extra_reg1.append(parsed['extra_reg1'])
        extra_reg2.append(parsed['extra_reg2'])
        extra_reg3.append(parsed['extra_reg3'])
        window_sizes.append(parsed['window_size'])
        ch_mask_bits.append(parsed['ch_mask_bits'])
        variances.append(parsed['variances'])

    # Convert lists to numpy arrays
    event_numbers = np.array(event_numbers)
    timestamps = np.array(timestamps)
    extra_reg1 = np.array(extra_reg1)
    extra_reg2 = np.array(extra_reg2)
    extra_reg3 = np.array(extra_reg3)
    window_sizes = np.array(window_sizes)
    ch_mask_bits = np.array(ch_mask_bits)
    variances = np.array(variances)

    print(f"Total events parsed: {len(event_numbers)}")
    print(f"Variances shape: {variances.shape}")

    # Add more integrity checks as needed
    # Example: Check for monotonic event numbers
    if not np.all(np.diff(event_numbers) >= 0):
        print("Warning: Event numbers are not monotonic!")
    else:
        print("Event numbers are monotonic.")

    return event_numbers, timestamps, extra_reg1, extra_reg2, extra_reg3, window_sizes, ch_mask_bits, variances

def plot_variance(timestamps_zeroed, variances, event_numbers, channel=0):
    """
    Plot variances vs time and time differences between events in subplots.
    """
    
    # Create figure with two subplots
    fig, ax = plt.subplots(figsize=(12, 8))
    
    if channel < variances.shape[1]:
        ax.plot(event_numbers, variances[:, channel], 'o-', 
                markersize=3, alpha=0.7, color='blue')
        ax.set_ylabel('Variance')
        ax.set_title(f'Channel {channel} Variances vs Event Number')
    else:
        ax.text(0.5, 0.5, f'Channel {channel} not found\nMax channel: {variances.shape[1]-1}', 
                transform=ax.transAxes, ha='center', va='center', fontsize=14)
        ax.set_ylabel('Event Number')
        ax.set_title(f'Channel {channel} - Invalid Channel')
    
    ax.grid(True, alpha=0.3)
    

    ax.set_xlabel('Event Number')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.show()
    

if __name__ == "__main__":
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print(f"Usage: {sys.argv[0]} <binary_file> [channel_number]")
        print(f"  binary_file: Path to the binary file")
        print(f"  channel_number: Channel to plot (default: 0)")
        sys.exit(1)
    
    binary_file = sys.argv[1]
    channel = 0  # default channel
    
    if len(sys.argv) == 3:
        try:
            channel = int(sys.argv[2])
        except ValueError:
            print(f"Error: Channel number must be an integer, got '{sys.argv[2]}'")
            sys.exit(1)
    
    event_numbers, timestamps, extra_reg1, extra_reg2, extra_reg3, window_sizes, ch_mask_bits, variances = load_data(binary_file)
    timestamps_zeroed = (timestamps - timestamps[0]) * 1000  # Convert to milliseconds
    
    print(f"Available channels: 0 to {variances.shape[1]-1}")
    print(f"Plotting channel: {channel}")
    
    # Plot variances and timing information
    plot_variance(timestamps_zeroed, variances, event_numbers, channel)

