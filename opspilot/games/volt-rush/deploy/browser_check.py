"""Visual smoke run after Vite build and server started.

Requires: pip install playwright && playwright install chromium
Run (from game's folder, with npm run dev started):
  VOLT_BASE_URL=http://127.0.0.1:5173/kart/ python deploy/browser_check.py
Does not establish physical iPhone 60-FPS performance; still check real Safari hardware.
"""
import os
from playwright.sync_api import sync_playwright

url = os.environ.get('VOLT_BASE_URL', 'http://127.0.0.1:5173/kart/')
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--enable-webgl', '--use-angle=swiftshader'])
    for label, opts in [
        ('desktop', {'viewport': {'width': 1440, 'height': 900}}),
        ('mobile', {'viewport': {'width': 844, 'height': 390}, 'device_scale_factor': 3, 'is_mobile': True, 'has_touch': True}),
    ]:
        ctx = browser.new_context(**opts)
        page = ctx.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(url, wait_until='networkidle', timeout=45000)
        page.locator('#viewport').wait_for(state='visible')
        page.locator('#solo').click()
        page.locator('#hud').wait_for(state='visible')
        page.wait_for_timeout(4300)
        assert page.locator('#lap').is_visible(), f'{label}: no lap HUD'
        if label == 'mobile':
            assert page.locator('[data-control="right"]').is_visible(), 'Touch steer RIGHT invisible'
            assert page.locator('[data-control="gas"]').is_visible(), 'Touch accelerator invisible'
            page.locator('[data-control="gas"]').dispatch_event('pointerdown', {'pointerId': 1})
            page.locator('[data-control="right"]').dispatch_event('pointerdown', {'pointerId': 2})
            page.wait_for_timeout(800)
            page.locator('[data-control="right"]').dispatch_event('pointerup', {'pointerId': 2})
            page.locator('[data-control="gas"]').dispatch_event('pointerup', {'pointerId': 1})
        else:
            page.keyboard.down('ArrowUp')
            page.keyboard.down('ArrowRight')
            page.wait_for_timeout(800)
            page.keyboard.up('ArrowRight')
            page.keyboard.up('ArrowUp')
        assert not errors, f'{label}: JS exceptions: {errors}'
        os.makedirs('artifacts', exist_ok=True)
        page.screenshot(path=f'artifacts/volt-rush-{label}.png', full_page=True)
        print(f'PASS {label}: 3D page, race, input, screenshot, no JS exceptions')
        ctx.close()
    browser.close()
