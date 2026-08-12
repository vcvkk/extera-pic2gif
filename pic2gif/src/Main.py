# pyright: reportMissingImports=false

import os # noqa: N999
import uuid # noqa: N999
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

def _tempDir():
    tempDir = os.path.join(get_plugins_dir(), "pic2gif_temp")
    ensure_dir_exists(tempDir)
    return tempDir

def _detectFormat(filePath):
    ext = os.path.splitext(filePath)[1].lower()
    return SUPPORTED_FORMATS.get(ext)

def _getReplyPhotoPath(replyMessage):
    if not replyMessage.isPhoto(): return None
    file = get_file_loader().getPathToMessage(replyMessage.messageOwner)
    if file is None or not file.exists(): return None

    return file.getAbsolutePath()


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


def _convertAndSend(peer, sourcePath, decoderName, replyMessage):
    tempDir = _tempDir()
    jobId = uuid.uuid4().hex
    inputCopy = os.path.join(tempDir, f"{jobId}{os.path.splitext(sourcePath)[1].lower()}")
    outputVideo = os.path.join(tempDir, f"{jobId}.mp4")

    try:
        with open(sourcePath, "rb") as src, open(inputCopy, "wb") as dst:
            dst.write(src.read())

        width, height = Native.convertToVideo(inputCopy, outputVideo, decoderName, fps=FPS, durationSeconds=DURATION_SECONDS)

        _sendVideoDocument(peer, outputVideo, width, height, DURATION_SECONDS, replyMessage)
    except Exception as e:
        log(f"p2g: conversion failed: {e}")
        log(traceback.format_exc())
        BulletinHelper.show_error("Failed to create GIF")
    finally:
        try:
            if os.path.exists(inputCopy): os.remove(inputCopy)
        except Exception as e: log(f"p2g: temp cleanup failed for {inputCopy}: {e}")


def handleSendMessageHook(params):
    if not hasattr(params, "message") or not isinstance(params.message, str): return HookResult()

    if params.message.strip() != COMMAND: return HookResult()

    replyMessage = getattr(params, "replyToMsg", None)
    if replyMessage is None:
        BulletinHelper.show_error("Reply to photo file")
        return HookResult(strategy=HookStrategy.CANCEL)

    photoPath = _getReplyPhotoPath(replyMessage)
    if photoPath is None:
        BulletinHelper.show_error("Reply to photo file")
        return HookResult(strategy=HookStrategy.CANCEL)

    decoderName = _detectFormat(photoPath)
    if decoderName is None:
        BulletinHelper.show_error("Unsupported photo format (.png/.jpg/.jpeg)")
        return HookResult(strategy=HookStrategy.CANCEL)

    peer = params.peer

    run_on_queue(lambda: _convertAndSend(peer, photoPath, decoderName, replyMessage))

    return HookResult(strategy=HookStrategy.CANCEL)
