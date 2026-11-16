from pathlib import Path
import json
import tempfile
import unittest
import subprocess
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def policy_support(source):
    """Real packaged policy validator dependencies, without runtime/MCP services."""
    for name in ('__init__.py','config.py','artifact_records.py','release_identity.py'):
        shutil.copyfile(ROOT/'bridge'/name,source/'bridge'/name)
    shutil.copyfile(ROOT/'artifact_retention.json',source/'artifact_retention.json')


class ReleaseTests(unittest.TestCase):
    def test_partial_install_requires_verified_rollback(self):
        from bridge.release_identity import build_release, sha256_path
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';target=root/'target'
            for folder in (source/'bridge',target/'bridge'): folder.mkdir(parents=True)
            policy_support(source)
            baseline={}
            for name in ('a.py','b.py'):
                (source/'bridge'/name).write_text('new')
                (target/'bridge'/name).write_text('old')
                baseline['bridge/'+name]=[sha256_path(target/'bridge'/name)]
            build_release(source,root/'package',baseline,'revision')
            config=root/'creative.json';config.write_text('{"workstation_id":"PC_PERSONALE"}')
            profile=root/'profile.json';profile.write_text(json.dumps({'workstation_id':'PC_PERSONALE','python_path':sys.executable,
                'creative_destination':str(target),'creative_config_path':str(config)}))
            def run(mode):
                return subprocess.run(['pwsh','-NoProfile','-ExecutionPolicy','Bypass','-File',
                    str(ROOT/'scripts'/'install_package.ps1'),'-PackagePath',str(root/'package'),
                    '-ProfilePath',str(profile),'-Mode',mode,'-BackupPath',str(root/'backup')],
                    capture_output=True,text=True)
            with (target/'bridge'/'b.py').open('rb'):
                failed=run('Install')
            self.assertNotEqual(0,failed.returncode)
            self.assertTrue((target/'.arphe-install-pending.json').exists())
            self.assertNotEqual(0,run('DryRun').returncode)
            rolled=run('Rollback');self.assertEqual(0,rolled.returncode,rolled.stderr)
            self.assertEqual('old',(target/'bridge'/'a.py').read_text())
            self.assertEqual('old',(target/'bridge'/'b.py').read_text())
            self.assertFalse((target/'.arphe-install-pending.json').exists())

    def test_identity_detects_actual_payload_and_effective_policy_changes(self):
        from bridge.release_identity import release_identity
        from tests.test_artifact_records import config_for
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'bridge').mkdir()
            (root/'bridge'/'tool_catalog.py').write_text('TOOLS=()')
            (root/'bridge'/'server.py').write_text('hello')
            policy = root/'artifact_retention.json'
            policy.write_text('{"quarantine_seconds":1296000}')
            config = replace(config_for(root), artifact_policy_path=policy)
            first = release_identity(config, root)
            (root/'bridge'/'server.py').write_text('changed')
            second = release_identity(config, root)
            self.assertNotEqual(first['source_fingerprint'], second['source_fingerprint'])
            self.assertEqual(first['catalogue_fingerprint'], second['catalogue_fingerprint'])
            third = release_identity(replace(config, purge_enabled=True), root)
            self.assertNotEqual(second['effective_policy_fingerprint'], third['effective_policy_fingerprint'])

    def test_build_is_deterministic_and_excludes_state(self):
        from bridge.release_identity import build_release
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'source'
            (source/'bridge').mkdir(parents=True)
            (source/'bridge'/'x.py').write_text('pass')
            (source/'creative_config.json').write_text('SECRET')
            (source/'state.json').write_text('STATE')
            a = build_release(source, root/'a', {}, 'test-revision')
            b = build_release(source, root/'b', {}, 'test-revision')
            self.assertEqual(a,b)
            self.assertNotIn('creative_config.json',a['files'])
            self.assertNotIn('state.json',a['files'])

    def test_installer_drift_tamper_idempotence_and_rollback_both_profiles(self):
        from bridge.release_identity import build_release, sha256_path
        for workstation in ('PC_PERSONALE','PC_SEGRETERIA'):
            with self.subTest(workstation=workstation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root/'source'
                target = root/'target'
                for folder in (source/'bridge', target/'bridge'):
                    folder.mkdir(parents=True)
                policy_support(source)
                (source/'bridge'/'x.py').write_text('new')
                (target/'bridge'/'x.py').write_text('old')
                baseline = {'bridge/x.py': [sha256_path(target/'bridge'/'x.py')]}
                build_release(source,root/'package',baseline,'revision')
                config = root/'creative.json';config.write_text(json.dumps({'workstation_id':workstation,'flags':{'CAP_RENDER':True}}))
                profile = root/'profile.json';profile.write_text(json.dumps({'workstation_id':workstation,'python_path':sys.executable,'creative_destination':str(target),'creative_config_path':str(config)}))
                saved_config = config.read_bytes()

                def run(mode='DryRun', backup=None):
                    args=['pwsh','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts'/'install_package.ps1'),
                          '-PackagePath',str(root/'package'),'-ProfilePath',str(profile),'-Mode',mode]
                    if backup: args += ['-BackupPath',str(backup)]
                    return subprocess.run(args,capture_output=True,text=True)

                preflight=run();self.assertEqual(0,preflight.returncode,preflight.stderr)
                (target/'bridge'/'x.py').write_text('drift')
                self.assertNotEqual(0,run('Install',root/'backup').returncode)
                (target/'bridge'/'x.py').write_text('old')
                payload=root/'package'/'payload'/'bridge'/'x.py'
                payload.write_text('tampered')
                self.assertNotEqual(0,run().returncode)
                payload.write_text('new')
                first=run('Install',root/'backup');self.assertEqual(0,first.returncode,first.stderr)
                self.assertEqual('new',(target/'bridge'/'x.py').read_text())
                self.assertEqual(0,run('Install',root/'backup2').returncode)
                rolled=run('Rollback',root/'backup');self.assertEqual(0,rolled.returncode,rolled.stderr)
                self.assertEqual('old',(target/'bridge'/'x.py').read_text())
                self.assertEqual(saved_config,config.read_bytes())

    def test_interrupted_owned_staging_is_audited_and_repeated_rollback_recovers(self):
        from bridge.release_identity import build_release,sha256_path
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';target=root/'target'
            for folder in (source/'bridge',target/'bridge'):folder.mkdir(parents=True)
            policy_support(source)
            (source/'bridge'/'x.py').write_text('new')
            original=target/'bridge'/'x.py';original.write_text('old')
            build_release(source,root/'package',{'bridge/x.py':[sha256_path(original)]},'revision')
            config=root/'creative.json';config.write_text('{"workstation_id":"PC_PERSONALE"}')
            saved=config.read_bytes()
            profile=root/'profile.json';profile.write_text(json.dumps({'workstation_id':'PC_PERSONALE','python_path':sys.executable,
                'creative_destination':str(target),'creative_config_path':str(config)}))
            def run(mode,backup='backup'):
                return subprocess.run(['pwsh','-NoProfile','-ExecutionPolicy','Bypass','-File',
                    str(ROOT/'scripts'/'install_package.ps1'),'-PackagePath',str(root/'package'),
                    '-ProfilePath',str(profile),'-Mode',mode,'-BackupPath',str(root/backup)],capture_output=True,text=True)
            # Fail after copy but before rename, then reproduce interruption during copy.
            with original.open('rb'):
                self.assertNotEqual(0,run('Install').returncode)
            staged=original.with_name(original.name+'.arphe-install.tmp')
            staged.write_bytes(b'ne')
            receipt=json.loads((root/'backup'/'receipt.json').read_text(encoding='utf-8-sig'))
            entry=next(e for e in receipt['files'] if e['path']=='bridge/x.py')
            self.assertTrue(entry.get('staging_owned'))
            rolled=run('Rollback');self.assertEqual(0,rolled.returncode,rolled.stderr)
            self.assertEqual(b'ne',(root/'backup'/'staging-audit'/'bridge'/'x.py.arphe-install.tmp').read_bytes())
            self.assertFalse(staged.exists())
            # A crash after the final receipt write but before marker removal is retryable.
            (target/'.arphe-install-pending.json').write_text(str(root/'backup'))
            self.assertEqual(0,run('Rollback').returncode)
            self.assertFalse((target/'.arphe-install-pending.json').exists())
            self.assertEqual('old',original.read_text())
            self.assertEqual(saved,config.read_bytes())
            installed=run('Install','backup2');self.assertEqual(0,installed.returncode,installed.stderr)
            self.assertEqual(0,run('Rollback','backup2').returncode)
            self.assertEqual('old',original.read_text())

    def test_unowned_staging_is_not_overwritten_or_removed(self):
        from bridge.release_identity import build_release,sha256_path
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';target=root/'target'
            for folder in (source/'bridge',target/'bridge'):folder.mkdir(parents=True)
            policy_support(source)
            (source/'bridge'/'x.py').write_text('new')
            original=target/'bridge'/'x.py';original.write_text('old')
            build_release(source,root/'package',{'bridge/x.py':[sha256_path(original)]},'revision')
            config=root/'creative.json';config.write_text('{"workstation_id":"PC_PERSONALE"}')
            profile=root/'profile.json';profile.write_text(json.dumps({'workstation_id':'PC_PERSONALE','python_path':sys.executable,
                'creative_destination':str(target),'creative_config_path':str(config)}))
            staged=original.with_name(original.name+'.arphe-install.tmp');staged.write_bytes(b'unowned')
            result=subprocess.run(['pwsh','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts'/'install_package.ps1'),
                '-PackagePath',str(root/'package'),'-ProfilePath',str(profile),'-Mode','Install','-BackupPath',str(root/'backup')],capture_output=True,text=True)
            self.assertNotEqual(0,result.returncode)
            self.assertEqual(b'unowned',staged.read_bytes())
            self.assertEqual('old',original.read_text())
            self.assertFalse((target/'.arphe-install-pending.json').exists())
            self.assertFalse((root/'backup').exists())

    def test_effective_policy_preflight_is_compatible_or_fails_before_writes_both_profiles(self):
        from bridge.release_identity import build_release,sha256_path
        for workstation in ('PC_PERSONALE','PC_SEGRETERIA'):
            for case in ('packaged','external_compatible','external_incompatible'):
                with self.subTest(workstation=workstation,case=case),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);source=root/'source';target=root/'target'
                    for folder in (source/'bridge',target/'bridge'):folder.mkdir(parents=True)
                    policy_support(source)
                    (source/'bridge'/'x.py').write_text('new');(target/'bridge'/'x.py').write_text('old')
                    build_release(source,root/'package',{'bridge/x.py':[sha256_path(target/'bridge'/'x.py')]},'revision')
                    raw={'workstation_id':workstation}
                    external=root/'external-policy.json'
                    if case!='packaged':
                        policy=json.loads((ROOT/'artifact_retention.json').read_text())
                        if case=='external_incompatible':policy['rules'].pop('TRANSCRIPTION_EXTRACTION')
                        external.write_text(json.dumps(policy));raw['artifact_policy_path']=str(external)
                    config=root/'creative.json';config.write_text(json.dumps(raw))
                    saved_config=config.read_bytes();saved_policy=external.read_bytes() if external.exists() else None
                    profile=root/'profile.json';profile.write_text(json.dumps({'workstation_id':workstation,'python_path':sys.executable,
                        'creative_destination':str(target),'creative_config_path':str(config)}))
                    def run(mode):
                        return subprocess.run(['pwsh','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts'/'install_package.ps1'),
                            '-PackagePath',str(root/'package'),'-ProfilePath',str(profile),'-Mode',mode,'-BackupPath',str(root/'backup')],capture_output=True,text=True)
                    dry=run('DryRun')
                    if case=='external_incompatible':
                        self.assertNotEqual(0,dry.returncode)
                        self.assertIn('Effective artifact policy incompatible',dry.stderr)
                        self.assertNotEqual(0,run('Install').returncode)
                        self.assertFalse((root/'backup').exists())
                        self.assertFalse((target/'.arphe-install-pending.json').exists())
                        self.assertEqual('old',(target/'bridge'/'x.py').read_text())
                    else:
                        self.assertEqual(0,dry.returncode,dry.stderr)
                        installed=run('Install');self.assertEqual(0,installed.returncode,installed.stderr)
                        rolled=run('Rollback');self.assertEqual(0,rolled.returncode,rolled.stderr)
                    self.assertEqual(saved_config,config.read_bytes())
                    if saved_policy is not None:self.assertEqual(saved_policy,external.read_bytes())
