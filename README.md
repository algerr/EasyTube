# YouTube Downloader

A simple, user-friendly web application for downloading YouTube videos and audio.

## Features

- Download YouTube videos in various quality options
- Extract audio from YouTube videos (MP3 format)
- Real-time download progress tracking
- Beautiful, responsive UI with animated background
- Error handling and user feedback

## Requirements

- Python 3.6+
- Flask
- yt-dlp

## Installation

1. Clone this repository:
```
git clone https://github.com/lsb/youtube-downloader.git
cd youtube-downloader
```

2. Install the required dependencies:
```
pip install flask yt-dlp
```

3. Run the application:
```
python app.py
```

4. Open your browser and navigate to `http://127.0.0.1:5000`

## Usage

1. Enter a YouTube URL in the input field
2. Select whether you want to download the video or just the audio
3. Choose your preferred quality option
4. Wait for the download to complete
5. The file will be automatically downloaded to your computer

## License

This project is open source and available under the MIT License.

## Acknowledgements

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) for the YouTube downloading functionality
- [Flask](https://flask.palletsprojects.com/) for the web framework 