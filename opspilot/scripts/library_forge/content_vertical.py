"""Library Forge content — vertical compliance packs + Texas legal pack.

The verticals match BVTech's outreach targets exactly (CPAs, law firms,
dental/medical, financial advisors), so every prospecting conversation has a
ready-made compliance deliverable behind it. 18 documents.
"""

CAT_VRT = ("VRT", "Vertical Compliance Packs")
CAT_TXL = ("TXL", "Texas Legal & Regulatory")

_WISP_CORE = [
    ("Designated security coordinator",
     "A qualified individual is designated to implement and supervise this WISP. For managed "
     "clients, BVTech LLC serves as the operational coordinator; the firm's principal retains "
     "ultimate accountability."),
    ("Risk assessment",
     "The firm identifies where client data lives (tax software, email, portals, paper), the "
     "reasonably foreseeable internal and external risks to it, and assesses the sufficiency of "
     "safeguards at least annually and after any incident."),
    ("Access controls & MFA",
     "Access to client data is limited to personnel who need it. Multi-factor authentication is "
     "required on email, tax software, remote access, and any system holding client records."),
    ("Encryption",
     "Client data is encrypted in transit (TLS) and at rest on laptops, portable media, and cloud "
     "storage. Unencrypted transmission of returns or PII is prohibited."),
    ("Monitoring & anti-malware",
     "Managed endpoint protection with real-time detection runs on every device; alerts are "
     "monitored and triaged by the coordinator."),
    ("Patch & configuration management",
     "Operating systems and applications are patched on a managed cadence; unsupported software "
     "that touches client data is retired."),
    ("Employee training & discipline",
     "All personnel receive security awareness training at hire and annually, including phishing "
     "recognition; violations of this WISP carry documented consequences."),
    ("Vendor oversight",
     "Service providers that access client data are selected for their ability to maintain "
     "safeguards and are bound by written contract to do so."),
    ("Incident response & notification",
     "Suspected data theft or breach triggers the incident response procedure, including required "
     "notifications (for tax preparers: the IRS Stakeholder Liaison and state authorities; in "
     "Texas, the Sec. 521.053 notification duties)."),
    ("Data retention & destruction",
     "Client records are retained only as long as required and destroyed securely (NIST 800-88) "
     "with certification. Devices are sanitized before disposal."),
    ("Continuous evaluation",
     "This WISP is reviewed at least annually, on material change to operations, and after any "
     "security event, with revisions documented."),
]


def _wisp(idx: int, slug: str, title: str, audience: str, law_para: str, extras: list[str]) -> dict:
    return {
        "id": f"BVT-VRT-{180 + idx}", "slug": slug, "title": title,
        "category": CAT_VRT[0], "category_label": CAT_VRT[1], "visibility": "client",
        "kind": "policy", "counsel": True,
        "summary": f"A complete Written Information Security Plan for {audience}, ready to adopt: "
                   "designate the coordinator, sign it, and keep it with the firm's records. "
                   "BVTech operationalizes every safeguard below under a managed services agreement.",
        "sections": [
            {"h": "Legal Basis", "kind": "para", "body": law_para},
            {"h": "Safeguards Program", "kind": "clauses",
             "body": _WISP_CORE + [("Additional vertical safeguards", x) for x in extras] if extras
                     else _WISP_CORE},
            {"h": "Adoption", "kind": "fills", "body": [
                "Firm name:", "Designated coordinator:", "Adopted on (date):",
                "Principal signature:", "Annual review due:"]},
        ],
    }


