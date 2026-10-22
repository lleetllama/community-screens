"""Run manually with: python tests/browser_layout.py (requires Playwright Chromium)."""
import os
import sys
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with tempfile.TemporaryDirectory() as data_dir:
    os.environ['DATA_DIR'] = data_dir
    import app
    client = app.app.test_client()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        def serve(route):
            from urllib.parse import urlsplit
            response = client.get(urlsplit(route.request.url).path)
            route.fulfill(status=response.status_code, body=response.data,
                          content_type=response.content_type)
        page.route('http://signage.test/**', serve)
        page.goto('http://signage.test/display/lobby')
        page.evaluate('document.fonts.ready')
        for width, height in [(1920, 1080), (1280, 720), (800, 600), (600, 800)]:
            page.set_viewport_size({'width': width, 'height': height})
            sizes = []
            for count in [1, 8, 20, 40, 80]:
                result = page.evaluate('''count => {
                  render(Array.from({length:count},(_,i)=>({
                    title:i%3===0?'Community gathering with music, refreshments and visiting friends':'Afternoon Bingo',
                    location:i%2===0?'Community Room, East Wing':'',start_time:'12:00'
                  })), 'No events');
                  fitEvents();
                  const listBox=list.getBoundingClientRect();
                  const rows=Array.from(list.children);
                  const problems=[];
                  for(const row of rows){
                    const box=row.getBoundingClientRect();
                    if(box.top<listBox.top-1||box.bottom>listBox.bottom+1)problems.push('row outside schedule');
                    for(const child of row.children){
                      const bounds=child.getBoundingClientRect();
                      if(bounds.top<box.top-0.5||bounds.bottom>box.bottom+0.5)problems.push('vertical clipping');
                      if(child.scrollWidth>child.clientWidth+1)problems.push('horizontal clipping');
                    }
                  }
                  return {problems,font:parseFloat(getComputedStyle(rows[0].querySelector('.event-title')).fontSize)};
                }''', count)
                assert not result['problems'], (width, height, count, result)
                sizes.append(round(result['font'], 2))
            assert sizes[-1] < sizes[0], sizes
            # Removing events must let the text grow again.
            page.evaluate("render([{title:'Bingo',location:'Hall',start_time:'12:00'}]);fitEvents()")
            assert page.locator('.event-title').evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)') >= sizes[-1]
            print(f'{width}x{height}: 1/8/20/40/80 events fit; title sizes {sizes}')
        browser.close()
