"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { createClient, type Session } from "@supabase/supabase-js";
import {
  ArrowUpRight,
  Bell,
  Database,
  FileSearch,
  LayoutDashboard,
  ListFilter,
  LogOut,
  RefreshCw,
  Shield,
  Target,
  Plus,
  Inbox,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type Row = Record<string, any>;
type View =
  "overview" | "incidents" | "reports" | "watchlist" | "sources" | "alerts";
type FieldSpec = {
  key: string;
  label: string;
  type?: "text" | "number" | "textarea" | "select" | "checkbox";
  options?: string[];
  list?: boolean;
  required?: boolean;
};
const ATTACKS = [
  "ransomware",
  "extortion",
  "data_breach",
  "phishing",
  "bec",
  "malware",
  "ddos",
  "defacement",
  "exploitation",
  "other",
];
const CONFIDENCE = ["claimed", "reported", "confirmed", "disputed"];
const LABELS: Record<string, string> = {
  overview: "Overview",
  incidents: "Victim incidents",
  reports: "Threat reports",
  watchlist: "Watchlist",
  sources: "Source health",
  alerts: "Alerts & LINE",
  digest: "Daily digest",
  monthly: "Monthly summary",
  immediate: "Immediate alerts",
  en: "English",
  th: "Thai",
};
const label = (value: string) => LABELS[value] || value.replaceAll("_", " ");
const when = (value?: string) =>
  value
    ? new Date(value).toLocaleString("en-GB", {
        timeZone: "Asia/Bangkok",
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "Unknown";
function SafeLink({ url, text = "Source" }: { url?: string; text?: string }) {
  if (!url || !/^https?:\/\//i.test(url))
    return <span className="muted">—</span>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="link-break"
    >
      {text} <ArrowUpRight size={13} style={{ display: "inline" }} />
    </a>
  );
}
function Badge({ value }: { value: string }) {
  return <span className={`badge ${value}`}>{label(value)}</span>;
}
function Empty({ text }: { text: string }) {
  return (
    <div className="empty">
      <Inbox size={30} />
      <p>{text}</p>
    </div>
  );
}

function Form({
  fields,
  initial,
  onSave,
  submit = "Save changes",
}: {
  fields: FieldSpec[];
  initial: Row;
  onSave: (values: Row) => Promise<void>;
  submit?: string;
}) {
  const [values, setValues] = useState<Row>(() =>
    Object.fromEntries(
      fields.map((f) => [
        f.key,
        f.list
          ? (initial[f.key] || []).join(", ")
          : (initial[f.key] ?? (f.type === "checkbox" ? false : "")),
      ]),
    ),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = { ...values };
      fields.forEach((f) => {
        if (f.list)
          body[f.key] = String(body[f.key])
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean);
        else if (f.type === "number") body[f.key] = Number(body[f.key]);
      });
      await onSave(body);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={save} className="stack">
      {error && (
        <div role="alert" className="error-banner">
          {error}
        </div>
      )}
      <div className="form-grid">
        {fields.map((f) => (
          <label key={f.key} className={f.type === "textarea" ? "full" : ""}>
            {f.label}
            {f.type === "select" ? (
              <select
                value={values[f.key]}
                onChange={(e) =>
                  setValues({ ...values, [f.key]: e.target.value })
                }
              >
                {f.options?.map((v) => (
                  <option key={v} value={v}>
                    {label(v)}
                  </option>
                ))}
              </select>
            ) : f.type === "textarea" ? (
              <textarea
                value={values[f.key]}
                onChange={(e) =>
                  setValues({ ...values, [f.key]: e.target.value })
                }
              />
            ) : f.type === "checkbox" ? (
              <input
                type="checkbox"
                checked={!!values[f.key]}
                onChange={(e) =>
                  setValues({ ...values, [f.key]: e.target.checked })
                }
              />
            ) : (
              <input
                required={f.required}
                type={f.type || "text"}
                value={values[f.key]}
                onChange={(e) =>
                  setValues({ ...values, [f.key]: e.target.value })
                }
              />
            )}
          </label>
        ))}
      </div>
      <Button disabled={busy} type="submit">
        {busy ? "Saving…" : submit}
      </Button>
    </form>
  );
}

export default function Dashboard() {
  const supabase = useMemo(() => {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
    return url && key ? createClient(url, key) : null;
  }, []);
  const [session, setSession] = useState<Session | null>(null);
  const requestVersion = useRef(0);
  const [authReady, setAuthReady] = useState(false);
  const [role, setRole] = useState("");
  const [view, setView] = useState<View>("overview");
  const [data, setData] = useState<Row>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [attack, setAttack] = useState("");
  const [country, setCountry] = useState("");
  const [days, setDays] = useState(30);
  const [pending, setPending] = useState(false);
  const [offset, setOffset] = useState(0);
  const [loadedAt, setLoadedAt] = useState("");
  const [modal, setModal] = useState<{ kind: string; row: Row } | null>(null);
  const canEdit = role === "admin" || role === "analyst";
  useEffect(() => {
    if (!supabase) {
      setAuthReady(true);
      return;
    }
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setAuthReady(true);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      if (!next) {
        requestVersion.current += 1;
        setData({});
        setRole("");
        setModal(null);
      }
    });
    return () => data.subscription.unsubscribe();
  }, [supabase]);
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(q);
      setOffset(0);
    }, 350);
    return () => clearTimeout(timer);
  }, [q]);
  const api = useCallback(
    async (path: string, method = "GET", body?: Row) => {
      if (!session) throw new Error("Sign in to continue");
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api${path}`,
        {
          method,
          headers: {
            Authorization: `Bearer ${session.access_token}`,
            ...(body ? { "Content-Type": "application/json" } : {}),
          },
          body: body ? JSON.stringify(body) : undefined,
          cache: "no-store",
        },
      );
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : "Check the values and try again.",
        );
      return result;
    },
    [session],
  );
  const load = useCallback(async () => {
    if (!session) return;
    const version = ++requestVersion.current;
    setLoading(true);
    setError("");
    try {
      const me = await api("/me");
      if (version !== requestVersion.current) return;
      setRole(me.role);
      let result: Row;
      if (view === "overview") {
        const [summary, latest] = await Promise.all([
          api(`/summary?days=${days}`),
          api(`/incidents?days=${days}&limit=5`),
        ]);
        result = { ...summary, latest: latest.items };
      } else if (view === "incidents" || view === "reports") {
        const params = new URLSearchParams({
          q: query,
          country,
          days: String(days),
          offset: String(offset),
          limit: "25",
        });
        if (attack) params.set("attack_type", attack);
        if (view === "reports" && pending) params.set("needs_review", "true");
        result = await api(`/${view}?${params}`);
      } else if (view === "alerts") {
        const [groups, rules, deliveries] = await Promise.all([
          api("/line/groups"),
          api("/alert-rules"),
          api("/line/deliveries"),
        ]);
        result = { groups, rules, deliveries };
      } else result = { items: await api(`/${view}`) };
      if (version !== requestVersion.current) return;
      setData(result);
      setLoadedAt(new Date().toISOString());
    } catch (err) {
      if (version !== requestVersion.current) return;
      setData({});
      setError((err as Error).message);
    } finally {
      if (version === requestVersion.current) setLoading(false);
    }
  }, [session, api, view, days, query, country, offset, attack, pending]);
  useEffect(() => {
    setData({});
    void load();
    const timer = setInterval(() => void load(), 60000);
    return () => {
      clearInterval(timer);
      requestVersion.current += 1;
    };
  }, [load]);
  async function signIn(event: FormEvent) {
    event.preventDefault();
    if (!supabase) return;
    setAuthBusy(true);
    setError("");
    try {
      const result = await supabase.auth.signInWithPassword({
        email,
        password,
      });
      if (result.error) setError(result.error.message);
    } catch {
      setError("Could not connect to sign-in. Please try again.");
    } finally {
      setPassword("");
      setAuthBusy(false);
    }
  }
  async function show(kind: string, row: Row) {
    try {
      setModal({
        kind,
        row:
          kind === "incident" || kind === "report"
            ? await api(
                `/${kind === "incident" ? "incidents" : "reports"}/${row.id}`,
              )
            : row,
      });
    } catch (err) {
      setError((err as Error).message);
    }
  }
  async function save(path: string, method: string, body: Row) {
    await api(path, method, body);
    setModal(null);
    await load();
  }
  const nav = [
    { key: "overview", icon: LayoutDashboard },
    { key: "incidents", icon: Shield },
    { key: "reports", icon: FileSearch },
    ...(canEdit ? [{ key: "watchlist", icon: Target }] : []),
    { key: "sources", icon: Database },
    ...(role === "admin" ? [{ key: "alerts", icon: Bell }] : []),
  ];
  const items: Row[] = data.items || [];
  const watchFields: FieldSpec[] = [
    { key: "name", label: "Company", required: true },
    { key: "priority", label: "Priority (1–3)", type: "number" },
    { key: "aliases", label: "Aliases, separated by commas", list: true },
    { key: "domains", label: "Domains, separated by commas", list: true },
    { key: "notes", label: "Private notes", type: "textarea" },
  ];
  function recordsTable(rows: Row[], isReport = false) {
    return rows.length ? (
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{isReport ? "Report" : "Organization"}</th>
              <th>Attack type</th>
              <th>Confidence</th>
              <th>Published · ICT</th>
              <th>Source</th>
              <th>Dark web URL</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <button
                    className="title-button"
                    onClick={() =>
                      void show(isReport ? "report" : "incident", row)
                    }
                  >
                    {row.title || row.victim_name}
                  </button>
                  <div className="small muted">
                    {isReport
                      ? label(row.kind)
                      : `${row.country || "Country unknown"} · ${row.group_name || "Actor unknown"}`}
                    {row.needs_review && (
                      <>
                        {" "}
                        · <Badge value="pending" />
                      </>
                    )}
                    {row.watchlist_hit && <> · Watchlist match</>}
                  </div>
                </td>
                <td>
                  {row.attack_types.map((t: string) => (
                    <Badge key={t} value={t} />
                  ))}
                </td>
                <td>
                  <Badge value={row.confidence} />
                </td>
                <td className="small">{when(row.published_at)}</td>
                <td>
                  <SafeLink url={row.source_url} text={row.source} />
                </td>
                <td>
                  {row.dark_web_url ? (
                    <SafeLink url={row.dark_web_url} text="Onion link" />
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ) : (
      <Empty
        text={
          loading
            ? "Loading records…"
            : "No records match this view. Try a different period or filter."
        }
      />
    );
  }
  if (!authReady)
    return (
      <div className="login">
        <p>Loading your workspace…</p>
      </div>
    );
  if (!session)
    return (
      <main className="login">
        <section className="panel login-box">
          <div className="brand" style={{ marginBottom: "2rem" }}>
            <Shield size={30} />
            <span>RansomWatch</span>
          </div>
          <p className="eyebrow">Threat intelligence workspace</p>
          <h1>Stay ahead of the next conversation.</h1>
          <p className="muted">
            Sourced incidents, emerging threats, and customer follow-up in one
            place.
          </p>
          {!supabase ? (
            <div className="notice">
              Sign-in is not configured yet. Ask your administrator to connect
              this dashboard to your Supabase project.
            </div>
          ) : (
            <form onSubmit={signIn}>
              <label>
                Email
                <input
                  autoComplete="username"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </label>
              <label>
                Password
                <input
                  autoComplete="current-password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>
              <Button disabled={authBusy}>
                {authBusy ? "Signing in…" : "Sign in"}
              </Button>
              <small>Access is limited to invited workspace members.</small>
            </form>
          )}
          {error && (
            <div role="alert" className="error-banner">
              {error}
            </div>
          )}
        </section>
      </main>
    );
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <Shield size={27} />
          <span>RansomWatch</span>
        </div>
        <nav aria-label="Main navigation">
          {nav.map(({ key, icon: Icon }) => (
            <button
              key={key}
              className={`navitem ${view === key ? "active" : ""}`}
              aria-current={view === key ? "page" : undefined}
              onClick={() => {
                setView(key as View);
                setOffset(0);
              }}
            >
              <Icon size={19} />
              {LABELS[key]}
            </button>
          ))}
        </nav>
        <div className="footer-note">
          Public-source intelligence
          <br />
          Bangkok · UTC+7
          <br />
          <span>Claims remain labeled until reviewed.</span>
        </div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Threat monitoring / Thailand</p>
            <h1>{LABELS[view]}</h1>
            <span className="small muted">
              {loadedAt
                ? `Updated ${when(loadedAt)} ICT`
                : "Connecting to your workspace"}
            </span>
          </div>
          <div className="row">
            <span className="badge role-label">
              {role || "Checking access"}
            </span>
            <Button
              variant="outline"
              size="icon"
              title="Refresh"
              aria-label="Refresh dashboard"
              disabled={loading}
              onClick={() => void load()}
            >
              <RefreshCw size={17} />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Sign out"
              title="Sign out"
              onClick={() => void supabase?.auth.signOut()}
            >
              <LogOut size={18} />
            </Button>
          </div>
        </header>
        {error && (
          <div role="alert" className="error-banner">
            {error} <button onClick={() => void load()}>Retry</button>
          </div>
        )}
        {(view === "overview" ||
          view === "incidents" ||
          view === "reports") && (
          <div className="toolbar">
            <select
              aria-label="Time period"
              value={days}
              onChange={(e) => {
                setDays(Number(e.target.value));
                setOffset(0);
              }}
            >
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
              <option value={365}>Last year</option>
            </select>
            {view !== "overview" && (
              <>
                <label className="sr-only" htmlFor="search">
                  Search
                </label>
                <input
                  id="search"
                  placeholder={
                    view === "incidents"
                      ? "Search organizations…"
                      : "Search threat reports…"
                  }
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
                <select
                  aria-label="Attack type"
                  value={attack}
                  onChange={(e) => {
                    setAttack(e.target.value);
                    setOffset(0);
                  }}
                >
                  <option value="">All attack types</option>
                  {ATTACKS.map((t) => (
                    <option key={t} value={t}>
                      {label(t)}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="Country"
                  value={country}
                  onChange={(e) => {
                    setCountry(e.target.value);
                    setOffset(0);
                  }}
                >
                  <option value="">All countries</option>
                  <option value="TH">Thailand</option>
                  <option value="JP">Japan</option>
                  <option value="KR">South Korea</option>
                  <option value="US">United States</option>
                </select>
                {view === "reports" && (
                  <Button
                    variant={pending ? "default" : "outline"}
                    onClick={() => {
                      setPending(!pending);
                      setOffset(0);
                    }}
                  >
                    <ListFilter size={16} />
                    Needs review
                  </Button>
                )}
              </>
            )}
          </div>
        )}
        {view === "overview" && (
          <>
            <section className="metrics">
              {[
                [
                  "Victim incidents",
                  data.incidents,
                  "Observed in selected period",
                ],
                [
                  "Threat reports",
                  data.reports,
                  "News, campaigns & advisories",
                ],
                [
                  "Awaiting review",
                  data.review_pending,
                  "Across the review queue",
                ],
                [
                  "Watchlist matches",
                  data.watchlist_hits,
                  canEdit ? "Companies you follow" : "Available to analysts",
                ],
              ].map(([title, count, note]) => (
                <div className="panel metric" key={title}>
                  <p>{title}</p>
                  <strong>
                    {count == null ? "—" : Number(count).toLocaleString()}
                  </strong>
                  <p>{note}</p>
                </div>
              ))}
            </section>
            <div className="twocol">
              <section className="panel">
                <div className="row spaced">
                  <h2>Incident activity</h2>
                  <span className="small muted">
                    First observed · Bangkok date
                  </span>
                </div>
                {data.timeline?.length ? (
                  <div className="chart">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={data.timeline}>
                        <defs>
                          <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
                            <stop
                              offset="0%"
                              stopColor="#52dbc5"
                              stopOpacity={0.3}
                            />
                            <stop
                              offset="100%"
                              stopColor="#52dbc5"
                              stopOpacity={0}
                            />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke="#26364b" vertical={false} />
                        <XAxis
                          dataKey="date"
                          tick={{ fill: "#9aaec7", fontSize: 12 }}
                          tickFormatter={(s) => String(s).slice(5)}
                        />
                        <YAxis
                          allowDecimals={false}
                          tick={{ fill: "#9aaec7", fontSize: 12 }}
                          width={30}
                        />
                        <Tooltip
                          contentStyle={{
                            background: "#172438",
                            border: "1px solid #344960",
                            borderRadius: 8,
                          }}
                        />
                        <Area
                          type="monotone"
                          dataKey="count"
                          name="Incidents"
                          stroke="#52dbc5"
                          strokeWidth={2}
                          fill="url(#fill)"
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <Empty text="Activity will appear as incidents are collected." />
                )}
              </section>
              <section className="panel">
                <h2>Attack types</h2>
                {data.attack_types?.length ? (
                  data.attack_types.map((item: Row) => (
                    <div key={item.type} style={{ margin: "1rem 0" }}>
                      <div className="row spaced">
                        <span>{label(item.type)}</span>
                        <strong>{item.count}</strong>
                      </div>
                      <div className="legend-bar">
                        <span
                          style={{
                            width: `${Math.min(100, (item.count / Math.max(1, data.incidents)) * 100)}%`,
                          }}
                        />
                      </div>
                    </div>
                  ))
                ) : (
                  <Empty text="No incident categories yet." />
                )}
                <small>One incident can have multiple attack types.</small>
              </section>
            </div>
            <section className="panel">
              <div className="row spaced">
                <h2>Latest victim reports</h2>
                <Button variant="ghost" onClick={() => setView("incidents")}>
                  View all <ArrowUpRight size={16} />
                </Button>
              </div>
              {recordsTable(data.latest || [])}
            </section>
            <p className="small muted">
              Counts reflect collected public reports, not all attacks.
              Vulnerability advisories are counted separately.
            </p>
          </>
        )}
        {(view === "incidents" || view === "reports") && (
          <section className="panel">
            {recordsTable(items, view === "reports")}
            <div className="pagination">
              <span>
                {(data.total || 0).toLocaleString()} records
                {loading ? " · Loading…" : ""}
              </span>
              <div className="row">
                <Button
                  variant="outline"
                  disabled={!offset || loading}
                  onClick={() => setOffset(Math.max(0, offset - 25))}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  disabled={offset + 25 >= (data.total || 0) || loading}
                  onClick={() => setOffset(offset + 25)}
                >
                  Next
                </Button>
              </div>
            </div>
          </section>
        )}
        {view === "watchlist" && (
          <section className="panel">
            <div className="row spaced">
              <h2>Customer & prospect watchlist</h2>
              <Button
                onClick={() =>
                  setModal({ kind: "watch", row: { priority: 1 } })
                }
              >
                <Plus size={16} />
                Add company
              </Button>
            </div>
            {items.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Company</th>
                      <th>Domains & aliases</th>
                      <th>Priority</th>
                      <th>Private notes</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((row) => (
                      <tr key={row.id}>
                        <td>{row.name}</td>
                        <td>
                          {[
                            ...(row.domains || []),
                            ...(row.aliases || []),
                          ].join(", ") || "—"}
                        </td>
                        <td>{row.priority}</td>
                        <td>{row.notes || "—"}</td>
                        <td>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setModal({ kind: "watch", row })}
                          >
                            Edit
                          </Button>{" "}
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={async () => {
                              if (
                                window.confirm(
                                  `Remove ${row.name} from the watchlist?`,
                                )
                              ) {
                                try {
                                  await api(`/watchlist/${row.id}`, "DELETE");
                                  await load();
                                } catch (err) {
                                  setError((err as Error).message);
                                }
                              }
                            }}
                          >
                            Remove
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty text="Add a company and its known aliases or domains to start matching incidents." />
            )}
          </section>
        )}
        {view === "sources" && (
          <section className="panel">
            <h2>Collection status</h2>
            {items.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Source</th>
                      <th>Status</th>
                      <th>Last success · ICT</th>
                      <th>Fetched / new</th>
                      <th>Rejected</th>
                      <th>Next retry · ICT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((row) => (
                      <tr key={row.source}>
                        <td>
                          <strong>{row.source}</strong>
                          <div className="small muted">
                            {row.last_error || "No current error"}
                          </div>
                        </td>
                        <td>
                          <Badge value={row.status} />
                          {row.stale && <Badge value="stale" />}
                        </td>
                        <td>{when(row.last_success_at)}</td>
                        <td>
                          {row.fetched} / {row.inserted}
                        </td>
                        <td>{row.rejected}</td>
                        <td>{when(row.next_retry_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty text="Source health appears after the collector runs." />
            )}
            <p className="small muted" style={{ marginTop: "1rem" }}>
              Health shown for the intelligence feeds. Ransomware polling is
              recorded in the worker logs.
            </p>
          </section>
        )}
        {view === "alerts" && (
          <>
            <section className="panel">
              <h2>LINE groups</h2>
              <p className="muted">
                Invite the Official Account into a group. It appears here for
                activation. Private watchlist notes are never included in group
                messages.
              </p>
              {data.groups?.length ? (
                data.groups.map((row: Row) => (
                  <div className="panel" key={row.group_id}>
                    <div className="row spaced">
                      <div>
                        <strong>{row.name}</strong>{" "}
                        <Badge
                          value={row.active && row.joined ? "ok" : "pending"}
                        />
                        <div className="small muted">
                          {label(row.delivery_mode)} · {label(row.language)} ·{" "}
                          {row.digest_hour}:00 Bangkok
                        </div>
                      </div>
                      <Button
                        variant="outline"
                        onClick={() => setModal({ kind: "line", row })}
                      >
                        Configure
                      </Button>
                    </div>
                  </div>
                ))
              ) : (
                <Empty text="No LINE groups registered yet. Invite the bot after its webhook is configured." />
              )}
            </section>
            <section className="panel">
              <div className="row spaced">
                <h2>Discord & email rules</h2>
                <Button
                  variant="outline"
                  onClick={() =>
                    setModal({
                      kind: "rule",
                      row: {
                        channel: "discord",
                        match_mode: "any_thailand",
                        enabled: true,
                      },
                    })
                  }
                >
                  <Plus size={16} />
                  Add rule
                </Button>
              </div>
              {data.rules?.map((row: Row) => (
                <div
                  className="row spaced"
                  key={row.id}
                  style={{
                    padding: ".75rem 0",
                    borderBottom: "1px solid var(--border)",
                  }}
                >
                  <div>
                    {row.name || "Unnamed rule"} <Badge value={row.channel} />
                    <span className="small muted">
                      {row.enabled ? "Enabled" : "Paused"}
                    </span>
                  </div>
                  <Button
                    variant="ghost"
                    onClick={() => setModal({ kind: "rule", row })}
                  >
                    Edit
                  </Button>
                </div>
              ))}
              {!data.rules?.length && (
                <Empty text="No Discord or email rules configured." />
              )}
            </section>
            <section className="panel">
              <h2>Recent LINE deliveries</h2>
              {data.deliveries?.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Group</th>
                        <th>Delivery</th>
                        <th>Sent · ICT</th>
                        <th>Attempts</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.deliveries.map((row: Row) => (
                        <tr key={row.id}>
                          <td>
                            {data.groups.find(
                              (g: Row) => g.group_id === row.group_id,
                            )?.name || "Group"}
                          </td>
                          <td>{row.delivery_key}</td>
                          <td>{when(row.sent_at)}</td>
                          <td>{row.attempts}</td>
                          <td>
                            {row.sent_at ? "Sent" : row.error || "Queued"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty text="No deliveries yet." />
              )}
            </section>
          </>
        )}
        <Dialog open={!!modal} onOpenChange={(open) => !open && setModal(null)}>
          <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
            <DialogHeader>
              <DialogTitle>
                {modal
                  ? (
                      {
                        incident: modal.row.victim_name,
                        report: modal.row.title,
                        watch: modal.row.id ? "Edit company" : "Add company",
                        line: "LINE group settings",
                        rule: "Alert rule",
                        promotion: "Create a victim incident",
                      } as Row
                    )[modal.kind]
                  : "Details"}
              </DialogTitle>
              <DialogDescription>
                {modal?.kind === "incident" || modal?.kind === "report"
                  ? "Source evidence and review status"
                  : "Changes apply to this workspace."}
              </DialogDescription>
            </DialogHeader>
            {modal && (
              <>
                {(modal.kind === "incident" || modal.kind === "report") && (
                  <>
                    <div>
                      {modal.row.attack_types.map((t: string) => (
                        <Badge key={t} value={t} />
                      ))}
                      <Badge value={modal.row.confidence} />
                    </div>
                    <p>
                      {modal.row.description || "No source summary available."}
                    </p>
                    <dl className="detail-grid">
                      <div>
                        <dt>Published · ICT</dt>
                        <dd>{when(modal.row.published_at)}</dd>
                      </div>
                      <div>
                        <dt>First observed · ICT</dt>
                        <dd>{when(modal.row.discovered_at)}</dd>
                      </div>
                      <div>
                        <dt>Country</dt>
                        <dd>{modal.row.country || "Unknown"}</dd>
                      </div>
                      <div>
                        <dt>Attack date</dt>
                        <dd>{modal.row.attack_date || "Not established"}</dd>
                      </div>
                      <div>
                        <dt>Source</dt>
                        <dd>
                          <SafeLink
                            url={modal.row.source_url}
                            text={modal.row.source_url}
                          />
                        </dd>
                      </div>
                      <div>
                        <dt>Dark web URL</dt>
                        <dd>
                          <SafeLink
                            url={modal.row.dark_web_url}
                            text={modal.row.dark_web_url}
                          />
                        </dd>
                      </div>
                      <div>
                        <dt>CVEs</dt>
                        <dd>{modal.row.cve_ids.join(", ") || "—"}</dd>
                      </div>
                      <div>
                        <dt>Affected products</dt>
                        <dd>{modal.row.affected_products.join(", ") || "—"}</dd>
                      </div>
                    </dl>
                    {modal.row.sources?.length > 0 && (
                      <div>
                        <h3>Supporting sources</h3>
                        {modal.row.sources.map((s: Row) => (
                          <p key={s.id}>
                            <SafeLink url={s.source_url} text={s.source} />{" "}
                            <span className="small muted">
                              {when(s.published_at)}
                            </span>
                          </p>
                        ))}
                      </div>
                    )}
                    {modal.kind === "report" && canEdit && (
                      <>
                        <h3>Review this report</h3>
                        <Form
                          key={modal.row.id}
                          initial={modal.row}
                          fields={[
                            {
                              key: "kind",
                              label: "Record kind",
                              type: "select",
                              options: ["news", "campaign", "advisory"],
                            },
                            {
                              key: "confidence",
                              label: "Confidence",
                              type: "select",
                              options: CONFIDENCE,
                            },
                            {
                              key: "country",
                              label: "Country code (leave blank if unknown)",
                            },
                            {
                              key: "attack_types",
                              label: "Attack types, separated by commas",
                              list: true,
                            },
                            {
                              key: "dark_web_url",
                              label: "Dark web URL (optional)",
                            },
                            {
                              key: "needs_review",
                              label: "Keep in review queue",
                              type: "checkbox",
                            },
                          ]}
                          onSave={(body) =>
                            save(`/reports/${modal.row.id}`, "PATCH", {
                              ...body,
                              country: body.country || null,
                              dark_web_url: body.dark_web_url || null,
                            })
                          }
                        />
                        {modal.row.kind !== "advisory" &&
                          !modal.row.promoted_incident_id && (
                            <Button
                              variant="outline"
                              onClick={() =>
                                setModal({ kind: "promotion", row: modal.row })
                              }
                            >
                              Create a victim incident from evidence
                            </Button>
                          )}
                        {modal.row.promoted_incident_id && (
                          <p className="notice">
                            A victim incident has already been linked to this
                            report.
                          </p>
                        )}
                      </>
                    )}
                  </>
                )}
                {modal.kind === "watch" && (
                  <Form
                    initial={modal.row}
                    fields={watchFields}
                    onSave={(body) =>
                      save(
                        `/watchlist${modal.row.id ? `/${modal.row.id}` : ""}`,
                        modal.row.id ? "PUT" : "POST",
                        body,
                      )
                    }
                  />
                )}
                {modal.kind === "promotion" && (
                  <>
                    <p className="notice">
                      Enter only facts supported by the source. This creates a
                      reviewed incident without sending a historical alert.
                    </p>
                    <Form
                      initial={{
                        ...modal.row,
                        confidence: "reported",
                        country: modal.row.country || "",
                      }}
                      fields={[
                        {
                          key: "victim_name",
                          label: "Victim organization",
                          required: true,
                        },
                        {
                          key: "country",
                          label: "Country code",
                          required: true,
                        },
                        { key: "group_name", label: "Actor (optional)" },
                        { key: "sector", label: "Sector (optional)" },
                        {
                          key: "attack_date",
                          label: "Attack date YYYY-MM-DD (optional)",
                        },
                        {
                          key: "attack_types",
                          label: "Attack types, separated by commas",
                          list: true,
                          required: true,
                        },
                        {
                          key: "confidence",
                          label: "Confidence",
                          type: "select",
                          options: CONFIDENCE,
                        },
                      ]}
                      submit="Create incident"
                      onSave={(body) =>
                        save(`/reports/${modal.row.id}/promote`, "POST", {
                          ...body,
                          attack_date: body.attack_date || null,
                          group_name: body.group_name || null,
                          sector: body.sector || null,
                        })
                      }
                    />
                  </>
                )}
                {modal.kind === "line" && (
                  <Form
                    initial={modal.row}
                    fields={[
                      { key: "name", label: "Group name", required: true },
                      {
                        key: "active",
                        label: "Activate this group",
                        type: "checkbox",
                      },
                      {
                        key: "language",
                        label: "Language",
                        type: "select",
                        options: ["en", "th"],
                      },
                      {
                        key: "delivery_mode",
                        label: "Delivery",
                        type: "select",
                        options: ["monthly", "digest", "immediate"],
                      },
                      {
                        key: "countries",
                        label: "Country codes (blank = all)",
                        list: true,
                      },
                      {
                        key: "attack_types",
                        label: "Attack types (blank = all)",
                        list: true,
                      },
                      {
                        key: "include_global_reports",
                        label: "Include global advisories",
                        type: "checkbox",
                      },
                      {
                        key: "digest_hour",
                        label: "Summary hour · Bangkok (0–23)",
                        type: "number",
                      },
                      {
                        key: "quiet_start",
                        label: "Quiet hours start (0–23)",
                        type: "number",
                      },
                      {
                        key: "quiet_end",
                        label: "Quiet hours end (same = off)",
                        type: "number",
                      },
                    ]}
                    onSave={(body) =>
                      save(`/line/groups/${modal.row.group_id}`, "PATCH", body)
                    }
                  />
                )}
                {modal.kind === "rule" && (
                  <Form
                    initial={modal.row}
                    fields={[
                      { key: "name", label: "Rule name", required: true },
                      { key: "enabled", label: "Enabled", type: "checkbox" },
                      {
                        key: "channel",
                        label: "Destination",
                        type: "select",
                        options: ["discord", "email", "both"],
                      },
                      {
                        key: "match_mode",
                        label: "Match",
                        type: "select",
                        options: [
                          "any_thailand",
                          "watchlist_only",
                          "group",
                          "sector",
                        ],
                      },
                      {
                        key: "match_value",
                        label: "Actor or sector (if applicable)",
                      },
                      {
                        key: "email_recipients",
                        label: "Email recipients, separated by commas",
                        list: true,
                      },
                    ]}
                    onSave={(body) =>
                      save(
                        `/alert-rules${modal.row.id ? `/${modal.row.id}` : ""}`,
                        modal.row.id ? "PUT" : "POST",
                        body,
                      )
                    }
                  />
                )}
              </>
            )}
          </DialogContent>
        </Dialog>
      </main>
    </div>
  );
}
