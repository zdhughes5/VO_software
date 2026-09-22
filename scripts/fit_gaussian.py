import sys
import yaml
import numpy as np
import matplotlib.pyplot as plt
from utility_functions import read_events_from_binary_file, parse_data_from_event
from scipy.optimize import differential_evolution
from scipy.optimize import curve_fit


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


def broken_gaussian(x, A, mu, sigma, *args):

    if len(args) % 2 != 0 and len(args) > 0:
        raise ValueError(f"*args must contain an even number of elements and be more than zero, got {len(args)}.")
    
    regions = [(args[i], args[i + 1]) for i in range(0, len(args), 2)]
    
    y = A * np.exp(-0.5 * ((x - mu) / sigma) ** 2) + regions[0][1]

    

    # prev_discontinuity = 0
    # for i, (discontinuity, offset) in enumerate(regions):
    #     discontinuity = int(discontinuity)
    #     if i == len(regions) - 1:
    #         y[prev_discontinuity:] += offset
    #     elif i == 0:
    #         y[0:discontinuity] += offset
    #     else:
    #         y[prev_discontinuity:discontinuity] += offset
    #     prev_discontinuity = discontinuity

    # prev_discontinuity = 0
    # for i, (discontinuity, offset) in enumerate(regions):
    #     discontinuity = int(discontinuity)
    #     if i == 0:
    #         prev_discontinuity = discontinuity
    #         continue  # skip the first discontinuity since it doesn't affect the fit region
    #     elif i < len(regions) - 1:
    #         y[prev_discontinuity:discontinuity] += offset
    #         prev_discontinuity = discontinuity
    #     else:
    #         y[prev_discontinuity:] += offset

    prev_discontinuity = 0
    for i, (discontinuity, offset) in enumerate(regions):
        discontinuity = int(discontinuity)
        if i == 0:
            prev_discontinuity = discontinuity
            continue  # skip the first discontinuity since it doesn't affect the fit region
        elif i < len(regions):
            y[prev_discontinuity:discontinuity] += offset
            prev_discontinuity = discontinuity
    else:
        y[discontinuity:] += offset

    return y  # * (x >= mu)

class SSECalculator:
	
    ''' A class to calculate the sum of square error between a function and some data. '''

	# Set the functions and data to be used.
    def __init__(self, xData, yData, func, weights=None):

        self.func = func
        self.xData = xData
        self.yData = yData
        if weights is None:
            self.weights = np.ones(len(self.yData))
        else:
            self.weights = weights

	# Calculate the SSE given test parameters of the function.
    def getSSE(self, parameterTuple):
        error = self.yData - self.func(self.xData, *parameterTuple)
        errorSq = self.weights * error ** 2
        return np.sum(np.sqrt(errorSq))
     

