"""Library Forge content — NIST 800-171 r2 pack + NIST CSF 2.0 program pack.

Every policy distills the family's actual requirements into enforceable
policy statements, then adds a matching self-assessment checklist, so the
suite works both as governance (what we require) and as evidence (how we
verify). 39 documents total.
"""

CAT_CMP = ("CMP", "NIST 800-171 Compliance")
CAT_CSF = ("CSF", "NIST CSF 2.0 Program")

# (family number, name, [policy statements], MSP implementation note)
FAMILIES = [
    ("3.1", "Access Control", [
        "System access is limited to authorized users, to processes acting on behalf of authorized users, and to authorized devices; every account is uniquely assigned and approved before creation.",
        "Access follows least privilege: users receive only the transactions and functions their role requires, and privileged accounts are separate from daily-driver accounts.",
        "Privileged functions are captured in audit logs, and non-privileged users are technically prevented from executing them.",
        "Unsuccessful logon attempts are limited; sessions lock after 15 minutes of inactivity with pattern-hiding displays and terminate after a defined condition.",
        "Remote access is routed through managed access control points, encrypted in transit, and monitored; privileged remote sessions require explicit authorization.",
        "Wireless access requires authorization and authentication before connection; personal or unmanaged devices connect only to segregated guest networks.",
        "Mobile devices that access company or client data are managed, encrypted, and remotely wipeable.",
        "Use of external systems and portable storage on external systems is controlled and, by default, prohibited without written approval.",
        "Publicly accessible content is reviewed before posting to ensure no controlled or client-confidential information is exposed.",
    ], "BVTech implements this family through Microsoft 365 conditional access, role-based Pulse portal permissions, separate -admin accounts, RMM-enforced screen locks, and guest network segregation on managed firewalls."),
    ("3.2", "Awareness & Training", [
        "All personnel receive security awareness training at hire and at least annually, covering the risks and the policies applicable to their role.",
        "Personnel with security-relevant duties (administrators, technicians, finance) receive role-specific training before receiving those duties.",
        "Training covers recognition and reporting of social engineering, phishing, and insider-threat indicators.",
        "Training completion is tracked and reported; overdue training suspends privileged access until completed.",
        "Simulated phishing exercises run at least quarterly; repeat clickers receive targeted remediation training.",
    ], "Delivered through the BVTech Cyber Academy in the OpsPilot portal: monthly refreshed modules, tracked completion, XP/streak incentives, and per-client compliance reporting."),
    ("3.3", "Audit & Accountability", [
        "Systems create and retain audit logs sufficient to enable monitoring, analysis, investigation, and reporting of unlawful or unauthorized activity.",
        "Actions of individual users are uniquely traceable to those users for accountability.",
        "Logged events are reviewed on a defined cadence and the set of audited events is re-evaluated at least annually.",
        "Audit failures generate alerts to responsible personnel within 24 hours.",
        "Audit records are correlated across sources for investigation, support on-demand analysis and reporting, and use synchronized authoritative time.",
        "Audit information and tools are protected from unauthorized access, modification, and deletion; log management is restricted to a defined privileged subset.",
    ], "Implemented via Microsoft 365 unified audit log, RMM agent event capture into Pulse monitoring, firewall syslog retention, and time synchronization to authoritative NTP."),
    ("3.4", "Configuration Management", [
        "Baseline configurations and inventories of systems, hardware, software, and firmware are established and maintained through each system's lifecycle.",
        "Security configuration settings are established, enforced, and documented for all technology products employed.",
        "Changes to systems are tracked, reviewed, approved via change control, and analyzed for security impact before deployment.",
        "Nonessential programs, functions, ports, protocols, and services are restricted, disabled, or removed.",
        "Software execution follows a deny-by-default posture where feasible (application allow-listing on servers and high-risk endpoints).",
        "User-installed software is controlled and monitored; unauthorized software is removed on detection.",
    ], "Enforced through RMM configuration baselines, automated software inventory in Pulse, documented change tickets, and hardening checklists applied at onboarding (BVT-CHK series)."),
    ("3.5", "Identification & Authentication", [
        "Every user, process, and device is uniquely identified and authenticated before access is granted.",
        "Multi-factor authentication is required for all privileged accounts, all remote access, and all cloud email/identity platforms - no exceptions without a written, time-boxed waiver.",
        "Replay-resistant authentication mechanisms are used for network access to privileged and non-privileged accounts.",
        "Identifier reuse is prevented for a defined period and inactive identifiers are disabled after 45 days.",
        "Passwords meet minimum complexity with mandatory change on first use, are checked against known-breached lists, are stored and transmitted only in cryptographically protected form, and are never reused across the last 10 generations.",
        "Feedback of authentication information is obscured (no shoulder-surfable echo).",
    ], "Implemented via Entra ID with enforced MFA and banned-password lists, per-technician named accounts in every tool, and quarterly dormant-account sweeps driven by Pulse posture checks."),
    ("3.6", "Incident Response", [
        "An operational incident-handling capability exists covering preparation, detection, analysis, containment, recovery, and user response activities.",
        "Incidents are tracked, documented, and reported to designated internal officials and, where contract or law requires, to affected clients and authorities within required timelines.",
        "The incident response capability is tested at least annually via tabletop or functional exercise.",
        "Post-incident reviews capture lessons learned and feed corrective actions into policy and configuration baselines.",
    ], "Operationalized in BVT-IRP-045 (Incident Response Plan), the ransomware and BEC playbooks, and Texas Bus. & Com. Code Sec. 521.053 notification procedures in BVT-TXL-208."),
    ("3.7", "Maintenance", [
        "System maintenance is performed and logged; tools, techniques, and personnel used for maintenance are controlled.",
        "Equipment removed for off-site maintenance is sanitized of any controlled or client data first.",
        "Media containing diagnostic or test programs are checked for malicious code before use.",
        "Nonlocal (remote) maintenance sessions require multi-factor authentication and are terminated when complete.",
        "Maintenance personnel without required access authorization are supervised during maintenance activities.",
    ], "Maintenance is performed by named, vetted BVTech technicians through MFA-protected remote tooling, with session logging in the RMM and sanitization per BVT-FRM media procedures."),
    ("3.8", "Media Protection", [
        "System media containing sensitive or client data - paper and digital - is protected, and access is limited to authorized users.",
        "Media is sanitized or destroyed in accordance with NIST SP 800-88 before disposal or release for reuse, and destruction is certified in writing.",
        "Media containing sensitive data is marked, controlled during transport outside secure areas, and encrypted when carried on portable storage.",
        "Use of removable media is restricted by policy and technical control; media without an identifiable owner is prohibited.",
        "Backup media and locations are protected with the same rigor as production data, including encryption at rest.",
    ], "Enforced through BitLocker/FileVault on portable devices, USB restrictions via RMM policy, certified destruction (BVT-FRM-263 certificate), and encrypted, access-controlled backup repositories."),
    ("3.9", "Personnel Security", [
        "Individuals are screened commensurate with role risk before being granted access to systems holding sensitive or client data.",
        "System access is revoked within one business hour of termination and reviewed upon transfer; credentials, tokens, and equipment are recovered through the offboarding checklist.",
        "Confidentiality and acceptable-use obligations survive employment and are acknowledged in writing at hire.",
    ], "Backed by BVT-INT-064 confidentiality agreements, the BVT-CHK offboarding checklist, and automated account-disable runbooks in Pulse."),
    ("3.10", "Physical Protection", [
        "Physical access to systems, equipment, and operating environments is limited to authorized individuals.",
        "Visitors are escorted, their activity monitored, and physical access is logged; audit logs of physical access are retained.",
        "Physical access devices (keys, badges, codes) are controlled, inventoried, and rotated on personnel change.",
        "Safeguarding measures for sensitive data are enforced at alternate work sites (home offices), including screen privacy, locked storage, and household-member exclusion from work devices.",
    ], "Implemented via keyed/badged access at BVTech facilities, the visitor log (BVT-FRM-262), and the Remote Work Standard for technician home offices."),
    ("3.11", "Risk Assessment", [
        "Risk to operations, assets, and individuals arising from system operation is assessed at least annually and upon major change.",
        "Vulnerability scanning runs on a defined cadence and when new vulnerabilities affecting the environment are identified; results feed the remediation queue.",
        "Identified vulnerabilities are remediated within timeframes commensurate with risk: critical/exploited within 72 hours, high within 14 days, others within 30 days.",
    ], "Driven by Pulse posture scoring, the CISA KEV feed integrated into daily monitoring, RMM patch compliance, and the risk register template (BVT-INT-069)."),
    ("3.12", "Security Assessment", [
        "Security controls are assessed at least annually to determine they are effective in their application.",
        "Plans of action (POA&M) are developed and maintained to correct deficiencies and reduce or eliminate vulnerabilities, with owners and due dates.",
        "Controls are monitored on an ongoing basis to ensure continued effectiveness between assessments.",
        "System security plans (SSPs) describing system boundaries, environments, control implementation, and connections are maintained and kept current.",
    ], "Executed through the annual self-assessment workbook (BVT-CMP-132), the POA&M template (BVT-CMP-131), and continuous posture snapshots in the OpsPilot portal."),
    ("3.13", "System & Communications Protection", [
        "Communications are monitored, controlled, and protected at system boundaries; managed firewalls enforce deny-by-default at network perimeters.",
        "Networks are segmented to separate management, production, guest, and IoT traffic; publicly accessible components live in separated subnetworks.",
        "Remote activation of collaboration devices (cameras, microphones) is prohibited without user consent indicators.",
        "Cryptography protecting sensitive data uses accepted, modern algorithms; sensitive data in transit is encrypted (TLS 1.2+) and at rest on portable and cloud storage.",
        "Network communication traffic is denied by default and allowed by exception; split tunneling on remote clients is controlled.",
        "Cryptographic keys are established and managed under documented procedures.",
    ], "Delivered through managed firewalls with segmented VLANs, enforced TLS on all BVTech services, DNS filtering, and M365 encryption controls - verified in the network audit checklist."),
    ("3.14", "System & Information Integrity", [
        "System flaws are identified, reported, and corrected within the risk-based timeframes of the Risk Assessment policy.",
        "Malicious-code protection is deployed at endpoints and email gateways, updated automatically, and performs real-time and periodic scanning.",
        "Security alerts and advisories (including CISA KEV) are monitored, assessed for applicability, and actioned.",
        "Inbound and outbound communications and system activity are monitored to detect attacks, indicators of attack, and unauthorized use.",
        "Unauthorized use of systems is identified and alerted through monitoring tooling.",
    ], "Operationalized by managed EDR on every endpoint, mail filtering with attachment detonation, the daily KEV review baked into BVTech's news pipeline, and 24/7 RMM alerting into Pulse."),
]


