import sys
import utility_functions as uf

def main():
    if len(sys.argv) != 2:
        print("Usage: python load_binary_as_df.py <binary_filename>")
        sys.exit(1)

    filename = sys.argv[1]
    processor = uf.DataProcessor(filename)
    df = processor.get_dataframe()
    print(df)

    return processor

if __name__ == "__main__":
    processor = main()
    processor.plot_with_matplotlib(1)