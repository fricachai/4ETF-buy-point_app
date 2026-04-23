# Product Data Fetch Reuse Guide

這份文件整理目前專案的「商品最新資料抓取」做法，目標是讓另一個專案可以直接套用同一套架構。

## 目標

- 右側商品清單內的每個商品都先走同一個 proxy
- 代理層統一處理 CORS、HTML 假回應、上游不穩定
- 前端只負責選商品、顯示結果、必要時退回站內快取
- 台股 ETF / 股票與加權指數可以共用同一個資料抓取框架

## 架構

```text
前端頁面
  -> Cloudflare Worker
    -> TWSE 官方日線 API
    -> Yahoo Finance TAIEX 圖表 API
  -> 失敗時才退回站內 cache JSON
```

## 適用商品

- 台股 ETF / 股票
  - 例如 `0050`、`0056`、`00878`、`006208`
- 台灣加權指數
  - 例如 `TPE: IX0001`

## 核心原則

1. 前端不要直接只依賴單一外站端點。
2. 任何回應在 `response.json()` 之前，先驗證是不是 JSON。
3. 如果回來是 `<!DOCTYPE ...` 或 `<html`，視為上游失敗，不要繼續解析。
4. 先走 proxy，再視情況重試其他來源。
5. 只有全部官方來源都失敗時，才退回站內快取。

## 前端設定

在 HTML 注入 proxy base URL：

```html
<script>
  window.APP_CONFIG = {
    twseProxyBase: "https://your-worker.your-subdomain.workers.dev",
  };
</script>
```

在 JS 讀設定：

```js
const APP_CONFIG = window.APP_CONFIG || {};
const TWSE_PROXY_BASE =
  typeof APP_CONFIG.twseProxyBase === "string"
    ? APP_CONFIG.twseProxyBase.trim().replace(/\/+$/, "")
    : "";
```

## 共用 helper

### sleep

```js
function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
```

### 安全解析 JSON

這段很重要，用來避免 `Unexpected token '<'`。

```js
async function readJsonResponse(response, sourceLabel) {
  const contentType = response.headers.get("content-type") || "";
  const text = await response.text();

  if (!response.ok) {
    throw new Error(`${sourceLabel} HTTP ${response.status}`);
  }

  const trimmed = text.trim();
  if (!trimmed) {
    throw new Error(`${sourceLabel} returned empty response`);
  }

  if (trimmed.startsWith("<!DOCTYPE") || trimmed.startsWith("<html")) {
    throw new Error(`${sourceLabel} returned HTML instead of JSON`);
  }

  try {
    return JSON.parse(trimmed);
  } catch (error) {
    if (contentType.includes("json")) throw error;
    throw new Error(`${sourceLabel} returned non-JSON content`);
  }
}
```

### 多來源重試

```js
async function fetchJsonFromCandidates(candidates, requestOptions = {}) {
  let lastError = null;

  for (let index = 0; index < candidates.length; index += 1) {
    const candidate = candidates[index];
    const attempts = Math.max(1, Number(candidate.attempts) || 1);

    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        const response = await fetch(candidate.url, requestOptions);
        return await readJsonResponse(response, candidate.label);
      } catch (error) {
        lastError = error;
        const hasNextAttempt = attempt + 1 < attempts;
        const hasNextCandidate = index + 1 < candidates.length;
        if (hasNextAttempt || hasNextCandidate) {
          await sleep(350 * (attempt + 1));
        }
      }
    }
  }

  throw lastError ?? new Error("Fetch failed");
}
```

## 台股 ETF / 股票資料抓法

### 月資料來源

TWSE 日資料端點：

```text
https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=YYYYMM01&stockNo=股票代號
```

### 產生月份 key

```js
function getRecentMonthKeys(startYear = 2020, startMonth = 1) {
  const keys = [];
  const cursor = new Date();
  cursor.setDate(1);

  while (
    cursor.getFullYear() > startYear
    || (cursor.getFullYear() === startYear && cursor.getMonth() + 1 >= startMonth)
  ) {
    keys.push(`${cursor.getFullYear()}${String(cursor.getMonth() + 1).padStart(2, "0")}01`);
    cursor.setMonth(cursor.getMonth() - 1);
  }

  return keys;
}
```

### 日期與數字清理

