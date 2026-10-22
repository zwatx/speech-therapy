import argparse,json,sys
from .policy import AdmissionError,digest
from .runner import prepare_plan,run_plan,write
from .models import private_read

def main(argv=None):
    parser=argparse.ArgumentParser(description='Known licensed offline admission challenges')
    sub=parser.add_subparsers(dest='command',required=True)
    plan=sub.add_parser('plan');plan.add_argument('output')
    run=sub.add_parser('run');run.add_argument('plan');run.add_argument('output');run.add_argument('--expected-sha',required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='plan':
            result=prepare_plan();write(args.output,result)
            print(json.dumps({'planSha256':digest(result),'denominators':result['denominators']},sort_keys=True));return 0
        plan=json.loads(private_read(args.plan,8000000));report=run_plan(plan,args.expected_sha,args.output)
        print(json.dumps({key:report[key] for key in ('planSha256','denominators','terminalAttempts','actualAcousticWorkerCalls','actualResearchBridgeCalls','processed','unavailableReasons','crossWordFalseMatchProbesAdmitted','replicates')},sort_keys=True));return 0
    except (AdmissionError,OSError,ValueError,KeyError,TypeError) as error:
        print(error.code if isinstance(error,AdmissionError) else 'run_unavailable',file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
