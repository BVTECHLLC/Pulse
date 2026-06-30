#!/usr/bin/env python3
"""
BVTech DialPad Deep Integration Module v2.0
=============================================
Full DialPad API + HubSpot CRM automation for MSP Marketing Command Center.

NEW in v2.0:
  - Post-Call Workflow Engine (auto-create HubSpot deals, notes, tasks)
  - AI Call Coaching Scores (talk ratio, keyword detection, objection handling)
  - Sentiment Trend Tracking
  - Call Disposition → CRM Pipeline Automation
  - MSP Keyword Detection (compliance, cybersecurity, cloud, backup)
  - Bulk transcript analysis for coaching insights
  - HubSpot Pipeline Dashboard
"""

import json, os, re, sys, time
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

MSP_KEYWORDS = {
    "pain_points": {
        "cybersecurity": ["hack","breach","ransomware","phishing","security","virus","malware","cyber","threat","vulnerability","firewall","antivirus","endpoint"],
        "compliance": ["hipaa","pci","sox","compliance","regulation","audit","nist","cmmc","data protection","privacy","gdpr"],
        "downtime": ["outage","downtime","crash","slow","broken","not working","down","offline","server","backup","disaster recovery"],
        "cloud": ["cloud","microsoft 365","office 365","m365","azure","aws","migration","google workspace","saas"],
        "it_support": ["help desk","it support","it guy","tech support","computer","network","printer","wifi","vpn","remote"],
        "growth": ["growing","expansion","new office","hiring","scaling","upgrade","modernize"],
    },
    "buying_signals": ["how much","pricing","cost","budget","quote","proposal","when can you start","next steps","send me","contract","interested","tell me more","sounds good","let's do it","schedule","meeting","demo","free assessment"],
    "objections": ["not interested","too expensive","already have","no budget","happy with current","too busy","call back later","not now","no money","can't afford","don't need","send email"],
    "competitors": ["rackspace","datto","connectwise","kaseya","ninja","it solutions","tech support","geek squad","local it"],
}

DISPOSITION_PIPELINE = {
    "qualified_lead":  {"hs_stage":"appointmentscheduled","deal_priority":"HIGH","followup_days":1},
    "interested":      {"hs_stage":"qualifiedtobuy","deal_priority":"MEDIUM","followup_days":3},
    "callback":        {"hs_stage":"presentationscheduled","deal_priority":"MEDIUM","followup_days":2},
    "send_info":       {"hs_stage":"decisionmakerboughtin","deal_priority":"LOW","followup_days":5},
    "not_interested":  {"hs_stage":None,"deal_priority":None,"followup_days":30},
    "no_answer":       {"hs_stage":None,"deal_priority":None,"followup_days":3},
    "voicemail":       {"hs_stage":None,"deal_priority":None,"followup_days":2},
    "wrong_number":    {"hs_stage":None,"deal_priority":None,"followup_days":None},
    "do_not_call":     {"hs_stage":None,"deal_priority":None,"followup_days":None},
    "gatekeeper":      {"hs_stage":None,"deal_priority":"LOW","followup_days":5},
}