def _policy(num: str, name: str, statements: list[str], impl: str, idx: int) -> dict:
    fam = num.replace(".", "")
    return {
        "id": f"BVT-CMP-{100 + idx}", "slug": f"NIST_800-171_{fam}_{name.replace(' ', '_').replace('&', 'and')}_Policy",
        "title": f"NIST 800-171 Policy - {num} {name}",
        "category": CAT_CMP[0], "category_label": CAT_CMP[1], "visibility": "internal",
        "kind": "policy",
        "summary": (f"Enforceable policy implementing the NIST SP 800-171 rev. 2 '{name}' "
                    f"family ({num}) across BVTech LLC and, where contracted, managed client "
                    "environments. Statements below are binding on all personnel."),
        "sections": [
            {"h": "Purpose & Authority", "kind": "para", "body":
                f"This policy implements the {name} requirement family of NIST SP 800-171 rev. 2 "
                "as part of BVTech LLC's security program. It is issued under the authority of the "
                "Managing Partner and applies to all employees, contractors, and systems that store, "
                "process, or transmit company or client data."},
            {"h": "Policy Statements", "kind": "bullets", "body": statements},
            {"h": "How BVTech Implements This", "kind": "para", "body": impl},
            {"h": "Roles & Responsibilities", "kind": "bullets", "body": [
                "Managing Partner - owns this policy, approves exceptions in writing, and reviews it annually.",
                "Technicians and administrators - implement and maintain the controls in the systems they manage.",
                "All personnel - comply with the statements above and report suspected violations immediately.",
            ]},
            {"h": "Exceptions & Enforcement", "kind": "para", "body":
                "Exceptions require a written, time-boxed waiver from the Managing Partner recorded in the "
                "risk register. Violations may result in discipline up to termination and, for contractors, "
                "termination of engagement. This policy is reviewed annually and upon material change."},
        ],
    }


