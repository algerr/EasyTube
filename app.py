# file: app.py

from flask import Flask, request, render_template, send_file, redirect, url_for, session, jsonify, flash
import subprocess
import json
import os
import uuid
import threading
import time
import re
from datetime import datetime
import random
import yt_dlp
import logging
from datetime import timedelta
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.logger.setLevel(logging.INFO)
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
        
        # Filter out formats without filesize or format_id
        valid_audio_formats = [af for af in audio_formats if af.get("filesize") and af.get("format_id")]
        
        if not valid_audio_formats:
            return choices
            
        # Sort by filesize (which correlates with quality)
        sorted_audio = sorted(valid_audio_formats, key=lambda x: x.get("filesize", 0))
        
        # Get the best quality (largest file size) - show this first
        if len(sorted_audio) > 1:
            best = sorted_audio[-1]
            best_size_mb = round(best["filesize"] / (1024 * 1024), 2)
            choices.append({
                "id": best["format_id"],
                "label": f"Audio | High Quality | {best_size_mb}MB"
            })
        
        # Get the worst quality (smallest file size) - show this second
        if sorted_audio:
            worst = sorted_audio[0]
            worst_size_mb = round(worst["filesize"] / (1024 * 1024), 2)
            choices.append({
                "id": worst["format_id"],
                "label": f"Audio | Low Quality | {worst_size_mb}MB"
            })
        
        return choices

    # For video, prefer MP4 formats but also include other formats that can be converted
    # We'll use the --merge-output-format mp4 flag to ensure the final output is MP4
    video_formats = [f for f in formats if f.get("vcodec") != "none"]
    
    # Prioritize MP4 formats
    mp4_formats = [f for f in video_formats if f.get("ext") == "mp4"]
    if mp4_formats:
        video_formats = mp4_formats
    
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
                "height": height,
                "ext": vf.get("ext", "mp4")  # Default to mp4 if not specified
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
        
        # Add format information to the label
        ext = entry.get("ext", "mp4")
        if ext != "mp4":
            label = f"Video | {quality_desc} ({res}) | {size_mb}MB (Will convert to MP4)"
        else:
            label = f"Video | {quality_desc} ({res}) | {size_mb}MB"
            
        formatted_choices.append({"id": entry["id"], "label": label})
    
    return formatted_choices

