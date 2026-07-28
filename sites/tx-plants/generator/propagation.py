#!/usr/bin/env python3
"""Texas Roots — propagation & cultivation knowledge engine (v5).

Turns the structured facts already in plants_data (family, tags, category,
sun/water/soil, days-to-harvest, etc.) into genuinely useful, species-aware
how-to prose: how to propagate, how to cultivate through the Texas year, how
to harvest, how to save seed, and how to troubleshoot — written in Jordan's
voice. Output is a list of (heading, [paragraphs...]) sections that the plant
builder renders as real article copy, plus a structured propagation method
list for HowTo schema.

The point is depth that is *true to the plant*, not boilerplate. We branch on
botanical family and on the tags the database already carries, so a fig gets
hardwood-cutting copy, a tomato gets transplant copy, garlic gets clove copy,
and a fence-line wild edible gets a forage-and-don't-plant-it note.
"""

# ---- family-level propagation knowledge -------------------------------------
# Each entry: how this family is usually started, plus the honest detail.
FAMILY_PROP = {
    "Lamiaceae": {  # mints, sages, basils, oregano
        "lead": "softwood cuttings",
        "text": ("Almost everything in the mint family roots from cuttings so "
                 "readily it feels like cheating. Snip a 4–5 inch non-flowering "
                 "tip, strip the bottom leaves, and either set it in a glass of "
                 "water on the windowsill or push it straight into damp "
                 "potting mix. You'll usually see roots in 1–2 weeks. Seed works "
                 "too, but cuttings give you an exact copy of the parent — which "
                 "matters when one plant tastes better than its neighbor."),
    },
    "Asteraceae": {  # sunflowers, lettuce, coneflower, marigold
        "lead": "seed (and division for the perennials)",
        "text": ("The daisy family is a seed family — those flower heads are "
                 "seed factories, and most members come up fast and willing from "
                 "direct sowing. The perennial members (coneflower, black-eyed "
                 "Susan, the native sunflowers) also clump up over a few years and "
                 "can be lifted and split in fall or early spring to make free "
                 "plants and keep the center from dying out."),
    },
    "Fabaceae": {  # beans, peas, clovers, vetch
        "lead": "direct-sown seed",
        "text": ("Legumes resent transplanting — that taproot wants to go "
                 "straight down — so sow them right where they'll grow once the "
                 "soil has warmed. Soak hard-coated seed overnight to speed "
                 "germination. As a bonus, this whole family pulls nitrogen out "
                 "of the air and banks it in the soil, so wherever you grow them "
                 "you're feeding next season's crop."),
    },
    "Brassicaceae": {  # cabbage, kale, mustard, radish, turnip
        "lead": "seed, started in trays or sown direct",
        "text": ("The cabbage family is a cool-season seed crop. Start the heading "
                 "types (cabbage, broccoli, cauliflower) in trays 5–6 weeks before "
                 "you want them in the ground; sow the fast roots and greens "
                 "(radish, turnip, mustard, arugula) straight into the bed. They "
                 "all cross with each other readily, so if you're saving seed, "
                 "only let one variety of a given species flower at a time."),
    },
    "Poaceae": {  # grains, corn, sorghum, grasses
        "lead": "direct-sown seed",
        "text": ("Grasses and grains are sown where they grow — they germinate "
                 "fast in warm soil and don't like having their roots disturbed. "
                 "The ornamental and native bunchgrasses can also be divided in "
                 "spring. For the grain types, plant in a block rather than a "
                 "single row so wind-pollination fills out the heads."),
    },
    "Solanaceae": {  # tomato, pepper, eggplant, potato, ground cherry
        "lead": "seed started indoors (potatoes from tubers)",
        "text": ("Tomatoes, peppers, eggplant and their cousins are warm-season "
                 "crops started inside 6–8 weeks before your last frost, then "
                 "transplanted out once nights stay above 50°F. Tomatoes are the "
                 "exception to most rules — you can bury the stem deep or root a "
                 "side shoot (a 'sucker') in water to clone a plant mid-season. "
                 "Potatoes skip seed entirely and grow from seed potatoes — chunks "
                 "of tuber with an eye or two."),
    },
    "Rosaceae": {  # apples, peaches, plums, blackberry, strawberry
        "lead": "cuttings, division, or grafted stock",
        "text": ("The rose family is where you stop relying on seed. Tree fruit "
                 "(peach, plum, pear, apple) is grafted onto rootstock because "
                 "seedlings won't come true to the parent. The brambles "
                 "(blackberry, raspberry, dewberry) spread by tip-layering and "
                 "root suckers — bend a cane to the ground, pin it, and it roots. "
                 "Strawberries throw runners that root themselves into new plants "
                 "all season."),
    },
    "Cucurbitaceae": {  # squash, melon, cucumber, gourds
        "lead": "direct-sown seed",
        "text": ("The squash and melon family wants warm soil and hates cold, wet "
                 "feet, so wait until the ground is reliably warm and sow the big "
                 "seeds an inch deep right in the garden. They sprawl, so give "
                 "them room or a trellis. They're insect-pollinated and cross "
                 "wildly within a species — keep that in mind if you ever want to "
                 "save seed that comes true."),
    },
    "Amaranthaceae": {  # amaranth, spinach, chard, beet, lambsquarters, quinoa
        "lead": "direct-sown seed",
        "text": ("This family — the amaranths, beets, chard, spinach and their "
                 "wild cousins — is grown from seed sown right where it'll stand. "
                 "The grain amaranths and quinoa throw enormous seed heads you can "
                 "harvest by the handful and re-sow for free. Beets and chard seed "
                 "are actually little clusters, so each 'seed' can send up several "
                 "seedlings you'll need to thin."),
    },
    "Apiaceae": {  # carrot, parsley, dill, fennel, cilantro, parsnip
        "lead": "direct-sown seed",
        "text": ("The carrot family carries a long taproot and does not want to be "
                 "moved, so sow it in place. The seed is slow and needs steady "
                 "moisture to germinate — never let the top of the soil dry out "
                 "during those first two weeks. Let one plant bolt and flower and "
                 "it'll hand you next year's seed in those lacy umbels, plus feed "
                 "every beneficial insect in the yard."),
    },
    "Malvaceae": {  # okra, hibiscus, mallow, Turk's cap
        "lead": "direct-sown seed",
        "text": ("The mallow family loves heat. Sow the seed once the soil is "
                 "thoroughly warm — soaking it overnight helps the hard coat — and "
                 "give it full sun. The perennial members (Turk's cap, rock rose) "
                 "also root from softwood cuttings taken in early summer."),
    },
    "Amaryllidaceae": {  # onion, garlic, leek, chives, shallot, wild onion
        "lead": "sets, cloves, or seed",
        "text": ("The onion family is grown three ways: from seed, from little "
                 "bulbs called sets, or — for garlic and shallots — by breaking "
                 "apart a bulb and planting the individual cloves. Garlic and "
                 "perennial onions are the easiest of all: plant a clove in fall, "
                 "harvest a whole head the next summer, and save your biggest "
                 "heads to replant. You never have to buy it again."),
    },
    "Polygonaceae": {  # sorrel, dock, buckwheat, rhubarb
        "lead": "seed or division",
        "text": ("This family — sorrel, dock, buckwheat, rhubarb — grows easily "
                 "from seed, and the perennial members (sorrel, rhubarb) clump up "
                 "and can be divided in early spring. Buckwheat is so fast from "
                 "seed it's used as a quick cover crop, flowering in about three "
                 "weeks."),
    },
    "Araceae": {  # taro, pothos, philodendron, peace lily, monstera
        "lead": "division and stem cuttings",
        "text": ("The arum family is propagated vegetatively, not from seed. The "
                 "edible types (taro) grow from cormels — offsets you break off "
                 "the parent corm. The houseplant members (pothos, philodendron, "
                 "monstera) root from stem cuttings taken at a node; drop them in "
                 "water and they'll root in a couple weeks."),
    },
    "Moraceae": {  # fig, mulberry, paw paw-adjacent
        "lead": "hardwood cuttings",
        "text": ("Figs and mulberries are some of the easiest woody plants to "
                 "clone. Take a pencil-thick hardwood cutting while the plant is "
                 "dormant in winter, stick two-thirds of it in soil, keep it "
                 "barely moist, and it'll leaf out and root by spring. One mature "
                 "tree can give you a whole orchard for the price of a pruning."),
    },
    "Cactaceae": {  # prickly pear
        "lead": "pad and stem cuttings",
        "text": ("Prickly pear and its kin propagate from a single pad. Snap one "
                 "off, let the cut end callus over in shade for a week so it won't "
                 "rot, then lay or shallowly plant it in dry, gritty soil. It "
                 "roots on its own with almost no water. It's nearly impossible to "
                 "kill this way."),
    },
    "Asparagaceae": {  # asparagus, agave, snake plant
        "lead": "division or crowns",
        "text": ("This family is propagated by division or by planting dormant "
                 "crowns. Asparagus is the long game — plant one-year crowns and "
                 "wait two full seasons before your first real harvest, but then a "
                 "bed produces for fifteen or twenty years. The succulent members "
                 "throw offsets ('pups') you can lift and pot up."),
    },
    "Zingiberaceae": {  # ginger, turmeric
        "lead": "rhizome pieces",
        "text": ("Ginger and turmeric grow from their own root — literally. Take a "
                 "knob of fresh rhizome with a visible bud, lay it just under warm, "
                 "rich soil, keep it humid, and it sends up shoots. A grocery-store "
                 "ginger root that's started to sprout will do it. They want heat "
                 "and a long season, so containers you can move are ideal here."),
    },
    "Boraginaceae": {  # borage, comfrey
        "lead": "seed (comfrey from root cuttings)",
        "text": ("Borage self-sows so freely from seed you'll have it forever after "
                 "one planting. Comfrey is the opposite — it almost never sets "
                 "viable seed and instead spreads from root cuttings. A two-inch "
                 "piece of comfrey root will grow a whole new plant, which is why "
                 "it's nearly impossible to remove once established."),
    },
    "Convolvulaceae": {  # sweet potato
        "lead": "slips (rooted shoots)",
        "text": ("Sweet potatoes grow from 'slips' — leafy shoots you sprout off a "
                 "stored tuber. Set a sweet potato half-buried in damp sand or "
                 "suspended in water, and in a few weeks it pushes out shoots you "
                 "snap off and root. Each tuber gives you a dozen or more new "
                 "plants."),
    },
    "Portulacaceae": {  # purslane
        "lead": "seed and stem cuttings",
        "text": ("Purslane is almost aggressively easy — tiny seed germinates in "
                 "warm soil, and any broken stem laid on damp ground will root at "
                 "the joints. That's exactly why it shows up uninvited in "
                 "sidewalk cracks. Lucky for us, it's also one of the most "
                 "nutritious greens you can eat."),
    },
    "Basellaceae": {  # malabar spinach
        "lead": "seed or stem cuttings",
        "text": ("Malabar spinach grows from seed (soak it first — the coat is "
                 "hard) or roots easily from a stem cutting set in water. It's a "
                 "heat-loving vine, so it shines in the dead of a Texas summer "
                 "when regular spinach has long since bolted."),
    },
    "Vitaceae": {  # grape, muscadine
        "lead": "hardwood cuttings",
        "text": ("Grapes and muscadines root from dormant hardwood cuttings taken "
                 "in winter — a length of pencil-thick cane with a few buds, stuck "
                 "in soil with one bud above the surface. They can also be "
                 "layered: bend a cane to the ground, bury a section, and it roots "
                 "while still attached to the mother vine."),
    },
    "Ericaceae": {  # blueberry
        "lead": "cuttings (and acid soil is everything)",
        "text": ("Blueberries root from softwood cuttings in early summer, but the "
                 "real trick with this family isn't propagation — it's pH. They "
                 "need genuinely acidic soil (4.5–5.5), which most of Texas does "
                 "not naturally have, so plan on amending heavily with peat and "
                 "elemental sulfur or growing in containers you control."),
    },
    "Rutaceae": {  # citrus
        "lead": "grafted stock (or seed for rootstock)",
        "text": ("Citrus is usually grafted, because seedlings take many years to "
                 "fruit and may not come true. On the Gulf Coast, cold-hardy "
                 "satsuma on trifoliate rootstock is the reliable choice. You can "
                 "sprout a seed for fun, but expect a decade-long wait and "
                 "uncertain fruit."),
    },
    "Tropaeolaceae": {  # nasturtium
        "lead": "direct-sown seed",
        "text": ("Nasturtiums grow from big, easy seeds sown right where they'll "
                 "grow once frost has passed — soak them overnight to soften the "
                 "hard coat and they come up fast. Give them poor, lean soil; rich "
                 "ground gives you lush leaves and few flowers. They self-sow, so "
                 "one planting often returns on its own."),
    },
    "Adoxaceae": {  # elderberry
        "lead": "hardwood cuttings",
        "text": ("Elderberry is one of the easiest woody plants to clone. In "
                 "winter, cut a pencil-thick dormant stem with a few buds, push "
                 "two-thirds of it into damp soil, and it roots by spring — a bare "
                 "stick becomes a fruiting shrub. Established plants also sucker "
                 "freely, so you can dig and move rooted offshoots."),
    },
    "Moringaceae": {  # moringa
        "lead": "seed or large cuttings",
        "text": ("Moringa is one of the fastest woody plants you'll ever grow, and "
                 "it propagates two easy ways. Seed germinates quickly in warm "
                 "soil. Even faster, a thick hardwood cutting — a branch an inch "
                 "or two across and a few feet long — pushed straight into the "
                 "ground will root and take off. Either way you can be harvesting "
                 "leaves the first summer. In our climate it's root-hardy: cut it "
                 "to the ground after a freeze and it springs back."),
    },
    "Bignoniaceae": {  # desert willow
        "lead": "seed or softwood cuttings",
        "text": ("Desert willow grows readily from seed collected from its long "
                 "pods, and also roots from softwood cuttings taken in early "
                 "summer. It's tough, fast, and forgiving once it's in the ground."),
    },
    "Verbenaceae": {  # frogfruit
        "lead": "division and cuttings",
        "text": ("Frogfruit spreads on its own — it roots at every node as it "
                 "creeps along the ground — so the easiest way to make more is to "
                 "lift a rooted section and replant it, or take short cuttings. "
                 "Plant a few plugs and they knit together into a living mat."),
    },
    "Plantaginaceae": {  # plantain weed
        "lead": "seed (it volunteers freely)",
        "text": ("Broadleaf plantain barely needs your help — it self-sows from "
                 "those rat-tail seed spikes and turns up wherever soil is "
                 "compacted. If you want it on purpose, scatter the seed on bare "
                 "ground and press it in; it asks for nothing else."),
    },
    "Cyperaceae": {  # chufa
        "lead": "tubers",
        "text": ("Chufa grows from its own little tubers — plant a few an inch deep "
                 "in warm, loose soil and each one multiplies into a clump that "
                 "makes dozens more by fall. Save some of the harvest to replant. "
                 "Because it spreads, many growers keep it in a tub or bed they "
                 "can contain."),
    },
    "Ebenaceae": {  # american persimmon
        "lead": "seed, grafting, or root suckers",
        "text": ("Native persimmon grows from seed (cold-stratified over winter) "
                 "but seedlings are variable, so named varieties are grafted. "
                 "Established trees also throw up root suckers you can dig and "
                 "transplant. You'll need a male and a female tree for fruit."),
    },
}

