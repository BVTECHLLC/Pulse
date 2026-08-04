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


_SUBJ_DENTIST = ("New patient — implant treatment plan, and a letter for the "
                 "court about my condition")
_BODY_DENTIST = """Dear {name},

My name is Jordan Polasek, and I'm looking for an implant dentist. I'm happy to
pay for your time, and I'll keep this short — there are two things I'm hoping
for:

1. A full evaluation of my mouth and current implants, and a written treatment
   plan: what needs to be done to fix them, roughly what it would cost, and how
   long it would take.

2. A written opinion I can share with a court. I'm dealing with a legal matter
   that could put me in custody. My current dentist wrote that I could be at
   serious risk — even a risk to my life — if I go without proper dental care,
   but he doesn't do implants, which is why I need an implant specialist. I'd
   be grateful if you could explain what can happen to someone with my kind of
   implant condition if they lose access to specialized dental care.

I'm ready to be a paying patient, to share my records, and to work around your
schedule. If you'd ever be willing to speak to my condition directly for the
court, I'd be truly grateful for that as well.

Please reply here or call me at 210-538-3669 ext. 1 whenever it's convenient.
Thank you so much for your time and care.

Warm regards,
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
    # WARM REFERRAL: Sadie Groberg (Lone Star Justice Alliance) replied and
    # referred us to the Grassroots Leadership Central Texas participatory
    # defense hub. Bespoke email naming the referral — sends immediately.
    {"id": "referral-ctx-pdh",
     "to": "cpridgon@grassrootsleadership.org",
     "subject": ("Referred by Sadie Groberg (Lone Star Justice Alliance) — "
                 "court support for cases in Comal & Guadalupe Counties"),
     "body": """Dear Central Texas Participatory Defense Hub,

Sadie Groberg at the Lone Star Justice Alliance kindly referred me to you, and
I'm grateful for the introduction.

I'm a Texas resident with pending criminal cases in Comal and Guadalupe
Counties that my defense attorneys believe are winnable, and they've encouraged
me to build visible community support in the courtroom. Briefly: a man pulled a
gun on me in broad daylight — it's on video — and police declined to pursue
him. The charges I now face grew out of what followed, and in both cases my
attorneys believe I was the one wronged: in one I was the person being
threatened when someone tried to open my car door, and in the other I was
charged over a family member's pistol in a shared vehicle that I did not know
was there. I have maintained my innocence throughout.

I understand your Central Texas participatory defense hub meets on the 2nd and
4th Mondays. I would be grateful to learn how I might take part, whether the
hub could offer court support for my hearing dates, or whether you could point
me toward anyone serving Comal, Guadalupe, or Hays Counties.

Thank you for the work you do — and please pass my thanks to Sadie for
connecting us.

Please reply here or call me at 210-538-3669 ext. 1 whenever it's convenient.

