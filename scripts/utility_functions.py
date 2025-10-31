import sys
import struct
import pandas as pd
import sys
import pyqtgraph as pg
import matplotlib.pyplot as plt
import numpy as np
from astropy.io import fits

class DataProcessor:
    def __init__(self, filename):
        self.filename = filename
        self.df = self.load_data_as_dataframe()

    def load_data_as_dataframe(self):
        events = read_binary_file(self.filename)
        data_list = []

        for event in events:
            data = extract_data(event)
            event_number = data['number']
            ch_mask_bits = data['ch_mask_bits']
            
            for channel in range(70):
                channel_mask = (ch_mask_bits >> (69 - channel)) & 1
                data_list.append({
                    'event_number': event_number,
                    'channel': channel + 1,
                    'timestamp': data['timestamp'],
                    'extra_reg1': data['extra_reg1'],
                    'extra_reg2': data['extra_reg2'],
                    'extra_reg3': data['extra_reg3'],
                    'window_size': data['window_size'],
                    'channel_mask': channel_mask,
                    'variance': data['variances'][channel]
                })

        df = pd.DataFrame(data_list)
        df.set_index(['event_number', 'channel'], inplace=True)
        return df

    def get_dataframe(self):
        return self.df

    def filter_by_channel_mask(self, mask_value):
        return self.df[self.df['channel_mask'] == mask_value]

    def get_event_data(self, event_number):
        return self.df.loc[event_number]

    def get_channel_data(self, event_number, channel):
        return self.df.loc[(event_number, channel)]

    def get_events_by_channel(self, channel):
        """
        Retrieve all events of a certain channel.
        """
        return self.df.xs(channel, level='channel')

    def plot_events(self, channel_data, title):
        """
        Plot events from the provided channel data ordered by timestamp.
        """
        channel_data = channel_data.sort_values(by='timestamp')
        plt.figure(figsize=(10, 6))
        plt.plot(channel_data['timestamp'], channel_data['variance'], marker='o')
        plt.title(title)
        plt.xlabel('Timestamp')
        plt.ylabel('Variance')
        plt.grid(True)
        plt.show()

    def plot_events_by_channel(self, channel):
        """
        Plot all events from a channel ordered by timestamp.
        """
        channel_data = self.get_events_by_channel(channel)
        self.plot_events(channel_data, f'Channel {channel} Events Ordered by Timestamp')

    def plot_events_between(self, channel, start_event, stop_event):
        """
        Plot events between a start and stop event for a channel, ordered by time.
        """
        channel_data = self.get_events_by_channel(channel)
        filtered_data = channel_data.loc[start_event:stop_event]
        self.plot_events(filtered_data, f'Channel {channel} Events from Event {start_event} to {stop_event} Ordered by Timestamp')

    def plot_time_differences_histogram(self, channel, bins=50):
        """
        Plot a histogram of the time differences between events for a channel.
        """
        channel_data = self.get_events_by_channel(channel)
        time_diffs = channel_data['timestamp'].diff().dropna()
        plt.figure(figsize=(10, 6))
        plt.hist(time_diffs, bins=bins, alpha=0.75)
        plt.title(f'Time Differences Histogram for Channel {channel}')
        plt.xlabel('Time Difference')
        plt.ylabel('Frequency')
        plt.grid(True)
        plt.show()

    def plot_time_differences_histogram_separate(self, channels, bins=50):
        """
        Plot histograms of the time differences between events for a group of channels, overplotted separately.
        """
        plt.figure(figsize=(10, 6))
        for channel in channels:
            channel_data = self.get_events_by_channel(channel)
            time_diffs = channel_data['timestamp'].diff().dropna()
            plt.hist(time_diffs, bins=bins, alpha=0.5, label=f'Channel {channel}')
        plt.title('Time Differences Histogram for Multiple Channels (Overplotted)')
        plt.xlabel('Time Difference')
        plt.ylabel('Frequency')
        plt.legend()
        plt.grid(True)
        plt.show()

    def plot_time_differences_histogram_combined(self, channels, bins=50):
        """
        Plot a histogram of the time differences between events for a group of channels in one histogram together.
        """
        all_time_diffs = []
        for channel in channels:
            channel_data = self.get_events_by_channel(channel)
            time_diffs = channel_data['timestamp'].diff().dropna()
            all_time_diffs.extend(time_diffs)
        plt.figure(figsize=(10, 6))
        plt.hist(all_time_diffs, bins=bins, alpha=0.75)
        plt.title('Time Differences Histogram for Multiple Channels (Combined)')
        plt.xlabel('Time Difference')
        plt.ylabel('Frequency')
        plt.grid(True)
        plt.show()

    def plot_with_pyqtgraph(self, channel, show_region=False):
        """
        Plot events for a channel using pyqtgraph with an optional LinearRegionItem and a zoomed-in view.
        Disable panning on the y-axis.
        """
        channel_data = self.get_events_by_channel(channel)
        timestamps = channel_data['timestamp'].values
        variances = channel_data['variance'].values

        app = pg.mkQApp("Plotting Example")
        win = pg.GraphicsLayoutWidget(show=True, title="Channel Plot with LinearRegionItem")
        win.resize(1000, 600)
        win.setWindowTitle(f'Channel {channel} Plot')

        # Enable antialiasing for prettier plots
        pg.setConfigOptions(antialias=True)

        # Create DateAxisItem instances for the x-axis
        date_axis_top = pg.DateAxisItem()
        date_axis_bottom = pg.DateAxisItem()

        # Top plot with optional LinearRegionItem
        p1 = win.addPlot(title=f"Channel {channel} Events Ordered by Timestamp", axisItems={'bottom': date_axis_top})
        p1.plot(timestamps, variances, pen=(255, 0, 0), symbol='o', symbolBrush=(255, 0, 0), name="Red curve")

        # Set the mouse mode to RectMode for zoom box
        p1.getViewBox().setMouseMode(pg.ViewBox.RectMode)

        if show_region:
            # Add LinearRegionItem to the top plot
            region = pg.LinearRegionItem()
            p1.addItem(region)

            # Set the starting bounds of the region to 33% and 66% of the data range
            x_min, x_max = timestamps.min(), timestamps.max()
            region_start = x_min + 0.33 * (x_max - x_min)
            region_end = x_min + 0.66 * (x_max - x_min)
            region.setRegion([region_start, region_end])

            # Bottom plot for zoomed-in view
            win.nextRow()
            p2 = win.addPlot(title="Zoomed-in view", axisItems={'bottom': date_axis_bottom})
            p2.plot(timestamps, variances, pen=(255, 0, 0), symbol='o', symbolBrush=(255, 0, 0), name="Red curve")

            # Set the mouse mode to RectMode for zoom box
            p2.getViewBox().setMouseMode(pg.ViewBox.RectMode)

            # Link the x-axes of the top and bottom plots
            p1.setXLink(p2)

            # Set the limits to the data range
            y_min, y_max = variances.min(), variances.max()
            p1.getViewBox().setLimits(xMin=x_min, xMax=x_max, yMin=y_min, yMax=y_max)
            p2.getViewBox().setLimits(xMin=x_min, xMax=x_max, yMin=y_min, yMax=y_max)

            # Set the initial range to the data range
            p1.setRange(xRange=[x_min, x_max], yRange=[y_min, y_max])
            p2.setRange(xRange=[x_min, x_max], yRange=[y_min, y_max])

            # Enable auto-range for the y-axis to fit visible data
            p2.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)

            # Update the bottom plot to show the zoomed-in region
            def updatePlot():
                p2.setXRange(*region.getRegion(), padding=0)

            # Update the region when the bottom plot's view is changed
            def updateRegion():
                region.setRegion(p2.getViewBox().viewRange()[0])

            region.sigRegionChanged.connect(updatePlot)
            p2.sigXRangeChanged.connect(updateRegion)

            # Initialize the region and plot
            updatePlot()
        else:
            # Set the limits to the data range
            x_min, x_max = timestamps.min(), timestamps.max()
            y_min, y_max = variances.min(), variances.max()
            p1.getViewBox().setLimits(xMin=x_min, xMax=x_max, yMin=y_min, yMax=y_max)

            # Set the initial range to the data range
            p1.setRange(xRange=[x_min, x_max], yRange=[y_min, y_max])

            # Enable auto-range for the y-axis to fit visible data
            #p1.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)

        if __name__ == '__main__':
            pg.exec()

    def plot_with_matplotlib(self, channel):
        """
        Plot events for a channel using matplotlib.
        """
        channel_data = self.get_events_by_channel(channel)
        timestamps = channel_data['timestamp'].values
        variances = channel_data['variance'].values

        plt.figure(figsize=(10, 6))
        plt.plot(timestamps, variances, 'o-', color='red', markersize=5, label=f'Channel {channel}')

        # Set the data ranges according to the data
        plt.xlim(timestamps.min(), timestamps.max())
        plt.ylim(variances.min(), variances.max())

        plt.title(f'Channel {channel} Events Ordered by Timestamp')
        plt.xlabel('Timestamp')
        plt.ylabel('Variance')
        plt.legend()
        plt.grid(True)
        plt.show()

    def plot_variance_histogram(self, channel, bins=10, threshold_flag=None):
        """
        Plot a histogram of the variances for a channel using matplotlib.
        Print the midpoint value of bins where the bin count is above the threshold_flag.
        """
        channel_data = self.get_events_by_channel(channel)
        variances = channel_data['variance'].values

        # Calculate the histogram
        counts, bin_edges = np.histogram(variances, bins=bins)

        # Plot the histogram
        plt.figure(figsize=(10, 6))
        plt.hist(variances, bins=bins, color='blue', alpha=0.7)
        plt.title(f'Variance Histogram for Channel {channel}')
        plt.xlabel('Variance')
        plt.ylabel('Frequency')
        plt.grid(True)

        # Draw a horizontal line at the level of threshold_flag
        if threshold_flag is not None:
            plt.axhline(y=threshold_flag, color='red', linestyle='--', label=f'Threshold: {threshold_flag}')
            plt.legend()

        plt.show()

        # Print the midpoint value of bins where the bin count is above the threshold_flag
        if threshold_flag is not None:
            for count, edge1, edge2 in zip(counts, bin_edges[:-1], bin_edges[1:]):
                if count > threshold_flag:
                    midpoint = (edge1 + edge2) / 2
                    print(f'Bin midpoint with count above {threshold_flag}: {midpoint}')

