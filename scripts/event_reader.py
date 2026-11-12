"""
Reader for VO run files (<run>_<telescope>.bin / <run>_<telescope>_h<n>.bin).

A run file is a headerless sequence of 308-byte big-endian event records, the
same packets the harvester boards send over UDP:

    offset  size     field
    ------  -------  ---------------------------------------------------------
     0      u32      event number
     4      u32      timestamp, UNIX seconds
     8      u32      timestamp, nanoseconds
    12      3 x u16  extra_reg1, extra_reg2, extra_reg3
    18      u16      window_size (top 3 bits) | ch_mask high 6 bits (low 6 bits)
    20      u64      ch_mask low 64 bits
    28      70 x u32 variances, unsigned 16.16 fixed point

Typical use:

    from event_reader import EventFile

    ev = EventFile("data/671_1_h0.bin")
    len(ev)                   # number of events
    ev.timestamp              # (N,) float64 UNIX time
    ev.variances[:, 2]        # channel 3, all events
    ev.channel_mask           # (N, 70) bool, column 0 = channel 1
    ev[0]                     # dict for the first event
    df = ev.to_dataframe()    # one row per event

The file is memory-mapped, so opening even a multi-GB run is instant; columns
are decoded with numpy the first time you access them.
"""

import os
import sys
import warnings

import numpy as np

EVENT_SIZE = 308
N_CHANNELS = 70

EVENT_DTYPE = np.dtype([
    ('event_number', '>u4'),
    ('timestamp_sec', '>u4'),
    ('timestamp_ns', '>u4'),
    ('extra_reg', '>u2', (3,)),
    ('window_mask', '>u2'),
    ('ch_mask_low', '>u8'),
    ('variance_raw', '>u4', (N_CHANNELS,)),
])
assert EVENT_DTYPE.itemsize == EVENT_SIZE

# Bit positions of channels 1..70 within the 70-bit mask (channel 1 = bit 69).
_HIGH_SHIFTS = np.arange(5, -1, -1, dtype=np.uint16)    # channels 1-6, bits 69..64
_LOW_SHIFTS = np.arange(63, -1, -1, dtype=np.uint64)    # channels 7-70, bits 63..0


