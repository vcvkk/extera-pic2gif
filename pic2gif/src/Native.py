import os # noqa: N999
import ctypes # noqa: N999
# pyright: reportMissingImports=false
from android_utils import log # noqa: N999
from file_utils import get_plugins_dir # noqa: N999

PLUGIN_ID = "shareui_ptg"
PLUGIN_FOLDER = "pic2gif"

_archDir = None
_libs = None

# AVPixelFormat vals
AV_PIX_FMT_RGBA = 26
AV_PIX_FMT_RGB8 = 20
AV_PIX_FMT_YUV420P = 0

AVIO_FLAG_WRITE = 2
AV_ERROR_MAX_STRING_SIZE = 64
AV_CODEC_FLAG_GLOBAL_HEADER = 1 << 22


class AVRational(ctypes.Structure):
    _fields_ = [
        ("num", ctypes.c_int),
        ("den", ctypes.c_int),
    ]

class AVFrame(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.c_void_p * 8),
        ("linesize", ctypes.c_int * 8),
        ("extended_data", ctypes.POINTER(ctypes.c_void_p)),
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("nb_samples", ctypes.c_int),
        ("format", ctypes.c_int),
        ("key_frame", ctypes.c_int),
        ("pict_type", ctypes.c_int),
        ("sample_aspect_ratio", AVRational),
        ("pts", ctypes.c_int64),
    ]

class AVCodecContext(ctypes.Structure):
    _fields_ = [
        ("av_class", ctypes.c_void_p),
        ("log_level_offset", ctypes.c_int),
        ("codec_type", ctypes.c_int),
        ("codec", ctypes.c_void_p),
        ("codec_id", ctypes.c_int),
        ("codec_tag", ctypes.c_uint),
        ("priv_data", ctypes.c_void_p),
        ("internal", ctypes.c_void_p),
        ("opaque", ctypes.c_void_p),
        ("bit_rate", ctypes.c_int64),
        ("bit_rate_tolerance", ctypes.c_int),
        ("global_quality", ctypes.c_int),
        ("compression_level", ctypes.c_int),
        ("flags", ctypes.c_int),
        ("flags2", ctypes.c_int),
        ("extradata", ctypes.c_void_p),
        ("extradata_size", ctypes.c_int),
        ("time_base", AVRational),
        ("ticks_per_frame", ctypes.c_int),
        ("delay", ctypes.c_int),
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("coded_width", ctypes.c_int),
        ("coded_height", ctypes.c_int),
        ("gop_size", ctypes.c_int),
        ("pix_fmt", ctypes.c_int),
    ]

class AVStream(ctypes.Structure):
    _fields_ = [
        ("av_class", ctypes.c_void_p),
        ("index", ctypes.c_int),
        ("id", ctypes.c_int),
        ("codecpar", ctypes.c_void_p),
        ("priv_data", ctypes.c_void_p),
        ("time_base", AVRational),
    ]

class AVFormatContext(ctypes.Structure):
    _fields_ = [
        ("av_class", ctypes.c_void_p),
        ("iformat", ctypes.c_void_p),
        ("oformat", ctypes.c_void_p),
        ("priv_data", ctypes.c_void_p),
        ("pb", ctypes.c_void_p),
        ("ctx_flags", ctypes.c_int),
        ("nb_streams", ctypes.c_uint),
        ("streams", ctypes.POINTER(ctypes.POINTER(AVStream))),
        ("url", ctypes.c_char_p),
    ]


class AVPacket(ctypes.Structure):
    _fields_ = [
        ("buf", ctypes.c_void_p),
        ("pts", ctypes.c_int64),
        ("dts", ctypes.c_int64),
        ("data", ctypes.c_void_p),
        ("size", ctypes.c_int),
        ("stream_index", ctypes.c_int),
        ("flags", ctypes.c_int),
        ("side_data", ctypes.c_void_p),
        ("side_data_elems", ctypes.c_int),
        ("duration", ctypes.c_int64),
        ("pos", ctypes.c_int64),
        ("opaque", ctypes.c_void_p),
        ("opaque_ref", ctypes.c_void_p),
        ("time_base", AVRational),
    ]


