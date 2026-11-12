"""One-shot publisher for the Microsoft 365 outage advisory (Nov 12, 2026).

Ships the operator-authored advisory to bvtech.org through the SAME native
pipeline the daily autopilot uses (content_autopilot.publish_custom -> GitLab
commit -> Cloudflare purge), so it inherits the brand guard, SEO/schema wrap,
and cache flush. Breaking-news item, so it uses override=True to bypass the
1-post-per-day SEO flood guard.

Run it on the box, piping this freshly-pulled file INTO the running api
container (works immediately, no image rebuild needed):

    cd /opt/bvtech-portal/opspilot && git pull origin main && \
      docker compose exec -T api python - < scripts/publish_advisory.py

Set LINKEDIN=1 to ALSO queue the same advisory to LinkedIn (delivers on the
next tick now that LinkedIn posting is fixed):

    docker compose exec -T -e LINKEDIN=1 api python - < scripts/publish_advisory.py
"""
import os
import sys

sys.path.insert(0, os.getcwd())
from app.core.db import SessionLocal                         # noqa: E402
from app.services import content_autopilot as ca             # noqa: E402

TITLE = "Microsoft 365 Global Service Outage Advisory — November 12, 2026"

EXCERPT = ("Microsoft 365 is hit by a widespread outage affecting Outlook, Exchange, "
           "Teams and SharePoint. BVTech's advisory: the likely causes, what to do "
           "right now, and why business-continuity planning matters.")

KEYWORDS = ("Microsoft 365 outage, Outlook outage, Exchange Online outage, Microsoft "
            "Teams outage, SharePoint outage, Microsoft 365 service health, cloud outage, "
            "business continuity, managed IT services, cybersecurity, BVTech, Texas")

HTML = """
<p><strong>November 12, 2026 —</strong> Microsoft is currently experiencing a widespread
service disruption affecting Outlook, Exchange Online, Microsoft Teams, SharePoint, and
other Microsoft&nbsp;365 services. BVTech&nbsp;LLC is actively monitoring the situation on
behalf of our clients.</p>

<h2>What caused the outage?</h2>
<p>According to Microsoft's ongoing investigation, the disruption appears to stem from
failures within its cloud infrastructure. Microsoft has identified several contributing
issues:</p>
<ul>
  <li><strong>Server health-check failures:</strong> automated monitoring systems are
  unexpectedly pulling healthy servers out of service.</li>
  <li><strong>Elevated server loads:</strong> the remaining infrastructure is running at
  excessive processor utilization, which is worsening connectivity.</li>
  <li><strong>Potential configuration issues:</strong> Microsoft is investigating whether a
  malfunctioning health-check component or a recent configuration change triggered the
  cascade.</li>
</ul>
<p>Microsoft engineers are actively restoring servers, redistributing workloads, and
deploying corrective changes. A definitive root cause has not yet been confirmed.</p>

<h2>What should businesses do?</h2>
<p>While Microsoft works to restore service, BVTech recommends that businesses:</p>
<ul>
  <li>Avoid unnecessary Outlook reinstalls, password resets, or mailbox/account
  configuration changes — these rarely help during a provider-side outage and can create
  new problems once service is restored.</li>
  <li>Use alternative communication channels (phone, SMS, or a backup messaging platform)
  for anything time-sensitive.</li>
  <li>Monitor Microsoft's official Service Health Dashboard for authoritative status
  updates rather than reacting to unverified reports.</li>
</ul>

<h2>Our perspective</h2>
<p>This outage is another reminder that even the world's largest cloud providers are not
immune to infrastructure failures. Cloud computing offers tremendous benefits, but every
business should maintain a contingency plan for critical services such as email and
communications.</p>
<p>At BVTech&nbsp;LLC, we emphasize proactive monitoring, business-continuity planning, and
resilient IT infrastructure to minimize the impact of unexpected disruptions. We will
continue tracking Microsoft's restoration efforts and keep our clients updated as the
situation develops.</p>

<p><strong>Microsoft Incident IDs:</strong> EX1550543 &middot; MO1550821</p>

<p><em>BVTech&nbsp;LLC — Managed IT Services &amp; Cybersecurity. Worried about what an outage
like this would do to your business? <a href="https://www.bvtech.org">Talk to our team</a>
about monitoring and continuity planning.</em></p>
""".strip()


def main() -> int:
    db = SessionLocal()
    try:
        res = ca.publish_custom(
            db, "bvtech",
            title=TITLE, html=HTML, excerpt=EXCERPT,
            slug="microsoft-365-global-outage-advisory",
            keywords=KEYWORDS, kind="advisory", override=True,
        )
        print("bvtech.org:", res)
        ok = bool(res.get("ok"))
        if ok and res.get("url"):
            print("LIVE URL:", res["url"])
        elif not ok:
            print("NOT published — reason:", res.get("detail"))

        if os.environ.get("LINKEDIN") == "1":
            li = ca.publish_custom(
                db, "linkedin",
                body=(f"{TITLE}\n\n"
                      "Microsoft 365 is experiencing a widespread outage affecting Outlook, "
                      "Exchange, Teams and SharePoint. Our advisory covers the likely causes, "
                      "what to do right now, and why continuity planning matters.\n\n"
                      "Read it: https://www.bvtech.org\n\n"
                      "#Microsoft365 #OutlookOutage #CloudComputing #BusinessContinuity "
                      "#ManagedITServices #BVTech"),
                link="https://www.bvtech.org", override=True,
            )
            print("linkedin:", li)
        return 0 if ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
