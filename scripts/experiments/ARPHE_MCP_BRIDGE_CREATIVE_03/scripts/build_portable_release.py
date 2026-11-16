"""Build a reproducible source-only package from the audited local checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

SOURCE=Path(__file__).resolve().parents[1]
REPO=SOURCE.parents[2]
sys.path.insert(0,str(SOURCE))
from bridge.release_identity import build_release, payload_files, sha256_path


def git(*args):
    return subprocess.check_output(['git','-c','safe.directory='+REPO.as_posix(),*args],cwd=REPO)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    provenance=json.loads((REPO/'docs'/'bridge-maintenance-installed-baseline.json').read_text(encoding='utf-8-sig'))
    observed={row['path']:row for row in provenance}
    baseline={}
    for name in payload_files(SOURCE):
        row=observed.get(name)
        if row:
            baseline[name]=[row['installed_sha256'],row['repository_sha256']]
        else:
            try:
                before=git('show','31c7a79:'+SOURCE.relative_to(REPO).as_posix()+'/'+name)
            except subprocess.CalledProcessError:
                before=None
            baseline[name]=[None]
            if before is not None:
                # Git stores LF; checkout files may be materialized with CRLF.
                baseline[name]+=[hashlib.sha256(before).hexdigest(),
                    hashlib.sha256(before.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')).hexdigest()]
    revision=git('rev-parse','HEAD').decode().strip()
    manifest=build_release(SOURCE,args.output,baseline,revision)
    archive=args.output.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as output:
        for path in sorted(args.output.rglob('*')):
            if path.is_file():
                entry=zipfile.ZipInfo(path.relative_to(args.output).as_posix(),date_time=(1980,1,1,0,0,0))
                entry.compress_type=zipfile.ZIP_DEFLATED
                entry.external_attr=0o100644<<16
                output.writestr(entry,path.read_bytes())
    print(json.dumps({'package':str(args.output),'archive':str(archive),'archive_sha256':sha256_path(archive),
        'manifest_sha256':sha256_path(args.output/'release-manifest.json'),
        'release_id':manifest['release_id'],'source_revision':revision,'file_count':len(manifest['files'])},indent=2))


if __name__=='__main__':main()
