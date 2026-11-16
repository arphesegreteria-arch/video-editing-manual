from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from bridge import artifact_hygiene as hygiene
from bridge.artifact_records import artifact_store_for, load_artifact_policy
from tests.test_artifact_records import config_for, POLICY_PATH
from tests.test_artifact_hygiene import ProjectRegistry

NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)


class PortableMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.config = replace(config_for(root), audio_jobs_root=root / 'jobs',
                              audio_root=root / 'audio', transcript_root=root / 'transcripts',
                              colorist_jobs_path=root / 'colorist.json')
        self.store = artifact_store_for(self.config)
        self.policy = load_artifact_policy(POLICY_PATH)

    def record(self):
        path = self.config.render_root / 'diagnostics' / 'a.jpg'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'a')
        return self.store.register_path(path, kind='file', category='DIAGNOSTIC_CAPTURE',
                                       producer='capture_timeline_frames', managed_root_id='render_root',
                                       created_at=NOW - timedelta(days=3))

    def item(self, record):
        return hygiene._record_item(record, self.config, ProjectRegistry(), self.policy, NOW)

    def test_purged_legacy_payload_is_audit_only(self):
        record = replace(self.record(), state='PURGED', quarantine_path='C:/obsolete/payload')
        item = self.item(record)
        self.assertEqual('PURGED', item['state'])
        self.assertEqual('C:/obsolete/payload', item['audit']['quarantine_path'])

    def test_active_payload_mismatch_reports_actual_reason(self):
        item = self.item(replace(self.record(), quarantine_path='C:/obsolete/payload'))
        self.assertEqual('ERROR', item['state'])
        self.assertEqual('Quarantine payload path mismatch', item['error_detail'])

    def test_keep_and_dependency_override_eligibility(self):
        record = self.record()
        for held in (replace(record, hold_reasons=('USER_KEEP',)),
                     replace(record, dependencies=('resolve-reference:active',))):
            self.assertEqual('PROTECTED', self.item(held)['state'])
            self.assertFalse(hygiene._disposable(held))

    def test_malformed_stores_block_with_diagnostics(self):
        self.config.audio_jobs_root.mkdir()
        (self.config.audio_jobs_root / 'bad.json').write_text('{')
        blockers = hygiene.producer_activity_blockers(self.config, NOW)
        self.assertEqual('UNREADABLE_OR_MALFORMED', blockers[0]['reason'])
        self.assertIn('next_safe_action', blockers[0])
        self.config.colorist_jobs_path.write_text('{"jobs": []}')
        self.assertEqual(2, len(hygiene.producer_activity_blockers(self.config, NOW)))

    def test_unknown_applying_retains_recovery_hold(self):
        self.config.colorist_jobs_path.write_text(json.dumps({'jobs': {
            'colorist_a': {'state': 'APPLYING', 'updated_at': '2026-10-31T09:55:25Z'}}}))
        blocker = hygiene.producer_activity_blockers(self.config, NOW)[0]
        self.assertEqual('RECOVERY_REQUIRED', blocker['next_safe_action'])
        self.assertGreater(blocker['age_seconds'], 86400)

    def test_held_maintenance_is_not_success(self):
        self.record()
        self.config.audio_jobs_root.mkdir()
        (self.config.audio_jobs_root / 'active.json').write_text('{"status":"RUNNING"}')
        result = hygiene.run_maintenance(self.config, self.store, ProjectRegistry(), self.policy, NOW)
        self.assertFalse(result['ok'])
        self.assertEqual('held', self.store.maintenance_state().last_result)
        self.assertTrue(result['blockers'])

    def test_unreadable_job_is_held(self):
        self.config.audio_jobs_root.mkdir()
        path = self.config.audio_jobs_root / 'a.json'
        path.write_text('{}')
        with patch.object(Path, 'read_text', side_effect=PermissionError('denied')):
            blockers = hygiene.producer_activity_blockers(self.config, NOW)
        self.assertEqual('UNREADABLE_OR_MALFORMED', blockers[0]['reason'])

    def test_scheduler_retries_held_after_hour(self):
        from bridge.maintenance_scheduler import run_if_due
        config = replace(self.config, flags={**self.config.flags, 'CAP_ARTIFACT_MAINTENANCE': True},
                         artifact_policy_path=POLICY_PATH)
        self.store.set_maintenance_state(last_attempt_at=NOW-timedelta(hours=2), last_result='held')
        with patch('bridge.maintenance_scheduler.run_maintenance', return_value={'ok': False}) as run:
            self.assertTrue(run_if_due(config, now_utc=NOW)['ran'])
            run.assert_called_once()

    def test_wav_hash_streams_without_read_bytes(self):
        import wave
        from bridge.timeline_transcription import _wav_evidence
        path = Path(self.temp.name) / 'large.wav'
        with wave.open(str(path), 'wb') as handle:
            handle.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
            handle.writeframes(b'\0' * (48000 * 2))
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('whole file read')):
            digest, duration = _wav_evidence(path, 1.0, 25.0)
        self.assertEqual(64, len(digest))
        self.assertEqual(1.0, duration)

    def test_transcription_lifecycle_is_profile_bound_and_idempotent(self):
        from bridge import artifact_producers
        from bridge.artifact_records import sha256_file
        for workstation in ('PC_PERSONALE', 'PC_SEGRETERIA'):
            config = replace(self.config, workstation_id=workstation,
                             artifact_registry_path=Path(self.temp.name) / (workstation+'.registry.json'))
            job_id = 'timeline_tx_' + 'a'*16
            manifest = config.transcript_root / '.timeline_jobs' / workstation / (job_id+'.json')
            wav = config.audio_root / 'timeline-transcriptions' / workstation / 'owned.wav'
            output = config.transcript_root / workstation / 'owned.json'
            for path in (wav, manifest, output):
                path.parent.mkdir(parents=True, exist_ok=True)
            wav.write_bytes(b'known extraction')
            source = {'project_id': 'fdf99c83-013a-4e50-a889-36203280ed45', 'timeline_id':'timeline1'}
            payload = {'schema':'ARPHE_CARABELLESE_TRANSCRIPTION_JOB_V1', 'job_id':job_id,
                       'workstation_id':workstation, 'status':'RUNNING', 'source_path':str(wav),
                       'source_fingerprint':sha256_file(wav), 'output_path':str(output), 'timeline_source':source}
            rendering={**payload,'status':'RENDERING','source_fingerprint':None}
            manifest.write_text(json.dumps(rendering))
            artifact_producers.register_timeline_transcription(config,manifest)
            self.assertEqual(1,len(artifact_store_for(config).records()))
            manifest.write_text(json.dumps(payload))
            artifact_producers.register_timeline_transcription(config, manifest)
            store = artifact_store_for(config)
            extracted = next(r for r in store.records() if r.path == str(wav.resolve()))
            self.assertFalse(hygiene._disposable(extracted))
            payload['status'] = 'INTERRUPTED'
            manifest.write_text(json.dumps(payload))
            artifact_producers.register_timeline_transcription(config, manifest)
            self.assertFalse(hygiene._disposable(next(r for r in store.records() if r.path == str(wav.resolve()))))
            output.write_text(json.dumps({'status':'complete', 'timeline_source':source}))
            payload.update(status='COMPLETED', transcript_fingerprint=sha256_file(output))
            manifest.write_text(json.dumps(payload))
            artifact_producers.register_timeline_transcription(config, manifest)
            before = store.records()
            artifact_producers.register_timeline_transcription(config, manifest)
            self.assertEqual(before, store.records())
            extracted = next(r for r in store.records() if r.path == str(wav.resolve()))
            self.assertTrue(hygiene._disposable(extracted))
            self.assertEqual(source['project_id'], extracted.project_id)
            self.assertIsNotNone(extracted.terminal_observed_at)
            self.assertTrue(all(r.protection_class == 'PROTECTED' for r in store.records() if r != extracted))
            store.replace(replace(extracted,hold_reasons=('USER_KEEP',),dependencies=('resolve:active',)))
            artifact_producers.register_timeline_transcription(config,manifest)
            held=next(r for r in store.records() if r.artifact_id==extracted.artifact_id)
            self.assertEqual(('USER_KEEP',),held.hold_reasons)
            self.assertEqual(('resolve:active',),held.dependencies)
            # Completed readers remain usable after maintenance moves the extraction.
            wav.unlink()
            store.replace(replace(extracted,state='PURGED'))
            artifact_producers.register_timeline_transcription(config,manifest)
            self.assertEqual('PURGED',next(r for r in store.records() if r.artifact_id==extracted.artifact_id).state)

    def test_cancel_is_exposed_without_resolve_access(self):
        from bridge import server
        from bridge.tool_catalog import EXPOSED_TOOL_NAMES
        self.assertIn('cancel_colorist_plan', EXPOSED_TOOL_NAMES)
        self.assertTrue(callable(server.cancel_colorist_plan))

    def test_guarded_cancel_is_idempotent_and_rejects_stale_or_active_jobs(self):
        from bridge import server
        from bridge.colorist_jobs import ColoristJobStore,new_colorist_job,approve_colorist_job,record_colorist_apply_started
        store=ColoristJobStore(self.config.colorist_jobs_path,self.config.workstation_id)
        def create():
            return store.create(new_colorist_job(workstation_id=self.config.workstation_id,project_name='ARPHE_TEST',
                timeline_name='ARPHE_TEST',timeline_identity='timeline',clip_ids=('clip',),reference_clip_id=None,
                adjustments={},preset_name='manual',drx_preset_name=None,drx_asset_identity=None,
                before_versions={'clip':{'versionName':'original','versionType':0}},cdl={}))
        job=create()
        with patch.object(server,'load_config',return_value=self.config), \
             patch.object(server,'_colorist_store',return_value=store), \
             patch.object(server,'_runtime',side_effect=AssertionError('Resolve must not be accessed')):
            self.assertFalse(server.cancel_colorist_plan(job.colorist_job_id,job.plan_fingerprint,99,'COLORIST','obsolete')['ok'])
            first=server.cancel_colorist_plan(job.colorist_job_id,job.plan_fingerprint,job.revision,'COLORIST','obsolete')
            second=server.cancel_colorist_plan(job.colorist_job_id,job.plan_fingerprint,job.revision,'COLORIST','obsolete')
            self.assertTrue(first['ok']);self.assertEqual(first,second)
            self.assertFalse(server.cancel_colorist_plan(job.colorist_job_id,'0'*64,job.revision,'COLORIST','obsolete')['ok'])
            active=create()
            active=store.save(approve_colorist_job(active,active.plan_fingerprint,'COLORIST'),active.revision)
            active=store.save(record_colorist_apply_started(active),active.revision)
            self.assertFalse(server.cancel_colorist_plan(active.colorist_job_id,active.plan_fingerprint,active.revision,'COLORIST','obsolete')['ok'])
            self.assertEqual('APPLYING',store.get(active.colorist_job_id,self.config.workstation_id).state)

    def test_unexpected_apply_exception_records_manual_recovery_evidence(self):
        from bridge.colorist_jobs import (ColoristJobStore, new_colorist_job, approve_colorist_job,
            record_colorist_apply_started, record_colorist_exception)
        store = ColoristJobStore(self.config.colorist_jobs_path, self.config.workstation_id)
        job = new_colorist_job(workstation_id=self.config.workstation_id,project_name='ARPHE_TEST',
            timeline_name='ARPHE_TEST',timeline_identity='timeline',clip_ids=('clip',),reference_clip_id=None,
            adjustments={},preset_name='manual',drx_preset_name=None,drx_asset_identity=None,
            before_versions={'clip':{'versionName':'original','versionType':0}},cdl={})
        job=store.create(job)
        job=store.save(approve_colorist_job(job,job.plan_fingerprint,'COLORIST'),job.revision)
        job=store.save(record_colorist_apply_started(job),job.revision)
        result=record_colorist_exception(store,job,RuntimeError('readback failed'))
        self.assertEqual('FAILED_MANUAL',result.state)
        self.assertEqual('RuntimeError',result.failure_evidence['error_type'])
        self.assertFalse(result.failure_evidence['recoverable'])
        self.assertEqual('RECOVERY_REQUIRED',hygiene.producer_activity_blockers(self.config,NOW)[0]['next_safe_action'])

    def test_legacy_extraction_is_diagnostic_only(self):
        path=self.config.audio_root/'timeline-transcriptions'/self.config.workstation_id/'legacy.wav'
        path.parent.mkdir(parents=True);path.write_bytes(b'original legacy')
        findings=hygiene._unclassified(self.config,set())
        self.assertTrue(any(i['display_path'].endswith('legacy.wav') for i in findings))
        self.assertTrue(all(i['state']=='UNCLASSIFIED' for i in findings))
        self.assertEqual([],self.store.records())

    def test_worker_registers_completion_automatically_and_preserves_originals(self):
        from bridge.transcription_worker import run_job, JOB_SCHEMA
        from bridge.artifact_records import sha256_file
        config=replace(self.config,artifact_policy_path=POLICY_PATH)
        job_id='timeline_tx_'+'b'*16
        wav=config.audio_root/'timeline-transcriptions'/config.workstation_id/'worker.wav'
        output=config.transcript_root/config.workstation_id/'worker.json'
        manifest=config.transcript_root/'.timeline_jobs'/config.workstation_id/(job_id+'.json')
        for path in (wav,output,manifest):path.parent.mkdir(parents=True,exist_ok=True)
        original=config.audio_root/'original.mp4';original.write_bytes(b'original source')
        wav.write_bytes(b'extracted worker audio')
        source={'project_id':'fdf99c83-013a-4e50-a889-36203280ed45','timeline_id':'timeline'}
        payload={'schema':JOB_SCHEMA,'job_id':job_id,'workstation_id':config.workstation_id,'status':'QUEUED',
            'source_path':str(wav),'source_name':wav.name,'source_fingerprint':sha256_file(wav),
            'output_path':str(output),'media_root':str(config.audio_root),'transcript_root':str(config.transcript_root),
            'model':'small','language':'it','timeline_source':source,'lifecycle_config_path':str(config.path)}
        manifest.write_text(json.dumps(payload))
        def transcribe(*args,**kwargs):output.write_text('{"status":"complete"}')
        with patch('bridge.transcription_worker.transcribe_checkpointed',side_effect=transcribe), \
             patch('bridge.config.load_config',return_value=config):
            run_job(manifest)
        self.assertEqual('COMPLETED',json.loads(manifest.read_text())['status'])
        self.assertEqual(3,len(artifact_store_for(config).records()))
        self.assertEqual(b'original source',original.read_bytes())

    def test_held_maintenance_does_not_reconcile_pending_filesystem_work(self):
        record=self.record()
        self.store.set_pending_operation({'type':'UNKNOWN','artifact_id':record.artifact_id,'source':record.path,'destination':''})
        self.config.audio_jobs_root.mkdir()
        (self.config.audio_jobs_root/'active.json').write_text('{"status":"RUNNING"}')
        result=hygiene.run_maintenance(self.config,self.store,ProjectRegistry(),self.policy,NOW)
        self.assertEqual('held',result['status'])
        self.assertIsNotNone(self.store.pending_operation())
