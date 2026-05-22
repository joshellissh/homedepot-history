#!/usr/bin/env python3
"""
Build a self-contained HTML report from Home Depot order JSON files.

Usage:
    python3 build_homedepot_html.py [file1.json file2.json ...]

If no files are given, all homedepot_orders*.json files in the current
directory are used. Output is homedepot_orders.html in the current directory.

The JSON files are produced by the browser scraper scripts:
  - homedepot_orders.json        (recent orders)
  - homedepot_orders_older.json  (older orders, if a second scraper run was needed)
"""

import json
import base64
import urllib.request
import concurrent.futures
import sys
import glob
import os
from datetime import datetime

# ── Load input files ──────────────────────────────────────────────────────────
input_files = sys.argv[1:] or sorted(glob.glob('homedepot_orders*.json'))
if not input_files:
    print('No JSON files found. Pass filenames as arguments or run from the')
    print('directory containing homedepot_orders*.json files.')
    sys.exit(1)

data = []
for path in input_files:
    with open(path) as f:
        data += json.load(f)
    print(f'Loaded {path}')

data = [o for o in data if o.get('detail')]
data.sort(key=lambda o: o['detail']['salesDate'], reverse=True)
print(f'{len(data)} orders total')

# ── Download product images ───────────────────────────────────────────────────
all_urls = {
    item.get('imageUrl', '')
    for o in data
    for g in o['detail'].get('fulfillmentGroups', [])
    for item in g.get('lineItems', [])
    if item.get('imageUrl')
}

PLACEHOLDER = (
    'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmci'
    'IHZpZXdCb3g9IjAgMCAxMDAgMTAwIj48cmVjdCB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgZmls'
    'bD0iI2VlZSIvPjx0ZXh0IHg9IjUwIiB5PSI1NSIgZm9udC1zaXplPSIxMiIgdGV4dC1hbmNob3I9'
    'Im1pZGRsZSIgZmlsbD0iI2FhYSI+Tm8gaW1hZ2U8L3RleHQ+PC9zdmc+'
)

def fetch_image(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
        ct = r.headers.get('Content-Type', 'image/jpeg').split(';')[0]
        return url, f'data:{ct};base64,{base64.b64encode(raw).decode()}'
    except Exception:
        return url, None

print(f'Downloading {len(all_urls)} product images...')
img_cache = {}
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
    futures = {ex.submit(fetch_image, u): u for u in all_urls}
    done = 0
    for fut in concurrent.futures.as_completed(futures):
        url, result = fut.result()
        if result:
            img_cache[url] = result
        done += 1
        if done % 50 == 0:
            print(f'  {done}/{len(all_urls)}')
print(f'Downloaded {len(img_cache)}/{len(all_urls)} images')

# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_money(v):
    if v is None:
        return ''
    return f'${v:,.2f}'

def fmt_date(s):
    if not s:
        return ''
    try:
        d = datetime.fromisoformat(s[:10])
        return f'{d.strftime("%b")} {d.day}, {d.year}'
    except Exception:
        return s[:10]

def esc(s):
    if s is None:
        return ''
    return (str(s)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))

def get_items(order):
    return [
        item
        for g in order['detail'].get('fulfillmentGroups', [])
        for item in g.get('lineItems', [])
    ]

