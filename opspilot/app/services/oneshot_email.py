"""v1.88.1 One-shot operator emails — queue one-time sends via code deploy.

The box self-deploys CI-green main every ~2 minutes, which makes the repo a
remote control: drop a task in ``TASKS``, merge to main, and the next
heartbeat on the box sends it — exactly once. Each task id is stamped in the
DB (provider ``oneshot_email``) the moment its send succeeds, so redeploys,
restarts, and repeat ticks can never double-send. Transport failures retry on
later ticks, capped at ``MAX_ATTEMPTS``. Delivery uses the same resolved
transport as the outbound engine (M365 Graph with the operator signature).

Intended for operator/personal sends that are not part of a campaign:
corrections, resends to fixed addresses, one-off notices. Ship the list,
watch the Notification confirm, then clear TASKS in a follow-up commit.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import secure_config

PROVIDER = "oneshot_email"
MAX_ATTEMPTS = 5
PER_TICK = 6           # send at most this many per heartbeat — spreads a big
#                        batch across ticks (~2 min apart) so a burst can't
#                        hurt the mailbox's sender reputation.

# Each task: {"id": unique-stable-string, "to": email, "subject": ..., "body": ...}
# The id is the idempotency key — NEVER reuse an id for different content.

_SUBJ_CONSULT = ("Consultation request — civil rights matters in Comal, "
                 "Guadalupe, Hays & Wharton Counties")
_BODY_CONSULT = """Dear {name},

I'm seeking a consultation about potential civil rights claims arising from a
connected series of events in Comal, Guadalupe, Hays, and Wharton Counties,
Texas. In chronological order:

1. UNLAWFUL STOP (Comal County). I was pulled over without any stated or
   apparent lawful basis. The agency's open-records (FOIA) response about the
   stop materially conflicts with what actually happened — I believe it
   contains false statements about the encounter.

2. ARMED THREAT IGNORED. A man pulled a gun on me in broad daylight, in
   public. The incident is captured on high-resolution (4K) video. Law
   enforcement declined to pursue him.

3. CHARGES AGAINST THE VICTIM (Guadalupe County). Nearly a year after an
   incident at my vehicle — in which I was the person being threatened when
   someone attempted to open my car door — a warrant issued for ME, not the
   aggressor. My defense counsel believes the case is winnable.

4. WEAPON CHARGE FROM A SHARED VEHICLE (Comal County). When that warrant was
   executed, I was sharing a family member's SUV; his pistol was in the
   vehicle, and I did not know it was present. I was charged with possession
   anyway. Counsel believes this case is winnable as well.

5. NO-BOND DETENTION DESPITE GRAVE MEDICAL RISK. In an earlier matter I was
   held with NO BOND over a single alleged technical probation violation,
   despite a dentist's detailed letter documenting a fragile oral/medical
   condition — in substance, that prolonged incarceration could kill me. I
   ultimately had to be medically furloughed. The prosecution has shown no
   concern about that documented risk, which raises serious pretrial-detention
   and deliberate-indifference issues should I be jailed again.

6. FIVE YEARS OF IGNORED STALKING (Wharton County / El Campo). An ongoing
   stalker has harassed and defamed me for roughly five years. I have
   evidence and multiple police reports filed in several jurisdictions where
   I've lived, and a judge personally spoke with the El Campo Police
   Department and directed me to them — yet they have refused to open a case
   or even issue a case number. This is my second stalker; the pattern of
   police non-response is documented.

I have maintained my innocence throughout — in the vehicle incident I acted
only as someone being threatened, and I did not know the pistol was in the
SUV. I am represented by criminal defense counsel on the pending matters, and
they believe those cases are winnable. What I'm asking you to evaluate is the
CIVIL side: the stop and the false open-records response, the selective
non-prosecution of the man who threatened me, detention despite documented
medical danger, and the years-long refusal to protect me from stalking. I can
provide everything — video, FOIA responses, police reports, and medical
records — at a consultation, under privilege.

