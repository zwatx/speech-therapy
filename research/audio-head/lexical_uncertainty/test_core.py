import unittest
import numpy as np
from lexical_uncertainty import core

class CoreTests(unittest.TestCase):
 def setUp(self):
  self.p=np.array([[.4,.2,.4],[.4,.3,.3],[.1,.2,.7],[.2,.2,.6]])
  self.c=np.array([[2,1,2],[1,0,4],[0,2,3],[3,1,1]])
  self.ph=np.array(['A','B','A','B'])
 def metric(self,w):return core.metrics(self.p,np.log(self.p),self.c,self.ph,w,['A','B'])
 def test_expanded_rows(self):
  w=np.array([3,0,2,1]);ids=np.repeat(np.arange(4),w);got=self.metric(w)
  other=core.metrics(self.p[ids],np.log(self.p[ids]),self.c[ids],self.ph[ids],np.ones(len(ids),dtype=int),['A','B'])
  for k in ['NLL','Brier','macroNLL','rating0AP','below2AP']:self.assertAlmostEqual(got[k],other[k],places=14)
  self.assertEqual(got['support'],other['support'])
  expected=sum(w[i]*sum(self.c[i,k]*sum((self.p[i,j]-(j==k))**2 for j in range(3)) for k in range(3)) for i in range(4))/(5*w.sum())
  self.assertAlmostEqual(got['Brier'],expected)
 def test_hand_ties(self):
  p=np.array([[.6,.1,.3],[.6,.2,.2],[.2,.1,.7]]);c=np.array([[5,0,0],[0,0,5],[5,0,0]])
  r=core.metrics(p,np.log(p),c,['A']*3,[1,1,1],['A'])
  self.assertAlmostEqual(r['rating0AP'],.5*.5+.5*(10/15))
  r=core.metrics(p,np.log(p),c,['A']*3,[0,0,1],['A']);self.assertEqual(r['rating0AP'],1.)
 def test_sparse(self):
  r=core.metrics(self.p,np.log(self.p),np.tile([0,0,5],(4,1)),self.ph,[1,0,1,0],['A','B'])
  self.assertEqual(r['support']['undefined'],['macroNLL','rating0AP','below2AP']);self.assertEqual(r['support']['absentPhones'],['B'])
 def test_extreme(self):
  lp=np.array([[0.,-1000.,-2000.]])
  r=core.metrics(np.exp(lp),lp,[[0,0,5]],['A'],[1],['A']);self.assertEqual(r['NLL'],2000.);self.assertEqual(r['Brier'],2.)
 def test_strata(self):
  ids=['z','b','a','b','c'];folds=[1,0,0,0,1]
  a=core.speaker_weights(ids,folds,200,9);b=core.speaker_weights(ids[::-1],folds[::-1],200,9)
  self.assertEqual(a['speakerIds'],['a','b','c','z']);np.testing.assert_array_equal(a['weights'],b['weights'])
  np.testing.assert_array_equal(a['weights'][:,:2].sum(1),2);np.testing.assert_array_equal(a['weights'][:,2:].sum(1),2)
  self.assertTrue(np.any(a['weights']==0));self.assertTrue(np.any(a['weights']==2))
  self.assertFalse(np.array_equal(a['weights'],core.speaker_weights(ids,folds,200,10)['weights']))
 def test_invalids(self):
  args=[self.p,np.log(self.p),self.c,self.ph,[1]*4,['A','B']]
  for slot,bad in [(0,self.p*2),(1,np.zeros_like(self.p)),(2,self.c.astype(float)),(2,np.ones((4,3),dtype=bool)),(2,np.zeros((4,3),dtype=int)),(4,[-1,1,1,1]),(4,[0]*4),(4,[True]*4),(4,[1.]*4),(4,[1]),(5,['A']),(5,['A','A'])]:
   a=args.copy();a[slot]=bad
   with self.subTest(slot=slot),self.assertRaises(ValueError):core.metrics(*a)
  for ids,folds,reps,seed in [(['a','a'],[0,1],2,1),([],[],2,1),(['a'],[False],2,1),(['a'],[0],True,1),(['a'],[0],0,1),(['a'],[0],2,-1)]:
   with self.assertRaises(ValueError):core.speaker_weights(ids,folds,reps,seed)
  for slot in [0,1]:
   a=args.copy();v=a[slot].copy();v[0,0]=np.nan;a[slot]=v
   with self.assertRaises(ValueError):core.metrics(*a)

if __name__=='__main__':unittest.main()