# ── HTML for one order card ───────────────────────────────────────────────────
def order_card(order):
    d = order['detail']
    origin = d.get('orderOrigin', '')
    store = d.get('storeName') or f"Store #{d.get('storeNumber', '?')}"
    if store == 'HOMEDEPOT.COM':
        store = 'homedepot.com'
    order_num = d.get('orderNumber', '')
    grand_total = d.get('grandTotalAmount') or 0
    is_return = grand_total < 0
    origin_badge = 'online' if origin == 'online' else 'in-store'

    order_search = esc(' '.join([
        str(d.get('orderNumber', '')),
        str(d.get('salesDate', '')),
        str(d.get('storeName') or ''),
        str(d.get('storeNumber') or ''),
    ]).lower())

    items_html = ''
    for item in get_items(order):
        img_src = img_cache.get(item.get('imageUrl', ''), PLACEHOLDER)
        desc = esc(item.get('description', 'Unknown Item'))
        brand = esc(item.get('brandName', ''))
        model = esc(item.get('modelNumber', ''))
        price = fmt_money(item.get('unitPrice'))
        qty = item.get('currentQuantity', 1)
        pip = item.get('pipSeoUrl', '')
        prod_url = esc(f'https://www.homedepot.com{pip}' if pip else '#')
        item_search = esc(' '.join([
            item.get('description', ''),
            item.get('brandName', ''),
            item.get('modelNumber', ''),
        ]).lower())
        qty_badge = f'<span class="qty">×{qty}</span>' if qty and qty > 1 else ''
        brand_line = (f'<div class="item-brand">{brand}'
                      + (f' · {model}' if model else '')
                      + '</div>') if brand else ''
        items_html += f'''
        <div class="item" data-item-search="{item_search}">
          <a href="{prod_url}" target="_blank"><img src="{img_src}" alt="{desc}" loading="lazy"></a>
          <div class="item-info">
            <a href="{prod_url}" target="_blank" class="item-name">{desc}</a>
            {brand_line}
            <div class="item-price">{price}{qty_badge}</div>
          </div>
        </div>'''

    return_badge = '<span class="badge return">Return</span>' if is_return else ''
    total_class = ' negative' if is_return else ''

    return f'''
  <div class="order" data-order-search="{order_search}">
    <div class="order-header">
      <div class="order-meta">
        <span class="order-date">{fmt_date(d.get("salesDate", ""))}</span>
        <span class="badge {origin_badge}">{origin_badge}</span>
        {return_badge}
        <span class="order-store">{esc(store)}</span>
        {f'<span class="order-num">#{esc(order_num)}</span>' if order_num else ''}
      </div>
      <div class="order-total{total_class}">{fmt_money(grand_total)}</div>
    </div>
    <div class="items">{items_html}</div>
  </div>'''

# ── Summary stats ─────────────────────────────────────────────────────────────
total_spend = sum(o['detail'].get('grandTotalAmount') or 0 for o in data)
total_items = sum(len(get_items(o)) for o in data)
dates = sorted(o['detail']['salesDate'] for o in data)
date_range = f'{fmt_date(dates[0])} – {fmt_date(dates[-1])}' if dates else ''

# ── Render ────────────────────────────────────────────────────────────────────
print('Building HTML...')
cards_html = '\n'.join(order_card(o) for o in data)

