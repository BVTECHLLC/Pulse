#!/usr/bin/env python3
"""Original, hand-composed arcade track cards. All rights: BVTech game."""
from PIL import Image,ImageDraw,ImageFilter
from pathlib import Path
import numpy as np,random,math
base=Path(__file__).resolve().parents[1]/'public'/'art'/'tracks'
base.mkdir(parents=True,exist_ok=True)
styles={
 'coast':((255,180,132),(94,203,240),(247,226,146),'sun'),
 'forest':((117,220,203),(63,126,152),(116,204,135),'forest'),
 'neon':((29,33,79),(6,12,46),(253,111,221),'city'),
 'candy':((255,183,218),(171,165,253),(255,224,132),'candy'),
 'moon':((22,46,91),(17,21,62),(102,255,221),'moon'),
 'volcano':((255,156,106),(88,43,76),(255,197,99),'lava')}
def color(x):return np.array(x,dtype=np.float32)
for idx,(key,(top,bottom,accent,env)) in enumerate(styles.items()):
 W,H=960,540
 y,x=np.mgrid[:H,:W];grad=(y/H)**.8
 pix=np.clip(color(top)[None,None,:]*(1-grad[...,None])+color(bottom)[None,None,:]*grad[...,None]+np.random.default_rng(900+idx).normal(0,1.6,(H,W,1)),0,255).astype('uint8')
 im=Image.fromarray(pix,'RGB');draw=ImageDraw.Draw(im,'RGBA');r=random.Random(30+idx)
 if env=='sun':
  draw.ellipse((643,55,831,242),fill=(255,240,169,245))
  for j in range(17):
   px=j*66-20;py=230+r.randrange(65)
   draw.polygon([(px-45,py+90),(px+22,py-30),(px+110,py+90)],fill=(83,161,168,120))
  draw.rectangle((0,332,960,540),fill=(48,168,189,170))
 elif env=='forest':
  for j in range(24):
   px=j*50-35;py=310+r.randrange(65);hh=160+r.randrange(100)
   draw.polygon([(px-60,py+60),(px+20,py-hh),(px+90,py+60)],fill=(20,83,80,180))
  for j in range(16):
   px=j*75-50;py=320+r.randrange(90)
   draw.polygon([(px-35,py+85),(px,py-125),(px+35,py+85)],fill=(27,107,79,235))
 elif env=='city':
  for j in range(55):
   px=j*23-30;hh=r.randrange(40,250)
   draw.rectangle((px,340-hh,px+23,380),fill=(23,31,67,230))
   for n in range(hh//16):
    draw.rectangle((px+5,335-hh+n*16,px+9,342-hh+n*16),fill=(*accent,220) if j%2 else (87,238,248,190))
  for j in range(45):
   px=r.randrange(960);py=r.randrange(210);draw.ellipse((px,py,px+2,py+2),fill='white')
 elif env=='candy':
  for j in range(15):
   px=j*72-40;py=275+r.randrange(65)
   draw.ellipse((px-55,py-15,px+72,py+80),fill=(*r.choice([(249,133,184),(125,224,238),(246,228,162)]),220))
   if j%3==0:draw.ellipse((px,py-125,px+95,py-30),outline=(255,255,255,230),width=10)
 elif env=='moon':
  draw.ellipse((720,40,879,199),fill=(214,242,255,210))
  for j in range(80):
   px=r.randrange(960);py=r.randrange(260);draw.ellipse((px,py,px+3,py+3),fill=(225,255,244,170))
  for j in range(15):
   px=j*80-60;py=298+r.randrange(40)
   draw.polygon([(px-32,py+65),(px+32,py-90),(px+71,py+65)],fill=(70,85,150,130))
 elif env=='lava':
  draw.ellipse((725,47,870,192),fill=(255,236,146,210))
  for j in range(14):
   px=j*90-40;py=310+r.randrange(45)
   draw.polygon([(px-72,py+95),(px+31,py-135),(px+105,py+95)],fill=(78,40,70,220))
   draw.line([(px,py+45),(px+30,py-115),(px+47,py+40)],fill=(255,138,75,180),width=12)
 # Winding roadway, foreground, neon curb, speed strips.
 draw.polygon([(345,249),(505,249),(810,540),(-70,540)],fill=(21,33,55,245) if env!='candy' else (79,58,104,240))
 draw.line([(345,249),(-70,540)],fill=(*accent,245),width=18)
 draw.line([(505,249),(810,540)],fill=(*accent,245),width=18)
 for j in range(7):
  t=(j+.5)/8;y0=260+t*t*290;x0=425+(t-.4)*40;ww=3+9*t
  draw.line([(x0,y0),(x0+ww*.3,y0+6+t*25)],fill=(250,252,245,205),width=max(2,int(ww)))
 # branded circular kinetic badge
 draw.ellipse((41,45,169,174),fill=(8,19,42,170),outline=(*accent,235),width=6)
 draw.text((105,94),'V',anchor='mm',fill=(255,255,255,255),stroke_width=2,stroke_fill=(*accent,245))
 draw.rounded_rectangle((35,412,540,507),radius=22,fill=(10,21,37,210),outline=(*accent,255),width=3)
 from PIL import ImageFont
 try:font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',36)
 except:font=None
 titles={'coast':'SOLAR COAST','forest':'EMERALD RUN','neon':'NEON METROPOLIS','candy':'CANDY CLOUDWAY','moon':'LUNAR LOOP','volcano':'EMBER RIDGE'}
 draw.text((61,430),titles[key],font=font,fill='white',stroke_width=1,stroke_fill=(10,15,40))
 im.save(base/f'{key}.webp','WEBP',quality=88,method=6)
print('Cards:',len(styles), 'total KB:',sum(f.stat().st_size for f in base.glob('*.webp'))//1024)
