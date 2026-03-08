/**
 * Cloudflare Worker Gateway (v0.3 sample)
 *
 * Required env vars:
 * - SLACK_SIGNING_SECRET
 * - USER_MAP (JSON string: {"U03...":"https://backend.example.com/slack/gateway"})
 */

function parsePayload(rawBody) {
  const params = new URLSearchParams(rawBody);
  const payloadParam = params.get("payload");

  if (payloadParam) {
    return {
      type: "interactive",
      data: JSON.parse(payloadParam),
    };
  }

  return {
    type: "command",
    data: Object.fromEntries(params),
  };
}

function extractUserId(payload) {
  if (payload.type === "interactive") {
    return payload.data?.user?.id;
  }
  return payload.data?.user_id;
}

function resolveBackendUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    // Allow USER_MAP values like "https://example.com/" by defaulting to gateway path.
    if (url.pathname === "/" || url.pathname === "") {
      url.pathname = "/slack/gateway";
    }
    return url.toString();
  } catch {
    return "";
  }
}

async function buildSlackResponse(backendResponse, payloadType) {
  const bodyText = await backendResponse.text();
  const headers = new Headers();

  const backendContentType = backendResponse.headers.get("Content-Type");
  if (backendContentType) {
    headers.set("Content-Type", backendContentType);
  } else if (payloadType === "interactive") {
    headers.set("Content-Type", "application/json; charset=utf-8");
  } else {
    headers.set("Content-Type", "text/plain; charset=utf-8");
  }
  headers.set("Cache-Control", "no-store");

  return new Response(bodyText, {
    status: backendResponse.status,
    headers,
  });
}

async function verifySlackSignature(request, rawBody, signingSecret) {
  const timestamp = request.headers.get("X-Slack-Request-Timestamp");
  const signature = request.headers.get("X-Slack-Signature");
  if (!timestamp || !signature) {
    return false;
  }

  const encoder = new TextEncoder();
  const base = `v0:${timestamp}:${rawBody}`;
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(signingSecret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const digest = await crypto.subtle.sign("HMAC", key, encoder.encode(base));
  const hex = Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  return signature === `v0=${hex}`;
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    const signingSecret = env.SLACK_SIGNING_SECRET;
    if (!signingSecret) {
      return new Response("Server misconfiguration", { status: 500 });
    }

    let userMap = {};
    try {
      userMap = JSON.parse(env.USER_MAP || "{}");
    } catch {
      return new Response("Invalid USER_MAP config", { status: 500 });
    }

    const rawBody = await request.text();
    const isValid = await verifySlackSignature(request, rawBody, signingSecret);
    if (!isValid) {
      return new Response("Invalid signature", { status: 401 });
    }

    let payload;
    try {
      payload = parsePayload(rawBody);
    } catch {
      return new Response("Invalid payload", { status: 400 });
    }

    const userId = extractUserId(payload);
    if (!userId) {
      return new Response("Cannot identify user", { status: 400 });
    }

    const backendUrl = resolveBackendUrl(userMap[userId]);
    if (!backendUrl) {
      return new Response("No backend for user (invalid URL)", { status: 403 });
    }

    const backendResponse = await fetch(backendUrl, {
      method: "POST",
      headers: {
        "Content-Type":
          request.headers.get("Content-Type") ||
          "application/x-www-form-urlencoded",
        "X-Slack-Request-Timestamp":
          request.headers.get("X-Slack-Request-Timestamp") || "",
        "X-Slack-Signature": request.headers.get("X-Slack-Signature") || "",
        "X-Forwarded-By": "cloudflare-gateway",
        "X-User-Id": userId,
      },
      body: rawBody,
    });

    // Build a clean response for Slack (avoid problematic hop-by-hop headers).
    return await buildSlackResponse(backendResponse, payload.type);
  },
};
