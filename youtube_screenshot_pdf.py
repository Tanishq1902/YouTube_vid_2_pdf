import yt_dlp
import cv2
import numpy as np
from fpdf import FPDF
import os
import argparse
import time
from datetime import timedelta
import re
import subprocess
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import webbrowser
import sys

# Function to get the direct video stream URL from YouTube
def get_youtube_stream_url(youtube_link):
    # Create a temp directory for downloads if it doesn't exist
    temp_dir = os.path.join(os.getcwd(), "temp_video_downloads")
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        
    # Create a unique filename for this download
    temp_video_path = os.path.join(temp_dir, f"temp_video_{int(time.time())}.mp4")
    
    print("Downloading video to temporary file. This may take a moment...")
    
    ydl_opts = {
        # Request more stable formats and download to temporary file
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "quiet": False,  # Show download progress
        "no_warnings": True,
        "socket_timeout": 30,
        "outtmpl": temp_video_path,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_link, download=True)
            
            if os.path.exists(temp_video_path) and os.path.getsize(temp_video_path) > 0:
                print(f"Video downloaded successfully to: {temp_video_path}")
                print(f"Selected format - Resolution: {info.get('height', 'unknown')}p, Codec: {info.get('vcodec', 'unknown')}")
                return temp_video_path, info.get("title", "Unknown"), info.get("duration", 0)
            else:
                # Check if yt-dlp used a different filename (sometimes adds extension)
                for filename in os.listdir(temp_dir):
                    if filename.startswith(os.path.basename(temp_video_path.split('.')[0])):
                        full_path = os.path.join(temp_dir, filename)
                        print(f"Video downloaded successfully to: {full_path}")
                        return full_path, info.get("title", "Unknown"), info.get("duration", 0)
                        
                print("Download appears to have failed. No file found.")
                return None, None, None
    except Exception as e:
        print(f"Error: Could not download YouTube video - {str(e)}")
        return None, None, None

# Function to parse time format (supports HH:MM:SS, MM:SS, or seconds)
def parse_timestamp(timestamp_str):
    # Check if it's just a number (seconds)
    if re.match(r'^\d+(\.\d+)?$', timestamp_str):
        return float(timestamp_str)
    
    # Try to parse as MM:SS or HH:MM:SS
    parts = timestamp_str.split(':')
    if len(parts) == 2:  # MM:SS
        return int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:  # HH:MM:SS
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    else:
        raise ValueError(f"Invalid time format: {timestamp_str}")

# Function to generate timestamps at regular intervals
def generate_interval_timestamps(duration, interval):
    return [i for i in range(0, int(duration) + 1, interval)]

