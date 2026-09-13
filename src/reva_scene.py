"""RevA original motion graphics; timing is supplied by the current narration.
This module renders pixels only and never accesses credentials or the network.
"""
from __future__ import annotations
import argparse, math, json, subprocess, sys, re
from pathlib import Path
from functools import lru_cache
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent
S=1.5; W=1080; H=1920; FPS=30; AUDIO_END=0.0; END=0.0
WHITE='#F0F5F8'; MUTED='#9BACBE'; YELLOW='#FFCB55'; CYAN='#60D8EF'; ORANGE='#FF9864'; INK='#0A1320'; LINE='#263D52'
REG='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
for p in [str(ROOT.parent/'assets/fonts/Lato-Regular.ttf'),'/usr/share/fonts/truetype/lato/Lato-Regular.ttf']:
 if Path(p).exists(): REG=p; break
for p in [str(ROOT.parent/'assets/fonts/Lato-Bold.ttf'),'/usr/share/fonts/truetype/lato/Lato-Bold.ttf']:
 if Path(p).exists(): BOLD=p; break
@lru_cache(maxsize=200)
def font(n,b=False): return ImageFont.truetype(BOLD if b else REG,round(n*S))
def xy(p): return tuple(round(v*S) for v in p)
def box(p): return xy(p)
def ease(x): x=max(0,min(1,x)); return 1-(1-x)**3

def text(im, s, p, n=30, color=WHITE, bold=False, anchor='la'):
 ImageDraw.Draw(im).text(xy(p),s,font=font(n,bold),fill=color,anchor=anchor)
def line(im,p,fill=LINE,width=2): ImageDraw.Draw(im).line([xy(k) for k in p],fill=fill,width=max(1,round(width*S)),joint='curve')
def ellipse(im,p,fill=None,outline=None,width=1): ImageDraw.Draw(im).ellipse(box(p),fill=fill,outline=outline,width=max(1,round(width*S)))
def rect(im,p,fill=None,outline=None,width=1,r=0):
 d=ImageDraw.Draw(im)
 if r: d.rounded_rectangle(box(p),radius=round(r*S),fill=fill,outline=outline,width=round(width*S))
 else: d.rectangle(box(p),fill=fill,outline=outline,width=round(width*S))
def poly(im,p,fill,outline=None,width=1):
 ImageDraw.Draw(im).polygon([xy(k) for k in p],fill=fill)
 if outline: line(im,p+[p[0]],outline,width)
def centered(im,s,y,n=30,color=WHITE,bold=False,x=350): text(im,s,(x,y),n,color,bold,'ma')
def width(s,n,b=False): return font(n,b).getlength(s)/S

def background(grid=True):
 yy,xx=np.mgrid[0:H,0:W]; q=np.exp(-(((xx-W*.63)/(W*.85))**2+((yy-H*.48)/(H*.42))**2)*2)
 a=np.empty((H,W,3),dtype=np.uint8)
 for i,(base,delta) in enumerate([(7,8),(14,17),(23,22)]): a[:,:,i]=base+q*delta
 im=Image.fromarray(a,'RGB').convert('RGBA')
 if grid:
  for x in range(0,721,48): line(im,[(x,320),(x,955)],'#152638',.6)
  for y in range(320,956,48): line(im,[(0,y),(720,y)],'#152638',.6)
  rect(im,(0,0,720,83),'#09121D')
 return im
BG=background(); OUTBG=background(False)

def heading(im,kicker,lines,colors=None):
 text(im,kicker,(48,109),17,MUTED,True)
 line(im,[(48,149),(112,149)],CYAN,3)
 for i,s in enumerate(lines): text(im,s,(45,178+i*66),57,(colors or [WHITE]*len(lines))[i],True)

