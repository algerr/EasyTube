#!/bin/bash

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Please install Python 3 to run this application."
    exit 1
fi

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Create downloads directory if it doesn't exist
if [ ! -d "downloads" ]; then
    echo "Creating downloads directory..."
    mkdir -p downloads
fi

# Run the application
echo "Starting YouTube Downloader..."
python app.py

# Deactivate virtual environment on exit
deactivate 