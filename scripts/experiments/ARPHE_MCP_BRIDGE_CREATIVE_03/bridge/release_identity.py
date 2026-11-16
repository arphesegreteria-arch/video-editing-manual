"""Deterministic, payload-derived release identity and source-only packaging."""
from pathlib import Path
import hashlib
import json
import shutil

CONTRACTS = frozenset({
    'artifact_retention.json', 'branded_longform_contract.json', 'branded_longform_kits.json',
    'carabellese_cleanup_contract.json', 'carabellese_preferences.json', 'colorist_presets.json',
    'editorial_preferences.json', 'editorial_selection_contract.json', 'editorial_workflows.json',
    'render_profiles.json', 'review_readability_contract.json', 'vertical_social_contract.json',
})


def sha256_path(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def payload_files(root):
    root = Path(root)
    paths = list((root/'bridge').glob('*.py'))
    paths += [root/name for name in CONTRACTS]
    paths += [root/'ARPHE_MCP_BRIDGE_CREATIVE_03.py',root/'install_on_segreteria.ps1',
              root/'scripts'/'install_package.ps1']
    return {p.relative_to(root).as_posix(): sha256_path(p) for p in sorted(paths) if p.is_file()}


def build_release(source, destination, baselines, source_revision):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise ValueError('Release destination must be new')
    files = payload_files(source)
    manifest = {'schema_version':1, 'source_revision':source_revision, 'files':files,
                'accepted_baselines':{key:list(dict.fromkeys(baselines.get(key, [None]))) for key in files}}
    manifest['release_id'] = fingerprint(manifest)
    destination.mkdir(parents=True)
    for name in files:
        target = destination/'payload'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/name,target)
        if sha256_path(target) != files[name]:
            raise ValueError('Payload changed during build')
    (destination/'release-manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    (destination/'release-manifest.sha256').write_text(sha256_path(destination/'release-manifest.json')+'\n',encoding='ascii')
    return manifest


def release_identity(config, root=None):
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    actual = payload_files(root)
    manifest_path = root/'release-manifest.json'
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig')) if manifest_path.exists() else None
    except (OSError, ValueError):
        manifest = None
    valid = False
    if isinstance(manifest,dict):
        expected_id = manifest.get('release_id')
        content = {k:v for k,v in manifest.items() if k != 'release_id'}
        valid = fingerprint(content) == expected_id and manifest.get('files') == actual
    try:
        policy = json.loads(config.artifact_policy_path.read_text(encoding='utf-8-sig'))
        policy_error = None
    except (OSError, ValueError, AttributeError) as exc:
        policy = None
        policy_error = type(exc).__name__
    effective = {'policy':policy, 'purge_enabled':getattr(config,'purge_enabled',False),
                 'maintenance_enabled':bool(config.flags.get('CAP_ARTIFACT_MAINTENANCE',False))}
    return {'release_id':manifest.get('release_id') if manifest and valid else None,
            'manifest_valid':valid, 'source_revision':manifest.get('source_revision') if manifest and valid else None,
            'source_fingerprint':fingerprint(actual),
            'catalogue_fingerprint':actual.get('bridge/tool_catalog.py'),
            'effective_policy_fingerprint':fingerprint(effective) if policy is not None else None,
            'policy_error':policy_error}
