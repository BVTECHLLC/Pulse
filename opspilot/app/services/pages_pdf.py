"""Free in-browser PDF tools for bvtech.org/tools/ (v1.140).

Everything runs client-side — the PDF never leaves the visitor's device — which is
both the honest privacy pitch for an MSP and the reason it can be free. The site
CSP is `default-src 'self'`, so the PDF engine is SELF-HOSTED: pdf-lib (edit/sign)
and pdf.js (render) ship as same-origin files under /tools/lib/ (published by
destination._add_tool_libs). Three tools: Sign a PDF, Images → PDF, PDF → Images.
"""
from __future__ import annotations

from .pages_tools import _wrap

_PDFJS = ('<script src="/tools/lib/pdf.min.js"></script>'
          '<script>try{pdfjsLib.GlobalWorkerOptions.workerSrc="/tools/lib/pdf.worker.min.js";}catch(e){}</script>')
_PDFLIB = '<script src="/tools/lib/pdf-lib.min.js"></script>'

_CSS = ("<style>"
        ".tl .pdf-drop{border:2px dashed var(--border);border-radius:14px;padding:30px 18px;text-align:center;"
        "background:rgba(255,255,255,.03);cursor:pointer;transition:.15s}"
        ".tl .pdf-drop:hover{border-color:var(--o2);background:rgba(245,190,88,.06)}"
        ".tl .pdf-drop input{display:none}"
        ".tl .stage{position:relative;max-width:100%;overflow:auto;border:1px solid var(--border);"
        "border-radius:10px;background:#0b0a1f;margin:14px 0}"
        ".tl .stage canvas{display:block;margin:0 auto;max-width:100%}"
        ".tl .sig{position:absolute;cursor:move;touch-action:none;border:1px dashed rgba(245,190,88,.8);"
        "box-shadow:0 0 0 9999px rgba(0,0,0,0)}.tl .sig img{display:block;width:100%;height:100%;pointer-events:none}"
        ".tl .sig .gr{position:absolute;right:-7px;bottom:-7px;width:16px;height:16px;border-radius:50%;"
        "background:var(--o2);cursor:nwse-resize}"
        ".tl .pager{display:flex;gap:10px;align-items:center;justify-content:center;margin:10px 0}"
        ".tl .pager button{padding:7px 14px;border-radius:8px;border:1px solid var(--border);"
        "background:rgba(255,255,255,.05);color:var(--white);cursor:pointer;font-weight:700}"
        ".tl .sigpad{border:1px solid var(--border);border-radius:10px;background:#fff;touch-action:none;width:100%;max-width:420px;height:150px}"
        ".tl .thumbs{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}"
        ".tl .thumbs .t{width:92px;border:1px solid var(--border);border-radius:8px;overflow:hidden;background:#0b0a1f}"
        ".tl .thumbs .t img{width:100%;display:block}"
        ".tl .thumbs .t span{display:block;font-size:.68rem;color:var(--muted);text-align:center;padding:3px}"
        ".tl .seg{display:flex;gap:8px;margin:0 0 14px;flex-wrap:wrap}"
        ".tl .seg button{padding:8px 14px;border-radius:8px;border:1px solid var(--border);background:transparent;color:var(--text);cursor:pointer;font-weight:700}"
        ".tl .seg button.on{background:var(--o);color:#0E0D2C;border-color:var(--o)}"
        ".tl .res-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px;margin-top:14px}"
        ".tl .res-grid figure{margin:0;border:1px solid var(--border);border-radius:10px;overflow:hidden;background:#0b0a1f}"
        ".tl .res-grid img{width:100%;display:block}"
        ".tl .res-grid a{display:block;text-align:center;padding:8px;font-weight:700;font-size:.85rem}"
        ".tl .lic{color:var(--muted);font-size:.74rem;margin-top:22px}"
        "</style>")