def download_video_with_progress(url, format_id, download_id, filename, format_mode):
    """Download video with progress tracking using direct subprocess call to yt-dlp"""
    try:
        # Determine output format and path
        is_audio = format_mode == "mp3"
        base_filename = os.path.splitext(filename)[0]
        output_template = os.path.join(DOWNLOAD_FOLDER, filename)
        
        # Update status to starting
        download_progress[download_id]['status'] = 'Starting download...'
        app.logger.info(f"Starting download for {download_id}: {url} with format {format_id}")
        
        # Build the yt-dlp command
        cmd = ["yt-dlp", "--newline"]
        
        # Add format selection
        cmd.extend(["--format", format_id])
        
        # Add output template
        cmd.extend(["--output", output_template])
        
        # Add post-processing for audio if needed
        if is_audio:
            cmd.extend(["--extract-audio", "--audio-format", "mp3", "--audio-quality", "192"])
        else:
            # For video, ensure the output is always MP4
            cmd.extend(["--merge-output-format", "mp4"])
        
        # Add the URL
        cmd.append(url)
        
        # Log the command
        app.logger.info(f"Running command: {' '.join(cmd)}")
        
        # Start the process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Process output line by line to update progress
        final_output_path = None
        for line in process.stdout:
            line = line.strip()
            app.logger.debug(f"yt-dlp output: {line}")
            
            # Update progress based on output
            if "[download]" in line and "%" in line:
                try:
                    # Extract percentage
                    percent_match = re.search(r'(\d+\.\d+)%', line)
                    if percent_match:
                        percent = float(percent_match.group(1))
                        download_progress[download_id]['progress'] = percent
                        download_progress[download_id]['status'] = 'Downloading...'
                        
                        # Extract speed
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
                except Exception as e:
                    app.logger.error(f"Error parsing progress: {e}")
            
            # Check for post-processing
            elif "Extracting audio" in line or "Merging formats" in line or "Recoding video" in line:
                download_progress[download_id]['status'] = 'Post-processing...'
                download_progress[download_id]['progress'] = 95
            
            # Check for destination file
            elif "[ExtractAudio] Destination:" in line:
                try:
                    final_output_path = line.split("[ExtractAudio] Destination:")[1].strip()
                    app.logger.info(f"Found destination path: {final_output_path}")
                except Exception as e:
                    app.logger.error(f"Error parsing destination: {e}")
            
            # Check for download completion
            elif "Deleting original file" in line or "has already been downloaded" in line:
                download_progress[download_id]['status'] = 'Finalizing...'
                download_progress[download_id]['progress'] = 99
        
        # Wait for process to complete
        process.wait()
        
        # Check if process completed successfully
        if process.returncode != 0:
            raise Exception(f"yt-dlp process failed with return code {process.returncode}")
        
        # Find the output file
        if is_audio:
            # For audio, check for .mp3 file
            expected_mp3 = os.path.join(DOWNLOAD_FOLDER, f"{base_filename}.mp3")
            if os.path.exists(expected_mp3):
                final_output_path = expected_mp3
            elif final_output_path and os.path.exists(final_output_path):
                # Use the path extracted from output
                pass
            else:
                # Try to find any file with the same base name
                possible_files = [f for f in os.listdir(DOWNLOAD_FOLDER) 
                                if f.startswith(base_filename) and os.path.isfile(os.path.join(DOWNLOAD_FOLDER, f))]
                if possible_files:
                    final_output_path = os.path.join(DOWNLOAD_FOLDER, possible_files[0])
                    app.logger.info(f"Found alternative file: {final_output_path}")
                else:
                    raise Exception("Could not find downloaded file")
        else:
            # For video, check for the original filename
            expected_mp4 = os.path.join(DOWNLOAD_FOLDER, f"{base_filename}.mp4")
            if os.path.exists(expected_mp4):
                final_output_path = expected_mp4
            elif os.path.exists(output_template):
                final_output_path = output_template
            else:
                # Try to find any file with the same base name
                possible_files = [f for f in os.listdir(DOWNLOAD_FOLDER) 
                                if f.startswith(base_filename) and os.path.isfile(os.path.join(DOWNLOAD_FOLDER, f))]
                if possible_files:
                    # Prefer .mp4 files if available
                    mp4_files = [f for f in possible_files if f.endswith('.mp4')]
                    if mp4_files:
                        final_output_path = os.path.join(DOWNLOAD_FOLDER, mp4_files[0])
                    else:
                        final_output_path = os.path.join(DOWNLOAD_FOLDER, possible_files[0])
                    app.logger.info(f"Found alternative file: {final_output_path}")
                else:
                    raise Exception("Could not find downloaded file")
        
        # Verify file exists and has content
        if not final_output_path or not os.path.exists(final_output_path):
            raise Exception(f"File not found after download")
        
        # For video files, ensure the extension is .mp4
        if not is_audio and not final_output_path.endswith('.mp4'):
            # Rename the file to have .mp4 extension
            new_path = os.path.splitext(final_output_path)[0] + '.mp4'
            try:
                os.rename(final_output_path, new_path)
                app.logger.info(f"Renamed file from {final_output_path} to {new_path}")
                final_output_path = new_path
            except Exception as e:
                app.logger.error(f"Error renaming file to .mp4: {str(e)}")
        
        file_size = os.path.getsize(final_output_path)
        if file_size == 0:
            raise Exception(f"Downloaded file is empty: {final_output_path}")
        
        # Update download progress with final information
        download_progress[download_id]['status'] = 'Download complete!'
        download_progress[download_id]['progress'] = 100
        download_progress[download_id]['file_ready'] = True
        download_progress[download_id]['file_path'] = final_output_path
        download_progress[download_id]['filename'] = os.path.basename(final_output_path)
        download_progress[download_id]['download_url'] = f'/download_file/{os.path.basename(final_output_path)}'
        
        # Log success
        app.logger.info(f"Download successful: {final_output_path}, Size: {file_size} bytes")
        
        return final_output_path
        
    except Exception as e:
        app.logger.error(f"Download error: {str(e)}", exc_info=True)
        download_progress[download_id]['status'] = f'Error: {str(e)}'
        download_progress[download_id]['error'] = str(e)
        raise

