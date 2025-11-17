#!/usr/bin/env python
"""
Utility script to explore IBT file structure and available data.
Run this to understand what's actually available in the pyirsdk library.

Usage:
    python explore_ibt.py /path/to/file.ibt
"""

import sys
import irsdk
import json
from pprint import pprint

def explore_ibt_file(file_path):
    """Explore an IBT file and print all available data."""

    print("=" * 80)
    print("IBT File Explorer")
    print("=" * 80)
    print(f"\nFile: {file_path}\n")

    # Create IBT object
    ibt = irsdk.IBT()

    print("\n1. IBT Object Methods and Attributes:")
    print("-" * 80)
    methods = [m for m in dir(ibt) if not m.startswith('_')]
    for method in methods:
        attr = getattr(ibt, method)
        print(f"  {method:30s} - {type(attr).__name__}")

    # Open the file
    print("\n2. Opening file...")
    print("-" * 80)
    try:
        ibt.open(file_path)
        print("  ✓ File opened successfully")
    except Exception as e:
        print(f"  ✗ Error opening file: {e}")
        return

    # Check what's available after opening
    print("\n3. Available Attributes After Opening:")
    print("-" * 80)
    for attr_name in methods:
        try:
            attr = getattr(ibt, attr_name)
            if callable(attr):
                print(f"  {attr_name:30s} - Method")
            else:
                print(f"  {attr_name:30s} - {type(attr).__name__}: {str(attr)[:50]}")
        except Exception as e:
            print(f"  {attr_name:30s} - Error: {e}")

    # Try to extract session info from the memory-mapped file
    print("\n4. Extracting Session Info from IBT Header:")
    print("-" * 80)

    try:
        # Access the header to get session info location
        header = ibt._header
        session_info_offset = header.session_info_offset
        session_info_len = header.session_info_len

        print(f"  Session info offset: {session_info_offset}")
        print(f"  Session info length: {session_info_len}")

        # Extract YAML session info from shared memory
        YAML_CODE_PAGE = 'cp1252'
        session_info_yaml = ibt._shared_mem[session_info_offset:session_info_offset + session_info_len]
        session_info_yaml = session_info_yaml.rstrip(b'\x00').decode(YAML_CODE_PAGE)

        # Parse YAML
        import yaml
        try:
            from yaml.cyaml import CSafeLoader as YamlSafeLoader
        except ImportError:
            from yaml import SafeLoader as YamlSafeLoader

        session_info = yaml.load(session_info_yaml, Loader=YamlSafeLoader)

        if session_info:
            print(f"\n  ✓ Successfully parsed session info!")
            print(f"  Top-level keys: {list(session_info.keys())}")

            # Extract useful information
            if 'WeekendInfo' in session_info:
                weekend_info = session_info['WeekendInfo']
                print(f"\n  Weekend Info:")
                print(f"    Track Name: {weekend_info.get('TrackDisplayName', 'N/A')}")
                print(f"    Track Config: {weekend_info.get('TrackConfigName', 'N/A')}")
                print(f"    Track Length: {weekend_info.get('TrackLength', 'N/A')}")
                print(f"    Track Type: {weekend_info.get('TrackType', 'N/A')}")
                print(f"    Air Temp: {weekend_info.get('TrackAirTemp', 'N/A')}")
                print(f"    Track Temp: {weekend_info.get('TrackSurfaceTemp', 'N/A')}")
                print(f"    Weather: {weekend_info.get('TrackWeatherType', 'N/A')}")
                print(f"    Event Date: {weekend_info.get('TrackWeekendStartDate', 'N/A')}")

            if 'DriverInfo' in session_info:
                driver_info = session_info['DriverInfo']
                drivers = driver_info.get('Drivers', [])
                if drivers:
                    print(f"\n  Driver Info (Player):")
                    player = drivers[0]
                    print(f"    Name: {player.get('UserName', 'N/A')}")
                    print(f"    Car: {player.get('CarScreenName', 'N/A')}")
                    print(f"    Car Class: {player.get('CarClassShortName', 'N/A')}")
                    print(f"    Car Number: {player.get('CarNumber', 'N/A')}")

            if 'SessionInfo' in session_info:
                sessions = session_info['SessionInfo'].get('Sessions', [])
                print(f"\n  Session Info:")
                print(f"    Total sessions: {len(sessions)}")
                for i, session in enumerate(sessions):
                    print(f"    Session {i}: {session.get('SessionType', 'N/A')} - {session.get('SessionLaps', 'N/A')} laps")

    except Exception as e:
        print(f"  Error extracting session info: {e}")
        import traceback
        traceback.print_exc()

    # Get all available variable names
    print("\n5. Available Telemetry Channels:")
    print("-" * 80)
    try:
        var_names = ibt.var_headers_names
        print(f"  Total channels: {len(var_names)}")
        print(f"  First 20 channels:")
        for i, name in enumerate(var_names[:20], 1):
            print(f"    {i:3d}. {name}")

        if len(var_names) > 20:
            print(f"    ... and {len(var_names) - 20} more")
    except Exception as e:
        print(f"  Error getting channel names: {e}")

    # Try to get data for a few common channels
    print("\n6. Sample Data from Common Channels:")
    print("-" * 80)

    test_channels = [
        'Speed', 'Throttle', 'Brake', 'Gear', 'RPM',
        'Lat', 'Lon', 'LapDist', 'SessionTime'
    ]

    for channel in test_channels:
        try:
            # get_all(key) returns a list of all values for that channel
            data = ibt.get_all(channel)
            if data is not None:
                if hasattr(data, '__len__'):
                    print(f"  {channel:15s} - Array with {len(data)} samples")
                    if len(data) > 0:
                        print(f"                    First value: {data[0]}")
                        print(f"                    Last value: {data[-1]}")
                        # Show some stats for speed
                        if channel == 'Speed' and len(data) > 0:
                            print(f"                    Max: {max(data):.2f}")
                            print(f"                    Avg: {sum(data)/len(data):.2f}")
                else:
                    print(f"  {channel:15s} - {data}")
            else:
                print(f"  {channel:15s} - None")
        except Exception as e:
            print(f"  {channel:15s} - Error: {e}")

    # Test get() with specific index
    print("\n7. Testing get(index, key) method:")
    print("-" * 80)
    try:
        # Get the first sample (index 0) for a few channels
        print("  Sample at index 0:")
        for channel in ['Speed', 'Throttle', 'Brake', 'Gear']:
            value = ibt.get(0, channel)
            print(f"    {channel:15s}: {value}")

        # Get the last sample
        last_index = ibt._disk_header.session_record_count - 1
        print(f"\n  Sample at last index ({last_index}):")
        for channel in ['Speed', 'Throttle', 'Brake', 'Gear']:
            value = ibt.get(last_index, channel)
            print(f"    {channel:15s}: {value}")

    except Exception as e:
        print(f"  Error calling get(): {e}")

    # Close file
    print("\n8. Closing file...")
    print("-" * 80)
    try:
        ibt.close()
        print("  ✓ File closed successfully")
    except Exception as e:
        print(f"  ✗ Error closing file: {e}")

    print("\n" + "=" * 80)
    print("Exploration complete!")
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python explore_ibt.py /path/to/file.ibt")
        print("\nExample:")
        print("  python explore_ibt.py ~/Documents/iRacing/telemetry/mazda_mx5_cup/session.ibt")
        sys.exit(1)

    file_path = sys.argv[1]
    explore_ibt_file(file_path)