# ------------------------------------------------------------------ Sign a PDF
def sign_pdf():
    body = _wrap(
        "✍️ Free PDF tool", "Sign a PDF — free &amp; private",
        "Add your signature to any PDF right in your browser — draw it or type it, drop it where it "
        "goes, and download the signed file. Your document never leaves your device and is never "
        "uploaded anywhere.",
        _CSS + r"""
<label class="pdf-drop" id="pd-drop"><input type="file" id="pd-file" accept="application/pdf">
  <div style="font-size:2rem">📄</div><b style="color:var(--white)">Choose a PDF</b>
  <div class="muted">or drop it here · stays on your device</div></label>
<div id="pd-work" hidden>
  <div class="seg" style="margin-top:16px">
    <button id="pd-draw-tab" class="on" type="button">✍️ Draw signature</button>
    <button id="pd-type-tab" type="button">⌨️ Type signature</button>
  </div>
  <div id="pd-draw-box"><canvas class="sigpad" id="pd-pad" width="420" height="150"></canvas></div>
  <div id="pd-type-box" hidden><input id="pd-type" placeholder="Type your name" style="font-family:'Segoe Script','Brush Script MT',cursive;font-size:1.6rem"></div>
  <div class="seg" style="margin-top:10px">
    <button class="btn" id="pd-use" type="button">Use this signature ↓</button>
    <button id="pd-clear" type="button">Clear</button>
  </div>
  <p class="muted" id="pd-hint">Make a signature, press <b>Use this signature</b>, then drag it onto the page. Resize with the gold corner.</p>
  <div class="pager"><button id="pd-prev" type="button">‹ Prev</button><span id="pd-pg" class="muted">Page 1</span><button id="pd-next" type="button">Next ›</button></div>
  <div class="stage" id="pd-stage"><canvas id="pd-canvas"></canvas></div>
  <button class="btn" id="pd-save" type="button" style="margin-top:6px">⬇️ Download signed PDF</button>
  <p class="muted" id="pd-msg" style="margin-top:10px"></p>
</div>
<p class="lic">Powered by the open-source pdf-lib (MIT) and pdf.js (Apache-2.0), served from this site — nothing is uploaded.</p>
""" + _PDFJS + _PDFLIB + r"""
<script>
(function(){
  var pdfBytes=null,pdf=null,page=1,scale=1,vpW=0,vpH=0,sigURL=null,placed=null;
  var file=document.getElementById('pd-file'),drop=document.getElementById('pd-drop'),work=document.getElementById('pd-work'),
      canvas=document.getElementById('pd-canvas'),stage=document.getElementById('pd-stage'),pg=document.getElementById('pd-pg'),
      msg=document.getElementById('pd-msg'),pad=document.getElementById('pd-pad'),hint=document.getElementById('pd-hint');
  function say(t,c){msg.textContent=t;msg.className='muted '+(c||'');}
  // ---- signature pad (draw) ----
  var ctx=pad.getContext('2d'),drawing=false,drew=false;
  ctx.lineWidth=2.5;ctx.lineCap='round';ctx.strokeStyle='#111';
  function pos(e){var r=pad.getBoundingClientRect(),t=e.touches?e.touches[0]:e;return [(t.clientX-r.left)*pad.width/r.width,(t.clientY-r.top)*pad.height/r.height];}
  function down(e){drawing=true;drew=true;var p=pos(e);ctx.beginPath();ctx.moveTo(p[0],p[1]);e.preventDefault();}
  function move(e){if(!drawing)return;var p=pos(e);ctx.lineTo(p[0],p[1]);ctx.stroke();e.preventDefault();}
  function up(){drawing=false;}
  pad.addEventListener('mousedown',down);pad.addEventListener('mousemove',move);window.addEventListener('mouseup',up);
  pad.addEventListener('touchstart',down);pad.addEventListener('touchmove',move);pad.addEventListener('touchend',up);
  document.getElementById('pd-clear').addEventListener('click',function(){ctx.clearRect(0,0,pad.width,pad.height);drew=false;document.getElementById('pd-type').value='';});
  var drawTab=document.getElementById('pd-draw-tab'),typeTab=document.getElementById('pd-type-tab');
  drawTab.addEventListener('click',function(){drawTab.classList.add('on');typeTab.classList.remove('on');document.getElementById('pd-draw-box').hidden=false;document.getElementById('pd-type-box').hidden=true;});
  typeTab.addEventListener('click',function(){typeTab.classList.add('on');drawTab.classList.remove('on');document.getElementById('pd-draw-box').hidden=true;document.getElementById('pd-type-box').hidden=false;});
  function typedSig(text){
    var c=document.createElement('canvas');c.width=600;c.height=180;var x=c.getContext('2d');
    x.fillStyle='#111';x.font="italic 70px 'Segoe Script','Brush Script MT',cursive";x.textBaseline='middle';
    x.fillText(text,20,95);return c;
  }
  // ---- load pdf ----
  function openFile(f){
    if(!f||f.type!=='application/pdf'){say('Please choose a PDF file.','err');return;}
    var r=new FileReader();
    r.onload=function(){
      pdfBytes=new Uint8Array(r.result);
      pdfjsLib.getDocument({data:pdfBytes.slice(0)}).promise.then(function(doc){
        pdf=doc;page=1;drop.style.display='none';work.hidden=false;render();
      }).catch(function(){say('Could not read that PDF.','err');});
    };
    r.readAsArrayBuffer(f);
  }
  file.addEventListener('change',function(){openFile(file.files[0]);});
  drop.addEventListener('dragover',function(e){e.preventDefault();});
  drop.addEventListener('drop',function(e){e.preventDefault();if(e.dataTransfer.files[0])openFile(e.dataTransfer.files[0]);});
  function render(){
    pdf.getPage(page).then(function(pg_){
      var base=pg_.getViewport({scale:1});var w=Math.min(stage.clientWidth||560,640);scale=w/base.width;
      var vp=pg_.getViewport({scale:scale});vpW=vp.width;vpH=vp.height;
      canvas.width=vp.width;canvas.height=vp.height;
      pg_.render({canvasContext:canvas.getContext('2d'),viewport:vp}).promise.then(function(){
        pg.textContent='Page '+page+' of '+pdf.numPages;
        if(placed&&placed.page===page){stage.appendChild(placed.el);positionEl();}
        else if(placed){placed.el.remove();}
      });
    });
  }
  document.getElementById('pd-prev').addEventListener('click',function(){if(page>1){page--;render();}});
  document.getElementById('pd-next').addEventListener('click',function(){if(page<pdf.numPages){page++;render();}});
  // ---- place + drag signature ----
  function makeSigEl(){
    var el=document.createElement('div');el.className='sig';el.style.width='180px';el.style.left='40px';el.style.top='40px';
    var im=document.createElement('img');im.src=sigURL;el.appendChild(im);
    var gr=document.createElement('div');gr.className='gr';el.appendChild(gr);
    var aspect=1;im.onload=function(){aspect=im.naturalHeight/im.naturalWidth;el.style.height=(180*aspect)+'px';};
    var dragging=false,ox=0,oy=0,resizing=false;
    function p(e){var t=e.touches?e.touches[0]:e;return [t.clientX,t.clientY];}
    el.addEventListener('mousedown',start);el.addEventListener('touchstart',start);
    gr.addEventListener('mousedown',function(e){resizing=true;e.stopPropagation();e.preventDefault();});
    gr.addEventListener('touchstart',function(e){resizing=true;e.stopPropagation();e.preventDefault();});
    function start(e){if(resizing)return;dragging=true;var c=p(e),r=el.getBoundingClientRect();ox=c[0]-r.left;oy=c[1]-r.top;e.preventDefault();}
    function mv(e){
      var c=p(e),sr=stage.getBoundingClientRect();
      if(resizing){var w=Math.max(40,c[0]-el.getBoundingClientRect().left);el.style.width=w+'px';el.style.height=(w*aspect)+'px';e.preventDefault();return;}
      if(!dragging)return;
      var x=c[0]-sr.left-ox+stage.scrollLeft,y=c[1]-sr.top-oy+stage.scrollTop;
      el.style.left=Math.max(0,Math.min(x,canvas.width-10))+'px';el.style.top=Math.max(0,Math.min(y,canvas.height-10))+'px';e.preventDefault();
    }
    window.addEventListener('mousemove',mv);window.addEventListener('touchmove',mv,{passive:false});
    window.addEventListener('mouseup',function(){dragging=false;resizing=false;});
    window.addEventListener('touchend',function(){dragging=false;resizing=false;});
    return el;
  }
  function positionEl(){/* keeps element on re-render */}
  document.getElementById('pd-use').addEventListener('click',function(){
    var src;
    if(!document.getElementById('pd-draw-box').hidden){if(!drew){say('Draw your signature first.','err');return;}src=pad;}
    else{var txt=document.getElementById('pd-type').value.trim();if(!txt){say('Type your signature first.','err');return;}src=typedSig(txt);}
    sigURL=src.toDataURL('image/png');
    if(placed)placed.el.remove();
    var el=makeSigEl();placed={el:el,page:page};stage.appendChild(el);
    hint.textContent='Drag the signature where it belongs, resize with the gold corner, then Download.';say('');
  });
  // ---- export ----
  document.getElementById('pd-save').addEventListener('click',function(){
    if(!placed){say('Add a signature and place it on the page first.','err');return;}
    say('Building your signed PDF…');
    PDFLib.PDFDocument.load(pdfBytes.slice(0)).then(function(doc){
      return fetch(sigURL).then(function(r){return r.arrayBuffer();}).then(function(buf){
        return doc.embedPng(buf).then(function(png){
          var pageObj=doc.getPages()[placed.page-1];var pw=pageObj.getWidth(),ph=pageObj.getHeight();
          var el=placed.el;var lx=parseFloat(el.style.left),ly=parseFloat(el.style.top),lw=parseFloat(el.style.width),lh=parseFloat(el.style.height);
          var x=lx/vpW*pw, w=lw/vpW*pw, h=lh/vpH*ph, y=ph-(ly/vpH*ph)-h;
          pageObj.drawImage(png,{x:x,y:y,width:w,height:h});
          return doc.save();
        });
      });
    }).then(function(bytes){
      var blob=new Blob([bytes],{type:'application/pdf'}),url=URL.createObjectURL(blob);
      var a=document.createElement('a');a.href=url;a.download='signed.pdf';document.body.appendChild(a);a.click();a.remove();
      setTimeout(function(){URL.revokeObjectURL(url);},4000);say('Done — your signed PDF downloaded.','ok');
    }).catch(function(){say('Sorry, that PDF could not be signed (it may be encrypted).','err');});
  });
})();
</script>""")
    return dict(slug="sign-pdf", title="Sign a PDF — Free &amp; Private e-Signature | BVTech",
                desc="Add your signature to a PDF free, right in your browser — draw or type it, "
                     "place it, download. Nothing is uploaded. By BVTech.",
                card_title="Sign a PDF (e-Sign)", icon="✍️",
                card_excerpt="Draw or type your signature onto any PDF and download it — free, "
                             "100% in your browser, nothing uploaded.",
                body=body)


