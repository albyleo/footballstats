(() => {
  // All content stays visible if animation scripts fail or JavaScript is disabled.
  if (!window.gsap || !window.ScrollTrigger) return;
  gsap.registerPlugin(ScrollTrigger);
  const media = gsap.matchMedia();
  media.add('(prefers-reduced-motion: no-preference)', () => {
    gsap.from('.title-line', {y:65, opacity:0, duration:1.05, stagger:.14, ease:'power3.out'});
    gsap.from('.hero-intro', {y:20, opacity:0, duration:.8, delay:.4, stagger:.12});
    gsap.from('.hero-art', {opacity:0, duration:1.4, delay:.2});
    gsap.to('.pitch', {rotation:-8, y:70, ease:'none', scrollTrigger:{trigger:'.hero', start:'top top', end:'bottom top', scrub:1}});
    gsap.to('.orb-rings', {rotation:35, ease:'none', scrollTrigger:{trigger:'.hero', start:'top top', end:'bottom top', scrub:1.3}});
    gsap.utils.toArray('.reveal').forEach(element => {
      gsap.from(element, {y:45, opacity:0, duration:.85, ease:'power2.out', scrollTrigger:{trigger:element, start:'top 90%', once:true}});
    });
  });
  media.add('(min-width: 901px) and (prefers-reduced-motion: no-preference)', () => {
    document.body.classList.add('motion-desktop');
    const track = document.querySelector('.slides');
    const progress = document.querySelector('.slide-progress i');
    const counter = document.querySelector('.step-active');
    const timeline = gsap.timeline({scrollTrigger:{
      trigger:'.method', start:'top top', end:() => '+=' + window.innerWidth * 2.1,
      pin:true, scrub:1, invalidateOnRefresh:true,
      onUpdate:self => {
        gsap.set(progress, {scaleX:(1 + self.progress * 2) / 3});
        counter.textContent = String(Math.min(3, Math.floor(self.progress * 3) + 1)).padStart(2, '0');
      }
    }});
    timeline.to(track, {x:() => -(track.scrollWidth - document.documentElement.clientWidth), ease:'none', duration:3});
    timeline.to('.radar-sweep', {rotation:160, ease:'none', duration:1}, 0);
    timeline.from('.connections svg', {rotation:-12, scale:.8, duration:1}, .7);
    timeline.from('.bar-chart span', {scaleY:.15, stagger:.07, duration:.7}, 1.9);
    return () => {
      document.body.classList.remove('motion-desktop');
      counter.textContent = '01';
      progress.style.transform = '';
    };
  });
  window.addEventListener('load', () => ScrollTrigger.refresh(), {once:true});
})();
