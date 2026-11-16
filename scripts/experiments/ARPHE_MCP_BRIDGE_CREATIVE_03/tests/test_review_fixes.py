from dataclasses import asdict, replace
from pathlib import Path
import json
import tempfile
import unittest

from bridge.artifact_hygiene import producer_activity_blockers
from bridge.colorist_jobs import ColoristJobStore, new_colorist_job, approve_colorist_job, cancel_colorist_job
from tests.test_artifact_records import config_for


class ProducerTerminalValidationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.config=replace(config_for(self.root),audio_root=self.root/'audio',audio_jobs_root=self.root/'jobs',
            transcript_root=self.root/'transcripts',colorist_jobs_path=self.root/'colorist.json')
        self.config.audio_jobs_root.mkdir()

    def audio(self):
        return {'schema':'ARPHE_AUDIO_JOB_V2','job_id':'audio_'+'a'*16,'workstation_id':'PC_PERSONALE',
            'status':'COMPLETED','preset':'VOICE_CLEAN','source_fingerprint':'a'*64,
            'output_path':str(self.config.audio_root/'owned.wav'),'output_sha256':'b'*64,
            'source_duration_seconds':10.0,'output_duration_seconds':10.0,'sync_delta_seconds':0.0,
            'sample_rate':48000,'channels':2,'progress_percent':100}

    def test_invalid_terminal_audio_schema_owner_and_evidence_are_recovery_blockers(self):
        path=self.config.audio_jobs_root/('audio_'+'a'*16+'.json')
        for payload in ({'status':'COMPLETED'}, {**self.audio(),'schema':'UNKNOWN'},
                        {**self.audio(),'workstation_id':'PC_SEGRETERIA'},
                        {**self.audio(),'output_sha256':None},
                        {**self.audio(),'sync_delta_seconds':1.0}):
            with self.subTest(payload=payload):
                path.write_text(json.dumps(payload))
                blockers=producer_activity_blockers(self.config)
                self.assertEqual(1,len(blockers))
                self.assertEqual('RECOVERY_REQUIRED',blockers[0]['next_safe_action'])
                self.assertEqual('UNREADABLE_OR_MALFORMED',blockers[0]['reason'])

    def test_valid_audio_terminal_and_evidenced_failure_clear_only_their_own_blocker(self):
        path=self.config.audio_jobs_root/('audio_'+'a'*16+'.json')
        for payload in (self.audio(),{**self.audio(),'status':'FAILED','error':'decode failed','error_type':'RuntimeError'}):
            path.write_text(json.dumps(payload))
            self.assertEqual([],producer_activity_blockers(self.config))
        payload=self.audio();payload.pop('workstation_id')
        path.write_text(json.dumps(payload))
        self.assertEqual('RECOVERY_REQUIRED',producer_activity_blockers(self.config)[0]['next_safe_action'])

    def test_invalid_colorist_terminal_store_record_and_ownership_are_held(self):
        for payload in ({'jobs':{'partial':{'state':'APPLIED'}}},
                        {'schema':'ARPHE_COLORIST_JOBS_V1','workstation_id':'PC_PERSONALE','jobs':{'partial':{'state':'APPLIED'}}},
                        {'schema':'ARPHE_COLORIST_JOBS_V1','workstation_id':'PC_SEGRETERIA','jobs':{}},
                        {'schema':'UNKNOWN','workstation_id':'PC_PERSONALE','jobs':{}}):
            self.config.colorist_jobs_path.write_text(json.dumps(payload))
            blockers=producer_activity_blockers(self.config)
            self.assertTrue(blockers)
            self.assertTrue(all(b['next_safe_action']=='RECOVERY_REQUIRED' for b in blockers))

    def test_supported_legacy_colorist_and_transcription_terminal_evidence(self):
        store=ColoristJobStore(self.config.colorist_jobs_path,self.config.workstation_id)
        job=store.create(new_colorist_job(workstation_id=self.config.workstation_id,project_name='ARPHE_TEST',
            timeline_name='ARPHE_TEST',timeline_identity='timeline',clip_ids=('clip',),reference_clip_id=None,
            adjustments={},preset_name='manual',drx_preset_name=None,drx_asset_identity=None,
            before_versions={'clip':{'versionName':'original','versionType':0}},cdl={}))
        cancelled=cancel_colorist_job(store,job.colorist_job_id,job.plan_fingerprint,job.revision,'COLORIST','unused')
        self.assertEqual([],producer_activity_blockers(self.config))
        # Pre-cancellation-schema legacy PREPARED is decoded by the existing contract.
        raw=asdict(job);raw.pop('cancellation_evidence')
        self.config.colorist_jobs_path.write_text(json.dumps({'schema':'ARPHE_COLORIST_JOBS_V1',
            'workstation_id':self.config.workstation_id,'jobs':{job.colorist_job_id:raw}}))
        blocker=producer_activity_blockers(self.config)[0]
        self.assertEqual('GUARDED_CANCEL_OR_CONTINUE',blocker['next_safe_action'])
        self.config.colorist_jobs_path.unlink()
        job_id='timeline_tx_'+'b'*16
        path=self.config.transcript_root/'.timeline_jobs'/self.config.workstation_id/(job_id+'.json')
        path.parent.mkdir(parents=True)
        payload={'schema':'ARPHE_CARABELLESE_TRANSCRIPTION_JOB_V1','job_id':job_id,
            'workstation_id':self.config.workstation_id,'status':'COMPLETED','model':'small','language':'it',
            'source_path':str(self.config.audio_root/'timeline-transcriptions'/self.config.workstation_id/'legacy.wav'),
            'source_name':'legacy.wav','source_fingerprint':'c'*64,'media_root':str(self.config.audio_root),
            'output_path':str(self.config.transcript_root/self.config.workstation_id/'legacy.json'),
            'transcript_root':str(self.config.transcript_root),'transcript_fingerprint':'d'*64,
            'progress_percent':100,'created_at':'2026-11-01T00:00:00Z','updated_at':'2026-11-02T00:00:00Z',
            'error':None,'timeline_source':{'timeline_id':'legacy-timeline','project_name':'ARPHE_TEST'}}
        path.write_text(json.dumps(payload))
        self.assertEqual([],producer_activity_blockers(self.config))
        for change in ({'transcript_fingerprint':None},{'schema':'UNKNOWN'},{'workstation_id':'PC_SEGRETERIA'}):
            path.write_text(json.dumps({**payload,**change}))
            self.assertEqual('RECOVERY_REQUIRED',producer_activity_blockers(self.config)[0]['next_safe_action'])
