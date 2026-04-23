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

    if (url.pathname === "/api/twse-quote") {
      return handleTwseQuote(url);
    }

    if (url.pathname === "/api/taiex-chart") {
      return handleTaiexChart(url);
    }

    return new Response("Not Found", { status: 404 });
  },
};

async function handleTwseStockDay(url) {
  const date = url.searchParams.get("date");
  const stockNo = url.searchParams.get("stockNo");

  if (!date || !stockNo) {
    return json({ stat: "ERROR", message: "Missing date or stockNo" }, 400);
  }

  const upstream = new URL("https://www.twse.com.tw/exchangeReport/STOCK_DAY");
  upstream.searchParams.set("response", "json");
  upstream.searchParams.set("date", date);
  upstream.searchParams.set("stockNo", stockNo);

  return proxyJson(upstream, {
    accept: "application/json,text/plain,*/*",
    "user-agent": "Mozilla/5.0",
    referer: "https://www.twse.com.tw/",
    origin: "https://www.twse.com.tw",
  });
}

async function handleTwseQuote(url) {
  const exCh = url.searchParams.get("ex_ch");

  if (!exCh) {
    return json({ rtcode: "9999", rtmessage: "Missing ex_ch", msgArray: [] }, 400);
  }

  const upstream = new URL("https://mis.twse.com.tw/stock/api/getStockInfo.jsp");
  upstream.searchParams.set("json", "1");
  upstream.searchParams.set("delay", "0");
  upstream.searchParams.set("ex_ch", exCh);
  upstream.searchParams.set("_", url.searchParams.get("_") || String(Date.now()));

  return proxyJson(upstream, {
    accept: "application/json,text/plain,*/*",
    "user-agent": "Mozilla/5.0",
    referer: "https://mis.twse.com.tw/stock/index.jsp",
    origin: "https://mis.twse.com.tw",
    pragma: "no-cache",
    "cache-control": "no-cache",
  }, 5);
}

async function handleTaiexChart(url) {
  const period1 = url.searchParams.get("period1");
  const period2 = url.searchParams.get("period2");
  const interval = url.searchParams.get("interval") || "1d";

  if (!period1 || !period2) {
    return json({ chart: { error: { message: "Missing period1 or period2" }, result: null } }, 400);
  }

  const headers = {
    accept: "application/json,text/plain,*/*",
    "user-agent": "Mozilla/5.0",
    referer: "https://finance.yahoo.com/",
    origin: "https://finance.yahoo.com",
  };
  const upstreams = [
    "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII",
    "https://query2.finance.yahoo.com/v8/finance/chart/%5ETWII",
  ];

  let lastErrorResponse = null;
  for (const baseUrl of upstreams) {
    const upstream = new URL(baseUrl);
    upstream.searchParams.set("interval", interval);
    upstream.searchParams.set("period1", period1);
    upstream.searchParams.set("period2", period2);
    const response = await proxyJson(upstream, headers);
    if (response.ok) return response;
    lastErrorResponse = response;
  }

  return lastErrorResponse ?? json({ stat: "ERROR", message: "Proxy fetch failed" }, 502);
}

async function proxyJson(upstream, headers, cacheTtl = 300) {
  try {
    const response = await fetch(upstream.toString(), {
      headers,
      cf: {
        cacheTtl,
        cacheEverything: false,
      },
    });

    const text = await response.text();
    const trimmed = text.trim();
    if (!trimmed) {
      return json({ stat: "ERROR", message: "Empty upstream response" }, 502);
    }
    if (trimmed.startsWith("<!DOCTYPE") || trimmed.startsWith("<html")) {
      return json({ stat: "ERROR", message: "Upstream returned HTML instead of JSON" }, 502);
    }

    return new Response(trimmed, {
      status: response.status,
      headers: corsJsonHeaders(),
    });
  } catch (error) {
    return json(
      {
        stat: "ERROR",
        message: error instanceof Error ? error.message : "Proxy fetch failed",
      },
      502,
    );
  }
}

function corsJsonHeaders() {
  return {
    "content-type": "application/json; charset=utf-8",
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET, OPTIONS",
    "access-control-allow-headers": "*",
    "cache-control": "public, max-age=300",
  };
}

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: corsJsonHeaders(),
  });
}