if __name__ == "__main__":
    if len(sys.argv) < 2 or len(sys.argv) > 4:
        print(f"Usage: {sys.argv[0]} <binary_file> [channel_number] [guesses.yaml]")
        print(f"  binary_file:   Path to the binary file")
        print(f"  channel_number: Channel to plot (default: 0)")
        print(f"  guesses.yaml:  Optional YAML file with fit parameters (skips interactive prompts)")
        sys.exit(1)

    channel    = int(sys.argv[2]) if len(sys.argv) >= 3 else 0
    yaml_file  = sys.argv[3] if len(sys.argv) == 4 else None
    filename   = sys.argv[1]
    event_numbers, timestamps, extra_reg1, extra_reg2, extra_reg3, window_sizes, ch_mask_bits, variances = load_data(filename)

    # Show variance vs index so the user can identify the signal region and discontinuities
    all_indices = np.arange(len(variances))
    plt.figure()
    plt.plot(all_indices, variances[:, channel], '.', markersize=2)
    plt.xlabel('Index')
    plt.ylabel('Variance')
    plt.title(f'Variance vs Index — Channel {channel}')
    plt.tight_layout()
    plt.show(block=False)
    plt.pause(0.5)

    # Load guesses from YAML or prompt interactively
    if yaml_file is not None:
        with open(yaml_file, 'r') as f:
            guesses = yaml.safe_load(f)
        start_idx = int(guesses['start_idx'])
        end_idx   = int(guesses['end_idx'])
        disc_guesses = [
            (int(d['location']) - start_idx, float(d['offset']))
            for d in guesses.get('discontinuities', [])
        ]
        ig = guesses['initial_guess']
        p0_A     = float(ig['A'])
        p0_mu    = float(ig['mu']) - start_idx   # convert to sliced-array index
        p0_sigma = float(ig['sigma'])
        print(f"Loaded guesses from {yaml_file}")
    else:
        # Prompt for the fit range
        start_idx = int(input("Enter starting index for fit: "))
        end_idx   = int(input("Enter ending index for fit:   "))

        # Prompt for initial guesses of core parameters
        print("\nEnter initial guesses for core parameters:")
        p0_A     = float(input("  A (amplitude):         "))
        p0_mu    = float(input("  mu (original index):   ")) - start_idx
        p0_sigma = float(input("  sigma:                 "))

        # Prompt for discontinuity guesses
        n_disc = int(input("\nEnter number of discontinuities: "))
        disc_guesses = []
        for i in range(n_disc):
            loc = int(input(f"  Discontinuity {i+1} location (original plot index): "))
            off = float(input(f"  Discontinuity {i+1} offset guess: "))
            disc_guesses.append((loc - start_idx, off))  # convert to sliced-array index

    # Slice data to the fit region and re-index from 0 (broken_gaussian uses array indices)
    y_fit = variances[start_idx:end_idx, channel]
    x_fit = np.arange(len(y_fit))
    n_fit = len(x_fit)
    print(f"\nFitting over original indices [{start_idx}, {end_idx}) — {n_fit} points.")

    weights = np.ones_like(y_fit)
    xErrFunc = SSECalculator(x_fit, y_fit, broken_gaussian, weights=weights).getSSE

    # Build bounds: (A, mu, sigma) then one (location, offset) pair per discontinuity
    y_range = np.max(y_fit) - np.min(y_fit)
    #xBounds = [
    #    (0, y_range * 2),   # A
    #    (0, n_fit),          # mu
    #    (0, n_fit),          # sigma
    #    (0, 200),   # c
    #]

    xBounds = [
        (0, 10),   # A
        (50000, 145000),          # mu
        (0, 50000),          # sigma
    ]
    #loc_margin = max(1, int(n_fit * 0.05))
    loc_margin = 500
    off_margin = 4.0
    for i, (loc, off) in enumerate(disc_guesses):
        xBounds.append((max(0, loc - loc_margin), min(n_fit, loc + loc_margin)))
        if i == 0:
            xBounds.append((50, 200))  # first offset absorbs the baseline (c)
        else:
            xBounds.append((off - off_margin, off + off_margin))

    bound_labels = ['A', 'mu', 'sigma']
    for i in range(len(disc_guesses)):
        bound_labels += [f'disc_{i+1}_loc', f'disc_{i+1}_offset']
    print("Parameter bounds:")
    for label, bound in zip(bound_labels, xBounds):
        print(f"  {label:<20} {bound}")

    # Build initial guess vector (x0) aligned with xBounds
    x0 = [p0_A, p0_mu, p0_sigma]
    for loc, off in disc_guesses:
        x0.append(float(loc))
        x0.append(off)
    x0 = np.array(x0)
    print("Initial guess:")
    for label, val in zip(bound_labels, x0):
        print(f"  {label:<20} {val}")

    # Perform differential evolution optimization
    opt = differential_evolution(xErrFunc, xBounds, x0=x0, seed=3, workers=24, updating='deferred', popsize=200)
    print(f"\nOptimization {'succeeded' if opt.success else 'FAILED'}: {opt.message}")
    print(f"  SSE:         {opt.fun:.6g}")
    print(f"  Iterations:  {opt.nit}  |  Function evaluations: {opt.nfev}")
    print("Optimized parameters:")
    for label, val in zip(bound_labels, opt.x):
        # Discontinuity locations are in sliced-array space; convert back to original indices
        if label.endswith('_loc'):
            print(f"  {label:<20} {val + start_idx:.2f}  (original index)")
        else:
            print(f"  {label:<20} {val:.6g}")

    # Plot data and fit
    y_fitted = broken_gaussian(x_fit, *opt.x)
    opt_A, opt_mu, opt_sigma = opt.x[0], opt.x[1], opt.x[2]

    # Convert from fit-slice index space to zeroed time (timestamps - timestamps[0])
    t_fit = timestamps[start_idx:end_idx] - timestamps[0]
    mu_idx = start_idx + int(round(opt_mu))
    mu_time = timestamps[mu_idx] - timestamps[0]
    sigma_end_idx = min(mu_idx + int(round(opt_sigma)), end_idx - 1)
    sigma_time = timestamps[sigma_end_idx] - timestamps[mu_idx]

    fig, ax = plt.subplots()
    # Sigma shading (3 → 1 so inner bands paint over outer ones)
    for n, alpha, color in [(3, 0.12, 'royalblue'), (2, 0.20, 'royalblue'), (1, 0.35, 'royalblue')]:
        ax.axvspan(mu_time - n * sigma_time, mu_time + n * sigma_time,
                   alpha=alpha, color=color, label=f'{n}σ region')
    ax.plot(t_fit, y_fit, '.', markersize=2, label='Data', zorder=3)
    ax.plot(t_fit, y_fitted, '-', linewidth=1.5, label='Fit', zorder=4)
    ax.axvline(mu_time, color='royalblue', linewidth=0.8, linestyle='--', label=f'μ = {mu_time:.1f},  σ = {sigma_time:.1f}')
    ax.set_xlabel(f'Time (zeroed from t[0] = {timestamps[0]})')
    ax.set_ylabel('Variance')
    ax.set_title(f'Fit Result — Channel {channel}')
    ax.legend()
    fig.tight_layout()
    plt.show()

