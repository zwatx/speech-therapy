from .policy import AdmissionError,decide
from .models import readiness
__all__=['AdmissionError','decide','readiness','recognize','assess','declaration']
def recognize(wav_bytes,**kwargs):
    from .adapter import recognize as run
    return run(wav_bytes,**kwargs)
def assess(wav_bytes,prompt,age_years=9,**kwargs):
    from .adapter import assess as run
    return run(wav_bytes,prompt,age_years,**kwargs)

def declaration():
    from .adapter import declaration as describe
    return describe()
