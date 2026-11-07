const fs=require('fs'),path=require('path'),{spawnSync}=require('child_process');
const sharp=require('sharp');
const {film,individual,DURATION}=require('./grid.cjs');
const out=path.join(__dirname,'outputs');fs.mkdirSync(out,{recursive:true});
function ff(args){const r=spawnSync('ffmpeg',['-hide_banner','-loglevel','error','-y',...args],{encoding:'utf8',windowsHide:true});if(r.status!==0)throw Error(r.stderr);}
async function render(kind){
 const main=kind==='family',fps=main?60:30,d=main?DURATION:8,n=Math.round(fps*d),dir=path.join(__dirname,'frames',kind);fs.mkdirSync(dir,{recursive:true});
 for(let i=0;i<n;i++){
  const svg=main?film(i/fps):individual(kind,i/fps);
  await sharp(Buffer.from(svg)).png({compressionLevel:1}).toFile(path.join(dir,String(i).padStart(5,'0')+'.png'));
  if(i%180===0)console.log(kind+' '+i+'/'+n);
 }
 await sharp(Buffer.from(main?film(d):individual(kind,d))).png().toFile(path.join(dir,'end.png'));
 const input=path.join(dir,'%05d.png'),stem=path.join(out,'kultura-'+kind+'-grid');
 const filt='fps=25,scale='+(main?'960:540':'512:512')+':flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=full[p];[b][p]paletteuse=dither=bayer:bayer_scale=4';
 ff(['-framerate',String(fps),'-i',input,'-filter_complex',filt,'-loop','0',stem+'.gif']);
 const audio=main?['-i',path.join(__dirname,'sound.wav'),'-c:a','aac','-b:a','192k']:[];
 ff(['-framerate',String(fps),'-i',input,...audio,'-c:v','libx264','-preset','medium','-crf','17','-pix_fmt','yuv420p','-movflags','+faststart','-t',String(d),stem+'.mp4']);
 console.log('EXPORTED '+kind);
}
(async()=>{for(const k of process.argv[2]&&process.argv[2]!=='all'?[process.argv[2]]:['family','os','pulse','research'])await render(k)})().catch(e=>{console.error(e);process.exit(1)});
