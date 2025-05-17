#!/usr/bin/env python

import os
import argparse
import fitz  # PyMuPDF
from gtts import gTTS
from progress.bar import Bar
from subprocess import DEVNULL, STDOUT, call, PIPE, run
import shutil
import sys

def pdf_to_video(pdf_file: str, output_file: str) -> None:
    print(f"Starting conversion of {pdf_file} to {output_file}")
    print(f"Current working directory: {os.getcwd()}")
    
    # Remove spaces from filenames
    name = os.path.splitext(os.path.basename(pdf_file))[0].replace(' ', '_')
    tmp_dir = 'tmp_pdf'
    os.makedirs(tmp_dir, exist_ok=True)
    
    try:
        doc = fitz.open(pdf_file)
        N = doc.page_count
        print(f"PDF opened successfully. Number of pages: {N}")

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

                page = doc.load_page(i)
                text = page.get_text().strip()
                print(f"Extracted text length: {len(text)} characters")
                bar.next()

                pix = page.get_pixmap()
                pix.save(image_path)
                print(f"Saved image to {image_path}")
                bar.next()

                if not text:
                    text = 'No text found.'
                try:
                    tts = gTTS(text=text, lang='en')
                    tts.save(audio_path)
                    print(f"Saved audio to {audio_path}")
                except Exception as e:
                    print(f"Error generating TTS: {str(e)}")
                bar.next()

                ffmpeg_args = [
                    '-y',
                    '-loop', '1',
                    '-i', image_path,
                    '-i', audio_path,
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
    args = parser.parse_args()
    pdf_to_video(args.pdf, args.output)

if __name__ == '__main__':
    main() 