def arrow(im,points,color=CYAN,t=0,width_=3,dots=True):
 line(im,points,color,width_)
 a=np.array(points[-2],float); b=np.array(points[-1],float); v=b-a; v/=max(np.linalg.norm(v),1); perp=np.array([-v[1],v[0]])
 p=[tuple(b),tuple(b-12*v+5*perp),tuple(b-12*v-5*perp)]; poly(im,p,color)
 if dots:
  lens=[math.dist(a,b) for a,b in zip(points,points[1:])]; total=sum(lens)
  for k in range(max(2,int(total/70))):
   loc=(t*75+k*70)%max(total,1)
   for j,L in enumerate(lens):
    if loc<=L:
     u=loc/max(L,.01); a=points[j]; b=points[j+1]; x=a[0]+(b[0]-a[0])*u; y=a[1]+(b[1]-a[1])*u
     ellipse(im,(x-4,y-4,x+4,y+4),WHITE); break
    loc-=L

# Populated by configure_timeline for the actual recording.
STARTS=[]; ENDS=[]; SENTENCES=[]

def wrapped(s,maxw=594,size=29):
 lines=[]; acc=''
 for w in s.split():
  nxt=(acc+' '+w).strip()
  if width(nxt,size,True)>maxw and acc: lines.append(acc); acc=w
  else: acc=nxt
 if acc: lines.append(acc)
 return lines
@lru_cache(maxsize=30)
def caption_image(i):
 ls=wrapped(SENTENCES[i]); im=Image.new('RGBA',(W,round((len(ls)*39+40)*S)),(0,0,0,0))
 rect(im,(40,0,660,len(ls)*39+31),'#09121E',outline='#263C4D',r=14)
 rect(im,(40,13,44,len(ls)*39+17),CYAN,r=2)
 for j,s in enumerate(ls): centered(im,s,16+j*39,29,WHITE,True)
 return im

def captions(im,t):
 for i,(a,b) in enumerate(zip(STARTS,ENDS)):
  if a-.025<=t<=b+.20:
   tile=caption_image(i); yy=round(992*S)
   im.alpha_composite(tile,(0,yy)); break

def topbar(im,section,t):
 text(im,'MAK\u0130NEN\u0130N ARKASINDAK\u0130 M\u00dcHEND\u0130SL\u0130K',(47,40),13,MUTED,True)
 text(im,section,(653,39),14,CYAN,True,'ra')
 rect(im,(48,75,650,78),'#203143')
 rect(im,(48,75,48+602*min(1,t/AUDIO_END),78),CYAN)

def wheel(im,cx,cy,r,t,electric=False):
 ellipse(im,(cx-r-4,cy-r-4,cx+r+4,cy+r+4),'#080C12',outline='#50606B',width=2)
 ellipse(im,(cx-r+6,cy-r+6,cx+r-6,cy+r-6),'#101B26',outline='#2F3C47',width=4)
 for k in range(22):
  a=k*math.tau/22+t*.7; a2=a+.06
  p=[(cx+(r-5)*math.cos(a),cy+(r-5)*math.sin(a)),(cx+(r-17)*math.cos(a2),cy+(r-17)*math.sin(a2))]; line(im,p,'#42505B',4)
 ellipse(im,(cx-r*.53,cy-r*.53,cx+r*.53,cy+r*.53),'#344659',outline='#688095',width=2)
 ellipse(im,(cx-r*.34,cy-r*.34,cx+r*.34,cy+r*.34),'#101E2B',outline='#9AADBE',width=2)
 for k in range(8):
  a=k*math.tau/8+t*.7; x=cx+r*.42*math.cos(a); y=cy+r*.42*math.sin(a)
  ellipse(im,(x-2,y-2,x+2,y+2),WHITE)
 if electric:
  ellipse(im,(cx-r-9,cy-r-9,cx+r+9,cy+r+9),None,CYAN,3)
  ellipse(im,(cx-14,cy-14,cx+14,cy+14),CYAN)
  poly(im,[(cx+2,cy-10),(cx-5,cy+1),(cx,cy+1),(cx-2,cy+10),(cx+6,cy-2),(cx+1,cy-2)],INK)
 else: ellipse(im,(cx-13,cy-13,cx+13,cy+13),'#8897A3')

