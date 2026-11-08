"""Five client-side converter tools for bvtech.org/tools/ (v1.139).

All conversion happens in the visitor's browser — nothing is uploaded — which
matches the "no signup, nothing leaves your device" promise of the tools hub and
is a genuine trust differentiator for an MSP. Each returns the same dict shape
as pages_tools so destination._pages()/all_tools() can ship them unchanged:
Image Converter, CSV ⇄ JSON, Markdown → HTML, Color Converter, Unit Converter.
"""
from __future__ import annotations

from .pages_tools import _wrap

_ROW = ("<style>.tl .row{display:flex;gap:14px;flex-wrap:wrap;margin:0 0 14px}"
        ".tl .row>div{flex:1 1 150px}.tl textarea{width:100%;min-height:150px;padding:13px 15px;"
        "border-radius:10px;border:1px solid var(--border);background:rgba(255,255,255,.04);"
        "color:var(--white);font:0.95rem/1.5 ui-monospace,Menlo,Consolas,monospace;resize:vertical}"
        ".tl .btn.sec{background:transparent;border:1px solid var(--o2);color:var(--o2)}"
        ".tl .btns{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 14px}"
        ".tl .out{white-space:pre-wrap;word-break:break-word}"
        ".tl .ok{color:#7ee081}.tl .err{color:#ff8a8a}</style>")


# ---------------------------------------------------------------- Image Converter
def image_converter():
    body = _wrap(
        "🖼️ Free file tool", "Image Converter — PNG · JPG · WebP",
        "Convert and resize images right in your browser. Nothing is uploaded — your "
        "picture never leaves your device. Great for shrinking photos before email or "
        "turning a PNG into a smaller WebP.",
        _ROW + r"""
<div class="card">
  <label>Choose an image</label>
  <input type="file" id="ic-file" accept="image/*">
  <div class="row" style="margin-top:14px">
    <div><label>Convert to</label><select id="ic-fmt">
      <option value="image/webp">WebP (smallest)</option>
      <option value="image/jpeg">JPG</option>
      <option value="image/png">PNG</option></select></div>
    <div><label>Max width px (optional)</label><input id="ic-w" type="number" min="1" placeholder="e.g. 1200"></div>
  </div>
  <label>Quality (JPG/WebP): <b id="ic-qv">0.90</b></label>
  <input type="range" id="ic-q" min="0.1" max="1" step="0.05" value="0.9" style="width:100%">
  <button class="btn" id="ic-go" disabled style="margin-top:14px">Convert &amp; download ↓</button>
  <p class="muted" id="ic-note" style="margin-top:10px">100% in your browser — your image is never uploaded.</p>
</div>
<div class="card" id="ic-prev" hidden><img id="ic-img" alt="converted preview" style="max-width:100%;border-radius:8px;display:block">
  <p class="muted" id="ic-info" style="margin:10px 0 0"></p></div>
<script>
(function(){
  var file=document.getElementById('ic-file'),fmt=document.getElementById('ic-fmt'),w=document.getElementById('ic-w'),
      q=document.getElementById('ic-q'),qv=document.getElementById('ic-qv'),go=document.getElementById('ic-go'),
      note=document.getElementById('ic-note'),prev=document.getElementById('ic-prev'),img=document.getElementById('ic-img'),
      info=document.getElementById('ic-info'),loaded=null;
  q.addEventListener('input',function(){qv.textContent=parseFloat(q.value).toFixed(2);});
  file.addEventListener('change',function(){
    var f=file.files[0]; if(!f){return;}
    var r=new FileReader();
    r.onload=function(){var i=new Image();i.onload=function(){loaded=i;go.disabled=false;
      note.textContent='Loaded '+i.width+'×'+i.height+' — ready to convert.';};
      i.onerror=function(){note.textContent='That file could not be read as an image.';};i.src=r.result;};
    r.readAsDataURL(f);
  });
  go.addEventListener('click',function(){
    if(!loaded){return;}
    var mw=parseInt(w.value,10),sw=loaded.width,sh=loaded.height;
    if(mw&&mw>0&&sw>mw){sh=Math.round(sh*mw/sw);sw=mw;}
    var cv=document.createElement('canvas');cv.width=sw;cv.height=sh;var ctx=cv.getContext('2d');
    if(fmt.value==='image/jpeg'){ctx.fillStyle='#fff';ctx.fillRect(0,0,sw,sh);}
    ctx.drawImage(loaded,0,0,sw,sh);
    var url=cv.toDataURL(fmt.value,parseFloat(q.value));
    var ext=fmt.value.split('/')[1].replace('jpeg','jpg');
    img.src=url;prev.hidden=false;
    info.textContent=sw+'×'+sh+' · ~'+Math.round((url.length*0.75)/1024)+' KB · '+ext.toUpperCase();
    var a=document.createElement('a');a.href=url;a.download='converted.'+ext;document.body.appendChild(a);a.click();a.remove();
  });
})();
</script>""")
    return dict(slug="image-converter", title="Image Converter (PNG, JPG, WebP) | Free | BVTech",
                desc="Convert and resize images to PNG, JPG or WebP right in your browser — "
                     "nothing uploaded, free, instant. By BVTech.",
                card_title="Image Converter", icon="🖼️",
                card_excerpt="Convert &amp; resize images to PNG, JPG or WebP — in your browser, "
                             "nothing uploaded.",
                body=body)


