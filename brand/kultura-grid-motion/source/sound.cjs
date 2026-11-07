const fs=require('fs'),path=require('path'),{DURATION,LANDINGS}=require('./grid.cjs');
const RATE=48000,frames=Math.round(RATE*DURATION),mix=new Float64Array(frames*2);
let seed=19087;const rand=()=>{seed=(1664525*seed+1013904223)>>>0;return seed/4294967296*2-1};
function click(time,gain=.13,body=180,pan=0){
 const n=Math.round(.11*RATE),start=Math.round(time*RATE);
 for(let i=0;i<n&&start+i<frames;i++){
  const t=i/RATE,env=Math.min(1,t/.0008);
  const v=env*gain*(rand()*.65*Math.exp(-t/0.005)+Math.sin(2*Math.PI*(body+120*Math.exp(-t/.008))*t)*.55*Math.exp(-t/.025));
  mix[(start+i)*2]+=v*(1-pan*.25);mix[(start+i)*2+1]+=v*(1+pan*.25);
 }
}
// One shared cue at each precise icon + wordmark landing. Holds remain silent.
for(const [k,time] of Object.entries(LANDINGS))click(time,k==='final'?.085:.065,120);
const buf=Buffer.alloc(44+frames*4);buf.write('RIFF',0);buf.writeUInt32LE(buf.length-8,4);buf.write('WAVEfmt ',8);buf.writeUInt32LE(16,16);buf.writeUInt16LE(1,20);buf.writeUInt16LE(2,22);buf.writeUInt32LE(RATE,24);buf.writeUInt32LE(RATE*4,28);buf.writeUInt16LE(4,32);buf.writeUInt16LE(16,34);buf.write('data',36);buf.writeUInt32LE(frames*4,40);
let peak=0;for(let i=0;i<mix.length;i++){peak=Math.max(peak,Math.abs(mix[i]));buf.writeInt16LE(Math.round(Math.max(-1,Math.min(1,mix[i]))*32767),44+i*2)}
fs.writeFileSync(path.join(__dirname,'sound.wav'),buf);console.log('Sound '+DURATION+'s, peak '+peak.toFixed(3));