```js
function parseTwseDate(value) {
  const [rocYear, month, day] = String(value || "").split("/").map(Number);
  if (!rocYear || !month || !day) return null;
  return new Date(rocYear + 1911, month - 1, day).toISOString();
}

function parseNumber(value) {
  if (value == null) return null;
  const cleaned = String(value).replace(/,/g, "").trim();
  if (!cleaned || cleaned === "--" || cleaned === "---") return null;
  return Number(cleaned);
}

function extractNameFromTitle(title, code) {
  if (!title) return code;
  const cleaned = title.replace(/\s+/g, " ").trim();
  const afterCode = cleaned.split(`${code} `)[1] || "";
  return afterCode.split(" ").find(Boolean) || code;
}
```

### 抓單月資料

```js
async function fetchTwseMonth(code, dateKey) {
  const directUrl =
    `https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=${dateKey}&stockNo=${encodeURIComponent(code)}`;

  const candidates = [];

  if (TWSE_PROXY_BASE) {
    candidates.push({
      label: "TWSE proxy",
      url: `${TWSE_PROXY_BASE}/api/twse-stock-day?date=${dateKey}&stockNo=${encodeURIComponent(code)}`,
      attempts: 2,
    });
  }

  candidates.push({
    label: "TWSE official",
    url: directUrl,
    attempts: 1,
  });

  const payload = await fetchJsonFromCandidates(candidates, { cache: "no-store" });
  if (payload.stat !== "OK") return { title: payload.title || "", rows: [] };

  const rows = (payload.data || [])
    .map((row) => ({
      date: parseTwseDate(row[0]),
      open: parseNumber(row[3]),
      high: parseNumber(row[4]),
      low: parseNumber(row[5]),
      close: parseNumber(row[6]),
      volume: parseNumber(row[1]) ?? 0,
    }))
    .filter((row) => row.date && [row.open, row.high, row.low, row.close].every(Number.isFinite));

  return { title: payload.title || "", rows };
}
```

### 合併全期間日線

```js
async function fetchTwseStockData(code) {
  const results = await Promise.all(getRecentMonthKeys().map((key) => fetchTwseMonth(code, key)));
  const nameSource = results.find((item) => item.title)?.title || "";
  const candles = results.flatMap((item) => item.rows).sort((a, b) => new Date(a.date) - new Date(b.date));
  const deduped = candles.filter((candle, index, array) => index === 0 || candle.date !== array[index - 1].date);

  if (!deduped.length) throw new Error("No official daily data");

  return {
    code,
    name: extractNameFromTitle(nameSource, code),
    candles: deduped,
  };
}
```

## 加權指數資料抓法

### 資料來源

優先順序：

1. Worker `/api/taiex-chart`
2. Yahoo Finance `query1`
3. Yahoo Finance `query2`

### 抓取函式

```js
async function fetchLiveTaiexData() {
  const period1 = Math.floor(new Date(2020, 0, 1).getTime() / 1000);
  const period2 = Math.floor(Date.now() / 1000) + 86400;
  const directUrl = `https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII?interval=1d&period1=${period1}&period2=${period2}`;
  const backupYahooUrl = `https://query2.finance.yahoo.com/v8/finance/chart/%5ETWII?interval=1d&period1=${period1}&period2=${period2}`;

  const candidates = [];

  if (TWSE_PROXY_BASE) {
    candidates.push({
      label: "market proxy",
      url: `${TWSE_PROXY_BASE}/api/taiex-chart?interval=1d&period1=${period1}&period2=${period2}`,
      attempts: 2,
    });
  }

  candidates.push(
    { label: "Yahoo Finance query1", url: directUrl, attempts: 1 },
    { label: "Yahoo Finance query2", url: backupYahooUrl, attempts: 1 },
  );

  const payload = await fetchJsonFromCandidates(candidates, {
    cache: "no-store",
    headers: {
      Accept: "application/json,text/plain,*/*",
    },
  });

  const result = payload?.chart?.result?.[0];
  const quote = result?.indicators?.quote?.[0];
  const timestamps = result?.timestamp || [];
  if (!quote || !timestamps.length) throw new Error("No official daily data");

  const candles = timestamps
    .map((timestamp, index) => ({
      date: new Date(timestamp * 1000).toISOString(),
      open: Number(quote.open?.[index]),
      high: Number(quote.high?.[index]),
      low: Number(quote.low?.[index]),
      close: Number(quote.close?.[index]),
      volume: Number(quote.volume?.[index] || 0),
    }))
    .filter((row) => row.date && [row.open, row.high, row.low, row.close].every(Number.isFinite))
    .sort((a, b) => new Date(a.date) - new Date(b.date));

  if (!candles.length) throw new Error("No official daily data");

  return { code: "TPE: IX0001", name: "台灣加權指數", candles };
}
```

## 站內快取 fallback

### 正規化快取資料

```js
function normalizeCandlePayload(rows) {
  return rows
    .map((row) => ({
      date: row.date,
      open: Number(row.open),
      high: Number(row.high),
      low: Number(row.low),
      close: Number(row.close),
      volume: Number(row.volume || 0),
    }))
    .filter((row) => row.date && [row.open, row.high, row.low, row.close].every(Number.isFinite))
    .sort((a, b) => new Date(a.date) - new Date(b.date));
}