class colors():

        """This class will color console text output using ANSI codes."""

        RED = ''
        ORANGE = ''
        YELLOW = ''
        GREEN = ''
        BLUE = ''
        INDIGO = ''
        VIOLET = ''
        PINK = ''                                                                        
        BLACK = ''
        CYAN = ''
        PURPLE = ''
        BROWN = ''
        GRAY = ''
        DARKGRAY = ''
        LIGHTBLUE = ''
        LIGHTGREEN = ''
        LIGHTCYAN = ''
        LIGHTRED = ''
        LIGHTPURPLE = ''
        WHITE = ''
        BOLD = ''
        UNDERLINE = ''
        ENDC = ''
    
        def enableColors(self):

                self.RED = '\033[0;31m'
                self.ORANGE = '\033[38;5;166m'
                self.YELLOW = '\033[1;33m'
                self.GREEN = '\033[0;32m'
                self.BLUE = '\033[0;34m'
                self.INDIGO = '\033[38;5;53m'
                self.VIOLET = '\033[38;5;163m'
                self.PINK =  '\033[38;5;205m'
                self.BLACK = '\033[0;30m'
                self.CYAN = '\033[0;36m'
                self.PURPLE = '\033[0;35m'
                self.BROWN = '\033[0;33m'
                self.GRAY = '\033[0;37m'
                self.DARKGRAY = '\033[1;30m'
                self.LIGHTBLUE = '\033[1;34m'
                self.LIGHTGREEN = '\033[1;32m'
                self.LIGHTCYAN = '\033[1;36m'
                self.LIGHTRED = '\033[1;31m'
                self.LIGHTPURPLE = '\033[1;35m'
                self.WHITE = '\033[1;37m'
                self.BOLD = '\033[1m'
                self.UNDERLINE = '\033[4m'
                self.ENDC = '\033[0m'

        
        def disableColors(self):
        
                self.RED = ''        
                self.ORANGE = ''
                self.YELLOW = ''
                self.GREEN = ''
                self.BLUE = ''
                self.INDIGO = ''
                self.VIOLET = ''
                self.PINK = ''
                self.BLACK = ''
                self.CYAN = ''
                self.PURPLE = ''
                self.BROWN = ''
                self.GRAY = ''
                self.DARKGRAY = ''
                self.LIGHTBLUE = ''
                self.LIGHTGREEN = ''
                self.LIGHTCYAN = ''
                self.LIGHTRED = ''
                self.LIGHTPURPLE = ''
                self.WHITE = ''
                self.BOLD = ''
                self.UNDERLINE = ''
                self.ENDC = ''

        def getState(self):
                if self.ENDC:
                        return True
                elif not self.ENDC:
                        return False
                else:
                        return -1

        def flipState(self):
                if self.getState():
                        self.disableColors()
                elif not self.getState():
                        self.enableColors()
                else:
                        sys.exit("Can't flip ANSI state, exiting.")

        def confirmColors(self):
                if self.getState() == True:
                        print('Colors are '+self.red('e')+self.orange('n')+self.yellow('a')+self.green('b')+self.blue('l')+self.indigo('e')+self.violet('d'))
                elif self.getState() == False:
                        print('Colors are off!')
                elif self.getState() == -1:
                        print('Error: Can\'t get color state.')

        def confirmColorsDonger(self):
                if self.getState() == True:
                        print('Colors are '+self.pink('(ﾉ')+self.lightblue('◕')+self.pink('ヮ')+self.lightblue('◕')+self.pink('ﾉ')+self.red('☆')+self.orange('.')+self.yellow('*')+self.green(':')+self.blue('･ﾟ')+self.indigo('✧')+self.violet(' enabled!'))    
                elif self.getState() == False:
                        print('Colors are off!')
                elif self.getState() == -1:
                        print('Error: Can\'t get color state.')

        def orange(self, inString):
                inString = str(self.ORANGE+str(inString)+self.ENDC)
                return inString
        def indigo(self, inString):
                inString = str(self.INDIGO+str(inString)+self.ENDC)
                return inString
        def violet(self, inString):
                inString = str(self.VIOLET+str(inString)+self.ENDC)
                return inString
        def pink(self, inString):
                inString = str(self.PINK+str(inString)+self.ENDC)
                return inString
        def black(self, inString):
                inString = str(self.BLACK+str(inString)+self.ENDC)
                return inString
        def blue(self, inString):
                inString = str(self.BLUE+str(inString)+self.ENDC)
                return inString
        def green(self, inString):
                inString = str(self.GREEN+str(inString)+self.ENDC)
                return inString
        def cyan(self, inString):
                inString = str(self.CYAN+str(inString)+self.ENDC)
                return inString
        def red(self, inString):
                inString = str(self.RED+str(inString)+self.ENDC)
                return inString
        def purple(self, inString):
                inString = str(self.PURPLE+str(inString)+self.ENDC)
                return inString
        def brown(self, inString):
                inString = str(self.BROWN+str(inString)+self.ENDC)
                return inString
        def gray(self, inString):
                inString = str(self.GRAY+str(inString)+self.ENDC)
                return inString
        def darkgray(self, inString):
                inString = str(self.DARKGRAY+str(inString)+self.ENDC)
                return inString
        def lightblue(self, inString):
                inString = str(self.LIGHTBLUE+str(inString)+self.ENDC)
                return inString
        def lightgreen(self, inString):
                inString = str(self.LIGHTGREEN+str(inString)+self.ENDC)
                return inString
        def lightcyan(self, inString):
                inString = str(self.LIGHTCYAN+str(inString)+self.ENDC)
                return inString
        def lightred(self, inString):
                inString = str(self.LIGHTRED+str(inString)+self.ENDC)
                return inString
        def yellow(self, inString):
                inString = str(self.YELLOW+str(inString)+self.ENDC)
                return inString
        def white(self, inString):
                inString = str(self.WHITE+str(inString)+self.ENDC)
                return inString
        def bold(self, inString):
                inString = str(self.BOLD+str(inString)+self.ENDC)
                return inString
        def underline(self, inString):
                inString = str(self.UNDERLINE+str(inString)+self.ENDC)
                return inString