# Function to capture screenshots at specific timestamps
def capture_screenshots(video_path, timestamps, output_dir="high_res_screenshots", max_retries=3):
    # Ensure output_dir is a full path
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(os.getcwd(), output_dir)
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    images = []
    total = len(timestamps)
    
    # Check if we're working with a local file
    is_local_file = os.path.exists(video_path) and os.path.isfile(video_path)
    
    # Get video information first to validate timestamps
    print("Checking video duration...")
    try:
        # Use OpenCV for local files or if ffmpeg is not available
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print("Error: Cannot open video file for initial check")
            return []
            
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # For local files, we can rely on frame count * fps
        if is_local_file and fps > 0 and total_frames > 0:
            duration = total_frames / fps
        else:
            # For streams, try to use other methods to get duration
            duration = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if duration <= 0:
                # If we get here, use the duration passed from yt_dlp
                if len(timestamps) > 0 and max(timestamps) > 0:
                    duration = max(timestamps) + 60  # Add a buffer
        
        cap.release()
        
        print(f"Video duration: {timedelta(seconds=int(duration))}")
        
        valid_timestamps = [t for t in timestamps if 0 <= t <= duration]
        if len(valid_timestamps) < len(timestamps):
            print(f"Warning: {len(timestamps) - len(valid_timestamps)} timestamps were outside video duration ({duration:.2f} seconds)")
        
        if not valid_timestamps:
            print("No valid timestamps to capture. Exiting...")
            return []
    except Exception as e:
        print(f"Warning: Could not determine video duration - {str(e)}")
        valid_timestamps = timestamps
    
    # Process each timestamp individually
    for i, timestamp in enumerate(valid_timestamps, 1):
        success = False
        for retry in range(max_retries):
            try:
                # Output file path
                img_path = os.path.join(output_dir, f"screenshot_{i:03d}_{int(timestamp)}s.jpg")
                
                print(f"Capturing screenshot {i}/{len(valid_timestamps)} at {timedelta(seconds=int(timestamp))}...")
                
                # For local files, prefer ffmpeg if available
                if shutil.which('ffmpeg'):
                    try:
                        cmd = [
                            'ffmpeg',
                            '-y',  # Overwrite output files
                            '-ss', str(timestamp),  # Seek position
                            '-i', video_path,  # Input file
                            '-frames:v', '1',  # Capture one frame
                            '-q:v', '1',  # Highest quality
                            img_path  # Output file
                        ]
                        
                        # Run ffmpeg with a timeout
                        process = subprocess.Popen(
                            cmd, 
                            stdout=subprocess.PIPE, 
                            stderr=subprocess.PIPE
                        )
                        
                        stdout, stderr = process.communicate(timeout=15)
                        
                        if process.returncode == 0 and os.path.exists(img_path) and os.path.getsize(img_path) > 0:
                            images.append(img_path)
                            success = True
                            print(f"✓ Captured screenshot at {timedelta(seconds=int(timestamp))}")
                            break
                    except (subprocess.SubprocessError, subprocess.TimeoutExpired) as e:
                        print(f"FFmpeg error: {str(e)}")
                
                # Fall back to OpenCV if ffmpeg failed or is not available
                if not success:
                    cap = cv2.VideoCapture(video_path)
                    if not cap.isOpened():
                        print(f"Error: Cannot open video file, attempt {retry + 1}/{max_retries}")
                        time.sleep(1)
                        continue
                    
                    # Calculate frame position
                    frame_pos = int(timestamp * cap.get(cv2.CAP_PROP_FPS))
                    
                    # Seek to the frame
                    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_pos))
                    
                    # Read the frame
                    ret, frame = cap.read()
                    
                    if ret:
                        # Save with high quality
                        cv2.imwrite(img_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                        cap.release()
                        
                        if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
                            images.append(img_path)
                            success = True
                            print(f"✓ Captured screenshot at {timedelta(seconds=int(timestamp))}")
                            break
                    
                    cap.release()
            
            except Exception as e:
                print(f"Error during capture: {str(e)}, attempt {retry + 1}/{max_retries}")
            
            if retry < max_retries - 1:
                print(f"Retrying... (attempt {retry + 1}/{max_retries})")
                time.sleep(1)
        
        if not success:
            print(f"⨯ Failed to capture screenshot at {timedelta(seconds=int(timestamp))} after {max_retries} attempts")
    
    print(f"Successfully captured {len(images)}/{len(valid_timestamps)} screenshots")
    return images

# Function to create a PDF from the screenshots
def create_pdf(image_paths, video_title="YouTube Video", output_pdf="screenshots.pdf"):
    try:
        # Always save to PDF folder by default if path doesn't include a directory
        if os.path.dirname(output_pdf) == '':
            pdf_dir = os.path.join(os.getcwd(), "PDF")
            if not os.path.exists(pdf_dir):
                os.makedirs(pdf_dir)
            output_pdf = os.path.join(pdf_dir, output_pdf)
        
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(output_pdf)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Thoroughly sanitize the video title to handle all special characters
        sanitized_title = ""
        for char in video_title:
            if ord(char) < 128:  # ASCII characters only
                sanitized_title += char
            else:
                # Replace non-ASCII with a placeholder
                sanitized_title += "_"
        
        # Create PDF with title (A4 landscape)
        pdf = FPDF(orientation='L', unit='pt', format='A4')  # Use points for precise sizing
        
        # Get A4 landscape dimensions in points (1pt = 1/72 inch)
        page_width = 842  # A4 width in points (landscape)
        page_height = 595  # A4 height in points (landscape)
        margin = 20  # margin in points
        
        # Calculate image dimensions to fit full page with margins
        image_width = page_width - (2 * margin)
        image_height = page_height - (2 * margin)
        
        # Add title page
        pdf.add_page()
        
        # "Screenshots from:" text - using Times New Roman
        pdf.set_font("Times", "B", 28)  # Times = Times New Roman
        pdf.cell(0, 60, "Screenshots from:", ln=True, align="C")
        
        # Video title - Using Arial Bold (keeping original font) but with larger size
        pdf.set_font("Arial", "B", 32)  # Increased from 16 to 32
        title_lines = [sanitized_title[i:i+45] for i in range(0, len(sanitized_title), 45)]
        for line in title_lines:
            pdf.cell(0, 30, line, ln=True, align="C")  # Increased height from 20 to 30
        
        # Screenshot count - Times New Roman, smaller than header but still readable
        pdf.set_font("Times", "", 18)  # Times = Times New Roman
        pdf.cell(0, 40, f"Total screenshots: {len(image_paths)}", ln=True, align="C")
        
        # Process one image per page
        for img_path in image_paths:
            pdf.add_page()
            # Center the image on the page
            pdf.image(img_path, x=margin, y=margin, w=image_width, h=image_height)

        # Use maximum quality settings for PDF output
        pdf.output(output_pdf)
        
        # Cleanup temporary files
        for img in image_paths:
            try:
                os.remove(img)
            except OSError as e:
                print(f"Warning: Could not delete temporary file {img}: {e}")
        
        # Try to remove the temp directory
        try:
            os.rmdir(os.path.dirname(image_paths[0]))
        except:
            pass
                
        print(f"✅ PDF created successfully: {output_pdf}")
        return True
    except Exception as e:
        print(f"Error creating PDF: {str(e)}")
        return False

# Function to clean up temporary files
def cleanup_temp_files(video_path):
    # Only clean up files in our temp directory
    if 'temp_video_downloads' in video_path:
        try:
            print(f"Cleaning up temporary file: {video_path}")
            os.remove(video_path)
            
            # If temp directory is empty, remove it
            temp_dir = os.path.dirname(video_path)
            if len(os.listdir(temp_dir)) == 0:
                os.rmdir(temp_dir)
                print("Removed empty temporary directory")
        except Exception as e:
            print(f"Warning: Failed to clean up temporary files - {str(e)}")
    else:
        print("No temporary files to clean up")

def main():
    # Set up command line arguments
    parser = argparse.ArgumentParser(description="Create a PDF of screenshots from a YouTube video")
    parser.add_argument("--url", help="YouTube video URL")
    parser.add_argument("--timestamps", help="Comma-separated timestamps (seconds, or MM:SS, or HH:MM:SS)")
    parser.add_argument("--interval", type=int, help="Take screenshots at regular intervals (in seconds)")
    parser.add_argument("--output", help="Output PDF filename")
    parser.add_argument("--pdf-name", help="Custom name for the PDF file")
    parser.add_argument("--download", action="store_true", help="Download video before processing (slower but more reliable)")
    parser.add_argument("--stream", action="store_true", help="Stream video directly (faster but may encounter connection errors)")
    parser.add_argument("--gui", action="store_true", help="Launch the graphical user interface")
    
    args = parser.parse_args()
    
    # Check if GUI mode is requested
    if args.gui:
        app = YouTubeScreenshotGUI()
        app.run()
        return
    
    # Get YouTube URL from command line or prompt
    youtube_link = args.url
    if not youtube_link:
        youtube_link = input("Enter YouTube video URL: ")
    
    # Determine processing mode (default to streaming)
    use_download_mode = args.download
    use_stream_mode = args.stream
    
    # If both are specified, download takes precedence
    if use_download_mode and use_stream_mode:
        print("Both download and stream modes specified, using download mode.")
        use_stream_mode = False
        
    # If neither is specified, we'll default to stream mode
    if not use_download_mode and not use_stream_mode:
        use_stream_mode = True
        
    video_path = None
    video_title = None
    video_duration = 0
    
    try:
        # Fetch video info
        print("Fetching video information...")
        
        if use_download_mode:
            # Download mode - save to temp file
            video_path, video_title, video_duration = get_youtube_stream_url(youtube_link)
        else:
            # Stream mode - get direct URL
            ydl_opts = {
                "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": 30,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(youtube_link, download=False)
                    formats = info.get('formats', [])
                    
                    # Find the best format that uses H.264 codec and is 1080p or lower
                    best_format = None
                    for f in formats:
                        vcodec = f.get('vcodec', '')
                        height = f.get('height', 0)
                        if 'avc' in vcodec and f.get('ext') == 'mp4' and height <= 1080:
                            if best_format is None or height > best_format.get('height', 0):
                                best_format = f
                    
                    if best_format is None:
                        # Fallback to any best MP4 format if H.264 is not available
                        best_format = max(
                            (f for f in formats if f.get('height', 0) <= 1080),
                            key=lambda f: f.get('height', 0),
                            default=formats[0]
                        )
                    
                    print(f"Selected format - Resolution: {best_format.get('height', 'unknown')}p, Codec: {best_format.get('vcodec', 'unknown')}")
                    video_path = best_format['url']
                    video_title = info.get("title", "Unknown")
                    video_duration = info.get("duration", 0)
                    
                    if use_stream_mode:
                        print("Using streaming mode. If you encounter connection errors, try with --download option instead.")
                        
                except Exception as e:
                    print(f"Error: Could not process YouTube link - {str(e)}")
                    video_path = None
        
        if video_path is None:
            print("Failed to get video. Exiting...")
            return
        
        print(f"Video title: {video_title}")
        
        # Get timestamps
        timestamps = []
        
        if args.interval and args.interval > 0:
            # Generate timestamps at regular intervals
            print(f"Generating timestamps at {args.interval} second intervals...")
            timestamps = generate_interval_timestamps(video_duration, args.interval)
        else:
            # Get timestamps from command line or prompt
            timestamps_input = args.timestamps
            if not timestamps_input:
                timestamps_input = input("Enter timestamps (comma-separated, can use HH:MM:SS, MM:SS, or seconds): ")
            
            try:
                # Parse timestamps which can be in various formats
                timestamps = [parse_timestamp(t.strip()) for t in timestamps_input.split(",")]
                if any(t < 0 for t in timestamps):
                    raise ValueError("Timestamps cannot be negative")
            except ValueError as e:
                print(f"Error: Invalid timestamps - {str(e)}")
                return
        
        # Sort timestamps for logical order
        timestamps.sort()
        
        # Get custom PDF name from command line or prompt
        pdf_name = args.pdf_name
        if not pdf_name and not args.output:
            pdf_name = input("Enter a name for the PDF file (or press Enter to use default): ")
        
        # Generate output filename based on user input, command line args, or video title
        if args.output:
            output_pdf = args.output
        elif pdf_name:
            # Ensure the name ends with .pdf
            if not pdf_name.lower().endswith('.pdf'):
                pdf_name += '.pdf'
            output_pdf = pdf_name
        elif video_title:
            # Sanitize the video title for use in filename
            # Replace special Unicode characters
            safe_title = video_title.replace('\u2026', '...')  # Replace ellipsis
            # Replace other problematic characters
            for char in ['\u2013', '\u2014', '\u2018', '\u2019', '\u201c', '\u201d', '\u2022']:
                safe_title = safe_title.replace(char, '_')
            
            # Create a safe filename from the video title
            safe_title = "".join(c if c.isalnum() or c in " -_." else "_" for c in safe_title)
            safe_title = safe_title[:50]  # Limit length
            output_pdf = f"{safe_title}_screenshots.pdf"
        else:
            output_pdf = "screenshots.pdf"
        
        print(f"Will capture {len(timestamps)} screenshots")
        
        # Check if output_pdf includes a directory path
        if os.path.dirname(output_pdf) == '':
            # If not, use the PDF folder
            pdf_dir = os.path.join(os.getcwd(), "PDF")
            full_output_path = os.path.join(pdf_dir, output_pdf)
            print(f"Output will be saved to: {full_output_path}")
        else:
            print(f"Output will be saved to: {output_pdf}")
        
        # Capture screenshots
        print("Capturing screenshots...")
        image_paths = capture_screenshots(video_path, timestamps)

        if image_paths:
            print("Generating PDF...")
            create_pdf(image_paths, video_title, output_pdf)
        else:
            print("No screenshots captured. Exiting...")
    
    finally:
        # Only clean up if we actually downloaded a file (not in streaming mode)
        if video_path and 'temp_video_downloads' in str(video_path):
            cleanup_temp_files(video_path)


class YouTubeScreenshotGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("YouTube Screenshot PDF Generator")
        self.root.geometry("700x700")
        self.root.minsize(600, 600)
        
        # Set theme and styling
        self.style = ttk.Style()
        self.style.configure("TButton", font=("Arial", 11))
        self.style.configure("TLabel", font=("Arial", 11))
        self.style.configure("TRadiobutton", font=("Arial", 11))
        self.style.configure("TCheckbutton", font=("Arial", 11))
        self.style.configure("Header.TLabel", font=("Arial", 14, "bold"))
        
        # Create main frame with padding
        self.main_frame = ttk.Frame(self.root, padding="20")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Variables
        self.url_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="stream")
        self.timestamp_type_var = tk.StringVar(value="specific")
        self.timestamps_var = tk.StringVar()
        self.interval_var = tk.StringVar(value="30")
        self.output_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0)
        
        # Create and place widgets
        self._create_widgets()
        
        # Center window on screen
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def _create_widgets(self):
        # Header
        header_label = ttk.Label(self.main_frame, text="YouTube Screenshot PDF Generator", style="Header.TLabel")
        header_label.grid(row=0, column=0, columnspan=3, pady=(0, 20), sticky="w")
        
        # URL input section
        url_label = ttk.Label(self.main_frame, text="YouTube URL:")
        url_label.grid(row=1, column=0, sticky="w", pady=(10, 5))
        
        url_frame = ttk.Frame(self.main_frame)
        url_frame.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(10, 5))
        url_frame.columnconfigure(0, weight=1)
        
        url_entry = ttk.Entry(url_frame, textvariable=self.url_var, width=50)
        url_entry.grid(row=0, column=0, sticky="ew")
        url_entry.focus_set()
        
        paste_button = ttk.Button(url_frame, text="Paste", command=self._paste_url)
        paste_button.grid(row=0, column=1, padx=(5, 0))
        
        # Processing mode section
        mode_label = ttk.Label(self.main_frame, text="Processing Mode:")
        mode_label.grid(row=2, column=0, sticky="w", pady=(15, 5))
        
        mode_frame = ttk.Frame(self.main_frame)
        mode_frame.grid(row=2, column=1, columnspan=2, sticky="w", pady=(15, 5))
        
        stream_radio = ttk.Radiobutton(mode_frame, text="Stream (faster but less reliable)", 
                                       variable=self.mode_var, value="stream")
        stream_radio.grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        download_radio = ttk.Radiobutton(mode_frame, text="Download (slower but more reliable)", 
                                         variable=self.mode_var, value="download")
        download_radio.grid(row=0, column=1, sticky="w")
        
        # Timestamp section
        timestamp_label = ttk.Label(self.main_frame, text="Timestamps:")
        timestamp_label.grid(row=3, column=0, sticky="w", pady=(15, 5))
        
        timestamp_frame = ttk.Frame(self.main_frame)
        timestamp_frame.grid(row=3, column=1, columnspan=2, sticky="w", pady=(15, 5))
        
        specific_radio = ttk.Radiobutton(timestamp_frame, text="Specific timestamps", 
                                        variable=self.timestamp_type_var, value="specific", 
                                        command=self._update_timestamp_ui)
        specific_radio.grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        interval_radio = ttk.Radiobutton(timestamp_frame, text="Regular intervals", 
                                        variable=self.timestamp_type_var, value="interval", 
                                        command=self._update_timestamp_ui)
        interval_radio.grid(row=0, column=1, sticky="w")
        
        # Specific timestamps input
        self.timestamps_frame = ttk.Frame(self.main_frame)
        self.timestamps_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(5, 0))
        self.timestamps_frame.columnconfigure(1, weight=1)
        
        timestamp_description = ttk.Label(self.timestamps_frame, 
                                        text="Enter timestamps (comma-separated, e.g., 0:30, 1:15, 2:45):")
        timestamp_description.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))
        
        timestamps_entry = ttk.Entry(self.timestamps_frame, textvariable=self.timestamps_var, width=50)
        timestamps_entry.grid(row=1, column=0, columnspan=2, sticky="ew")
        
        # Interval input
        self.interval_frame = ttk.Frame(self.main_frame)
        self.interval_frame.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(5, 0))
        self.interval_frame.columnconfigure(1, weight=1)
        
        interval_label = ttk.Label(self.interval_frame, text="Interval (seconds):")
        interval_label.grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        interval_entry = ttk.Entry(self.interval_frame, textvariable=self.interval_var, width=10)
        interval_entry.grid(row=0, column=1, sticky="w")
        
        # Output section
        output_label = ttk.Label(self.main_frame, text="Output PDF file:")
        output_label.grid(row=6, column=0, sticky="w", pady=(15, 5))
        
        output_frame = ttk.Frame(self.main_frame)
        output_frame.grid(row=6, column=1, columnspan=2, sticky="ew", pady=(15, 5))
        output_frame.columnconfigure(0, weight=1)
        
        output_entry = ttk.Entry(output_frame, textvariable=self.output_var, width=50)
        output_entry.grid(row=0, column=0, sticky="ew")
        
        browse_button = ttk.Button(output_frame, text="Browse", command=self._browse_output)
        browse_button.grid(row=0, column=1, padx=(5, 0))
        
        # Status and progress section
        status_frame = ttk.Frame(self.main_frame)
        status_frame.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(15, 5))
        status_frame.columnconfigure(0, weight=1)
        
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var)
        self.status_label.grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        self.progress_bar = ttk.Progressbar(status_frame, orient="horizontal", length=300, mode="determinate", variable=self.progress_var)
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        
        # Log
        log_label = ttk.Label(self.main_frame, text="Progress Log:")
        log_label.grid(row=8, column=0, columnspan=3, sticky="w", pady=(5, 5))
        
        log_frame = ttk.Frame(self.main_frame)
        log_frame.grid(row=9, column=0, columnspan=3, sticky="nsew", pady=(0, 10))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        
        self.log_text = tk.Text(log_frame, height=10, width=60, wrap=tk.WORD, font=("Consolas", 10))
        self.log_text.grid(row=0, column=0, sticky="nsew")
        
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        # Action buttons
        button_frame = ttk.Frame(self.main_frame)
        button_frame.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        
        process_button = ttk.Button(button_frame, text="Process Video", command=self._process_video)
        process_button.grid(row=0, column=0, padx=(0, 5), sticky="e")
        
        exit_button = ttk.Button(button_frame, text="Exit", command=self.root.destroy)
        exit_button.grid(row=0, column=1, padx=(5, 0), sticky="w")
        
        # Footer with GitHub link
        github_link = ttk.Label(self.main_frame, text="GitHub Repository", foreground="blue", cursor="hand2")
        github_link.grid(row=11, column=0, columnspan=3, pady=(20, 0))
        github_link.bind("<Button-1>", lambda e: webbrowser.open_new("https://github.com/yourusername/youtube-screenshot-pdf"))
        
        # Configure grid weights
        self.main_frame.columnconfigure(1, weight=1)
        self.main_frame.rowconfigure(9, weight=1)
        
        # Initially hide interval frame
        self.interval_frame.grid_remove()
    
    def _paste_url(self):
        """Paste clipboard content into URL field"""
        clipboard = self.root.clipboard_get()
        self.url_var.set(clipboard)
    
    def _browse_output(self):
        """Open file browser to select output PDF file"""
        filename = filedialog.asksaveasfilename(
            title="Save PDF As",
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")]
        )
        if filename:
            self.output_var.set(filename)
    
    def _update_timestamp_ui(self):
        """Show/hide timestamp fields based on selection"""
        if self.timestamp_type_var.get() == "specific":
            self.interval_frame.grid_remove()
            self.timestamps_frame.grid()
        else:
            self.timestamps_frame.grid_remove()
            self.interval_frame.grid()
    
    def _log(self, message):
        """Add message to log and scroll to end"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def _update_status(self, message, progress=None):
        """Update status message and progress bar"""
        self.status_var.set(message)
        if progress is not None:
            self.progress_var.set(progress)
        self.root.update_idletasks()
    
    def _process_video(self):
        """Process the video in a separate thread"""
        # Validate inputs
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a YouTube URL")
            return
        
        # Clear log
        self.log_text.delete(1.0, tk.END)
        
        # Start processing thread
        self._update_status("Starting process...", 0)
        threading.Thread(target=self._process_worker, daemon=True).start()
    
    def _process_worker(self):
        """Worker thread to process the video and create PDF"""
        try:
            url = self.url_var.get().strip()
            mode = self.mode_var.get()
            timestamp_type = self.timestamp_type_var.get()
            output_pdf = self.output_var.get().strip()
            
            # Get timestamps
            timestamps = []
            if timestamp_type == "specific":
                timestamps_input = self.timestamps_var.get().strip()
                if not timestamps_input:
                    self._log("Error: Please enter timestamps")
                    self._update_status("Error: No timestamps provided", 0)
                    return
                
                try:
                    timestamps = [parse_timestamp(t.strip()) for t in timestamps_input.split(",")]
                    if any(t < 0 for t in timestamps):
                        self._log("Error: Timestamps cannot be negative")
                        self._update_status("Error: Invalid timestamps", 0)
                        return
                except ValueError as e:
                    self._log(f"Error: Invalid timestamps - {str(e)}")
                    self._update_status("Error: Invalid timestamps", 0)
                    return
            else:  # interval
                interval_input = self.interval_var.get().strip()
                try:
                    interval = int(interval_input)
                    if interval <= 0:
                        self._log("Error: Interval must be a positive number")
                        self._update_status("Error: Invalid interval", 0)
                        return
                except ValueError:
                    self._log("Error: Interval must be a valid number")
                    self._update_status("Error: Invalid interval", 0)
                    return
            
            # Fetch video information
            self._log("Fetching video information...")
            self._update_status("Fetching video information...", 10)
            
            video_path = None
            video_title = None
            video_duration = 0
            
            if mode == "download":
                # Download mode
                self._log("Using download mode (more reliable but slower)")
                video_path, video_title, video_duration = get_youtube_stream_url(url)
                
                class LogCapture:
                    def __init__(self, gui):
                        self.gui = gui
                    def write(self, msg):
                        if msg.strip():
                            self.gui._log(msg.strip())
                    def flush(self):
                        pass
                
                original_stdout = sys.stdout
                sys.stdout = LogCapture(self)
                video_path, video_title, video_duration = get_youtube_stream_url(url)
                sys.stdout = original_stdout
                
            else:
                # Stream mode
                self._log("Using stream mode (faster but may encounter connection errors)")
                ydl_opts = {
                    "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                    "quiet": True,
                    "no_warnings": True,
                    "socket_timeout": 30,
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    formats = info.get('formats', [])
                    
                    # Find a good format
                    best_format = None
                    for f in formats:
                        vcodec = f.get('vcodec', '')
                        height = f.get('height', 0)
                        if 'avc' in vcodec and f.get('ext') == 'mp4' and height <= 1080:
                            if best_format is None or height > best_format.get('height', 0):
                                best_format = f
                    
                    if best_format is None:
                        best_format = max(
                            (f for f in formats if f.get('height', 0) <= 1080),
                            key=lambda f: f.get('height', 0),
                            default=formats[0]
                        )
                    
                    self._log(f"Selected format - Resolution: {best_format.get('height', 'unknown')}p, "
                           f"Codec: {best_format.get('vcodec', 'unknown')}")
                    video_path = best_format['url']
                    video_title = info.get("title", "Unknown")
                    video_duration = info.get("duration", 0)
            
            if video_path is None:
                self._log("Failed to get video. Exiting...")
                self._update_status("Failed to get video", 0)
                return
            
            self._log(f"Video title: {video_title}")
            self._update_status("Video information fetched", 20)
            
            # Generate timestamps if interval mode
            if timestamp_type == "interval":
                interval = int(self.interval_var.get().strip())
                self._log(f"Generating timestamps at {interval} second intervals...")
                timestamps = generate_interval_timestamps(video_duration, interval)
            
            # Sort timestamps
            timestamps.sort()
            
            # Generate output filename if not provided
            if not output_pdf:
                # Sanitize the video title for use in filename
                safe_title = "".join(c if c.isalnum() or c in " -_." else "_" for c in video_title)
                safe_title = safe_title[:50]  # Limit length
                output_pdf = f"{safe_title}_screenshots.pdf"
            
            # Ensure PDF extension
            if not output_pdf.lower().endswith('.pdf'):
                output_pdf += '.pdf'
            
            # Ensure PDF is saved in the PDF folder if no directory is specified
            if os.path.dirname(output_pdf) == '':
                pdf_dir = os.path.join(os.getcwd(), "PDF")
                if not os.path.exists(pdf_dir):
                    os.makedirs(pdf_dir)
                output_pdf = os.path.join(pdf_dir, output_pdf)
            
            self._log(f"Will capture {len(timestamps)} screenshots")
            self._log(f"Output will be saved to: {output_pdf}")
            self._update_status("Capturing screenshots...", 30)
            
            # Capture screenshots (with progress updates)
            self._log("Capturing screenshots...")
            
            # Create a custom screenshot capturer to track progress
            image_paths = []
            total_screenshots = len(timestamps)
            
            for i, timestamp in enumerate(timestamps, 1):
                progress = 30 + (i / total_screenshots * 40)  # Progress from 30% to 70%
                self._update_status(f"Capturing screenshot {i}/{total_screenshots}...", progress)
                
                # Get a single screenshot
                single_image = capture_screenshots(video_path, [timestamp])
                if single_image:
                    image_paths.extend(single_image)
                    self._log(f"✓ Captured screenshot at {timedelta(seconds=int(timestamp))}")
                else:
                    self._log(f"⨯ Failed to capture screenshot at {timedelta(seconds=int(timestamp))}")
            
            if not image_paths:
                self._log("No screenshots captured. Exiting...")
                self._update_status("No screenshots captured", 0)
                return
            
            # Generate PDF
            self._log("Generating PDF...")
            self._update_status("Generating PDF...", 80)
            
            if create_pdf(image_paths, video_title, output_pdf):
                self._log(f"✅ PDF created successfully: {output_pdf}")
                self._update_status("PDF created successfully", 100)
                
                # Ask if user wants to open the PDF
                if messagebox.askyesno("Success", f"PDF created successfully at:\n{output_pdf}\n\nWould you like to open it now?"):
                    try:
                        os.startfile(output_pdf)
                    except:
                        # Fallback for non-Windows systems
                        try:
                            if sys.platform == 'darwin':  # macOS
                                subprocess.call(('open', output_pdf))
                            else:  # Linux or other
                                subprocess.call(('xdg-open', output_pdf))
                        except:
                            self._log("Could not open PDF automatically. Please open it manually.")
            else:
                self._log("Failed to create PDF")
                self._update_status("Failed to create PDF", 0)
            
            # Clean up temp files
            if mode == "download" and 'temp_video_downloads' in str(video_path):
                self._log("Cleaning up temporary files...")
                cleanup_temp_files(video_path)
                
        except Exception as e:
            self._log(f"Error: {str(e)}")
            self._update_status(f"Error: {str(e)}", 0)
    
    def run(self):
        """Run the application"""
        self.root.mainloop()


if __name__ == "__main__":
    try:
        # Check if any arguments were provided
        if len(sys.argv) > 1:
            # If arguments were provided, run in CLI mode
            main()
        else:
            # No arguments, default to GUI mode
            app = YouTubeScreenshotGUI()
            app.run()
    except KeyboardInterrupt:
        print("\nProcess interrupted by user. Exiting...")
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")
