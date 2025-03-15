# file: app.py

from flask import Flask, request, render_template, send_file, redirect, url_for, session, jsonify
import subprocess
import json
import os
import uuid
import threading
import time
import re
from datetime import datetime
import random

app = Flask(__name__)
app.secret_key = os.urandom(24)
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Store download progress information
download_progress = {}

def get_video_info(url):
    result = subprocess.run(
        ["yt-dlp", "--dump-json", url], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise Exception("Error fetching video info")
    return json.loads(result.stdout)

def extract_resolution_number(res):
    if isinstance(res, str):
        if 'x' in res:
            try:
                return int(res.split('x')[1])
            except:
                return 0
        if 'p' in res:
            try:
                return int(res.replace('p', ''))
            except:
                return 0
    return 0

def extract_format_choices(formats, mode):
    choices = []
    if mode == "mp3":
        # Filter audio formats
        audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") == "none"]
        
        # Group audio formats by similar file sizes (within 10% of each other)
        size_groups = {}
        for af in audio_formats:
            if not af.get("filesize") or not af.get("format_id"):
                continue
                
            size_mb = round(af["filesize"] / (1024 * 1024), 2)
            # Use size range as key to group similar sizes
            size_key = int(size_mb / 10)  # Group by each 10MB range
            
            if size_key not in size_groups or af.get("abr", 0) > size_groups[size_key].get("abr", 0):
                size_groups[size_key] = {
                    "format_id": af["format_id"],
                    "size_mb": size_mb,
                    "abr": af.get("abr", 0)
                }
        
        # Create choices from the best format in each size group
        for group in sorted(size_groups.keys(), reverse=True):  # Sort by size (largest first)
            format_info = size_groups[group]
            # Simplified label without bitrate information
            label = f"Audio | {format_info['size_mb']}MB"
            choices.append({"id": format_info["format_id"], "label": label})
            
        return choices

    video_formats = [f for f in formats if f.get("vcodec") != "none" and f.get("ext") == "mp4"]
    audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") == "none"]

    best_audio = max(audio_formats, key=lambda a: a.get("filesize", 0), default=None)
    if not best_audio:
        return choices

    resolution_map = {}
    for vf in video_formats:
        if not vf.get("filesize") or not vf.get("format_id"):
            continue
        height = vf.get("height")
        if not height:
            continue
        res = f"{height}p"
        total_size = vf.get("filesize", 0) + best_audio.get("filesize", 0)
        if res not in resolution_map or total_size > resolution_map[res]["total_size"]:
            resolution_map[res] = {
                "id": f"{vf['format_id']}+{best_audio['format_id']}",
                "label": f"Video | {res} | {round(total_size / (1024 * 1024), 2)}MB",
                "total_size": total_size,
                "height": height
            }

    # Add user-friendly quality descriptions to video options
    formatted_choices = []
    for res in sorted(resolution_map.keys(), key=extract_resolution_number, reverse=True):
        entry = resolution_map[res]
        height = entry.get("height", 0)
        size_mb = round(entry["total_size"] / (1024 * 1024), 2)
        
        # Add quality description based on resolution
        quality_desc = ""
        if height >= 1080:
            quality_desc = "High Quality"
        elif height >= 720:
            quality_desc = "Medium Quality"
        elif height >= 480:
            quality_desc = "Standard Quality"
        else:
            quality_desc = "Low Quality"
            
        label = f"Video | {quality_desc} ({res}) | {size_mb}MB"
        formatted_choices.append({"id": entry["id"], "label": label})
    
    return formatted_choices

def download_video_with_progress(url, format_id, download_id, video_title, filename, format_mode):
    """Download video with progress tracking"""
    try:
        # Determine output format
        is_audio = format_mode == "mp3"  # Use passed format_mode instead of session
        output_path = os.path.join(DOWNLOAD_FOLDER, filename)
        
        # Build command
        command = ["yt-dlp"]
        
        if is_audio:
            command.extend([
                "-f", format_id,
                "-x",  # Extract audio
                "--audio-format", "mp3",
                "--audio-quality", "0",  # Best quality
            ])
        else:
            command.extend([
                "-f", format_id,
                "--merge-output-format", "mp4",
            ])
        
        # Add common parameters
        command.extend([
            "-o", output_path,
            "--newline",  # Important for parsing progress
            url
        ])
        
        # Start the download process
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Parse output for progress updates
        for line in process.stdout:
            # Update progress based on output
            update_progress_from_output(line, download_id)
        
        # Wait for process to complete
        process.wait()
        
        # Check if download was successful
        if process.returncode == 0:
            # Update status to indicate post-processing
            download_progress[download_id]['status'] = 'Post-processing file...'
            download_progress[download_id]['progress'] = 95  # Set to 95% to show it's almost done
            
            # Log the post-processing start
            print(f"Starting post-processing for {output_path}")
            
            # Add a significant delay to ensure file is fully written and processed
            time.sleep(2)
            download_progress[download_id]['status'] = 'Optimizing media...'
            time.sleep(2)
            download_progress[download_id]['status'] = 'Finalizing file...'
            time.sleep(1)
            
            # Verify file exists
            if not os.path.exists(output_path):
                raise Exception(f"File not found after download: {output_path}")
                
            # Verify file size
            file_size = os.path.getsize(output_path)
            if file_size == 0:
                raise Exception(f"Downloaded file is empty: {output_path}")
                
            # Add another delay to ensure file is fully processed
            download_progress[download_id]['status'] = 'Preparing file for download...'
            time.sleep(2)
                
            # Set final status and progress exactly once
            download_progress[download_id]['progress'] = 100
            download_progress[download_id]['status'] = 'Download complete!'
            download_progress[download_id]['file_ready'] = True
            
            # Log success
            print(f"Download successful: {output_path}, Size: {file_size} bytes")
            
            return output_path
        else:
            download_progress[download_id]['status'] = 'Download failed'
            raise Exception("Download process failed with return code: " + str(process.returncode))
            
    except Exception as e:
        download_progress[download_id]['status'] = f'Error: {str(e)}'
        print(f"Download error: {str(e)}")
        raise

def update_progress_from_output(line, download_id):
    """Parse yt-dlp output to update download progress"""
    
    # Skip updates if progress is already at 100%
    if download_id in download_progress and download_progress[download_id]['progress'] >= 100:
        return
    
    # Extract download percentage
    percent_match = re.search(r'(\d+\.\d+)%', line)
    if percent_match:
        try:
            percent = float(percent_match.group(1))
            # Cap progress at 100%
            download_progress[download_id]['progress'] = min(percent, 100)
        except:
            pass
    
    # Extract download speed
    speed_match = re.search(r'(\d+\.\d+\s*[KMG]iB/s)', line)
    if speed_match:
        download_progress[download_id]['speed'] = speed_match.group(1)
    
    # Extract ETA
    eta_match = re.search(r'ETA\s+(\d+:\d+)', line)
    if eta_match:
        download_progress[download_id]['eta'] = eta_match.group(1)
    
    # Extract file size
    size_match = re.search(r'(\d+\.\d+\s*[KMG]iB)\s+of\s+(\d+\.\d+\s*[KMG]iB)', line)
    if size_match:
        download_progress[download_id]['downloaded'] = size_match.group(1)
        download_progress[download_id]['total_size'] = size_match.group(2)
    
    # Extract status messages
    if 'Downloading' in line:
        download_progress[download_id]['status'] = 'Downloading...'
    elif 'Merging' in line:
        download_progress[download_id]['status'] = 'Merging formats...'
    elif 'Extracting audio' in line:
        download_progress[download_id]['status'] = 'Extracting audio...'
    elif 'Converting' in line:
        download_progress[download_id]['status'] = 'Converting format...'
    elif '[download] 100%' in line or 'Deleting original file' in line:
        download_progress[download_id]['status'] = 'Finalizing download...'

def initialize_download_progress(download_id, url, format_id, video_title, filename, file_path):
    """Initialize the download progress tracking for a new download"""
    download_progress[download_id] = {
        'progress': 0,
        'status': 'Starting download...',
        'speed': '0 KiB/s',
        'downloaded': '0 MB',
        'total_size': 'Unknown',
        'eta': 'Unknown',
        'download_url': f'/download_file/{filename}',
        'title': video_title,
        'file_path': file_path,
        'file_ready': False,  # Flag to indicate if file is ready for download
        'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Log the download initialization
    print(f"Initialized download tracking for {download_id}: {url} -> {file_path}")

def is_valid_youtube_url(url):
    """Check if the URL is a valid YouTube URL"""
    youtube_regex = (
        r'(https?://)?(www\.)?'
        r'(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')
    
    match = re.match(youtube_regex, url)
    return match is not None

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        url = request.form.get('url')
        format_mode = request.form.get('format')
        
        # Validate YouTube URL
        if not is_valid_youtube_url(url):
            return render_template('index.html', error="Please enter a valid YouTube URL")
        
        # Fix format_mode value to match the radio button value
        if format_mode == "video":
            format_mode = "video"
        elif format_mode == "mp3":
            format_mode = "mp3"
            
        try:
            video_info = get_video_info(url)
            formats = video_info.get("formats", [])
            choices = extract_format_choices(formats, format_mode)
            session['url'] = url
            session['format_mode'] = format_mode
            session['formats'] = choices
            session['video_title'] = video_info.get('title', 'Video')
            return render_template('select_format.html', title=video_info.get('title'), choices=choices)
        except Exception as e:
            error_message = str(e)
            print(f"Error processing URL: {error_message}")
            return render_template('index.html', error=f"Error: {error_message}")

    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    format_id = request.form.get('format')
    url = session.get('url')
    video_title = session.get('video_title', 'Video')
    format_mode = session.get('format_mode')  # Get format_mode from session
    
    if not url or not format_id:
        return redirect(url_for('index'))
    
    # Generate a unique download ID and filename
    download_id = str(uuid.uuid4())
    ext = "mp3" if format_mode == "mp3" else "mp4"
    filename = f"{uuid.uuid4()}.{ext}"
    
    # Ensure we have the absolute path
    file_path = os.path.abspath(os.path.join(DOWNLOAD_FOLDER, filename))
    
    # Make sure the download directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # Initialize progress tracking
    initialize_download_progress(download_id, url, format_id, video_title, filename, file_path)
    
    # Start download in a background thread
    download_thread = threading.Thread(
        target=download_video_with_progress,
        args=(url, format_id, download_id, video_title, filename, format_mode)
    )
    download_thread.daemon = True
    download_thread.start()
    
    # Redirect to progress page
    return render_template('download_progress.html', download_id=download_id, title=video_title)

def cleanup_old_downloads():
    """Clean up old download progress entries to prevent memory leaks"""
    current_time = datetime.now()
    to_remove = []
    
    for download_id, info in download_progress.items():
        # Parse the start time
        try:
            start_time = datetime.strptime(info.get('start_time', ''), '%Y-%m-%d %H:%M:%S')
            # If download is older than 1 hour, remove it
            if (current_time - start_time).total_seconds() > 3600:
                to_remove.append(download_id)
        except:
            # If we can't parse the start time, assume it's old
            to_remove.append(download_id)
    
    # Remove old entries
    for download_id in to_remove:
        del download_progress[download_id]
        print(f"Cleaned up old download: {download_id}")

@app.route('/download_status/<download_id>')
def download_status(download_id):
    """Return the current download status as JSON"""
    # Clean up old downloads periodically
    if random.random() < 0.1:  # 10% chance to clean up on each status check
        cleanup_old_downloads()
        
    if download_id in download_progress:
        return jsonify(download_progress[download_id])
    return jsonify({'status': 'Download not found', 'progress': 0})

@app.route('/download_file/<filename>')
def download_file(filename):
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    
    # Log the download attempt
    print(f"Attempting to download file: {file_path}")
    
    # Check if file exists
    if not os.path.exists(file_path):
        # Log the error
        print(f"Error: File not found at {file_path}")
        
        # Return a user-friendly error page
        return render_template('error.html', 
                              error_message="The download file could not be found. Please try downloading again.",
                              back_url=url_for('index'))
    
    # Check if file is empty
    if os.path.getsize(file_path) == 0:
        print(f"Error: File exists but is empty: {file_path}")
        return render_template('error.html',
                              error_message="The downloaded file appears to be empty. Please try downloading again.",
                              back_url=url_for('index'))
    
    # Check if file is still being processed
    # Find the download_id for this file
    for download_id, info in download_progress.items():
        if info.get('file_path') == file_path and not info.get('file_ready', False):
            print(f"File is still being processed: {file_path}")
            return render_template('error.html',
                                  error_message="Your file is still being processed. Please wait a moment and try again.",
                                  back_url=request.referrer or url_for('index'))
    
    try:
        # Add a small delay before sending the file
        time.sleep(0.5)
        
        # Log successful download
        print(f"Sending file: {file_path}")
        return send_file(file_path, as_attachment=True)
    except Exception as e:
        print(f"Error sending file: {str(e)}")
        return render_template('error.html', 
                              error_message=f"An error occurred while downloading the file: {str(e)}. Please try again.",
                              back_url=url_for('index'))

@app.route('/check_file_ready/<filename>')
def check_file_ready(filename):
    """Check if a file is ready for download"""
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    
    # Check if file exists
    if not os.path.exists(file_path):
        return jsonify({'ready': False, 'reason': 'File being processed for download...'})
    
    # Check if file is empty
    if os.path.getsize(file_path) == 0:
        return jsonify({'ready': False, 'reason': 'File is empty'})
    
    # Check if file is still being processed
    for download_id, info in download_progress.items():
        if info.get('file_path') == file_path:
            if info.get('file_ready', False):
                return jsonify({'ready': True})
            else:
                return jsonify({'ready': False, 'reason': 'File is still being processed'})
    
    # If we can't find the file in download_progress, assume it's ready
    # (This could happen if the server was restarted)
    return jsonify({'ready': True})

if __name__ == '__main__':
    app.run(debug=True)

# https://www.youtube.com/live/S63TB25Bt3Q?si=YaMcfX4z56esFRVO