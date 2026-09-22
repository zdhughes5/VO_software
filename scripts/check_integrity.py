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

def plot_variance_and_timing(timestamps_zeroed, variances, event_numbers, channel=0):
    """
    Plot variances vs time and time differences between events in subplots.
    """
    # Calculate time differences between consecutive events
    time_diffs = np.diff(timestamps_zeroed)
    
    # Create figure with two subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    
    # Plot 1: Variances vs time for selected channel
    if channel < variances.shape[1]:
        ax1.plot(timestamps_zeroed, variances[:, channel], 'o-', 
                markersize=3, alpha=0.7, color='blue')
        ax1.set_ylabel('Variance')
        ax1.set_title(f'Channel {channel} Variances vs Time')
    else:
        ax1.text(0.5, 0.5, f'Channel {channel} not found\nMax channel: {variances.shape[1]-1}', 
                transform=ax1.transAxes, ha='center', va='center', fontsize=14)
        ax1.set_ylabel('Variance')
        ax1.set_title(f'Channel {channel} - Invalid Channel')
    
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Time differences between events
    ax2.plot(timestamps_zeroed[1:], time_diffs, 'ro-', markersize=4, alpha=0.7)
    ax2.set_xlabel('Time (milliseconds)')
    ax2.set_ylabel('Time Diff (milliseconds)')
    ax2.set_title('Time Differences Between Consecutive Events')
    ax2.grid(True, alpha=0.3)
    
    # Add statistics as text
    mean_diff = np.mean(time_diffs)
    std_diff = np.std(time_diffs)
    ax2.text(0.02, 0.98, f'Mean: {mean_diff:.3f}ms\nStd: {std_diff:.3f}ms', 
             transform=ax2.transAxes, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    plt.tight_layout()
    plt.show()
    
    return time_diffs

def plot_timing_histogram(time_diffs):
    """
    Plot histogram of time differences with 1ms bins in a separate figure.
    """
    # Create separate figure for histogram
    fig, ax = plt.subplots(1, 1, figsize=(10, 6))
    
    # Create 1ms bins
    bins = np.arange(time_diffs.min(), time_diffs.max() + 1, 1)  # 1ms bins
    ax.hist(time_diffs, bins=bins, alpha=0.7, color='green', edgecolor='black')
    ax.set_xlabel('Time Difference (milliseconds)')
    ax.set_ylabel('Count')
    ax.set_title('Distribution of Time Differences Between Events (1ms bins)')
    ax.grid(True, alpha=0.3)
    
    # Add statistics to histogram
    mean_diff = np.mean(time_diffs)
    median_diff = np.median(time_diffs)
    ax.axvline(mean_diff, color='red', linestyle='--', linewidth=2, label=f'Mean: {mean_diff:.3f}ms')
    ax.axvline(median_diff, color='orange', linestyle='--', linewidth=2, label=f'Median: {median_diff:.3f}ms')
    ax.legend()
    
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
    time_diffs = plot_variance_and_timing(timestamps_zeroed, variances, event_numbers, channel)
    
    # Plot timing histogram in separate figure
    plot_timing_histogram(time_diffs)
    
    # Print timing statistics
    print(f"\nTiming Statistics:")
    print(f"Mean time between events: {np.mean(time_diffs):.3f} milliseconds")
    print(f"Std time between events: {np.std(time_diffs):.3f} milliseconds")
    print(f"Min time between events: {np.min(time_diffs):.3f} milliseconds")
    print(f"Max time between events: {np.max(time_diffs):.3f} milliseconds")
