(() => {
  const motion = matchMedia('(prefers-reduced-motion: no-preference) and (hover: hover) and (pointer: fine)');
  const owl = document.createElement('div');
  owl.className = 'cursor-owl'; owl.setAttribute('aria-hidden','true');
  const image = document.createElement('img'); image.src='/static/owl-logo.svg'; image.alt='';
  owl.append(image); document.body.append(owl);
  let x=0, y=0, tx=0, ty=0, frame=0, last=0, active=false;
  function hide() {
    active=false; owl.classList.remove('is-visible');
    cancelAnimationFrame(frame); frame=0; last=0;
  }
  function tick(time) {
    const delta = last ? Math.min(time-last,50) : 16;
    last=time;
    const ease=1-Math.exp(-delta/95);
    x+=(tx-x)*ease; y+=(ty-y)*ease;
    const tilt=Math.max(-14,Math.min(14,(tx-x)*.15));
    owl.style.transform=`translate3d(${x}px,${y}px,0) rotate(${tilt}deg)`;
    if (Math.abs(tx-x)+Math.abs(ty-y)>.15) frame=requestAnimationFrame(tick);
    else {frame=0;last=0;}
  }
  document.addEventListener('pointermove',event=>{
    if (!motion.matches || event.pointerType==='touch') return;
    tx=Math.max(0,Math.min(innerWidth-60,event.clientX+24));
    ty=Math.max(0,Math.min(innerHeight-60,event.clientY+22));
    if (!active) {x=tx;y=ty;active=true;owl.classList.add('is-visible');}
    if (!frame) frame=requestAnimationFrame(tick);
  },{passive:true});
  document.documentElement.addEventListener('pointerleave',hide);
  window.addEventListener('blur',hide);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)hide();});
  motion.addEventListener('change',hide);
})();
