import sys
import utility_functions as uf
from collections import defaultdict


def main():
    if len(sys.argv) != 2:
        print("Usage: python script.py <binary_filename>")
        sys.exit(1)

    filename = sys.argv[1]
    events = uf.read_binary_file(filename)

    event_numbers = []
    variances = []
    variance_dict = defaultdict(list)

    # Process the events
    for i, event in enumerate(events):
        data = uf.extract_data(event)
        number = data['number']
        timestamp = data['timestamp']
        variance = data['variance']
        event_numbers.append(number)
        variances.append(variance)
        variance_dict[variance].append(number)
        print(f"Event {i + 1}: Number = {number}, Timestamp = {timestamp}, Variance = {variance}")

    # Check if event numbers are sequential
    sequential = all(event_numbers[i] + 1 == event_numbers[i + 1] for i in range(len(event_numbers) - 1))
    if sequential:
        print("Event numbers are sequential.")
    else:
        print("Event numbers are not sequential.")

    # Check if all event numbers and variances are unique
    unique_event_numbers = len(event_numbers) == len(set(event_numbers))
    unique_variances = len(variances) == len(set(variances))

    if unique_event_numbers:
        print("All event numbers are unique.")
    else:
        print("Event numbers are not unique.")

    if unique_variances:
        print("All variances are unique.")
    else:
        print("Variances are not unique.")
        # Print duplicated variances and their corresponding event numbers
        for variance, numbers in variance_dict.items():
            if len(numbers) > 1:
                print(f"Variance {variance} is duplicated in event numbers: {numbers}")

    # Calculate the number of unique events by removing duplicates
    total_events = len(events)
    duplicate_variances_count = sum(len(numbers) - 1 for numbers in variance_dict.values() if len(numbers) > 1)
    unique_events = total_events - duplicate_variances_count
    print(f"Number of unique events: {unique_events}")

if __name__ == "__main__":
    main()