#!/usr/bin/env python

import os
import argparse
import fitz  # PyMuPDF
from gtts import gTTS
from progress.bar import Bar
from subprocess import DEVNULL, STDOUT, call, PIPE, run
import shutil
import sys
import re
import urllib.request

def extract_markdown_from_pdf(pdf_file: str, num_pages: int = None, start_page: int = 0) -> list:
    """
    Extract text from PDF and convert to markdown format.
    Returns a list of markdown strings, one for each page.
    
    Parameters
    ----------
    pdf_file : str
        Path to the PDF file
    num_pages : int, optional
        Number of pages to convert. If None, converts all pages.
    start_page : int, optional
        The starting page index (0-based). Default is 0.
    """
    doc = fitz.open(pdf_file)
    markdown_pages = []
    
    # Calculate the range of pages to process
    if num_pages is None:
        pages_to_process = range(start_page, doc.page_count)
    else:
        pages_to_process = range(start_page, min(start_page + num_pages, doc.page_count))
    
    for page_num in pages_to_process:
        page = doc[page_num]
        # Get text blocks with their formatting
        blocks = page.get_text("dict")["blocks"]
        markdown_text = []
        
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        if not text:
                            continue
                            
                        # Check font size to determine headers
                        font_size = span["size"]
                        if font_size > 14:  # Adjust threshold as needed
                            markdown_text.append(f"\n## {text}\n")
                        else:
                            markdown_text.append(text)
                            
                    markdown_text.append("\n")
        
        # Join the text and clean up
        page_text = " ".join(markdown_text)
        page_text = re.sub(r'\n\s*\n', '\n\n', page_text)  # Remove extra newlines
        markdown_pages.append(page_text.strip())
    
    return markdown_pages

def markdown_to_speech_text(markdown_text: str) -> str:
    """
    Convert markdown text to speech-friendly text for Japanese.
    Adds natural pauses between sections.
    """
    # Add pauses for headers
    text = re.sub(r'##\s*(.*?)\n', r'\1。', markdown_text)
    
    # Add pauses for paragraphs
    text = re.sub(r'\n\n', '。', text)
    
    # Clean up multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    # Add natural pauses with Japanese punctuation
    text = re.sub(r'([。！？])\s*', r'\1 ', text)
    
    # Ensure proper spacing after Japanese punctuation
    text = re.sub(r'([。！？])([^\s])', r'\1 \2', text)
    
    return text.strip()

def download_background_music(output_path: str) -> str:
    """
    Get background music from a local file or download if not available.
    Returns the path to the music file.
    """
    # First try to use a local music file
    local_music_path = "background_music.mp3"
    if os.path.exists(local_music_path):
        print("Using local background music file")
        return local_music_path
        
    # If no local file exists, create a simple tone using FFmpeg
    try:
        print("Creating background music...")
        ffmpeg_args = [
            '-y',
            '-f', 'lavfi',
            '-i', 'sine=frequency=440:duration=3600',  # 1-hour long tone
            '-filter:a', 'volume=0.1',  # Low volume
            output_path
        ]
        result = run(['ffmpeg'] + ffmpeg_args, 
                    stdout=PIPE, stderr=PIPE, text=True)
        if result.returncode == 0:
            print(f"Background music created at {output_path}")
            return output_path
    except Exception as e:
        print(f"Error creating background music: {str(e)}")
    
    return None