# ---------------------------------------------------------------- CSV <-> JSON
def csv_json():
    body = _wrap(
        "🔄 Free data tool", "CSV ⇄ JSON Converter",
        "Turn a CSV (from a spreadsheet) into clean JSON, or JSON back into CSV — instantly, "
        "in your browser. Nothing is uploaded. Perfect for quick data wrangling without a script.",
        _ROW + r"""
<div class="card">
  <label>Paste CSV or JSON</label>
  <textarea id="cj-in" placeholder="name,city&#10;Ada,Austin&#10;Linus,Houston"></textarea>
  <div class="btns" style="margin-top:12px">
    <button class="btn" id="cj-tojson">CSV → JSON</button>
    <button class="btn sec" id="cj-tocsv">JSON → CSV</button>
    <button class="btn sec" id="cj-copy">Copy output</button>
  </div>
  <p class="muted" id="cj-msg"></p>
  <textarea id="cj-out" class="out" readonly placeholder="Result appears here…"></textarea>
</div>
<script>
(function(){
  var inp=document.getElementById('cj-in'),out=document.getElementById('cj-out'),msg=document.getElementById('cj-msg');
  function parseCSV(t){
    var rows=[],row=[],cur='',q=false;
    for(var i=0;i<t.length;i++){var c=t[i];
      if(q){ if(c==='"'){ if(t[i+1]==='"'){cur+='"';i++;} else {q=false;} } else {cur+=c;} }
      else { if(c==='"'){q=true;} else if(c===','){row.push(cur);cur='';}
        else if(c==='\n'||c==='\r'){ if(c==='\r'&&t[i+1]==='\n')i++; row.push(cur);rows.push(row);row=[];cur=''; }
        else {cur+=c;} } }
    if(cur!==''||row.length){row.push(cur);rows.push(row);}
    return rows.filter(function(r){return r.length>1||(r[0]||'').trim()!=='';});
  }
  function esc(v){v=String(v==null?'':v); return /[",\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;}
  function show(v,cls){msg.textContent=v;msg.className='muted '+(cls||'');}
  document.getElementById('cj-tojson').addEventListener('click',function(){
    try{var rows=parseCSV(inp.value.trim());if(!rows.length){show('Nothing to convert.','err');return;}
      var head=rows[0],objs=rows.slice(1).map(function(r){var o={};head.forEach(function(h,i){o[h]=r[i]!==undefined?r[i]:'';});return o;});
      out.value=JSON.stringify(objs,null,2);show(objs.length+' row(s) → JSON','ok');}
    catch(e){show('Could not parse that CSV.','err');}
  });
  document.getElementById('cj-tocsv').addEventListener('click',function(){
    try{var data=JSON.parse(inp.value);if(!Array.isArray(data))data=[data];
      var keys=[];data.forEach(function(o){Object.keys(o||{}).forEach(function(k){if(keys.indexOf(k)<0)keys.push(k);});});
      var lines=[keys.map(esc).join(',')];data.forEach(function(o){lines.push(keys.map(function(k){return esc(o?o[k]:'');}).join(','));});
      out.value=lines.join('\n');show(data.length+' row(s) → CSV','ok');}
    catch(e){show('That is not valid JSON.','err');}
  });
  document.getElementById('cj-copy').addEventListener('click',function(){
    out.select();try{document.execCommand('copy');show('Copied!','ok');}catch(e){}
  });
})();
</script>""")
    return dict(slug="csv-json", title="CSV to JSON &amp; JSON to CSV Converter | Free | BVTech",
                desc="Convert CSV to JSON and JSON to CSV instantly in your browser — nothing "
                     "uploaded, free. By BVTech.",
                card_title="CSV ⇄ JSON Converter", icon="🔄",
                card_excerpt="Convert spreadsheets to JSON and back — instant, in your browser, "
                             "nothing uploaded.",
                body=body)


