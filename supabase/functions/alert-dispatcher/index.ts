import { createClient } from "jsr:@supabase/supabase-js@2";
import {
  type AlertDeps,
  type AlertRule,
  dispatchIncidentAlerts,
  type Incident,
} from "../_shared/alerting.ts";

interface WebhookPayload {
  type: string;
  table: string;
  schema: string;
  record: Record<string, unknown> | null;
  old_record: Record<string, unknown> | null;
}

function env(name: string): string {
  return Deno.env.get(name) ?? "";
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

Deno.serve(async (req: Request): Promise<Response> => {
  try {
    if (req.method !== "POST") {
      return jsonResponse({ error: "method not allowed" }, 405);
    }

    const hookSecret = env("ALERT_DISPATCHER_SECRET");
    if (hookSecret && req.headers.get("x-webhook-secret") !== hookSecret) {
      return jsonResponse({ error: "unauthorized" }, 401);
    }

    const payload = (await req.json()) as WebhookPayload;
    if (
      payload.type !== "INSERT" ||
      payload.table !== "incidents" ||
      !payload.record
    ) {
      return jsonResponse({ skipped: true, reason: "not an incidents INSERT" });
    }

    const incident = payload.record as unknown as Incident;

    const supabase = createClient(
      env("SUPABASE_URL"),
      env("SUPABASE_SERVICE_ROLE_KEY") || env("SUPABASE_KEY"),
    );

    const { data: rules, error: rulesError } = await supabase
      .from("alert_rules")
      .select(
        "id, name, match_mode, match_value, channel, email_recipients, enabled",
      )
      .eq("enabled", true);
    if (rulesError) {
      return jsonResponse({ error: `alert_rules: ${rulesError.message}` }, 500);
    }

    const webhookUrl = env("DISCORD_WEBHOOK_URL");
    const resendApiKey = env("RESEND_API_KEY");
    const emailFrom = env("ALERT_EMAIL_FROM");

    const deps: AlertDeps = {
      async hasSuccessfulDelivery(incidentId, ruleId, channel) {
        const { data, error } = await supabase
          .from("alert_log")
          .select("id")
          .eq("incident_id", incidentId)
          .eq("rule_id", ruleId)
          .eq("channel", channel)
          .eq("success", true)
          .limit(1);
        if (error) throw new Error(`alert_log read: ${error.message}`);
        return (data?.length ?? 0) > 0;
      },
      async recordDelivery(entry) {
        const { error } = await supabase.from("alert_log").insert(entry);
        if (error) throw new Error(`alert_log insert: ${error.message}`);
      },
      async sendDiscord(payload) {
        if (!webhookUrl) throw new Error("DISCORD_WEBHOOK_URL not set");
        const res = await fetch(webhookUrl, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          throw new Error(`discord webhook: HTTP ${res.status}`);
        }
      },
      async sendEmail({ to, subject, html }) {
        if (!resendApiKey) throw new Error("RESEND_API_KEY not set");
        if (!emailFrom) throw new Error("ALERT_EMAIL_FROM not set");
        const res = await fetch("https://api.resend.com/emails", {
          method: "POST",
          headers: {
            authorization: `Bearer ${resendApiKey}`,
            "content-type": "application/json",
          },
          body: JSON.stringify({ from: emailFrom, to, subject, html }),
        });
        if (!res.ok) {
          throw new Error(`resend: HTTP ${res.status} ${await res.text()}`);
        }
      },
      sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
      now: () => new Date(),
    };

    const summary = await dispatchIncidentAlerts(
      incident,
      (rules ?? []) as AlertRule[],
      deps,
      { adminRoleId: env("DISCORD_ADMIN_ROLE_ID") },
    );

    return jsonResponse({ incident_id: incident.id, ...summary });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return jsonResponse({ error: message }, 500);
  }
});
