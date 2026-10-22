"""Local owner CLI: credentials never appear in command arguments or output."""
import argparse
import getpass
from pathlib import Path
import secrets
from .setup import initialize,reopen
from .server import serve
from .models import JourneyError

def main():
    parser=argparse.ArgumentParser(description='Local engineering desktop journey')
    commands=parser.add_subparsers(dest='command',required=True)
    for name in ('init','fixture','serve','cleanup'):
        command=commands.add_parser(name); command.add_argument('root',type=Path)
        if name=='init': command.add_argument('--account',required=True)
        if name=='serve': command.add_argument('--port',type=int,default=8780)
    args=parser.parse_args()
    try:
        if args.command in ('init','fixture'):
            account=args.account if args.command=='init' else 'operator'
            password=getpass.getpass('Local account password: ') if args.command=='init' else secrets.token_urlsafe(32)
            initialize(args.root,account,password,fixture=args.command=='fixture')
            print('Private journey initialized. Fixture credentials are stored privately.' if args.command=='fixture' else 'Private journey initialized.')
        else:
            engine,catalog=reopen(args.root)
            if args.command=='cleanup': engine.cleanup(); print('Private derived retention reconciled.')
            else: serve(engine,catalog,port=args.port)
    except Exception as error:
        code=error.code if isinstance(error,JourneyError) else 'journey_unavailable'
        parser.exit(1,code+'\n')
if __name__=='__main__': main()
