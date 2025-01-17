#!/usr/bin/env python3

import logging
import os
import signal
import tempfile

import requests
import sentry_sdk
from celery import Celery, signals, states
from celery.exceptions import Reject
from datauri import DataURI
from dotenv import load_dotenv
from sentry_sdk.integrations.celery import CeleryIntegration

from app.analog import transcribe_call as transcribe_analog
from app.conversion import convert_to_wav
from app.digital import transcribe_call as transcribe_digital
from app.metadata import Metadata
from app.notification import send_notifications
from app.search import index_call

load_dotenv()

sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[
            CeleryIntegration(),
        ],
        release=os.getenv("GIT_COMMIT"),
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=float(os.getenv("SENTRY_TRACE_SAMPLE_RATE", "0.1")),
        _experiments={
            "profiles_sample_rate": float(
                os.getenv("SENTRY_PROFILE_SAMPLE_RATE", "0.1")
            ),
        },
    )

broker_url = os.getenv("CELERY_BROKER_URL")
result_backend = os.getenv("CELERY_RESULT_BACKEND")
celery = Celery(
    "worker",
    broker=broker_url,
    backend=result_backend,
    task_cls="app.whisper:WhisperTask",
    task_acks_late=True,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
)

task_counts = {}


@signals.task_prerun.connect
def task_prerun(**kwargs):
    # If we've only had failing tasks on this worker, terminate it
    if states.SUCCESS not in task_counts and len(
        [
            count
            for state, count in task_counts.items()
            if state in states.EXCEPTION_STATES and count > 5
        ]
    ):
        logging.fatal("Exceeded job failure threshold, exiting...\n" + str(task_counts))
        os.kill(os.getppid(), signal.SIGQUIT if hasattr(signal, "SIGQUIT") else signal.SIGTERM)


@signals.task_postrun.connect
def task_postrun(**kwargs):
    if kwargs["state"] not in task_counts:
        task_counts[kwargs["state"]] = 0
    task_counts[kwargs["state"]] += 1


@signals.task_unknown.connect
def task_unknown(**kwargs):
    logging.exception(kwargs["exc"])
    logging.fatal("Unknown job, exiting...")
    os.kill(os.getpid(), signal.SIGQUIT)


def transcribe(
    model,
    model_lock,
    metadata: Metadata,
    audio_file: str,
    mp3_file: str,
    raw_audio_url: str,
    id: str | None = None,
    index_name: str | None = None,
) -> str:
    try:
        if (
            metadata["audio_type"] == "digital"
            or metadata["audio_type"] == "digital tdma"
        ):
            transcript = transcribe_digital(model, model_lock, audio_file, metadata)
        elif metadata["audio_type"] == "analog":
            transcript = transcribe_analog(model, model_lock, audio_file)
        else:
            raise Reject(f"Audio type {metadata['audio_type']} not supported")
    except RuntimeError as e:
        return repr(e)
    logging.debug(transcript.json)

    search_url = index_call(
        metadata, raw_audio_url, transcript, id, index_name=index_name
    )

    # Do not send Telegram messages for calls we already have transcribed previously
    if not id:
        send_notifications(audio_file, metadata, transcript, mp3_file, search_url)

    return transcript.txt


@celery.task(name="transcribe")
def transcribe_task(
    metadata: Metadata,
    audio_url: str,
    id: str | None = None,
    index_name: str | None = None,
) -> str:
    with tempfile.TemporaryDirectory() as tempdir:
        mp3_file = tempfile.NamedTemporaryFile(delete=False, dir=tempdir, suffix=".mp3")
        if audio_url.startswith("data:"):
            uri = DataURI(audio_url)
            mp3_file.write(uri.data)  # type: ignore
            mp3_file.close()
        else:
            with requests.get(audio_url, stream=True) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    mp3_file.write(chunk)
                mp3_file.close()

        audio_file = convert_to_wav(mp3_file.name)

        return transcribe(
            transcribe_task.model,
            transcribe_task.model_lock,
            metadata,
            audio_file,
            mp3_file.name,
            audio_url,
            id,
            index_name,
        )
