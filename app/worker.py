#!/usr/bin/env python3

import asyncio
import logging
import os
import tempfile
from base64 import b64decode

import requests
from celery import Celery
from dotenv import load_dotenv

from app.conversion import convert_to_wav
from app.search import ID, RAW_AUDIO_URL, index_call
from app.storage import upload_raw_audio
from app.telegram import send_message

load_dotenv()

broker_url = os.getenv("CELERY_BROKER_URL")
result_backend = os.getenv("CELERY_RESULT_BACKEND")
celery = Celery("worker", broker=broker_url, backend=result_backend)


def transcribe(
    metadata: dict, audio_file: str, debug: bool = False, document: dict | None = None
) -> str:
    if metadata["audio_type"] == "digital":
        from app.digital import transcribe_call
    elif metadata["audio_type"] == "analog":
        from app.analog import transcribe_call
    else:
        raise Exception(f"Audio type {metadata['audio_type']} not supported")

    try:
        transcript = transcribe_call(audio_file, metadata)
    except RuntimeError as e:
        return str(e)
    logging.debug(transcript)

    # Check if we are re-transcribing an existing file
    if document:
        index_call(metadata, document[RAW_AUDIO_URL], transcript, document[ID])
    else:
        try:
            asyncio.run(
                send_message(
                    audio_file,
                    metadata,
                    transcript,
                    dry_run=debug,
                )
            )
        finally:
            raw_audio_url = upload_raw_audio(metadata, audio_file)
            index_call(metadata, raw_audio_url, transcript)

    return transcript


@celery.task(name="transcribe")
def transcribe_task(metadata: dict, audio_file_b64: str, debug: bool = False) -> str:
    with tempfile.TemporaryDirectory() as tempdir:
        audio_file = tempfile.NamedTemporaryFile(
            delete=False, dir=tempdir, suffix=".wav"
        )
        audio_file.write(b64decode(audio_file_b64))
        audio_file.close()

        return transcribe(metadata=metadata, audio_file=audio_file.name, debug=debug)


@celery.task(name="retranscribe")
def retranscribe_task(metadata: dict, audio_url: str, id: str) -> str:
    with tempfile.TemporaryDirectory() as tempdir:
        with requests.get(audio_url, stream=True) as r:
            r.raise_for_status()
            mp3_file = tempfile.NamedTemporaryFile(
                delete=False, dir=tempdir, suffix=".mp3"
            )
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                mp3_file.write(chunk)
            mp3_file.close()

        audio_file = convert_to_wav(mp3_file.name)

        return transcribe(
            metadata=metadata,
            audio_file=audio_file,
            document={RAW_AUDIO_URL: audio_url, ID: id},
        )
