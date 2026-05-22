# Home Depot Order History Exporter

Exports your Home Depot purchase history to a self-contained, searchable HTML file with embedded product images. No dependencies beyond Python 3.

**Note:** The Home Depot API only returns orders from approximately the last 24 months.

## How it works

Home Depot's website blocks automation tools (Playwright, Puppeteer, etc.), so data collection happens via JavaScript you run in your own browser's DevTools console while logged in. The scripts call the same API the website uses, authenticated by your existing session.

## Step 1 — Get your order data

Log in to [homedepot.com/myaccount/purchase-history](https://www.homedepot.com/myaccount/purchase-history) in Chrome, open DevTools (`F12` or `Cmd+Option+I`), go to the **Console** tab, and run the following script. It will download `homedepot_orders.json` when finished (~30–60 seconds depending on order count).

<details>
<summary>Scraper script (click to expand)</summary>

```javascript
(async function() {
  const c = document.cookie.split('; ')
    .find(c => c.startsWith('THD_CUSTOMER='))?.slice('THD_CUSTOMER='.length);
  if (!c) { console.error('Not logged in!'); return; }

  const p = JSON.parse(atob(c.split('.')[0]));
  const userId = p.u.replace(/\s/g, '');
  const authToken = p.i;
  const customerAccountId = p.t.replace(/\s/g, '');
  const TIMEZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const BASE = `https://www.homedepot.com/oms/customer/order/v1/user/${userId}`;
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  function post(path, body) {
    return fetch(BASE + path, {
      method: 'POST', credentials: 'include',
      headers: {
        'Accept': 'application/json', 'Content-Type': 'application/json',
        'channelId': '1', 'Authorization': authToken,
        'Client': 'ocm_pd_experience_customer-account-orders-purchases',
        'channel': 'desktop', 'X-Client-App': 'PHX-Desktop'
      },
      body: JSON.stringify(body)
    }).then(async r => { const j = await r.json(); if (!r.ok) throw j; return j; });
  }

  console.log('Fetching order history year by year...');
  const allOrders = [];
  const currentYear = new Date().getFullYear();
  let emptyYears = 0;

  for (let year = currentYear; year >= 2000 && emptyYears < 2; year--) {
    const startDate = `${year}-01-01`;
    const endDate = year === currentYear
      ? new Date().toISOString().slice(0, 10)
      : `${year}-12-31`;
    let page = 1, yearOrders = 0, yearTotal = null;
    try {
      do {
        const resp = await post('/orderhistory', {
          orderHistoryRequest: { pageSize: 100, pageNumber: page, startDate, endDate, timezone: TIMEZONE }
        });
        if (!resp.orders?.length) break;
        if (yearTotal === null) yearTotal = resp.orderCount;
        allOrders.push(...resp.orders);
        yearOrders += resp.orders.length;
        if (yearOrders >= yearTotal) break;
        page++;
        await sleep(200);
      } while (true);
      emptyYears = yearOrders === 0 ? emptyYears + 1 : 0;
      console.log(`${year}: ${yearOrders} orders (total: ${allOrders.length})`);
    } catch(e) {
      emptyYears++;
    }
    await sleep(300);
  }

  // If year-by-year hits the API's date limit, fall back to monthly chunks
  if (allOrders.length === 0) {
    console.log('Trying monthly chunks...');
    for (let year = currentYear, month = new Date().getMonth() + 1;
         year >= 2000 && emptyYears < 3; ) {
      const startDate = `${year}-${String(month).padStart(2,'0')}-01`;
      const lastDay = new Date(year, month, 0).getDate();
      const endDate = `${year}-${String(month).padStart(2,'0')}-${lastDay}`;
      let monthOrders = 0;
      try {
        const resp = await post('/orderhistory', {
          orderHistoryRequest: { pageSize: 100, pageNumber: 1, startDate, endDate, timezone: TIMEZONE }
        });
        if (resp.orders?.length) { allOrders.push(...resp.orders); monthOrders = resp.orders.length; }
        emptyYears = monthOrders === 0 ? emptyYears + 1 : 0;
        if (monthOrders) console.log(`${year}-${String(month).padStart(2,'0')}: ${monthOrders} orders`);
      } catch(e) { emptyYears++; }
      await sleep(300);
      if (--month === 0) { month = 12; year--; }
    }
  }

  console.log(`\nFetching details for ${allOrders.length} orders...`);
  const results = [];
  for (let i = 0; i < allOrders.length; i++) {
    const o = allOrders[i];
    const body = o.orderOrigin === 'online'
      ? { orderDetailsRequest: { searchType: 'online', orderNumber: o.orderNumbers?.[0] || '',
            requestOriginatedFrom: 'purchaseHistory', timezone: TIMEZONE } }
      : { orderDetailsRequest: { searchType: 'instore', registerNumber: o.registerNumber,
            salesDate: (o.salesDate || '').slice(0, 10), storeNumber: o.storeNumber,
            transactionId: o.transactionId, orderNumber: '', customerAccountId,
            groupAndSortBy: { groupBy: 'fulfillmentType', filterResponse: true },
            requestOriginatedFrom: 'purchaseHistory', timezone: TIMEZONE } };
    try {
      results.push({ summary: o, detail: await post('/orderdetails', body) });
    } catch(e) {
      results.push({ summary: o, detail: null });
    }
    if ((i + 1) % 20 === 0) console.log(`Details: ${i+1}/${allOrders.length}`);
    await sleep(150);
  }

  const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' });
  const a = Object.assign(document.createElement('a'),
    { href: URL.createObjectURL(blob), download: 'homedepot_orders.json' });
  document.body.appendChild(a); a.click(); a.remove();
  console.log(`Done! Downloaded ${results.length} orders.`);
})();
```

</details>

### If the API rejects requests with a date range error

The API limits how far back you can query at once. If year-by-year queries fail, run this second script from the same console session to collect older orders. It walks backward month by month and saves to `homedepot_orders_older.json`.

<details>
<summary>Older orders script (click to expand)</summary>

```javascript
(async function() {
  const c = document.cookie.split('; ')
    .find(c => c.startsWith('THD_CUSTOMER='))?.slice('THD_CUSTOMER='.length);
  const p = JSON.parse(atob(c.split('.')[0]));
  const userId = p.u.replace(/\s/g, '');
  const authToken = p.i;
  const customerAccountId = p.t.replace(/\s/g, '');
  const TIMEZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const BASE = `https://www.homedepot.com/oms/customer/order/v1/user/${userId}`;
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  function post(path, body) {
    return fetch(BASE + path, {
      method: 'POST', credentials: 'include',
      headers: {
        'Accept': 'application/json', 'Content-Type': 'application/json',
        'channelId': '1', 'Authorization': authToken,
        'Client': 'ocm_pd_experience_customer-account-orders-purchases',
        'channel': 'desktop', 'X-Client-App': 'PHX-Desktop'
      },
      body: JSON.stringify(body)
    }).then(async r => { const j = await r.json(); if (!r.ok) throw j; return j; });
  }

  // Start from the month before the current month and walk backward
  const now = new Date();
  let year = now.getFullYear();
  let month = now.getMonth(); // 0-indexed, so this is "last month"
  if (month === 0) { month = 12; year--; }

  const allOrders = [];
  let emptyMonths = 0;

  while (year >= 2000 && emptyMonths < 3) {
    const startDate = `${year}-${String(month).padStart(2,'0')}-01`;
    const lastDay = new Date(year, month, 0).getDate();
    const endDate = `${year}-${String(month).padStart(2,'0')}-${lastDay}`;
    let monthOrders = 0;
    try {
      const resp = await post('/orderhistory', {
        orderHistoryRequest: { pageSize: 100, pageNumber: 1, startDate, endDate, timezone: TIMEZONE }
      });
      if (resp.orders?.length) { allOrders.push(...resp.orders); monthOrders = resp.orders.length; }
      emptyMonths = monthOrders === 0 ? emptyMonths + 1 : 0;
      console.log(`${year}-${String(month).padStart(2,'0')}: ${monthOrders} orders (total: ${allOrders.length})`);
    } catch(e) {
      emptyMonths++;
      console.log(`${year}-${String(month).padStart(2,'0')}: error`);
    }
    await sleep(300);
    if (--month === 0) { month = 12; year--; }
  }

  if (allOrders.length === 0) { console.log('No additional orders found.'); return; }

  console.log(`\nFetching details for ${allOrders.length} orders...`);
  const results = [];
  for (let i = 0; i < allOrders.length; i++) {
    const o = allOrders[i];
    const body = o.orderOrigin === 'online'
      ? { orderDetailsRequest: { searchType: 'online', orderNumber: o.orderNumbers?.[0] || '',
            requestOriginatedFrom: 'purchaseHistory', timezone: TIMEZONE } }
      : { orderDetailsRequest: { searchType: 'instore', registerNumber: o.registerNumber,
            salesDate: (o.salesDate || '').slice(0, 10), storeNumber: o.storeNumber,
            transactionId: o.transactionId, orderNumber: '', customerAccountId,
            groupAndSortBy: { groupBy: 'fulfillmentType', filterResponse: true },
            requestOriginatedFrom: 'purchaseHistory', timezone: TIMEZONE } };
    try {
      results.push({ summary: o, detail: await post('/orderdetails', body) });
    } catch(e) { results.push({ summary: o, detail: null }); }
    if ((i + 1) % 20 === 0) console.log(`Details: ${i+1}/${allOrders.length}`);
    await sleep(150);
  }

  const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' });
  const a = Object.assign(document.createElement('a'),
    { href: URL.createObjectURL(blob), download: 'homedepot_orders_older.json' });
  document.body.appendChild(a); a.click(); a.remove();
  console.log(`Done! Downloaded ${results.length} older orders.`);
})();
```

</details>

## Step 2 — Build the HTML report

Place `build_homedepot_html.py` in the same directory as your downloaded JSON files and run:

```bash
python3 build_homedepot_html.py
```

This reads all `homedepot_orders*.json` files in the current directory. You can also pass files explicitly:

```bash
python3 build_homedepot_html.py homedepot_orders.json homedepot_orders_older.json
```

It downloads all product images and writes `homedepot_orders.html` in the current directory. No internet connection is needed to view the file afterward.

## Output

A single `homedepot_orders.html` file (~2 MB) containing:

- All orders sorted newest first
- Product images embedded as base64 (no external requests)
- Live search by item name, brand, model number, order number, date, or store — filtering at the item level within each order
- Badges for online, in-store, and return orders
- Summary stats: order count, item count, total spend, date range

## Requirements

- Python 3.6+
- A Home Depot account with order history
- Chrome (or any browser with DevTools)
