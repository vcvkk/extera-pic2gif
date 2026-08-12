# pyright: reportMissingImports=false

import os # noqa: N999
import time # noqa: N999
import uuid # noqa: N999
import shutil # noqa: N999
import threading # noqa: N999
import traceback # noqa: N999

from android_utils import log, run_on_ui_thread # noqa: N999
from base_plugin import HookResult, HookStrategy # noqa: N999
from client_utils import get_file_loader, get_send_messages_helper, get_connections_manager, run_on_queue # noqa: N999
from file_utils import get_plugins_dir, ensure_dir_exists # noqa: N999
from hook_utils import set_private_field # noqa: N999
from ui.bulletin import BulletinHelper # noqa: N999
from java.util import ArrayList # noqa: N999
from java import jarray, jbyte # noqa: N999
from java.io import File as JFile # noqa: N999
from org.telegram.tgnet import TLRPC # noqa: N999
from org.telegram.messenger import VideoEditedInfo # noqa: N999

from . import Native # noqa: N999

COMMAND = ".ptg"

SUPPORTED_FORMATS = {
    ".png": "png",
    ".jpg": "mjpeg",
    ".jpeg": "mjpeg",
}

FPS = 10
DURATION_SECONDS = 1

MAX_SOURCE_BYTES = 32 * 1024 * 1024
STALE_TEMP_SECONDS = 60 * 60
JOB_TIMEOUT_SECONDS = 120