@lru_cache(maxsize=16)
def truck(rotframe=0,electric=True):
 im=Image.new('RGBA',(round(660*S),round(380*S)),(0,0,0,0)); t=rotframe/15
 # Far wheels, ladder and chassis.
 wheel(im,187,288,67,t,False); wheel(im,519,288,67,t,False)
 poly(im,[(87,222),(577,222),(592,262),(97,267)],'#596774','#A0ADB9',2)
 rect(im,(145,204,468,238),'#293747',r=6)
 # Dump body, filled with rock. Generic illustration, not a CAD model.
 poly(im,[(47,74),(65,39),(98,55),(128,29),(161,48),(197,23),(230,47),(260,28),(293,45),(328,39),(366,65),(406,76)],'#697985','#87929A',2)
 poly(im,[(30,62),(390,62),(430,195),(388,227),(92,227),(46,171)],YELLOW,'#8A661F',3)
 poly(im,[(45,80),(378,80),(410,183),(376,207),(108,207),(64,162)],'#E2A93E')
 for xx in [110,165,220,275,330]: line(im,[(xx,85),(xx+25,202)],'#BB862A',5)
 line(im,[(42,76),(386,76)],'#FFE0A0',4)
 # Engine hood and cab.
 poly(im,[(411,148),(574,148),(594,214),(572,242),(430,240),(404,209)],'#E2AC45','#FFD789',2)
 rect(im,(480,86,567,153),'#EAB64B',outline='#FFDB91',width=2,r=5)
 poly(im,[(488,95),(557,95),(557,137),(488,137)],'#32677A','#73B7C9',2)
 line(im,[(521,96),(521,138)],'#DFAC46',3)
 rect(im,(475,78,574,89),YELLOW,r=3)
 rect(im,(570,151,585,214),'#243746',r=2)
 for yy in range(156,210,7): line(im,[(572,yy),(584,yy)],'#7D9BA8',1)
 for xx in range(422,474,9): line(im,[(xx,167),(xx,195)],'#896224',3)
 rect(im,(580,208,603,225),'#9FACB7',r=3)
 rect(im,(578,173,592,183),'#F8F7E7',r=3)
 # Exhaust, platform, railings and ladder.
 rect(im,(445,99,452,160),'#85939F',r=2); line(im,[(449,100),(443,94)],'#9AAAB7',4)
 line(im,[(476,156),(476,189),(563,189),(563,149)],'#DDE5E7',3)
 line(im,[(583,237),(598,306)],'#C7D3DC',3); line(im,[(596,232),(611,302)],'#C7D3DC',3)
 for yy in range(245,303,12):
  x=584+(yy-237)*.21; line(im,[(x,yy),(x+14,yy-3)],'#C7D3DC',3)
 # Suspension and foreground wheels.
 line(im,[(163,232),(160,272)],'#ACBAC5',9); line(im,[(500,231),(496,271)],'#ACBAC5',9)
 wheel(im,157,291,72,t,electric); wheel(im,491,291,72,t,False)
 return im

def paste_truck(im,x,y,scale=.98,t=0,angle=0,electric=True):
 tile=truck(int(t*15)%160,electric).copy()
 if scale!=1: tile=tile.resize((round(tile.width*scale),round(tile.height*scale)),Image.Resampling.LANCZOS)
 if angle: tile=tile.rotate(angle,resample=Image.Resampling.BICUBIC,expand=True)
 im.alpha_composite(tile,xy((x,y)))

def engine_icon(im,x,y,t,col=YELLOW):
 rect(im,(x-48,y-26,x+42,y+31),'#263A48',col,3,8)
 for k in range(3):
  xx=x-35+k*28; rect(im,(xx,y-43,xx+21,y-17),col,r=3)
  h=4+6*math.sin(t*6+k*2); line(im,[(xx+10,y-12),(xx+10,y+15+h)],WHITE,3)
 line(im,[(x-61,y+19),(x-48,y+19)],col,8); line(im,[(x+42,y+12),(x+60,y+12)],col,8)
 rect(im,(x-30,y+31,x+27,y+39),col,r=2)