def update_progress_from_output(download_id, line):
    """Update download progress based on yt-dlp output line."""
    try:
        # Skip if download_id is invalid
        if download_id not in download_progress:
            return
            
        # Skip if download is already complete
        if download_progress[download_id].get('progress') == 100:
            return
            
        # Log the output line for debugging
        line = line.strip()
        
        # Update progress based on output
        if "[download]" in line and "%" in line:
            # Extract percentage
            percent_match = re.search(r'(\d+\.\d+)%', line)
            if percent_match:
                percent = float(percent_match.group(1))
                download_progress[download_id]['progress'] = percent
                download_progress[download_id]['status'] = 'downloading'
                
                # Extract speed
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
                    download_progress[download_id]['size'] = f"{size_match.group(1)} of {size_match.group(2)}"
                    download_progress[download_id]['downloaded'] = size_match.group(1)
                    download_progress[download_id]['total_size'] = size_match.group(2)
        
        # Check for post-processing
        elif "Extracting audio" in line or "Merging formats" in line or "Recoding video" in line:
            download_progress[download_id]['status'] = 'post-processing'
            download_progress[download_id]['progress'] = 95
        
        # Check for download completion
        elif "Deleting original file" in line or "has already been downloaded" in line:
            download_progress[download_id]['status'] = 'finalizing'
            download_progress[download_id]['progress'] = 99
        
        # Update last updated timestamp
        download_progress[download_id]['last_updated'] = time.time()
        
    except Exception as e:
        app.logger.error(f"Error updating progress from output: {str(e)}")
        app.logger.error(traceback.format_exc())

def initialize_download_progress(download_id, filename, url=None, format_id=None, video_title=None, file_path=None):
    """Initialize the download progress tracking for a new download"""
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    download_progress[download_id] = {
        'progress': 0,
        'status': 'Starting download...',
        'speed': '--',
        'downloaded': '0 KiB',
        'total_size': '--',
        'eta': '--',
        'download_url': f'/download_file/{filename}',
        'title': video_title,
        'file_path': file_path,
        'file_ready': False,  # Flag to indicate if file is ready for download
        'start_time': current_time,
        'last_updated': current_time,  # Track when this entry was last updated
        'cancelled': False  # Flag to track if download was cancelled
    }
    
    # Log the download initialization
    app.logger.info(f"Initialized download tracking for {download_id}: {url} -> {file_path}")

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
    try:
        format_id = request.form.get('format')
        url = session.get('url')
        video_title = session.get('video_title', 'Video')
        format_mode = session.get('format_mode', 'video')
        
        if not url:
            return render_template('index.html', error="Missing URL. Please enter a YouTube URL.")
            
        if not format_id:
            return render_template('index.html', error="Missing format selection. Please select a format.")
            
        # Validate YouTube URL again as a safety check
        if not is_valid_youtube_url(url):
            return render_template('index.html', error="Invalid YouTube URL. Please enter a valid YouTube URL.")
        
        # Generate a unique download ID and filename
        download_id = str(uuid.uuid4())
        ext = "mp3" if format_mode == "mp3" else "mp4"
        filename = f"{uuid.uuid4()}.{ext}"
        
        # Ensure we have the absolute path
        file_path = os.path.abspath(os.path.join(DOWNLOAD_FOLDER, filename))
        
        # Make sure the download directory exists
        os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
        
        # Initialize progress tracking
        initialize_download_progress(download_id, filename, url, format_id, video_title, file_path)
        
        # Log the download request
        app.logger.info(f"Starting download: {url} with format {format_id} to {file_path}")
        
        # Start download in a background thread
        download_thread = threading.Thread(
            target=download_video_with_progress,
            args=(url, format_id, download_id, filename, format_mode),
            daemon=True
        )
        download_thread.start()
        
        # Redirect to progress page
        return redirect(url_for('download_progress_page', download_id=download_id))
    except Exception as e:
        app.logger.error(f"Error starting download: {str(e)}", exc_info=True)
        return render_template('index.html', error=f"Error: {str(e)}")