html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Home Depot Order History</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f5f5; color: #333; }}
header {{ background: #f96302; color: white; padding: 16px 24px; position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 8px rgba(0,0,0,.2); display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }}
header h1 {{ font-size: 1.2rem; font-weight: 700; white-space: nowrap; }}
.search-wrap {{ flex: 1; min-width: 200px; }}
#search {{ width: 100%; padding: 8px 12px; border: none; border-radius: 4px; font-size: 1rem; outline: none; }}
.stats {{ background: white; padding: 12px 24px; border-bottom: 1px solid #ddd; display: flex; gap: 24px; flex-wrap: wrap; font-size: 0.9rem; color: #555; }}
.stat {{ display: flex; flex-direction: column; gap: 2px; }}
.stat strong {{ font-size: 1.1rem; color: #222; }}
.results-info {{ padding: 10px 24px; font-size: 0.85rem; color: #666; }}
.orders {{ max-width: 960px; margin: 0 auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }}
.order {{ background: white; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.1); overflow: hidden; }}
.order[hidden] {{ display: none; }}
.order-header {{ padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #f0f0f0; flex-wrap: wrap; gap: 8px; }}
.order-meta {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
.order-date {{ font-weight: 600; font-size: 0.95rem; }}
.order-store {{ color: #555; font-size: 0.85rem; }}
.order-num {{ color: #888; font-size: 0.8rem; font-family: monospace; }}
.order-total {{ font-weight: 700; font-size: 1.05rem; color: #222; }}
.order-total.negative {{ color: #c62828; }}
.badge {{ font-size: 0.7rem; font-weight: 600; padding: 2px 7px; border-radius: 3px; text-transform: uppercase; letter-spacing: .04em; }}
.badge.online {{ background: #e3f2fd; color: #1565c0; }}
.badge.in-store {{ background: #e8f5e9; color: #2e7d32; }}
.badge.return {{ background: #fdecea; color: #c62828; }}
.items {{ padding: 8px 16px 12px; display: flex; flex-direction: column; gap: 10px; }}
.item {{ display: flex; gap: 12px; align-items: flex-start; padding: 6px 0; border-bottom: 1px solid #f5f5f5; }}
.item[hidden] {{ display: none; }}
.item:last-child {{ border-bottom: none; }}
.item img {{ width: 64px; height: 64px; object-fit: contain; flex-shrink: 0; border: 1px solid #eee; border-radius: 4px; background: #fafafa; }}
.item-info {{ flex: 1; min-width: 0; }}
.item-name {{ font-size: 0.88rem; line-height: 1.3; color: #333; text-decoration: none; display: block; }}
.item-name:hover {{ color: #f96302; text-decoration: underline; }}
.item-brand {{ font-size: 0.78rem; color: #888; margin-top: 2px; }}
.item-price {{ font-size: 0.88rem; font-weight: 600; color: #222; margin-top: 4px; }}
.qty {{ font-weight: 400; color: #666; font-size: 0.82rem; margin-left: 4px; }}
#no-results {{ text-align: center; padding: 40px; color: #888; display: none; }}
</style>
</head>
<body>
<header>
  <h1>🏠 Home Depot Orders</h1>
  <div class="search-wrap">
    <input id="search" type="search" placeholder="Search items, brands, order numbers…" autofocus>
  </div>
</header>
<div class="stats">
  <div class="stat"><span>Orders</span><strong>{len(data)}</strong></div>
  <div class="stat"><span>Items</span><strong>{total_items}</strong></div>
  <div class="stat"><span>Total spent</span><strong>{fmt_money(total_spend)}</strong></div>
  <div class="stat"><span>Date range</span><strong>{date_range}</strong></div>
</div>
<div class="results-info" id="results-info">Showing all {len(data)} orders</div>
<div id="no-results">No orders match your search.</div>
<div class="orders">{cards_html}</div>
<script>
const search = document.getElementById('search');
const orders = document.querySelectorAll('.order');
const info = document.getElementById('results-info');
const noResults = document.getElementById('no-results');
const total = orders.length;

search.addEventListener('input', () => {{
  const q = search.value.toLowerCase().trim();
  let visible = 0;
  orders.forEach(order => {{
    if (!q) {{
      order.hidden = false;
      order.querySelectorAll('.item').forEach(i => i.hidden = false);
      visible++;
      return;
    }}
    if (order.dataset.orderSearch.includes(q)) {{
      order.hidden = false;
      order.querySelectorAll('.item').forEach(i => i.hidden = false);
      visible++;
      return;
    }}
    let itemCount = 0;
    order.querySelectorAll('.item').forEach(item => {{
      const match = item.dataset.itemSearch.includes(q);
      item.hidden = !match;
      if (match) itemCount++;
    }});
    order.hidden = itemCount === 0;
    if (itemCount > 0) visible++;
  }});
  info.textContent = q
    ? `Showing ${{visible}} of ${{total}} orders matching "${{search.value}}"`
    : `Showing all ${{total}} orders`;
  noResults.style.display = visible === 0 ? 'block' : 'none';
}});
</script>
</body>
</html>'''

out = 'homedepot_orders.html'
with open(out, 'w') as f:
    f.write(html)
print(f'Wrote {out} ({len(html.encode()) / 1024 / 1024:.1f} MB)')