class EventFile:
    """Parsed view of a VO binary run file.

    Parameters
    ----------
    filename : str or path-like
        Run file to open.
    max_events : int, optional
        Only expose the first `max_events` events.
    """

    def __init__(self, filename, max_events=None):
        self.filename = os.fspath(filename)
        size = os.path.getsize(self.filename)
        n_events, leftover = divmod(size, EVENT_SIZE)
        if leftover:
            warnings.warn(
                f"{self.filename}: {leftover} trailing bytes after the last full "
                f"{EVENT_SIZE}-byte event were ignored")
        if max_events is not None:
            n_events = min(n_events, max(0, int(max_events)))

        if n_events == 0:
            records = np.zeros(0, dtype=EVENT_DTYPE)
        else:
            records = np.memmap(self.filename, dtype=EVENT_DTYPE, mode='r',
                                shape=(n_events,))
        self._set_records(records)

    @classmethod
    def from_records(cls, records, filename=None):
        """Wrap an existing EVENT_DTYPE array (e.g. a slice or np.frombuffer)."""
        obj = cls.__new__(cls)
        obj.filename = filename
        obj._set_records(np.asarray(records, dtype=EVENT_DTYPE).reshape(-1))
        return obj

    @classmethod
    def from_bytes(cls, data):
        """Parse a bytes buffer holding one or more whole events."""
        n_events = len(data) // EVENT_SIZE
        return cls.from_records(np.frombuffer(data, dtype=EVENT_DTYPE, count=n_events))

    def _set_records(self, records):
        self._records = records
        self._cache = {}

    # ------------------------------------------------------------------ basics

    @property
    def raw(self):
        """The underlying (N,) structured record array (big-endian, undecoded)."""
        return self._records

    def raw_bytes(self, i):
        """The original 308 bytes of event `i`."""
        return self._records[i].tobytes()

    def __len__(self):
        return len(self._records)

    def __repr__(self):
        return f"<EventFile {self.filename!r}: {len(self)} events>"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        """Drop the memory map. Arrays already taken from this object stay valid."""
        self._set_records(np.zeros(0, dtype=EVENT_DTYPE))

    # ----------------------------------------------------------------- columns

    def _column(self, name, compute):
        if name not in self._cache:
            self._cache[name] = compute()
        return self._cache[name]

    @property
    def event_number(self):
        return self._column('event_number',
                            lambda: self._records['event_number'].astype(np.uint32))

    @property
    def timestamp_sec(self):
        return self._column('timestamp_sec',
                            lambda: self._records['timestamp_sec'].astype(np.uint32))

    @property
    def timestamp_ns(self):
        return self._column('timestamp_ns',
                            lambda: self._records['timestamp_ns'].astype(np.uint32))

    @property
    def timestamp(self):
        """UNIX time as float64 seconds (sec + ns * 1e-9)."""
        return self._column('timestamp', lambda: (
            self.timestamp_sec.astype(np.float64)
            + self.timestamp_ns.astype(np.float64) * 1e-9))

    @property
    def extra_reg(self):
        """(N, 3) uint16: extra_reg1..3."""
        return self._column('extra_reg',
                            lambda: self._records['extra_reg'].astype(np.uint16))

    @property
    def extra_reg1(self):
        return self.extra_reg[:, 0]

    @property
    def extra_reg2(self):
        return self.extra_reg[:, 1]

    @property
    def extra_reg3(self):
        return self.extra_reg[:, 2]

    @property
    def window_size(self):
        return self._column('window_size', lambda: (
            self._records['window_mask'].astype(np.uint16) >> 13).astype(np.uint8))

    @property
    def ch_mask_high(self):
        """Top 6 bits (channels 1-6) of the 70-bit channel mask."""
        return self._column('ch_mask_high', lambda: (
            self._records['window_mask'].astype(np.uint16) & 0x3F).astype(np.uint8))

    @property
    def ch_mask_low(self):
        """Low 64 bits (channels 7-70) of the 70-bit channel mask."""
        return self._column('ch_mask_low',
                            lambda: self._records['ch_mask_low'].astype(np.uint64))

    @property
    def channel_mask(self):
        """(N, 70) bool; column c is channel c+1 (channel 1 = mask bit 69)."""
        def compute():
            high = (self.ch_mask_high.astype(np.uint16)[:, None] >> _HIGH_SHIFTS) & 1
            low = (self.ch_mask_low[:, None] >> _LOW_SHIFTS) & np.uint64(1)
            return np.concatenate([high, low], axis=1).astype(bool)
        return self._column('channel_mask', compute)

    @property
    def variance_raw(self):
        """(N, 70) uint32 raw 16.16 fixed-point variance words."""
        return self._column('variance_raw',
                            lambda: self._records['variance_raw'].astype(np.uint32))

    @property
    def variances(self):
        """(N, 70) float64 variances; column c is channel c+1."""
        return self._column('variances',
                            lambda: self.variance_raw.astype(np.float64) / 65536.0)

    def ch_mask_bits(self, i):
        """Full 70-bit channel mask of event `i` as a Python int."""
        return (int(self.ch_mask_high[i]) << 64) | int(self.ch_mask_low[i])

    # ----------------------------------------------------------- per-event API

    def __getitem__(self, key):
        if isinstance(key, (int, np.integer)):
            i = int(key)
            if i < 0:
                i += len(self)
            if not 0 <= i < len(self):
                raise IndexError(f"event index {key} out of range for {len(self)} events")
            return self._event_dict(i)
        return EventFile.from_records(self._records[key], filename=self.filename)

    def __iter__(self):
        for i in range(len(self)):
            yield self._event_dict(i)

    def _event_dict(self, i):
        r = self._records[i]
        window_mask = int(r['window_mask'])
        sec, ns = int(r['timestamp_sec']), int(r['timestamp_ns'])
        return {
            'event_number': int(r['event_number']),
            'timestamp': sec + ns * 1e-9,
            'extra_reg1': int(r['extra_reg'][0]),
            'extra_reg2': int(r['extra_reg'][1]),
            'extra_reg3': int(r['extra_reg'][2]),
            'window_size': window_mask >> 13,
            'ch_mask_bits': ((window_mask & 0x3F) << 64) | int(r['ch_mask_low']),
            'variances': (r['variance_raw'].astype(np.float64) / 65536.0).tolist(),
        }

    # ------------------------------------------------------------- bulk export

    def to_dict(self):
        """All decoded columns as a dict of numpy arrays."""
        return {
            'event_number': self.event_number,
            'timestamp': self.timestamp,
            'timestamp_sec': self.timestamp_sec,
            'timestamp_ns': self.timestamp_ns,
            'extra_reg1': self.extra_reg1,
            'extra_reg2': self.extra_reg2,
            'extra_reg3': self.extra_reg3,
            'window_size': self.window_size,
            'ch_mask_high': self.ch_mask_high,
            'ch_mask_low': self.ch_mask_low,
            'channel_mask': self.channel_mask,
            'variances': self.variances,
        }

    def to_dataframe(self, long=False):
        """Return a pandas DataFrame.

        long=False: one row per event; variances in columns var_1..var_70 and
                    the channel mask in ch_mask_high / ch_mask_low.
        long=True:  one row per (event, channel), indexed by
                    (event_number, channel) with columns timestamp,
                    extra_reg1-3, window_size, channel_mask, variance.
        """
        import pandas as pd

        if not long:
            df = pd.DataFrame({
                'event_number': self.event_number,
                'timestamp': self.timestamp,
                'extra_reg1': self.extra_reg1,
                'extra_reg2': self.extra_reg2,
                'extra_reg3': self.extra_reg3,
                'window_size': self.window_size,
                'ch_mask_high': self.ch_mask_high,
                'ch_mask_low': self.ch_mask_low,
            })
            var = pd.DataFrame(self.variances,
                               columns=[f'var_{c}' for c in range(1, N_CHANNELS + 1)])
            return pd.concat([df, var], axis=1)

        n = len(self)

        def per_channel(a):
            return np.repeat(a, N_CHANNELS)

        index = pd.MultiIndex.from_arrays(
            [per_channel(self.event_number),
             np.tile(np.arange(1, N_CHANNELS + 1), n)],
            names=['event_number', 'channel'])
        return pd.DataFrame({
            'timestamp': per_channel(self.timestamp),
            'extra_reg1': per_channel(self.extra_reg1),
            'extra_reg2': per_channel(self.extra_reg2),
            'extra_reg3': per_channel(self.extra_reg3),
            'window_size': per_channel(self.window_size),
            'channel_mask': self.channel_mask.reshape(-1).astype(np.uint8),
            'variance': self.variances.reshape(-1),
        }, index=index)