def cleanup_old_downloads():
    """Clean up old download progress entries and files to prevent memory leaks and disk space issues"""
    current_time = datetime.now()
    to_remove = []
    
    for download_id, info in download_progress.items():
        should_remove = False
        
        # Check if download is old (older than 1 hour)
        try:
            start_time = datetime.strptime(info.get('start_time', ''), '%Y-%m-%d %H:%M:%S')
            if (current_time - start_time).total_seconds() > 3600:  # 1 hour
                should_remove = True
        except:
            # If we can't parse the start time, assume it's old
            should_remove = True
        
        # Check if download was cancelled
        if info.get('cancelled', False):
            should_remove = True
        
        # Check if download is stuck (no progress for a long time)
        if 'last_updated' in info:
            try:
                last_updated = datetime.strptime(info['last_updated'], '%Y-%m-%d %H:%M:%S')
                if (current_time - last_updated).total_seconds() > 1800:  # 30 minutes
                    should_remove = True
            except:
                pass
        
        # If download should be removed, add it to the list
        if should_remove:
            to_remove.append(download_id)
    
    # Remove old entries and their files
    for download_id in to_remove:
        try:
            # Get the file path before removing the entry
            file_path = download_progress[download_id].get('file_path')
            
            # Remove the entry
            del download_progress[download_id]
            
            # Delete the file if it exists
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                app.logger.info(f"Deleted file for {download_id}: {file_path}")
            
            app.logger.info(f"Cleaned up download: {download_id}")
        except Exception as e:
            app.logger.error(f"Error cleaning up download {download_id}: {str(e)}")

