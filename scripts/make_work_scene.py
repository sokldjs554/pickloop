"""Encode the public picking clip from a recorded run, preserving simulation elapsed time."""
import json
from bisect import bisect_right
from math import ceil
from pathlib import Path
from subprocess import Popen, PIPE, run

from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / 'web'
RUN = ROOT / 'data/runs/suction_once-3000-recovery-aaff86/run.json'
MEDIA = ROOT / 'media'
FPS = 20
CROP = (60, 100, 636, 460)


def main():
    record = json.loads(RUN.read_text())
    frames = record['frames']
    times = [round(f['sim_time'] - frames[0]['sim_time'], 4) for f in frames]
    assert times == sorted(times) and record['success'] and frames[-1]['state'] == 'COMPLETED'
    MEDIA.mkdir(exist_ok=True)
    ffmpeg = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pixel_format', 'rgb24',
              '-video_size', '576x360', '-framerate', str(FPS), '-i', 'pipe:0', '-an',
              '-c:v', 'libx264', '-crf', '17', '-preset', 'slow', '-pix_fmt', 'yuv420p',
              '-movflags', '+faststart', str(MEDIA / 'picking-recovery.mp4')]
    poster = next(i for i, f in enumerate(frames) if f['attached'] and f['state'] == 'TRANSPORT')
    with Popen(ffmpeg, stdin=PIPE) as encoder:
        last = -1
        # The final verified placement remains on screen for one extra second.
        for tick in range(ceil(times[-1] * FPS) + FPS):
            index = bisect_right(times, tick / FPS) - 1
            if index != last:
                with Image.open(RUN.parent / frames[index]['scene']) as source:
                    cropped = source.convert('RGB').crop(CROP)
                    pixels = cropped.tobytes()
                    if index == poster:
                        cropped.save(MEDIA / 'picking-recovery.jpg', quality=93)
                last = index
            encoder.stdin.write(pixels)
        encoder.stdin.close()
        if encoder.wait():
            raise RuntimeError('Could not encode picking clip')

    # GitHub renders GIFs inline. Show the second seal through release at real speed.
    seal = next(e for e in record['events'] if e['event'] == 'STATE_ENTER' and
                e['state'] == 'SEAL' and e['attempt'] == 2)
    start = seal['sim_time'] - frames[0]['sim_time']
    filters = ('fps=6,scale=480:300:flags=lanczos,split[a][b];'
               '[a]palettegen=max_colors=160:stats_mode=diff[p];[b][p]paletteuse=dither=bayer')
    run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{start:.3f}', '-i',
         str(MEDIA / 'picking-recovery.mp4'), '-t', '10', '-filter_complex', filters,
         '-loop', '0', str(MEDIA / 'picking-transport.gif')], check=True)


if __name__ == '__main__':
    main()