class _JobGate:
    """Admits one conversion at a time.

    Spamming the command otherwise piles up decoded frames and x264 encoders in
    native memory. The deadline makes the gate self-healing: if a job is ever
    lost before it can release (queue drops the task, process hiccup) the slot
    frees itself instead of disabling the plugin until restart.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._startedAt = None

    def tryAcquire(self):
        with self._lock:
            now = time.monotonic()
            if self._startedAt is not None and now - self._startedAt < JOB_TIMEOUT_SECONDS:
                return False
            self._startedAt = now
            return True

    def release(self):
        with self._lock:
            self._startedAt = None


_gate = _JobGate()


def _showError(text):
    """Bulletins touch the view hierarchy, so they must run on the UI thread.

    Conversions run on a background queue; calling into the UI toolkit from
    there is undefined behaviour and can take the process down natively.
    """
    try:
        run_on_ui_thread(lambda: BulletinHelper.show_error(text))
    except Exception as e:
        log(f"p2g: failed to show bulletin: {e}")


def _tempDir():
    tempDir = os.path.join(get_plugins_dir(), "pic2gif_temp")
    ensure_dir_exists(tempDir)
    return tempDir


def _cleanStaleTemp(tempDir):
    """Drop leftovers from jobs that died before their finally block ran."""
    cutoff = time.time() - STALE_TEMP_SECONDS
    try:
        entries = os.listdir(tempDir)
    except OSError as e:
        log(f"p2g: cannot list temp dir: {e}")
        return

    for name in entries:
        path = os.path.join(tempDir, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError as e:
            log(f"p2g: stale temp cleanup failed for {path}: {e}")


def _removeQuietly(path):
    try:
        if path and os.path.exists(path): os.remove(path)
    except OSError as e:
        log(f"p2g: temp cleanup failed for {path}: {e}")


def _detectFormat(filePath):
    ext = os.path.splitext(filePath)[1].lower()
    return SUPPORTED_FORMATS.get(ext)


def _getReplyPhotoPath(replyMessage):
    try:
        if not replyMessage.isPhoto(): return None
        file = get_file_loader().getPathToMessage(replyMessage.messageOwner)
        if file is None or not file.exists(): return None

        return file.getAbsolutePath()
    except Exception as e:
        log(f"p2g: cannot resolve reply photo path: {e}")
        return None


def _buildVideoDocument(filePath, width, height, durationSeconds):
    jfile = JFile(filePath)

    doc = TLRPC.TL_document()
    doc.id = 0
    doc.access_hash = 0
    doc.file_reference = jarray(jbyte)(0)
    doc.date = get_connections_manager().getCurrentTime()
    doc.mime_type = "video/mp4"
    doc.size = jfile.length()
    doc.dc_id = 0

    attrFileName = TLRPC.TL_documentAttributeFilename()
    attrFileName.file_name = jfile.getName()

    attrVideo = TLRPC.TL_documentAttributeVideo()
    attrVideo.w = width
    attrVideo.h = height
    attrVideo.duration = float(durationSeconds)
    attrVideo.supports_streaming = True

    attrAnimated = TLRPC.TL_documentAttributeAnimated()

    doc.attributes = ArrayList()
    doc.attributes.add(attrFileName)
    doc.attributes.add(attrVideo)
    doc.attributes.add(attrAnimated)
    doc.thumbs = ArrayList()

    return doc


def _sendVideoDocument(peer, filePath, width, height, durationSeconds, replyMessage):
    document = _buildVideoDocument(filePath, width, height, durationSeconds)

    videoEditedInfo = VideoEditedInfo()
    videoEditedInfo.muted = True
    videoEditedInfo.bitrate = -2
    videoEditedInfo.originalWidth = width
    videoEditedInfo.originalHeight = height
    videoEditedInfo.resultWidth = width
    videoEditedInfo.resultHeight = height
    videoEditedInfo.originalPath = filePath
    videoEditedInfo.startTime = -1
    videoEditedInfo.endTime = -1
    videoEditedInfo.estimatedDuration = int(durationSeconds * 1000)
    videoEditedInfo.framerate = FPS

    sendMessagesHelper = get_send_messages_helper()
    messageParams = sendMessagesHelper.SendMessageParams()
    messageParams.peer = peer
    messageParams.document = document
    messageParams.path = filePath
    messageParams.caption = ""
    messageParams.replyToMsg = replyMessage
    messageParams.videoEditedInfo = videoEditedInfo
    # messageParams.notify
    # java.lang.Object.notify()
    set_private_field(messageParams, "notify", True)
    run_on_ui_thread(lambda: sendMessagesHelper.sendMessage(messageParams))


def _copySource(sourcePath, inputCopy):
    size = os.path.getsize(sourcePath)
    if size <= 0:
        raise ValueError("source photo is empty")
    if size > MAX_SOURCE_BYTES:
        raise ValueError(f"source photo too large: {size} bytes")

    # chunked: reading a 30 MB photo into a Python bytes object just to write it
    # straight back out doubles peak memory for no reason
    with open(sourcePath, "rb") as src, open(inputCopy, "wb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)


def _convertAndSend(peer, sourcePath, decoderName, replyMessage):
    inputCopy = None
    outputVideo = None
    sent = False
    try:
        tempDir = _tempDir()
        _cleanStaleTemp(tempDir)

        jobId = uuid.uuid4().hex
        inputCopy = os.path.join(tempDir, f"{jobId}{os.path.splitext(sourcePath)[1].lower()}")
        outputVideo = os.path.join(tempDir, f"{jobId}.mp4")

        _copySource(sourcePath, inputCopy)

        width, height = Native.convertToVideo(inputCopy, outputVideo, decoderName, fps=FPS, durationSeconds=DURATION_SECONDS)

        _sendVideoDocument(peer, outputVideo, width, height, DURATION_SECONDS, replyMessage)
        sent = True
    except Exception as e:
        log(f"p2g: conversion failed: {e}")
        log(traceback.format_exc())
        _showError("Failed to create GIF")
    finally:
        _removeQuietly(inputCopy)
        # the sender owns the mp4 once handed over; otherwise it would sit in
        # the temp dir forever
        if not sent: _removeQuietly(outputVideo)
        _gate.release()


def handleSendMessageHook(params):
    if not hasattr(params, "message") or not isinstance(params.message, str): return HookResult()

    if params.message.strip() != COMMAND: return HookResult()

    replyMessage = getattr(params, "replyToMsg", None)
    if replyMessage is None:
        _showError("Reply to photo file")
        return HookResult(strategy=HookStrategy.CANCEL)

    peer = getattr(params, "peer", None)
    if peer is None:
        _showError("Cannot resolve chat")
        return HookResult(strategy=HookStrategy.CANCEL)

    photoPath = _getReplyPhotoPath(replyMessage)
    if photoPath is None:
        _showError("Reply to photo file")
        return HookResult(strategy=HookStrategy.CANCEL)

    decoderName = _detectFormat(photoPath)
    if decoderName is None:
        _showError("Unsupported photo format (.png/.jpg/.jpeg)")
        return HookResult(strategy=HookStrategy.CANCEL)

    if not _gate.tryAcquire():
        _showError("Already making a GIF, wait a moment")
        return HookResult(strategy=HookStrategy.CANCEL)

    try:
        run_on_queue(lambda: _convertAndSend(peer, photoPath, decoderName, replyMessage))
    except Exception as e:
        _gate.release()
        log(f"p2g: failed to queue conversion: {e}")
        _showError("Failed to create GIF")

    return HookResult(strategy=HookStrategy.CANCEL)
