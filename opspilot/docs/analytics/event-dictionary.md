# BVTech Analytics — Governed Event Dictionary (Phase 15)

A single source of truth for analytics events so they fire **once**, carry
consistent dimensions, and never leak PII / assessment answers / secrets.
Implement behind a typed helper (one `track(event, props)` entry point) rather
than scattering GTM `dataLayer.push` calls.

## Shared dimensions (attach to every event where known)

`content_type`, `service`, `city`, `path` (learning path), `lab_id`,
`difficulty`, `acquisition_source`, `device`, `authed` (bool, never the user id/email).

## Commercial (bvtech.org)

| Event | Fires when |
| --- | --- |
| `service_view` | a service page is viewed |
| `pricing_view` | pricing page viewed |
| `calculator_started` / `calculator_completed` | a tool/calculator is used |
| `phone_click` / `email_click` | contact link clicked |
| `assessment_cta_click` | primary "Book assessment" CTA clicked |
| `booking_started` / `booking_completed` | booking flow |
| `contact_started` / `contact_submitted` | lead/contact form |
| `case_study_view` | a case study viewed |
| `guide_download` | a guide downloaded |

**Business funnel:** Landing → Service/Pricing → Proof → CTA → Booking → Qualified lead.

## Academy (portal.bvtech.org)

| Event | Fires when |
| --- | --- |
| `academy_signup_started` / `academy_signup_completed` | registration |
| `path_started` | a learning path begun |
| `lab_started` / `lab_completed` / `lab_failed` | lab attempts |
| `hint_used` | a hint revealed |
| `assessment_started` / `assessment_passed` / `assessment_failed` | assessments |
| `badge_earned` | a badge earned |
| `certificate_earned` | a certificate issued |
| `return_7d` / `return_30d` | retention markers |

**Academy funnel:** Landing → Signup → Path selected → First lab started → First lab passed → 3 labs passed → Path milestone → Credential.

## Rules

- **Never** send: secrets, assessment answers, passwords, raw email/user id, or any PII.
- Each event fires exactly once per occurrence (guard double-fires); add a duplicate-event test.
- Keep existing GTM identifiers unless a migration is explicitly planned.
- Define a `debug` mode that logs events without sending, for QA.
