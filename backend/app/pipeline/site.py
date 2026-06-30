"""Build a real, self-contained frontend from the baked spec + Blender frames.

Frame-sequence scrollytelling (the technique Apple/Active-Theory use for pre-rendered
3D): the page preloads the Blender-rendered frames and scrubs them by scroll position,
with per-act DOM copy fading in over the rendered structure. This is the "actual website".
"""
from __future__ import annotations

from pathlib import Path

_HTML = """<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root{--bg:__BG__;--accent:__ACCENT__;--text:__TEXT__}
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{background:var(--bg);color:var(--text);font-family:'Space Grotesk',system-ui,sans-serif;-webkit-font-smoothing:antialiased}
  #stage{position:fixed;inset:0;width:100vw;height:100vh;z-index:0}
  #stage canvas{width:100%;height:100%;object-fit:cover;display:block}
  #scroller{position:relative;z-index:1;height:__SCROLLH__vh}
  .act{position:sticky;top:0;height:100vh;display:flex;align-items:flex-end;padding:clamp(2rem,7vw,7rem);pointer-events:none}
  .act .inner{max-width:560px;opacity:0;transform:translateY(28px);transition:opacity .6s,transform .6s}
  .act.show .inner{opacity:1;transform:none}
  .eyebrow{font-family:ui-monospace,monospace;text-transform:uppercase;letter-spacing:.32em;font-size:.7rem;color:var(--accent);margin-bottom:1rem}
  h2{font-size:clamp(2rem,5.5vw,4.2rem);line-height:1.0;font-weight:700;letter-spacing:-.02em}
  p{margin-top:1rem;font-size:1.05rem;line-height:1.5;opacity:.8;max-width:44ch}
  .brand{position:fixed;top:1.4rem;left:clamp(1.5rem,6vw,7rem);z-index:3;font-family:ui-monospace,monospace;letter-spacing:.14em;font-size:.85rem}
  .hint{position:fixed;bottom:1.3rem;left:50%;transform:translateX(-50%);z-index:3;font-family:ui-monospace,monospace;font-size:.66rem;letter-spacing:.3em;opacity:.5}
  .made{position:fixed;bottom:1.1rem;right:1.2rem;z-index:3;font-size:.62rem;opacity:.4;letter-spacing:.12em}
</style></head><body>
<div class="brand">__PROJECT__</div>
<div id="stage"><canvas id="c"></canvas></div>
<div id="scroller">__ACTS__</div>
<div class="hint">SCROLL ↓</div><div class="made">Made with WEGEK · Blender</div>
<script>
const FRAMES=__FRAMES__, BASE="frames/";
const cv=document.getElementById("c"), ctx=cv.getContext("2d");
const imgs=[]; let loaded=0;
for(let i=0;i<FRAMES;i++){const im=new Image();im.src=BASE+"f_"+String(i+1).padStart(4,"0")+".jpg";im.onload=()=>{loaded++;if(i===0)draw(0)};imgs[i]=im;}
function fit(){cv.width=innerWidth*Math.min(devicePixelRatio,2);cv.height=innerHeight*Math.min(devicePixelRatio,2);}
function draw(idx){const im=imgs[Math.max(0,Math.min(FRAMES-1,idx|0))];if(!im||!im.complete)return;
  const ir=im.width/im.height, cr=cv.width/cv.height; let w,h,x,y;
  if(ir>cr){h=cv.height;w=h*ir;}else{w=cv.width;h=w/ir;} x=(cv.width-w)/2;y=(cv.height-h)/2;
  ctx.clearRect(0,0,cv.width,cv.height);ctx.drawImage(im,x,y,w,h);}
let target=0,cur=0;
function onScroll(){const max=document.body.scrollHeight-innerHeight; const p=max>0?scrollY/max:0; target=p*(FRAMES-1);
  document.querySelectorAll('.act').forEach((a,i,arr)=>{const c=(i+0.5)/arr.length; a.classList.toggle('show', Math.abs(p-c)<0.5/arr.length+0.12);});}
function loop(){cur+=(target-cur)*0.18; draw(cur); requestAnimationFrame(loop);}
addEventListener('resize',()=>{fit();draw(cur)});addEventListener('scroll',onScroll,{passive:true});
fit();onScroll();loop();
</script></body></html>"""


def build(spec: dict, frames: list[str], out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    fdir = out_dir / "frames"
    fdir.mkdir(exist_ok=True)
    n = 0
    try:
        from PIL import Image
        for i, fp in enumerate(frames):
            im = Image.open(fp).convert("RGB")
            if im.width > 1100:
                im.thumbnail((1100, 1100))
            im.save(fdir / f"f_{i+1:04d}.jpg", "JPEG", quality=72)
            n += 1
    except Exception:
        # fall back to copying raw frames if PIL missing
        import shutil
        for i, fp in enumerate(frames):
            shutil.copy(fp, fdir / f"f_{i+1:04d}.jpg")
            n += 1

    pal = (spec.get("acts", [{}])[0].get("palette") or ["#06080d", "#00e5ff", "#a06bff", "#eef6ff"])
    acts_html = []
    for a in spec.get("acts", []):
        acts_html.append(
            f'<section class="act"><div class="inner">'
            f'<div class="eyebrow">{a.get("id","")} · {a.get("title","")}</div>'
            f'<h2>{a.get("title","")}</h2><p>{a.get("narrative","")}</p></div></section>'
        )
    html = (_HTML
            .replace("__TITLE__", f"{spec.get('project_name','WEGEK')} — {spec.get('tagline','')}")
            .replace("__PROJECT__", spec.get("project_name", "WEGEK"))
            .replace("__BG__", pal[0]).replace("__ACCENT__", pal[1] if len(pal) > 1 else "#00e5ff")
            .replace("__TEXT__", pal[3] if len(pal) > 3 else "#eef6ff")
            .replace("__SCROLLH__", str(max(300, n * 6)))
            .replace("__FRAMES__", str(n))
            .replace("__ACTS__", "\n".join(acts_html)))
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    return {"frames": n, "path": str(out_dir / "index.html")}
