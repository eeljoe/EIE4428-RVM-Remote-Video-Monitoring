"""Measure the encoder so the report quotes numbers that can be reproduced.

The report states frame rate, bit rate and quality figures.  Those figures
have to be measured rather than remembered, on the machine that will run the
demonstration, with the same code that will be submitted.  This tool does
that and prints a table.

Usage::

    python tools/benchmark.py                     # 320x240, 120 pictures
    python tools/benchmark.py --width 640 --height 480 --pictures 60
    python tools/benchmark.py --profile           # where the time goes
"""

from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rvm.analysis.quality import psnr  # noqa: E402
from rvm.codec.video import VideoEncoder  # noqa: E402
from rvm.core.colorspace import rgb_to_ycbcr, to_planes  # noqa: E402
from rvm.server.source import SyntheticSource  # noqa: E402


def build_scene(width: int, height: int, count: int) -> list[np.ndarray]:
    """A moving scene, sampled once so the benchmark is not I/O bound."""
    source = SyntheticSource(width, height, fps=25.0)
    return [source.read() for _ in range(count)]


def measure(
    width: int, height: int, pictures: int, bitrate: int, gop_size: int
) -> dict:
    frames = build_scene(width, height, pictures)
    encoder = VideoEncoder(
        width, height, target_bitrate=bitrate, frame_rate=25.0, gop_size=gop_size
    )

    sizes: list[int] = []
    qualities: list[float] = []
    encode_times: list[float] = []

    wall_start = time.perf_counter()
    for frame in frames:
        encoded = encoder.encode(frame)
        sizes.append(encoded.size)
        encode_times.append(encoded.encode_time_ms)

        luma = to_planes(rgb_to_ycbcr(frame))[0].astype(np.uint8)
        reconstruction = encoder.reconstruction_luma
        if reconstruction is not None:
            qualities.append(psnr(luma, reconstruction.astype(np.uint8)))
    wall = time.perf_counter() - wall_start

    total_bits = sum(sizes) * 8
    ordered = sorted(encode_times)
    median = ordered[len(ordered) // 2]
    return {
        "resolution": f"{width}x{height}",
        "pictures": pictures,
        "wall_seconds": wall,
        "fps": pictures / wall if wall else 0.0,
        "encode_ms_mean": sum(encode_times) / len(encode_times),
        "encode_ms_median": median,
        "encode_ms_min": ordered[0],
        "encode_ms_max": max(encode_times),
        "bitrate_kbps": total_bits / wall / 1000.0,
        "bytes_mean": sum(sizes) / len(sizes),
        "bytes_max": max(sizes),
        "psnr_mean": sum(qualities) / len(qualities) if qualities else 0.0,
        "psnr_min": min(qualities) if qualities else 0.0,
        "qp": encoder.rate_controller.current_qp,
    }


def profile(width: int, height: int, pictures: int) -> None:
    frames = build_scene(width, height, pictures)
    encoder = VideoEncoder(width, height, target_bitrate=1_200_000, frame_rate=25.0)

    runner = cProfile.Profile()
    runner.enable()
    for frame in frames:
        encoder.encode(frame)
    runner.disable()

    stream = io.StringIO()
    pstats.Stats(runner, stream=stream).sort_stats("cumulative").print_stats(22)
    print(stream.getvalue())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--pictures", type=int, default=120)
    parser.add_argument("--bitrate", type=int, default=1_200_000)
    parser.add_argument("--gop", type=int, default=30)
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()

    if args.profile:
        profile(args.width, args.height, args.pictures)
        return 0

    print(f"python {sys.version.split()[0]}   numpy {np.__version__}")
    print()

    for width, height in ((args.width, args.height),):
        result = measure(width, height, args.pictures, args.bitrate, args.gop)
        median = result["encode_ms_median"]
        print(f"=== {result['resolution']}  ({result['pictures']} pictures) ===")
        # The median is the figure to quote: a laptop that is also running a
        # browser makes the wall-clock average wander, but the cost of coding
        # one picture does not.
        print(f"  encode time     {median:.1f} ms median, "
              f"{result['encode_ms_min']:.1f} ms best, "
              f"{result['encode_ms_max']:.1f} ms worst")
        print(f"  throughput      {1000.0 / median:.1f} pictures/s "
              f"(median encode time)")
        print(f"  bit rate        {result['bitrate_kbps']:.0f} kbit/s")
        print(f"  picture size    {result['bytes_mean']:.0f} B mean, "
              f"{result['bytes_max']:.0f} B worst")
        print(f"  PSNR            {result['psnr_mean']:.2f} dB mean, "
              f"{result['psnr_min']:.2f} dB worst")
        print(f"  final QP        {result['qp']}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
