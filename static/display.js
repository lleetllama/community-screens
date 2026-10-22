const list=document.getElementById('eventList');
let clockTime=Date.parse(window.SIGNAGE_TIME);
let clockSyncedAt=performance.now();
const dateFormat=new Intl.DateTimeFormat('en-US',{timeZone:window.SIGNAGE_TIMEZONE,weekday:'long',month:'long',day:'numeric',year:'numeric'});
const clockFormat=new Intl.DateTimeFormat('en-US',{timeZone:window.SIGNAGE_TIMEZONE,hour:'numeric',minute:'2-digit',second:'2-digit'});
function tick(){const current=new Date(clockTime+performance.now()-clockSyncedAt);document.getElementById('todayDate').textContent=dateFormat.format(current);document.getElementById('clock').textContent=clockFormat.format(current)}
function timeLabel(time){const [hour,min]=time.split(':').map(Number);return (hour%12||12)+':'+String(min).padStart(2,'0')+' '+(hour<12?'AM':'PM')}
function render(events,emptyMessage){list.replaceChildren();if(!events.length){const empty=document.createElement('div');empty.className='empty-tv';empty.textContent=emptyMessage;list.append(empty);return}for(const event of events){const row=document.createElement('div');row.className='tv-event';const time=document.createElement('span');time.className='event-time';time.textContent=timeLabel(event.start_time);const info=document.createElement('div');const title=document.createElement('span');title.className='event-title';title.textContent=event.title;info.append(title);if(event.location){const location=document.createElement('span');location.className='event-location';location.textContent=event.location;info.append(location)}row.append(time,info);list.append(row)}queueFit()}
async function refresh(){try{const response=await fetch('/api/display/'+encodeURIComponent(window.SIGNAGE_SLUG),{cache:'no-store'});if(!response.ok)throw new Error(response.status);const data=await response.json();clockTime=Date.parse(data.time);clockSyncedAt=performance.now();tick();render(data.events,data.display.empty_message);document.getElementById('bannerHeading').textContent=data.display.heading;document.getElementById('welcomeText').textContent=data.display.welcome||'Have a wonderful day!';document.getElementById('updateStatus').textContent='Live schedule'}catch(e){document.getElementById('updateStatus').textContent='Reconnecting…'}}
tick();setInterval(tick,1000);refresh();setInterval(refresh,30000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden){tick();refresh()}});

// Keep a consistent text size across rows, fitted to the most crowded row.
function fitEvents(){
  const rows=Array.from(list.querySelectorAll('.tv-event'));
  if(!rows.length||!list.clientHeight)return;
  function fits(scale){
    list.style.setProperty('--event-scale',scale);
    return rows.every(row=>{
      const box=row.getBoundingClientRect();
      const style=getComputedStyle(row);
      const availableHeight=box.height-parseFloat(style.paddingTop)-parseFloat(style.paddingBottom);
      return Array.from(row.children).every(child=>{
        const bounds=child.getBoundingClientRect();
        return bounds.height<=availableHeight+0.1&&child.scrollWidth<=child.clientWidth+1;
      });
    });
  }
  if(fits(1))return;
  let low=0,high=1;
  for(let i=0;i<14;i++){
    const middle=(low+high)/2;
    if(fits(middle))low=middle;else high=middle;
  }
  list.style.setProperty('--event-scale',low);
}
let fitFrame;
function queueFit(){cancelAnimationFrame(fitFrame);fitFrame=requestAnimationFrame(fitEvents)}
new ResizeObserver(queueFit).observe(list);
if(document.fonts)document.fonts.ready.then(queueFit);
queueFit();
