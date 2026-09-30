#!/usr/bin/env python3
"""One stable CLI for agents: inspect, plan, validate, build, preview."""
import argparse,atexit,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.replace(path)

def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    s.add_parser('capabilities')
    a=s.add_parser('map');a.add_argument('plan',type=Path);a.add_argument('--output',type=Path,required=True);a.add_argument('--title',default='City plan');a.add_argument('--no-labels',action='store_true')
    a=s.add_parser('plan');a.add_argument('request',type=Path);a.add_argument('--output',type=Path,required=True)
    a=s.add_parser('validate');a.add_argument('plan',type=Path)
    for cmd in ('build','preview'):
        a=s.add_parser(cmd);a.add_argument('plan',type=Path);a.add_argument('--output',type=Path,required=True);a.add_argument('--blender');a.add_argument('--resolution',type=int,default=640);a.add_argument('--replace',action='store_true')
    args=p.parse_args();start=time.perf_counter()
    from city_generator.planning import plan_city,validate_plan
    if args.command=='capabilities':
        from asset_library.building.scripts.catalog import CATALOG
        result={'version':1,'commands':['plan','validate','build','preview','map'],'road_source':'road_authoring/src/authoringV2.ts (same compiler as GUI)','buildings':[{'key':s.key,'width':s.width,'depth':s.depth,'floors':s.floors} for s in CATALOG], 'request_example':'examples/city/central_200.json','guide':'docs/AGENT_WORKFLOW.md'}
    elif args.command=='plan':
        result=plan_city(json.loads(args.request.read_text()));write(args.output,result);from city_generator.layout import svg
        args.output.with_suffix('.svg').write_text(svg(result))
        result={'valid':True,'plan':str(args.output),**result['summary'],'warnings':result['warnings']}
    elif args.command=='map':
        from city_generator.layout import svg
        if args.output.suffix.lower()!='.svg':raise ValueError('Map output must use .svg')
        if args.output.resolve()==args.plan.resolve():raise ValueError('Map output cannot overwrite its plan')
        content=svg(json.loads(args.plan.read_text()),args.title,not args.no_labels)
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(content,encoding='utf-8')
        result={'valid':True,'map':str(args.output),'kind':'schematic','build_validated':False}
    else:
        plan=json.loads(args.plan.read_text());result=validate_plan(plan)
        if args.command in ('build','preview'):
            blender=args.blender or os.environ.get('BLENDER_BIN') or shutil.which('blender') or '/Applications/Blender.app/Contents/MacOS/Blender'
            if not Path(blender).is_file():raise ValueError('Blender unavailable; pass --blender or set BLENDER_BIN')
            out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
            import fcntl
            lock=(out/'.city.lock').open('a+')
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise ValueError('Another generator is using this output directory') from None
            atexit.register(lock.close)
            if (out/'city.blend').exists() and not (out/'build_report.json').exists() and not args.replace:raise ValueError('Unrecognized existing Blend; choose another output or --replace')
            from asset_library.shared.fonts import font_signature
            current_font=font_signature()
            cached=None
            if (out/'build_report.json').exists():
                previous=json.loads((out/'build_report.json').read_text())
                if previous.get('plan_fingerprint')!=plan['fingerprint'] and not args.replace:raise ValueError('Output belongs to another plan; use a new output or --replace')
                blend=out/'city.blend'
                if previous.get('font_signature')==current_font and previous.get('plan_fingerprint')==plan['fingerprint'] and blend.is_file() and hashlib.sha256(blend.read_bytes()).hexdigest()==previous.get('blend_sha256'):cached=previous
            if cached:
                images_ok=cached.get('preview_resolution')==args.resolution and all((out/name).is_file() and hashlib.sha256((out/name).read_bytes()).hexdigest()==digest for name,digest in cached.get('render_hashes',{}).items()) and len(cached.get('render_hashes',{}))==2
                if args.command=='build' or images_ok:
                    print(json.dumps({'valid':True,'reused':True,'blend':str(out/'city.blend'),'summary':plan['summary'],'elapsed_seconds':round(time.perf_counter()-start,3)},ensure_ascii=False,indent=2));return
            worker='preview.py' if cached and args.command=='preview' else 'build.py'
            cmd=[blender,'-b','--factory-startup','--python-exit-code','1','--python',str(ROOT/'city_generator'/worker),'--','--plan',str(args.plan.resolve()),'--output',str(out),'--resolution',str(args.resolution)]
            if args.command=='preview':cmd+=['--preview']
            with (out/'build.log').open('w') as log:
                run=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
            if run.returncode:raise ValueError('Blender failed; see '+str(out/'build.log'))
            report=json.loads((out/'build_report.json').read_text())
            result={k:v for k,v in report.items() if k in ('valid','blend','summary','road_seconds','build_seconds','total_seconds','preview_seconds','blend_bytes','renders','warnings')}
            result['report']=str(out/'build_report.json')
    result['elapsed_seconds']=round(time.perf_counter()-start,3);print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError,OSError) as e:print(json.dumps({'valid':False,'errors':[str(e)]},ensure_ascii=False),file=sys.stderr);sys.exit(1)
