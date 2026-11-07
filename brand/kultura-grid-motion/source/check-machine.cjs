const sharp=require(process.env.KULTURA_SHARP||'sharp');
const path=require('path'),assert=require('assert');
const f=require('./grid.cjs');
const glyphs=svg=>[...svg.matchAll(/<path[^>]*transform="translate\(([-\d.]+) ([-\d.]+)\) scale\(([-\d.]+) ([-\d.]+)\)"/g)].filter(m=>+m[2]===580);
(async()=>{
 let checked=0;
 for(let j=0;j<732;j++)for(const m of glyphs(f.film(j/60))){
  const cell=(+m[1]-600)/62.4;
  assert(Math.abs(cell-Math.round(cell))<1e-5,'Glyph left its fixed cell');
  assert(+m[3]===.104&&+m[4]===-.104,'Wordmark font size changed');checked++;
 }
 for(let count=0;count<=8;count++){
  const t=f.LANDINGS.research-f.SUFFIX_TIME.research+count*.16+.001;
  assert.equal(glyphs(f.film(t)).filter(m=>+m[1]>=1099).length,count,'Research did not type one letter at a time');
 }
 for(const [k,t] of Object.entries(f.LANDINGS))assert.equal(f.film(t),f.film(t+.2),k+' moves after landing');
 for(const k of ['family','os','pulse','research']){
  const dir=path.join(__dirname,'frames',k);
  const first=await sharp(path.join(dir,'00000.png')).raw().toBuffer();
  const last=await sharp(path.join(dir,'end.png')).raw().toBuffer();
  assert(first.equals(last),k+' loop seam');
  const meta=await sharp(path.join(__dirname,'outputs','kultura-'+k+'-grid.gif'),{animated:true}).metadata();
  assert.equal(meta.delay.reduce((a,b)=>a+b,0),k==='family'?18400:8000);
  assert.equal(meta.loop,0);
 }
 console.log(checked+' glyph positions verified: fixed cells, identical size.');
 console.log('Research types 0 through 8 letters in order. All four loops and landing holds verified.');
})().catch(e=>{console.error(e);process.exit(1)});