class FFmpegError(Exception): pass


def _resolveArchDir():
    global _archDir
    if _archDir is not None:
        return _archDir

    from android.os import Build
    abi = Build.SUPPORTED_ABIS[0]

    pluginDir = os.path.join(get_plugins_dir(), "ElyxPlugins", PLUGIN_ID, PLUGIN_FOLDER)
    if "arm64" in abi: _archDir = os.path.join(pluginDir, "ffmpeg", "arm64-v8a", "lib")
    else: _archDir = os.path.join(pluginDir, "ffmpeg", "armeabi-v7a", "lib")
    log(f"p2g: resolved ffmpeg arch dir for abi {abi}: {_archDir}")
    return _archDir


def _loadLibs():
    global _libs
    if _libs is not None:
        return _libs

    libDir = _resolveArchDir()

    avutil = ctypes.CDLL(os.path.join(libDir, "libavutil.so"), mode=ctypes.RTLD_GLOBAL)
    avcodec = ctypes.CDLL(os.path.join(libDir, "libavcodec.so"), mode=ctypes.RTLD_GLOBAL)
    avformat = ctypes.CDLL(os.path.join(libDir, "libavformat.so"), mode=ctypes.RTLD_GLOBAL)
    swscale = ctypes.CDLL(os.path.join(libDir, "libswscale.so"), mode=ctypes.RTLD_GLOBAL)

    _declareSignatures(avutil, avcodec, avformat, swscale)
    _libs = (avutil, avcodec, avformat, swscale)
    log("p2g: ffmpeg libraries loaded")
    return _libs