@app.route('/download_status/<download_id>')
def download_status(download_id):
    """Return the current download status as JSON"""
    # Clean up old downloads occasionally (10% chance)
    if random.random() < 0.1:
        cleanup_old_downloads()
    
    if download_id in download_progress:
        # Update the last_updated timestamp to track activity
        download_progress[download_id]['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return jsonify(download_progress[download_id])
    return jsonify({'status': 'Download not found', 'progress': 0})

@app.route('/download_file/<filename>')
def download_file(filename):
    try:
        # Construct the file path
        file_path = os.path.join(DOWNLOAD_FOLDER, filename)
        
        # Check if file exists
        if not os.path.exists(file_path):
            app.logger.error(f"File not found: {file_path}")
            return render_template('error.html', 
                                  error_message=f"The requested file could not be found. It may have been deleted or moved.",
                                  back_url=url_for('index'))
        
        # Check if file is empty
        if os.path.getsize(file_path) == 0:
            app.logger.error(f"File is empty: {file_path}")
            return render_template('error.html', 
                                  error_message=f"The requested file is empty. Please try downloading again.",
                                  back_url=url_for('index'))
        
        try:
            # Get the download ID from the filename (if available)
            download_id = None
            for d_id, info in download_progress.items():
                if info.get('file_path') and os.path.basename(info['file_path']) == filename:
                    download_id = d_id
                    break
            
            # Log the download
            app.logger.info(f"Sending file: {file_path}, Size: {os.path.getsize(file_path)} bytes")
            
            # Determine the appropriate mimetype based on file extension
            mimetype = None
            if filename.endswith('.mp3'):
                mimetype = 'audio/mpeg'
            elif filename.endswith('.mp4'):
                mimetype = 'video/mp4'
            
            # Send the file with appropriate headers
            return send_file(file_path, 
                            mimetype=mimetype,
                            as_attachment=True, 
                            download_name=f"{download_progress[download_id]['title']}.{filename.split('.')[-1]}" if download_id else filename)
                            
        except Exception as e:
            app.logger.error(f"Error sending file: {str(e)}")
            return render_template('error.html', 
                                  error_message=f"An error occurred while sending the file: {str(e)}",
                                  back_url=url_for('index'))
    except Exception as e:
        app.logger.error(f"Unexpected error in download_file: {str(e)}")
        return render_template('error.html', 
                              error_message=f"An unexpected error occurred: {str(e)}",
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

def format_file_size(size_in_bytes):
    """Format file size in bytes to human-readable format"""
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.2f} KiB"
    elif size_in_bytes < 1024 * 1024 * 1024:
        return f"{size_in_bytes / (1024 * 1024):.2f} MiB"
    else:
        return f"{size_in_bytes / (1024 * 1024 * 1024):.2f} GiB"

def progress_hook(d):
    """Legacy progress hook for yt-dlp Python library (kept for compatibility)"""
    download_id = d.get('download_id')
    
    # Skip if download_id is not valid
    if not download_id or download_id not in download_progress:
        app.logger.warning(f"Invalid download_id in progress_hook: {download_id}")
        return
        
    # Log the status for debugging
    app.logger.debug(f"Progress hook: {download_id} - Status: {d['status']}")
    
    # Update the last_updated timestamp
    download_progress[download_id]['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # This function is kept for compatibility but is no longer the primary progress tracking method
    # The direct subprocess approach in download_video_with_progress now handles progress updates

@app.route('/download_progress/<download_id>')
def download_progress_page(download_id):
    """Render the download progress page"""
    if download_id not in download_progress:
        app.logger.warning(f"Invalid download_id requested: {download_id}")
        return redirect(url_for('index'))
        
    video_title = download_progress[download_id].get('title', 'Video')
    return render_template('download_progress.html', download_id=download_id, title=video_title)

@app.route('/get_progress/<download_id>')
def get_progress(download_id):
    """Get the current progress of a download."""
    if download_id not in download_progress:
        return jsonify({
            'error': 'Download not found',
            'redirect': url_for('index')
        }), 404
        
    progress_data = download_progress[download_id].copy()
    
    # Check if download is complete
    if progress_data.get('status') == 'complete':
        # Generate download URL
        filename = progress_data.get('filename')
        if filename:
            progress_data['download_url'] = url_for('download_file', filename=filename)
    
    # Check if download has error
    if progress_data.get('status') == 'error':
        progress_data['error_message'] = progress_data.get('error', 'Unknown error')
    
    return jsonify(progress_data)

@app.route('/cancel_download/<download_id>')
def cancel_download(download_id):
    """Cancel a download and clean up any partial files"""
    if download_id in download_progress:
        try:
            # Get the file path
            file_path = download_progress[download_id].get('file_path')
            
            # Mark the download as cancelled
            download_progress[download_id]['status'] = 'Cancelled'
            download_progress[download_id]['cancelled'] = True
            download_progress[download_id]['progress'] = 0  # Reset progress
            
            # Delete the file if it exists
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    app.logger.info(f"Deleted cancelled download file: {file_path}")
                except Exception as file_error:
                    app.logger.error(f"Error deleting file {file_path}: {str(file_error)}")
            else:
                app.logger.info(f"No file to delete for cancelled download {download_id}")
            
            return jsonify({'success': True, 'message': 'Download cancelled'})
        except Exception as e:
            app.logger.error(f"Error cancelling download: {str(e)}")
            return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    
    return jsonify({'success': False, 'message': 'Download not found'})

@app.route('/check_ytdlp')
def check_ytdlp():
    """Check if yt-dlp is properly installed and working"""
    try:
        # Get yt-dlp version
        result = subprocess.run(
            ["yt-dlp", "--version"], capture_output=True, text=True
        )
        version = result.stdout.strip()
        
        # Try to get info for a test video
        test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # A well-known video that's unlikely to be taken down
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(test_url, download=False)
            title = info.get('title', 'Unknown')
            formats = len(info.get('formats', []))
        
        return jsonify({
            'status': 'success',
            'version': version,
            'test_video': {
                'title': title,
                'formats_available': formats
            },
            'message': f"yt-dlp {version} is working correctly"
        })
    except Exception as e:
        app.logger.error(f"Error checking yt-dlp: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f"Error checking yt-dlp: {str(e)}"
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)