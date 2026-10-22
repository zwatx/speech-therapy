import copy
import unittest
import numpy as np
import torch
from multiphone_models import MeanPoolPhoneRatingHead
from lexical_noise import core as c


def prediction(p):
    p = np.asarray(p, dtype=np.float64)
    return dict(probabilities=p.tolist(), logProbabilities=np.log(p).tolist())


def fixture(width=13, n=65):
    torch.manual_seed(12)
    m = MeanPoolPhoneRatingHead(feature_dim=width, num_phones=24, hidden_dim=128, dropout=.1).eval()
    state = dict(model=m.state_dict(), mean=torch.zeros(width), std=torch.ones(width))
    rng = np.random.default_rng(4)
    return m, state, rng.normal(size=(n,1024)).astype(np.float32), rng.normal(size=(n,13)).astype(np.float32)


class CoreTests(unittest.TestCase):
    def test_label_free_scalar_matches_direct_two_batch_path_without_mutation(self):
        m, s, t, x = fixture()
        old = {k:v.clone() for k,v in s['model'].items()}
        ids = list(range(65)); phones = [i % 23 for i in ids]
        out = c.predict(s,t,x,ids,phones)
        with torch.no_grad():
            chunks=[]
            for start in (0,64):
                p=torch.tensor(phones[start:start+64])[:,None];mask=torch.ones(p.shape,dtype=torch.bool)
                chunks.append(m(torch.tensor(x[start:start+64])[:,None,:],mask,p,mask)[:,0])
            logits=torch.cat(chunks)
        self.assertEqual(out['logProbabilities'],logits.double().log_softmax(-1).tolist())
        self.assertEqual(out['rawProbabilities'],logits.softmax(-1).tolist())
        self.assertNotIn('NLL',out)
        for k,v in s['model'].items(): self.assertTrue(torch.equal(v,old[k]))

    def test_projection_zero_and_nonzero_cast_order(self):
        m,s,t,x=fixture(29)
        torch.manual_seed(8)
        transform=dict(center=torch.randn(1024,dtype=torch.float64),basis=torch.randn(1024,16,dtype=torch.float64)/32)
        delta=torch.randn(1024,16,dtype=torch.float64)/1000
        ids=list(range(65));phones=[i%23 for i in ids]
        base=c.predict(s,t,x,ids,phones,transform)
        self.assertEqual(base,c.predict(s,t,x,ids,phones,transform,torch.zeros_like(delta)))
        out=c.predict(s,t,x,ids,phones,transform,delta)
        centered=torch.tensor(t,dtype=torch.float64)-transform['center']
        values=torch.cat(((centered@transform['basis']).float(),torch.tensor(x)),1)
        logits=[]
        with torch.no_grad():
            for start in (0,64):
                ix=ids[start:start+64];v=values[ix].clone();v[:,:16]+=(centered[ix]@delta).float()
                p=torch.tensor(phones[start:start+64])[:,None];mask=torch.ones(p.shape,dtype=torch.bool)
                logits.append(m(v[:,None,:],mask,p,mask)[:,0])
        self.assertEqual(out['logProbabilities'],torch.cat(logits).double().log_softmax(-1).tolist())
        self.assertNotEqual(base,out)

    def test_invalid_inputs_rejected(self):
        _,s,t,x=fixture(n=2)
        for kind in ('offset','phone','nan','scale','correction'):
            ss=copy.deepcopy(s);tt=t.copy();ids=[0,1];phones=[0,1];kwargs={}
            if kind=='offset':ids=[0,0]
            elif kind=='phone':phones=[0,23]
            elif kind=='nan':tt[0,0]=np.nan
            elif kind=='scale':ss['std'][0]=0
            else:kwargs['correction']=torch.zeros((1024,16),dtype=torch.float64)
            with self.subTest(kind=kind),self.assertRaises(ValueError):c.predict(ss,tt,x,ids,phones,**kwargs)

    def test_movement_hand_calculation_and_argmax_ties(self):
        a=prediction([[.2,.3,.5],[.45,.45,.1]])
        b=prediction([[.1,.2,.7],[.1,.45,.45]])
        m=c.movement(a,b)
        np.testing.assert_allclose(m['TV'],[.2,.35],atol=1e-15)
        np.testing.assert_allclose(m['expectedShift'],[.3,.7],atol=1e-15)
        np.testing.assert_allclose(m['rating0Shift'],[-.1,-.35],atol=1e-15)
        np.testing.assert_allclose(m['below2Shift'],[-.2,-.35],atol=1e-15)
        self.assertEqual(m['argmaxChanged'],[False,True])
        rev=c.movement(b,a)
        np.testing.assert_allclose(rev['TV'],m['TV'])
        np.testing.assert_allclose(rev['expectedShift'],-np.asarray(m['expectedShift']))

    def test_extreme_average_is_stable_and_movement_has_no_label_inputs(self):
        a=dict(probabilities=[[0.,0.,1.]],logProbabilities=[[-2000.,-3000.,0.]])
        b=dict(probabilities=[[0.,0.,1.]],logProbabilities=[[-2200.,-2800.,0.]])
        mixed=c.average(a,b)
        self.assertAlmostEqual(mixed['logProbabilities'][0][0],-2000-np.log(2),places=12)
        self.assertEqual(c.movement(a,mixed)['TV'],[0.])
        bad=copy.deepcopy(a);bad['probabilities'][0][2]=2
        with self.assertRaises(ValueError):c.movement(a,bad)

    def test_empty_support_and_paired_maximum_definition(self):
        m=c.movement(prediction([[.2,.3,.5],[.2,.3,.5]]),prediction([[.1,.2,.7],[.1,.3,.6]]))
        rows=[dict(clipId='a',speakerId='s',targetPhone='B'),dict(clipId='a',speakerId='s',targetPhone='P')]
        summary=c.summarize(m,rows)
        self.assertEqual(summary['positions'],2);self.assertEqual(summary['clips'],1);self.assertEqual(summary['speakers'],1)
        self.assertIsNone(c.summarize({k:[] for k in m},[])['measures'])
        candidate=dict(m,TV=[.2,.1]);reference=dict(m,TV=[.1,.3])
        compare=c.compare(candidate,reference)
        self.assertAlmostEqual(compare['maxTVChange'],-.1)
        self.assertEqual((compare['lowerTV'],compare['higherTV']),(1,1))
        self.assertIsNone(c.compare({k:[] for k in m},{k:[] for k in m}))


if __name__=='__main__':unittest.main()
