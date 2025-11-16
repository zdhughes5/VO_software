import  utility_functions as uf
import sys

def main():
    if len(sys.argv) < 3:
        print("Usage: python process_to_fits.py <binary_filename> <fits_filename> [max_events] [--incremental] [--batch-size N]")
        print("  --incremental: Process file in batches to save memory (default batch_size=1000)")
        print("  --batch-size N: Set batch size for incremental processing")
        sys.exit(1)

    binary_filename = sys.argv[1]
    fits_filename = sys.argv[2]
    
    # Parse optional arguments
    max_events = None
    incremental = False
    batch_size = 1000
    
    i = 3
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--incremental':
            incremental = True
        elif arg == '--batch-size':
            if i + 1 < len(sys.argv):
                batch_size = int(sys.argv[i + 1])
                i += 1
            else:
                print("Error: --batch-size requires a value")
                sys.exit(1)
        else:
            # Assume it's max_events
            max_events = int(arg)
        i += 1
    
    if incremental:
        print(f"Processing {binary_filename} -> {fits_filename} (max_events: {max_events if max_events else 'all'}, incremental mode, batch_size: {batch_size})")
        uf.process_and_save_to_fits_incrementally(binary_filename, fits_filename, max_events, batch_size)
    else:
        print(f"Processing {binary_filename} -> {fits_filename} (max_events: {max_events if max_events else 'all'})")
        uf.process_and_save_to_fits(binary_filename, fits_filename, max_events)
    
    print(f"Successfully created {fits_filename}")

if __name__ == "__main__":
    main()