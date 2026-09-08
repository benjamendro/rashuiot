/* =================================================================
   Chart engine (RTL-aware) + scroll FX + counters + tooltip + nav
   Exposes window.RC used by render.js. No external libraries.
   ================================================================= */
(function(){
  const NS="http://www.w3.org/2000/svg";
  const S=(t,a)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
  const series=i=>`var(--s${(i%7)+1})`;

  /* tooltip */
  const tip=document.createElement('div'); tip.className='tip'; document.body.appendChild(tip);
  const showTip=h=>{tip.innerHTML=h;tip.classList.add('show');};
  const hideTip=()=>tip.classList.remove('show');
  function moveTip(e){const p=14,w=tip.offsetWidth,h=tip.offsetHeight;let x=e.clientX+p,y=e.clientY+p;
    if(x+w>innerWidth-8)x=e.clientX-w-p; if(y+h>innerHeight-8)y=e.clientY-h-p; tip.style.left=x+'px';tip.style.top=y+'px';}
  function hover(node, html){
    node.addEventListener('mouseenter',e=>{showTip(html);moveTip(e);node.style.filter='brightness(1.08)';});
    node.addEventListener('mousemove',moveTip);
    node.addEventListener('mouseleave',()=>{hideTip();node.style.filter='';});
  }

  /* scroll-trigger registry */
  const players=[];
  const register=(el,fn)=>players.push([el,fn]);

  /* counters */
  function countUp(el){
    const t=parseFloat(el.dataset.v), dec=+el.dataset.dec||0, dur=1400, t0=performance.now();
    (function step(now){let p=Math.min(1,(now-t0)/dur);p=1-Math.pow(1-p,3);
      const cur=t*p; el.textContent=dec?cur.toFixed(dec):Math.round(cur).toLocaleString('en-US');
      if(p<1)requestAnimationFrame(step);})(performance.now());
  }

  /* ---------- vertical columns ---------- */
  function barColumns(host, spec){
    const d=spec.data, W=720,H=320, m={t:38,r:20,b:58,l:20}, iw=W-m.l-m.r, ih=H-m.t-m.b;
    const max=Math.max(...d.map(x=>x.value))*1.15;
    const n=d.length, step=iw/n, bw=Math.min(86, step*0.56);
    const svg=S('svg',{viewBox:`0 0 ${W} ${H}`}); host.appendChild(svg);
    const base=m.t+ih;
    svg.appendChild(S('line',{x1:m.l,x2:W-m.r,y1:base,y2:base,class:'grid-line'}));
    const bars=[];
    d.forEach((x,i)=>{
      // RTL: first category on the right
      const cx=W-m.r-(i+0.5)*step;
      const bh=x.value/max*ih;
      const rect=S('rect',{x:cx-bw/2,y:base,width:bw,height:0,rx:5,fill:series(i),style:'cursor:pointer'});
      rect.dataset.h=bh; rect.dataset.y=base-bh;
      hover(rect,`<span class="t-key">${x.label}</span><div class="t-row"><span>ערך</span><span>${x.value}${spec.unit||''}</span></div>`);
      svg.appendChild(rect); bars.push(rect);
      const vl=S('text',{x:cx,y:base-bh-12,'text-anchor':'middle',class:'val-label'}); vl.textContent=x.value+(spec.unit||''); vl.style.fontSize='17px'; vl.style.fontWeight='800'; vl.style.fill='var(--ink)'; vl.style.direction='ltr'; vl.style.opacity=0; svg.appendChild(vl); bars.push(vl);
      const cl=S('text',{x:cx,y:base+30,'text-anchor':'middle',class:'ax-label'}); cl.textContent=x.label; cl.style.fontSize='16px'; cl.style.fontWeight='700'; cl.style.fill='var(--ink-2)'; svg.appendChild(cl);
    });
    register(host,()=>bars.forEach((b,i)=>{ if(b.tagName==='rect'){ b.style.transition=`height .8s cubic-bezier(.2,.7,.2,1) ${i*0.04}s, y .8s cubic-bezier(.2,.7,.2,1) ${i*0.04}s`; b.setAttribute('height',b.dataset.h); b.setAttribute('y',b.dataset.y);} else { b.style.transition=`opacity .5s ease ${0.4+i*0.04}s`; b.style.opacity=1; } }));
  }

  /* ---------- horizontal ranked bars (label on its own line, above each bar) ---------- */
  function barRanked(host, spec){
    const d=spec.data, W=720, rowH=66, top=6, H=top*2+d.length*rowH;
    const max=Math.max(...d.map(x=>x.value))*1.16;        // left headroom for the value text
    const svg=S('svg',{viewBox:`0 0 ${W} ${H}`}); host.appendChild(svg);
    const bars=[];
    d.forEach((x,i)=>{
      const rTop=top+i*rowH;
      // category label — full width, flush right, RTL-correct
      const lab=S('text',{x:W,y:rTop+18,'text-anchor':'start',class:'val-label',style:'direction:rtl;unicode-bidi:plaintext'});
      lab.textContent=x.label; lab.style.fontWeight='600'; lab.style.fontSize='15px'; lab.style.fill='var(--ink)'; svg.appendChild(lab);
      // bar — grows from the right edge leftward
      const by=rTop+30, bw=x.value/max*W;
      svg.appendChild(S('line',{x1:0,x2:W,y1:by+8,y2:by+8,class:'grid-line'}));
      const rect=S('rect',{x:W,y:by,width:0,height:16,rx:4,fill:series(i),style:'cursor:pointer'}); rect.dataset.w=bw;
      hover(rect,`<span class="t-key">${x.label}</span><div class="t-row"><span>ערך</span><span>${x.value}${spec.unit||''}</span></div>`);
      svg.appendChild(rect); bars.push(rect);
      // value — inside the bar tip when it fits, otherwise just outside it
      const vtxt=x.value+(spec.unit||''); const vIn=bw>(vtxt.length*10+22);
      const vl=S('text',{x:(vIn?W-bw+11:W-bw-9),y:by+13,'text-anchor':(vIn?'start':'end'),class:'val-label'});
      vl.textContent=vtxt; vl.style.fill=(vIn?'#fff':'var(--accent)'); vl.style.fontWeight='800'; vl.style.fontSize='14px'; vl.style.direction='ltr'; vl.style.opacity=0; svg.appendChild(vl); bars.push(vl);
    });
    register(host,()=>bars.forEach((b,i)=>{ if(b.tagName==='rect'){ const w=+b.dataset.w; b.style.transition=`width .9s cubic-bezier(.2,.7,.2,1) ${(i/2)*0.06}s, x .9s cubic-bezier(.2,.7,.2,1) ${(i/2)*0.06}s`; b.setAttribute('width',w); b.setAttribute('x', W-w); } else { b.style.transition=`opacity .5s ease ${0.5+(i/2)*0.06}s`; b.style.opacity=1; } }));
  }

  /* ---------- grouped (two series) — label on top, bars stacked beneath ---------- */
  function grouped(host, spec){
    const d=spec.data, ser=spec.series, W=720, rowH=94, top=6, H=top*2+d.length*rowH;
    const max=Math.max(...d.flatMap(x=>x.values))*1.14;
    const svg=S('svg',{viewBox:`0 0 ${W} ${H}`}); host.appendChild(svg);
    const bars=[];
    d.forEach((x,i)=>{
      const rTop=top+i*rowH;
      const lab=S('text',{x:W,y:rTop+18,'text-anchor':'start',class:'val-label',style:'direction:rtl;unicode-bidi:plaintext'});
      lab.textContent=x.label; lab.style.fontWeight='700'; lab.style.fontSize='15px'; lab.style.fill='var(--ink)'; svg.appendChild(lab);
      x.values.forEach((v,si)=>{
        const by=rTop+28+si*24, bw=v/max*W, col=(ser[si]&&ser[si].color)||series(si);
        const rect=S('rect',{x:W,y:by,width:0,height:16,rx:4,fill:col,style:'cursor:pointer'}); rect.dataset.w=bw;
        hover(rect,`<span class="t-key">${x.label} · ${ser[si].name}</span><div class="t-row"><span>ערך</span><span>${v}${spec.unit||''}</span></div>`);
        svg.appendChild(rect); bars.push(rect);
        const vtxt=v+(spec.unit||''); const vIn=bw>(vtxt.length*8.5+18);
        const vl=S('text',{x:(vIn?W-bw+9:W-bw-8),y:by+13,'text-anchor':(vIn?'start':'end'),class:'val-label'}); vl.textContent=vtxt; vl.style.fontSize='12.5px'; vl.style.fontWeight='800'; vl.style.fill=(vIn?'#fff':col); vl.style.direction='ltr'; vl.style.opacity=0; svg.appendChild(vl); bars.push(vl);
      });
    });
    register(host,()=>bars.forEach((b,i)=>{ if(b.tagName==='rect'){ const w=+b.dataset.w; b.style.transition=`width .85s cubic-bezier(.2,.7,.2,1) ${(i/4)*0.07}s, x .85s cubic-bezier(.2,.7,.2,1) ${(i/4)*0.07}s`; b.setAttribute('width',w); b.setAttribute('x', W-w);} else { b.style.transition=`opacity .5s ease ${0.5+(i/4)*0.07}s`; b.style.opacity=1; } }));
  }

  /* ---------- donut ---------- */
  function donut(host, spec){
    const d=spec.data, tot=d.reduce((s,x)=>s+x.value,0);
    const W=320,H=320,cx=160,cy=160,R=116,sw=44,C=2*Math.PI*R;
    const svg=S('svg',{viewBox:`0 0 ${W} ${H}`}); host.appendChild(svg);
    svg.appendChild(S('circle',{cx,cy,r:R,fill:'none',stroke:'var(--paper-2)','stroke-width':sw}));
    let acc=0; const segs=[];
    d.forEach((x,i)=>{
      const seg=S('circle',{cx,cy,r:R,fill:'none',stroke:x.color||series(i),'stroke-width':sw,'stroke-dasharray':`0 ${C}`,'stroke-dashoffset':-acc,transform:`rotate(-90 ${cx} ${cy})`,style:'cursor:pointer'});
      seg.dataset.len=x.value/tot*C;
      hover(seg,`<span class="t-key">${x.label}</span><div class="t-row"><span>חלק</span><span>${x.value}${spec.unit||'%'}</span></div>`);
      svg.appendChild(seg); segs.push(seg); acc+=x.value/tot*C;
    });
    const ct=S('text',{x:cx,y:cy-2,'text-anchor':'middle'}); ct.style.cssText='font-family:var(--font-num);font-weight:800;font-size:32px;fill:var(--ink)'; ct.textContent=d[0].value+(spec.unit||'%'); svg.appendChild(ct);
    const cs=S('text',{x:cx,y:cy+22,'text-anchor':'middle',class:'ax-label'}); cs.textContent=d[0].label; svg.appendChild(cs);
    register(host,()=>segs.forEach((s,i)=>{s.style.transition=`stroke-dasharray .9s cubic-bezier(.2,.7,.2,1) ${i*0.1}s`;s.setAttribute('stroke-dasharray',`${s.dataset.len} ${C}`);}));
  }

  /* ---------- line (RTL: earliest year on the right) ---------- */
  function line(host, spec){
    const W=720,H=320,m={t:24,r:54,b:40,l:24}, iw=W-m.l-m.r, ih=H-m.t-m.b;
    const xs=spec.x, vmin=Math.min(...spec.values), vmax=Math.max(...spec.values);
    const pad=(vmax-vmin)*0.18||1, lo=vmin-pad, hi=vmax+pad;
    const X=i=>m.l+iw-(i/(xs.length-1))*iw;       // reversed for RTL
    const Y=v=>m.t+(1-(v-lo)/(hi-lo))*ih;
    const svg=S('svg',{viewBox:`0 0 ${W} ${H}`}); host.appendChild(svg);
    for(let i=0;i<=4;i++){const v=lo+(hi-lo)*i/4; svg.appendChild(S('line',{x1:m.l,x2:W-m.r,y1:Y(v),y2:Y(v),class:'grid-line'}));
      const t=S('text',{x:W-m.r+8,y:Y(v)+4,'text-anchor':'start',class:'ax-label'}); t.textContent=Math.round(v)+(spec.unit||''); svg.appendChild(t);}
    xs.forEach((lab,i)=>{const t=S('text',{x:X(i),y:H-14,'text-anchor':'middle',class:'ax-label'}); t.textContent=lab; svg.appendChild(t);});
    const pts=spec.values.map((v,i)=>[X(i),Y(v)]);
    const path=S('path',{d:'M'+pts.map(p=>p.join(',')).join('L'),fill:'none',stroke:spec.color||'var(--accent)','stroke-width':2.6,'stroke-linecap':'round','stroke-linejoin':'round'}); svg.appendChild(path);
    const len=path.getTotalLength(); path.style.strokeDasharray=len; path.style.strokeDashoffset=len;
    const dots=pts.map((p,i)=>{const c=S('circle',{cx:p[0],cy:p[1],r:4.5,fill:'#fff',stroke:spec.color||'var(--accent)','stroke-width':2.5,style:'cursor:pointer',opacity:0});
      hover(c,`<span class="t-key">${xs[i]}</span><div class="t-row"><span>ערך</span><span>${spec.values[i]}${spec.unit||''}</span></div>`); svg.appendChild(c); return c;});
    register(host,()=>{path.style.transition='stroke-dashoffset 1.4s cubic-bezier(.2,.7,.2,1)';path.style.strokeDashoffset=0; dots.forEach((c,i)=>{c.style.transition=`opacity .4s ease ${.5+i*0.08}s`;c.style.opacity=1;});});
  }

  /* ---------- observers / nav / progress ---------- */
  function start(){
    const ro=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');ro.unobserve(e.target);}}),{threshold:.14});
    document.querySelectorAll('.reveal').forEach(el=>ro.observe(el));
    document.querySelectorAll('.cnt').forEach(el=>{const o=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){countUp(el);o.unobserve(el);}}),{threshold:.4});o.observe(el);});
    const po=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){const hit=players.find(p=>p[0]===e.target); if(hit){hit[1]();} po.unobserve(e.target);}}),{threshold:.25});
    players.forEach(p=>po.observe(p[0]));

    const prog=document.getElementById('progress'); const links=[...document.querySelectorAll('.topnav a')];
    const targets=links.map(a=>document.querySelector(a.getAttribute('href'))).filter(Boolean);
    function onScroll(){const h=document.documentElement; if(prog)prog.style.width=(h.scrollTop/(h.scrollHeight-h.clientHeight)*100)+'%';
      let cur=null,best=-1e9; links.forEach((a,i)=>{const t=targets[i]; if(!t)return; const r=t.getBoundingClientRect(); if(r.top<=150&&r.top>best){best=r.top;cur=a;}});
      links.forEach(a=>a.classList.toggle('active',a===cur));}
    addEventListener('scroll',onScroll,{passive:true}); onScroll();
  }

  window.RC={ S, series, hover, register, barColumns, barRanked, grouped, donut, line, start };
})();
