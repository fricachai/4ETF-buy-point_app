export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: corsJsonHeaders(),
      });
    }

    if (url.pathname !== "/api/twse-stock-day") {
      return new Response("Not Found", { status: 404 });
    }

    const date = url.searchParams.get("date");
    const stockNo = url.searchParams.get("stockNo");

    if (!date || !stockNo) {
      return json({ stat: "ERROR", message: "Missing date or stockNo" }, 400);
    }

    const upstream = new URL("https://www.twse.com.tw/exchangeReport/STOCK_DAY");
    upstream.searchParams.set("response", "json");
    upstream.searchParams.set("date", date);
    upstream.searchParams.set("stockNo", stockNo);

    try {
      const response = await fetch(upstream.toString(), {
        headers: {
          accept: "application/json,text/plain,*/*",
          "user-agent": "Mozilla/5.0",
          referer: "https://www.twse.com.tw/",
          origin: "https://www.twse.com.tw",
        },
        cf: {
          cacheTtl: 300,
          cacheEverything: false,
        },
      });

      const text = await response.text();

      return new Response(text, {
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
  },
};

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
