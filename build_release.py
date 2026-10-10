#!/usr/bin/env python3
"""Build a public archive from an explicit list; never package local identity/state."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parent
FILES = [
    'flop_agent.py', 'flop_activity.py', 'flop_watch.py', 'flop_tasks.py',
    'test_flop_agent.py', 'test_flop_activity.py', 'test_flop_readiness.py',
    'PUBLIC_GUIDE_JA.md', 'requirements.txt', 'templates/receipt.json',
    'contributions/AGENT_UNLOCK_REPORT.md', 'contributions/PR_191_REVIEW.md',
    'contributions/pr-191-assertions.patch', 'contributions/review_191_repro.py',
    'build_release.py', 'README_PUBLIC.md', '.gitignore',
    'contributions/ATTRIBUTION.md', 'contributions/UPSTREAM_LICENSE',
    'contributions/UPSTREAM_NOTICE',
]

def main():
    content = {name: (ROOT/name).read_bytes() for name in FILES}
    content['README.md'] = (ROOT/'README_PUBLIC.md').read_bytes()
    manifest = {name: hashlib.sha256(data).hexdigest() for name,data in content.items()}
    content['MANIFEST.json'] = (json.dumps(manifest, indent=2)+'\n').encode()
    output = ROOT/'dist'
    output.mkdir(exist_ok=True)
    archive = output/'flop-preparation-20261010.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in content.items():
            z.writestr(name,data)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert set(z.namelist()) == set(content)
        for name,digest in manifest.items():
            assert hashlib.sha256(z.read(name)).hexdigest() == digest
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output/'SHA256SUMS').write_text(digest+'  '+archive.name+'\n')
    print(json.dumps({'archive':str(archive),'files':len(content),'sha256':digest},indent=2))

if __name__ == '__main__':
    main()
