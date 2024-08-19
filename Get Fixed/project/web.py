import os
import uuid
import datetime
from flask import Flask, render_template_string, request, send_from_directory, redirect, url_for
from threading import Thread
import shutil
from test import (
    load_subtitles_from_file, subriptime_to_seconds, load_video_from_file, 
    concatenate_videoclips, get_segments_using_srt, generate_srt_from_txt_and_audio
)
from pathlib import Path
import pysrt

app = Flask(__name__)

def generate_unique_id():
    return str(uuid.uuid4())

def generate_datetime_alias():
    current_time = datetime.datetime.now()
    return current_time.strftime("%Y-%m-%d_%H-%M-%S")

@app.route('/')
def index():
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Scene Optimisation Bot</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f2f2f2;
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                }
                .container {
                    background-color: white;
                    padding: 20px;
                    border-radius: 10px;
                    box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
                    width: 400px;
                    text-align: center;
                }
                h1 {
                    color: #333;
                }
                input[type="file"], input[type="text"], input[type="submit"] {
                    margin-bottom: 10px;
                    width: 100%;
                    padding: 8px;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                }
                input[type="submit"] {
                    background-color: #4CAF50;
                    color: white;
                    cursor: pointer;
                }
                input[type="submit"]:hover {
                    background-color: #45a049;
                }
                #waitMessage {
                    margin-top: 20px;
                    color: #555;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Scene Optimisation Bot</h1>
                <form action="/process" method="post" enctype="multipart/form-data" onsubmit="displayMessage()">
                    Video File <input type="file" name="video_file" required><br>
                    Clips (zip) <input type="file" name="clips_folder" required><br>
                    MP3 File <input type="file" name="mp3_file" required><br>
                    Text File <input type="file" name="text_file" required><br>
                    TTF Font File <input type="file" name="font_file" required><br>
                    Font Size <input type="text" name="font_size" required><br>
                    Font Color <input type="text" name="font_color" required><br>
                    Background Color <input type="text" name="bg_color" required><br>
                    Box Margin <input type="text" name="margin" required><br>
                    <input type="submit" value="Process">
                </form>
                <h1 id="waitMessage"></h1>
            </div>
        </body>
        </html>
    ''')

@app.route('/process', methods=['POST'])
def process():
    static_out_file_server = os.path.join('static', 'output_root')
    tmp = os.path.join(os.getcwd(), 'tmp')
    final_out_path = os.path.join('static', 'output_root', 'final')
    outpath = os.path.join(static_out_file_server, 'output')
    
    try:
        # Cleanup old files
        remove_all_files_in_directory(os.path.join(outpath, 'videos'))
        remove_all_files_in_directory(os.path.join(outpath, 'audios'))
        remove_all_files_in_directory(final_out_path)
        
        if os.path.exists(tmp):
            tmp_dirs = os.listdir(tmp)
            for dir in tmp_dirs:
                remove_all_files_in_directory(os.path.join(tmp, dir))
            remove_all_files_in_directory(tmp)
    except Exception as e:
        return f"An error occurred during cleanup: {e}", 500
    
    try:
        # Create necessary directories
        os.makedirs(outpath, exist_ok=True)
        os.makedirs(os.path.join(outpath, 'audios'), exist_ok=True)
        os.makedirs(os.path.join(outpath, 'videos'), exist_ok=True)
        os.makedirs(final_out_path, exist_ok=True)
        os.makedirs(tmp, exist_ok=True)  # Ensure the tmp directory exists
    except Exception as e:
        return f"An error occurred during directory creation: {e}", 500
    
    unique_special_id = os.path.join(tmp, generate_unique_id())
    
    video_dir = os.path.join(unique_special_id, "video")
    clips_dir = os.path.join(unique_special_id, "clips")
    mp3_dir = os.path.join(unique_special_id, "mp3")
    text_dir = os.path.join(unique_special_id, "text")
    font_dir = os.path.join(unique_special_id, "font")
    os.makedirs(video_dir, exist_ok=True)
    os.makedirs(clips_dir, exist_ok=True)
    os.makedirs(mp3_dir, exist_ok=True)
    os.makedirs(text_dir, exist_ok=True)
    os.makedirs(font_dir, exist_ok=True)

    try:
        # Save uploaded files
        video_file = request.files.get('video_file')
        clips_folder = request.files.get('clips_folder')
        mp3_file = request.files.get('mp3_file')
        text_file = request.files.get('text_file')
        font_file = request.files.get('font_file')

        if not video_file or not clips_folder or not mp3_file or not text_file or not font_file:
            return "Missing required files", 400

        video_file_path = os.path.join(video_dir, video_file.filename)
        clips_folder_path = os.path.join(clips_dir, clips_folder.filename)
        mp3_file_path = os.path.join(mp3_dir, mp3_file.filename)
        text_file_path = os.path.join(text_dir, text_file.filename)
        font_file_path = os.path.join(font_dir, font_file.filename)

        video_file.save(video_file_path)
        clips_folder.save(clips_folder_path)
        mp3_file.save(mp3_file_path)
        text_file.save(text_file_path)
        font_file.save(font_file_path)
    except Exception as e:
        return f"An error occurred while saving files: {e}", 500
    
    try:
        shutil.unpack_archive(clips_folder_path, clips_dir)
    except Exception as e:
        return f"An error occurred while unpacking clips folder: {e}", 500
    
    # New parameters
    font_size = request.form.get('font_size')
    box_color = request.form.get('font_color')
    bg_color = request.form.get('bg_color')
    margin = request.form.get('margin', 20)  # Default margin if not provided
    
    if not font_size or not box_color or not bg_color:
        return "Missing required form data", 400

    # Generate the SRT file from TXT and MP3 files
    try:
        srt_file = generate_srt_from_txt_and_audio(Path(text_file_path), Path(mp3_file_path), Path(tmp))
    except Exception as e:
        return f"Failed to generate SRT file: {e}", 500
    
    # Move the SRT file to uploads directory for further processing
    final_srt_path = os.path.join('uploads', 'original_subtitles.srt')
    shutil.move(srt_file, final_srt_path)
    
    # Move the video file to uploads directory for further processing
    final_video_path = os.path.join('uploads', 'original_video.mp4')
    shutil.move(video_file_path, final_video_path)
    
    return redirect(url_for('video_processing_page'))

@app.route('/video_processing')
def video_processing_page():
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Scene Optimisation Bot - Video</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f2f2f2;
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                }
                .container {
                    background-color: white;
                    padding: 20px;
                    border-radius: 10px;
                    box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
                    width: 400px;
                    text-align: center;
                }
                h1 {
                    color: #333;
                }
                video {
                    width: 100%;
                    height: auto;
                    margin-bottom: 20px;
                }
            </style>
            <script>
                function getSceneIndex(currentTime) {
                    fetch(`/get_srt_index?time=${currentTime}`)
                        .```python
                        .then(response => response.json())
                        .then(data => {
                            if (data.srt_index !== -1) {
                                var newFileInput = document.createElement('input');
                                newFileInput.type = 'file';
                                newFileInput.onchange = function(event) {
                                    var file = event.target.files[0];
                                    var formData = new FormData();
                                    formData.append('scene', file);
                                    formData.append('srt_index', data.srt_index);
                                    fetch('/upload_new_scene', {
                                        method: 'POST',
                                        body: formData
                                    }).then(response => {
                                        if (response.ok) {
                                            alert('Scene uploaded and replaced successfully!');
                                        } else {
                                            alert('Failed to upload new scene.');
                                        }
                                    });
                                };
                                newFileInput.click();
                            }
                        })
                        .catch(error => console.error('Error:', error));
                }
            </script>
        </head>
        <body>
            <div class="container">
                <h1>Scene Optimisation Bot - Video</h1>
                <video id="videoPlayer" controls ondblclick="getSceneIndex(this.currentTime)">
                    <source src="/uploads/original_video.mp4" type="video/mp4">
                    Your browser does not support the video tag.
                </video>
            </div>
        </body>
        </html>
    ''')

