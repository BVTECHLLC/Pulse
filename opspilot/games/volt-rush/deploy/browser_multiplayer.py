"""Two browser contexts (desktop and emulated iPhone layout) over Vite -> Node proxy.
Run Vite, Node server separately, then:
  VOLT_BASE_URL=http://127.0.0.1:5173/kart/ python deploy/browser_multiplayer.py
Does not replace real iPhone Safari test or test FastAPI proxy unless BASE_URL points at portal.
"""
import os
from playwright.sync_api import sync_playwright

url=os.environ.get('VOLT_BASE_URL','http://127.0.0.1:5173/kart/')
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--enable-webgl','--use-angle=swiftshader'])
    errors=[]
    desktop=browser.new_context(viewport={'width':1280,'height':780})
    phone=browser.new_context(viewport={'width':844,'height':390},device_scale_factor=2,is_mobile=True,has_touch=True)
    host=desktop.new_page();guest=phone.new_page()
    for pg in [host,guest]:
        pg.on('pageerror',lambda err: errors.append(str(err)))
        pg.goto(url,wait_until='domcontentloaded',timeout=45000)
        pg.locator('#host').wait_for(state='visible')
    host.locator('#playerName').fill('Desktop');host.locator('#host').click()
    host.locator('#roomCode').wait_for(state='visible',timeout=15000)
    host.wait_for_function("document.querySelector('#roomCode').textContent.trim().length === 5")
    code=host.locator('#roomCode').inner_text()
    guest.locator('#playerName').fill('iPhone')
    guest.locator('#joinShow').click()
    guest.locator('#joinCode').fill(code)
    guest.locator('#join').click()
    guest.locator('#roster').get_by_text('Desktop').wait_for(timeout=15000)
    host.wait_for_function("document.querySelector('#headcount')?.textContent.includes('2 / 8')",timeout=15000)
    host.locator('#raceGo').click()
    for pg in [host,guest]:pg.locator('#hud').wait_for(state='visible',timeout=15000)
    host.locator('#countdown').wait_for(state='hidden',timeout=16000)
    guest.locator('#countdown').wait_for(state='hidden',timeout=16000)
    host.keyboard.down('ArrowUp')
    guest.locator('[data-control="gas"]').dispatch_event('pointerdown',{'pointerId':10})
    host.wait_for_timeout(3500)
    assert float(host.locator('#speed').inner_text().split()[0])>0,'Desktop speed frozen at zero'
    assert float(guest.locator('#speed').inner_text().split()[0])>0,'Phone speed frozen at zero'
    assert not errors, f'Browser crashed or client physics error: {errors}'
    host.keyboard.up('ArrowUp')
    guest.locator('[data-control="gas"]').dispatch_event('pointerup',{'pointerId':10})
    print('PASS two rendered browsers in one room after countdown, both speeds >0; no JS errors')
    desktop.close();phone.close();browser.close()