def _declareSignatures(avutil, avcodec, avformat, swscale):
    c_void_p = ctypes.c_void_p
    c_int = ctypes.c_int
    c_char_p = ctypes.c_char_p

    avutil.av_frame_alloc.restype = ctypes.POINTER(AVFrame)
    avutil.av_frame_free.argtypes = [ctypes.POINTER(ctypes.POINTER(AVFrame))]
    avutil.av_frame_get_buffer.argtypes = [ctypes.POINTER(AVFrame), c_int]
    avutil.av_frame_get_buffer.restype = c_int
    avutil.av_frame_unref.argtypes = [ctypes.POINTER(AVFrame)]

    avutil.av_strerror.argtypes = [c_int, c_char_p, ctypes.c_size_t]
    avutil.av_strerror.restype = c_int

    avutil.av_opt_set.argtypes = [c_void_p, c_char_p, c_char_p, c_int]
    avutil.av_opt_set.restype = c_int

    avcodec.avcodec_find_decoder_by_name.argtypes = [c_char_p]
    avcodec.avcodec_find_decoder_by_name.restype = c_void_p
    avcodec.avcodec_find_encoder_by_name.argtypes = [c_char_p]
    avcodec.avcodec_find_encoder_by_name.restype = c_void_p

    avcodec.avcodec_alloc_context3.argtypes = [c_void_p]
    avcodec.avcodec_alloc_context3.restype = ctypes.POINTER(AVCodecContext)
    avcodec.avcodec_free_context.argtypes = [ctypes.POINTER(ctypes.POINTER(AVCodecContext))]

    avcodec.avcodec_open2.argtypes = [ctypes.POINTER(AVCodecContext), c_void_p, ctypes.POINTER(c_void_p)]
    avcodec.avcodec_open2.restype = c_int

    avcodec.avcodec_send_packet.argtypes = [ctypes.POINTER(AVCodecContext), ctypes.POINTER(AVPacket)]
    avcodec.avcodec_send_packet.restype = c_int
    avcodec.avcodec_receive_frame.argtypes = [ctypes.POINTER(AVCodecContext), ctypes.POINTER(AVFrame)]
    avcodec.avcodec_receive_frame.restype = c_int
    avcodec.avcodec_send_frame.argtypes = [ctypes.POINTER(AVCodecContext), ctypes.POINTER(AVFrame)]
    avcodec.avcodec_send_frame.restype = c_int
    avcodec.avcodec_receive_packet.argtypes = [ctypes.POINTER(AVCodecContext), ctypes.POINTER(AVPacket)]
    avcodec.avcodec_receive_packet.restype = c_int

    avcodec.av_packet_alloc.restype = ctypes.POINTER(AVPacket)
    avcodec.av_packet_free.argtypes = [ctypes.POINTER(ctypes.POINTER(AVPacket))]
    avcodec.av_packet_from_data.argtypes = [ctypes.POINTER(AVPacket), c_void_p, c_int]
    avcodec.av_packet_from_data.restype = c_int
    avcodec.av_packet_unref.argtypes = [ctypes.POINTER(AVPacket)]

    avcodec.avcodec_parameters_from_context.argtypes = [c_void_p, ctypes.POINTER(AVCodecContext)]
    avcodec.avcodec_parameters_from_context.restype = c_int

    avformat.av_guess_format.argtypes = [c_char_p, c_char_p, c_char_p]
    avformat.av_guess_format.restype = c_void_p

    avformat.avformat_alloc_output_context2.argtypes = [
        ctypes.POINTER(ctypes.POINTER(AVFormatContext)), c_void_p, c_char_p, c_char_p
    ]
    avformat.avformat_alloc_output_context2.restype = c_int

    avformat.avformat_new_stream.argtypes = [ctypes.POINTER(AVFormatContext), c_void_p]
    avformat.avformat_new_stream.restype = ctypes.POINTER(AVStream)

    avformat.avformat_free_context.argtypes = [ctypes.POINTER(AVFormatContext)]

    avformat.avio_open.argtypes = [ctypes.POINTER(c_void_p), c_char_p, c_int]
    avformat.avio_open.restype = c_int
    avformat.avio_closep.argtypes = [ctypes.POINTER(c_void_p)]
    avformat.avio_closep.restype = c_int

    avformat.avformat_write_header.argtypes = [ctypes.POINTER(AVFormatContext), ctypes.POINTER(c_void_p)]
    avformat.avformat_write_header.restype = c_int
    avformat.av_interleaved_write_frame.argtypes = [ctypes.POINTER(AVFormatContext), ctypes.POINTER(AVPacket)]
    avformat.av_interleaved_write_frame.restype = c_int
    avformat.av_write_trailer.argtypes = [ctypes.POINTER(AVFormatContext)]
    avformat.av_write_trailer.restype = c_int

    swscale.sws_getContext.argtypes = [
        c_int, c_int, c_int, c_int, c_int, c_int, c_int, c_void_p, c_void_p, c_void_p
    ]
    swscale.sws_getContext.restype = c_void_p
    swscale.sws_freeContext.argtypes = [c_void_p]
    swscale.sws_scale_frame.argtypes = [c_void_p, ctypes.POINTER(AVFrame), ctypes.POINTER(AVFrame)]
    swscale.sws_scale_frame.restype = c_int


def _errStr(avutil, code):
    buf = ctypes.create_string_buffer(AV_ERROR_MAX_STRING_SIZE)
    avutil.av_strerror(code, buf, AV_ERROR_MAX_STRING_SIZE)
    return buf.value.decode("utf-8", "replace")