async function fetchCachedCandles(path) {
  const response = await fetch(`${path}?ts=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const payload = await response.json();
  const candles = normalizeCandlePayload(Array.isArray(payload) ? payload : payload.candles || []);
  if (!candles.length) throw new Error("No cached data");
  return candles;
}
```

### 失敗時退回快取

```js
async function fetchInstrumentDataWithFallback(code, preferredName = "") {
  try {
    return await fetchInstrumentData(code);
  } catch (error) {
    if (code === "TPE: IX0001") {
      const candles = await fetchCachedCandles("./data/taiex.json");
      return { code, name: "台灣加權指數", candles, sourceError: error };
    }

    const candles = await fetchCachedCandles(`./data/${code}.json`);
    return { code, name: preferredName || code, candles, sourceError: error };
  }
}
```

## Worker 端點設計

建議至少提供兩個 API：

- `/api/twse-stock-day`
- `/api/taiex-chart`

### Worker 範例

```js
export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: corsJsonHeaders(),
      });
    }

    if (url.pathname === "/api/twse-stock-day") {
      return handleTwseStockDay(url);
    }

    if (url.pathname === "/api/taiex-chart") {
      return handleTaiexChart(url);
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

### Worker 重點

- 一律補 CORS header
- 上游回應先讀成 text
- 如果是 HTML，直接回 502 JSON 錯誤
- Yahoo Finance 可在 Worker 端也做 `query1` / `query2` 備援

## 前端整合入口

可用一個統一函式分流：

```js
function isMarketIndexCode(code) {
  return ["IX0001", "TPE:IX0001", "TPE: IX0001"].includes(String(code || "").trim().toUpperCase());
}

async function fetchInstrumentData(code) {
  if (isMarketIndexCode(code)) return fetchLiveTaiexData();
  return fetchTwseStockData(code);
}
```

## 驗證方式

### 測 TWSE proxy

```text
https://your-worker.your-subdomain.workers.dev/api/twse-stock-day?date=20260401&stockNo=006208
```

正常應看到：

```json
"stat":"OK"
```

### 測 TAIEX proxy

```text
https://your-worker.your-subdomain.workers.dev/api/taiex-chart?interval=1d&period1=1577808000&period2=1776902400
```

正常應看到：

```json
"chart":{"result":[...]}
```

## 套用到另一個專案時要改的地方

- `window.APP_CONFIG.twseProxyBase`
- 是否從 `2020-01` 開始抓資料
- 快取檔路徑
- 商品代號規則
- 指數代號規則
- UI 狀態訊息文案

## 建議不要省略的部分

- `readJsonResponse()`
- `fetchJsonFromCandidates()`
- proxy 優先、官方次之的順序
- 全部失敗才 fallback cache
- Worker 端對 HTML 假回應的防呆

## 參考檔案

- [app.js](D:\USB_Data\個人研究\實用分析分類\ChatGPT_個人累積\ChatGPT_Codex_專案資料夾\4檔ETF跌幅監控\app.js)
- [cloudflare-worker.js](D:\USB_Data\個人研究\實用分析分類\ChatGPT_個人累積\ChatGPT_Codex_專案資料夾\4檔ETF跌幅監控\cloudflare-worker.js)
- [wrangler.toml](D:\USB_Data\個人研究\實用分析分類\ChatGPT_個人累積\ChatGPT_Codex_專案資料夾\4檔ETF跌幅監控\wrangler.toml)
