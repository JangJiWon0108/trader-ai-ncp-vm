---
name: AI Financial Dashboard Design System
colors:
  surface: '#faf8ff'
  surface-dim: '#d9d9e2'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f3fc'
  surface-container: '#ededf6'
  surface-container-high: '#e7e7f0'
  surface-container-highest: '#e2e2eb'
  on-surface: '#191b22'
  on-surface-variant: '#434653'
  inverse-surface: '#2e3037'
  inverse-on-surface: '#f0f0f9'
  outline: '#737784'
  outline-variant: '#c3c6d5'
  surface-tint: '#2559bd'
  primary: '#00327d'
  on-primary: '#ffffff'
  primary-container: '#0047ab'
  on-primary-container: '#a5bdff'
  inverse-primary: '#b1c5ff'
  secondary: '#006c49'
  on-secondary: '#ffffff'
  secondary-container: '#6cf8bb'
  on-secondary-container: '#00714d'
  tertiary: '#651f00'
  on-tertiary: '#ffffff'
  tertiary-container: '#8b2e01'
  on-tertiary-container: '#ffaa8a'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dae2ff'
  primary-fixed-dim: '#b1c5ff'
  on-primary-fixed: '#001946'
  on-primary-fixed-variant: '#00419e'
  secondary-fixed: '#6ffbbe'
  secondary-fixed-dim: '#4edea3'
  on-secondary-fixed: '#002113'
  on-secondary-fixed-variant: '#005236'
  tertiary-fixed: '#ffdbcf'
  tertiary-fixed-dim: '#ffb59a'
  on-tertiary-fixed: '#380d00'
  on-tertiary-fixed-variant: '#802900'
  background: '#faf8ff'
  on-background: '#191b22'
  surface-variant: '#e2e2eb'
typography:
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.3'
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: '1.4'
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
    letterSpacing: '0'
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
    letterSpacing: '0'
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: '1.4'
    letterSpacing: 0.02em
  tabular-nums:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: '1'
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  sidebar-width: 260px
  container-padding: 32px
  gutter: 24px
  unit: 4px
---

## Brand & Style
The design system is engineered to project absolute precision, reliability, and institutional-grade intelligence for US stock market investors. The brand personality is "The Sophisticated Co-pilot"—an AI-driven partner that distills complex market volatility into actionable, calm insights. 

The visual style follows a **Corporate / Modern** aesthetic. It prioritizes clarity over decoration, using expansive white space to reduce cognitive load while managing dense financial data. The interface feels light and airy yet grounded by high-contrast primary accents, ensuring that the user feels in control of their capital at all times.

## Colors
The palette is anchored by **Deep Blue (#0047AB)**, a color synonymous with stability and institutional trust in the financial sector. This is used for primary actions, active navigation states, and brand-critical elements.

To communicate market performance, the system utilizes a high-visibility semantic pairing: **Emerald Green (#10B981)** for positive growth and AI "Buy" signals, and **Soft Red (#EF4444)** for losses or "Sell" alerts. These are balanced against a neutral background of cool grays (Slate) to ensure the semantic colors pop. Backgrounds should primarily use a very light off-white (#F8FAFC) to differentiate from pure white (#FFFFFF) cards.

## Typography
This design system utilizes **Inter** for its exceptional readability in data-heavy environments and its clean, modern Korean character rendering. Typography is structured to emphasize a clear information hierarchy.

Large headlines are used sparingly for dashboard overviews, while body text and labels are optimized for scanning stock tickers and values. For financial figures, "tabular numbers" must be enabled to ensure that columns of digits align perfectly in tables, allowing users to compare stock prices and percentages with a quick vertical glance.

## Layout & Spacing
The layout employs a **Fixed-Fluid hybrid grid**. A permanent left sidebar at 260px provides high-level navigation, while the main content area utilizes a 12-column fluid grid system that responds to the browser width.

A spacing rhythm based on a 4px baseline unit is strictly followed. Generous 32px padding is applied to the main dashboard container to maintain an "uncluttered" feel. Gutters between cards are set at 24px, ensuring that complex data tables and timeline feeds remain distinct and legible.

## Elevation & Depth
Depth is created through **Ambient Shadows** and tonal layering. The design system avoids heavy borders in favor of soft, diffused shadows (0px 4px 12px rgba(0, 0, 0, 0.05)) that lift cards off the neutral background.

Interactive elements like buttons and hoverable table rows use a slightly more pronounced shadow to indicate clickability. The left sidebar is treated as the lowest layer, while main dashboard cards occupy the middle tier. Modal dialogs and dropdown menus represent the highest elevation, using a semi-opaque backdrop blur to focus the user's attention.

## Shapes
The shape language is defined by a consistent **Rounded (8px-12px)** radius. This level of roundedness softens the professional tone, making the AI service feel approachable and modern rather than stiff or overly institutional.

Standard cards and input fields should use an 8px radius. Larger layout containers and primary dashboard widgets use 12px. Status badges and action buttons should maintain the 8px standard to ensure a cohesive geometric rhythm across the interface.

## Components
This design system includes specific components tailored for financial monitoring:

- **Data Tables:** Feature "sticky" headers and a "hover" state that highlights the entire row in a soft blue tint. Stock tickers are emphasized with semi-bold weights.
- **Status Badges:** Compact, pill-shaped indicators for "Buy," "Hold," or "Sell." These use low-opacity versions of the emerald green and soft red backgrounds with high-contrast text.
- **Info Cards:** The primary container for portfolio summaries. They must include a subtle "micro-chart" (sparkline) to show 24-hour trends.
- **Timeline Feeds:** A vertical stream of AI market signals and news. Each entry uses a left-accented border (Deep Blue) to denote AI-generated content vs. standard news.
- **Input Fields:** Clean, outlined boxes with 8px corners that turn to the Primary Blue on focus, accompanied by a soft blue outer glow.