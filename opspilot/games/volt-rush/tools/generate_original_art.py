#!/usr/bin/env python3
"""VOLT RUSH original asset generator. Authored for BVTech. Requires numpy Pillow trimesh.
All meshes, images and palettes are created here; no downloaded assets or music.
Run: python tools/generate_original_art.py
"""
from pathlib import Path
import math,random
import numpy as np
from PIL import Image,ImageDraw,ImageFilter
import trimesh
from trimesh.transformations import rotation_matrix,translation_matrix

ROOT=Path(__file__).resolve().parents[1]/'public'/'art'
for sub in ('models','textures','portraits'): (ROOT/sub).mkdir(parents=True,exist_ok=True)
PEOPLE=[('nova','#3bd9ff','#e0f9ff','#edba9c','#fffbb2'),('jax','#ffa347','#25384e','#a46d52','#ffd485'),('ivy','#70e6a8','#603a7b','#f2ceb5','#d9ff81'),('bolt','#ffdc5e','#f35c63','#daa17d','#ecffff'),('echo','#e88aff','#284c9d','#c99481','#82f1ff'),('rook','#fc727c','#e9edf0','#976a51','#b2e9ff')]
THEMES={
 'coast':('#415367','#263743','#a9b6b4','#b9c4bb'),
 'forest':('#414f58','#2c3e40','#718c82','#9bc1aa'),
 'neon':('#293950','#171f39','#526991','#f16cda'),
 'candy':('#896883','#684c74','#fcb5d1','#ffe3c5'),
 'moon':('#495878','#2d3659','#9cb5cf','#83fff0'),
 'volcano':('#55434e','#362b3e','#c17666','#ffab63'),
}

def hexrgb(color):
    color=color.lstrip('#');return tuple(int(color[i:i+2],16) for i in (0,2,4))

