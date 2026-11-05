# BVTech Overhaul — Roadmap mapped to the real codebase

_Translates the 18-phase "Comprehensive Digital Audit & Overhaul Plan" into this
repository's actual architecture (Python/FastAPI + published static HTML + Cloudflare
edge workers), per the plan's Rule #10 ("if repository reality conflicts with this
prompt, preserve production safety and implement the closest safe architecture")._

Status legend: ✅ done · 🟡 partial · ⬜ not started · 🔁 conflicts-with-plan-assumption

| Phase | Plan intent | Reality in this repo | Status |
| --- | --- | --- | --- |
| **0. Repo discovery** | Inventory stack, routes, data, deploy | `docs/audit/repository-baseline.md` written | ✅ |
| **1. URL/route inventory** | routes-before / redirect-map / canonical-map | `docs/migration/routes-before.csv` generated from the live app (501 portal + 13 static). redirect-map/canonical-map: scaffolded below | 🟡 |
| **2. Design tokens + accessible shell** | Token system + React primitives (Header, MegaMenu…) | 🔁 No React shell. Equivalent = the Python page-builder + shared chrome + `pulse.css`. Real work: extract shared CSS tokens into one place; add skip-nav + focus-visible + aria to generated pages | ⬜ |
| **3. Business IA templates** | ServicePage/LocationPage/… component templates | 🔁 Public marketing pages (home/services/pricing) live in the **external GitLab repo**, not here. We own `/tools/`, `/explore/`, city pages, academy pages. City pages already follow the LocationPage shape | 🟡 |
| **4. SEO / metadata / schema** | Central metadata helper, per-type schema, sitemap indexes, AEO answer-blocks | `_schema` graph (WebPage/WebSite/ProfessionalService/FAQPage) + canonical/OG + viewport + llms.txt/robots/IndexNow all exist. **Backlog:** AEO "answer block" pattern on tool/city pages; split sitemaps | 🟡 |
| **5. Canonicalization / filters** | Canonical filter combos, noindex search, trailing-slash convention | Trailing-slash + canonical already enforced in `build_page`. No crawlable filter explosion today | ✅ |
| **6. Academy data model** | Normalized Lab object | Labs are structured dicts (`LABS`) with id/difficulty/category/points/checker; completions normalized. A formal `Lab` schema file would help the 500-lab program | 🟡 |
| **7. 500-lab taxonomy** | Schema + manifest + validation + migrate, NOT bulk shallow pages | ~63 labs + 20 lessons + 26 dojo + 3 lightning exist, server-graded. Expanding to 500 is a **content program**; needs a manifest + quality-gate + prerequisite metadata first | ⬜ |
| **8. Learning paths (graph)** | Prerequisite DAG, role paths, cycle check | Lessons/labs have implicit ordering; no explicit prerequisite graph yet | ⬜ |
| **9. Assessments** | Server-authoritative, multiple types, anti-replay, idempotent | ✅ Grading is already server-side; XP awarded once (idempotent). Richer assessment types (ordering/matching/log-investigation) = backlog | 🟡 |
| **10. Gamification** | Reward transaction records w/ idempotency_key | XP/levels/badges/streaks/leaderboard exist; rewards are awarded-once via `AcademyCompletion`. A dedicated transaction-ledger w/ `idempotency_key` would harden against exploits | 🟡 |
| **11. LMS / learning-event bus** | Event bus + xAPI/LTI/OpenBadges adapters | ⬜ Not started. Large; only if a client needs LMS interop | ⬜ |
| **12. Accessibility (WCAG 2.2 AA)** | axe tests, keyboard, focus, skip-nav, labels | 🟡 Portal `academy.html` is mobile-first with 48px targets + 16px inputs. Quick wins: skip-nav, focus-visible, replace emoji-as-essential-labels with aria-labels on generated pages | ⬜ |
| **13. Performance (CWV budgets)** | Lighthouse CI, budgets, responsive/AVIF images, lazy-load | 🟡 Pages are light + inline-CSS (fast). No Lighthouse CI or enforced budgets yet | ⬜ |
| **14. Security (OWASP ASVS)** | CSP/HSTS/headers, CSRF, dep/secret scan | 🟡 Strong auth/MFA/rate-limit/captcha/moderation/audit exist. **Backlog:** security headers (CSP nonces, HSTS, Permissions-Policy, Referrer-Policy) at the app/edge; dependency + secret scanning in CI | 🟡 |
| **15. Analytics (typed event contract)** | Governed event dictionary, fire-once | GTM present; `docs/analytics/event-dictionary.md` drafted below. Typed layer = backlog | 🟡 |
| **16. Localization (en/es parity)** | hreflang, x-default, locale selector, parity report | 🟡 `/es/` exists but partial; no reciprocal hreflang/parity yet | ⬜ |
| **17. CI/CD** | install/lint/typecheck/unit/e2e/a11y/link/schema/perf/sec | 🔁 Python CI (alembic + smoke) exists, not npm. Add: schema-validation, broken-link, a11y checks to the Python suite | 🟡 |
| **18. Deployment safety** | staging, feature flags, canary, monitoring, rollback | 🟡 Version-gated auto-deploy + cache purge + daily self-heal + 404 telemetry exist. No staging/canary split | 🟡 |

## Already delivered this session (counts toward phases 4, 9, 12, 14)

- Portal CAPTCHA (PoW + honeypot + disposable-email) on signup & academy register (Phase 14).
- Guaranteed mobile/Tesla viewport on every built + swept page (Phase 12/13).
- Real, HMAC-verifiable Academy **certificates** + public verify page (Phase 9/10).
- 3 new client-side tools with FAQ schema (Phase 4), Explore GitHub-trending widget.
- Tools + certificates surfaced in `llms.txt` (Phase 4 AEO).

## Recommended next (production-safe, in-architecture, high ROI)

1. **AEO answer-blocks** on tool & city pages ("What is X?" + "In short" + key-facts) → stronger AI-answer surfacing. _(Phase 4, low risk, I own these pages.)_
2. **Security headers** (CSP, HSTS, Permissions-Policy, Referrer-Policy, X-Content-Type-Options) added at the FastAPI middleware + recommended for the Cloudflare edge. _(Phase 14.)_
3. **Accessibility quick wins** on generated pages: skip-nav, `:focus-visible` rings, aria-labels where emoji act as labels. _(Phase 12.)_
4. **Schema/link validation tests** added to the smoke suite. _(Phase 17.)_
5. **Reward ledger** with `idempotency_key` for Academy (hardening). _(Phase 10.)_

## Phases that are strategic decisions (need owner input, not just code)

- Public **navigation redesign** into Business vs Academy modes (the marketing chrome is externally maintained in GitLab — needs coordination).
- **500-lab** content program (schema + manifest + QA, then authored cohorts over weeks).
- **LMS/LTI** adapters (only if a client requires it).
- Full **Spanish parity** (translation + QA of real terminology).