# ---------------------------------------------------------------- Markdown -> HTML
def markdown_html():
    body = _wrap(
        "📝 Free writing tool", "Markdown → HTML Converter",
        "Paste Markdown and get clean HTML you can drop into any website or email — with a live "
        "preview. Everything runs in your browser; nothing is uploaded.",
        _ROW + r"""
<div class="card">
  <label>Markdown</label>
  <textarea id="md-in" placeholder="# Hello&#10;&#10;Some **bold** and *italic* and a [link](https://bvtech.org).&#10;&#10;- one&#10;- two"></textarea>
  <div class="btns" style="margin-top:12px"><button class="btn sec" id="md-copy">Copy HTML</button></div>
  <label>Live preview</label>
  <div class="card" id="md-prev" style="background:rgba(255,255,255,.03)"></div>
  <label style="margin-top:14px">HTML output</label>
  <textarea id="md-out" class="out" readonly></textarea>
</div>
<script>
(function(){
  var inp=document.getElementById('md-in'),out=document.getElementById('md-out'),prev=document.getElementById('md-prev');
  function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
  function inline(s){
    return esc(s)
      .replace(/`([^`]+)`/g,'<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>')
      .replace(/\*([^*]+)\*/g,'<em>$1</em>')
      .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,'<a href="$2" rel="nofollow">$1</a>');
  }
  function md(t){
    var lines=t.replace(/\r\n/g,'\n').split('\n'),html=[],i=0;
    while(i<lines.length){
      var l=lines[i];
      var h=l.match(/^(#{1,6})\s+(.*)$/);
      if(h){html.push('<h'+h[1].length+'>'+inline(h[2])+'</h'+h[1].length+'>');i++;continue;}
      if(/^\s*```/.test(l)){var buf=[];i++;while(i<lines.length&&!/^\s*```/.test(lines[i])){buf.push(esc(lines[i]));i++;}i++;html.push('<pre><code>'+buf.join('\n')+'</code></pre>');continue;}
      if(/^\s*[-*+]\s+/.test(l)){var items=[];while(i<lines.length&&/^\s*[-*+]\s+/.test(lines[i])){items.push('<li>'+inline(lines[i].replace(/^\s*[-*+]\s+/,''))+'</li>');i++;}html.push('<ul>'+items.join('')+'</ul>');continue;}
      if(/^\s*\d+\.\s+/.test(l)){var it=[];while(i<lines.length&&/^\s*\d+\.\s+/.test(lines[i])){it.push('<li>'+inline(lines[i].replace(/^\s*\d+\.\s+/,''))+'</li>');i++;}html.push('<ol>'+it.join('')+'</ol>');continue;}
      if(/^\s*>\s?/.test(l)){html.push('<blockquote>'+inline(l.replace(/^\s*>\s?/,''))+'</blockquote>');i++;continue;}
      if(l.trim()===''){i++;continue;}
      html.push('<p>'+inline(l)+'</p>');i++;
    }
    return html.join('\n');
  }
  function run(){var h=md(inp.value);out.value=h;prev.innerHTML=h||'<span class="muted">Preview…</span>';}
  inp.addEventListener('input',run);
  document.getElementById('md-copy').addEventListener('click',function(){out.select();try{document.execCommand('copy');}catch(e){}});
  run();
})();
</script>""")
    return dict(slug="markdown-html", title="Markdown to HTML Converter | Free | BVTech",
                desc="Convert Markdown to clean HTML with a live preview, right in your browser — "
                     "free, nothing uploaded. By BVTech.",
                card_title="Markdown → HTML", icon="📝",
                card_excerpt="Turn Markdown into clean HTML with a live preview — in your browser.",
                body=body)


