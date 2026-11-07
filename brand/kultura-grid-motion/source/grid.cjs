const fs=require('fs'),path=require('path');
const font=JSON.parse(fs.readFileSync(path.join(__dirname,'assets/glyphs.json'),'utf8'));
const O='#FF4B0A',DURATION=18.4;
const clamp=p=>Math.max(0,Math.min(1,p)),p=(t,a,d)=>clamp((t-a)/d),lerp=(a,b,v)=>a+(b-a)*v,N=v=>+v.toFixed(4);
// A short acceleration ramp, constant-speed travel, and controlled braking.
// No overshoot, springs, sine drift, or scale animation.
function rail(q){q=clamp(q);const r=.22;return q<r?q*q/(2*r*(1-r)):q>1-r?1-(1-q)**2/(2*r*(1-r)):(q-r/2)/(1-r);}
const rect=(x,y,w,h,c,r=0,stroke='none',sw=0)=>w>0&&h>0?`<rect x="${N(x)}" y="${N(y)}" width="${N(w)}" height="${N(h)}" rx="${r}" fill="${c}" stroke="${stroke}" stroke-width="${sw}"/>`:'';
const group=(s,x=0,y=0,z=1)=>`<g transform="translate(${N(x)} ${N(y)}) scale(${N(z)})">${s}</g>`;
const alpha=(s,a)=>`<g opacity="${N(clamp(a))}">${s}</g>`;
const TYPE_STEP=.16;
const SUFFIX_TIME={os:2*TYPE_STEP,pulse:5*TYPE_STEP,research:8*TYPE_STEP};
const MARK_TIME={os:.58,pulse:1.00,research:1.28};
const LANDINGS={os:1.90,pulse:5.68,research:9.96,final:14.76};
const onset=(k,land)=>land-MARK_TIME[k];
const mask=(id,x,y,w,h,s)=>`<defs><clipPath id="${id}">${rect(x,y,w,h,'white')}</clipPath></defs><g clip-path="url(#${id})">${s}</g>`;
function glyph(c,x,y,size,color){const g=font.glyphs[c];return g?`<path d="${g.path}" fill="${color}" transform="translate(${N(x)} ${N(y)}) scale(${N(size/font.units)} ${N(-size/font.units)})"/>`:'';}
function run(str,x,y,size,c){return [...str].map((v,i)=>glyph(v,x+i*size*.6,y,size,c)).join('');}
function prefix(x,y,size,c,t,start,id){
 const age=t-start;if(age<0)return '';
 // Atomic terminal states: glyphs never translate, scale, fade or clip.
 const count=age>=.70-1e-7?7:age>=.42-1e-7?4:age>=.18-1e-7?2:0;
 return run('kultura'.slice(0,count),x,y,size,c);
}
function suffix(str,x,y,size,c,t,start,end=99,id='suffix'){
 if(t<start||t>=end+.28)return '';
 const typing=t<end;
 const count=typing?Math.min(str.length,Math.floor((t-start+1e-7)/TYPE_STEP)):Math.max(0,str.length-Math.floor((t-end+1e-7)/.28*str.length));
 return run(str.slice(0,count),x,y,size,c);
}
function dot(x,y,size,on=true){return on?rect(x+size*.21,y-size*.18,size*.18,size*.18,O):'';}
function wordmark(k,x,y,size,c,t,start,land,id){
 return prefix(x,y,size,c,t,start,id)+dot(x+7*.6*size,y,size,t>=start+.70)+suffix(k,x+8*.6*size,y,size,c,t,land-SUFFIX_TIME[k],99,id+'suffix');
}
function os(t,c,id){
 let s='';
 const k=run('k',82,300,265,c);
 const a=rail(p(t,0,.52));
 if(a>0)s+=mask(id+'k',70,85,178*a,220,group(k,24*(1-a),0));
 if(t>=.58)s+=rect(264,266,34,34,O);
 return s;
}
function pulse(t,c){
 let s=t>=0?rect(174,174,52,52,O,10):'';
 for(let i=0;i<3;i++){
  const onset=.22+i*.22;if(t<onset)continue;
  const w=[110,186,266][i],sw=[16,10,6][i];
  // Complete rigid contours settle in place; avoid clipped side fragments.
  const a=rail(p(t,onset,.34));
  s+=`<g opacity="${N(a)}">${rect(200-w/2,200-w/2,w,w,'none',N(w*.18),c,sw)}</g>`;
 }return s;
}
function research(t,c){
 let s='';const b=85,z=230,sw=19;
 const a=[0,.10,.20,.30].map(v=>rail(p(t,v,.24)));
 s+=rect(b-sw/2,b-sw/2,z*a[0]+sw,sw,c);
 s+=rect(b+z-sw/2,b-sw/2,sw,z*a[1]+sw,c);
 s+=rect(b+z-(z+sw)*a[2]+sw/2,b+z-sw/2,(z+sw)*a[2],sw,c);
 s+=rect(b-sw/2,b+z-(z+sw)*a[3]+sw/2,sw,(z+sw)*a[3],c);
 for(let i=0;i<3;i++){
  const a=rail(p(t,.48+i*.18,.44)),h=[64,99,139][i]*a;
  s+=rect(114+i*59,281-h,36,h,i===2?O:c);
 }return s;
}
function mark(k,t,c,id='mark'){return k==='os'?os(t,c,id):k==='pulse'?pulse(t,c):research(t,c);}
function place(s,cx,cy,z){return group(group(s,-200,-200),cx,cy,z);}
function hero(t){
 let s=rect(0,0,1920,1080,'black');
 const x=600,y=580,size=104,periodX=x+7*.6*size;
 if(t<.70){
  const q=rail(p(t,.20,.50));
  const x1=lerp(960,periodX+size*.3,q),y1=lerp(540,y-size*.09,q);
  const w=lerp(40,size*.18,q);s+=rect(x1-w/2,y1-w/2,w,w,O);
 }else{
  s+=dot(periodX,y,size);
 }
 s+=prefix(x,y,size,'white',t,.58,'hero');
 const sx=x+8*.6*size;
 s+=suffix('os',sx,y,size,'white',t,LANDINGS.os-SUFFIX_TIME.os,4.30,'os-suffix');
 s+=suffix('pulse',sx,y,size,'white',t,LANDINGS.pulse-SUFFIX_TIME.pulse,8.30,'pulse-suffix');
 s+=suffix('research',sx,y,size,'white',t,LANDINGS.research-SUFFIX_TIME.research,99,'research-suffix');
 const k=t<4.68?'os':t<8.68?'pulse':'research',begin=onset(k,LANDINGS[k]);
 let m=t<begin?'':place(mark(k,t-begin,'white','hero-mark'),320,532,1.12);
 const exitAt=k==='os'?4.30:k==='pulse'?8.30:99;
 if(t>exitAt){const e=rail(p(t,exitAt,.28));m=alpha(group(m,18*e,0),1-p(t,exitAt+.20,.08));}
 s+=m;
 return s;
}
function finale(t){
 let s=rect(0,0,1920,1080,'white');
 for(const [i,k] of ['os','pulse','research'].entries()){
  const cx=320+i*640,start=onset(k,LANDINGS.final);
  if(t>=start)s+=place(mark(k,t-start,'black','final-'+k),cx,445,.95);
  const size=48,x=cx-('kultura.'+k).length*size*.6/2;
  s+=wordmark(k,x,710,size,'black',t,12.78,LANDINGS.final,'finaltext'+k);
 }
 return s;
}
function film(t){
 t=Math.max(0,Math.min(DURATION,t));let s;
 if(t<12.2)s=hero(t);
 else if(t<12.8){
  const edge=1920*rail(p(t,12.2,.6));
  s=hero(t)+mask('final-wipe',0,0,edge,1080,finale(t))+rect(edge-16,0,16,1080,O);
 }else s=finale(t);
 if(t>=17.05){
  const edge=1920*rail(p(t,17.05,.65));
  s+=rect(0,0,edge,1080,'black');
  if(edge>980)s+=rect(940,520,40,40,O);
 }
 if(t>=17.70)s=rect(0,0,1920,1080,'black')+rect(940,520,40,40,O);
 return `<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">${s}</svg>`;
}
// theme: 'dark' — как утверждено (чёрный фон, белые знак и буквы); 'light' — светлая версия для
// аватарок ботов (решение владельца 2026-11-07): белый фон, чёрные знак и буквы, затемнение конца
// цикла уходит в белый. Оранжевый, тайминги и геометрия — те же.
function individual(k,t,theme='dark'){
 const bg=theme==='light'?'white':'black',ink=theme==='light'?'black':'white';
 let s=rect(0,0,600,600,bg);
 if(t<.35||t>=7.56)s+=rect(285,285,30,30,O);
 if(t>=.35&&t<7.56){
  const z=.94,land=2.48,begin=onset(k,land);
  if(t>=begin)s+=place(mark(k,t-begin,ink,'individual-'+k),300,240,z);
  const size=k==='research'?43:48,x=300-('kultura.'+k).length*size*.6/2;
  s+=wordmark(k,x,487,size,ink,t,.35,land,'individual-text');
  if(t>=7.0)s+=rect(0,0,600*rail(p(t,7.0,.5)),600,bg);
 }
 return `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600" viewBox="0 0 600 600">${s}</svg>`;
}
module.exports={film,individual,DURATION,font,LANDINGS,SUFFIX_TIME,MARK_TIME};