def generator_icon(im,x,y,t,col=CYAN):
 ellipse(im,(x-48,y-48,x+48,y+48),'#162A39',col,3)
 ellipse(im,(x-32,y-32,x+32,y+32),None,'#467589',2)
 for k in range(3):
  a=t*2+k*math.tau/3; line(im,[(x,y),(x+29*math.cos(a),y+29*math.sin(a))],col,7)
 centered(im,'G',y-18,30,WHITE,True,x)

def drive_icon(im,x,y,t,col=CYAN):
 rect(im,(x-44,y-46,x+44,y+46),'#183141',col,3,8)
 line(im,[(x-26,y-17),(x+26,y-17)],col,2)
 pts=[]
 for k in range(53): pts.append((x-26+k,y+13+11*math.sin((k/52)*math.tau*1.8-t*4)))
 line(im,pts,WHITE,2)
 for k in range(4): line(im,[(x-48,y-30+k*20),(x-59,y-30+k*20)],col,3); line(im,[(x+48,y-30+k*20),(x+59,y-30+k*20)],col,3)

def battery_icon(im,x,y,col=CYAN):
 rect(im,(x-115,y-66,x+115,y+66),None,col,5,14)
 rect(im,(x+115,y-22,x+130,y+22),col,r=4)
 for k in range(3): rect(im,(x-96+k*65,y-46,x-44+k*65,y+46),'#183949',col,2,4)

SCENES=[]
EVENTS={}


def configure_timeline(cues, duration):
 global STARTS, ENDS, SENTENCES, AUDIO_END, END, SCENES, EVENTS
 STARTS=[c['start'] for c in cues]
 ENDS=[c['end'] for c in cues]
 SENTENCES=[c['text'] for c in cues]
 AUDIO_END=duration; END=duration+1.5
 indices=[0,2,5,8,10,12]
 labels=['01 / GİRİŞ','02 / GÜÇ AKIŞI','03 / YAVAŞLATMA','04 / SORU','05 / ISI','06 / SONUÇ']
 boundaries=[0]+[STARTS[i] for i in indices[1:]]+[AUDIO_END]
 SCENES=[(boundaries[i],boundaries[i+1],labels[i]) for i in range(6)]
 EVENTS={
  'generator':STARTS[2]+(ENDS[2]-STARTS[2])*.48,
  'drive':STARTS[3]+(ENDS[3]-STARTS[3])*.065,
  'wheels':STARTS[3]+(ENDS[3]-STARTS[3])*.52,
  'retarding':STARTS[6], 'battery_no':STARTS[9],
 }
 caption_image.cache_clear()