def pdf_to_video(pdf_file: str, output_file: str, num_pages: int = None, start_page: int = 0) -> None:
    print(f"Starting conversion of {pdf_file} to {output_file}")
    if num_pages:
        print(f"Converting {num_pages} pages starting from page {start_page + 1}")
    print(f"Current working directory: {os.getcwd()}")
    
    # Remove spaces from filenames
    name = os.path.splitext(os.path.basename(pdf_file))[0].replace(' ', '_')
    tmp_dir = 'tmp_pdf'
    os.makedirs(tmp_dir, exist_ok=True)
    
    try:
        # Download background music
        bg_music_path = os.path.join(tmp_dir, 'background_music.mp3')
        bg_music_path = download_background_music(bg_music_path)
        
        # Extract markdown from PDF
        print("Converting PDF to Markdown...")
        markdown_pages = extract_markdown_from_pdf(pdf_file, num_pages, start_page)
        N = len(markdown_pages)
        print(f"PDF converted successfully. Number of pages: {N}")

        print('Creating MP3s (TTS) and PNGs for each page, then combining them into MP4...')
        bar = Bar('Processing pages', max=5*N, suffix='%(percent)d%%')
        list_txt_path = os.path.join(tmp_dir, 'list.txt')
        
        with open(list_txt_path, 'w') as list_txt:
            for i in range(N):
                file_name = os.path.join(tmp_dir, f'{name}_page_{i+1}')
                image_path = f'{file_name}.png'
                audio_path = f'{file_name}.mp3'
                out_path_mp4 = f'{file_name}.mp4'

                print(f"\nProcessing page {i+1}/{N}")
                print(f"Image path: {image_path}")
                print(f"Audio path: {audio_path}")
                print(f"Output path: {out_path_mp4}")

                # Write the absolute path to the list.txt file
                list_txt.write(f"file '{os.path.abspath(out_path_mp4)}'\n")

                if os.path.exists(out_path_mp4):
                    print(f"Video for page {i+1} already exists, skipping...")
                    bar.next(); bar.next(); bar.next(); bar.next(); bar.next()
                    continue

                # Convert page to image
                doc = fitz.open(pdf_file)
                page = doc.load_page(start_page + i)
                pix = page.get_pixmap()
                pix.save(image_path)
                print(f"Saved image to {image_path}")
                bar.next()

                # Convert markdown to speech-friendly text
                speech_text = markdown_to_speech_text(markdown_pages[i])
                if not speech_text:
                    speech_text = 'テキストが見つかりませんでした。'
                print(f"Extracted text length: {len(speech_text)} characters")
                bar.next()

                try:
                    tts = gTTS(text=speech_text, lang='ja')
                    tts.save(audio_path)
                    print(f"Saved audio to {audio_path}")
                except Exception as e:
                    print(f"Error generating TTS: {str(e)}")
                bar.next()

                # Mix narration with background music
                mixed_audio_path = f'{file_name}_mixed.mp3'
                if bg_music_path:
                    ffmpeg_mix_args = [
                        '-y',
                        '-i', audio_path,
                        '-i', bg_music_path,
                        '-filter_complex', '[0:a]volume=1.0[a1];[1:a]volume=0.2[a2];[a1][a2]amix=inputs=2:duration=longest',
                        mixed_audio_path
                    ]
                    try:
                        result = run(['ffmpeg'] + ffmpeg_mix_args, 
                                   stdout=PIPE, stderr=PIPE, text=True)
                        if result.returncode != 0:
                            print(f"FFmpeg error during audio mixing: {result.stderr}")
                            mixed_audio_path = audio_path  # Fallback to original audio
                    except Exception as e:
                        print(f"Error mixing audio: {str(e)}")
                        mixed_audio_path = audio_path  # Fallback to original audio
                else:
                    mixed_audio_path = audio_path

                ffmpeg_args = [
                    '-y',
                    '-loop', '1',
                    '-i', image_path,
                    '-i', mixed_audio_path,
                    '-c:v', 'libx264',
                    '-tune', 'stillimage',
                    '-c:a', 'aac',
                    '-b:a', '192k',
                    '-pix_fmt', 'yuv420p',
                    '-shortest',
                    out_path_mp4
                ]
                
                try:
                    result = run(['ffmpeg'] + ffmpeg_args, 
                               stdout=PIPE, stderr=PIPE, text=True)
                    if result.returncode != 0:
                        print(f"FFmpeg error: {result.stderr}")
                    else:
                        print(f"Created video for page {i+1}")
                except Exception as e:
                    print(f"Error running FFmpeg: {str(e)}")
                bar.next()
            bar.finish()

        print(f'\nCombining the MP4s for all pages into the single output video {output_file}...')
        ffmpeg_args = [
            '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', list_txt_path,
            '-c', 'copy',
            output_file
        ]
        
        try:
            result = run(['ffmpeg'] + ffmpeg_args, 
                        stdout=PIPE, stderr=PIPE, text=True)
            if result.returncode != 0:
                print(f"FFmpeg error during final combination: {result.stderr}")
            else:
                print('Done!')
        except Exception as e:
            print(f"Error running FFmpeg for final combination: {str(e)}")
            
        if os.path.exists(output_file):
            print(f"Final video created successfully at: {os.path.abspath(output_file)}")
        else:
            print("Error: Final video file was not created!")
            
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print('Temporary files cleaned up.')
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--pdf', type=str, required=True, help='Input PDF file to convert.')
    parser.add_argument('-o', '--output', type=str, required=True, help='Output MP4 file for video.')
    parser.add_argument('-n', '--num-pages', type=int, help='Number of pages to convert (default: all pages)')
    parser.add_argument('-s', '--start-page', type=int, default=0, help='Starting page index (0-based, default: 0)')
    args = parser.parse_args()
    pdf_to_video(args.pdf, args.output, args.num_pages, args.start_page)

if __name__ == '__main__':
    main() 