def art_textures():
    rng=np.random.default_rng(1511)
    for theme,(base,deep,mid,trim) in THEMES.items():
        for size,label in ((1024,'desktop'),(512,'mobile')):
            # Procedural multi-scale terrain aggregate; seamless noise, painted chips and color flecks.
            base_col=np.array(hexrgb(base),dtype=np.float32)
            tiny=rng.normal(0,7,(size,size,1)).astype(np.float32)
            coarse=rng.normal(0,1,(32,32)).astype(np.float32)
            coarse_img=Image.fromarray(np.uint8(np.clip((coarse*14)+128,0,255))).resize((size,size),Image.Resampling.BICUBIC)
            noise=(np.array(coarse_img,dtype=np.float32)-128)[...,None]
            data=np.clip(base_col[None,None,:]+tiny+noise*.5,0,255).astype(np.uint8)
            img=Image.fromarray(data,'RGB')
            d=ImageDraw.Draw(img,'RGBA')
            for j in range(size*size//90):
                x=int(rng.integers(0,size));y=int(rng.integers(0,size));rad=float(rng.random()*2.5+.5)
                c=hexrgb([deep,mid,trim][j%3]);alpha=int(rng.integers(13,48))
                d.ellipse((x-rad,y-rad,x+rad,y+rad),fill=(*c,alpha))
            if theme in ('candy','moon','neon'):
                for j in range(75 if size==1024 else 38):
                    x=int(rng.integers(0,size));y=int(rng.integers(0,size));rr=int(rng.integers(2,9))*size//512
                    d.ellipse((x-rr,y-rr,x+rr,y+rr),outline=(*hexrgb(trim),55),width=max(1,size//512))
            img.save(ROOT/'textures'/f'{theme}-road-{label}.webp','WEBP',quality=89,method=6)
    # Two image assets for colorful road markings; generated independently, no copied game art.
    size=512
    img=Image.new('RGBA',(size,size));d=ImageDraw.Draw(img)
    for j in range(8):
        c=['#ffdc72','#eaf6f8','#5dede5','#fe8b96'][j%4]
        d.rounded_rectangle((j*64+5,10,j*64+55,502),radius=14,fill=c)
        d.rounded_rectangle((j*64+17,24,j*64+43,488),radius=9,fill='#ffffff44')
    img.save(ROOT/'textures'/'track-accent-atlas.webp','WEBP',quality=90,method=6)

def portrait(i,name,suit,hat,skin,accent):
    W=512; im=Image.new('RGB',(W,W));p=ImageDraw.Draw(im)
    a=np.array(hexrgb(hat));b=np.array(hexrgb(suit));arr=np.empty((W,W,3),dtype=np.uint8)
    yy,xx=np.mgrid[:W,:W];blend=np.clip((xx+yy)/850,0,1)[...,None]
    arr[:]=np.clip(a[None,None,:]*(1-blend)+b[None,None,:]*blend*.87,0,255)
    im=Image.fromarray(arr);p=ImageDraw.Draw(im,'RGBA')
    p.ellipse((35,42,477,475),fill=(5,16,36,40),outline=(255,255,255,60),width=6)
    # padded shoulders, glossy costume and oversized friendly face
    p.ellipse((63,342,453,625),fill=hexrgb(suit),outline=(255,255,255,200),width=8)
    p.ellipse((121,112,391,420),fill=hexrgb(skin),outline=(76,39,53,90),width=7)
    p.pieslice((104,69,407,268),180,360,fill=hexrgb(hat))
    p.ellipse((91,119,177,277),fill=hexrgb(hat));p.ellipse((332,119,418,277),fill=hexrgb(hat))
    for x in (186,325):
        p.ellipse((x-40,239,x+39,327),fill='white');p.ellipse((x-19,265,x+22,316),fill='#243047')
        p.ellipse((x-10,272,x+3,287),fill='white')
        p.ellipse((x-61,307,x-19,331),fill=(253,122,146,140))
    p.arc((219,320,304,373),0,180,fill=(89,37,53,210),width=8)
    if i==0:
        p.line((253,72,253,8),fill='white',width=13);p.regular_polygon((253,17,31),5,rotation=15,fill=accent)
    elif i==1:
        p.polygon([(112,146),(93,9),(205,118)],fill=hat);p.polygon([(304,118),(420,10),(408,160)],fill=hat)
    elif i==2:
        p.ellipse((348,12,430,155),fill=accent);p.polygon([(389,71),(350,5),(449,48)],fill=accent)
    elif i==3:
        p.polygon([(136,126),(122,13),(199,104)],fill=accent);p.polygon([(321,104),(400,13),(381,126)],fill=accent)
    elif i==4:
        p.ellipse((194,11,324,82),outline=accent,width=20)
    else:
        p.ellipse((78,83,190,185),fill=hat);p.ellipse((315,83,427,185),fill=hat)
    p.rounded_rectangle((106,429,406,485),radius=22,fill=(5,16,34,190),outline=(255,255,255,95),width=3)
    p.text((256,443),name.upper(),anchor='mt',fill='white',stroke_width=0)
    im.save(ROOT/'portraits'/f'{name}.webp','WEBP',quality=92,method=6)

# glTF originals: expressive collectible characters integrated into six distinct kart bodies.
# Models are PBR geometry, not empty template references.
def blend_color(c):return tuple(hexrgb(c))+(255,)
def make_model(index,detail):
    name,suit,helmet,skin,accent=PEOPLE[index];low=(detail=='mobile')
    balls=1 if low else 2;sides=9 if low else 16
    groups={x:[] for x in ('Paint','Trim','Metal','Glass','Rubber','Seat','Suit','Skin','Helmet','EyeWhite','Pupil','Shine','Blush','Mouth','Accent','Lamp','Dark')}
    palette={'Paint':'#ffffff','Trim':accent,'Metal':'#c0d3e9','Glass':'#406886','Rubber':'#222736','Seat':'#222d49',
       'Suit':suit,'Skin':skin,'Helmet':helmet,'EyeWhite':'#ffffff','Pupil':'#22304a','Shine':'#ffffff','Blush':'#f18d99',
       'Mouth':'#633d59','Accent':accent,'Lamp':'#fdffd1','Dark':'#23344f'}
    def add(mesh,part='Paint',pos=(0,0,0),scale=None,rot=None):
        if scale:mesh.apply_scale(scale)
        if rot:mesh.apply_transform(rotation_matrix(rot[0],rot[1]))
        mesh.apply_translation(pos);groups[part].append(mesh)
    def box(pos,size,part='Paint',rot=None): add(trimesh.creation.box(extents=size),part,pos,rot=rot)
    def ball(pos,size,part='Paint'): add(trimesh.creation.icosphere(subdivisions=balls),part,pos,scale=size)
    def cyl(pos,r,h,part='Metal',axis='y',n=None):
        m=trimesh.creation.cylinder(radius=r,height=h,sections=n or sides)
        # Trimesh cylinders are along Z
        if axis=='y':m.apply_transform(rotation_matrix(math.pi/2,(1,0,0)))
        if axis=='x':m.apply_transform(rotation_matrix(math.pi/2,(0,1,0)))
        add(m,part,pos)
    def cone(pos,r,h,part='Accent',axis='y'):
        m=trimesh.creation.cone(radius=r,height=h,sections=sides)
        if axis=='y':m.apply_transform(rotation_matrix(-math.pi/2,(1,0,0)))
        add(m,part,pos)
    # Six different chassis silhouettes with rounded body sculpting and molded details.
    ball((0,.89,0),(1.29,.48,1.93),'Paint')
    box((0,.86,0),(2.38,.59,3.5),'Paint')
    box((0,1.13,-.27),(2.18,.18,2.1),'Seat')
    if index==0:  # NOVA sleek hover coupe, fins, light bars
        ball((0,.98,1.48),(1.07,.37,.92));box((0,1.55,-1.42),(2.1,.17,.72),'Paint')
        for x in (-1,1):box((x*1.11,.94,-.7),(.37,.32,2.8),'Trim')
    elif index==1: # JAX rally mini-truck with exposed coil chassis
        box((0,1.15,1.3),(2.45,.49,1.1));box((0,1.55,-1.4),(2.52,.21,.53),'Metal')
        for x in (-1,1):cyl((x*1.13,1.2,.7),.18,.98,'Metal','y')
    elif index==2: # IVY garden-speedster, petal fenders
        ball((0,1.13,1.35),(1.23,.31,.77));
        for x in (-1,1):ball((x*1.32,1.2,.5),(.38,.33,1.27),'Trim')
    elif index==3: # BOLT rocket dragster
        ball((0,1.13,1.55),(1.04,.4,1.13));
        for x in (-1,1):cyl((x*.95,.68,-1.95),.33,.74,'Metal','y')
    elif index==4: # ECHO neon race coupe
        box((0,1.58,-1.52),(2.75,.21,.55));
        for x in (-1,1):ball((x*1.22,1.1,.1),(.26,.27,1.78),'Trim')
    else: # ROOK offroad buggy and armored rollbars
        box((0,.86,2),(2.7,.43,.35),'Metal');
        for x in (-1,1):box((x*1.2,1.7,-.55),(.18,.9,.18),'Metal')
    box((0,1.47,-.45),(1.6,.41,1.25),'Seat')
    box((0,1.5,1.9),(1.72,.18,.14),'Metal')
    box((0,.63,2.15),(2.62,.24,.35),'Seat')
    for x in (-.79,.79):
        ball((x,1.07,2),(.4,.15,.09),'Lamp')
        box((x,.97,-1.94),(.38,.20,.12),'Trim')
        for z in (-1.2,1.2):
            box((x*1.48,1.06,z),(.16,.13,.78),'Trim')
    # Dashboard and steering controls
    box((0,1.67,.58),(1.23,.2,.5),'Metal')
    cyl((0,1.95,.78),.47,.1,'Dark','x')
    # tiny mascot pilot. Big face and detailed eyes are visible from forward angle.
    ball((0,2.28,-.55),(.65,.78,.54),'Suit')
    ball((0,3.19,-.5),(.74,.83,.72),'Skin')
    ball((0,3.53,-.69),(.82,.65,.66),'Helmet')
    ball((0,3.36,.07),(.64,.59,.31),'Skin')
    for x in (-.27,.27):
        ball((x,3.43,.333),(.186,.23,.11),'EyeWhite')
        ball((x+.038,3.41,.425),(.108,.155,.074),'Pupil')
        ball((x+.005,3.48,.48),(.042,.054,.04),'Shine')
        ball((x*1.8,3.12,.265),(.165,.085,.043),'Blush')
        ball((x*1.92,3.60,-.42),(.08,.08,.10),'Accent')
    ball((0,3.12,.36),(.15,.057,.047),'Mouth')
    # gloves wrapping steering wheel
    for x in (-1,1):
        ball((x*.59,2.02,.27),(.26,.26,.25),'Suit')
        ball((x*.52,1.88,.51),(.17,.17,.16),'Skin')
    # signature hats, antenna, creature ears, sprouts, horns, planet halo, goggles.
    if index==0:
        cyl((0,4.18,-.53),.045,.48,'Metal');ball((0,4.53,-.53),(.23,.23,.23),'Accent')
        cone((0,4.64,-.53),.23,.46,'Lamp')
    elif index==1:
        for x in (-.67,.67):
            cone((x,4.08,-.64),.34,.93,'Helmet')
            ball((x,4.48,-.6),(.1,.16,.12),'Accent')
    elif index==2:
        cone((-.36,4.2,-.6),.24,.91,'Accent');cone((.33,4.2,-.6),.24,.77,'Suit')
        ball((0,4.29,-.45),(.19,.14,.13),'Accent')
    elif index==3:
        for x in (-.46,.46):cone((x,4.16,-.6),.2,.62,'Accent')
        box((0,4.12,-.27),(1.2,.1,.5),'Helmet')
    elif index==4:
        cyl((0,4.22,-.63),.57,.09,'Accent','y')
        for x in (-.53,.53):ball((x,3.58,.27),(.13,.13,.13),'Metal')
    else:
        ball((-.66,4.05,-.49),(.36,.35,.4),'Accent')
        ball((.66,4.05,-.49),(.36,.35,.4),'Accent')
        box((0,4.15,-.6),(1.0,.11,.56),'Helmet')
    # Model material merges: one draw call per material, plus independently animated wheel sets.
    scene=trimesh.Scene()
    for key,meshes in groups.items():
        if not meshes:continue
        combined=trimesh.util.concatenate(meshes)
        combined.visual.material=trimesh.visual.material.PBRMaterial(name=key,baseColorFactor=blend_color(palette[key]),metallicFactor=.46 if key in ('Metal','Trim','Paint') else .04,roughnessFactor=.25 if key=='Glass' else .48)
        scene.add_geometry(combined,geom_name=key,node_name=key)
    # Four independent wheel transform nodes (each two geometries). Low model keeps geometry light.
    for side in (-1,1):
        for front in (-1,1):
            x,z=side*1.43,front*1.35
            suffix=f'{"L" if side<0 else "R"}{"F" if front>0 else "B"}'
            for label,r,h,color in (('Wheel',.67,.5,'#181e2b'),('Rim',.37,.55,accent),('Hub',.17,.59,'#d6e7fa')):
                wheel=trimesh.creation.cylinder(radius=r,height=h,sections=sides)
                wheel.apply_transform(rotation_matrix(math.pi/2,(0,1,0)))
                wheel.visual.material=trimesh.visual.material.PBRMaterial(name=label,baseColorFactor=blend_color(color),roughnessFactor=.65,metallicFactor=.24)
                scene.add_geometry(wheel,geom_name=f'{label}_{suffix}',node_name=f'{label}_{suffix}',transform=translation_matrix((x,.64,z)))
    scene.export(ROOT/'models'/f'{name}-{detail}.glb')

if __name__=='__main__':
    art_textures()
    for i,p in enumerate(PEOPLE):
        portrait(i,*p)
        for detail in ('desktop','mobile'):
            make_model(i,detail)
    print('Generated',len(list(ROOT.rglob('*.*'))),'original art files',sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file())//1024,'KiB')