@app.route('/get_srt_index')
def get_srt_index():
    current_time = float(request.args.get('time'))
    subtitles = load_subtitles_from_file(Path('uploads/original_subtitles.srt'))
    
    # Iterate over the subtitles to find which one matches the current time
    for index, subtitle in enumerate(subtitles):
        start_time = subriptime_to_seconds(subtitle.start)
        end_time = subriptime_to_seconds(subtitle.end)
        if start_time <= current_time <= end_time:
            return {"srt_index": index}
    
    return {"srt_index": -1}  # Return -1 if no matching subtitle is found

@app.route('/upload_new_scene', methods=['POST'])
def upload_new_scene():
    srt_index = int(request.form['srt_index'])
    new_scene = request.files['scene']
    
    # Save the new video segment to a temporary file
    temp_scene_path = os.path.join('tmp', new_scene.filename)
    new_scene.save(temp_scene_path)
    
    # Load the current video and subtitles
    video = load_video_from_file(Path('uploads/original_video.mp4'))
    subtitles = load_subtitles_from_file(Path('uploads/original_subtitles.srt'))
    
    # Determine the corresponding segment and replace it
    start_time = subriptime_to_seconds(subtitles[srt_index].start)
    end_time = subriptime_to_seconds(subtitles[srt_index].end)
    replacement_video = load_video_from_file(Path(temp_scene_path)).subclip(0, end_time - start_time)
    
    video_segments, subtitle_segments = get_segments_using_srt(video, subtitles)
    video_segments[srt_index] = replacement_video
    
    # Assemble the final video
    final_video = concatenate_videoclips(video_segments)
    final_video.write_videofile('static/output_root/final/final_video.mp4', codec="libx264", audio_codec="aac")
    
    return "Success"

@app.route('/uploads/<filename>')
def download_file(filename):
    return send_from_directory('uploads', filename)

def remove_all_files_in_directory(directory):
    if os.path.exists(directory):
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"An error occurred while removing {file_path}: {e}")
    else:
        print(f"Directory {directory} does not exist")

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0')
