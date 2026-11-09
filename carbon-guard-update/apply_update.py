from pathlib import Path
import shutil,datetime
source=Path(__file__).resolve().parent/'files'
root=Path.cwd()
if not (root/'run.py').is_file() or not (root/'backend'/'main.py').is_file():
 raise SystemExit('請在 carbon-guard 根目錄開啟終端機，執行 python 路徑/apply_update.py')
backup=root/('update-backup-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
for item in source.rglob('*'):
 if item.is_file():
  relative=item.relative_to(source);target=root/relative
  if target.exists():
   saved=backup/relative;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,saved)
  target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(item,target)
print('更新完成。舊程式備份：',backup)
print('不修改 .env、data、.venv、ic-2023.json 或原始資料。請用原虛擬環境 python run.py 重啟。')