Would your office have availability for a consultation, paid or otherwise?
Thank you for your time.

Respectfully,
Jordan Polasek
El Campo, Texas
help@bvtech.org"""

_SUBJ_SUPPORT = ("Request for court support — pending cases in Comal & "
                 "Guadalupe Counties (defense counsel welcomes courtroom "
                 "presence)")
_BODY_SUPPORT = """Dear {name},

I'm a Texas resident with pending criminal cases in Comal and Guadalupe
Counties that my defense attorneys believe are winnable, and they've advised
that visible community support in the courtroom can genuinely matter. I'm
reaching out to ask whether your organization offers court support,
participatory defense, or courtwatch presence — or can connect me with people
who do.

My story, briefly: a man pulled a gun on me in broad daylight — it is captured
on 4K video — and police declined to pursue him. The charges I now face grew
out of the chain of events that followed, and in both cases my attorneys
believe I was the one wronged: in one, I was the person being threatened when
someone tried to open my car door, yet the warrant issued for me, not the
aggressor; in the other, I was charged over a family member's pistol in a
shared vehicle that I did not know was present. Along the way I was once held
with NO BOND over a single alleged technical probation violation, even though
a physician's letter documented that jail endangers my life because of a
serious medical condition — I ultimately had to be medically furloughed, and
the prosecution has shown no concern about that risk. Separately, for roughly
five years police have refused to act on an ongoing stalker who harasses and
defames me — despite multiple police reports from several jurisdictions and a
judge who personally directed me to the department, they will not even open a
case.

I have maintained my innocence throughout, and I have good lawyers. What I
don't have is community in the room — people whose presence reminds the court
that someone is watching. If your organization does court support, I would be
honored to have you, and I'm glad to share court dates and documentation. If
not, a referral to any participatory defense hub or courtwatch group serving
Comal, Guadalupe, or Hays Counties would mean a great deal.

Thank you for the work you do.

Respectfully,
Jordan Polasek
El Campo, Texas
help@bvtech.org"""


_SUBJ_DENTIST = ("Requesting an implant evaluation & medical opinion for a "
                 "court matter — patient with serious oral-implant needs")
_BODY_DENTIST = """Dear {name},

My name is Jordan Polasek. I'm writing to ask whether your practice would take
me on as a patient for a dental-implant evaluation, and — if you're willing —
help document the seriousness of my oral condition for a court matter.

Briefly and honestly: I'm facing criminal charges that my attorneys at Cofer &
Connelly believe are winnable. They involve what I consider victimless
accusations, and I have maintained my innocence — but some may go to trial,
and a jury could always decide the other way, so I have to prepare for the
possibility of incarceration even as an innocent man. I am not a career
criminal. I run an award-winning B2B IT solutions company and I'm currently a
4.0 student finishing my bachelor's in cloud computing.

Here is why I'm reaching out to an implant dentist specifically. I have a
serious oral-implant condition. One dentist has already written that
incarceration could kill me because of it, and the last time I was held with
no bond — over using a plant I have a valid prescription for — I had to be
medically furloughed. The prosecution has not treated that risk seriously, and
my attorneys have asked me to obtain a more formal, clinical write-up from
another qualified dentist. It appears the court gives more weight to a
thorough professional evaluation than to a brief letter.

What I'm hoping you can help with:
  - Examine my mouth and current implants and assess their condition;
  - Create a treatment plan / game plan to address what needs to be fixed,
    including any surgery required;
  - Document, for the court, how serious oral health is to overall health, and
    specifically how dangerous an implant-bearing mouth can become without
    regular professional checkups and care — the infection risk if I cannot
    get proper treatment while incarcerated.
  - If at all possible, I would gladly pay for a dentist willing to appear at
    trial. In my experience the courts do not take written letters as
    seriously as they should, given how serious my condition is.

I'm ready to be a paying patient, to share my existing records, and to work
around your schedule. If you're able to help — or can refer me to a colleague
who does complex implant and expert-opinion work — I would be deeply grateful.

