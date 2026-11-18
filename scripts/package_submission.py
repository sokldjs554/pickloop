"""Package source and raw evidence; full replay images remain on the public Site."""
import hashlib,json,re,shutil,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT.parent/'delivery';DEST.mkdir(exist_ok=True)
revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
(ROOT/'SOURCE_REVISION.txt').write_text(revision+'\n')
archive=DEST/'PickLoop-소스와-실행증거.zip'
roots=['src','tests','cpp','ros2','models','assets','configs','scripts','docs','verification','.github','web','runs/final','runs/ablation-heldout','runs/mobile','runs/sku-validation','runs/live']
files=[]
for name in roots:
    files.extend(p for p in (ROOT/name).rglob('*') if p.is_file())
files.extend(ROOT/name for name in ['README.md','LICENSE','Dockerfile','pyproject.toml','requirements-lock.txt','SOURCE_REVISION.txt','.gitignore'] if (ROOT/name).exists())
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(set(files)):
        rel=p.relative_to(ROOT)
        if any(part in ('__pycache__','.pytest_cache','.venv','frames') for part in rel.parts) or p.suffix=='.pyc' or p.name.endswith(('-wal','-shm')):continue
        z.write(p,'pickloop/'+str(rel))
    z.writestr('pickloop/REPLAY_MEDIA.md', '# 재생 이미지와 실행 원문\n\n이 ZIP은 소스·학습 모델·모든 최종 평가 원문·대표 재생 이벤트/텔레메트리를 포함합니다. 다운로드 용량을 줄이기 위해 frames/ JPEG는 포함하지 않습니다. 전체 28개 재생 이미지와 동시 비교는 https://pickloop-robot-ops.ykh13571.chatgpt.site 에서 확인할 수 있습니다.\n\n오프라인 재생이 필요하면 docs/ablation-protocol.md의 record_ablation.py → export_ablation.py 명령으로 이미지를 생성하세요. 웹 소스만 로컬에서 열면 기존 프레임은 누락 상태로 표시됩니다. `pickloop serve`의 로컬 실시간 실행은 새 이미지를 직접 기록합니다. MP4는 Site에서 별도로 다운로드할 수 있습니다.\n')
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
for source,dest in [('docs/submission-summary.md','검증-결과.md'),('runs/ablation-heldout/metrics.json','비교-지표.json'),('runs/ablation-heldout/trials.csv','원본-실행목록.csv'),('docs/pcb-experience.md','PCB-경험-정리.md')]:shutil.copy2(ROOT/source,DEST/dest)
# Standalone requirement matrix points into the ZIP rather than broken web-relative paths.
matrix=(ROOT/'docs/job-requirements-matrix.md').read_text()
def zip_path(match):
    label,path=match.groups()
    if path.startswith(('http://','https://','#')):return match.group(0)
    from posixpath import normpath
    return f'{label} (`pickloop/{normpath("docs/"+path)}` in ZIP)'
matrix=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',zip_path,matrix)
(DEST/'공고-대응표.md').write_text(matrix)
shutil.copy2(ROOT/'work/pickloop-demo.mp4',DEST/'PickLoop-실행-데모.mp4')
checks={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(DEST.iterdir()) if p.is_file() and p.name!='파일-검증.json'}
(DEST/'파일-검증.json').write_text(json.dumps({'source_revision':revision,'files':checks},ensure_ascii=False,indent=2))
print(json.dumps({'archive_bytes':archive.stat().st_size,'source_files':len(files),'destination':str(DEST)}))
