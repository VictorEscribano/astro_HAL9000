"""Proxy for Stellarium Web — serves stellarium-web.org through our backend
so the iframe shares the same origin as the React app. That lets us inject a
postMessage listener that drives the SWE engine (core.selection + pointAndLock)
without cross-origin restrictions.

Stellarium pulls assets from two CDNs:
  - CloudFront (d3ufh70wg9uzo4.cloudfront.net) for static JS/CSS/WASM/images
  - DigitalOcean Spaces (stellarium.sfo2.cdn.digitaloceanspaces.com) for sky-data
    packs (stars, DSOs, surveys) — this CDN does not return Access-Control-Allow-Origin,
    so the sky catalogs would be CORS-blocked without our proxy.

Both CDN URLs are rewritten to our same-origin proxy paths in the HTML and in any
JS/CSS we serve, so webpack publicPath and every dynamic asset request stays
same-origin and the proxy adds the required CORS header."""
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response

router = APIRouter(tags=["stel-proxy"])

_STEL = "https://stellarium-web.org"
# (origin, proxy-prefix) pairs — order matters only for clarity.
_CDN_MAP = [
    ("https://d3ufh70wg9uzo4.cloudfront.net/",          "/stel-cdn/"),
    ("https://stellarium.sfo2.cdn.digitaloceanspaces.com/", "/stel-data/"),
]

# Injected into every Stellarium page.  Polls until the Vue $stel engine is
# ready, then listens for {t:"sel", n:"Jupiter"} postMessages from the parent.
_INJECT = r"""<script>
(function(){
  var _s=null;
  function find(){
    try{
      var el=document.getElementById('app');
      if(el&&el.__vue__&&el.__vue__.$stel){_s=el.__vue__.$stel;return;}
    }catch(e){}
    setTimeout(find,400);
  }
  setTimeout(find,1500);

  /* React → Stellarium: select an object by name.
     Catalog IDs (NGC 224, HIP 32349, M 31) work directly; planets and proper
     names need a "NAME " prefix, so we try the raw form first then fall back. */
  window.addEventListener('message',function(ev){
    var d=ev.data;
    if(!d||d.t!=='sel')return;
    var n=d.n;
    (function go(){
      if(!_s){setTimeout(go,250);return;}
      var o=_s.getObj(n)||_s.getObj('NAME '+n);
      if(o){_s.core.selection=o;_s.pointAndLock(o);}
    })();
  });

  /* Stellarium → React: emit a snapshot of the selected object (RA/DEC,
     Az/Alt, vmag, distance, phase, rise/set) whenever the selection changes,
     plus periodic refreshes so Az/Alt update as the sky moves. */
  function sphFromVec(v){
    var x=v[0], y=v[1], z=v[2];
    return [Math.atan2(y, x), Math.atan2(z, Math.sqrt(x*x+y*y))];
  }
  function snapshot(sel){
    if(!sel) return null;
    var radec=sel.getInfo('radec');
    var observed=null;
    try{ observed=_s.convertFrame(_s.core.observer,'ICRF','OBSERVED',radec); }catch(e){}
    var sphRadec=sphFromVec(radec);
    var sphObs=observed?sphFromVec(observed):null;
    return {
      names: sel.designations(),
      ra_h: ((sphRadec[0]*12/Math.PI)+24)%24,
      dec_deg: sphRadec[1]*180/Math.PI,
      az_deg: sphObs?(((sphObs[0]*180/Math.PI)+360)%360):null,
      alt_deg: sphObs?(sphObs[1]*180/Math.PI):null,
      vmag: sel.getInfo('vmag'),
      distance: sel.getInfo('distance'),
      phase: sel.getInfo('phase'),
      utc_mjd: _s.core.observer.utc,
    };
  }
  function send(info){
    try{ parent.postMessage({t:'stel-selection',info:info},'*'); }catch(e){}
  }
  function emit(){
    if(!_s) return;
    var sel=_s.core.selection;
    var info;
    try{ info=snapshot(sel); }catch(e){ send(null); return; }
    /* Emit immediately with what we have; computeVisibility is async and
       sometimes never settles, so we don't gate the emit on it.  If it
       does resolve, send a follow-up with rise/set times. */
    send(info);
    if(info && sel.computeVisibility){
      try{
        var p=sel.computeVisibility();
        if(p && p.then) p.then(function(v){ info.visibility=v; send(info); }, function(){});
      }catch(e){}
    }
  }
  /* The engine fires onValueChanged for "observer.utc" every frame but
     doesn't fire a "selection" event when something else mutates
     core.selection.  So we drive change detection from the per-frame tick
     and dedupe by the selected object's first designation. */
  var lastKey=null;
  function checkSelection(){
    if(!_s) return;
    var sel=_s.core.selection;
    var key=sel?sel.designations().join('|'):'';
    if(key!==lastKey){ lastKey=key; emit(); }
  }
  var lastEmit=0;
  function wireUp(){
    if(!_s){setTimeout(wireUp,300);return;}
    if(_s.onValueChanged){
      _s.onValueChanged(function(path){
        if(path==='observer.utc'){
          checkSelection();
          /* Throttled refresh while a selection is held so Az/Alt track sky motion. */
          var now=Date.now();
          if(_s.core.selection && now-lastEmit>1500){ lastEmit=now; emit(); }
        }
      });
    }
  }
  setTimeout(wireUp,2500);
})();
</script>"""


