import assert from "node:assert/strict";
import test from "node:test";
import {
  type AlertDeps,
  type AlertRule,
  buildDiscordPayload,
  buildEmail,
  clearnetSourceUrl,
  COLOR_NORMAL_ORANGE,
  COLOR_WATCHLIST_RED,
  dispatchIncidentAlerts,
  displaySource,
  formatBangkok,
  type Incident,
  ruleMatches,
  TOR_SOURCE_NOTE,
} from "./alerting.ts";

const baseIncident: Incident = {
  id: "inc-1",
  victim_name: "Thai Example Co",
  group_name: "LockBit",
  sector: "Manufacturing",
  country: "TH",
  source: "ransomware.live",
  source_url: "https://example.com/victim/1",
  discovered_at: "2024-01-15T05:30:00Z",
  watchlist_hit: false,
  status: "unverified",
};

function rule(overrides: Partial<AlertRule>): AlertRule {
  return {
    id: "rule-1",
    name: "test",
    match_mode: "any_thailand",
    match_value: null,
    channel: "discord",
    email_recipients: null,
    enabled: true,
    ...overrides,
  };
}

test("ruleMatches: any_thailand matches TH case-insensitively", () => {
  assert.equal(ruleMatches(rule({}), baseIncident), true);
  assert.equal(ruleMatches(rule({}), { ...baseIncident, country: "th" }), true);
  assert.equal(
    ruleMatches(rule({}), { ...baseIncident, country: "US" }),
    false,
  );
});

test("ruleMatches: watchlist_only requires watchlist_hit", () => {
  const r = rule({ match_mode: "watchlist_only" });
  assert.equal(ruleMatches(r, baseIncident), false);
  assert.equal(ruleMatches(r, { ...baseIncident, watchlist_hit: true }), true);
});

test("ruleMatches: group is case-insensitive exact match", () => {
  const r = rule({ match_mode: "group", match_value: "lockbit" });
  assert.equal(ruleMatches(r, baseIncident), true);
  assert.equal(ruleMatches(r, { ...baseIncident, group_name: "ALPHV" }), false);
});

test("ruleMatches: sector is case-insensitive substring", () => {
  const r = rule({ match_mode: "sector", match_value: "manuf" });
  assert.equal(ruleMatches(r, baseIncident), true);
  assert.equal(
    ruleMatches(r, { ...baseIncident, sector: "Healthcare" }),
    false,
  );
});

test("ruleMatches: disabled rule never matches", () => {
  assert.equal(ruleMatches(rule({ enabled: false }), baseIncident), false);
});

test("formatBangkok converts UTC to ICT", () => {
  assert.equal(formatBangkok("2024-01-15T05:30:00Z"), "2024-01-15 12:30 ICT");
  assert.equal(formatBangkok(null), "unknown");
  assert.equal(formatBangkok("not-a-date"), "unknown");
});

test("buildDiscordPayload: watchlist hit is red with role mention", () => {
  const p = buildDiscordPayload(
    { ...baseIncident, watchlist_hit: true },
    "role-123",
  ) as {
    content?: string;
    embeds: { color: number; fields: { name: string }[] }[];
  };
  assert.equal(p.content, "<@&role-123>");
  assert.equal(p.embeds[0].color, COLOR_WATCHLIST_RED);
  assert.ok(p.embeds[0].fields.some((f) => f.name.includes("WATCHLIST")));
});

test("buildDiscordPayload: normal incident is orange without mention", () => {
  const p = buildDiscordPayload(baseIncident, "role-123") as {
    content?: string;
    embeds: { color: number }[];
  };
  assert.equal(p.content, undefined);
  assert.equal(p.embeds[0].color, COLOR_NORMAL_ORANGE);
});

test("buildEmail: subject format and watchlist row", () => {
  const normal = buildEmail(baseIncident);
  assert.equal(
    normal.subject,
    "[RansomWatch TH] Thai Example Co hit by LockBit",
  );
  assert.ok(!normal.html.includes("WATCHLIST MATCH"));

  const hit = buildEmail({ ...baseIncident, watchlist_hit: true });
  assert.ok(hit.html.includes("WATCHLIST MATCH"));
  assert.ok(hit.html.includes(baseIncident.source_url ?? ""));
});

// Real KT RESTAURANT incident values (2026-07-09, group majinahanashi).
const KT_ONION =
  "http://lthicpjqc7gkn5eq3epxndc2uig3yngvcbdya4u3m3byjod5km4yuwqd.onion/#post/blog-3";
const KT_CLEARNET =
  "https://www.ransomware.live/id/S1QgUkVTVEFVUkFOVEBtYWppbmFoYW5hc2hp";

const onionIncident: Incident = {
  ...baseIncident,
  victim_name: "KT RESTAURANT",
  group_name: "majinahanashi",
  source_url: KT_ONION,
};

test("clearnetSourceUrl: per-victim page is base64(victim@group)", () => {
  assert.equal(
    clearnetSourceUrl("KT RESTAURANT", "majinahanashi"),
    KT_CLEARNET,
  );
  // group page fallback when no victim name
  assert.equal(
    clearnetSourceUrl(null, "lockbit"),
    "https://www.ransomware.live/group/lockbit",
  );
  // no usable group -> no link
  assert.equal(clearnetSourceUrl("Some Victim", null), null);
  assert.equal(clearnetSourceUrl("Some Victim", "unknown"), null);
});

