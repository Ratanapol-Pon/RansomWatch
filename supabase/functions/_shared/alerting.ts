export interface Incident {
  id: string;
  victim_name: string;
  group_name: string | null;
  sector: string | null;
  country: string | null;
  source: string | null;
  source_url: string | null;
  discovered_at: string | null;
  watchlist_hit: boolean;
  status: string | null;
  dark_web_url?: string | null;
  alert_eligible?: boolean;
}

export interface AlertRule {
  id: string;
  name: string | null;
  match_mode: string | null;
  match_value: string | null;
  channel: string | null;
  email_recipients: string[] | null;
  enabled: boolean | null;
}

export interface AlertDeps {
  hasSuccessfulDelivery(
    incidentId: string,
    ruleId: string,
    channel: string,
  ): Promise<boolean>;
  recordDelivery(entry: {
    incident_id: string;
    rule_id: string;
    channel: string;
    sent_at: string;
    success: boolean;
    error: string | null;
  }): Promise<void>;
  sendDiscord(payload: Record<string, unknown>): Promise<void>;
  sendEmail(email: {
    to: string[];
    subject: string;
    html: string;
  }): Promise<void>;
  sleep(ms: number): Promise<void>;
  now(): Date;
}

export interface DispatchSummary {
  matched_rules: number;
  sent: number;
  skipped_dedup: number;
  failed: number;
}

export function ruleMatches(rule: AlertRule, incident: Incident): boolean {
  if (incident.alert_eligible === false) return false;
  if (rule.enabled === false) return false;
  switch (rule.match_mode) {
    case "any_thailand":
      return (incident.country ?? "").toUpperCase() === "TH";
    case "watchlist_only":
      return incident.watchlist_hit === true;
    case "group":
      return (
        !!rule.match_value &&
        (incident.group_name ?? "").toLowerCase() ===
          rule.match_value.toLowerCase()
      );
    case "sector":
      return (
        !!rule.match_value &&
        (incident.sector ?? "")
          .toLowerCase()
          .includes(rule.match_value.toLowerCase())
      );
    default:
      return false;
  }
}

const BKK_FMT = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Bangkok",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function formatBangkok(isoUtc: string | null): string {
  if (!isoUtc) return "unknown";
  const d = new Date(isoUtc);
  if (Number.isNaN(d.getTime())) return "unknown";
  const parts = Object.fromEntries(
    BKK_FMT.formatToParts(d).map((p) => [p.type, p.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute} ICT`;
}

export const COLOR_WATCHLIST_RED = 0xe74c3c;
export const COLOR_NORMAL_ORANGE = 0xe67e22;

export const TOR_SOURCE_NOTE = "(original source: Tor leak site)";

function base64Utf8(s: string): string {
  let bin = "";
  for (const b of new TextEncoder().encode(s)) bin += String.fromCharCode(b);
  return btoa(bin);
}

/**
 * Clearnet ransomware.live links. Verified in a real browser (2026-08-16):
 * ransomware.live is a hash-routed SPA — there is NO server-side /victims
 * route. Working patterns:
 *   /id/<base64("victim@group")>  per-victim page, e.g.
 *     KT RESTAURANT + majinahanashi ->
 *     https://www.ransomware.live/id/S1QgUkVTVEFVUkFOVEBtYWppbmFoYW5hc2hp
 *   /#/group/<group>              group page (fallback when uncertain)
 * Standard base64 (UTF-8), matching the site's encoding exactly.
 */
export function clearnetSourceUrl(
  victimName: string | null,
  groupName: string | null,
): string | null {
  const group = (groupName ?? "").trim();
  if (!group || group.toLowerCase() === "unknown") return null;
  const victim = (victimName ?? "").trim();
  if (victim) {
    return `https://www.ransomware.live/id/${base64Utf8(`${victim}@${group}`)}`;
  }
  return `https://www.ransomware.live/#/group/${encodeURIComponent(group)}`;
}

export interface SourceDisplay {
  url: string | null;
  tor: boolean;
}

export function isRansomwareLiveSource(incident: Incident): boolean {
  const src = (incident.source ?? "").toLowerCase();
  const url = (incident.source_url ?? "").toLowerCase();
  return (
    src.includes("ransomware") ||
    url.includes("ransomware.live") ||
    url.includes(".onion")
  );
}

/**
 * Display-ready source for alerts/bot output. ALL ransomware.live-sourced
 * incidents render the canonical clearnet /id/ (or #/group/) link — the
 * original source_url (incl. .onion) stays in incidents.source_url/raw for
 * audit. The Tor note is added only when the original link was a .onion.
 */
export function displaySource(incident: Incident): SourceDisplay {
  const url = incident.source_url;
  if (isRansomwareLiveSource(incident)) {
    const clearnet = clearnetSourceUrl(incident.victim_name, incident.group_name);
    return { url: clearnet ?? url, tor: !!url && url.includes(".onion") };
  }
  return { url, tor: false };
}