def scene_frame(t):
 im=BG.copy()
 idx=next((i for i,(a,b,l) in enumerate(SCENES) if a<=t<b),5)
 a,b,label=SCENES[idx]; q=t-a; topbar(im,label,t)
 if idx==0:
  heading(im,'D\u0130ZEL M\u0130, ELEKTR\u0130KL\u0130 M\u0130?',['MAZOT YAKIYOR.','ELEKTR\u0130KLE','Y\u00dcR\u00dcYOR.'],[YELLOW,CYAN,CYAN])
  paste_truck(im,10+16*ease(q/1.1),470,.98,t)
  line(im,[(44,836),(654,836)],'#526171',2)
  for k in range(9):
   xx=(k*90-t*40)%740; line(im,[(xx,855),(xx+45,855)],'#344A5E',3)
  rect(im,(51,890,288,936),'#322C21',r=8); text(im,'ENERJ\u0130: D\u0130ZEL',(69,901),22,YELLOW,True)
  rect(im,(308,890,653,936),'#103341',r=8); text(im,'TAHR\u0130K: ELEKTR\u0130K',(329,901),22,CYAN,True)
 elif idx==1:
  heading(im,'CAT 798 AC / BAS\u0130TLE\u015eT\u0130R\u0130LM\u0130\u015e PRENS\u0130P',['ENERJ\u0130 D\u0130ZELDEN.','HAREKET','ELEKTR\u0130KTEN.'],[YELLOW,WHITE,CYAN])
  positions=[(190,525),(500,525),(500,805),(190,805)]
  active=[True,t>EVENTS['generator'],t>EVENTS['drive'],t>EVENTS['wheels']]
  labs=['D\u0130ZEL MOTOR','JENERAT\u00d6R','ELEKTRON\u0130K S\u00dcR\u00dcC\u00dc','TEKERLEK MOTORLARI']
  for k,(x,y) in enumerate(positions):
   col=YELLOW if k==0 else CYAN
   ellipse(im,(x-87,y-87,x+87,y+87),'#101F2D',col if active[k] else LINE,2)
   if k==0: engine_icon(im,x,y,t,col)
   elif k==1: generator_icon(im,x,y,t)
   elif k==2: drive_icon(im,x,y,t)
   else: wheel(im,x,y,51,t,True)
   centered(im,labs[k],y+105,19,col if active[k] else MUTED,True,x)
  if t>EVENTS['generator']: arrow(im,[(280,525),(405,525)],YELLOW,t); centered(im,'MEKAN\u0130K',483,13,YELLOW,True,344)
  if t>EVENTS['drive']: arrow(im,[(500,664),(500,710)],CYAN,t); text(im,'ELEKTR\u0130K',(510,677),12,CYAN,True)
  if t>EVENTS['wheels']: arrow(im,[(402,805),(287,805)],CYAN,t)
 elif idx==2:
  heading(im,'ELEKTR\u0130KL\u0130 YAVA\u015eLATMA',['YOKU\u015e A\u015eA\u011eIDA','AKI\u015e','DE\u011e\u0130\u015e\u0130YOR.'],[WHITE,WHITE,CYAN])
  poly(im,[(0,727),(720,851),(720,885),(0,761)],'#293F50')
  line(im,[(0,727),(720,851)],'#7790A3',3)
  paste_truck(im,10,435,.94,t,-9)
  for k in range(6):
   xx=(k*150-t*70)%820-40; yy=743+xx*124/720; line(im,[(xx,yy),(xx+68,yy+12)],'#6A7984',3)
  if t>EVENTS['retarding']:
   arrow(im,[(165,758),(165,866),(411,866)],CYAN,t)
   generator_icon(im,510,868,t)
  centered(im,'HAREKET  \u2192  ELEKTR\u0130K',936,27,CYAN,True)
 elif idx==3:
  heading(im,'\u00dcRET\u0130LEN ELEKTR\u0130\u011eE NE OLUYOR?',['BATARYAYA','MI G\u0130D\u0130YOR?'],[WHITE,CYAN])
  battery_icon(im,347,608)
  centered(im,'\u00c7EK\u0130\u015e BATARYASI',713,20,MUTED,True)
  if t<EVENTS['battery_no']:
   centered(im,'?',796,114,CYAN,True)
  else:
   line(im,[(227,521),(474,693)],ORANGE,9)
   centered(im,'BU D\u00dcZENDE HAYIR.',820,37,ORANGE,True)
 elif idx==4:
  heading(im,'FREN D\u0130REN\u00c7LER\u0130 VE SO\u011eUTMA',['ELEKTR\u0130K,','ISIYA D\u00d6N\u00dc\u015e\u00dcR.'],[CYAN,ORANGE])
  arrow(im,[(81,441),(196,441),(196,527)],CYAN,t)
  text(im,'ELEKTR\u0130K',(84,409),18,CYAN,True)
  rect(im,(89,540,302,809),'#282930','#795E4B',2,13)
  for x in [106,285]:
   for y in [558,790]: ellipse(im,(x-4,y-4,x+4,y+4),'#A88B75')
  pts=[(196,541),(196,561)]
  for k in range(10): pts.append((143 if k%2==0 else 247,574+k*20))
  pts.extend([(196,774),(196,807)])
  line(im,pts,'#642F26',16); line(im,pts,ORANGE,6)
  centered(im,'D\u0130REN\u00c7 GRUBU',837,19,ORANGE,True,197)
  # Fan: schematic airflow, not an OEM assembly drawing.
  cx,cy=475,674
  ellipse(im,(cx-90,cy-90,cx+90,cy+90),'#152B3A','#648499',3)
  for k in range(5):
   ang=t*5+k*math.tau/5
   p=[]
   for rr,aa in [(15,0),(70,-.25),(78,.17),(42,.65)]: p.append((cx+rr*math.cos(ang+aa),cy+rr*math.sin(ang+aa)))
   poly(im,p,'#93B6C7','#D0E1E8',1)
  ellipse(im,(cx-18,cy-18,cx+18,cy+18),'#D6E4EA')
  for k in range(4):
   pts=[]
   for j in range(45):
    x=311+j*2.0; y=589+k*49+6*math.sin(j*.19-t*5+k)
    pts.append((x,y))
   line(im,pts,ORANGE,2)
  for k in range(3):
   arrow(im,[(575,624+k*50),(642,624+k*50)],ORANGE,t,2)
  centered(im,'FAN',837,19,MUTED,True,476)
  centered(im,'HAREKET  \u2192  ELEKTR\u0130K  \u2192  ISI',905,26,ORANGE,True)
  centered(im,'Servis ve park frenleri ayr\u0131ca bulunur.',951,17,MUTED)
 else:
  heading(im,'ASLINDA \u0130K\u0130 AYRI KAVRAM',['ELEKTR\u0130KL\u0130','Y\u00dcR\u00dcY\u00dc\u015e'],[CYAN,CYAN])
  centered(im,'\u2260',418,148,YELLOW,True)
  centered(im,'BATARYALI',637,63,WHITE,True)
  centered(im,'ARA\u00c7',718,63,WHITE,True)
  rect(im,(82,848,621,908),'#15303C',outline='#305B6E',r=12)
  centered(im,'ENERJ\u0130 KAYNA\u011eI  /  TAHR\u0130K S\u0130STEM\u0130',867,21,CYAN,True)
 captions(im,t)
 text(im,'Temsili teknik animasyon',(48,1171),14,MUTED)
 text(im,'Kaynak: Caterpillar 798 AC',(650,1171),14,MUTED,False,'ra')
 return im