def build() -> list[dict]:
    docs: list[dict] = []
    # ---- CPA / tax pack ----
    docs.append(_wisp(1, "CPA_Tax_Preparer_WISP_IRS_4557",
        "Written Information Security Plan (WISP) - CPA & Tax Preparer Edition",
        "CPA firms and tax preparers",
        "Federal law requires every professional tax preparer to have a written information "
        "security plan: the FTC Safeguards Rule (16 C.F.R. Part 314, under the Gramm-Leach-Bliley "
        "Act) applies to tax preparers as financial institutions, and IRS Publication 4557 "
        "('Safeguarding Taxpayer Data') directs preparers to implement one. A current WISP is also "
        "attested when renewing a PTIN. This document satisfies that obligation when adopted, "
        "implemented, and reviewed annually.",
        ["EFIN/PTIN credentials are protected, never shared, and monitored for misuse; IRS e-Services "
         "accounts use the strongest available authentication.",
         "Client tax data leaves the firm only through encrypted portals - never as plain email attachments."]))
    docs.append({
        "id": "BVT-VRT-182", "slug": "CPA_Firm_Security_Checklist",
        "title": "CPA Firm Annual Security Checklist (IRS 4557 aligned)",
        "category": CAT_VRT[0], "category_label": CAT_VRT[1], "visibility": "client",
        "kind": "checklist",
        "summary": "The working checklist behind the WISP: run it annually (ideally before filing "
                   "season) and keep the completed copy as evidence of your safeguards program.",
        "sections": [{"h": "Annual Items", "kind": "checks", "body": [
            "WISP reviewed, updated, and re-signed by the principal",
            "MFA verified on email, tax software, e-Services, and remote access",
            "All staff completed security awareness training this year",
            "Phishing simulation run and repeat-clickers retrained",
            "Endpoint protection active and reporting on every device",
            "Operating systems and tax software fully patched",
            "Backups verified by an actual test restore of client files",
            "Encrypted portal in use for all client document exchange",
            "Old client records past retention destroyed with certificate",
            "Departed-staff accounts disabled and access reviewed",
            "Vendor list reviewed; contracts include safeguard obligations",
            "Incident response contacts current (IRS Stakeholder Liaison, insurer, counsel, BVTech)"]},
        ]})
    # ---- Financial advisor pack ----
    docs.append(_wisp(3, "Financial_Advisor_WISP_FTC_Safeguards",
        "Written Information Security Plan (WISP) - Financial Advisory Edition",
        "investment advisers, insurance agencies, and lenders",
        "The FTC Safeguards Rule (16 C.F.R. Part 314) requires covered financial institutions - "
        "including many advisers, agencies, and lenders - to develop, implement, and maintain a "
        "written information security program with a designated qualified individual, risk "
        "assessments, specified safeguards (access controls, encryption, MFA, monitoring, secure "
        "disposal), staff training, vendor oversight, and an incident response plan. SEC-registered "
        "advisers face parallel obligations under Regulation S-P. This document implements those "
        "requirements when adopted and maintained.",
        ["Annual written report on the security program is delivered to the firm's principal or board, "
         "as the Safeguards Rule requires."]))
    # ---- Law firm pack ----
    docs.append({
        "id": "BVT-VRT-184", "slug": "Law_Firm_Client_Confidentiality_Security_Program",
        "title": "Law Firm Information Security & Client Confidentiality Program",
        "category": CAT_VRT[0], "category_label": CAT_VRT[1], "visibility": "client",
        "kind": "policy", "counsel": True,
        "summary": "A security program built around a lawyer's professional duties: Texas "
                   "Disciplinary Rule 1.05 (confidentiality) and the duty of technological "
                   "competence, informed by ABA Formal Opinions 477R (secure communication) and "
                   "483 (data breach obligations).",
        "sections": [
            {"h": "Professional Duty Basis", "kind": "para", "body":
                "Client confidences are protected by Texas Disciplinary Rules of Professional "
                "Conduct Rule 1.05, and competent representation requires keeping pace with the "
                "benefits and risks of relevant technology. ABA Formal Op. 477R calls for "
                "reasonable efforts - including encryption where appropriate - when communicating "
                "client information, and Op. 483 addresses a lawyer's obligations when a breach "
                "occurs, including prompt client notification. This program gives those duties "
                "operational teeth."},
            {"h": "Program Safeguards", "kind": "clauses", "body": [
                ("Matter-based access control", "Access to matter files follows need-to-know; departed personnel lose access the same day; ethical walls are enforced technically when required."),
                ("Encrypted communication & storage", "Email encryption is available for sensitive matters, portals are used for client file exchange, and all firm devices are encrypted at rest."),
                ("Privileged-data handling", "Privileged material is stored only in firm-controlled systems; personal accounts and unmanaged devices are prohibited for client work."),
                ("Managed detection & response", "Every firm endpoint runs managed EDR with 24/7 alerting; email is filtered for phishing and account-takeover indicators."),
                ("Breach response & client notice", "Suspected compromise triggers the incident response plan; affected clients are informed promptly and honestly, consistent with Op. 483 and Texas Sec. 521.053."),
                ("Business continuity for deadlines", "Backups are tested and recovery objectives documented so court deadlines survive hardware loss, ransomware, or disaster."),
                ("Trust-account payment controls", "Wire and trust-account transactions require out-of-band verification to defeat business-email-compromise fraud."),
                ("Training for legal staff", "Attorneys and staff train annually on phishing, BEC, and confidentiality technology duties."),
            ]},
            {"h": "Adoption", "kind": "fills", "body": [
                "Firm name:", "Managing partner:", "Adopted on:", "Signature:"]},
        ],
    })
    # ---- Dental / medical HIPAA pack ----
    docs.append({
        "id": "BVT-VRT-185", "slug": "HIPAA_Security_Rule_Compliance_Program_Dental_Medical",
        "title": "HIPAA Security Rule Compliance Program - Dental & Medical Practices",
        "category": CAT_VRT[0], "category_label": CAT_VRT[1], "visibility": "client",
        "kind": "policy", "counsel": True,
        "summary": "The administrative, physical, and technical safeguards of the HIPAA Security "
                   "Rule (45 C.F.R. Part 164, Subpart C) organized into an adoptable program for a "
                   "covered practice, operated day-to-day by BVTech as business associate.",
        "sections": [
            {"h": "Scope", "kind": "para", "body":
                "This program covers all electronic protected health information (ePHI) the practice "
                "creates, receives, maintains, or transmits - practice management and imaging systems, "
                "email, backups, and devices. BVTech LLC operates safeguards under a signed Business "
                "Associate Agreement (BVT-LGL-010)."},
            {"h": "Safeguards", "kind": "clauses", "body": [
                ("Security management & risk analysis", "A written risk analysis of ePHI systems is performed annually and after material change (use BVT-VRT-186); identified risks receive documented remediation."),
                ("Security officer", "The practice designates a security officer; BVTech provides operational support and evidence for that role."),
                ("Workforce access & termination", "ePHI access is role-based, uniquely identified, and revoked immediately on separation."),
                ("Training & sanctions", "Workforce members train on ePHI protection at hire and annually; violations follow a documented sanction policy."),
                ("Facility & workstation security", "Operatory and front-desk screens are positioned or shielded against public view; server closets are locked; devices are inventoried."),
                ("Encryption & transmission security", "ePHI is encrypted at rest on portable devices and in transit; texting PHI over unencrypted SMS is prohibited."),
                ("Audit controls & integrity", "System activity involving ePHI is logged and reviewed; integrity mechanisms protect ePHI from improper alteration."),
                ("Contingency plan", "Data backup, disaster recovery, and emergency-mode operation plans are documented and tested at least annually."),
                ("Business associates", "Vendors handling ePHI sign BAAs before any disclosure; the vendor list is reviewed annually."),
                ("Breach notification", "Suspected breaches are risk-assessed under the HIPAA Breach Notification Rule; individuals, HHS, and where required media are notified within required timelines."),
            ]},
            {"h": "Adoption", "kind": "fills", "body": [
                "Practice name:", "Security officer:", "Adopted on:", "Signature:"]},
        ],
    })
    docs.append({
        "id": "BVT-VRT-186", "slug": "HIPAA_Security_Risk_Assessment_Worksheet",
        "title": "HIPAA Security Risk Assessment (SRA) Worksheet",
        "category": CAT_VRT[0], "category_label": CAT_VRT[1], "visibility": "client",
        "kind": "checklist",
        "summary": "The annual risk-analysis worksheet MIPS/meaningful-use audits ask for: where "
                   "ePHI lives, what threatens it, and what you're doing about it.",
        "sections": [
            {"h": "ePHI Inventory", "kind": "fills", "body": [
                "Practice management system & host:", "Imaging/X-ray systems:",
                "Email platform:", "Backup destinations:", "Mobile devices with ePHI:",
                "Vendors with ePHI access:"]},
            {"h": "Threat & Safeguard Review", "kind": "checks", "body": [
                "Unique logins for every workforce member (no shared accounts)",
                "MFA on email and remote access to ePHI systems",
                "Encryption verified on servers, workstations, laptops, and backups",
                "EDR/antivirus active on every device touching ePHI",
                "Operating systems and PM software supported and patched",
                "Backup restore tested within the last 12 months",
                "Workforce HIPAA security training current",
                "BAAs on file for every vendor handling ePHI",
                "Termination checklist removes access same-day",
                "Audit logging enabled on the PM system and reviewed",
                "Server/network closet physically secured",
                "Incident response and breach notification contacts current"]},
            {"h": "Findings", "kind": "fills", "body": [
                "Risks identified:", "Remediation plan / owner / date:",
                "Assessor:", "Assessment date:"]},
        ],
    })
    # ---- Vertical one-page briefs (client-facing door-openers) ----
    briefs = [
        ("187", "Law_Firms", "Law Firms", "Texas Rule 1.05 confidentiality, ABA Ops. 477R/483, and court-deadline continuity", [
            "Confidentiality is an ethical duty - a breach is a bar problem, not just an IT problem.",
            "BEC wire fraud targets firm trust accounts; out-of-band verification stops it.",
            "Tested backups keep filing deadlines survivable through ransomware or hardware loss.",
            "Our Law Firm Security Program (BVT-VRT-184) is ready to adopt at engagement."]),
        ("188", "CPA_Tax_Firms", "CPA & Tax Firms", "FTC Safeguards Rule + IRS Pub. 4557 - a WISP is legally required, and PTIN renewal attests to it", [
            "Every paid preparer must maintain a written information security plan (WISP).",
            "EFIN theft and client-refund fraud are the top attacks on tax practices.",
            "Our CPA WISP (BVT-VRT-181) satisfies the requirement the day you adopt it.",
            "Filing-season uptime is an SLA here, not a hope."]),
        ("189", "Dental_Medical", "Dental & Medical Practices", "HIPAA Security Rule safeguards + annual SRA evidence for MIPS audits", [
            "HIPAA requires an annual security risk assessment - we run it and hand you the evidence.",
            "Practice-management downtime is measured in cancelled chairs; recovery objectives fix that.",
            "Encrypted-everything: devices, backups, transmissions - verified, not assumed.",
            "BAA signed on day one (BVT-LGL-010); program in BVT-VRT-185."]),
        ("190", "Financial_Advisors", "Financial Advisors & Insurance", "FTC Safeguards Rule program with the required annual report to leadership", [
            "The Safeguards Rule requires a qualified individual, a written program, MFA, encryption, and vendor oversight - we operate all of it.",
            "Client PII plus wire authority makes advisories prime BEC targets.",
            "Annual written security report to your principal - delivered, as the rule requires.",
            "WISP ready to adopt at engagement (BVT-VRT-183)."]),
    ]
    for num, slug, name, hook, points in briefs:
        docs.append({
            "id": f"BVT-VRT-{num}", "slug": f"Security_Brief_{slug}",
            "title": f"One-Page Security Brief - {name}",
            "category": CAT_VRT[0], "category_label": CAT_VRT[1], "visibility": "client",
            "kind": "onepager",
            "summary": f"Why {name.lower()} have specific, legally grounded security obligations - "
                       f"and exactly how BVTech covers them: {hook}.",
            "sections": [
                {"h": "What Your Profession Requires", "kind": "para", "body": hook + "."},
                {"h": "The Four Things That Matter", "kind": "bullets", "body": points},
                {"h": "Next Step", "kind": "para", "body":
                    "A free 15-minute review tells you exactly where you stand - no pitch, and you "
                    "keep the findings either way. Book any slot at bvtech.org/book or reply to "
                    "your BVTech contact."},
            ],
        })
    # ---- Texas legal pack ----
    docs.append({
        "id": "BVT-TXL-208", "slug": "Texas_Breach_Notification_Procedure_521.053",
        "title": "Texas Data Breach Notification Procedure (Bus. & Com. Code Sec. 521.053)",
        "category": CAT_TXL[0], "category_label": CAT_TXL[1], "visibility": "internal",
        "kind": "policy", "counsel": True,
        "summary": "The clock-driven procedure for Texas breach duties: who must be told, by when, "
                   "and with what content - integrated with the Incident Response Plan.",
        "sections": [
            {"h": "Legal Duties", "kind": "bullets", "body": [
                "Notify affected Texas residents without unreasonable delay and no later than 60 days after determining a breach of system security occurred involving sensitive personal information.",
                "If 250 or more Texas residents are affected, notify the Texas Attorney General no later than 30 days after determination - via the AG's electronic form - including the nature of the breach, number of residents notified, safeguard measures, and law-enforcement engagement.",
                "Consumer reporting agencies must be notified when more than 10,000 persons are notified.",
                "Notification may be delayed at the documented request of law enforcement.",
                "Other regimes may run in parallel and faster: HIPAA breach rules, IRS preparer duties, contractual client commitments, and cyber-insurance conditions."]},
            {"h": "Procedure", "kind": "clauses", "body": [
                ("Determination & clock start", "The incident commander documents the date the breach was 'determined' - both notification clocks run from that date. Preserve the determination memo."),
                ("Scope the affected population", "Identify affected individuals and their states of residence; Texas counts drive AG and CRA duties, other states trigger their own statutes."),
                ("Engage counsel and carrier", "Before external notices go out, engage breach counsel and the cyber-insurance carrier - most policies require carrier consent to notification costs."),
                ("Draft and deliver notices", "Use the content requirements of Sec. 521.053(b); deliver by written or permitted electronic notice; substitute notice only when statutory thresholds are met."),
                ("File the AG notification", "At 250+ Texas residents, submit the AG's form within 30 days; keep the submission receipt in the incident record."),
                ("Close the record", "File all notices, dates, counts, and decisions in the incident record; feed lessons into the POA&M."),
            ]},
        ],
    })
    docs.append({
        "id": "BVT-TXL-209", "slug": "Texas_Data_Privacy_Security_Act_Readiness",
        "title": "Texas Data Privacy & Security Act (TDPSA) Readiness Guide",
        "category": CAT_TXL[0], "category_label": CAT_TXL[1], "visibility": "client",
        "kind": "policy",
        "summary": "What the TDPSA (in force since 2024) means for Texas small businesses and for "
                   "BVTech as a processor - applicability, consumer rights, and the small-business "
                   "sensitive-data rule.",
        "sections": [
            {"h": "Applicability", "kind": "para", "body":
                "The TDPSA applies to persons conducting business in Texas that process or sell "
                "personal data, with a notable carve-out: small businesses (as defined by the U.S. "
                "SBA) are largely exempt - EXCEPT that they may not sell sensitive personal data "
                "without consumer consent. Most BVTech clients are exempt small businesses; the "
                "duties below still represent best practice and apply fully once a client outgrows "
                "the exemption."},
            {"h": "Core Duties (non-exempt controllers)", "kind": "bullets", "body": [
                "Post a privacy notice covering categories processed, purposes, sharing, and consumer rights.",
                "Honor consumer rights: access, correction, deletion, portability, and opt-out of sale, targeted advertising, and profiling.",
                "Obtain consent before processing sensitive data (health, biometrics, precise geolocation, children's data).",
                "Bind processors (like BVTech) by contract - our DPA (BVT-LGL-011) satisfies the processor-contract requirement.",
                "Respond to verified consumer requests within 45 days (one 45-day extension permitted).",
                "Enforcement is by the Texas Attorney General with a 30-day cure period; there is no private right of action."]},
            {"h": "BVTech's Role", "kind": "para", "body":
                "As processor, BVTech processes client-entrusted personal data only on documented "
                "instructions, maintains the safeguards in this library, assists with consumer-rights "
                "responses where systems permit, and flows the same duties to subprocessors."},
        ],
    })
    docs.append({
        "id": "BVT-TXL-210", "slug": "Texas_Contract_Rider",
        "title": "Texas Law Contract Rider (attach to any BVTech agreement)",
        "category": CAT_TXL[0], "category_label": CAT_TXL[1], "visibility": "internal",
        "kind": "agreement", "counsel": True, "party_b": "Client",
        "summary": "A short rider that hardens any BVTech agreement under Texas law: governing law "
                   "and venue, e-signature validity, notice mechanics, and enforceability boilerplate.",
        "sections": [
            {"h": "Rider Terms", "kind": "clauses", "body": [
                ("Governing law", "This Agreement is governed by the laws of the State of Texas, without regard to conflict-of-laws principles."),
                ("Venue and jurisdiction", "Exclusive venue for any dispute lies in the state courts of Wharton County, Texas, or the United States District Court for the Southern District of Texas, and the parties consent to personal jurisdiction there."),
                ("Electronic execution", "This Agreement may be executed electronically and in counterparts; electronic signatures are enforceable under the Texas Uniform Electronic Transactions Act (Tex. Bus. & Com. Code ch. 322) and the federal E-SIGN Act."),
                ("Notices", "Formal notices are effective when delivered by certified mail to the addresses on the signature page or by email with confirmed receipt to the designated notice addresses."),
                ("Severability & waiver", "If any provision is held unenforceable, the remainder continues in effect; failure to enforce a provision is not a waiver of it."),
                ("Attorney's fees", "In any action to enforce this Agreement, the prevailing party is entitled to recover reasonable attorney's fees and costs, as permitted by Tex. Civ. Prac. & Rem. Code ch. 38."),
                ("Entire agreement", "This rider, together with the agreement it accompanies, is the entire agreement on its subject and supersedes prior discussions; amendments must be written and signed."),
            ]},
        ],
    })
    docs.append({
        "id": "BVT-TXL-211", "slug": "Electronic_Signature_Records_Policy_UETA",
        "title": "Electronic Signature & Records Policy (UETA / E-SIGN)",
        "category": CAT_TXL[0], "category_label": CAT_TXL[1], "visibility": "internal",
        "kind": "policy",
        "summary": "How BVTech executes and retains agreements electronically so they hold up: "
                   "consent, attribution, integrity, and retention under Texas UETA and E-SIGN.",
        "sections": [
            {"h": "Policy", "kind": "clauses", "body": [
                ("Validity", "BVTech conducts transactions electronically. Under Tex. Bus. & Com. Code ch. 322 and 15 U.S.C. ch. 96, a record or signature may not be denied legal effect solely because it is electronic."),
                ("Consent", "Counterparties demonstrate consent to transact electronically by executing electronically; consumer-facing flows present the required E-SIGN disclosures."),
                ("Attribution", "Signatures are attributed through authenticated portal sessions, verified email, or commercial e-sign platforms that capture signer identity, timestamp, and IP."),
                ("Integrity & audit trail", "Executed documents are stored read-only with their audit certificates; alterations after execution void the stored copy and require re-execution."),
                ("Retention", "Executed agreements are retained for the life of the relationship plus six years, satisfying UETA's retention-by-accurate-reproduction standard."),
            ]},
        ],
    })
    docs.append({
        "id": "BVT-TXL-212", "slug": "Records_Retention_Destruction_Schedule",
        "title": "Records Retention & Destruction Schedule",
        "category": CAT_TXL[0], "category_label": CAT_TXL[1], "visibility": "internal",
        "kind": "policy",
        "summary": "How long each record class is kept and how it dies: the schedule that backs "
                   "the destruction certificates and defends the company in disputes.",
        "sections": [
            {"h": "Schedule", "kind": "table",
             "headers": ["Record class", "Retention", "Destruction"],
             "widths": [70, 50, 60],
             "body": [
                 ["Client contracts & riders", "Relationship + 6 years", "Certified destruction"],
                 ["Invoices & financial records", "7 years", "Certified destruction"],
                 ["Incident records & breach files", "6 years", "Certified destruction"],
                 ["Backup snapshots", "Per client backup policy", "Automatic rotation"],
                 ["Employee records", "Employment + 4 years", "Certified destruction"],
                 ["Security logs & audit trails", "1 year minimum", "Automatic rotation"],
                 ["Training & compliance evidence", "6 years", "Certified destruction"],
                 ["Prospect/marketing data", "2 years of inactivity", "Deletion"],
             ]},
            {"h": "Destruction Standard", "kind": "para", "body":
                "Digital media is sanitized per NIST SP 800-88 (clear/purge/destroy by media type); "
                "paper is cross-cut shredded. Destruction is certified using BVT-FRM-263. Litigation "
                "hold suspends this schedule for affected records immediately upon notice."},
        ],
    })
    docs.append({
        "id": "BVT-TXL-213", "slug": "Texas_Client_Compliance_Snapshot",
        "title": "Texas Small-Business Compliance Snapshot (client-shareable)",
        "category": CAT_TXL[0], "category_label": CAT_TXL[1], "visibility": "client",
        "kind": "onepager",
        "summary": "One page for Texas owners: the four legal regimes that most often apply to "
                   "their data, and the one-line answer for each.",
        "sections": [
            {"h": "The Four Regimes", "kind": "bullets", "body": [
                "Texas breach notification (Bus. & Com. Code Sec. 521.053): 60 days to notify affected Texans; 30 days to the Attorney General at 250+ residents. Have an incident plan BEFORE you need it.",
                "TDPSA: most small businesses are exempt, but selling sensitive personal data without consent is prohibited for everyone; processors must be under contract.",
                "Industry rules ride on top: HIPAA for health, FTC Safeguards/IRS 4557 for financial and tax, professional-conduct duties for lawyers.",
                "Contracts count too: your clients' MSAs and your cyber-insurance policy impose notification and safeguard duties with their own deadlines."]},
            {"h": "What BVTech Does About It", "kind": "para", "body":
                "Every managed client gets the safeguard stack these regimes expect - MFA, "
                "encryption, monitoring, tested backups, training - plus the paperwork that proves "
                "it: adopted policies, assessment evidence, and an incident plan with the Texas "
                "clocks already built in."},
        ],
    })
    return docs
