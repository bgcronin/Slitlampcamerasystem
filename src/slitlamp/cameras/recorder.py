"""Bounded, threaded recording for simulated and Canon preview streams.

Uses wall-clock timing so slower preview delivery does not speed up playback.
The source and actual frame dimensions are always labelled in metadata.
"""

import queue
import threading
import time


class StreamRecorder:
    def __init__(self, path, first_frame, fps=15):
        self.path = path
        self.size = first_frame.size
        self.fps = fps
        self.error = None
        self.frames = queue.Queue(maxsize=2)
        self.first = first_frame.copy()
        self.stop_event = threading.Event()
        self.started_at = time.monotonic()
        self.stopped_at = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def offer(self, image):
        try:
            self.frames.put_nowait(image.copy())
        except queue.Full:
            pass

    def _run(self):
        import imageio_ffmpeg

        writer = None
        try:
            writer = imageio_ffmpeg.write_frames(
                str(self.path),
                self.size,
                fps=self.fps,
                codec="libx264",
                pix_fmt_in="rgb24",
                pix_fmt_out="yuv420p",
                macro_block_size=2,
                output_params=["-movflags", "+faststart"],
                ffmpeg_log_level="error",
            )
            writer.send(None)
            current = self.first
            deadline = self.started_at
            written = 0
            while not self.stop_event.is_set() or written < max(
                1, round(((self.stopped_at or time.monotonic()) - self.started_at) * self.fps)
            ):
                try:
                    while True:
                        current = self.frames.get_nowait()
                except queue.Empty:
                    pass
                writer.send(current.resize(self.size).convert("RGB").tobytes())
                written += 1
                deadline += 1 / self.fps
                self.stop_event.wait(max(0, deadline - time.monotonic()))
        except Exception as exc:
            self.error = exc
        finally:
            if writer:
                try:
                    writer.close()
                except Exception as exc:
                    self.error = exc

    def finish(self):
        self.stopped_at = time.monotonic()
        self.stop_event.set()
        self.thread.join(timeout=30)
        if self.thread.is_alive():
            raise TimeoutError("Video encoder has not finished; recording retained in staging.")
        if self.error:
            raise RuntimeError(f"Video encoder failed: {self.error}")
        return self.path
