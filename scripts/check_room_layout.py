from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright
import re, json
root=Path.cwd()
Path('.layout-check').mkdir(exist_ok=True)
env=Environment(loader=FileSystemLoader('app/templates'))
html=env.get_template('rooms/detail.html').render(room=dict(name='测试玩家的牌桌',code='ABC123',seat_count=9,small_blind=5,big_blind=10,buy_in=1000,creator_id=1),current_user=dict(id=1,username='测试玩家'),viewer_is_owner=True,csrf_token='test',initial_state={},bot_strategy_options=[],url_for=lambda name,path: 'http://layout.test/static'+path)
html=re.sub(r'<script\b[^>]*>.*?</script>', '', html, flags=re.S)
layout=Path('app/static/js/room-layout.js').read_text(encoding='utf-8').replace('export function','function')
with sync_playwright() as p:
 browser=p.chromium.launch(channel="msedge")
 page=browser.new_page()
 page.route('http://layout.test/**', lambda route: route.fulfill(path=str(root/'app'/route.request.url.split('layout.test/')[1].split('?')[0])))
 for w,h in [(1440,900),(1280,720),(427,800),(390,700),(320,568)]:
  page.set_viewport_size(dict(width=w,height=h))
  page.set_content(html)
  page.evaluate(layout+';setupRoomLayout(document.querySelector("#room-app"));')
  page.evaluate('''() => {
   const mobile=innerWidth<=690;
   const pos=mobile?[[50,88],[19,78],[17,38],[13,13],[38,13],[62,13],[87,13],[83,38],[81,78]]:[[50,86],[18,73],[10,43],[16,18],[39,15],[61,15],[84,18],[90,43],[82,73]];
   const card='<span class="card card-face"><span class="card-corner">A<span>♠</span></span><span class="card-pip">♠</span></span>';
   document.querySelector('#seats').innerHTML=pos.map(([x,y],i)=>`<article class="seat ${i===0?'self-seat':''}" style="--desk-x:${x}%;--desk-y:${y}%;--mobile-x:${x}%;--mobile-y:${y}%">${i?`<div class="seat-cards card-row">${card.repeat(2)}</div>`:''}<div class="seat-plate"><div class="seat-name">测试玩家${i}</div><div class="seat-stack">1,000</div></div><div class="seat-tags"><span class="seat-tag">两对 +50</span></div></article>`).join('');
   document.querySelector('#community-cards').innerHTML=card.repeat(5);
   document.querySelector('#player-hole-cards').innerHTML=`<div class="own-cards card-row">${card.repeat(2)}</div>`;
   document.querySelector('#settlement').hidden=false;
   document.querySelector('#settlement-caption').textContent='测试玩家获胜';
   document.querySelector('#settlement-title').textContent='两对';
   document.querySelector('#settlement-awards').innerHTML='<strong class="settlement-amount">+50</strong>';
   document.querySelector('#action-controls').innerHTML='<div class="action-status"><strong>轮到你</strong></div><div class="action-row"><button class="button">弃牌</button><button class="button">跟注 100</button><button class="button">加注</button></div><div class="raise-editor"><div class="raise-presets">'+['最小','1/2池','底池','全下'].map(t=>`<button class="raise-preset">${t}</button>`).join('')+'</div><div class="raise-adjust"><input type="range" class="raise-slider"><label>加注到 <input class="raise-number" value="100"></label></div></div>';
  }''')
  page.wait_for_timeout(100)
  result=page.evaluate('''() => {
   const rect=n=>n.getBoundingClientRect(); const overlap=(a,b)=>a.left<b.right-1&&a.right>b.left+1&&a.top<b.bottom-1&&a.bottom>b.top+1;
   const plates=[...document.querySelectorAll('.seat-plate')].map(rect);
   const cards=[...document.querySelectorAll('.seat-cards .card,#community-cards .card')].map(rect);
   const table=rect(document.querySelector('.table-surface')), dock=rect(document.querySelector('.action-dock'));
   return {scroll:document.documentElement.scrollHeight>innerHeight||document.body.scrollHeight>innerHeight,collisions:cards.filter(c=>plates.some(p=>overlap(c,p))).length, tableBottom:table.bottom,dockTop:dock.top,controlsFit:rect(document.querySelector('.raise-adjust')).bottom<=dock.bottom};
  }''')
  print(w,h,result,flush=True)
  assert not result['scroll'] and not result['collisions'] and result['controlsFit'] and result['tableBottom']<=result['dockTop']+1
  stable=page.evaluate("""() => {
   const nodes=['.table-viewport','.action-dock','#community-cards'];
   const before=nodes.map(s=>JSON.stringify(document.querySelector(s).getBoundingClientRect()));
   document.querySelector('#settlement').hidden=true;
   document.querySelector('#action-controls').hidden=true;
   const after=nodes.map(s=>JSON.stringify(document.querySelector(s).getBoundingClientRect()));
   document.querySelector('#settlement').hidden=false;
   document.querySelector('#action-controls').hidden=false;
   const viewport=document.querySelector('.table-viewport').getBoundingClientRect();
   const contained=[...document.querySelectorAll('.seat-cards .card')].every(n=>{const r=n.getBoundingClientRect();return r.top>=viewport.top&&r.left>=viewport.left&&r.right<=viewport.right&&r.bottom<=viewport.bottom});
   return before.every((r,i)=>r===after[i]) && contained;
  }""")
  assert stable, 'state changes moved layout or clipped cards'
  page.click('#history-open')
  assert page.locator('#history-modal').evaluate('(d)=>d.open')
  page.keyboard.press('Escape')
  assert not page.locator('#history-modal').evaluate('(d)=>d.open')
  page.screenshot(path=f'.layout-check/{w}.png')
 browser.close()