def _assessment(num: str, name: str, statements: list[str], idx: int) -> dict:
    fam = num.replace(".", "")
    return {
        "id": f"BVT-CMP-{140 + idx}", "slug": f"NIST_800-171_{fam}_{name.replace(' ', '_').replace('&', 'and')}_Assessment_Checklist",
        "title": f"800-171 Self-Assessment Checklist - {num} {name}",
        "category": CAT_CMP[0], "category_label": CAT_CMP[1], "visibility": "internal",
        "kind": "checklist",
        "summary": (f"Evidence-gathering checklist for the {num} {name} family. Work through each "
                    "item, mark it, and note the evidence location - the completed checklist feeds "
                    "the annual self-assessment score and the POA&M."),
        "sections": [
            {"h": "Assessment Items", "kind": "checks",
             "body": [f"VERIFIED: {s}" for s in statements]},
            {"h": "Evidence & Gaps", "kind": "fills", "body": [
                "Assessed by:", "Assessment date:", "Evidence location:",
                "Gaps identified:", "POA&M items opened:"]},
        ],
    }


# ---- CSF 2.0 ----
CSF_FUNCTIONS = [
    ("GV", "Govern", "The organization's cybersecurity risk management strategy, expectations, and policy are established, communicated, and monitored.", [
        ("Organizational Context", "Mission, stakeholder expectations, legal and contractual requirements (including client MSAs and Texas statutes) are understood and inform security decisions."),
        ("Risk Management Strategy", "Risk appetite is set by the Managing Partner; risks are captured in the risk register with owners and review dates."),
        ("Roles, Responsibilities & Authorities", "Security roles are defined in policy; the Managing Partner is accountable, technicians are responsible for control operation."),
        ("Policy", "The BVT policy suite (this library) is established, approved, communicated, and reviewed annually."),
        ("Oversight", "Posture scores, audit results, and incident metrics are reviewed monthly in the OpsPilot portal and quarterly with clients."),
        ("Cybersecurity Supply Chain Risk Management", "Vendors and subcontractors are risk-assessed before engagement (BVT-CHK vendor review) and bound by written security obligations."),
    ]),
    ("ID", "Identify", "The organization's current cybersecurity risks are understood.", [
        ("Asset Management", "Hardware, software, services, and data are inventoried automatically via RMM and reviewed quarterly; assets are classified by criticality."),
        ("Risk Assessment", "Threats, vulnerabilities, likelihood, and impact are assessed at least annually and on major change; KEV-listed vulnerabilities are treated as actively exploited."),
        ("Improvement", "Lessons from assessments, incidents, and exercises drive documented improvements to controls and this program."),
    ]),
    ("PR", "Protect", "Safeguards to manage the organization's cybersecurity risks are used.", [
        ("Identity Management & Access Control", "Unique identities, enforced MFA, least privilege, and lifecycle-managed accounts per the 3.1/3.5 policies."),
        ("Awareness & Training", "Cyber Academy training with tracked completion and quarterly phishing simulation."),
        ("Data Security", "Data is classified, encrypted in transit and at rest where required, backed up on the 3-2-1 pattern, and destroyed per NIST 800-88."),
        ("Platform Security", "Hardened baselines, timely patching, EDR on every endpoint, and application control on high-risk systems."),
        ("Technology Infrastructure Resilience", "Redundant backups, tested restores, UPS protection, and documented recovery objectives (RTO/RPO) per client."),
    ]),
    ("DE", "Detect", "Possible cybersecurity attacks and compromises are found and analyzed.", [
        ("Continuous Monitoring", "Endpoints, identities, email, and network devices are monitored 24/7 through RMM and M365 alerting into Pulse."),
        ("Adverse Event Analysis", "Alerts are triaged against severity definitions; suspected incidents are escalated to the IRP within defined timelines."),
    ]),
    ("RS", "Respond", "Actions regarding a detected cybersecurity incident are taken.", [
        ("Incident Management", "Incidents are declared, categorized, and managed per BVT-IRP-045 with named incident command."),
        ("Incident Analysis", "Scope, root cause, and impact are established and preserved forensically where legal action or insurance may follow."),
        ("Reporting & Communication", "Clients, carriers, and authorities are notified per contract and Texas Bus. & Com. Code Sec. 521.053 timelines."),
        ("Mitigation", "Containment and eradication actions follow the ransomware/BEC playbooks and are logged in the incident record."),
    ]),
    ("RC", "Recover", "Assets and operations affected by a cybersecurity incident are restored.", [
        ("Incident Recovery Plan Execution", "Restores follow the DR plan with integrity verification before returning systems to service."),
        ("Incident Recovery Communication", "Stakeholders receive honest status through recovery, and a post-incident review closes every declared incident."),
    ]),
]