def _decodeImage(avutil, avcodec, inputPath, decoderName): # frame, ctx, pkt, buf
    with open(inputPath, "rb") as f:
        raw = f.read()

    decoder = avcodec.avcodec_find_decoder_by_name(decoderName.encode())
    if not decoder:
        raise FFmpegError(f"decoder '{decoderName}' not found")

    ctx = avcodec.avcodec_alloc_context3(decoder)
    if not ctx:
        raise FFmpegError("avcodec_alloc_context3 failed")

    ret = avcodec.avcodec_open2(ctx, decoder, None)
    if ret < 0:
        avcodec.avcodec_free_context(ctypes.byref(ctx))
        raise FFmpegError(f"avcodec_open2 failed: {_errStr(avutil, ret)}")

    pkt = avcodec.av_packet_alloc()
    buf = ctypes.create_string_buffer(raw, len(raw))
    ret = avcodec.av_packet_from_data(pkt, ctypes.cast(buf, ctypes.c_void_p), len(raw))
    if ret < 0:
        avcodec.avcodec_free_context(ctypes.byref(ctx))
        raise FFmpegError(f"av_packet_from_data failed: {_errStr(avutil, ret)}")

    ret = avcodec.avcodec_send_packet(ctx, pkt)
    if ret < 0:
        avcodec.avcodec_free_context(ctypes.byref(ctx))
        raise FFmpegError(f"avcodec_send_packet failed: {_errStr(avutil, ret)}")

    frame = avutil.av_frame_alloc()
    ret = avcodec.avcodec_receive_frame(ctx, frame)
    if ret < 0:
        avutil.av_frame_free(ctypes.byref(frame))
        avcodec.avcodec_free_context(ctypes.byref(ctx))
        raise FFmpegError(f"avcodec_receive_frame failed: {_errStr(avutil, ret)}")

    return frame, ctx, pkt, buf


def _scaleFrame(avutil, swscale, srcFrame, dstW, dstH, dstFormat):
    swsCtx = swscale.sws_getContext(
        srcFrame.contents.width, srcFrame.contents.height, srcFrame.contents.format,
        dstW, dstH, dstFormat,
        2,  # SWS_BILINEAR
        None, None, None,
    )
    if not swsCtx:
        raise FFmpegError("sws_getContext failed")

    dstFrame = avutil.av_frame_alloc()
    dstFrame.contents.width = dstW
    dstFrame.contents.height = dstH
    dstFrame.contents.format = dstFormat

    ret = avutil.av_frame_get_buffer(dstFrame, 0)
    if ret < 0:
        swscale.sws_freeContext(swsCtx)
        avutil.av_frame_free(ctypes.byref(dstFrame))
        raise FFmpegError(f"av_frame_get_buffer failed: {_errStr(avutil, ret)}")

    ret = swscale.sws_scale_frame(swsCtx, dstFrame, srcFrame)
    swscale.sws_freeContext(swsCtx)
    if ret < 0:
        avutil.av_frame_free(ctypes.byref(dstFrame))
        raise FFmpegError(f"sws_scale_frame failed: {_errStr(avutil, ret)}")

    return dstFrame


