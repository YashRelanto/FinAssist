// Supabase Edge Function: nightly cron → trigger Python training worker
// Deploy: supabase functions deploy train-forecast --no-verify-jwt
// Secrets (supabase secrets set):
//   FORECAST_CRON_SECRET=...
//   TRAINING_WORKER_URL=https://your-api.example.com

import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const TRAINING_WORKER_URL = Deno.env.get("TRAINING_WORKER_URL") ?? "";
const FORECAST_CRON_SECRET = Deno.env.get("FORECAST_CRON_SECRET") ?? "";

Deno.serve(async (req: Request) => {
  if (req.method !== "POST" && req.method !== "GET") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405,
      headers: { "Content-Type": "application/json" },
    });
  }

  if (!TRAINING_WORKER_URL || !FORECAST_CRON_SECRET) {
    return new Response(
      JSON.stringify({
        error: "Missing TRAINING_WORKER_URL or FORECAST_CRON_SECRET function secrets",
      }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
  }

  const url = `${TRAINING_WORKER_URL.replace(/\/$/, "")}/api/internal/train-forecast`;

  try {
    const workerRes = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${FORECAST_CRON_SECRET}`,
        "Content-Type": "application/json",
      },
    });

    const body = await workerRes.text();
    return new Response(body, {
      status: workerRes.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return new Response(JSON.stringify({ success: false, error: message }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }
});