# ---------------------------------------------------------------- Color Converter
def color_converter():
    body = _wrap(
        "🎨 Free design tool", "Color Converter — HEX · RGB · HSL",
        "Pick a color or paste a HEX, RGB or HSL value and get every format at once, with a live "
        "swatch. All in your browser — handy for CSS, design and branding.",
        _ROW + r"""
<div class="card">
  <div class="row">
    <div><label>Pick</label><input type="color" id="cc-pick" value="#eb6f24" style="height:48px;padding:4px"></div>
    <div><label>Or type (HEX, rgb(), hsl())</label><input id="cc-txt" value="#EB6F24" placeholder="#EB6F24"></div>
  </div>
  <div id="cc-swatch" style="height:70px;border-radius:12px;border:1px solid var(--border);margin:6px 0 16px;background:#EB6F24"></div>
  <div class="row">
    <div><label>HEX</label><input id="cc-hex" class="out" readonly></div>
    <div><label>RGB</label><input id="cc-rgb" class="out" readonly></div>
    <div><label>HSL</label><input id="cc-hsl" class="out" readonly></div>
  </div>
  <p class="muted" id="cc-msg"></p>
</div>
<script>
(function(){
  var pick=document.getElementById('cc-pick'),txt=document.getElementById('cc-txt'),sw=document.getElementById('cc-swatch'),
      hx=document.getElementById('cc-hex'),rg=document.getElementById('cc-rgb'),hs=document.getElementById('cc-hsl'),msg=document.getElementById('cc-msg');
  function toHex(n){n=Math.max(0,Math.min(255,Math.round(n)));return ('0'+n.toString(16)).slice(-2);}
  function rgb2hsl(r,g,b){r/=255;g/=255;b/=255;var mx=Math.max(r,g,b),mn=Math.min(r,g,b),h,s,l=(mx+mn)/2;
    if(mx===mn){h=s=0;}else{var d=mx-mn;s=l>0.5?d/(2-mx-mn):d/(mx+mn);
      h=mx===r?(g-b)/d+(g<b?6:0):mx===g?(b-r)/d+2:(r-g)/d+4;h/=6;}
    return [Math.round(h*360),Math.round(s*100),Math.round(l*100)];}
  function hsl2rgb(h,s,l){h/=360;s/=100;l/=100;var r,g,b;
    if(s===0){r=g=b=l;}else{function f(p,q,t){if(t<0)t+=1;if(t>1)t-=1;if(t<1/6)return p+(q-p)*6*t;if(t<1/2)return q;if(t<2/3)return p+(q-p)*(2/3-t)*6;return p;}
      var q=l<0.5?l*(1+s):l+s-l*s,p=2*l-q;r=f(p,q,h+1/3);g=f(p,q,h);b=f(p,q,h-1/3);}
    return [r*255,g*255,b*255];}
  function parse(v){v=v.trim();
    var m=v.match(/^#?([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if(m){var h=m[1];if(h.length===3)h=h[0]+h[0]+h[1]+h[1]+h[2]+h[2];return [parseInt(h.slice(0,2),16),parseInt(h.slice(2,4),16),parseInt(h.slice(4,6),16)];}
    m=v.match(/rgba?\(\s*(\d+)\D+(\d+)\D+(\d+)/i);if(m)return [+m[1],+m[2],+m[3]];
    m=v.match(/hsla?\(\s*(\d+)\D+(\d+)\D+(\d+)/i);if(m)return hsl2rgb(+m[1],+m[2],+m[3]);
    return null;}
  function render(rgbv){
    var hex='#'+toHex(rgbv[0])+toHex(rgbv[1])+toHex(rgbv[2]);
    var hsl=rgb2hsl(rgbv[0],rgbv[1],rgbv[2]);
    sw.style.background=hex;hx.value=hex.toUpperCase();
    rg.value='rgb('+Math.round(rgbv[0])+', '+Math.round(rgbv[1])+', '+Math.round(rgbv[2])+')';
    hs.value='hsl('+hsl[0]+', '+hsl[1]+'%, '+hsl[2]+'%)';
    pick.value=hex;msg.textContent='';
  }
  txt.addEventListener('input',function(){var p=parse(txt.value);if(p){render(p);}else{msg.textContent='Enter a HEX, rgb() or hsl() color.';msg.className='muted err';}});
  pick.addEventListener('input',function(){txt.value=pick.value.toUpperCase();render(parse(pick.value));});
  render([235,111,36]);
})();
</script>""")
    return dict(slug="color-converter", title="Color Converter — HEX, RGB, HSL | Free | BVTech",
                desc="Convert colors between HEX, RGB and HSL with a live picker and swatch — "
                     "free, in your browser. By BVTech.",
                card_title="Color Converter", icon="🎨",
                card_excerpt="HEX ⇄ RGB ⇄ HSL with a live picker and swatch — right in your browser.",
                body=body)


