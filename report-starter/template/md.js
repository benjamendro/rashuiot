/* =================================================================
   md.js — parses template/content.md (the no-code Markdown format)
   into the window.REPORT object the renderer understands.
   Used by Editor.html (live preview) and can also generate content.js.
   ================================================================= */
(function(){
  const BLOCKS = ['REPORT','HERO','NAV','FOOTER'];

  function splitPipes(s){ return s.split('|').map(x=>x.trim()).filter(x=>x!==''); }
  function tableCells(line){
    let s=line.trim();
    if(s.startsWith('|')) s=s.slice(1);
    if(s.endsWith('|')) s=s.slice(0,-1);
    return s.split('|').map(c=>c.trim());
  }
  function num(v){ const n=parseFloat(String(v).replace(/,/g,'')); return isNaN(n)?v:n; }
  function deepBold(o){
    if(typeof o==='string') return o.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
    if(Array.isArray(o)) return o.map(deepBold);
    if(o && typeof o==='object'){ for(const k in o) o[k]=deepBold(o[k]); return o; }
    return o;
  }

  window.parseReportMD = function(src){
    const R = { brand:{}, theme:'mosaic', nav:[], hero:{}, sections:[], footer:{meta:[]} };
    const lines = src.replace(/\r/g,'').split('\n');
    let ctx=null;          // 'REPORT'|'HERO'|'NAV'|'FOOTER'|'section'
    let sec=null;          // current section
    let arrKey=null;       // collecting "- " items into this key
    let arrTarget=null;    // object that owns arrKey
    let table=null;        // collecting table rows

    const setField=(key,val)=>{
      val = val.trim();
      if(ctx==='REPORT'){
        if(key==='theme') R.theme=val; else R.brand[key]=val;
      } else if(ctx==='HERO'){
        if(key==='meta') R.hero.meta=splitPipes(val);
        else if(key==='accent') R.hero.titleAccent=val;
        else if(key==='foot') R.hero.foot=splitPipes(val);
        else R.hero[key]=val;
      } else if(ctx==='FOOTER'){
        if(key==='sig') R.footer.sig=val;
      } else if(ctx==='section' && sec){
        if(key==='series'){
          sec.series = splitPipes(val).map(p=>{ const m=p.match(/^(.*?)\s*\((.*)\)\s*$/); return m?{name:m[1].trim(),color:m[2].trim()}:{name:p.trim()}; });
        } else if(key==='cols'){ sec.cols=splitPipes(val); }
        else if(key==='date'){ const a=splitPipes(val); sec.date={d:a[0],m:a[1],dow:a[2]}; }
        else if(key.indexOf('.')>0){
          const parts=key.split('.'); let t=sec;
          for(let j=0;j<parts.length-1;j++){ t[parts[j]]=t[parts[j]]||{}; t=t[parts[j]]; }
          t[parts[parts.length-1]]=val;
        }
        else if(key==='x'){ sec.x=splitPipes(val); }
        else if(key==='values'){ sec.values=splitPipes(val).map(num); }
        else sec[key]=val;
      }
    };

    const commitTable=()=>{
      if(!table || table.length<2){ table=null; return; }
      const head=table[0], rows=table.slice(1);
      const byName=(r,n)=>{ const i=head.indexOf(n); return i>=0?r[i]:undefined; };
      if(ctx==='section' && sec){
        const k=sec.kind;
        if(k==='kpis') sec.items=rows.map(r=>({value:num(byName(r,'value')), unit:byName(r,'unit')||'', label:byName(r,'label'), note:byName(r,'note')||''}));
        else if(k==='barRanked'||k==='barColumns') sec.data=rows.map(r=>({label:byName(r,'label'), value:num(byName(r,'value'))}));
        else if(k==='grouped') sec.data=rows.map(r=>({label:r[0], values:r.slice(1).map(num)}));
        else if(k==='donut') sec.data=rows.map(r=>({label:byName(r,'label'), value:num(byName(r,'value')), color:byName(r,'color')}));
        else if(k==='recs') sec.items=rows.map(r=>({tag:byName(r,'tag'), title:byName(r,'title'), body:byName(r,'body')}));
        else if(k==='flow') sec.steps=rows.map(r=>({n:byName(r,'n'), title:byName(r,'title'), body:byName(r,'body'), tools:(byName(r,'tools')||'').split(',').map(s=>s.trim()).filter(Boolean)}));
        else if(k==='sources') sec.rows=rows.map(r=>({nm:byName(r,'nm'), scope:byName(r,'scope'), period:byName(r,'period'), quality:byName(r,'quality'), notes:byName(r,'notes')}));
        else if(k==='limits') sec.items=rows.map(r=>({mk:byName(r,'mk'), html:byName(r,'html')}));
        else if(k==='event') sec.agenda=rows.map(r=>({t:byName(r,'time')||r[0], txt:byName(r,'text')||r[1]}));
      }
      table=null;
    };

    for(let raw of lines){
      const line=raw.replace(/\s{2,}#.*$/,'');     // strip trailing "  # comment"
      const t=line.trim();

      if(t==='' ){ commitTable(); arrKey=null; continue; }

      // table rows
      if(t.startsWith('|')){ (table=table||[]).push(tableCells(t)); continue; }
      else if(table){ commitTable(); }

      // section header:  ## id [kind] {band}
      let mSec=t.match(/^##\s+([^\s\[]+)\s*\[([^\]]+)\]\s*(?:\{([^}]+)\})?/);
      if(mSec){ arrKey=null; sec={ id:mSec[1].trim(), kind:mSec[2].trim() }; if(mSec[3]) sec.band=mSec[3].trim(); R.sections.push(sec); ctx='section'; continue; }

      // block header:  # REPORT / # HERO / # NAV / # FOOTER  (else it's a comment)
      let mBlk=t.match(/^#\s+([A-Z]+)\b/);
      if(t.startsWith('#') && !t.startsWith('##')){
        if(mBlk && BLOCKS.includes(mBlk[1])){ arrKey=null; ctx=mBlk[1]; sec=null; }
        continue;   // comment or block header — nothing else to do
      }

      // NAV lines:  label -> id
      if(ctx==='NAV' && t.includes('->')){ const [lab,id]=t.split('->'); R.nav.push({id:id.trim(), label:lab.trim()}); continue; }

      // array continuation:  - item
      if(t.startsWith('- ')){
        const item=t.slice(2).trim();
        if(arrKey==='footer.meta') R.footer.meta.push(item);
        else if(arrKey && arrTarget) (arrTarget[arrKey]=arrTarget[arrKey]||[]).push(item);
        continue;
      }

      // key: value
      const c=t.indexOf(':');
      if(c>0){
        const key=t.slice(0,c).trim(), val=t.slice(c+1).trim();
        if(val===''){
          // start of an array (body:, meta:, …)
          if(ctx==='FOOTER' && key==='meta'){ arrKey='footer.meta'; R.footer.meta=[]; }
          else if(ctx==='section' && sec){ arrKey=key; arrTarget=sec; sec[key]=[]; }
          else { arrKey=null; }
        } else {
          arrKey=null; setField(key,val);
        }
      }
    }
    commitTable();
    return deepBold(R);
  };

  // Produce a content.js file body from a REPORT object.
  window.reportToJS = function(R){
    return '/* Generated from content.md by the no-code editor. */\n'
         + 'window.REPORT = ' + JSON.stringify(R, null, 2) + ';\n';
  };
})();
