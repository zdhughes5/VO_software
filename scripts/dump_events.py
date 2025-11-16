import sys
from utility_functions import dump_events

def main():
    if len(sys.argv) != 2:
        print("Usage: python run_dump_events.py <binary_filename>")
        sys.exit(1)

    filename = sys.argv[1]
    dump_events(filename)

if __name__ == "__main__":
    main()