# ---------------------------------------------------------------- Unit Converter
def unit_converter():
    body = _wrap(
        "📐 Free everyday tool", "Unit Converter",
        "Convert length, weight, temperature and data sizes instantly. No ads, no tracking, all "
        "in your browser — a quick, honest answer when you just need the number.",
        _ROW + r"""
<div class="card">
  <div class="row">
    <div><label>Category</label><select id="uc-cat"></select></div>
    <div><label>From</label><select id="uc-from"></select></div>
    <div><label>To</label><select id="uc-to"></select></div>
  </div>
  <div class="row">
    <div><label>Value</label><input id="uc-val" type="number" value="1"></div>
    <div><label>Result</label><input id="uc-res" class="out" readonly></div>
  </div>
</div>
<script>
(function(){
  var U={
    Length:{base:'m',u:{Meters:1,Kilometers:1000,Centimeters:0.01,Millimeters:0.001,Miles:1609.344,Yards:0.9144,Feet:0.3048,Inches:0.0254}},
    Weight:{base:'g',u:{Grams:1,Kilograms:1000,Milligrams:0.001,Pounds:453.592,Ounces:28.3495,Tonnes:1000000}},
    Data:{base:'B',u:{Bytes:1,Kilobytes:1024,Megabytes:1048576,Gigabytes:1073741824,Terabytes:1099511627776}}
  };
  var cat=document.getElementById('uc-cat'),from=document.getElementById('uc-from'),to=document.getElementById('uc-to'),
      val=document.getElementById('uc-val'),res=document.getElementById('uc-res');
  ['Length','Weight','Temperature','Data'].forEach(function(c){cat.add(new Option(c,c));});
  function fill(sel,arr,idx){sel.innerHTML='';arr.forEach(function(u){sel.add(new Option(u,u));});sel.selectedIndex=idx||0;}
  function units(){var c=cat.value;if(c==='Temperature')return ['Celsius','Fahrenheit','Kelvin'];return Object.keys(U[c].u);}
  function conv(){
    var c=cat.value,v=parseFloat(val.value);if(isNaN(v)){res.value='';return;}
    var out;
    if(c==='Temperature'){
      var f=from.value,t=to.value,cel;
      cel=f==='Celsius'?v:f==='Fahrenheit'?(v-32)*5/9:v-273.15;
      out=t==='Celsius'?cel:t==='Fahrenheit'?cel*9/5+32:cel+273.15;
    }else{var m=U[c].u;out=v*m[from.value]/m[to.value];}
    res.value=Math.round(out*1e6)/1e6;
  }
  function rebuild(){var a=units();fill(from,a,0);fill(to,a,1);conv();}
  cat.addEventListener('change',rebuild);
  [from,to,val].forEach(function(el){el.addEventListener('input',conv);el.addEventListener('change',conv);});
  rebuild();
})();
</script>""")
    return dict(slug="unit-converter", title="Unit Converter — Length, Weight, Temp, Data | Free | BVTech",
                desc="Convert length, weight, temperature and data sizes instantly in your browser "
                     "— free, no ads, no tracking. By BVTech.",
                card_title="Unit Converter", icon="📐",
                card_excerpt="Length, weight, temperature &amp; data — instant conversions, no ads, "
                             "no tracking.",
                body=body)


def all_converters():
    return [image_converter(), csv_json(), markdown_html(), color_converter(), unit_converter()]