def read_events(filename, max_events=None):
    """Read a run file and return all decoded columns as a dict of numpy arrays."""
    return EventFile(filename, max_events=max_events).to_dict()


def parse_event(buf):
    """Parse one 308-byte event (bytes-like) into a dict.

    Keys: event_number, timestamp, extra_reg1-3, window_size,
    ch_mask_bits (70-bit Python int), variances (list of 70 floats).
    """
    if len(buf) < EVENT_SIZE:
        raise ValueError(f"event needs {EVENT_SIZE} bytes, got {len(buf)}")
    return EventFile.from_bytes(bytes(buf[:EVENT_SIZE]))[0]


def _main(argv):
    if len(argv) != 2:
        print(f"Usage: python {os.path.basename(argv[0])} <run_file.bin>")
        return 1
    with EventFile(argv[1]) as ev:
        print(ev)
        if not len(ev):
            return 0
        t = ev.timestamp
        print(f"events {int(ev.event_number[0])} .. {int(ev.event_number[-1])}, "
              f"time span {t[-1] - t[0]:.3f} s")
        first = ev[0]
        for key, value in first.items():
            if key == 'variances':
                value = np.array2string(np.asarray(value), precision=4, max_line_width=100)
            elif key == 'ch_mask_bits':
                value = f'{value:070b}'
            print(f"{key}: {value}")
    return 0


if __name__ == '__main__':
    sys.exit(_main(sys.argv))
