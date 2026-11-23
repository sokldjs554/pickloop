"""Build the featured film, chapters, captions and replay entry from one recorded run."""
import argparse
import json
import re
from bisect import bisect_right
from math import ceil
from pathlib import Path
from subprocess import PIPE, Popen, run
from tempfile import TemporaryDirectory

from PIL import Image, ImageOps

WEB = Path(__file__).resolve().parents[1] / 'web'
FPS = 20
CROP = (60, 100, 636, 460)
CHAPTERS = (('failure', '첫 흡착 실패'), ('transport', '두 번째 흡착 후 운반'), ('verified', '배치 확인'))


def timing(record):
    frames = record['frames']
    start = frames[0]['sim_time']
    times = [round(frame['sim_time'] - start, 4) for frame in frames]
    if times != sorted(times) or not record['success'] or frames[-1]['state'] != 'COMPLETED':
        raise ValueError('expected a completed run with chronologically ordered recorded frames')

    def elapsed(event, state, attempt):
        match = next(e for e in record['events']
                     if (e['event'], e['state'], e['attempt']) == (event, state, attempt))
        return round(match['sim_time'] - start, 4)

    moments = {'failure': elapsed('STATE_FAILED', 'SEAL', 1), 'retry': elapsed('STATE_ENTER', 'OBSERVE', 2),
               'seal': elapsed('STATE_ENTER', 'SEAL', 2), 'lift': elapsed('STATE_ENTER', 'LIFT', 2),
               'transport': elapsed('STATE_ENTER', 'TRANSPORT', 2), 'release': elapsed('STATE_ENTER', 'RELEASE', 2),
               'verified': elapsed('PLACEMENT_VERIFIED', 'VERIFY', 2)}
    if list(moments.values()) != sorted(moments.values()) or not 0 < moments['failure'] < moments['verified'] <= times[-1]:
        raise ValueError('check the recorded failure, recovery and placement timeline')
    return times, moments


def film_frame(path, crop):
    with Image.open(path) as source:
        x1, y1, x2, y2 = crop
        if not (0 <= x1 < x2 <= source.width and 0 <= y1 < y2 <= source.height):
            raise ValueError(f'crop {crop} falls outside the {source.size} scene')
        return ImageOps.pad(source.convert('RGB').crop(crop), (576, 360),
                            method=Image.Resampling.LANCZOS, color='#10181d')


def encode(directory, frames, times, moments, media, crop):
    command = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pixel_format', 'rgb24',
               '-video_size', '576x360', '-framerate', str(FPS), '-i', 'pipe:0', '-an',
               '-c:v', 'libx264', '-crf', '17', '-preset', 'slow', '-pix_fmt', 'yuv420p',
               '-movflags', '+faststart', str(media / 'picking-recovery.mp4')]
    poster = next(i for i, f in enumerate(frames) if f['attached'] and f['state'] == 'TRANSPORT')
    # Duplicate recorded frames to preserve elapsed simulation time. Hold the last one for one second.
    ticks = ceil(times[-1] * FPS) + FPS
    with Popen(command, stdin=PIPE) as encoder:
        last = -1
        for tick in range(ticks):
            index = bisect_right(times, tick / FPS) - 1
            if last != index:
                pixels = film_frame(directory / frames[index]['scene'], crop).tobytes()
                last = index
            encoder.stdin.write(pixels)
        encoder.stdin.close()
        if encoder.wait():
            raise RuntimeError('could not encode the featured film')
    film_frame(directory / frames[poster]['scene'], crop).save(media / 'picking-recovery.jpg', quality=93)
    filters = ('fps=6,scale=480:300:flags=lanczos,split[a][b];'
               '[a]palettegen=max_colors=160:stats_mode=diff[p];[b][p]paletteuse=dither=bayer')
    run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(moments['seal']), '-i',
         str(media / 'picking-recovery.mp4'), '-t', '10', '-filter_complex', filters,
         '-loop', '0', str(media / 'picking-transport.gif')], check=True)
    return ticks / FPS


def clock(seconds):
    hours, remainder = divmod(round(seconds * 1000), 3600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole, millis = divmod(remainder, 1000)
    return f'{hours:02}:{minutes:02}:{whole:02}.{millis:03}'


def captions(moments, duration):
    cues = [(0, '로봇이 흰 줄이 있는 빨간 상자에 접근합니다.'),
            (moments['failure'], '첫 흡착에 실패해 팔을 올리고 다시 관측합니다.'),
            (moments['retry'], '다시 계산한 위치로 접근해 두 번째 흡착을 시도합니다.'),
            (moments['lift'], '흡착이 확인돼 빨간 상자를 들어 올립니다.'),
            (moments['transport'], '빨간 상자를 파란 통 위로 옮겨 내립니다.'),
            (moments['release'], '흡착을 풀고 팔을 물립니다.'),
            (moments['verified'], '영상과 시뮬레이터 상태로 배치를 확인했습니다.')]
    blocks = [f'{clock(start)} --> {clock(end)}\n{text}'
              for (start, text), (end, _) in zip(cues, cues[1:] + [(duration, '')])]
    return 'WEBVTT\n\n' + '\n\n'.join(blocks) + '\n'


def update_film(markup, moments, run_id):
    anchors = []
    for key, label in CHAPTERS:
        # First encoded frame at or after the logged event.
        elapsed = ceil(round(moments[key] * FPS, 6)) / FPS
        text = clock(elapsed)[3:-1]
        anchors.append(f'      <a data-elapsed="{elapsed:.2f}" href="media/picking-recovery.mp4#t={elapsed:.2f}">'
                       f'<time>{text}</time>{label}</a>')
    pattern = r'(<nav class="film-moments"[^>]*>)\n.*?\n    </nav>'
    updated, replacements = re.subn(pattern, r'\g<1>\n' + '\n'.join(anchors) + '\n    </nav>', markup, flags=re.S)
    if replacements != 1:
        raise ValueError('expected one film chapter list per page')
    assets = r'(media/picking-(?:recovery\.(?:mp4|jpg|ko\.vtt)|transport\.gif))(?:\?run=[a-zA-Z0-9_-]+)?'
    return re.sub(assets, lambda match: f'{match[1]}?run={run_id}', updated)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, help='web/data/runs/<id>/run.json; defaults to the current featured entry')
    parser.add_argument('--crop', nargs=4, type=int, metavar=('LEFT', 'TOP', 'RIGHT', 'BOTTOM'),
                        help='source crop in scene pixels; defaults to the current featured crop or original framing')
    args = parser.parse_args()
    metadata = WEB / 'data/featured-run.json'
    current = json.loads(metadata.read_text()) if metadata.exists() else {}
    path = args.run.resolve() if args.run else WEB / current['run_url']
    crop = args.crop or current.get('film_crop', CROP)
    record = json.loads(path.read_text())
    expected = WEB / 'data/runs' / record['run_id'] / 'run.json'
    archived = json.loads((WEB / 'data/index.json').read_text())['runs']
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', record['run_id']) or path != expected or any(row['run_id'] == record['run_id'] for row in archived):
        raise ValueError('expected a separate recorded run in web/data/runs/<run_id>/run.json')
    times, moments = timing(record)
    pages = {page: update_film(page.read_text(), moments, record['run_id']) for page in [WEB/'index.html', WEB/'evidence.html']}
    keys = ('run_id', 'job_id', 'seed', 'fault', 'policy', 'status', 'success', 'sku',
            'sim_duration_s', 'wall_duration_s', 'retries', 'condition_id')
    entry = {key: record[key] for key in keys if key in record}
    entry['run_url'] = path.relative_to(WEB).as_posix()
    entry['film_crop'] = list(crop)
    media = WEB / 'media'
    media.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=media) as tmp:
        staged = Path(tmp)
        duration = encode(path.parent, record['frames'], times, moments, staged, crop)
        (staged/'picking-recovery.ko.vtt').write_text(captions(moments, duration), encoding='utf-8')
        for artifact in staged.iterdir():
            artifact.replace(media/artifact.name)
    for page, markup in pages.items():
        page.write_text(markup, encoding='utf-8')
    metadata.write_text(json.dumps(entry, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'run': entry['run_id'], 'video_seconds': duration, 'elapsed': moments}, indent=2))


if __name__ == '__main__':
    main()
