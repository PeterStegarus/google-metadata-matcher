import subprocess
import os
from datetime import datetime, UTC
from auxFunctions import *
import json
from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener()

CLR = "\x1B[0K"
CURSOR_UP_FACTORY = lambda upLines : "\x1B[" + str(upLines) + "A"
CURSOR_DOWN_FACTORY = lambda upLines : "\x1B[" + str(upLines) + "B"

OrientationTagID = 274

piexifCodecs = [k.casefold() for k in ['TIF', 'TIFF', 'JPEG', 'JPG', 'HEIC', 'PNG']]
ffmpegCodecs = [k.casefold() for k in ['MP4', 'MOV']]
supportedCodecs = [*piexifCodecs, *ffmpegCodecs]

def get_media_files_from_folder(folder: str, edited_word: str):
    files: list[tuple[str, str]] = []
    folder_entries = list(os.scandir(folder))

    for entry in folder_entries:
        if entry.is_dir():
            files = files + get_media_files_from_folder(entry.path, edited_word)
            continue

        if entry.is_file():
            (file_name, ext) = os.path.splitext(entry.name)

            if ext == ".json" and file_name != "metadata":
                file = searchMedia(folder, file_name, edited_word)
                files.append((entry.path, file))

    return files

def get_output_filename(root_folder, out_folder, media_file_path):
    (media_file_name, ext) = os.path.splitext(os.path.basename(media_file_path))
    new_media_file_name = media_file_name + (".jpg" if is_image(media_file_path) else ext)
    media_file_path_dir = os.path.dirname(media_file_path)
    relative_to_new_media_file_folder = os.path.relpath(media_file_path_dir, root_folder)
    return os.path.join(out_folder, relative_to_new_media_file_folder, new_media_file_name)

def create_dir_if_not_exists(path):
    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        os.makedirs(dir)

def is_image(media_file_path):
    (_, ext) = os.path.splitext(os.path.basename(media_file_path))
    return ext[1:].casefold() in piexifCodecs

def processFolder(root_folder: str, edited_word: str, optimize: int, out_folder: str, max_dimension):
    errorCounter = 0
    successCounter = 0

    media_files = get_media_files_from_folder(root_folder, edited_word)

    print("Total media files found:", len(media_files))

    for entry in media_files:
        metadata_path = entry[0]
        media_file_path = entry[1]

        print("\n", "Current media file:", media_file_path, is_image(media_file_path), CLR)

        if not media_file_path:
            print(CURSOR_UP_FACTORY(2), "Missing media file for:", metadata_path, CLR, CURSOR_DOWN_FACTORY(2))

            errorCounter += 1
            continue

        (_, ext) = os.path.splitext(media_file_path)
        if not ext[1:].casefold() in supportedCodecs:
            print(CURSOR_UP_FACTORY(2), 'Media format is not supported:', media_file_path, CLR, CURSOR_DOWN_FACTORY(2))
            errorCounter += 1
            continue

        with open(metadata_path, encoding="utf8") as f: 
            metadata = json.load(f)

        if is_image(media_file_path):
            print('image ok')
            # process_image(root_folder, out_folder, max_dimension, optimize, media_file_path, metadata)
        else:
            process_video(root_folder, out_folder, media_file_path, metadata)

        successCounter += 1

    print()
    print('Metadata merging has been finished')
    print('Success', successCounter)
    print('Failed', errorCounter)

def process_image(root_folder, out_folder, max_dimension, optimize, image_path, metadata):
    image = Image.open(image_path, mode="r").convert('RGB')
    image_exif = image.getexif()
    if OrientationTagID in image_exif:
        orientation = image_exif[OrientationTagID]

        if orientation == 3:
            image = image.rotate(180, expand=True)
        elif orientation == 6:
            image = image.rotate(270, expand=True)
        elif orientation == 8:
            image = image.rotate(90, expand=True)

    if max_dimension:
        image.thumbnail(max_dimension)

    new_image_path = get_output_filename(root_folder, out_folder, image_path)

    create_dir_if_not_exists(new_image_path)

    if "exif" in image.info:
        new_exif = adjust_exif(image.info["exif"], metadata)
        image.save(new_image_path, quality=optimize, exif=new_exif)
    else:
        image.save(new_image_path, quality=optimize)

    timestamp = int(metadata['photoTakenTime']['timestamp'])
    setFileCreationTime(new_image_path, timestamp)

def process_video(root_folder, out_folder, input_video_path, metadata):
    output_video_path = get_output_filename(root_folder, out_folder, input_video_path)

    create_dir_if_not_exists(output_video_path)

    lat = metadata['geoData']['latitude']
    lng = metadata['geoData']['longitude']
    location = str(lat) + "+" + str(lng)

    timestamp = int(metadata["photoTakenTime"]["timestamp"])
    datetime_iso_string = datetime.fromtimestamp(timestamp, UTC).isoformat()

    subprocess.run([
        'ffmpeg',
        '-i', input_video_path,
        '-metadata', f'title={metadata["title"]}',
        '-metadata', f'description={metadata["description"]}',
        '-metadata', f'creation_time={datetime_iso_string}',
        '-metadata', f'location={location}',
        '-metadata', f'location-eng={location}',
        '-c', 'copy',
        output_video_path
    ])

    setFileCreationTime(output_video_path, timestamp)
