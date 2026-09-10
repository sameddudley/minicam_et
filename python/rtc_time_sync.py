#!/usr/bin/env python3
"""
Auto-sync ESP32 RTC time via serial when the device connects.
This script watches the serial port and automatically sends the current time
in the SETTIME format whenever the ESP32 boots.
"""

import serial
import serial.tools.list_ports
import time
from datetime import datetime

# Configuration
BAUD_RATE = 115200
TIMEOUT = 2

def find_esp32_port():
    """Find the COM port of the connected ESP32"""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        # Look for ESP32-specific identifiers
        if 'ESP32' in port.description or 'CH340' in port.description or 'USB' in port.description:
            print(f"Found ESP32 on port: {port.device}")
            return port.device
    return None

def send_time_sync(port_name):
    """Connect to ESP32 and send current time via SETTIME command"""
    try:
        # Open serial connection
        ser = serial.Serial(port_name, BAUD_RATE, timeout=TIMEOUT)
        time.sleep(1)  # Give the device time to settle
        
        # Get current time
        now = datetime.now()
        year = now.year
        month = now.month
        day = now.day
        hour = now.hour
        minute = now.minute
        second = now.second
        
        # Format the SETTIME command
        command = f"SETTIME {year},{month},{day},{hour},{minute},{second}\n"
        
        print(f"Connected to {port_name}")
        print(f"Sending time: {year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}")
        
        # Send the command
        ser.write(command.encode())
        
        # Read response from ESP32
        time.sleep(0.5)
        while ser.in_waiting:
            response = ser.readline().decode('utf-8', errors='ignore').strip()
            if response:
                print(f"ESP32: {response}")
        
        ser.close()
        print("Time sync complete!")
        return True
        
    except serial.SerialException as e:
        print(f"Serial error: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def watch_for_device():
    """Continuously watch for ESP32 and sync time when it connects"""
    known_ports = set()
    
    print("Watching for ESP32 connections... (Press Ctrl+C to stop)")
    print("Make sure your ESP32 is connected via USB\n")
    
    try:
        while True:
            # Get current list of ports
            ports = serial.tools.list_ports.comports()
            current_ports = {port.device for port in ports}
            
            # Check for new connections
            new_ports = current_ports - known_ports
            
            if new_ports:
                for port_device in new_ports:
                    port_info = next((p for p in ports if p.device == port_device), None)
                    if port_info and ('ESP32' in port_info.description or 'CH340' in port_info.description or 'USB' in port_info.description):
                        print(f"\n✓ New device detected: {port_device}")
                        time.sleep(2)  # Wait for bootloader to finish
                        send_time_sync(port_device)
                        print()
            
            known_ports = current_ports
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping...")

if __name__ == "__main__":
    import sys
    
    # Check if pyserial is installed
    try:
        import serial
    except ImportError:
        print("Error: pyserial not installed")
        print("Install it with: pip install pyserial")
        sys.exit(1)
    
    # Option 1: Watch mode (recommended) - automatically detects when ESP32 connects
    watch_for_device()
    
    # Option 2: Manual mode - if you want to specify the port
    # port = "COM3"  # Change to your ESP32's port (COM3, COM4, etc. on Windows; /dev/ttyUSB0 on Linux)
    # send_time_sync(port)