test("displaySource: .onion replaced by clearnet, flagged as tor", () => {
  const d = displaySource(onionIncident);
  assert.equal(d.tor, true);
  assert.equal(d.url, KT_CLEARNET);
  assert.ok(!d.url?.includes(".onion"));

  const clean = displaySource(baseIncident);
  assert.equal(clean.tor, false);
  assert.equal(clean.url, baseIncident.source_url);
});

test("buildDiscordPayload: onion source shows clearnet link + plain-text note", () => {
  const p = buildDiscordPayload(onionIncident, "role-123") as {
    embeds: { fields: { name: string; value: string }[] }[];
  };
  const discovered = p.embeds[0].fields.find((f) => f.name === "Discovered");
  assert.ok(discovered);
  assert.ok(discovered.value.includes(KT_CLEARNET));
  assert.ok(discovered.value.includes(TOR_SOURCE_NOTE));
  assert.ok(!discovered.value.includes(".onion"));
});

test("buildEmail: onion source shows clearnet link + plain-text note", () => {
  const { html } = buildEmail(onionIncident);
  assert.ok(html.includes(`<a href="${KT_CLEARNET}">${KT_CLEARNET}</a>`));
  // note is plain text outside the anchor
  assert.ok(html.includes(`</a> ${TOR_SOURCE_NOTE}`));
  assert.ok(!html.includes(".onion"));
});

interface MockDepsOptions {
  existingDeliveries?: boolean;
  failTimes?: number;
}

function mockDeps(opts: MockDepsOptions = {}) {
  const sent: { channel: string }[] = [];
  const recorded: { success: boolean; error: string | null }[] = [];
  let failures = opts.failTimes ?? 0;
  const deps: AlertDeps = {
    hasSuccessfulDelivery: () =>
      Promise.resolve(opts.existingDeliveries ?? false),
    recordDelivery: (entry) => {
      recorded.push({ success: entry.success, error: entry.error });
      return Promise.resolve();
    },
    sendDiscord: () => {
      sent.push({ channel: "discord" });
      if (failures > 0) {
        failures -= 1;
        return Promise.reject(new Error("discord down"));
      }
      return Promise.resolve();
    },
    sendEmail: () => {
      sent.push({ channel: "email" });
      return Promise.resolve();
    },
    sleep: () => Promise.resolve(),
    now: () => new Date("2024-01-15T06:00:00Z"),
  };
  return { deps, sent, recorded };
}

test("dispatch: channel 'both' sends discord and email", async () => {
  const { deps, sent, recorded } = mockDeps();
  const summary = await dispatchIncidentAlerts(
    baseIncident,
    [rule({ channel: "both", email_recipients: ["bd@example.com"] })],
    deps,
    { adminRoleId: "r" },
  );
  assert.deepEqual(summary, {
    matched_rules: 1,
    sent: 2,
    skipped_dedup: 0,
    failed: 0,
  });
  assert.deepEqual(sent, [{ channel: "discord" }, { channel: "email" }]);
  assert.equal(recorded.length, 2);
  assert.ok(recorded.every((r) => r.success));
});

test("dispatch: prior successful delivery is skipped (never alert twice)", async () => {
  const { deps, sent } = mockDeps({ existingDeliveries: true });
  const summary = await dispatchIncidentAlerts(baseIncident, [rule({})], deps, {
    adminRoleId: "r",
  });
  assert.equal(summary.skipped_dedup, 1);
  assert.equal(sent.length, 0);
});

test("dispatch: retries with backoff then succeeds", async () => {
  const { deps, sent, recorded } = mockDeps({ failTimes: 2 });
  const summary = await dispatchIncidentAlerts(baseIncident, [rule({})], deps, {
    adminRoleId: "r",
  });
  assert.equal(summary.sent, 1);
  assert.equal(sent.length, 3);
  assert.deepEqual(recorded, [{ success: true, error: null }]);
});

test("dispatch: all retries exhausted records failure", async () => {
  const { deps, recorded } = mockDeps({ failTimes: 99 });
  const summary = await dispatchIncidentAlerts(baseIncident, [rule({})], deps, {
    adminRoleId: "r",
  });
  assert.equal(summary.failed, 1);
  assert.equal(recorded.length, 1);
  assert.equal(recorded[0].success, false);
  assert.equal(recorded[0].error, "discord down");
});

test("dispatch: email rule without recipients is skipped", async () => {
  const { deps, sent } = mockDeps();
  const summary = await dispatchIncidentAlerts(
    baseIncident,
    [rule({ channel: "email", email_recipients: [] })],
    deps,
    { adminRoleId: "r" },
  );
  assert.equal(summary.skipped_dedup, 1);
  assert.equal(sent.length, 0);
});

test("dispatch: non-matching rules are not counted", async () => {
  const { deps } = mockDeps();
  const summary = await dispatchIncidentAlerts(
    baseIncident,
    [
      rule({ match_mode: "watchlist_only" }),
      rule({ enabled: false }),
      rule({ match_mode: "group", match_value: "ALPHV" }),
    ],
    deps,
    { adminRoleId: "r" },
  );
  assert.equal(summary.matched_rules, 0);
});