# ------------------------------------------------------------------ Images -> PDF
def images_to_pdf():
    body = _wrap(
        "🖼️ Free PDF tool", "Images → PDF",
        "Combine JPGs and PNGs into a single PDF — in the order you choose, right in your browser. "
        "Great for turning phone photos of a document into one clean file to email. Nothing is uploaded.",
        _CSS + r"""
<label class="pdf-drop" id="ip-drop"><input type="file" id="ip-file" accept="image/*" multiple>
  <div style="font-size:2rem">🖼️</div><b style="color:var(--white)">Choose images</b>
  <div class="muted">JPG or PNG · pick several · stays on your device</div></label>
<div class="thumbs" id="ip-thumbs"></div>
<button class="btn" id="ip-go" hidden>⬇️ Create PDF</button>
<p class="muted" id="ip-msg" style="margin-top:10px"></p>
<p class="lic">Powered by the open-source pdf-lib (MIT), served from this site — nothing is uploaded.</p>
""" + _PDFLIB + r"""
<script>
(function(){
  var file=document.getElementById('ip-file'),thumbs=document.getElementById('ip-thumbs'),go=document.getElementById('ip-go'),msg=document.getElementById('ip-msg');
  var imgs=[];
  function say(t,c){msg.textContent=t;msg.className='muted '+(c||'');}
  file.addEventListener('change',function(){
    imgs=[].slice.call(file.files);thumbs.innerHTML='';
    imgs.forEach(function(f,i){var r=new FileReader();r.onload=function(){
      var d=document.createElement('div');d.className='t';d.innerHTML='<img src="'+r.result+'"><span>'+(i+1)+'</span>';thumbs.appendChild(d);};r.readAsDataURL(f);});
    go.hidden=imgs.length===0;say(imgs.length+' image(s) selected.');
  });
  go.addEventListener('click',function(){
    say('Building your PDF…');
    PDFLib.PDFDocument.create().then(function(doc){
      var chain=Promise.resolve();
      imgs.forEach(function(f){chain=chain.then(function(){return f.arrayBuffer();}).then(function(buf){
        var isPng=f.type.indexOf('png')>-1;
        return (isPng?doc.embedPng(buf):doc.embedJpg(buf)).then(function(img){
          var pg=doc.addPage([img.width,img.height]);pg.drawImage(img,{x:0,y:0,width:img.width,height:img.height});
        }).catch(function(){/* skip an unsupported image */});
      });});
      return chain.then(function(){return doc.save();});
    }).then(function(bytes){
      var blob=new Blob([bytes],{type:'application/pdf'}),url=URL.createObjectURL(blob);
      var a=document.createElement('a');a.href=url;a.download='images.pdf';document.body.appendChild(a);a.click();a.remove();
      setTimeout(function(){URL.revokeObjectURL(url);},4000);say('Done — your PDF downloaded.','ok');
    }).catch(function(){say('Sorry, that did not work — try PNG or JPG images.','err');});
  });
})();
</script>""")
    return dict(slug="images-to-pdf", title="Images to PDF — Free JPG/PNG to PDF | BVTech",
                desc="Combine JPG and PNG images into one PDF in your browser — free, in order, "
                     "nothing uploaded. By BVTech.",
                card_title="Images → PDF", icon="🖼️",
                card_excerpt="Combine JPG/PNG images into one PDF — in your browser, nothing uploaded.",
                body=body)