ICON=Image.open(ROOT.parent/'assets/site-icon.png').convert('RGBA')
LOCKUP=Image.new('RGBA',(W,round(390*S)),(0,0,0,0))
LOCKUP.alpha_composite(ICON,(round((720-112)/2*S),round(20*S)))
full=width('algo',80,True)+width('Team',80,True)
x=360-full/2
text(LOCKUP,'algo',(x,153),80,WHITE,True); text(LOCKUP,'Team',(x+width('algo',80,True),153),80,'#68C4FF',True)
centered(LOCKUP,'Engineering Tools & Insights',274,28,WHITE,False,360)

def outro(t):
 im=OUTBG.copy(); u=ease((t-AUDIO_END)/.35); scale=.70+.30*u
 tile=LOCKUP.resize((round(LOCKUP.width*scale),round(LOCKUP.height*scale)),Image.Resampling.LANCZOS)
 tile=tile.rotate(13*(1-u),resample=Image.Resampling.BICUBIC,expand=True)
 im.alpha_composite(tile,((W-tile.width)//2,round(640*S)-tile.height//2))
 return im

def frame(t):
 if t>=AUDIO_END: return outro(t)
 im=scene_frame(t)
 # Tiny transition dip only between sections, never a long fade-in.
 for a,_,_ in SCENES[1:]:
  dt=abs(t-a)
  if dt<.10:
   darkness=(1-dt/.1)*.32
   ov=Image.new('RGBA',im.size,(4,10,16,round(255*darkness))); im=Image.alpha_composite(im,ov)
 return im

