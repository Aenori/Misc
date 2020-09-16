import sys
import os
import os.path
import subprocess
import math
import datetime as dt

import pydub 

from pydub.silence import detect_silence


FILTERED_ROOT = ['./temp', './out']

def isVideo(f):
    return f.endswith('.mkv')

def extractAudioCmd(video_file, audio_file):
    subprocess.check_output(['ffmpeg', '-i', video_file, '-acodec', 'libmp3lame', audio_file])

def filterRoot(root):
    for filter_ in FILTERED_ROOT:
        if root.startswith(filter_):
            return True

    return False
        
def findAllVideosFiles(root_dir):
    all_videos = []
  
    for root, _, files in os.walk(root_dir):
        if filterRoot(root):
            continue
        
        for f in files:
            if isVideo(f):
                print(f"Found video ! {f}")
                all_videos.append(os.path.join(root, f))

    return all_videos

def createParentDirs(target_filename):
    dir_ = os.path.dirname(target_filename)
    if not os.path.isdir(dir_):
        os.makedirs(dir_)
    
def extractAudioFile(f):
    temp_audio_file = f"temp/{f[:-4]}.mp3" 
    if os.path.isfile(temp_audio_file):
        return temp_audio_file
   
    createParentDirs(temp_audio_file)
    extractAudioCmd(f, temp_audio_file)

    return temp_audio_file

def chunkToTime(c):
    return secondToTime(c // 1000)

def secondToTime(s):
    s = f"{s // 60}:{s % 60:02d}"

    return s

def isChunkEnd(c, duration_seconds):
    return abs(c // 1000 - duration_seconds) < 3

def printResume(video_file, temp_audio_file, duration_seconds, silence_audio_chunks):
    print('#' * 25)
    print(f"  Processing {video_file}")
    print(f"  Temp audio file : {temp_audio_file}")
    print(f"  Video duration ; {secondToTime(int(duration_seconds))}")
    for start, end in silence_audio_chunks:
        start = "debut" if start == 0 else chunkToTime(start)
        end = "fin" if isChunkEnd(end, duration_seconds) else chunkToTime(end)
        print(f"  Silence de {start} à {end}")

def keepBeginAndEndChunk(duration_seconds, audio_chunks):
    filtered_chunks = []

    for start, end in audio_chunks:
        if start == 0:
            filtered_chunks.append([start, end])
        elif isChunkEnd(end, duration_seconds):
            filtered_chunks.append([start, end])
              
    return filtered_chunks

def msToTimeStamp(time, ceil = False, no_hour = False):
    time /= 1000
    s = int(math.ceil(time) if ceil else math.floor(time))

    if no_hour:
        return f'{s // 3600:02d}:{((s // 60) % 60):02d}:{(s % 60):02d}'
    else:
        return f'{((s // 60) % 60):02d}:{(s % 60):02d}'
    
def trimVideo(video_file, silence_audio_chunks, duration_seconds):
    concat_files = len(silence_audio_chunks) > 2
    final_file = f'./out/{video_file}'

    if os.path.isfile(final_file):
        print(f"{final_file} already exist, skipping {video_file}")
        return

    createParentDirs(final_file)
    
    if not silence_audio_chunks[0][0] == 0:
        silence_audio_chunks = [[0, 0]] + silence_audio_chunks
    if not isChunkEnd(silence_audio_chunks[-1][-1], duration_seconds):
        silence_audio_chunks += [[duration_seconds * 1000] * 2]

    if len(silence_audio_chunks) == 2:
        extractVideoSequence(0, silence_audio_chunks, video_file, final_file)
    else:
        temp_files = []
        for i in range(len(silence_audio_chunks) - 1):
            temp_file = f'video_{i}{os.path.splitext(video_file)[1]}'
            extractVideoSequence(i,  silence_audio_chunks, video_file, 'temp/' + temp_file)
            temp_files.append(temp_file)

        concatFiles(temp_files, final_file)

    return final_file, silence_audio_chunks
            
def extractVideoSequence(i,  silence_audio_chunks, video_file, out_file):
    start = msToTimeStamp(silence_audio_chunks[i][-1])
    end = msToTimeStamp(silence_audio_chunks[i+1][0], ceil = True)

    assert(end > start)
    print((start, end))
            
    subprocess.check_output(['ffmpeg',  '-i',  video_file,  '-ss', start, '-to', end, '-c:v', 'copy', '-c:a', 'copy', out_file])

def concatFiles(temp_files, final_file):
    with open('temp/mylist.txt', 'w') as f:
        for temp_file in temp_files:
            f.write(f"file {temp_file}\n")
    
    subprocess.check_output(['ffmpeg', '-f', 'concat', '-safe', '0', '-i', 'temp/mylist.txt', '-c', 'copy', final_file])

    for temp_file in temp_files:
        os.remove(f'temp/{temp_file}')
    
def processVideo(f, log_file):
    print(f'Processing {f}')
    temp_audio_file = extractAudioFile(f)
    
    aus = pydub.AudioSegment.from_file(temp_audio_file, format='mp3')
    silence_audio_chunks = detect_silence(aus, min_silence_len=2000, seek_step=500, silence_thresh=-40)

    print("chunks: ", silence_audio_chunks) 
    printResume(f, temp_audio_file, aus.duration_seconds, silence_audio_chunks)

    if silence_audio_chunks:
        final_file, silence_audio_chunks = trimVideo(f, silence_audio_chunks, aus.duration_seconds) 
        logSuccess(f, final_file, silence_audio_chunks, aus.duration_seconds, log_file)
    else:
        logNothing(f, log_file)

def format_chunk(chunk):
    start, end = chunk

    return f"{msToTimeStamp(start, no_hour = True)} -> {msToTimeStamp(end, ceil = True, no_hour = True)}"
        
def logSuccess(f, final_file, silence_audio_chunks, duration_seconds, log_file):
    content = f""" Successfull processed {f}
  Written in out file {final_file}
  Input duration : {msToTimeStamp(duration_seconds * 1000)}
  Silence cuts : {', '.join(format_chunk(chunk) for chunk in silence_audio_chunks)}
  Output duration : {msToTimeStamp(int(1000 * duration_seconds - sum(end - start for start, end in silence_audio_chunks)))}"""
    
    writeFileResult(content, log_file)
        
def logNothing(f, log_file):
    writeFileResult(f'  Nothing to do for {f}', log_file)
        
def logError(f, e, log_file):
    writeFileResult(f"""  Issue while processing : {f}
{e}""", log_file)

def writeFileResult(content, log_file):
    write_ln = lambda s : print(s, file=log_file)
    write_ln('#' * 25)
    write_ln(content)
    write_ln('#' * 25)

def processVideos(all_videos):
    for processing_dir in ['temp', 'out']:
        if not os.path.isdir(processing_dir):
            os.mkdir(processing_dir)

    with open(f'video_processing_log_{dt.datetime.now().strftime("%Y%m%d_%H%M")}.log', 'w') as log_file:
        for f in all_videos:
            try:
                processVideo(f, log_file)
            except Exception as e:
                logError(f, e, log_file)

def main(root_dir):
    all_videos = findAllVideosFiles(root_dir)
    processVideos(all_videos)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        main('.')
    else:
        main(sys.argv[1])

