import signal
import subprocess


def launch_ffmpeg(fifo_out):
    return subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-f",
            "v4l2",
            "-framerate",
            "15",
            "-video_size",
            "640x480",
            "-i",
            "/dev/video0",
            "-f",
            "data",
            "-i",
            "/tmp/tel_fifo",
            "-map",
            "0:v:0",
            "-map",
            "1:0",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-b:v",
            "700k",
            "-c:d",
            "copy",
            "-f",
            "mpegts",
            "-muxrate",
            "965326",
            fifo_out,
        ]
    )


def launch_dvbs2_tx(fifo_in, freq_mhz, sym_rate, modcod):
    return subprocess.Popen(
        [
            "python3",
            "rf/dvbs2/tx.py",
            "--source",
            "fifo",
            "--in-file",
            fifo_in,
            "--sink",
            "hackrf",
            "--freq",
            str(freq_mhz),
            "--sym-rate",
            str(sym_rate),
            "--modcod",
            str(modcod),
            "--pilots",
        ]
    )


def stop_pipeline(*procs):
    for proc in procs:
        proc.send_signal(signal.SIGTERM)
    for proc in procs:
        proc.wait()