class DialPadClient:
    BASE = "https://dialpad.com/api/v2"

    def __init__(self, api_key=None, user_id=None):
        if not api_key:
            cfg = self._load_config()
            api_key = cfg.get("dialpad_key", "")
            user_id = cfg.get("dialpad_user_id", "")
            self.hubspot_token = cfg.get("hubspot_token", "")
        else:
            self.hubspot_token = ""
        self.api_key = api_key
        self.user_id = user_id
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def _load_config(self):
        # Try: 1) next to EXE (frozen), 2) next to script, 3) CWD
        candidates = []
        if getattr(sys, 'frozen', False):
            candidates.append(Path(os.path.dirname(sys.executable)) / "bvtech_config.json")
        candidates.append(Path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bvtech_config.json")))
        candidates.append(Path("bvtech_config.json"))
        for p in candidates:
            if p.exists():
                try:
                    with open(p) as f: return json.load(f)
                except: pass
        return {}

    def _get(self, path, params=None, timeout=30):
        try:
            r = requests.get(f"{self.BASE}{path}", headers=self.headers, params=params, timeout=timeout)
            return (r.json(), None) if r.status_code == 200 else (None, f"HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e: return None, str(e)

    def _post(self, path, data=None, timeout=30):
        try:
            r = requests.post(f"{self.BASE}{path}", headers=self.headers, json=data, timeout=timeout)
            return (r.json() if r.text else {}, None) if r.status_code in (200,201,202) else (None, f"HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e: return None, str(e)

    def _put(self, path, data=None, timeout=30):
        try:
            r = requests.put(f"{self.BASE}{path}", headers=self.headers, json=data, timeout=timeout)
            return (r.json() if r.text else {}, None) if r.status_code == 200 else (None, f"HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e: return None, str(e)

    def _delete(self, path):
        try:
            r = requests.delete(f"{self.BASE}{path}", headers=self.headers, timeout=30)
            return (True, None) if r.status_code in (200,204) else (None, f"HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e: return None, str(e)

    # --- HubSpot helpers ---
    def _hs_headers(self):
        return {"Authorization": f"Bearer {self.hubspot_token}", "Content-Type": "application/json"}
    def _hs_post(self, path, data):
        try:
            r = requests.post(f"https://api.hubapi.com{path}", headers=self._hs_headers(), json=data, timeout=15)
            return (r.json(), None) if r.status_code in (200,201) else (None, f"HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e: return None, str(e)
    def _hs_get(self, path, params=None):
        try:
            r = requests.get(f"https://api.hubapi.com{path}", headers=self._hs_headers(), params=params, timeout=15)
            return (r.json(), None) if r.status_code == 200 else (None, f"HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e: return None, str(e)
    def _hs_patch(self, path, data):
        try:
            r = requests.patch(f"https://api.hubapi.com{path}", headers=self._hs_headers(), json=data, timeout=15)
            return (r.json(), None) if r.status_code == 200 else (None, f"HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e: return None, str(e)

    # --- Calls ---
    def initiate_call(self, phone_number):
        return self._post(f"/users/{self.user_id}/initiate_call", {"phone_number": phone_number})
    def get_call_info(self, call_id):
        return self._get(f"/call/{call_id}")
    def get_call_history(self, days=7, limit=50):
        """Get call history. DialPad v2 uses /stats/calls or /call endpoint."""
        # Try the stats endpoint first (more reliable)
        params = {"limit": min(limit, 50)}  # DialPad caps at 50 per page
        # Try /call with user_id filter
        result, err = self._get(f"/users/{self.user_id}/calls", params=params, timeout=45)
        if result:
            # Normalize response format
            if isinstance(result, list):
                return {"items": result}, None
            return result, None
        # Fallback to /call endpoint
        result2, err2 = self._get(f"/call", params=params, timeout=45)
        if result2:
            if isinstance(result2, list):
                return {"items": result2}, None
            return result2, None
        return None, err or err2 or "Could not fetch call history"
    def hangup_call(self, call_id):
        return self._put(f"/call/{call_id}/hangup")
    def transfer_call(self, call_id, to_number):
        return self._post(f"/call/{call_id}/transfer", {"phone_number": to_number})
    def set_call_label(self, call_id, labels):
        return self._put(f"/call/{call_id}/labels", {"labels": labels})
    def get_call_labels(self):
        return self._get("/calllabels")

    # --- AI Transcripts & Recaps ---
    def get_transcript(self, call_id):
        return self._get(f"/transcripts/{call_id}")
    def get_ai_recap(self, call_id):
        return self._get(f"/call/{call_id}/ai_recap")
    def get_call_review_link(self, call_id):
        return self._post("/callreviewsharelink", {"call_id": call_id, "access_level": "company"})

    # --- SMS ---
    def send_sms(self, to_number, text):
        return self._post("/sms", {"to_numbers": [to_number], "text": text,
            "user_id": int(self.user_id) if self.user_id.isdigit() else self.user_id})
    def get_sms_opt_outs(self):
        return self._get("/company/sms_opt_out")

    # --- Contacts ---
    def list_contacts(self, limit=100):
        return self._get("/contacts", params={"limit": limit})
    def create_contact(self, first_name, last_name, phone, email="", company=""):
        data = {"first_name": first_name, "last_name": last_name, "phones": [phone] if phone else []}
        if email: data["emails"] = [email]
        if company: data["company_name"] = company
        return self._post("/contacts", data)
    def update_contact(self, contact_id, **kwargs):
        return self._post(f"/contacts/{contact_id}", kwargs)
    def delete_contact(self, contact_id):
        return self._delete(f"/contacts/{contact_id}")

    # --- Blocked / DNC ---
    def block_number(self, phone_number):
        return self._post("/blockednumbers/add", {"phone_number": phone_number})
    def unblock_number(self, phone_number):
        return self._post("/blockednumbers/remove", {"phone_number": phone_number})
    def list_blocked(self):
        return self._get("/blockednumbers")

    # --- Company & Users ---
    def get_company_info(self):
        return self._get("/company")
    def list_users(self):
        return self._get("/users")
    def get_user(self, user_id=None):
        return self._get(f"/users/{user_id or self.user_id}")

    # --- Call Centers ---
    def list_call_centers(self):
        return self._get("/callcenters")
    def get_call_center(self, cc_id):
        return self._get(f"/callcenters/{cc_id}")
    def get_call_center_status(self, cc_id):
        return self._get(f"/callcenters/{cc_id}/status")

    # --- Recordings ---
    def get_recording_url(self, call_id):
        call_info, err = self.get_call_info(call_id)
        if call_info and "recording_url" in call_info:
            return call_info["recording_url"], None
        return None, err or "No recording found"

    # ==========================================================
    # ENHANCED ANALYTICS
    # ==========================================================
    def get_call_analytics(self, days=30):
        calls_data, err = self.get_call_history(days=days, limit=500)
        if not calls_data: return None, err
        calls = calls_data.get("items", [])
        if not calls: return {"total_calls": 0}, None

        total = len(calls)
        inbound = sum(1 for c in calls if c.get("direction") == "inbound")
        outbound = total - inbound
        recorded = sum(1 for c in calls if c.get("was_recorded"))
        durations = [c.get("duration", 0) for c in calls if c.get("duration")]
        avg_duration = sum(durations) / len(durations) if durations else 0

        hourly = {}
        for c in calls:
            ds = c.get("date_started", "")
            if ds:
                try:
                    h = datetime.fromisoformat(ds.replace("Z", "+00:00")).hour
                    hourly[h] = hourly.get(h, 0) + 1
                except: pass

        connected = sum(1 for c in calls if (c.get("duration") or 0) > 30000)
        connect_rate = round(connected / max(outbound, 1) * 100, 1)

        out_durs = [c.get("duration",0) for c in calls if c.get("direction") != "inbound" and c.get("duration")]
        in_durs = [c.get("duration",0) for c in calls if c.get("direction") == "inbound" and c.get("duration")]

        return {
            "total_calls": total, "inbound": inbound, "outbound": outbound, "recorded": recorded,
            "avg_duration_sec": round(avg_duration / 1000), "total_duration_min": round(sum(durations) / 60000),
            "connect_rate": connect_rate, "connected_calls": connected,
            "avg_outbound_sec": round(sum(out_durs) / max(len(out_durs),1) / 1000),
            "avg_inbound_sec": round(sum(in_durs) / max(len(in_durs),1) / 1000),
            "hourly_distribution": hourly,
            "best_hour": max(hourly, key=hourly.get) if hourly else None,
            "calls_today": sum(1 for c in calls if _is_today(c.get("date_started", ""))),
        }, None

    def get_recent_transcripts(self, limit=10):
        calls_data, err = self.get_call_history(days=7, limit=limit)
        if not calls_data: return [], err
        transcripts = []
        for call in calls_data.get("items", [])[:limit]:
            call_id = call.get("call_id")
            if not call_id: continue
            transcript, _ = self.get_transcript(call_id)
            if transcript:
                transcripts.append({"call_id": call_id, "direction": call.get("direction",""),
                    "contact": call.get("contact",{}).get("name","Unknown"),
                    "contact_phone": call.get("contact",{}).get("phone",""),
                    "duration": call.get("duration",0), "date": call.get("date_started",""),
                    "transcript": transcript})
            time.sleep(0.1)
        return transcripts, None

    # ==========================================================
    # AI CALL COACHING ENGINE (v2.0)
    # ==========================================================
    def analyze_call_for_coaching(self, call_id):
        call_info, err = self.get_call_info(call_id)
        if not call_info: return None, err or "Could not load call info"
        transcript_data, _ = self.get_transcript(call_id)
        recap_data, _ = self.get_ai_recap(call_id)

        coaching = {
            "call_id": call_id,
            "duration_sec": round((call_info.get("duration") or 0) / 1000),
            "direction": call_info.get("direction", "outbound"),
            "contact_name": call_info.get("contact",{}).get("name","Unknown"),
            "contact_phone": call_info.get("contact",{}).get("phone",""),
            "was_recorded": call_info.get("was_recorded", False),
            "date": call_info.get("date_started", ""),
        }

        if transcript_data:
            lines = transcript_data.get("lines", [])
            full_text = " ".join([l.get("text","") for l in lines]).lower()
            agent_words = prospect_words = 0
            for line in lines:
                words = len(line.get("text","").split())
                speaker = (line.get("speaker") or "").lower()
                if any(x in speaker for x in ("agent","jordan","bvtech")):
                    agent_words += words
                else:
                    prospect_words += words
            total_words = agent_words + prospect_words
            talk_ratio = round(agent_words / max(total_words, 1) * 100)

            pain_points_found = {}
            for cat, kws in MSP_KEYWORDS["pain_points"].items():
                hits = [kw for kw in kws if kw in full_text]
                if hits: pain_points_found[cat] = hits

            buying_signals = [s for s in MSP_KEYWORDS["buying_signals"] if s in full_text]
            objections = [o for o in MSP_KEYWORDS["objections"] if o in full_text]
            competitors = [c for c in MSP_KEYWORDS["competitors"] if c in full_text]

            score = 50
            if 35 <= talk_ratio <= 55: score += 15
            elif 25 <= talk_ratio <= 65: score += 8
            else: score -= 10

            dur = coaching["duration_sec"]
            if dur >= 300: score += 15
            elif dur >= 120: score += 10
            elif dur >= 60: score += 5
            elif dur < 30: score -= 10

            score += min(len(pain_points_found) * 5, 15)
            score += min(len(buying_signals) * 8, 20)
            if objections: score += 3

            tips = []
            if talk_ratio > 65: tips.append("You talked too much — aim for 40-55% talk ratio.")
            elif talk_ratio < 30: tips.append("You didn't talk enough — present value clearly.")
            if not pain_points_found: tips.append("No pain points found. Ask: 'What's your biggest IT challenge?'")
            if not buying_signals and dur > 120: tips.append("No buying signals. Try: 'Would a free assessment help?'")
            if dur < 60 and coaching["direction"] == "outbound": tips.append("Too short — work on your opening hook.")
            if competitors: tips.append(f"Competitor mentioned: {', '.join(competitors)}. Prepare differentiators!")
            if buying_signals: tips.append("Buying signals detected! Schedule the assessment ASAP.")
            if pain_points_found.get("cybersecurity"): tips.append("Cyber pain point — lead with your security stack.")
            if pain_points_found.get("compliance"): tips.append("Compliance need — emphasize HIPAA/PCI/SOX expertise.")

            coaching.update({
                "talk_ratio_agent": talk_ratio, "talk_ratio_prospect": 100-talk_ratio,
                "total_words": total_words, "agent_words": agent_words, "prospect_words": prospect_words,
                "pain_points": pain_points_found, "buying_signals": buying_signals,
                "objections": objections, "competitors_mentioned": competitors,
                "coaching_score": min(100, max(0, score)), "transcript_available": True, "tips": tips,
            })
        else:
            coaching.update({"talk_ratio_agent":None, "coaching_score":None, "pain_points":{},
                "buying_signals":[], "objections":[], "competitors_mentioned":[],
                "tips":["No transcript available. Enable recording for coaching."], "transcript_available":False})

        if recap_data and not recap_data.get("error"):
            coaching["ai_summary"] = recap_data.get("summary","")
            coaching["action_items"] = recap_data.get("action_items",[])
            coaching["key_moments"] = recap_data.get("moments",[])
            coaching["sentiment"] = recap_data.get("sentiment","")
        else:
            coaching.update({"ai_summary":"","action_items":[],"key_moments":[],"sentiment":""})

        return coaching, None

    def get_coaching_summary(self, days=7, limit=20):
        calls_data, err = self.get_call_history(days=days, limit=limit)
        if not calls_data: return None, err
        calls = calls_data.get("items", [])
        if not calls: return {"total_analyzed": 0}, None

        all_coaching = []
        for call in calls:
            cid = call.get("call_id")
            if not cid or (call.get("duration") or 0) < 30000: continue
            coaching, _ = self.analyze_call_for_coaching(cid)
            if coaching and coaching.get("coaching_score") is not None:
                all_coaching.append(coaching)
            time.sleep(0.15)
        if not all_coaching: return {"total_analyzed": 0}, None

        scores = [c["coaching_score"] for c in all_coaching if c.get("coaching_score") is not None]
        ratios = [c["talk_ratio_agent"] for c in all_coaching if c.get("talk_ratio_agent") is not None]
        all_pain_points = {}
        all_buying = all_objections = 0
        for c in all_coaching:
            for cat in c.get("pain_points",{}): all_pain_points[cat] = all_pain_points.get(cat,0)+1
            all_buying += len(c.get("buying_signals",[]))
            all_objections += len(c.get("objections",[]))

        return {
            "total_analyzed": len(all_coaching),
            "avg_coaching_score": round(sum(scores)/len(scores)) if scores else 0,
            "avg_talk_ratio": round(sum(ratios)/len(ratios)) if ratios else 0,
            "top_pain_points": sorted(all_pain_points.items(), key=lambda x:-x[1]),
            "total_buying_signals": all_buying, "total_objections": all_objections,
            "best_call": max(all_coaching, key=lambda c: c.get("coaching_score",0)),
            "calls_needing_coaching": [c for c in all_coaching if (c.get("coaching_score") or 0) < 50],
        }, None

    # ==========================================================
    # POST-CALL WORKFLOW ENGINE (v2.0)
    # ==========================================================
    def post_call_workflow(self, call_id, disposition, notes="", prospect_phone=""):
        results = {"call_logged":False,"contact_updated":False,"deal_created":False,
                   "task_created":False,"call_tagged":False,"blocked":False,"errors":[]}
        if not self.hubspot_token:
            results["errors"].append("No HubSpot token"); return results
        pipeline = DISPOSITION_PIPELINE.get(disposition, {})
        if not pipeline:
            results["errors"].append(f"Unknown disposition: {disposition}"); return results

        call_info, _ = self.get_call_info(call_id)
        duration = round((call_info.get("duration") or 0)/1000) if call_info else 0
        contact_phone = prospect_phone or (call_info or {}).get("contact",{}).get("phone","")

        # Find HubSpot contact
        hs_contact_id = None
        if contact_phone:
            sr, _ = self._hs_post("/crm/v3/objects/contacts/search", {
                "filterGroups":[{"filters":[{"propertyName":"phone","operator":"CONTAINS_TOKEN","value":contact_phone[-10:]}]}]
            })
            if sr and sr.get("total",0) > 0: hs_contact_id = sr["results"][0]["id"]

        # Log call note
        call_note = f"Call via DialPad | Duration: {duration}s | Disposition: {disposition}"
        if notes: call_note += f"\nNotes: {notes}"
        coaching, _ = self.analyze_call_for_coaching(call_id)
        if coaching and coaching.get("coaching_score") is not None:
            call_note += f"\n\nAI Coaching Score: {coaching['coaching_score']}/100"
            if coaching.get("pain_points"): call_note += f"\nPain Points: {', '.join(coaching['pain_points'].keys())}"
            if coaching.get("buying_signals"): call_note += f"\nBuying Signals: {', '.join(coaching['buying_signals'][:3])}"
            if coaching.get("ai_summary"): call_note += f"\nAI Summary: {coaching['ai_summary']}"

        if hs_contact_id:
            nr, ne = self._hs_post("/crm/v3/objects/notes", {"properties":{"hs_note_body":call_note,"hs_timestamp":datetime.utcnow().isoformat()+"Z"},
                "associations":[{"to":{"id":hs_contact_id},"types":[{"associationCategory":"HUBSPOT_DEFINED","associationTypeId":202}]}]})
            results["call_logged"] = nr is not None
            if ne: results["errors"].append(f"Note: {ne}")

        # Update contact
        if hs_contact_id and pipeline.get("deal_priority"):
            props = {"hs_lead_status": disposition.upper().replace("_"," ")}
            if disposition in ("qualified_lead","interested"): props["lifecyclestage"] = "salesqualifiedlead"
            ur, ue = self._hs_patch(f"/crm/v3/objects/contacts/{hs_contact_id}", {"properties":props})
            results["contact_updated"] = ur is not None
            if ue: results["errors"].append(f"Update: {ue}")

        # Create deal
        if pipeline.get("hs_stage") and hs_contact_id:
            cname = (call_info or {}).get("contact",{}).get("name","Unknown")
            dr, de = self._hs_post("/crm/v3/objects/deals", {"properties":{
                "dealname":f"MSP Services — {cname}","dealstage":pipeline["hs_stage"],
                "pipeline":"default","amount":"1500","description":call_note,"hs_priority":pipeline["deal_priority"]},
                "associations":[{"to":{"id":hs_contact_id},"types":[{"associationCategory":"HUBSPOT_DEFINED","associationTypeId":3}]}]})
            results["deal_created"] = dr is not None
            if dr: results["deal_id"] = dr.get("id")
            if de: results["errors"].append(f"Deal: {de}")

        # Create follow-up task
        fd = pipeline.get("followup_days")
        if fd and hs_contact_id:
            due = (datetime.utcnow()+timedelta(days=fd)).strftime("%Y-%m-%d")
            tbody = f"Follow-up from {disposition.replace('_',' ')} call"
            if notes: tbody += f": {notes}"
            tr, te = self._hs_post("/crm/v3/objects/tasks", {"properties":{
                "hs_task_body":tbody,"hs_task_subject":f"Follow-up: {contact_phone}",
                "hs_task_status":"NOT_STARTED","hs_task_priority":pipeline.get("deal_priority","MEDIUM"),
                "hs_timestamp":due+"T09:00:00Z"},
                "associations":[{"to":{"id":hs_contact_id},"types":[{"associationCategory":"HUBSPOT_DEFINED","associationTypeId":204}]}]})
            results["task_created"] = tr is not None
            if te: results["errors"].append(f"Task: {te}")

        # Tag call in DialPad
        lr, _ = self.set_call_label(call_id, [disposition, "msp_campaign"])
        results["call_tagged"] = lr is not None

        # Block if DNC
        if disposition == "do_not_call" and contact_phone:
            br, _ = self.block_number(contact_phone)
            results["blocked"] = br is not None

        return results

    # ==========================================================
    # HUBSPOT PIPELINE DASHBOARD (v2.0)
    # ==========================================================
    def get_hubspot_pipeline(self):
        if not self.hubspot_token: return None, "No HubSpot token"
        deals, err = self._hs_get("/crm/v3/objects/deals", params={
            "limit":100,"properties":"dealname,dealstage,amount,hs_priority,createdate,closedate,pipeline"})
        if not deals: return None, err

        stages = {
            "appointmentscheduled": {"name":"Assessment Booked","deals":[],"value":0},
            "qualifiedtobuy": {"name":"Interested","deals":[],"value":0},
            "presentationscheduled": {"name":"Proposal Sent","deals":[],"value":0},
            "decisionmakerboughtin": {"name":"Decision Maker","deals":[],"value":0},
            "contractsent": {"name":"Contract Sent","deals":[],"value":0},
            "closedwon": {"name":"Closed Won","deals":[],"value":0},
            "closedlost": {"name":"Closed Lost","deals":[],"value":0},
        }
        for deal in deals.get("results",[]):
            props = deal.get("properties",{})
            stage = props.get("dealstage","")
            if stage in stages:
                amt = float(props.get("amount") or 0)
                stages[stage]["deals"].append({"id":deal.get("id"),"name":props.get("dealname",""),
                    "amount":amt,"priority":props.get("hs_priority",""),"created":props.get("createdate","")})
                stages[stage]["value"] += amt

        return {
            "stages": stages,
            "total_pipeline_value": sum(s["value"] for k,s in stages.items() if k != "closedlost"),
            "total_won": stages["closedwon"]["value"],
            "total_deals": sum(len(s["deals"]) for s in stages.values()),
        }, None

    def get_hubspot_contacts_summary(self):
        if not self.hubspot_token: return None, "No HubSpot token"
        contacts, err = self._hs_get("/crm/v3/objects/contacts", params={
            "limit":100,"properties":"firstname,lastname,company,phone,email,lifecyclestage,hs_lead_status,city,industry"})
        if not contacts: return None, err
        results = contacts.get("results",[])
        by_stage = {}; by_status = {}; by_industry = {}
        for c in results:
            props = c.get("properties",{})
            s = props.get("lifecyclestage") or "unknown"; by_stage[s] = by_stage.get(s,0)+1
            st = props.get("hs_lead_status") or "unknown"; by_status[st] = by_status.get(st,0)+1
            ind = props.get("industry") or "unknown"; by_industry[ind] = by_industry.get(ind,0)+1
        return {
            "total_contacts": len(results), "by_lifecycle_stage": by_stage,
            "by_lead_status": by_status, "by_industry": sorted(by_industry.items(), key=lambda x: -(x[1] or 0)),
            "recent": [{"id":c.get("id"),
                "name":f"{(c['properties'].get('firstname') or '')} {(c['properties'].get('lastname') or '')}".strip() or "Unknown",
                "company":c["properties"].get("company") or "","phone":c["properties"].get("phone") or "",
                "email":c["properties"].get("email") or "","stage":c["properties"].get("lifecyclestage") or "",
                "status":c["properties"].get("hs_lead_status") or ""} for c in results[:20]],
        }, None

    # ==========================================================
    # PROSPECT SYNC
    # ==========================================================
    def sync_prospects_to_dialpad(self, prospects):
        created = skipped = failed = 0
        for p in prospects:
            phone = p.get("phone","").strip()
            if not phone: skipped += 1; continue
            result, err = self.create_contact(p.get("first_name",""), p.get("last_name",""),
                phone, p.get("email",""), p.get("company",""))
            if result: created += 1
            elif "already exists" in str(err).lower() or "409" in str(err): skipped += 1
            else: failed += 1
            time.sleep(0.1)
        return {"created": created, "skipped": skipped, "failed": failed}


def _is_today(date_str):
    if not date_str: return False
    try:
        return datetime.fromisoformat(date_str.replace("Z","+00:00")).date() == datetime.utcnow().date()
    except: return False


if __name__ == "__main__":
    dp = DialPadClient()
    print("BVTech DialPad Integration v2.0 Test")
    print("=" * 50)
    info, err = dp.get_company_info()
    if info: print(f"Company: {info.get('name','N/A')}")
    else: print(f"Error: {err}")
    analytics, err = dp.get_call_analytics(days=30)
    if analytics:
        print(f"Total calls: {analytics['total_calls']}")
        print(f"Connect rate: {analytics.get('connect_rate',0)}%")
    print("Done!")