def _rewrite(text: str) -> str:
    """Rewrite CDN origins to same-origin proxy prefixes, and Vue Router's
    history base from "/" to "/stel/" so the SPA routes match under our
    proxy mount path (otherwise <router-view> matches nothing and the
    canvas never mounts → blank page)."""
    for origin, prefix in _CDN_MAP:
        text = text.replace(origin, prefix)
    text = text.replace('mode:"history",base:"/"', 'mode:"history",base:"/stel/"')
    return text


async def _fetch(url: str, timeout: float = 30.0) -> httpx.Response:
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as c:
        return await c.get(url, headers={"User-Agent": "Mozilla/5.0"})


async def _proxy_cdn(origin: str, path: str) -> Response:
    r = await _fetch(f"{origin}{path}")
    ct = r.headers.get("content-type", "application/octet-stream")
    if "javascript" in ct or "css" in ct:
        content = _rewrite(r.text).encode()
        cache = "no-store"   # avoid serving pre-rewrite cached copies during dev
    else:
        content = r.content
        cache = "public, max-age=3600"
    return Response(
        content=content,
        media_type=ct,
        headers={"Cache-Control": cache,
                 "Access-Control-Allow-Origin": "*"},
    )


@router.get("/stel-cdn/{path:path}")
async def cdn_proxy(path: str):
    """CloudFront CDN: static JS/CSS/WASM/images."""
    return await _proxy_cdn("https://d3ufh70wg9uzo4.cloudfront.net/", path)


@router.get("/stel-data/{path:path}")
async def data_proxy(path: str):
    """DigitalOcean Spaces CDN: sky data packs (stars, DSOs, surveys)."""
    return await _proxy_cdn("https://stellarium.sfo2.cdn.digitaloceanspaces.com/", path)


@router.get("/stel")
@router.get("/stel/")
@router.get("/stel/{path:path}")
async def stel_proxy(request: Request, path: str = ""):
    """Serve Stellarium Web (always the SPA root) with CDN URLs rewritten
    and the SWE bridge injected."""
    qs = str(request.url.query)
    url = _STEL + "/" + ("?" + qs if qs else "")
    r = await _fetch(url)
    ct = r.headers.get("content-type", "text/html")
    if "text/html" not in ct:
        return Response(content=r.content, media_type=ct)
    html = _rewrite(r.text)
    html = html.replace("</head>", _INJECT + "</head>", 1)
    return Response(
        content=html,
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )
