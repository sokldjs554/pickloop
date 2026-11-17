"""Compose synchronized recorded camera/scene evidence into a short MP4 using actual sim time."""
import argparse,json,subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont


def make(run_paths,out,fps=10):
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    font_path='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    font=ImageFont.truetype(font_path,18);small=ImageFont.truetype(font_path,14)
    proc=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pixel_format','rgb24','-video_size','1120x620','-framerate',str(fps),'-i','-','-c:v','libx264','-preset','fast','-crf','22','-pix_fmt','yuv420p',str(out)],stdin=subprocess.PIPE)
    for run_path in run_paths:
        p=Path(run_path);r=json.loads(p.read_text());frames=r['frames']
        if not frames:raise ValueError('Video needs actual frames')
        start,end=frames[0]['sim_time'],frames[-1]['sim_time'];idx=0
        ticks=int((end-start)*fps)+1
        for i in range(ticks+fps):
            t=min(end,start+i/fps)
            while idx+1<len(frames) and frames[idx+1]['sim_time']<=t:idx+=1
            f=frames[idx];canvas=Image.new('RGB',(1120,620),(12,20,28));draw=ImageDraw.Draw(canvas)
            canvas.paste(Image.open(p.parent/f['scene']).convert('RGB'),(0,74));canvas.paste(Image.open(p.parent/f['camera']).convert('RGB'),(640,74))
            draw.text((20,14),f"PickLoop | {r['fault']} | {r['policy']} | ACTUAL MUJOCO RECORDING",font=font,fill=(117,234,211))
            draw.text((20,42),f"job {r['job_id']} / sim {t:.2f}s / {f['state']} / attempt {f['attempt']}",font=small,fill='white')
            draw.text((20,568),f"Pressure {f['pressure_kpa']:.1f} kPa   Valve {'ON' if f['valve'] else 'OFF'}   Attachment sensor {f['attached']}",font=font,fill='white')
            draw.text((20,596),f"Outcome: {r['status']} | {r['reason'] or 'visual + independent truth verified'} | source {r['provenance']['source_sha256'][:12]}",font=small,fill=(245,189,89))
            proc.stdin.write(canvas.tobytes())
    proc.stdin.close()
    if proc.wait()!=0:raise RuntimeError('ffmpeg failed')
    print(out)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('runs',nargs='+');p.add_argument('--out',default='work/pickloop-demo.mp4');a=p.parse_args();make(a.runs,a.out)