def convertToVideo(inputPath, outputPath, decoderName, fps=10, durationSeconds=1):
    avutil, avcodec, avformat, swscale = _loadLibs()

    log("p2g: decoding image")
    frame, decCtx, decPkt, _rawBuf = _decodeImage(avutil, avcodec, inputPath, decoderName)

    dstW = (frame.contents.width // 2) * 2
    dstH = (frame.contents.height // 2) * 2
    if dstW <= 0 or dstH <= 0:
        raise FFmpegError("invalid image dimensions after scaling")

    log(f"p2g: scaling to {dstW}x{dstH} yuv420p")
    scaledFrame = _scaleFrame(avutil, swscale, frame, dstW, dstH, AV_PIX_FMT_YUV420P)

    log("p2g: allocating output context")
    fmtCtx = ctypes.POINTER(AVFormatContext)()
    ret = avformat.avformat_alloc_output_context2(ctypes.byref(fmtCtx), None, b"mp4", outputPath.encode())
    if ret < 0:
        raise FFmpegError(f"avformat_alloc_output_context2 failed: {_errStr(avutil, ret)}")

    log("p2g: finding h264 encoder")
    encoder = avcodec.avcodec_find_encoder_by_name(b"libx264")
    if not encoder:
        raise FFmpegError("libx264 encoder not found")

    log("p2g: creating stream")
    stream = avformat.avformat_new_stream(fmtCtx, encoder)
    if not stream:
        raise FFmpegError("avformat_new_stream failed")

    log("p2g: allocating encoder context")
    encCtx = avcodec.avcodec_alloc_context3(encoder)
    if not encCtx:
        raise FFmpegError("avcodec_alloc_context3 (encoder) failed")

    log("p2g: configuring encoder context")
    encCtx.contents.width = dstW
    encCtx.contents.height = dstH
    encCtx.contents.pix_fmt = AV_PIX_FMT_YUV420P
    encCtx.contents.time_base = AVRational(1, fps)
    encCtx.contents.gop_size = fps
    encCtx.contents.bit_rate = 2_000_000
    encCtx.contents.flags = encCtx.contents.flags | AV_CODEC_FLAG_GLOBAL_HEADER

    avutil.av_opt_set(encCtx, b"threads", b"1", 0)

    avutil.av_opt_set(encCtx.contents.priv_data, b"rc-lookahead", b"0", 0)
    avutil.av_opt_set(encCtx.contents.priv_data, b"preset", b"ultrafast", 0)

    log("p2g: opening encoder")
    ret = avcodec.avcodec_open2(encCtx, encoder, None)
    if ret < 0:
        raise FFmpegError(f"avcodec_open2 (encoder) failed: {_errStr(avutil, ret)}")

    log("p2g: copying codec parameters to stream")
    avcodec.avcodec_parameters_from_context(stream.contents.codecpar, encCtx)
    stream.contents.time_base = AVRational(1, fps)

    log("p2g: opening avio")
    avioCtx = ctypes.c_void_p()
    ret = avformat.avio_open(ctypes.byref(avioCtx), outputPath.encode(), AVIO_FLAG_WRITE)
    if ret < 0:
        raise FFmpegError(f"avio_open failed: {_errStr(avutil, ret)}")
    fmtCtx.contents.pb = avioCtx.value

    log("p2g: writing header")
    ret = avformat.avformat_write_header(fmtCtx, None)
    if ret < 0:
        raise FFmpegError(f"avformat_write_header failed: {_errStr(avutil, ret)}")

    totalFrames = fps * durationSeconds
    outPkt = avcodec.av_packet_alloc()

    for i in range(totalFrames):
        log(f"p2g: encoding frame {i}")
        scaledFrame.contents.pts = i

        ret = avcodec.avcodec_send_frame(encCtx, scaledFrame)
        if ret < 0:
            raise FFmpegError(f"avcodec_send_frame failed: {_errStr(avutil, ret)}")

        while True:
            ret = avcodec.avcodec_receive_packet(encCtx, outPkt)
            if ret < 0:
                break
            outPkt.contents.stream_index = stream.contents.index
            avformat.av_interleaved_write_frame(fmtCtx, outPkt)
            avcodec.av_packet_unref(outPkt)

    log("p2g: flushing encoder")
    avcodec.avcodec_send_frame(encCtx, None)
    while True:
        ret = avcodec.avcodec_receive_packet(encCtx, outPkt)
        if ret < 0:
            break
        outPkt.contents.stream_index = stream.contents.index
        avformat.av_interleaved_write_frame(fmtCtx, outPkt)
        avcodec.av_packet_unref(outPkt)

    log("p2g: writing trailer")
    avformat.av_write_trailer(fmtCtx)

    log("p2g: cleaning up")
    avcodec.av_packet_free(ctypes.byref(outPkt))
    avioCtx.value = fmtCtx.contents.pb
    avformat.avio_closep(ctypes.byref(avioCtx))
    avcodec.avcodec_free_context(ctypes.byref(encCtx))
    avformat.avformat_free_context(fmtCtx)

    avutil.av_frame_free(ctypes.byref(scaledFrame))
    avutil.av_frame_free(ctypes.byref(frame))
    avcodec.av_packet_free(ctypes.byref(decPkt))
    avcodec.avcodec_free_context(ctypes.byref(decCtx))

    log(f"p2g: video written to {outputPath}")

    return dstW, dstH
