#!/usr/bin/env python3
"""
Somali Subtitle Generator Web Application
Run this script to start the web server
"""

import os
import sys

def check_requirements():
    """Check if required packages are installed"""
    try:
        import flask
        import pandas
        import librosa
        import numpy
        import speech_recognition
        import pydub
        import soundfile
        print("✓ All required packages are installed")
        return True
    except ImportError as e:
        print(f"✗ Missing required package: {e}")
        print("Please install requirements with: pip install -r requirements.txt")
        return False

def main():
    print("=== Somali Subtitle Generator Web App ===")
    print()
    
    # Check requirements
    if not check_requirements():
        sys.exit(1)
    
    # Check if dataset exists
    if not os.path.exists("dataset"):
        print("Warning: Dataset directory not found")
        print("The app will still work but may have reduced accuracy")
        print()
    
    # Start the Flask app
    print("Starting web server...")
    print("Open your browser and go to: http://localhost:5000")
    print("Press Ctrl+C to stop the server")
    print()
    
    try:
        from app import app
        app.run(debug=True, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        print("\nServer stopped.")
    except Exception as e:
        print(f"Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
