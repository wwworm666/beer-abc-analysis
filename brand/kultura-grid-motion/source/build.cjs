const fs=require('fs'),path=require('path');
const root=__dirname,read=p=>fs.readFileSync(path.join(root,p),'utf8');
const source=read('grid.cjs').replace("const fs=require('fs'),path=require('path');",'').replace("const font=JSON.parse(fs.readFileSync(path.join(__dirname,'assets/glyphs.json'),'utf8'));",'const font='+read('assets/glyphs.json')+';').replace('module.exports={film,individual,avatar,AVATAR_SCALE,DURATION,font,LANDINGS,SUFFIX_TIME,MARK_TIME};','window.KulturaMotion={film,individual,avatar,AVATAR_SCALE,DURATION,font,LANDINGS,SUFFIX_TIME,MARK_TIME};');
fs.writeFileSync(path.join(root,'assets/motion.js'),source);
console.log('Browser composition updated');