Respectfully,
Jordan Polasek
El Campo, Texas
help@bvtech.org"""},
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
    # --- Round 6: more verified plaintiff-side civil-rights firms ---
    _consult("aug2-lucio", "Lucio Law (Brownsville / Rio Grande Valley)",
             "elucio@luciolaw.com"),
    _consult("aug2-corbett", "Corbett & Corbett LLP (Dallas)",
             "info@corbettfirm.com"),
    _consult("aug2-law-wizard", "Law Wizard PLLC (San Antonio)",
             "zachary@texaslawwizard.com"),
    _consult("aug2-gale", "Gale Law Group, PLLC (Corpus Christi)",
             "Chris@GaleLawGroup.com"),
    _consult("aug2-kcole", "K Cole Law, PLLC (Frisco)", "kcole@kcolelaw.com"),
    # --- Round 8: more verified plaintiff-side civil-rights firms ---
    _consult("aug2-johnson-justice", "Johnson Law Firm (Houston)",
             "njohnson@contactjohnsonlawfirm.com"),
    _consult("aug2-marquez", "Law Office of Daniel A. Marquez (El Paso)",
             "dan@damlawoffice.com"),
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
    # --- Round 7: more NAACP/LULAC branches, legal aid, minority bar
    #     associations (verified emails; duplicate firms + immigrant-only orgs
    #     skipped to stay on target) ---
    _support("aug2-naacp-lubbock", "NAACP Lubbock Branch",
             "info@lubbocknaacp.org"),
    _support("aug2-naacp-tyler", "NAACP Tyler Branch",
             "naacptyler6232@gmail.com"),
    _support("aug2-naacp-elpaso", "NAACP El Paso Branch",
             "naacpelpasobranch@yahoo.com"),
    _support("aug2-naacp-arlington", "NAACP Arlington Branch",
             "7047@arlingtonnaacp.com"),
    _support("aug2-naacp-amarillo", "NAACP Amarillo Branch",
             "president@amanaacp.org"),
    _support("aug2-naacp-brazoria", "NAACP Brazoria County Branch",
             "bcnaacptreasurer@gmail.com"),
    _support("aug2-naacp-sanangelo", "NAACP San Angelo Branch",
             "info-admin@sanangelonaacp.org"),
    _support("aug2-naacp-missouricity", "NAACP Missouri City & Vicinity Branch",
             "secretary@naacpmissouricityvicinity.org"),
    _support("aug2-lulac-d8", "LULAC District VIII (Houston)", "d8mgr@lulac.org"),
    _support("aug2-lulac-dallas-rainbow", "LULAC Dallas Rainbow Council",
             "jessegarciadallas@gmail.com"),
    _support("aug2-lulac-402", "LULAC Education Council 402 (Houston)",
             "hugomojica@gmail.com"),
    _support("aug2-lulac-4971", "LULAC Council 4971 (Temple)",
             "president@lulaccouncil4971.org"),
    _support("aug2-lone-star-legal", "Lone Star Legal Aid (Houston)",
             "communications@lonestarlegal.org"),
    _support("aug2-elpaso-bar", "El Paso Bar Association", "info@elpasobar.com"),
    _support("aug2-maba-houston", "Mexican American Bar Association of Houston",
             "mabahouston@gmail.com"),
    _support("aug2-collin-cdla", "Collin County Criminal Defense Lawyers "
             "Association", "admin@cccdla.org"),
    _support("aug2-justice-net-tc", "Justice Network of Tarrant County",
             "info@justicenetworktc.com"),
    _support("aug2-houston-lawyers", "Houston Lawyers Association",
             "info@houstonlawyersassociation.org"),
    _support("aug2-lcdavis", "L. Clifford Davis Legal Association (Fort Worth)",
             "LCDLEGALASSOC@gmail.com"),
    _support("aug2-jlturner", "J.L. Turner Legal Association (Dallas)",
             "admin@jltla.org"),
    _support("aug2-austin-black-lawyers", "Austin Black Lawyers Association",
             "president@austinblacklawyers.org"),
    _support("aug2-hba-austin", "Hispanic Bar Association of Austin",
             "ericdaviscuellar@gmail.com"),
    _support("aug2-cc-bar", "Corpus Christi Bar Association",
             "corpusbar@corpusbar.com"),
    _support("aug2-aals-tx", "African American Lawyers Section, State Bar of "
             "Texas", "info@aalstx.org"),
    # --- Round 9: minority/county/women bar associations + justice-advocacy +
    #     victim advocacy (verified emails; 3 already-contacted orgs skipped) ---
    _support("aug2-maba-sa", "Mexican American Bar Association of San Antonio",
             "mabasanantonio@yahoo.com"),
    _support("aug2-maba-dallas", "Mexican American Bar Association of Dallas",
             "maba.dtx@gmail.com"),
    _support("aug2-maba-tx", "Mexican American Bar Association of Texas",
             "mail@mabatexas.com"),
    _support("aug2-dallas-hispanic-bar", "Dallas Hispanic Bar Association",
             "mail@dallashispanicbar.com"),
    _support("aug2-sa-black-lawyers", "San Antonio Black Lawyers Association",
             "sanantonioblacklawyers@gmail.com"),
    _support("aug2-austin-asian-bar", "Austin Asian American Bar Association",
             "info@austinaaba.org"),
    _support("aug2-dallas-asian-bar", "Dallas Asian American Bar Association",
             "info@daaba.org"),
    _support("aug2-aaba-houston", "Asian American Bar Association of Houston",
             "president.aabahouston@gmail.com"),
    _support("aug2-tcwla", "Travis County Women Lawyers' Association",
             "info@tcwla.org"),
    _support("aug2-bcwba", "Bexar County Women's Bar Association",
             "info@bexarcountywomensbar.org"),
    _support("aug2-dwla", "Dallas Women Lawyers Association",
             "info@dallaswomenlawyersfoundation.org"),
    _support("aug2-austin-bar", "Austin Bar Association",
             "austinbar@austinbar.org"),
    _support("aug2-tarrant-bar", "Tarrant County Bar Association",
             "admin@tarrantbar.org"),
    _support("aug2-denton-bar", "Denton County Bar Association",
             "executivedirector@dentonbar.com"),
    _support("aug2-collin-bar", "Collin County Bar Association",
             "admin@collincountybar.org"),
    _support("aug2-jefferson-bar", "Jefferson County Bar Association",
             "director@jcba.org"),
    _support("aug2-fortbend-bar-assoc", "Fort Bend County Bar Association",
             "info-fortbendbar@gmx.com"),
    _support("aug2-friends-justice", "Friends of Justice",
             "abean@friendsofjustice.net"),
    _support("aug2-vocal-tx", "VOCAL-TX", "info@vocal-tx.org"),
    _support("aug2-ctd", "Coalition of Texans with Disabilities",
             "info@txdisabilities.org"),
    _support("aug2-faith-in-tx", "Faith in Texas", "awallace@faithintx.org"),
    _support("aug2-cops-metro", "COPS/Metro Alliance (San Antonio)",
             "COPSMETRO@SBCGLOBAL.NET"),
    _support("aug2-move-tx", "MOVE Texas", "tori@movetexas.org"),
    _support("aug2-surj-houston", "Houston SURJ (Showing Up for Racial "
             "Justice)", "surjhtx@gmail.com"),
    _support("aug2-surj-austin", "Undoing White Supremacy Austin (SURJ)",
             "undoingwhitesupremacy@gmail.com"),
    _support("aug2-safe-alliance", "SAFE Alliance (Austin)",
             "safecares@safeaustin.org"),
    _support("aug2-naacp-beaumont", "NAACP Beaumont Branch",
             "bmtnaacp@hotmail.com"),
    _support("aug2-lulac-272", "LULAC Council 272 (Dallas)",
             "Lulacscholarships272@gmail.com"),
    _support("aug2-lulac-4875", "LULAC Council 4875 (El Paso)",
             "fragcm@yahoo.com"),
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
    # --- Round 4 dentists: statewide, specialists first (verified emails) ---
    _dentist("dds-softtouch", "Softtouch Dental & Implants (Plano)",
             "dr.lakhani@softtouchdentist.net"),
    _dentist("dds-prodental", "Pro Dental Dallas (Plano)",
             "office@prodentaldallas.com"),
    _dentist("dds-mosaic", "Mosaic Prosthodontics (Cedar Park)",
             "contactus@mosaicprostx.com"),
    _dentist("dds-grimes", "Grimes Dentistry (Lubbock)",
             "grimesdentistry@yahoo.com"),
    _dentist("dds-stxperio", "South Texas Periodontics & Implants "
             "(Corpus Christi)", "info@stxperio.com"),
    _dentist("dds-friedberg", "Dr. Friedberg & Associates (Houston)",
             "info@drfriedbergandassociates.com"),
    _dentist("dds-cepi", "Center of Endodontics, Periodontics and Implantology "
             "(Allen)", "care@cepi-allen.com"),
    _dentist("dds-pearland-perio", "Pearland Periodontics & Dental Implants",
             "drbonaventura@pearlandperio.com"),
    _dentist("dds-nhos", "North Houston Oral Surgery (Spring)",
             "info@titanium-surgicalarts.com"),
    _dentist("dds-katy-cofs", "The Center for Oral & Facial Surgery (Katy)",
             "xrays@katycofs.com"),
    _dentist("dds-tyler-sedation", "Texas Sedation Dental & Implant Center "
             "(Tyler)", "info@texassedationdental.com"),
    _dentist("dds-east-elpaso", "East El Paso Dentist",
             "smile@eastelpasodentist.com"),
    _dentist("dds-vista-hills", "Vista Hills Family Dental (El Paso)",
             "office@vistahillsfamilydental.com"),
    _dentist("dds-the-dentist-ep", "The Dentist El Paso",
             "thedentistelpaso@gmail.com"),
    _dentist("dds-pershing", "Pershing Family Dental (El Paso)",
             "smile@pershingfamilydental.com"),
    _dentist("dds-acv", "ACV Dental (Edinburg)", "drv@acvdental.com"),
    _dentist("dds-lakes-family", "The Lakes Family Dental (Edinburg)",
             "thelakesfamilydental4428@gmail.com"),
    _dentist("dds-midland-studio", "The Dental Studio of Midland",
             "office@dentalstudiomidland.com"),
    _dentist("dds-denta-odessa", "Denta Dental of Odessa", "info@dentaodessa.com"),
    _dentist("dds-restoration-sa", "Restoration Dental (San Antonio)",
             "frontdesk@restorationdentalSA.com"),
    _dentist("dds-sonterra", "Sonterra Dental (San Antonio)",
             "info@sonterradentalcare.com"),
    _dentist("dds-renew-frisco", "Renew Family Dentistry (Frisco)",
             "smile@renewdentistry.com"),
    _dentist("dds-hq-georgetown", "HQ Dental (Georgetown)",
             "manager.hqdentaldesign@gmail.com"),
    _dentist("dds-gtx-group", "Georgetown Dental Group",
             "info@gtxdentalgroup.com"),
    _dentist("dds-gtx-family", "Georgetown Family Dentistry",
             "info@gtxfamilydentistry.com"),
    _dentist("dds-4405", "4405 Dental Studio (Georgetown)",
             "dredmonds@4405dentalstudio.com"),
    _dentist("dds-bcs", "BCS Family Dental (Bryan)", "office@bcsfamilydental.com"),
    _dentist("dds-katy-family", "Katy Family Dental Group",
             "infos@katyfamilydentalgroup.com"),
    _dentist("dds-charm-katy", "Charm Dental Katy", "info@charmdentalkaty.com"),
    _dentist("dds-friendswood", "Friendswood Smiles",
             "drklavyusheva@gmail.com"),
    _dentist("dds-mann", "Mann Dental (Sugar Land)", "smile@manndental.com"),
    _dentist("dds-sugar-creek", "Sugar Creek Smile Dentistry (Sugar Land)",
             "dentist@sugarcreeksmiledentistry.com"),
    _dentist("dds-pearland-care", "Pearland Dental Care",
             "dentalcare@pearlanddentalcare.com"),
    _dentist("dds-station-waco", "Dental Station Waco",
             "staff@dentalstationwaco.com"),
    _dentist("dds-dental-method", "The Dental Method (Dallas)",
             "dallas@thedentalmethod.com"),
    _dentist("dds-greene-ratcliff", "Greene & Ratcliff Family & Cosmetic "
             "Dentistry (Arlington)", "smiles@stephenratcliffdds.com"),
    _dentist("dds-collins-street", "Collins Street Dental (Arlington)",
             "info.collinsstreetdental@gmail.com"),
    _dentist("dds-allheart", "Allheart Dental Care (Grand Prairie)",
             "allheartdentalgp@gmail.com"),
    _dentist("dds-red-bud", "Red Bud Dental (Round Rock)",
             "redbuddental@gmail.com"),
    _dentist("dds-adc-rr", "Advanced Dental Care of Round Rock",
             "info@adcroundrock.com"),
    _dentist("dds-cedar-park-wellness", "Cedar Park Dental Wellness",
             "info@cedarparkdentalwellness.com"),
    _dentist("dds-ndc-cypress", "NDC Houston Family Dentistry (Cypress)",
             "admin@ndchouston.com"),
    _dentist("dds-solidsmiles", "SolidSMILES Dental (Lewisville)",
             "hello@solid-smiles.com"),
    _dentist("dds-flower-mound", "Flower Mound Dental",
             "frontdesk@flowermounddental.com"),
    _dentist("dds-thompson-cc", "John T. Thompson DDS (Corpus Christi)",
             "johnthompsondds@stx.rr.com"),
    _dentist("dds-dental-images", "Dental Images (Harker Heights)",
             "info@dentalimagestexas.com"),
    _dentist("dds-w-dentistry", "W Dentistry (Lubbock)",
             "info@wdentistrylbk.com"),
    _dentist("dds-lone-star-lbk", "Lone Star Smiles (Lubbock)",
             "lonestarsmileslubbock@gmail.com"),
    _dentist("dds-new-smile-tyler", "New Smile Dental of Tyler",
             "newsmiledentaloftyler@gmail.com"),
    _dentist("dds-humble-smiles", "Humble Smiles", "1humblesmiles@gmail.com"),
    _dentist("dds-humble-dentistry", "Humble Dentistry",
             "office@humbledentist.com"),
    _dentist("dds-austin-family", "Austin Family Dentist",
             "info@austinfamilydentist.com"),
    _dentist("dds-south-austin", "South Austin Dental",
             "info@southaustindental.com"),
    _dentist("dds-beaumont-clinic", "Beaumont Dental Clinic",
             "office@dentistinbeaumont.com"),
    _dentist("dds-all-valley", "All Valley Smiles (Brownsville)",
             "drliz@allvalleysmilesdental.com"),
    _dentist("dds-xavier-leos", "Xavier Leos Family Dentistry (Brownsville)",
             "info@xavierleosfamilydentistry.com"),
    _dentist("dds-ada-weslaco", "Advanced Dental Associates (Weslaco)",
             "adaharligen@gmail.com"),
    _dentist("dds-txdentist101", "Texas Dentist 101 (Bellaire)",
             "txdentist101bellaire@gmail.com"),
    # --- Round 5 dentists: more specialists statewide (verified; dups removed) ---
    _dentist("dds-oms-abilene", "Oral & Maxillofacial Surgery of Abilene",
             "info@oralsurgeryabilene.com"),
    _dentist("dds-lovelace", "Teri Brooks Lovelace DDS MS (Abilene)",
             "xrays@lovelacedds.com"),
    _dentist("dds-hot-perio", "Heart of Texas Periodontics & Implantology "
             "(Temple)", "HeartOfTXPerioImplant@mydentalmail.com"),
    _dentist("dds-todays-galveston", "Today's Dentistry (Galveston)",
             "tdtx.galveston@gmail.com"),
    _dentist("dds-todays-leaguecity", "Today's Dentistry (League City)",
             "tdtx.lc@gmail.com"),
    _dentist("dds-gossett", "Gossett Implant & Oral Surgery (Schertz)",
             "schertz@gossettoralsurgery.com"),
    _dentist("dds-fw-perio", "FW Periodontics (Fort Worth)",
             "info@fwperiodontics.com"),
    _dentist("dds-britain-perio", "Britain Periodontics (Fort Worth)",
             "officemanager@britainperio.com"),
    _dentist("dds-perio-assoc-fw", "Periodontal Associates (Fort Worth)",
             "contact@periotexas.com"),
    _dentist("dds-adamo", "Adamo Dental Implants & Periodontics (Waco)",
             "frontdesk@adamodentalimplants.com"),
    _dentist("dds-gopin", "Bruce Gopin DDS Periodontics (El Paso)",
             "gopinperio@elp.rr.com"),
    _dentist("dds-lubbock-perio", "Lubbock Perio & Implant Center",
             "lubbockimplantcenter@gmail.com"),
    _dentist("dds-shoal-creek", "Shoal Creek Prosthodontic Group (Austin)",
             "scpg@sbcglobal.net"),
    _dentist("dds-regen-allen", "REGEN Periodontics & Dental Implant Center "
             "(Allen)", "info@regenperiotx.com"),
    _dentist("dds-lorenzana", "Lorenzana Periodontics (San Antonio)",
             "lorenzanaperio@yahoo.com"),
    _dentist("dds-austin-perio", "Austin Periodontal Associates",
             "chari@austinperiodontal.com"),
    _dentist("dds-smile-solutions-rr", "Smile Solutions Dentistry (Round Rock)",
             "info@smilesolutionsroundrock.com"),
    _dentist("dds-village-perio", "Village Periodontics & Implant Dentistry "
             "(Lewisville)", "info@villageperio.com"),
    _dentist("dds-genesis-fm", "Genesis Dental (Flower Mound)",
             "genesisdental4u@gmail.com"),
]

# --- Scheduling: a first wave goes out now; the bulk holds until Monday 9am
#     Central (14:00 UTC 2026-08-03) so it lands when open/reply rates are
#     highest. A task with no "not_before" is eligible immediately; otherwise
#     it waits until now >= not_before.
_MONDAY_9AM_CT = "2026-08-03T14:00:00+00:00"
_NOW_WAVE = {
    "referral-ctx-pdh",       # warm referral — send now, not Monday-gated
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
