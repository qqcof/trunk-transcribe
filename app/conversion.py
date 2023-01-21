import subprocess
import tempfile
from os.path import dirname


def __convert_file(audio_file: str, format: str, ffmpeg_args: list[str]) -> str:
    dir = dirname(audio_file)
    file = tempfile.NamedTemporaryFile(delete=False, dir=dir, suffix=f".{format}")
    file.close()
    p = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            audio_file,
        ]
        + ffmpeg_args
        + [
            file.name,
        ]
    )
    p.check_returncode()
    return file.name


def convert_to_wav(audio_file: str) -> str:
    return __convert_file(
        audio_file,
        "wav",
        [
            "-c:a",
            "pcm_s16le",
            "-ar",
            "16000",
        ],
    )


def convert_to_mp3(audio_file: str) -> str:
    return __convert_file(
        audio_file,
        "mp3",
        [
            "-c:a",
            "libmp3lame",
            "-b:a",
            "32k",
        ],
    )


def convert_to_ogg(audio_file: str) -> str:
    return __convert_file(
        audio_file,
        "ogg",
        [
            "-c:a",
            "libopus",
            "-b:a",
            "128k",
        ],
    )