export function buildDiscordPayload(
  incident: Incident,
  adminRoleId: string,
): Record<string, unknown> {
  const hit = incident.watchlist_hit === true;
  const src = displaySource(incident);
  const srcText = `${src.url ?? "n/a"}${src.tor ? ` ${TOR_SOURCE_NOTE}` : ""}`;
  const fields = [
    {
      name: "Victim",
      value: `${incident.victim_name}${incident.sector ? ` (${incident.sector})` : ""}`,
      inline: false,
    },
    { name: "Group", value: incident.group_name ?? "unknown", inline: true },
    {
      name: "Discovered",
      value: `${formatBangkok(incident.discovered_at)} | Source: ${srcText}`,
      inline: false,
    },
  ];
  if (hit) {
    fields.push({
      name: "⚠️ WATCHLIST MATCH",
      value: `${incident.victim_name} — pipeline row created`,
      inline: false,
    });
  }
  return {
    content: hit ? `<@&${adminRoleId}>` : undefined,
    embeds: [
      {
        title: "🚨 New Ransomware Victim — Thailand",
        color: hit ? COLOR_WATCHLIST_RED : COLOR_NORMAL_ORANGE,
        fields,
        timestamp: incident.discovered_at ?? undefined,
      },
    ],
  };
}

export function buildEmail(incident: Incident): {
  subject: string;
  html: string;
} {
  const subject = `[RansomWatch TH] ${incident.victim_name} hit by ${incident.group_name ?? "unknown group"}`;
  const src = displaySource(incident);
  const srcCell = src.url
    ? `<a href="${src.url}">${src.url}</a>${src.tor ? ` ${TOR_SOURCE_NOTE}` : ""}`
    : `n/a${src.tor ? ` ${TOR_SOURCE_NOTE}` : ""}`;
  const watchlistRow = incident.watchlist_hit
    ? `<tr><td style="padding:4px 12px 4px 0;color:#c0392b"><b>⚠️ WATCHLIST MATCH</b></td><td>pipeline row created</td></tr>`
    : "";
  const html = `<!doctype html>
<html><body style="font-family:Arial,sans-serif;color:#222">
<h2 style="color:#c0392b">New Ransomware Victim — Thailand</h2>
<table>
<tr><td style="padding:4px 12px 4px 0"><b>Victim</b></td><td>${incident.victim_name}</td></tr>
<tr><td style="padding:4px 12px 4px 0"><b>Sector</b></td><td>${incident.sector ?? "unknown"}</td></tr>
<tr><td style="padding:4px 12px 4px 0"><b>Group</b></td><td>${incident.group_name ?? "unknown"}</td></tr>
<tr><td style="padding:4px 12px 4px 0"><b>Discovered</b></td><td>${formatBangkok(incident.discovered_at)}</td></tr>
<tr><td style="padding:4px 12px 4px 0"><b>Source</b></td><td>${srcCell}</td></tr>
<tr><td style="padding:4px 12px 4px 0"><b>Status</b></td><td>${incident.status ?? "unverified"}</td></tr>
${watchlistRow}
</table>
<p style="color:#777;font-size:12px">RansomWatch TH — public threat-intel aggregation. Verify via source before external use.</p>
</body></html>`;
  return { subject, html };
}

const RETRY_DELAYS_MS = [1000, 2000, 4000];

async function sendWithRetry(
  send: () => Promise<void>,
  deps: AlertDeps,
): Promise<string | null> {
  let lastError: unknown = null;
  for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
    try {
      await send();
      return null;
    } catch (err) {
      lastError = err;
      if (attempt < RETRY_DELAYS_MS.length) {
        await deps.sleep(RETRY_DELAYS_MS[attempt]);
      }
    }
  }
  return lastError instanceof Error ? lastError.message : String(lastError);
}

export async function dispatchIncidentAlerts(
  incident: Incident,
  rules: AlertRule[],
  deps: AlertDeps,
  config: { adminRoleId: string },
): Promise<DispatchSummary> {
  const summary: DispatchSummary = {
    matched_rules: 0,
    sent: 0,
    skipped_dedup: 0,
    failed: 0,
  };

  for (const rule of rules) {
    if (!ruleMatches(rule, incident)) continue;
    summary.matched_rules += 1;

    const channels =
      rule.channel === "both"
        ? ["discord", "email"]
        : rule.channel === "discord" || rule.channel === "email"
          ? [rule.channel]
          : [];

    for (const channel of channels) {
      if (await deps.hasSuccessfulDelivery(incident.id, rule.id, channel)) {
        summary.skipped_dedup += 1;
        continue;
      }

      let send: () => Promise<void>;
      if (channel === "discord") {
        const payload = buildDiscordPayload(incident, config.adminRoleId);
        send = () => deps.sendDiscord(payload);
      } else {
        const recipients = rule.email_recipients ?? [];
        if (recipients.length === 0) {
          summary.skipped_dedup += 1;
          continue;
        }
        const { subject, html } = buildEmail(incident);
        send = () => deps.sendEmail({ to: recipients, subject, html });
      }

      const error = await sendWithRetry(send, deps);
      await deps.recordDelivery({
        incident_id: incident.id,
        rule_id: rule.id,
        channel,
        sent_at: deps.now().toISOString(),
        success: error === null,
        error,
      });
      if (error === null) summary.sent += 1;
      else summary.failed += 1;
    }
  }

  return summary;
}