# ------------------------------------------------------------------ PDF -> Images
def pdf_to_images():
    body = _wrap(
        "📑 Free PDF tool", "PDF → Images",
        "Turn each page of a PDF into a high-quality PNG you can download — right in your browser. "
        "Handy for grabbing a single page as a picture. Your PDF never leaves your device.",
        _CSS + r"""
<label class="pdf-drop" id="pi-drop"><input type="file" id="pi-file" accept="application/pdf">
  <div style="font-size:2rem">📑</div><b style="color:var(--white)">Choose a PDF</b>
  <div class="muted">each page becomes a PNG · stays on your device</div></label>
<p class="muted" id="pi-msg" style="margin-top:12px"></p>
<div class="res-grid" id="pi-out"></div>
<p class="lic">Powered by the open-source pdf.js (Apache-2.0), served from this site — nothing is uploaded.</p>
""" + _PDFJS + r"""
<script>
(function(){
  var file=document.getElementById('pi-file'),out=document.getElementById('pi-out'),msg=document.getElementById('pi-msg');
  function say(t,c){msg.textContent=t;msg.className='muted '+(c||'');}
  file.addEventListener('change',function(){
    var f=file.files[0];if(!f){return;}out.innerHTML='';say('Rendering pages…');
    var r=new FileReader();
    r.onload=function(){
      pdfjsLib.getDocument({data:new Uint8Array(r.result)}).promise.then(function(pdf){
        var n=pdf.numPages,done=0;say('Rendering '+n+' page(s)…');
        function page(i){
          pdf.getPage(i).then(function(pg){
            var vp=pg.getViewport({scale:2});var c=document.createElement('canvas');c.width=vp.width;c.height=vp.height;
            pg.render({canvasContext:c.getContext('2d'),viewport:vp}).promise.then(function(){
              var url=c.toDataURL('image/png');
              var fig=document.createElement('figure');
              fig.innerHTML='<img src="'+url+'" alt="page '+i+'"><a href="'+url+'" download="page-'+i+'.png">⬇️ Page '+i+'</a>';
              out.appendChild(fig);done++;if(done===n)say('Done — '+n+' page(s). Click a page to download.','ok');
              if(i<n)page(i+1);
            });
          });
        }
        page(1);
      }).catch(function(){say('Could not read that PDF.','err');});
    };
    r.readAsArrayBuffer(f);
  });
})();
</script>""")
    return dict(slug="pdf-to-images", title="PDF to Images — Free PDF to PNG | BVTech",
                desc="Convert each page of a PDF into a downloadable PNG image in your browser — "
                     "free, nothing uploaded. By BVTech.",
                card_title="PDF → Images", icon="📑",
                card_excerpt="Turn each PDF page into a downloadable PNG — in your browser, "
                             "nothing uploaded.",
                body=body)


def all_pdf_tools():
    return [sign_pdf(), images_to_pdf(), pdf_to_images()]
