import  utility_functions as uf
import sys

def main():
    if len(sys.argv) != 3:
        print("Usage: python utility_functions.py <binary_filename> <fits_filename>")
        sys.exit(1)

    binary_filename = sys.argv[1]
    fits_filename = sys.argv[2]
    uf.process_and_save_to_fits_incrementally(binary_filename, fits_filename)

if __name__ == "__main__":
    main()