import sys
import yaml
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from utility_functions import read_events_from_binary_file, parse_data_from_event


def high_pass_filter(data, window_size):
    """High-pass = signal minus its own long moving average (low-pass estimate)."""
    kernel = np.ones(window_size) / window_size
    lowpass = np.convolve(data, kernel, mode='same')
    return data - lowpass, lowpass


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

    if not np.all(np.diff(event_numbers) >= 0):
        print("Warning: Event numbers are not monotonic!")
    else:
        print("Event numbers are monotonic.")

    return event_numbers, timestamps, extra_reg1, extra_reg2, extra_reg3, window_sizes, ch_mask_bits, variances


def moving_average(data, window_size):
    kernel = np.ones(window_size) / window_size
    return np.convolve(data, kernel, mode='same')


def step_convolve(data, half_width, demean=True):
    """Convolve data with a bipolar step kernel [+1...+1, -1...-1] of total width
    2*half_width.  Returns (conv_signal, x_offset) where x_offset is the index
    into the original array that corresponds to conv_signal[0] (i.e. the step
    boundary lands at original_index = k + half_width for output sample k)."""
    d = data - np.mean(data) if demean else data.copy()
    kernel = np.hstack((np.ones(half_width), -np.ones(half_width)))
    conv = np.convolve(d, kernel, mode='valid')
    return conv, half_width  # caller adds x_offset to get original indices


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <binary_file> <config.yaml>")
        sys.exit(1)

    bin_filename = sys.argv[1]
    config_file  = sys.argv[2]

    with open(config_file, 'r') as f:
        cfg = yaml.safe_load(f)

    channel   = int(cfg.get('channel', 0))
    start_idx = cfg.get('start_idx', None)
    end_idx   = cfg.get('end_idx', None)

    ma_window    = int(cfg.get('moving_average', {}).get('window_size', 200))
    diff_order   = int(cfg.get('diff_order', 1))
    diff_enabled = bool(cfg.get('diff_enabled', True))

    pf      = cfg.get('peak_finding', {})
    pf_abs  = bool(pf.get('abs_value', True))

    # Only forward non-null keys to find_peaks
    _pf_keys = ('height', 'threshold', 'distance', 'prominence', 'width', 'wlen', 'rel_height', 'plateau_size')
    peak_kwargs = {k: pf[k] for k in _pf_keys if pf.get(k) is not None}

    hp_cfg        = cfg.get('high_pass', {})
    hp_enabled    = bool(hp_cfg.get('enabled', True))
    hp_window     = int(hp_cfg.get('window_size', 10000))
    hp_pf_cfg     = hp_cfg.get('peak_finding', pf)   # fall back to main peak_finding block
    hp_pf_abs     = bool(hp_pf_cfg.get('abs_value', True))
    hp_peak_kwargs = {k: hp_pf_cfg[k] for k in _pf_keys if hp_pf_cfg.get(k) is not None}

    sc_cfg         = cfg.get('step_convolution', {})
    sc_enabled     = bool(sc_cfg.get('enabled', True))
    sc_half_width  = int(sc_cfg.get('half_width', 5000))
    sc_demean      = bool(sc_cfg.get('demean', True))
    sc_pf_cfg      = sc_cfg.get('peak_finding', pf)   # fall back to main peak_finding block
    sc_pf_abs      = bool(sc_pf_cfg.get('abs_value', True))
    sc_peak_kwargs = {k: sc_pf_cfg[k] for k in _pf_keys if sc_pf_cfg.get(k) is not None}

    # ── Load data ─────────────────────────────────────────────────────────────
    event_numbers, timestamps, extra_reg1, extra_reg2, extra_reg3, window_sizes, ch_mask_bits, variances = load_data(bin_filename)

    channel_data = variances[:, channel]

    if start_idx is None:
        start_idx = 0
    if end_idx is None:
        end_idx = len(channel_data)

    channel_data_slice = channel_data[start_idx:end_idx]
    x_orig = np.arange(start_idx, end_idx)

    print(f"\nChannel:        {channel}")
    print(f"Analysis range: [{start_idx}, {end_idx})  —  {end_idx - start_idx} points")

    # ── Moving average (low-pass, for diff approach) ─────────────────────────
    smoothed = moving_average(channel_data_slice, ma_window)
    print(f"Moving average: window = {ma_window}")

    # ── Diff ──────────────────────────────────────────────────────────────────
    diffed = smoothed.copy()
    for _ in range(diff_order):
        diffed = np.diff(diffed)
    # np.diff reduces length by 1 per order; keep x aligned
    x_diff = x_orig[:len(diffed)]
    print(f"Diff order:     {diff_order}")

    # ── Peak finding on diff signal ───────────────────────────────────────────
    diff_signal = np.abs(diffed) if pf_abs else diffed
    if diff_enabled:
        peaks, _ = find_peaks(diff_signal, **peak_kwargs)
        peak_locations = x_diff[peaks]
        print(f"\nDiff approach peak-finding kwargs: {peak_kwargs}")
        print(f"Found {len(peaks)} discontinuities (diff):")
        for i, (loc, pk) in enumerate(zip(peak_locations, peaks)):
            print(f"  {i + 1:>3}: index {loc:>7}   signal value = {diff_signal[pk]:.4f}")
    else:
        print("\nDiff approach: disabled")
        peaks = np.array([], dtype=int)
        peak_locations = np.array([], dtype=int)

    # ── High-pass filter (remove slow Gaussian envelope) ─────────────────────
    if hp_enabled:
        hp_residual, hp_lowpass = high_pass_filter(channel_data_slice, hp_window)
        print(f"\nHigh-pass filter: window = {hp_window}")

        # Diff the HP residual once, then find peaks
        hp_diffed = np.diff(hp_residual)
        x_hp_diff = x_orig[:len(hp_diffed)]
        hp_signal = np.abs(hp_diffed) if hp_pf_abs else hp_diffed
        hp_peaks, _ = find_peaks(hp_signal, **hp_peak_kwargs)
        hp_peak_locations = x_hp_diff[hp_peaks]

        print(f"High-pass peak-finding kwargs: {hp_peak_kwargs}")
        print(f"Found {len(hp_peaks)} discontinuities (high-pass):")
        for i, (loc, pk) in enumerate(zip(hp_peak_locations, hp_peaks)):
            print(f"  {i + 1:>3}: index {loc:>7}   signal value = {hp_signal[pk]:.4f}")
    else:
        print("\nHigh-pass filter: disabled")
        hp_residual = hp_lowpass = hp_signal = None
        hp_peaks = np.array([], dtype=int)
        hp_peak_locations = np.array([], dtype=int)
        x_hp_diff = x_orig

    # ── Step-function convolution ─────────────────────────────────────────────
    if sc_enabled:
        sc_conv, sc_offset = step_convolve(channel_data_slice, sc_half_width, demean=sc_demean)
        x_sc = x_orig[sc_offset : sc_offset + len(sc_conv)]
        sc_signal = np.abs(sc_conv) if sc_pf_abs else sc_conv
        sc_peaks, _ = find_peaks(sc_signal, **sc_peak_kwargs)
        sc_peak_locations = x_sc[sc_peaks]

        print(f"\nStep convolution: half_width = {sc_half_width}, demean = {sc_demean}")
        print(f"Peak-finding kwargs: {sc_peak_kwargs}")
        print(f"Found {len(sc_peaks)} discontinuities (step conv):")
        for i, (loc, pk) in enumerate(zip(sc_peak_locations, sc_peaks)):
            print(f"  {i + 1:>3}: index {loc:>7}   signal value = {sc_signal[pk]:.4f}")
    else:
        print("\nStep convolution: disabled")
        sc_conv = sc_signal = None
        sc_peaks = np.array([], dtype=int)
        sc_peak_locations = np.array([], dtype=int)
        x_sc = x_orig

    # ── Plotting ──────────────────────────────────────────────────────────────
    n_panels = 1 + int(diff_enabled) + int(hp_enabled) + int(sc_enabled)
    fig_height = 4.5 * n_panels
    fig, axes = plt.subplots(n_panels, 1, figsize=(14, fig_height), sharex=True)
    if n_panels == 1:
        axes = [axes]
    _ax_iter = iter(axes)
    ax1 = next(_ax_iter)
    ax2 = next(_ax_iter) if diff_enabled else None
    ax3 = next(_ax_iter) if hp_enabled else None
    ax4 = next(_ax_iter) if sc_enabled else None

    xlim = (x_orig[0], x_orig[-1])

    # Panel 1: raw variance + short moving average + detected peaks
    ax1.plot(x_orig, channel_data_slice, '.', markersize=1.5, alpha=0.35,
             color='steelblue', label='Raw variance')
    ax1.plot(x_orig, smoothed, '-', linewidth=1.0, color='darkorange',
             label=f'Moving avg (w={ma_window})')
    if hp_enabled:
        ax1.plot(x_orig, hp_lowpass, '-', linewidth=1.2, color='purple', alpha=0.7,
                 label=f'HP low-pass (w={hp_window})')
    for i, loc in enumerate(peak_locations):
        ax1.axvline(loc, color='red', linewidth=0.9, alpha=0.7,
                    label='Diff peaks' if i == 0 else None)
    if hp_enabled:
        for i, loc in enumerate(hp_peak_locations):
            ax1.axvline(loc, color='green', linewidth=0.9, alpha=0.7, linestyle='--',
                        label='HP peaks' if i == 0 else None)
    if sc_enabled:
        for i, loc in enumerate(sc_peak_locations):
            ax1.axvline(loc, color='darkorchid', linewidth=0.9, alpha=0.7, linestyle=':',
                        label='Step conv peaks' if i == 0 else None)
    ax1.set_ylabel('Variance')
    ax1.set_title(f'Variance vs Index, Channel {channel}')
    ax1.legend(loc='upper right', fontsize=8)
    ax1.set_xlim(*xlim)

    # Panel 2: diff of smoothed signal + detected peaks
    if diff_enabled:
        diff_label = f'|diff| (order={diff_order}, w={ma_window})' if pf_abs else f'diff (order={diff_order}, w={ma_window})'
        ax2.plot(x_diff, diff_signal, '-', linewidth=0.7, color='steelblue', label=diff_label)
        ax2.plot(x_diff[peaks], diff_signal[peaks], 'v', color='red',
                 markersize=5, zorder=5, label=f'Peaks ({len(peaks)})')
        for loc in peak_locations:
            ax2.axvline(loc, color='red', linewidth=0.9, alpha=0.7)
        ax2.set_ylabel('|Δ Variance|' if pf_abs else 'Δ Variance')
        ax2.set_title(f'Diff Approach — Channel {channel}')
        ax2.legend(loc='upper right', fontsize=8)
        ax2.set_xlim(*xlim)
        if not hp_enabled and not sc_enabled:
            ax2.set_xlabel('Index')

    # Panel 3: high-pass residual + |diff(hp)| overlay + HP peaks (optional)
    if hp_enabled:
        ax3_r = ax3.twinx()
        ax3.plot(x_orig, hp_residual, '-', linewidth=0.6, color='steelblue', alpha=0.8,
                 label=f'HP residual (w={hp_window})')
        ax3_r.plot(x_hp_diff, hp_signal, '-', linewidth=0.7, color='darkorange', alpha=0.85,
                   label='|diff(HP)|')
        ax3_r.plot(x_hp_diff[hp_peaks], hp_signal[hp_peaks], 'v', color='green',
                   markersize=5, zorder=5, label=f'HP Peaks ({len(hp_peaks)})')
        for loc in hp_peak_locations:
            ax3.axvline(loc, color='green', linewidth=0.9, alpha=0.7, linestyle='--')
        ax3.set_xlabel('Index')
        ax3.set_ylabel('HP Residual', color='steelblue')
        ax3_r.set_ylabel('|diff(HP residual)|', color='darkorange')
        ax3.set_title(f'High-Pass Approach — Channel {channel}')
        lines1, labels1 = ax3.get_legend_handles_labels()
        lines2, labels2 = ax3_r.get_legend_handles_labels()
        ax3.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=8)
        ax3.set_xlim(*xlim)
        if not sc_enabled:
            ax3.set_xlabel('Index')

    # Panel 4: step-function convolution signal + peaks (optional)
    if sc_enabled:
        ax4_r = ax4.twinx()
        ax4.plot(x_sc, sc_conv, '-', linewidth=0.6, color='steelblue', alpha=0.8,
                 label=f'Step conv (hw={sc_half_width})')
        ax4_r.plot(x_sc, sc_signal, '-', linewidth=0.7, color='darkorange', alpha=0.85,
                   label='|step conv|' if sc_pf_abs else 'step conv')
        ax4_r.plot(x_sc[sc_peaks], sc_signal[sc_peaks], 'v', color='darkorchid',
                   markersize=5, zorder=5, label=f'Peaks ({len(sc_peaks)})')
        for loc in sc_peak_locations:
            ax4.axvline(loc, color='darkorchid', linewidth=0.9, alpha=0.7, linestyle=':')
        ax4.set_xlabel('Index')
        ax4.set_ylabel('Step conv', color='steelblue')
        ax4_r.set_ylabel('|Step conv|' if sc_pf_abs else 'Step conv', color='darkorange')
        ax4.set_title(f'Step Convolution, Channel {channel}')
        lines1, labels1 = ax4.get_legend_handles_labels()
        lines2, labels2 = ax4_r.get_legend_handles_labels()
        ax4.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=8)
        ax4.set_xlim(*xlim)

    fig.tight_layout()
    plt.show()