Please reply to this email or call me at 210-538-3669 ext. 1 at your earliest
convenience.

Thank you for your time and your care.

Respectfully,
Jordan Polasek
El Campo, Texas
help@bvtech.org"""


def _consult(task_id: str, name: str, to: str) -> dict:
    return {"id": task_id, "to": to, "subject": _SUBJ_CONSULT,
            "body": _BODY_CONSULT.format(name=name)}


def _support(task_id: str, name: str, to: str) -> dict:
    return {"id": task_id, "to": to, "subject": _SUBJ_SUPPORT,
            "body": _BODY_SUPPORT.format(name=name)}


def _dentist(task_id: str, name: str, to: str) -> dict:
    return {"id": task_id, "to": to, "subject": _SUBJ_DENTIST,
            "body": _BODY_DENTIST.format(name=name)}


TASKS: list[dict] = [
    # Bounce fix: NAACP San Antonio's satx.rr.com box is dead; current branch
    # email verified on sanantoniotxnaacp.org.
    _support("aug2-resend-naacp-sa", "NAACP San Antonio Branch",
             "sanantonionaacp@gmail.com"),
    # New civil-rights attorney targets (verified published intake emails).
    _consult("aug2-dean-malone", "Law Offices of Dean Malone, P.C.",
             "dean@deanmalone.com"),
    _consult("aug2-mccaffity", "Sommerman, McCaffity, Quesada & Geisler, LLP",
             "smccaffity@textrial.com"),
    _consult("aug2-lewis-law", "The Lewis Law Group, PLLC",
             "office@thelewislaw.com"),
    _consult("aug2-austin-clc", "Austin Community Law Center",
             "brian@austincommunitylawcenter.org"),
    _consult("aug2-ut-crc", "UT Austin Civil Rights Clinic",
             "lia.davis@law.utexas.edu"),
    # New court-support / justice-org targets.
    _support("aug2-tx-defender", "Texas Defender Service",
             "info@texasdefender.org"),
    _support("aug2-tfdp", "Texas Fair Defense Project",
             "ylondon@fairdefense.org"),
    _support("aug2-tcadp", "Texas Coalition to Abolish the Death Penalty",
             "info@tcadp.org"),
    _support("aug2-top", "Texas Organizing Project",
             "info@organizetexas.org"),
    _support("aug2-bridges", "Bridges To Life",
             "contact@bridgestolife.org"),
    _support("aug2-lsja", "Lone Star Justice Alliance", "contact@lsja.org"),
    _support("aug2-naacp-hou", "NAACP Houston Branch",
             "branch@naacphouston.org"),
    _support("aug2-naacp-dal", "NAACP Dallas Branch #6169",
             "Dallasnaacp6169B@gmail.com"),
    _support("aug2-earl-carl", "Earl Carl Institute (TSU Thurgood Marshall "
             "School of Law)", "earlcarlinstitute@tmslaw.tsu.edu"),
    _support("aug2-deason", "Deason Criminal Justice Reform Center (SMU)",
             "DeasonJusticeCenter@smu.edu"),
    # --- Round 3: more civil-rights attorneys (verified published emails) ---
    _consult("aug2-merritt", "Merritt Law Firm", "info@leemerrittesq.com"),
    _consult("aug2-stafford-moore", "Stafford Moore, PLLC",
             "info@staffordmoore.law"),
    # (Removed: The Schaffer Firm + Josh Schaffer + Udashen Anton — these are
    #  criminal-appeals/habeas practices, not plaintiff-side civil rights. The
    #  Schaffer Firm replied confirming criminal-only, so we stay on target.)
    # --- Round 3: Texas criminal-defense bar associations (referral reach) ---
    _support("aug2-tcdla", "Texas Criminal Defense Lawyers Association",
             "info@tcdla.com"),
    _support("aug2-hccla", "Harris County Criminal Lawyers Association",
             "cjappelt@yahoo.com"),
    _support("aug2-sacdla", "San Antonio Criminal Defense Lawyers Association",
             "210SACDLA@gmail.com"),
    _support("aug2-dcdla", "Dallas Criminal Defense Lawyers Association",
             "dcdlaboard@gmail.com"),
    _support("aug2-tccdla", "Tarrant County Criminal Defense Lawyers "
             "Association", "info@tccdla.com"),
    # (Neighborhood Defender Service — Hays County removed: no verifiable
    #  published email; reach by phone 512-749-0690 or their web form.)
    # --- Round 3: more NAACP branches + justice orgs (verified emails) ---
    _support("aug2-naacp-ftw", "NAACP Fort Worth-Tarrant County Branch #6178",
             "ftw.naacp.info@gmail.com"),
    _support("aug2-naacp-cc", "NAACP Corpus Christi (H. Boyd Hall Branch)",
             "naacp.cctx@gmail.com"),
    _support("aug2-naacp-waco", "NAACP Waco-McLennan County Branch",
             "waconaacp@gmail.com"),
    _support("aug2-naacp-killeen", "NAACP Killeen Branch #6189",
             "naacpkilleentx@yahoo.com"),
    _support("aug2-tcje-dir", "Texas Center for Justice and Equity",
             "KJohnson@texascje.org"),
    _support("aug2-tpca", "Texas Prisons Community Advocates",
             "Iwa.Geraldo@TPCAdvocates.org"),
    _support("aug2-tavp", "Texas After Violence Project",
             "info@texasafterviolence.org"),
    _support("aug2-truth-be-told", "Truth Be Told", "office@truth-be-told.org"),
    _support("aug2-kolbe", "Kolbe Prison Ministries",
             "KolbePrisonMinistries@gmail.com"),
    _support("aug2-act4sa", "ACT 4 SA", "info@act4sa.org"),
    # --- Round 4: more civil-rights attorneys + law-school criminal clinics +
    #     county defense bar + local support (verified emails; immigration/
    #     veterans clinics skipped as not applicable) ---
    _consult("aug2-turley", "Turley Law Firm", "turley@wturley.com"),
    _consult("aug2-elmazi", "Elmazi Law", "blerim@elmazilaw.com"),
    _consult("aug2-kaplan", "Kaplan Law Firm (Austin)",
             "mzschiesche@kaplanlawatx.com"),
    _support("aug2-tsu-crim", "TSU Thurgood Marshall Criminal Law Clinic",
             "crimlaw@tmslaw.tsu.edu"),
    _support("aug2-tsu-clinical", "TSU Clinical Legal Studies",
             "lydjohnson@tmslaw.tsu.edu"),
    _support("aug2-ttu-crim", "Texas Tech Law Criminal Defense Clinic",
             "dwight.mcdonald@ttu.edu"),
    _support("aug2-ttu-caprock", "Texas Tech Caprock Regional Public Defender",
             "joe.stephens@ttu.edu"),
    _support("aug2-baylor-clinics", "Baylor Law Legal Clinics",
             "LegalClinics@baylor.edu"),
    _support("aug2-smu-crim", "SMU Dedman Criminal Justice Clinic",
             "sanchezlawdebbie@me.com"),
    _support("aug2-fortbend-bar", "Fort Bend County Criminal Defense Attorneys "
             "Association", "fortbenddefensebar@gmail.com"),
    _support("aug2-lulac1", "LULAC Council 1 (Corpus Christi)",
             "contact@lulac1.org"),
    _support("aug2-denton-bail", "Denton Bail Fund", "dentonbailfund@gmail.com"),
    _support("aug2-unlocking-doors", "Unlocking Doors (reentry)",
             "info@unlockingdoors.org"),
    _support("aug2-miles", "MILES of Freedom (reentry)",
             "contact@milesoffreedom.org"),
    _support("aug2-crosswalk", "CrossWalk Center (reentry)",
             "info@crosswalkcenter.org"),
    _support("aug2-crisis-comal", "Crisis Center of Comal County",
             "crisiscenter@crisiscenternb.org"),
    # --- Round 5: justice-advocacy orgs (prison/reentry ministries skipped as
    #     off-target — they serve the already-incarcerated, not court support) ---
    _support("aug2-hpjc", "Houston Peace & Justice Center", "info@hpjc.org"),
    _support("aug2-txvoices", "Texas Voices for Reason and Justice",
             "info@texasvoices.org"),
    # --- Implant dentists (verified emails) — evaluation + expert-opinion ask.
    #     Sugar Land / Richmond / Rosenberg first, then statewide + home area.
    _dentist("dds-rimes", "Rimes DDS (Sugar Land)", "info@rimesdds.com"),
    _dentist("dds-smiles-greatwood", "Smiles On Greatwood Dentistry",
             "info@smilesongreatwood.com"),
    _dentist("dds-luxe", "Luxe Dental Arts (Sugar Land)",
             "info@luxedentalarts.com"),
    _dentist("dds-cc", "C & C Dental (Sugar Land)", "mydentist@candcdental.com"),
    _dentist("dds-sugarland-oms", "Sugar Land Oral & Maxillofacial Surgery",
             "sugarlandsurgery@yahoo.com"),
    _dentist("dds-implant-studio", "The Dental Implant Studio of Houston "
             "(Missouri City)", "info@dentalimplantstudiohouston.com"),
    _dentist("dds-richmond-care", "Richmond Dental Care",
             "info@richmond-dentalcare.com"),
    _dentist("dds-rosenberg-smiles", "Rosenberg Smiles Dental",
             "rosenbergsmiles4@gmail.com"),
    _dentist("dds-ace-t", "Ace T Dental (Rosenberg)", "acetdental@yahoo.com"),
    _dentist("dds-stankewitz", "Houston Dental Implants & Prosthodontics",
             "markstankewitz515@gmail.com"),
    _dentist("dds-hps", "Houston Prosthodontic Specialists",
             "hpsdoctors@gmail.com"),
    _dentist("dds-hanna", "Hanna Dental Implant Center (Houston)",
             "Contact@DrHanna.Co"),
    _dentist("dds-prosof-tx", "Prosthodontics of Texas (Austin)",
             "info@prosoftx.com"),
    _dentist("dds-clover", "Clover Smile Studio (Austin)",
             "cloversmileatx@gmail.com"),
    _dentist("dds-denture-sa", "Denture Implants San Antonio",
             "contact@dentureimplantssanantonio.com"),
    _dentist("dds-gulley", "Oral Surgery Associates of South Texas "
             "(Corpus Christi)", "info@bryangulley.com"),
    _dentist("dds-victoria", "Victoria Dentistry", "info@victoriatxdentistry.com"),
    # --- Round 2 dentists: statewide expansion (verified published emails) ---
    _dentist("dds-antoine", "Antoine Dental Center (Houston)",
             "help@antoinedental.com"),
    _dentist("dds-olim", "Olim & Associates (Katy)", "marvolim@aol.com"),
    _dentist("dds-cypress", "Cypress Dental", "cypressdental.info@gmail.com"),
    _dentist("dds-partners-pdi", "Partners Dentures & Dental Implants "
             "(The Woodlands)", "info@partnerspdi.com"),
    _dentist("dds-woodlands-elite", "Woodlands Elite Dental Partners",
             "woodlandsdentalpartners@gmail.com"),
    _dentist("dds-maxwello", "Maxwello Dental (Pearland)",
             "pearland@maxwellodental.com"),
    _dentist("dds-pearland-group", "Pearland Dental Group",
             "info@pearlanddentalgroup.com"),
    _dentist("dds-pomsa", "Pearland Oral & Maxillofacial Surgery Associates",
             "pomsa@att.net"),
    _dentist("dds-eagle", "Eagle Dental Texas (Sugar Land)",
             "edtappointment@gmail.com"),
    _dentist("dds-dominion", "Dominion Dental Spa (San Antonio)",
             "info@dominion.dental"),
    _dentist("dds-austin-advanced", "Austin Advanced Dentistry",
             "manager@austinadvanceddentistry.com"),
    _dentist("dds-austin-cosmetic", "Austin Cosmetic & Implant Dentistry",
             "info@austintopdentist.com"),
    _dentist("dds-austin-co", "Austin Dental Company", "info@austindentalco.com"),
    _dentist("dds-dallas-pros", "Dallas Prosthodontics",
             "info@dallasprosthodontics.com"),
    _dentist("dds-elite-dallas", "Elite Dental Studio (Dallas)",
             "ktdao.dds@gmail.com"),
    _dentist("dds-tcosdi", "Texas Center for Oral Surgery & Dental Implants "
             "(Flower Mound)", "office@oralsurgerytexas.com"),
    _dentist("dds-fischer", "Fischer Dental (Fort Worth)", "office@fwpros.com"),
    _dentist("dds-fw-dental", "Fort Worth Dental", "info@fortworthdental.com"),
    _dentist("dds-fw-implant", "Fort Worth Dental Implant Center",
             "info@myreliabledentistry.com"),
    _dentist("dds-smile-makers", "Smile Makers Dentistry (Fort Worth)",
             "info@smilemakersdds.com"),
    _dentist("dds-lake-country", "Lake Country Dental (Fort Worth)",
             "raydsnider@yahoo.com"),
    _dentist("dds-fw-dentist", "Fort Worth Dentist", "admin@fortworthdentist.com"),
    _dentist("dds-coastal", "Coastal Dental Implant (Corpus Christi)",
             "info@coastaldentalimplant.com"),
    _dentist("dds-toothology", "Toothology (Corpus Christi)",
             "toothologycc@gmail.com"),
    _dentist("dds-hot-smiles", "Heart of Texas Smiles (Waco)",
             "carrie@heartoftexassmiles.com"),
    _dentist("dds-starr", "Starr General Dentistry (Waco)",
             "om@starrgeneraldentistry.com"),
    _dentist("dds-texas-ave", "Texas Avenue Dental (College Station)",
             "info@texasavedental.com"),
    _dentist("dds-careplus", "CarePlus Smiles (Bryan)",
             "eagleriverdentalassoc@gmail.com"),
    _dentist("dds-cs-dental", "College Station Dental & Orthodontics",
             "CollegeStationDental@mb2dental.com"),
    # --- Round 3 dentists: more implant/oral-surgery/perio (verified emails) ---
    _dentist("dds-new-smiles", "New Smiles Texas (Bellaire/Houston)",
             "implants@newsmilesbellaire.com"),
    _dentist("dds-implant-dental-ctr", "Implant Dental Center (Houston)",
             "impdentalcenter@gmail.com"),
    _dentist("dds-aa-dental", "A&A Dental Implant and Cosmetic Center (Houston)",
             "frontdesk@aadentalclinic.com"),
    _dentist("dds-woodlands-dno", "Woodlands Dentistry and Orthodontics",
             "woodlandsdno@gmail.com"),
    _dentist("dds-pearland-implant", "Pearland Implant Center",
             "info@myaccentdental.com"),
    _dentist("dds-sa-perio", "San Antonio Periodontics and Implant Dentistry",
             "question@sanantonioperio.com"),
    _dentist("dds-alamo-heights", "Alamo Heights Implant Center (San Antonio)",
             "info@alamoheightsimplant.com"),
    _dentist("dds-cosmetic-sa", "Cosmetic Dentistry of San Antonio",
             "info@cosmeticdentistryofsa.com"),
    _dentist("dds-implant-place", "The Dental Implant Place (Fort Worth)",
             "doc@thedentalimplantplace.com"),
    _dentist("dds-rivertree", "Fort Worth Family & Implant Dentistry (Rivertree)",
             "frontdesk@rivertreedentist.com"),
    _dentist("dds-dallas-implant", "Dallas Dental Implant Center & Cosmetic "
             "Dentistry", "dallasimplant@gmail.com"),
    _dentist("dds-dallas-coms", "Dallas Center for Oral & Maxillofacial Surgery "
             "(Plano)", "willowbend@oralsurgerydfw.com"),
    _dentist("dds-implant-choice", "Implant Choice Center (Plano/Frisco)",
             "info@implantchoicecenter.com"),
]

# --- Scheduling: a first wave goes out now; the bulk holds until Monday 9am
#     Central (14:00 UTC 2026-08-03) so it lands when open/reply rates are
#     highest. A task with no "not_before" is eligible immediately; otherwise
#     it waits until now >= not_before.
_MONDAY_9AM_CT = "2026-08-03T14:00:00+00:00"
_NOW_WAVE = {
    "aug2-resend-naacp-sa",   # corrected-address resend — time-sensitive
    "aug2-dean-malone",       # top jail-medical civil-rights firm
    "aug2-merritt",           # civil-rights litigator
    "aug2-ut-crc",            # UT Austin Civil Rights Clinic
    "aug2-tcdla",             # statewide criminal-defense bar
    "dds-rimes",              # Sugar Land prosthodontist — best expert fit
    "dds-sugarland-oms",      # Sugar Land oral surgeon
    "dds-hps",                # Houston prosthodontic specialists
}
for _t in TASKS:
    if _t["id"] not in _NOW_WAVE:
        _t["not_before"] = _MONDAY_9AM_CT


def _eligible(task: dict, now: datetime) -> bool:
    nb = task.get("not_before")
    if not nb:
        return True
    return now >= datetime.fromisoformat(nb)


def _resolver(db: Session):
    from . import outbound
    return outbound.resolve_send_fn(db)


_SEND_RESOLVER = _resolver          # test seam


def tick(db: Session, now: datetime | None = None) -> dict:
    """Heartbeat entrypoint. Sends every not-yet-done task; harmless when
    TASKS is empty or everything is stamped done."""
    now = now or datetime.now(timezone.utc)
    if not TASKS:
        return {"ran": False, "reason": "no_tasks"}
    conn = secure_config.get_platform(db, PROVIDER)
    raw = dict((conn.config if conn else None) or {})
    done = dict(raw.get("done") or {})
    attempts = {k: int(v) for k, v in dict(raw.get("attempts") or {}).items()}
    undone = [t for t in TASKS
              if t["id"] not in done and attempts.get(t["id"], 0) < MAX_ATTEMPTS]
    if not undone:
        return {"ran": False, "reason": "all_done"}
    pending = [t for t in undone if _eligible(t, now)]
    if not pending:
        # Everything left is scheduled for later (e.g. the Monday wave).
        return {"ran": False, "reason": "scheduled", "held": len(undone)}
    send_fn, transport = _SEND_RESOLVER(db)
    if send_fn is None:
        return {"ran": False, "reason": "no_transport", "detail": transport}
    remaining = len(pending) - PER_TICK
    pending = pending[:PER_TICK]
    sent = failed = 0
    for task in pending:
        attempts[task["id"]] = attempts.get(task["id"], 0) + 1
        try:
            send_fn(task["to"], task["subject"], task["body"])
            done[task["id"]] = now.date().isoformat()
            sent += 1
        except Exception:  # noqa: BLE001 — transport hiccup: retry next tick
            failed += 1
    secure_config.upsert_platform(db, PROVIDER, "One-shot Emails", "System",
                                  {**raw, "done": done, "attempts": attempts})
    if sent or failed:
        tail = (f" — {remaining} more queued for the next tick"
                if remaining > 0 else "")
        _notify(db, "info" if not failed else "warning",
                f"📮 One-shot emails: {sent} sent, {failed} failed "
                f"(will retry, cap {MAX_ATTEMPTS}){tail} via {transport}.")
    return {"ran": True, "sent": sent, "failed": failed,
            "queued": max(0, remaining), "transport": transport}


def _notify(db: Session, severity: str, message: str) -> None:
    try:
        from ..models import Notification
        db.add(Notification(client_id=None, target_user_id=None, kind="system",
                            severity=severity, message=message[:1000]))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