# ---- tag-driven cultivation detail ------------------------------------------
def _season_note(p):
    tags = p["tags"]
    if "cool-season" in tags:
        return ("This is a cool-season crop. On the Texas Gulf Coast that means "
                "your real windows are fall and late winter, not summer — sow as "
                "the heat breaks in September–October and again in late winter, "
                "and you'll harvest through our mild winters while the rest of "
                "the country is frozen out.")
    if "heat-lover" in tags:
        return ("This one thrives in heat that flattens other plants, so it earns "
                "its space through a Texas summer. Get it established before the "
                "worst of July, keep water steady, and it'll produce when little "
                "else will.")
    if "perennial" in tags and "perennial" not in ("",):
        return ("Because it's a perennial, the work is mostly up front. Get it "
                "sited and established and it comes back on its own year after "
                "year — one of the best returns on effort in the whole garden.")
    return ("Time your planting to our long warm season and watch the frost dates "
            "at both ends; the live weather tool on this site is built for "
            "exactly that.")

def _water_note(p):
    tags = p["tags"]
    if "drought" in tags or "low-water" in tags:
        return ("Once it's rooted in, this is a low-water plant — overwatering "
                "does more harm than drought here. Water deeply to establish, "
                "then back off and let it prove how tough it is.")
    if "container" in tags:
        return ("In a container it'll dry faster than in the ground, so check the "
                "top inch of soil daily in summer; pots on a hot Texas patio can "
                "need water every single day.")
    return ("Keep moisture even, especially while it's young — deep, less-frequent "
            "soaks build better roots than a daily sprinkle.")

