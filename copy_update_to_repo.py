"""Copy this extracted update into a local clone, preserving secrets and backing up changed sources."""
import hashlib
import shutil
from datetime import datetime
from pathlib import Path

EXCLUDE = {'.git','private','.venv','__pycache__','.mirror-rfid'}
BASE = Path(__file__).resolve().parent

def eligible(relative):
    return not any(part in EXCLUDE for part in relative.parts) and relative.name != 'config.json' and not relative.name.startswith('config.json.') and relative.suffix not in ('.pyc','.log')

def apply_update(source, destination, backup):
    source, destination, backup = map(lambda p: Path(p).resolve(), (source,destination,backup))
    if source == destination or not (destination/'.git').exists():
        raise ValueError('Select a different existing cloned Git repository folder.')
    copied=0
    for path in sorted(source.rglob('*')):
        relative=path.relative_to(source)
        if not path.is_file() or path.is_symlink() or not eligible(relative):
            continue
        target=destination/relative
        if target.exists():
            if target.is_symlink() or not target.is_file():
                raise ValueError('Unexpected file type: '+str(target))
            if hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256(target.read_bytes()).digest():
                continue
            saved=backup/relative; saved.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(target,saved)
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,target); copied+=1
    return copied

def main():
    default=Path.home()/'Downloads'/'UTDHACKATHON-git'
    print('Copies this update into your clone. Keeps config.json, private, .git and .venv.')
    entered=input(f'Repository folder [Enter for {default}]: ').strip().strip('"')
    destination=Path(entered) if entered else default
    backup=destination.parent/('mirror-source-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    count=apply_update(BASE,destination,backup)
    print(f'Copied {count} changed/new source files to {destination}')
    print('Previous changed files backed up at:',backup)
    print('Stop the old app.py, start the updated copy, and review git diff before committing.')

if __name__=='__main__':
    try: main()
    except (OSError,ValueError) as error: raise SystemExit(str(error))
