import math,unittest
from road_generator.core.parking import curved_frontage
class Arc:
 length=150
 def __init__(self,radius=80,angle=0):self.radius=radius;self.angle=angle
 def tangent_at_distance(self,s):
  a=s/self.radius+self.angle;return math.cos(a),math.sin(a)
 def offset_point(self,s,lateral):
  a=s/self.radius+self.angle;r=self.radius-lateral
  return r*math.sin(a),-r*math.cos(a)
class Line:
 length=150
 def tangent_at_distance(self,s):return 1,0
 def offset_point(self,s,lateral):return s,lateral
class FrontageTests(unittest.TestCase):
 def test_straight_no_extension(self):
  for side in (-1,1):
   f=curved_frontage(Line(),70,side*10.3,side,18,9)
   self.assertFalse(f['curved']);self.assertEqual(f['setback'],0)
 def test_inner_outer_and_rotations(self):
  for angle in (0,.4,2):
   for side in (-1,1):
    f=curved_frontage(Arc(angle=angle),70,side*10.3,side,18,9)
    self.assertTrue(f['curved'])
    self.assertTrue(all(f['setback']-y>=.00499 for x,y in f['points']))
    for x,y in f['points']:
     tangent_distance=x-9;radius=80-side*10.3
     expected=side*(radius-math.sqrt(radius**2-tangent_distance**2))
     self.assertAlmostEqual(y,expected,places=6)
 def test_edge_end_rejected(self):
  with self.assertRaises(ValueError):curved_frontage(Line(),1,10.3,1,18,9)
if __name__=='__main__':unittest.main()
