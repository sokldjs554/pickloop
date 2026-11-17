"""Add the handoff bundle to a static deployment without a recursive source ZIP."""
import argparse,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('delivery');p.add_argument('dist');a=p.parse_args()
root=Path(__file__).resolve().parents[1];dist=Path(a.dist);target=dist/'downloads';target.mkdir(exist_ok=True)
names={'PickLoop-소스와-실행증거.zip':'pickloop-source.zip','PickLoop-실행-데모.mp4':'pickloop-demo.mp4','검증-결과.md':'summary.md','비교-지표.json':'metrics.json','원본-실행목록.csv':'trials.csv','공고-대응표.md':'job-requirements.md','PCB-경험-정리.md':'pcb-experience.md','파일-검증.json':'checksums.json'}
for source,dest in names.items():shutil.copy2(Path(a.delivery)/source,target/dest)
html=(root/'web/index.html').read_text();part=(root/'web/handoff.partial.html').read_text();(dist/'index.html').write_text(html.replace('</main>',part+'\n</main>'))