def read_binary_file(filename):
    events = []
    event_size = 308  # Size of each event in bytes

    try:
        with open(filename, 'rb') as file:
            while True:
                event = file.read(event_size)
                if len(event) < event_size:
                    break  # End of file or incomplete event
                events.append(event)
    except IOError as e:
        print(f"Error reading file {filename}: {e}")
        sys.exit(1)

    return events

def format_binary_with_spaces(binary_str):
    # Group the last 2 bits separately and then group the rest in 4-bit chunks
    return ' '.join([binary_str[:2]] + [binary_str[i:i+4] for i in range(2, len(binary_str), 4)])

def print_hex(event, color_methods, default_color):
    # Format the event data as hex numbers with 7 double words (32 bits each) per line
    hex_lines = []
    for i in range(0, len(event), 28):  # 28 bytes = 7 double words * 4 bytes per double word
        if i < 28:
            hex_line = '    '.join(
                color_methods[j // 4](f'{struct.unpack_from(">I", event, j)[0]:08x}'[:4] + ' ' + f'{struct.unpack_from(">I", event, j)[0]:08x}'[4:])
                for j in range(i, min(i + 28, len(event)), 4)
            )
        else:
            hex_line = '    '.join(
                default_color(f'{struct.unpack_from(">I", event, j)[0]:08x}'[:4] + ' ' + f'{struct.unpack_from(">I", event, j)[0]:08x}'[4:])
                for j in range(i, min(i + 28, len(event)), 4)
            )
        hex_lines.append(hex_line)

    # Print the formatted hex lines
    for line in hex_lines:
        print(line)

def dump_events(filename):
    c = colors()
    c.enableColors()
    
    events = read_binary_file(filename)

    color_methods = [c.red, c.orange, c.yellow, c.green, c.blue, c.indigo, c.violet]
    default_color = c.cyan

    event_index = 0
    print(f"Event Number: {event_index + 1}")
    print_hex(events[event_index], color_methods, default_color)

    while event_index < len(events):
        event = events[event_index]
        user_input = input("Press Enter to dump the next event, 'p' to parse the event, 'b' to reprint the hex, or 'x' to terminate: ")
        if user_input.lower() == 'x':
            print("Terminating early.")
            break

        if user_input.lower() == 'p':
            print(f"Event Number: {event_index + 1}")
            parsed_data = extract_data(event)
            print("Parsed Event Data:")
            for key, value in parsed_data.items():
                if key == 'ch_mask_bits':
                    value = format_binary_with_spaces(f'{value:070b}')
                if key != 'variances':  # Skip printing variances here
                    print(f"{key}: {value}")

            # Format and print the variances
            variances = parsed_data['variances']
            variance_lines = []
            variance_width = 20  # Adjust the width as needed
            for i in range(0, len(variances), 7):
                variance_line = ' '.join(f'{variance:>{variance_width}.6f}' for variance in variances[i:i+7])
                variance_lines.append(variance_line)

            print("Variances:")
            for line in variance_lines:
                print(line)
        elif user_input.lower() == 'b':
            print(f"Event Number: {event_index + 1}")
            print_hex(event, color_methods, default_color)
        else:
            event_index += 1
            if event_index < len(events):
                print(f"Event Number: {event_index + 1}")
                print_hex(events[event_index], color_methods, default_color)

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
    ch_mask_bits_offset = 20
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
    ch_mask_bits_high = window_size_and_mask & 0x3F

    # Extract the 64-bit channel mask at offset 20
    ch_mask_bits_low = struct.unpack_from('>Q', event, ch_mask_bits_offset)[0]

    # Combine the 6 bits with the 64-bit number to form the full channel mask
    ch_mask_bits = (ch_mask_bits_high << 64) | ch_mask_bits_low

    # Extract the variances (280 bytes) starting at offset 28
    variances = []
    for i in range(70):
        variance_word = struct.unpack_from('>I', event, variance_offset + i * 4)[0]
        variances.append(convert_to_decimal(variance_word))

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

def read_binary_file_in_chunks(filename, chunk_size=308):
    with open(filename, 'rb') as file:
        while True:
            chunk = file.read(chunk_size)
            if len(chunk) < chunk_size:
                break  # End of file or incomplete chunk
            yield chunk

def extract_data_from_chunk(chunk):
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

    # Extract the variances (280 bytes) starting at offset 28
    variances = []
    for i in range(70):
        variance_word = struct.unpack_from('>I', chunk, variance_offset + i * 4)[0]
        variances.append(convert_to_decimal(variance_word))

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

def save_to_fits(data, filename):
    # Convert the data to a FITS table
    # Note: ch_mask_bits is 70-bit, so we split it into two 64-bit parts
    col1 = fits.Column(name='number', format='K', array=np.array([d['number'] for d in data], dtype=np.uint64))
    col2 = fits.Column(name='timestamp', format='D', array=np.array([d['timestamp'] for d in data], dtype=np.float64))
    col3 = fits.Column(name='extra_reg1', format='I', array=np.array([d['extra_reg1'] for d in data], dtype=np.uint32))
    col4 = fits.Column(name='extra_reg2', format='I', array=np.array([d['extra_reg2'] for d in data], dtype=np.uint32))
    col5 = fits.Column(name='extra_reg3', format='I', array=np.array([d['extra_reg3'] for d in data], dtype=np.uint32))
    col6 = fits.Column(name='window_size', format='I', array=np.array([d['window_size'] for d in data], dtype=np.uint32))
    # Split 70-bit channel mask into low 64 bits and high 6 bits
    col7 = fits.Column(name='ch_mask_low', format='K', array=np.array([d['ch_mask_bits'] & 0xFFFFFFFFFFFFFFFF for d in data], dtype=np.uint64))
    col8 = fits.Column(name='ch_mask_high', format='B', array=np.array([d['ch_mask_bits'] >> 64 for d in data], dtype=np.uint8))
    col9 = fits.Column(name='variances', format='70D', array=np.array([d['variances'] for d in data], dtype=np.float64))

    cols = fits.ColDefs([col1, col2, col3, col4, col5, col6, col7, col8, col9])
    hdu = fits.BinTableHDU.from_columns(cols)

    # Write the FITS file
    hdu.writeto(filename, overwrite=True)

def process_and_save_to_fits(binary_filename, fits_filename, max_events=None):
    data = []
    for i, chunk in enumerate(read_binary_file_in_chunks(binary_filename)):
        if max_events is not None and i >= max_events:
            break
        parsed_data = extract_data_from_chunk(chunk)
        data.append(parsed_data)
    
    save_to_fits(data, fits_filename)

def save_to_fits_incrementally(data, filename):
    # Convert the data to a FITS table
    # Note: ch_mask_bits is 70-bit, so we split it into two 64-bit parts
    col1 = fits.Column(name='number', format='K', array=np.array([d['number'] for d in data], dtype=np.uint64))
    col2 = fits.Column(name='timestamp', format='D', array=np.array([d['timestamp'] for d in data], dtype=np.float64))
    col3 = fits.Column(name='extra_reg1', format='I', array=np.array([d['extra_reg1'] for d in data], dtype=np.uint32))
    col4 = fits.Column(name='extra_reg2', format='I', array=np.array([d['extra_reg2'] for d in data], dtype=np.uint32))
    col5 = fits.Column(name='extra_reg3', format='I', array=np.array([d['extra_reg3'] for d in data], dtype=np.uint32))
    col6 = fits.Column(name='window_size', format='I', array=np.array([d['window_size'] for d in data], dtype=np.uint32))
    # Split 70-bit channel mask into low 64 bits and high 6 bits
    col7 = fits.Column(name='ch_mask_low', format='K', array=np.array([d['ch_mask_bits'] & 0xFFFFFFFFFFFFFFFF for d in data], dtype=np.uint64))
    col8 = fits.Column(name='ch_mask_high', format='B', array=np.array([d['ch_mask_bits'] >> 64 for d in data], dtype=np.uint8))
    col9 = fits.Column(name='variances', format='70D', array=np.array([d['variances'] for d in data], dtype=np.float64))

    cols = fits.ColDefs([col1, col2, col3, col4, col5, col6, col7, col8, col9])
    hdu = fits.BinTableHDU.from_columns(cols)

    # Write the FITS file
    hdu.writeto(filename, overwrite=True)

def process_and_save_to_fits_incrementally(binary_filename, fits_filename, max_events=None, batch_size=1000):
    """
    Process binary file incrementally to avoid loading entire file into memory.
    
    Parameters:
    -----------
    binary_filename : str
        Path to the binary file to process
    fits_filename : str
        Path to the output FITS file
    max_events : int or None
        Maximum number of events to process (None for all)
    batch_size : int
        Number of events to accumulate before writing to disk (default 1000)
    """
    data = []
    event_count = 0
    
    for i, chunk in enumerate(read_binary_file_in_chunks(binary_filename)):
        if max_events is not None and i >= max_events:
            break
            
        parsed_data = extract_data_from_chunk(chunk)
        data.append(parsed_data)
        event_count += 1
        
        # Write batch when we reach batch_size or when we hit max_events
        if len(data) >= batch_size or (max_events is not None and event_count >= max_events):
            if event_count <= batch_size:  # First batch - create new file
                save_to_fits(data, fits_filename)
                print(f"Created FITS file with first {len(data)} events")
            else:  # Subsequent batches - append to existing table
                # Read existing data
                with fits.open(fits_filename) as hdul:
                    existing_data = hdul[1].data
                    
                    # Convert existing data to list of dicts
                    all_data = []
                    for row in existing_data:
                        ch_mask = reconstruct_channel_mask(row['ch_mask_low'], row['ch_mask_high'])
                        all_data.append({
                            'number': row['number'],
                            'timestamp': row['timestamp'],
                            'extra_reg1': row['extra_reg1'],
                            'extra_reg2': row['extra_reg2'],
                            'extra_reg3': row['extra_reg3'],
                            'window_size': row['window_size'],
                            'ch_mask_bits': ch_mask,
                            'variances': list(row['variances'])
                        })
                    
                    # Add new data
                    all_data.extend(data)
                
                # Write combined data back
                save_to_fits(all_data, fits_filename)
                print(f"Appended {len(data)} events (total: {len(all_data)} events)")
            
            data.clear()
    
    # Write any remaining data
    if data:
        if event_count <= len(data):  # Only batch - create new file
            save_to_fits(data, fits_filename)
            print(f"Created FITS file with {len(data)} events")
        else:  # Final partial batch - append
            with fits.open(fits_filename) as hdul:
                existing_data = hdul[1].data
                
                all_data = []
                for row in existing_data:
                    ch_mask = reconstruct_channel_mask(row['ch_mask_low'], row['ch_mask_high'])
                    all_data.append({
                        'number': row['number'],
                        'timestamp': row['timestamp'],
                        'extra_reg1': row['extra_reg1'],
                        'extra_reg2': row['extra_reg2'],
                        'extra_reg3': row['extra_reg3'],
                        'window_size': row['window_size'],
                        'ch_mask_bits': ch_mask,
                        'variances': list(row['variances'])
                    })
                
                all_data.extend(data)
            
            save_to_fits(all_data, fits_filename)
            print(f"Appended final {len(data)} events (total: {len(all_data)} events)")

def reconstruct_channel_mask(ch_mask_low, ch_mask_high):
    """
    Reconstruct the original 70-bit channel mask from the split components.
    
    Parameters:
    -----------
    ch_mask_low : int or array
        Lower 64 bits of the channel mask
    ch_mask_high : int or array  
        Upper 6 bits of the channel mask
        
    Returns:
    --------
    int or array : The reconstructed 70-bit channel mask
    """
    # Convert to Python int to allow arbitrary precision arithmetic
    if isinstance(ch_mask_low, np.ndarray):
        return np.array([(int(high) << 64) | int(low) for low, high in zip(ch_mask_low, ch_mask_high)])
    else:
        return (int(ch_mask_high) << 64) | int(ch_mask_low)