def _harvest_note(p):
    cat = p["category"]
    days = p.get("quick", {}).get("Days to harvest", "")
    parts = (p.get("edible") or {}).get("parts", "")
    bits = []
    if days:
        bits.append(f"Figure on roughly {days.lower()} before you're harvesting.")
    if cat == "herb":
        bits.append("Pick herbs in the morning after the dew dries for the "
                     "strongest oils, and harvest little and often — regular "
                     "cutting keeps a herb bushy and stops it bolting.")
    elif cat in ("vegetable", "survival"):
        bits.append("Harvest at peak and keep harvesting — most vegetables "
                     "produce harder the more you pick, and one left to over-mature "
                     "tells the plant its job is done.")
    elif cat == "fruit":
        bits.append("Let fruit ripen on the plant where you can — it's where the "
                     "sugars finish — and pick gently to avoid bruising what you "
                     "don't eat right away.")
    if parts:
        bits.append(f"The part you're after: {parts.lower()}.")
    return " ".join(bits) if bits else ""

def _save_seed_note(p):
    tags = p["tags"]
    fam = p["family"].split("(")[0].strip()
    if "in-shop" in tags or "edible" in tags:
        if fam in ("Lamiaceae", "Moraceae", "Vitaceae", "Rosaceae", "Cactaceae",
                   "Araceae", "Zingiberaceae", "Convolvulaceae", "Basellaceae"):
            return ("Save it the easy way — vegetatively. Because you can clone "
                    "this plant from a cutting, division, or piece of root, you "
                    "never have to buy it again: keep one healthy mother plant and "
                    "make all the copies you want.")
        return ("Every seed we sell is open-pollinated, which means you can save "
                "your own from the best plants and it'll grow true next year. Let "
                "a few of your strongest plants finish and go to seed, dry it fully, "
                "and store it cool and dark. That's the whole point of heirlooms — "
                "buy once, grow forever.")
    return ("If you want more, let your healthiest plants mature fully and collect "
            "the seed once it's dry on the plant — then store it somewhere cool, "
            "dark, and dry until next season.")

