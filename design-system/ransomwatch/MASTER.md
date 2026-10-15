# Design System Master File

> **LOGIC:** When building a specific page, first check `design-system/pages/[page-name].md`.
> If that file exists, its rules **override** this Master file.
> If not, strictly follow the rules below.

---

**Project:** RansomWatch
**Generated:** 2026-10-16 (with ui-ux-pro-max design intelligence, `--design-system`)
**Category:** Cybersecurity threat-intelligence dashboard (SaaS, analyst-facing)
**Resolved Style:** Data-Dense Dashboard — dark operations console
**Design Dials:** Variance 5/10 (Balanced / Modern) | Motion 3/10 (Subtle) | Density 8/10 (Dense / Dashboard)

> Note: the tool's raw palette suggestion (matrix-green cyberpunk / light-mode blue) was
> rejected as off-brand. The product's existing dark + teal identity is preserved and
> refined; the style/layout/density/motion guidance is applied on top of it.

---

## Global Rules

### Color Palette (applied)

| Role | Hex | CSS Variable |
|------|-----|--------------|
| Primary (signal teal) | `#4FE0C6` | `--primary` |
| On Primary | `#052A23` | `--primary-foreground` |
| Background | `#070C14` | `--background` |
| Foreground | `#E6EEFB` | `--foreground` |
| Card | `#0D1622` | `--card` |
| Surface 1 / 2 / 3 | `#0A121C` / `#101B2A` / `#16233A` | `--surface-1..3` |
| Muted foreground | `#93A9C4` | `--muted-foreground` |
| Border | `#1D2C40` | `--border` |
| Destructive | `#FF7E8C` | `--destructive` |
| Ring (focus) | `#4FE0C6` | `--ring` |
| Semantic: ok / warn / info / bad | `#5CE8B0` / `#FFD38A` / `#8FC1FF` / `#FF8D9A` | `--ok` `--warn` `--info` `--bad` |

### Typography

- Body/UI: **Fira Sans** (fallbacks: Noto Sans Thai, system-ui) — dashboard/data pairing per skill DB
- Monospace (IDs, onion URLs, timestamps): **Fira Code**
- Base 16px, line-height 1.55, `letter-spacing: -0.03em` on h1, tabular numerals for metric values
- Eyebrow labels: uppercase, 0.72rem, 0.18em tracking, primary color

### Layout & Density (8/10)

- App shell: sticky 236px sidebar + fluid workspace, `max padding clamp(1rem, 2.5vw, 2.5rem)`
- Panels: 0.8rem radius, 1.15–1.25rem padding, 1px `--border`, subtle inset highlight + soft shadow
- Metric cards: 4-up grid (2-up ≤1100px), 3px left accent bar, icon chip, 2.1rem tabular value
- Tables: sticky header (`--surface-2`), uppercase 0.72rem headers, 0.8rem cell padding, row hover `#101C2C`

### Badges & Status

- Pill badges with 6px status dot (`::before`), semantic colors:
  confirmed/ok → ok-teal, reported → info-blue, claimed/pending/degraded/stale → warn-amber, disputed/error → bad-red

### Motion (3/10 — subtle)

- Panel entrance: `rise` 320ms cubic-bezier(0.2, 0.7, 0.3, 1)
- Hover/focus transitions: 140–160ms ease
- Live indicator: 2.4s pulse on `.live-dot`
- **All motion disabled under `prefers-reduced-motion: reduce`**

### Accessibility (must hold)

- Visible `:focus-visible` ring (2px primary, 3px offset)
- Inputs: focus border + 3px primary glow ring; hover border lightening
- Contrast ≥ 4.5:1 for body text on all surfaces
- Icon-only buttons keep `aria-label` / `title`
- No emojis as icons (Lucide only)

### Anti-Patterns (avoid)

- Light mode reskin, matrix-green cyberpunk reskin (off-brand)
- Placeholder-only form labels, gray-on-gray text, raw hex outside tokens
- Animating width/height, instant 0ms state changes

### Breakpoints

- ≤1100px: metrics 2-up, twocol collapses, sidebar 196px
- ≤700px: sidebar becomes top bar with horizontal scroll nav, single-column forms
