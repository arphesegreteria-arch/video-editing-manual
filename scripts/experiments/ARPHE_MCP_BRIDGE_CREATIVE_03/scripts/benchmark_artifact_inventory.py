"""Bounded read-only before/after lookup benchmark against one registry snapshot."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge import artifact_hygiene as hygiene
from bridge.artifact_records import artifact_store_for, load_artifact_policy, sha256_file
from bridge.config import load_config
from bridge.registry import Registry


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repetitions',type=int,default=3,choices=range(1,6))
    parser.add_argument('--policy',type=Path,default=Path(__file__).resolve().parents[1]/'artifact_retention.json')
    args=parser.parse_args()
    config=load_config(args.config)
    config=replace(config,artifact_policy_path=args.policy.resolve())
    store=artifact_store_for(config)
    registry_hash=sha256_file(store.path)
    records=store.records()
    known={Path(r.path).resolve() for r in records if r.state!='PURGED'}
    new=hygiene._unclassified
    source=inspect.getsource(new).replace('any(parent in known_paths for parent in resolved.parents)',
        'any(known in resolved.parents for known in known_paths)')
    namespace=dict(hygiene.__dict__)
    exec(compile(source,'<old-lookup-benchmark>','exec'),namespace)
    old=namespace['_unclassified']
    timings={'old':[],'new':[]}
    outputs={}
    for label,function in (('old',old),('new',new)):
        for _ in range(args.repetitions):
            start=time.perf_counter();outputs[label]=function(config,known)
            timings[label].append(time.perf_counter()-start)
    if outputs['old']!=outputs['new']:raise AssertionError('Lookup results differ')
    full={}
    now=datetime.now(timezone.utc)
    for label,function in (('old',old),('new',new)):
        hygiene._unclassified=function
        start=time.perf_counter()
        result=hygiene.inspect_artifacts(config,store,Registry(config.state_path),
            load_artifact_policy(config.artifact_policy_path),now,limit=50)
        full[label]={'seconds':time.perf_counter()-start,'fingerprint':result['inventory_fingerprint'],
                     'item_count':result['item_count'],'summary':result['summary']}
    hygiene._unclassified=new
    if full['old']['fingerprint']!=full['new']['fingerprint']:raise AssertionError('Inventory results differ')
    if sha256_file(store.path)!=registry_hash:raise AssertionError('Registry changed during measurement')
    report={'known_paths':len(known),'unclassified_candidates':len(outputs['new']),
            'registry_sha256':registry_hash,'equal_results':True,'lookup_seconds':timings,'full_inspect':full}
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