def _wild_note(p):
    return ("A safety note, because this one grows wild: positive identification "
            "comes before anything goes in your mouth or your medicine. Confirm it "
            "on several features — leaf, stem, flower, smell — not a single "
            "resemblance, check the lookalike warnings, and never forage from "
            "roadsides or sprayed ground. When in doubt, leave it out.")

# ---- main entry -------------------------------------------------------------
def propagation_sections(p):
    """Return (sections, methods) for plant dict p.
    sections: list of (heading, [paragraph, ...])
    methods : list of (name, text) for HowTo schema
    """
    fam = p["family"].split("(")[0].strip()
    tags = p["tags"]
    cat = p["category"]
    common = p["common"]
    sections = []
    methods = []

    # 1) How to propagate it -------------------------------------------------
    fp = FAMILY_PROP.get(fam)
    prop_paras = []
    if fp:
        prop_paras.append(fp["text"])
        methods.append((f"Propagate {common}", fp["text"]))
        lead = fp["lead"]
    else:
        # generic but honest fallback by category
        if cat == "fruit":
            lead = "cuttings or grafted stock"
            txt = (f"{common} is best started from a cutting or nursery stock "
                   "rather than seed, so the fruit comes true to the parent. Seed "
                   "from fruit trees tends to revert to something wilder.")
        elif "perennial" in tags:
            lead = "seed or division"
            txt = (f"{common} comes up from seed and, once it's a few years old, "
                   "can be lifted and divided in cool weather to make more plants "
                   "and keep the clump vigorous.")
        else:
            lead = "seed"
            txt = (f"{common} is grown from seed. Start it in the season it "
                   "favors, keep the seedbed evenly moist until it's up, and thin "
                   "to give each plant room to size up.")
        prop_paras.append(txt)
        methods.append((f"Propagate {common}", txt))

    # cutting-specific bonus step where it applies
    if fam in ("Lamiaceae", "Moraceae", "Vitaceae") or "container" in tags and fam == "Araceae":
        prop_paras.append(
            "Beginner's path: take more cuttings than you think you need. They're "
            "free, they cost you nothing but a few minutes, and the ones that take "
            "more than make up for the ones that don't. This is how a single plant "
            "becomes a hedge, a row, or a gift for every neighbor on the street.")
    sections.append((f"How to propagate {common.lower()}", prop_paras))

    # 2) How to grow it through the Texas year -------------------------------
    grow_paras = [_season_note(p), _water_note(p)]
    sun = p.get("quick", {}).get("Sun", "")
    soil = p.get("quick", {}).get("Soil", "")
    if sun or soil:
        line = "Give it "
        if sun: line += sun.lower()
        if sun and soil: line += " and "
        if soil: line += f"{soil.lower()} soil"
        line += ". Match the spot to the plant and most of the battle is already won."
        grow_paras.insert(0, line)
    sections.append((f"Growing {common.lower()} in Texas", grow_paras))
    methods.append((f"Grow {common}",
                    " ".join(grow_paras)[:300]))

    # 3) Harvesting ----------------------------------------------------------
    hv = _harvest_note(p)
    if hv:
        sections.append((f"Harvesting", [hv]))
        methods.append((f"Harvest {common}", hv))

    # 4) Saving / making more for free --------------------------------------
    ss = _save_seed_note(p)
    sections.append(("Making more for free", [ss]))

    # 5) Wild safety note where relevant ------------------------------------
    if "wild" in tags or "forage" in tags:
        sections.append(("Before you forage it", [_wild_note(p)]))

    return sections, methods


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from plants_data import ALL_PLANTS
    total_paras = 0
    for p in ALL_PLANTS:
        secs, methods = propagation_sections(p)
        total_paras += sum(len(paras) for _, paras in secs)
    print(f"Generated propagation/cultivation content for {len(ALL_PLANTS)} plants")
    print(f"~{total_paras} new paragraphs, avg {total_paras/len(ALL_PLANTS):.1f} per plant")
    # spot check a few
    for slug in ("fig", "garlic", "tomato-heirloom", "prickly-pear", "dandelion", "ginger"):
        p = next((x for x in ALL_PLANTS if x["slug"] == slug), None)
        if not p: continue
        secs, _ = propagation_sections(p)
        print(f"\n=== {p['common']} ({p['family']}) ===")
        for h, paras in secs:
            print(f"  [{h}]")
