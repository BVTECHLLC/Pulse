"""Social posting doctor — answers "why aren't LinkedIn / Google posting?".

Run it on the server, inside the api container:
    docker compose exec -T api python scripts/social_doctor.py
Add --post to also FORCE one real LinkedIn + Google attempt and show the result:
    docker compose exec -T api python scripts/social_doctor.py --post

Read-only by default. Robust to older code (uses getattr), so it runs before or
after a deploy and tells you which one you're on."""
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")
from app.core.db import SessionLocal           # noqa: E402
from app.core.config import get_settings       # noqa: E402
from app.services import autopost, content_autopilot as ca, secure_config as sc  # noqa: E402
from app.models import SocialPost, OAuthToken   # noqa: E402
from collections import Counter                 # noqa: E402

db = SessionLocal()
ver = get_settings().APP_VERSION
has_deliver = hasattr(autopost, "deliver_all_due")   # the v1.146 fix

print("=" * 64)
print(f"  SOCIAL POSTING DOCTOR — OpsPilot v{ver}")
print("=" * 64)

# 1) Is the delivery fix deployed?
print("\n[1] Delivery fix (v1.146 — posts send without the campaign toggle)")
print(f"    deployed: {'YES' if has_deliver else 'NO  <-- run ./deploy.sh (you are on old code)'}")

# 2) Daily content drip
cc = ca.get_config(db)
print("\n[2] Daily content drip (content_autopilot)")
print(f"    enabled: {cc['enabled']}   linkedin channel: {cc['channels'].get('linkedin')}   "
      f"gbp channel: {cc['channels'].get('gbp')}")
print(f"    last run — linkedin: {cc['last'].get('linkedin')}   gbp: {cc['last'].get('gbp')}")

# 3) Channel readiness (are the posters actually usable?)
rd = autopost.channel_readiness(db)
print("\n[3] Channel readiness (is the poster usable right now?)")
for ch in ("linkedin", "google_business", "google_business_personal"):
    paused = bool(autopost.get_reauth(db, ch)) if hasattr(autopost, "get_reauth") else False
    print(f"    {ch:26s} ready: {str(rd.get(ch)):5s}  paused(needs reconnect): {paused}")

# 4) Credentials detail
li = sc.get_platform(db, "pub_linkedin"); licfg = (li.config if li else {}) or {}
li_tok = bool(sc.get_secret(licfg, "access_token")) or db.query(OAuthToken).filter(OAuthToken.provider == "linkedin").count() > 0
li_urn = bool(sc.get_secret(licfg, "person_urn") or licfg.get("person_urn"))
gb = sc.get_platform(db, "gbp"); gbcfg = (gb.config if gb else {}) or {}
gb_fields = {k: bool(sc.get_secret(gbcfg, k) or gbcfg.get(k)) for k in
             ("client_id", "client_secret", "refresh_token", "account_name", "location_name")}
print("\n[4] Credentials")
print(f"    LinkedIn: token={li_tok}  person_urn={li_urn}")
print(f"    Google Business: " + "  ".join(f"{k}={v}" for k, v in gb_fields.items()))

# 5) Queue + last delivered
q = db.query(SocialPost).all()
print("\n[5] Social post queue")
print("    by status:", dict(Counter(p.status for p in q)) or "empty")
lastc = getattr(autopost, "_last_posted_channel", None)
if lastc:
    print(f"    last LinkedIn delivered: {lastc(db,'linkedin')}")
    print(f"    last Google   delivered: {lastc(db,'google_business')}")

# 6) Verdict
print("\n" + "=" * 64)
print("  VERDICT")
print("=" * 64)
if not has_deliver:
    print("  ❌ You're on OLD code. The posts are generated daily but never sent")
    print("     (delivery sat behind an off-by-default toggle).  FIX:")
    print("       cd /opt/bvtech-portal/opspilot && git pull origin main && ./deploy.sh")
elif not (li_tok and li_urn):
    print("  ❌ LinkedIn isn't fully connected (need token + person URN).")
    print("     FIX: Settings -> LinkedIn tile -> paste token + Person URN, or one-click Connect.")
elif rd.get("linkedin") and all(gb_fields.values()):
    print("  ✅ Everything needed is connected. LinkedIn + Google should post on the")
    print("     next daily tick. Use --post to force one now and watch it go.")
elif rd.get("linkedin"):
    missing = [k for k, v in gb_fields.items() if not v]
    print("  ✅ LinkedIn is ready (posts daily).")
    print(f"  ⚠️  Google Business missing: {', '.join(missing)} -> connect it in Settings.")
else:
    print("  ⚠️  LinkedIn poster not ready — token likely expired. Reconnect in Settings.")

# 7) Optional: force a real attempt
if "--post" in sys.argv:
    print("\n[force] Generating + delivering one LinkedIn/Google post now...")
    now = datetime.now(timezone.utc)
    try:
        ok, detail = ca._run_linkedin(db, now)
        print(f"    linkedin generate: ok={ok} {detail[:120]}")
    except Exception as e:
        print(f"    linkedin generate error: {e}")
    if has_deliver:
        res = autopost.deliver_all_due(db, now)
        print(f"    delivered: {res}")
    else:
        print("    (deliver_all_due not present — deploy first)")

db.close()
