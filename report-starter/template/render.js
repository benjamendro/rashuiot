/* =================================================================
   Renderer — builds the report DOM from window.REPORT (content.js).
   Authors never edit this file; they edit content.js only.
   ================================================================= */
(function(){
  const R = window.REPORT;
  const app = document.getElementById('app');
  const esc = s => s==null?'':String(s);
  const kicker = t => t?`<p class="kicker"><span class="mk"><i></i><i></i><i></i><i></i></span>${t}</p>`:'';
  const paras = arr => (arr||[]).map(p=>`<p>${p}</p>`).join('');

  /* ---- mosaic decoration (brand motif) ---- */
  function mosaicSVG(){
    const cols=['var(--c-skyhi)','var(--c-sky)','var(--c-cyan)','var(--c-blue)','var(--c-bluedeep)','var(--c-tealblk)','var(--c-gold)','var(--c-magenta)','var(--c-lime)','var(--c-ice)'];
    // fixed pattern resembling the logo's pixel speech-bubble
    const cells=[
      [4,0,5],[5,0,6],          // top detached squares
      [0,1,0],[1,1,1],[2,1,7],[3,1,4],[5,1,3],
      [0,2,9],[1,2,2],[2,2,0],[3,2,3],[4,2,4],
      [0,3,1],[1,3,0],[2,3,8],[3,3,2],
      [0,4,2],[1,4,4],[2,4,3],
      [0,5,0],[1,5,2]
    ];
    const u=34, g=4, W=6*u, H=7*u;
    let r='';
    cells.forEach(([cx,cy,c])=>{ r+=`<rect x="${cx*(u)}" y="${cy*(u)}" width="${u-g}" height="${u-g}" rx="3" fill="${cols[c]}"/>`; });
    return `<svg class="hero-mosaic" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" aria-hidden="true">${r}</svg>`;
  }

  /* ---- topbar + hero ---- */
  function buildHead(){
    document.getElementById('logo').src = R.brand.logo;
    document.getElementById('logo').alt = R.brand.name;
    document.getElementById('topnav').innerHTML = R.nav.map(n=>`<a href="#${n.id}">${n.label}</a>`).join('');

    const h=R.hero;
    document.getElementById('hero').innerHTML = `
      <div class="wrap">
        ${mosaicSVG()}
        <div class="hero-meta">${h.meta.map(m=>`<span>${m}</span>`).join('')}</div>
        <h1>${h.title} <em>${h.titleAccent}</em></h1>
        <p class="hero-sub">${h.sub}</p>
        <div class="hero-foot">
          <span class="scrollcue"><span class="dot"></span>גללו להתחלה</span>
          ${h.foot.map(f=>`<span class="scrollcue" style="opacity:.7">${f}</span>`).join('')}
        </div>
      </div>`;
  }

  /* ---- a chart figure (optionally with side narrative) ---- */
  let chartSeq=0;
  function figure(spec){
    const id='chart-'+(chartSeq++);
    const fig = `<div class="figure reveal">
        <div class="fig-head"><div>
          <div class="fig-title">${esc(spec.title)}</div>
          ${spec.sub?`<div class="fig-sub">${spec.sub}</div>`:''}
        </div></div>
        <div class="chart" id="${id}"></div>
        ${spec.legend?`<div class="legend">${spec.legend}</div>`:''}
        ${spec.source?`<div class="fig-src">${spec.source}</div>`:''}
      </div>`;
    return {id, fig, spec};
  }
  function legendFromSeries(series){
    return series.map(s=>`<span class="item"><span class="sw" style="background:${s.color}"></span>${s.name}</span>`).join('');
  }

  /* ---- section builders by kind ---- */
  const build = {
    rich(s){
      return `<div class="wrap"><div class="measure">
        ${kicker(s.kicker)}
        ${s.title?`<h2 class="reveal">${s.title}</h2>`:''}
        ${s.lede?`<p class="lede reveal d1" style="margin-top:22px">${s.lede}</p>`:''}
        ${s.body?`<div class="body-col reveal d1" style="margin-top:24px">${paras(s.body)}</div>`:''}
      </div></div>`;
    },
    kpis(s){
      const cards = s.items.map(k=>{
        const dec=(String(k.value).split('.')[1]||'').length;
        return `<div class="kpi"><div class="num"><span class="cnt" data-v="${k.value}" data-dec="${dec}">0</span>${k.unit?`<span class="unit">${k.unit}</span>`:''}</div>
          <div class="lab">${k.label}</div>${k.note?`<div class="note">${k.note}</div>`:''}</div>`;
      }).join('');
      return `<div class="wrap">
        <div class="measure">${kicker(s.kicker)}${s.title?`<h2 class="reveal">${s.title}</h2>`:''}</div>
        <div class="kpi-grid reveal d1" style="margin-top:40px">${cards}</div>
        ${s.note?`<p class="reveal d2" style="margin-top:22px;font-size:14px;color:var(--ink-3)">${s.note}</p>`:''}
      </div>`;
    },
    chart(s){
      if(s.series && !s.legend) s.legend = legendFromSeries(s.series);
      const f = figure(s);
      pending.push(f);
      let inner;
      if(s.split){
        const nv = `<div class="body-col reveal d1">
          ${s.split.title?`<h3 style="margin-bottom:14px">${s.split.title}</h3>`:''}
          ${s.split.body?`<p>${s.split.body}</p>`:''}
          ${s.split.pull?`<div class="pull" style="margin-top:22px"><div class="big">${s.split.pull.big}</div><div class="txt">${s.split.pull.txt}</div></div>`:''}
        </div>`;
        inner = `<div class="split s-wide-end">${nv}${f.fig}</div>`;
      } else {
        inner = `<div style="max-width:920px;margin:0 auto">${f.fig}</div>`;
      }
      return `<div class="wrap">
        ${(s.kicker||s.heading)?`<div class="measure" style="margin-bottom:32px">${kicker(s.kicker)}${s.heading?`<h2 class="reveal">${s.heading}</h2>`:''}</div>`:''}
        ${inner}
      </div>`;
    },
    pull(s){
      return `<div class="wrap"><div class="measure">${kicker(s.kicker)}
        <div class="pull reveal d1"><div class="big">${s.big}</div><div class="txt">${s.txt}</div></div>
      </div></div>`;
    },
    flow(s){
      const steps=s.steps.map(st=>`<div class="step"><div class="n">${st.n}</div><h4>${st.title}</h4><p>${st.body}</p>
        ${st.tools?`<div class="tools">${st.tools.map(t=>`<span class="chip">${t}</span>`).join('')}</div>`:''}</div>`).join('');
      return `<div class="wrap"><div class="measure">${kicker(s.kicker)}${s.title?`<h2 class="reveal">${s.title}</h2>`:''}
        ${s.lede?`<p class="lede reveal d1" style="margin-top:22px">${s.lede}</p>`:''}</div>
        <div class="flow reveal d1" style="margin-top:40px">${steps}</div></div>`;
    },
    sources(s){
      const head=s.cols.map(c=>`<th>${c}</th>`).join('');
      const q={high:'גבוהה',med:'בינונית',low:'מוגבלת'};
      const rows=s.rows.map(r=>`<tr><td><span class="nm">${r.nm}</span></td><td>${r.scope}</td><td>${r.period}</td>
        <td><span class="badge ${r.quality}">${q[r.quality]||r.quality}</span></td><td>${r.notes}</td></tr>`).join('');
      return `<div class="wrap"><div class="measure">${kicker(s.kicker)}${s.title?`<h2 class="reveal">${s.title}</h2>`:''}</div>
        <div class="figure reveal d1" style="margin-top:32px;padding:24px 24px 10px"><div style="overflow-x:auto">
        <table class="src-table"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div></div></div>`;
    },
    recs(s){
      const cards=s.items.map(r=>`<div class="rec"><div class="rn">${r.tag}</div><h4>${r.title}</h4><p>${r.body}</p></div>`).join('');
      return `<div class="wrap"><div class="measure">${kicker(s.kicker)}${s.title?`<h2 class="reveal">${s.title}</h2>`:''}
        ${s.lede?`<p class="lede reveal d1" style="margin-top:22px">${s.lede}</p>`:''}</div>
        <div class="rec-grid reveal d1" style="margin-top:40px">${cards}</div></div>`;
    },
    limits(s){
      const items=s.items.map(l=>`<div class="limit"><span class="mk">${l.mk}</span><p>${l.html}</p></div>`).join('');
      return `<div class="wrap"><div class="measure" style="margin-bottom:34px">${kicker(s.kicker)}${s.title?`<h2 class="reveal">${s.title}</h2>`:''}</div>
        <div class="limits reveal d1">${items}</div></div>`;
    },
    event(s){
      const ag=s.agenda.map(a=>`<div class="ag-row"><span class="t">${a.t}</span><span>${a.txt}</span></div>`).join('');
      return `<div class="wrap"><div class="measure" style="margin-bottom:34px">${kicker(s.kicker)}
        <h2 class="reveal">${s.title}</h2>${s.sub?`<p class="lede reveal d1" style="margin-top:18px">${s.sub}</p>`:''}</div>
        <div class="event reveal d1">
          <div class="date"><div class="d">${s.date.d}</div><div class="m">${s.date.m}</div><div class="m" style="opacity:.85;font-weight:500">${s.date.dow}</div></div>
          <div class="agenda">${ag}</div>
        </div>
        ${s.contact?`<p class="reveal d2" style="margin-top:26px;font-family:var(--font-head);font-weight:700;font-size:18px">${s.contact}</p>`:''}
      </div>`;
    }
  };

  const CHART_KINDS=['barColumns','barRanked','grouped','donut','line'];
  const pending=[]; // {id, fig, spec}

  function buildSections(){
    let html='';
    R.sections.forEach((s,i)=>{
      const bandClass = s.band==='dark'?'band-dark':s.band==='alt'?'band-alt':'';
      let inner;
      if(CHART_KINDS.includes(s.kind)){ inner = build.chart(s); }
      else if(build[s.kind]){ inner = build[s.kind](s); }
      else { inner = build.rich(s); }
      html += `<section id="${s.id}" class="section-pad ${bandClass}">${inner}</section>`;
      // light divider between two plain (no-band) sections
      const next=R.sections[i+1];
      if(next && !s.band && !next.band) html += `<hr class="divider">`;
    });
    app.innerHTML = html;

    // now draw charts into their containers
    pending.forEach(({id,spec})=>{
      const host=document.getElementById(id); if(!host)return;
      if(spec.kind==='line') RC.line(host, {x:spec.x, values:spec.values, unit:spec.unit, color:spec.color});
      else RC[spec.kind](host, spec);
    });
  }

  function buildFooter(){
    document.getElementById('footer').innerHTML = `
      <hr class="divider" style="background:color-mix(in srgb,var(--band) 70%,#fff);margin-bottom:46px">
      <div class="wrap">
        <div><div class="sig">${R.footer.sig}</div></div>
        <div class="meta">${R.footer.meta.map(m=>`${m}`).join('<br>')}</div>
      </div>`;
  }

  function boot(){
    document.documentElement.setAttribute('data-theme', R.theme||'mosaic');
    document.title = R.brand.name + ' · ' + R.hero.title;
    buildHead(); buildSections(); buildFooter();
    RC.start();
    window.dispatchEvent(new Event('report:ready'));
  }
  if(document.readyState!=='loading') boot(); else document.addEventListener('DOMContentLoaded',boot);
})();
