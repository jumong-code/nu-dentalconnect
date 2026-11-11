<div align="center">
  <img src="assets/nu-logo.svg" width="220">

<h1>Design reference</h1>

<p>Visual tokens and responsive behavior in the current interface</p>
</div>

[README](../README.md) · [INSTALL](../INSTALL.md) · [User guide](USER_GUIDE.md) ·
[Architecture](ARCHITECTURE.md) · [Database](DATABASE.md) · [Security](SECURITY.md) ·
[Reviewer guide](REVIEWER_GUIDE.md) · [Design](DESIGN.md)

> [!NOTE]
> This file covers the interface palette, typography, motion and layout.
> It does not cover usage instructions or backend structure (see [User guide](USER_GUIDE.md)
> and [Architecture](ARCHITECTURE.md)).

## Visual direction

![Original navy and gold section divider](assets/divider.svg)

The interface uses a campus-navy and gold palette, a high-contrast display face
for headings, and a readable sans-serif for navigation and operational content.
The home page foregrounds the campus image and a working listing search. Signed-in
workspaces use role-specific navigation and compact task-oriented tables and
forms. This description follows `app.css`, `base.html` and the local
`.impeccable` design notes.

## Color tokens

| Token | Value | Use |
| --- | --- | --- |
| `--navy-950` | `#04142e` | Deepest dark field |
| `--navy-900` | `#071b3d` | Navigation and dark backgrounds |
| `--navy-800` | `#0a2555` | Deep blue surfaces |
| `--navy-700` | `#102f71` | Primary campus blue |
| `--blue-600` | `#16418e` | Blue control state |
| `--blue-500` | `#2e64d8` | Accent blue |
| `--gold-500` | `#d9a61c` | Gold accent |
| `--gold-400` | `#f2c64a` | Gold action and highlight |
| `--gold-ink` | `#6f5200` | Text on light gold |
| `--ink` | `#111e33` | Main text |
| `--muted` | `#4e5f77` | Secondary text |
| `--paper` | `#f3f6fa` | Light page surface |
| `--line` | `#d9e1ed` | Borders and dividers |

Semantic success, warning, danger and info colors have separate text, surface
and border tokens. Status is also labeled in text; color is not its only cue.

## Typography and spacing

- Display headings: `Barlow Condensed`, with system fallbacks.
- Body, navigation and forms: `DM Sans`, with system fallbacks.
- `base.html` loads both from Google Fonts; a network connection is needed for
  those faces. The rest of the interface has fallback fonts.
- Base body size is `0.9375rem` with `1.65` line height. Display sizes use
  responsive `clamp()` values.
- Spacing uses `--sp-1` through `--sp-9`, from `0.25rem` to `6rem`.

## Motion and accessibility

Control transitions use short durations around 140–220ms. The stylesheet has
`prefers-reduced-motion: reduce` rules. Focus styling uses a gold outline/shadow
token; templates include a skip link, labeled controls and accessible menu
state attributes. These are implementation details, not a full accessibility
conformance audit.

## Responsive approach

`base.html` always loads `app.css`. It conditionally loads bundled Bootstrap
5.2.3 before it for student application, appointment and dashboard endpoints,
plus profile routes. The custom CSS defines the app-specific navigation rail,
page layouts and breakpoints. The mobile navigation adjustment is at 760px;
several components have additional breakpoints between 520px and 1180px. The
`.impeccable` direction notes a tablet breakpoint of 1050px. Responsive
behavior comes from custom rules across the site and Bootstrap on that selected
route set; `app.css` contains extensive responsive overrides.

---

[README](../README.md) · [INSTALL](../INSTALL.md) · [User guide](USER_GUIDE.md) ·
[Architecture](ARCHITECTURE.md) · [Database](DATABASE.md) · [Security](SECURITY.md) ·
[Reviewer guide](REVIEWER_GUIDE.md) · [Design](DESIGN.md)