def build() -> list[dict]:
    docs: list[dict] = []
    for i, (num, name, stmts, impl) in enumerate(FAMILIES, start=1):
        docs.append(_policy(num, name, stmts, impl, i))
        docs.append(_assessment(num, name, stmts, i))
    # SSP, POA&M, self-assessment workbook
    docs.append({
        "id": "BVT-CMP-130", "slug": "System_Security_Plan_Template",
        "title": "System Security Plan (SSP) Template",
        "category": CAT_CMP[0], "category_label": CAT_CMP[1], "visibility": "internal",
        "kind": "policy",
        "summary": "The master description of a covered system: its boundary, environment, "
                   "connections, and how each 800-171 family is implemented. Complete one per "
                   "assessed environment (BVTech internal, and any client contracted for compliance).",
        "sections": [
            {"h": "System Identification", "kind": "fills", "body": [
                "System name:", "System owner:", "Environment (cloud/on-prem/hybrid):",
                "Locations:", "Authorization boundary summary:"]},
            {"h": "System Description", "kind": "para", "body":
                "Describe the mission the system supports, the types of data stored, processed, or "
                "transmitted, user categories and counts, and all interconnections with external "
                "systems including cloud services, vendors, and client networks."},
            {"h": "Control Implementation Summary", "kind": "table",
             "headers": ["Family", "Status", "Implementation reference"],
             "widths": [58, 34, 88],
             "body": [[f"{num} {name}", "Implemented / Partial / Planned",
                       f"BVT-CMP policy + evidence checklist"] for num, name, _, _ in FAMILIES]},
            {"h": "Maintenance", "kind": "para", "body":
                "The SSP is reviewed annually, on major change, and after any reportable incident. "
                "Changes are versioned and approved by the Managing Partner."},
        ],
    })
    docs.append({
        "id": "BVT-CMP-131", "slug": "Plan_of_Action_and_Milestones_Template",
        "title": "Plan of Action & Milestones (POA&M) Template",
        "category": CAT_CMP[0], "category_label": CAT_CMP[1], "visibility": "internal",
        "kind": "checklist",
        "summary": "The living list of security gaps and their path to closure. Every deficiency "
                   "from assessments, scans, or incidents gets a row, an owner, and a date.",
        "sections": [
            {"h": "Open Items", "kind": "table",
             "headers": ["#", "Weakness / gap", "Family", "Owner", "Due", "Status"],
             "widths": [8, 72, 24, 30, 22, 24],
             "body": [[str(i), "", "", "", "", ""] for i in range(1, 13)]},
            {"h": "Completion Log", "kind": "fills", "body": [
                "Item # closed:", "Closure evidence:", "Verified by:", "Date:"]},
        ],
    })
    docs.append({
        "id": "BVT-CMP-132", "slug": "Annual_Self_Assessment_Workbook",
        "title": "NIST 800-171 Annual Self-Assessment Workbook",
        "category": CAT_CMP[0], "category_label": CAT_CMP[1], "visibility": "internal",
        "kind": "checklist",
        "summary": "Annual scoring exercise across all 14 families: work each family checklist "
                   "(BVT-CMP-141..154), record status here, and open POA&M items for every gap.",
        "sections": [
            {"h": "Scoring Summary", "kind": "table",
             "headers": ["Family", "Met", "Partial", "Not met", "POA&M #s"],
             "widths": [70, 22, 24, 26, 38],
             "body": [[f"{num} {name}", "", "", "", ""] for num, name, _, _ in FAMILIES]},
            {"h": "Attestation", "kind": "fills", "body": [
                "Assessment period:", "Lead assessor:", "Overall result:",
                "Managing Partner signature:", "Date:"]},
        ],
    })
    # CSF 2.0 pack
    docs.append({
        "id": "BVT-CSF-160", "slug": "CSF_2.0_Program_Charter",
        "title": "Cybersecurity Program Charter (NIST CSF 2.0)",
        "category": CAT_CSF[0], "category_label": CAT_CSF[1], "visibility": "internal",
        "kind": "policy",
        "summary": "The top-level charter aligning BVTech's security program - and the managed "
                   "service it delivers to clients - to the six functions of NIST CSF 2.0.",
        "sections": [
            {"h": "Commitment", "kind": "para", "body":
                "BVTech LLC operates a cybersecurity program structured on the NIST Cybersecurity "
                "Framework 2.0. The Managing Partner is accountable for the program; every function "
                "below has documented policies, operating procedures, and evidence in this library."},
            {"h": "The Six Functions", "kind": "bullets", "body": [
                f"{code} {name} - {desc}" for code, name, desc, _ in CSF_FUNCTIONS]},
            {"h": "Program Governance", "kind": "para", "body":
                "Function profiles (BVT-CSF-161..166) define category-level implementation. The "
                "current-vs-target profile worksheet (BVT-CSF-167) is refreshed annually and drives "
                "the improvement roadmap. Client-facing services map to these same functions "
                "(BVT-CSF-168), so every client deliverable traces to a framework outcome."},
        ],
    })
    for j, (code, name, desc, cats) in enumerate(CSF_FUNCTIONS, start=1):
        docs.append({
            "id": f"BVT-CSF-{160 + j}", "slug": f"CSF_2.0_Function_Profile_{code}_{name}",
            "title": f"CSF 2.0 Function Profile - {code} {name}",
            "category": CAT_CSF[0], "category_label": CAT_CSF[1], "visibility": "internal",
            "kind": "policy",
            "summary": f"Category-level implementation profile for the {name} function: {desc}",
            "sections": [
                {"h": "Function Outcome", "kind": "para", "body": desc},
                {"h": "Category Implementation", "kind": "bullets",
                 "body": [f"{cname}: {impl}" for cname, impl in cats]},
                {"h": "Evidence Sources", "kind": "para", "body":
                    "Evidence for this function lives in the OpsPilot portal (posture history, "
                    "audit log, training records, incident records) and the referenced BVT policy "
                    "and checklist documents. Review annually with the profile worksheet."},
            ],
        })
    docs.append({
        "id": "BVT-CSF-167", "slug": "CSF_2.0_Current_vs_Target_Profile_Worksheet",
        "title": "CSF 2.0 Current-vs-Target Profile Worksheet",
        "category": CAT_CSF[0], "category_label": CAT_CSF[1], "visibility": "internal",
        "kind": "checklist",
        "summary": "Annual maturity snapshot: rate each function 1-4 (Partial, Risk-Informed, "
                   "Repeatable, Adaptive), set the target, and plan the delta.",
        "sections": [
            {"h": "Profile", "kind": "table",
             "headers": ["Function", "Current tier", "Target tier", "Priority gaps"],
             "widths": [46, 30, 30, 74],
             "body": [[f"{c} {n}", "", "", ""] for c, n, _, _ in CSF_FUNCTIONS]},
            {"h": "Roadmap", "kind": "fills", "body": [
                "Top improvement 1:", "Top improvement 2:", "Top improvement 3:",
                "Review date:", "Approved by:"]},
        ],
    })
    docs.append({
        "id": "BVT-CSF-168", "slug": "CSF_2.0_Services_Mapping",
        "title": "BVTech Services-to-CSF Mapping",
        "category": CAT_CSF[0], "category_label": CAT_CSF[1], "visibility": "client",
        "kind": "policy",
        "summary": "Client-shareable: how each BVTech managed service delivers NIST CSF 2.0 "
                   "outcomes - the one-page answer to 'are we covered?'",
        "sections": [
            {"h": "Service Coverage", "kind": "table",
             "headers": ["BVTech service", "CSF functions", "What you get"],
             "widths": [46, 34, 100],
             "body": [
                 ["Managed IT & RMM", "ID, PR, DE", "Inventory, patching, hardening baselines, and 24/7 monitoring on every endpoint."],
                 ["Managed security (EDR + email)", "PR, DE, RS", "Endpoint detection and response, mail filtering, and alert triage into incident response."],
                 ["Backup & disaster recovery", "PR, RC", "3-2-1 backups with tested restores and documented recovery objectives."],
                 ["Microsoft 365 management", "GV, PR", "Conditional access, MFA enforcement, audit logging, and secure-score improvement."],
                 ["Security awareness (Cyber Academy)", "PR", "Monthly training, phishing simulation, and completion compliance reporting."],
                 ["vCISO / compliance advisory", "GV, ID", "Policy suite, risk register, assessments, and this framework program."],
             ]},
        ],
    })
    return docs
