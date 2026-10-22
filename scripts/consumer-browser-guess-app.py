#!/usr/bin/env python3
"""Explicit dispatch into the isolated native API; no predecessor imports/fallback."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'research/assessment-consumer-browser-guess-app'
sys.path.insert(0,str(PACKAGE))
from consumer_sound_app import launcher
if Path(launcher.__file__).resolve()!=PACKAGE/'consumer_sound_app/launcher.py':
    raise ValueError('wrong_successor_package')
if __name__=='__main__':raise SystemExit(launcher.main())
