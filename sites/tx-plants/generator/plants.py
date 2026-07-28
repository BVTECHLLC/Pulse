#!/usr/bin/env python3
# Texas Roots — Plant Database
# The free plant data library: growing data, identification, edibility, survival use.
# Each plant is a dict. Fields drive page rendering, schema, search index, and filters.
#
# Field guide:
#   slug, common, latin, family, category(key into PLANT_CATS)
#   tags: list of filter tags (edible, medicinal, native-tx, drought, survival, perennial, ...)
#   summary: 1-2 sentence hook
#   quick: dict of at-a-glance data (sun, water, soil, hardiness, height, spacing, days, ph)
#   sections: list of (heading, paragraph) — long-form free data
#   id_marks: list of identification bullet strings (for "identify this plant")
#   lookalikes: list of (name, how-to-tell-apart)  — survival safety
#   edible: dict {parts, uses, caution} or None
#   companion: list of plant names
#   in_shop: bool (do we sell seed/cuttings) -> sales funnel CTA
#   sku_hint: short string for the shop tie-in

PLANT_CATS = {
    "vegetable": {"name": "Vegetables", "color": "#5C8A3A", "desc": "Food crops for the bed, the bucket, and the pantry."},
    "herb":      {"name": "Herbs", "color": "#7CB342", "desc": "Kitchen, tea, and medicine — small footprint, big return."},
    "fruit":     {"name": "Fruit & Berries", "color": "#B5552F", "desc": "Perennial food that pays you back for years."},
    "native":    {"name": "Texas Natives", "color": "#C99A3B", "desc": "Plants that already know how to live here."},
    "wild":      {"name": "Wild & Foraged", "color": "#8a5a3a", "desc": "What grows free on the fence line — and how to know it's safe."},
    "survival":  {"name": "Survival Calories", "color": "#5a6b72", "desc": "Storable energy crops for when it counts."},
    "cover":     {"name": "Cover & Soil Crops", "color": "#68a3c4", "desc": "Plants that feed the dirt instead of you."},
}

PLANTS = [
# ============================ VEGETABLES ============================
{
"slug":"tomato-heirloom","common":"Heirloom Tomato","latin":"Solanum lycopersicum","family":"Solanaceae (Nightshade)",
"category":"vegetable","tags":["edible","annual","full-sun","beginner","in-shop"],
"summary":"The plant that turns a beginner into a gardener. One good heirloom tomato off your own vine and you're hooked for life.",
"quick":{"Sun":"Full sun, 6–8 hr","Water":"Deep, even — 1–2 in/week","Soil":"Rich, well-drained loam","pH":"6.2–6.8","Hardiness":"Warm-season annual","Height":"4–8 ft (indeterminate)","Spacing":"24–36 in","Days to harvest":"60–85 from transplant"},
"sections":[
("What it is","An heirloom tomato is any open-pollinated variety passed down for generations — meaning its seed breeds true, so you can save it and grow the same tomato again next year. That's the whole reason heirlooms matter: you buy the seed once and own the line forever. Hybrids can't do that."),
("Growing it in Texas heat","The trick on the Gulf Coast is timing. Tomatoes set fruit best between 55°F and 85°F nights; once it's reliably above 90°F at night, blossoms drop and the plant just coasts. So you push hard in spring, take a break in deep summer, and many growers run a second crop from late-summer transplants for a fall harvest. Mulch heavily to keep roots cool and moisture even — uneven water is what splits fruit and causes blossom-end rot."),
("Determinate vs indeterminate","Determinate varieties grow to a set size and ripen most of their fruit in a couple weeks — good for canning. Indeterminate vines keep growing and fruiting until frost — good for fresh eating all season. Most heirlooms are indeterminate, so give them a real cage or a string trellis, not a flimsy store cone."),
("Feeding","Tomatoes are heavy feeders but too much nitrogen gives you a jungle with no fruit. Feed with something balanced or slightly phosphorus-forward once flowers appear. Calcium matters — a handful of crushed eggshell or gypsum in the hole helps prevent blossom-end rot, though inconsistent watering is the bigger culprit."),
],
"id_marks":["Compound leaves with jagged-edged leaflets, distinctly hairy and pungent when crushed","Yellow five-pointed star flowers in clusters","Square-ish fuzzy stems that root readily where they touch soil","Fruit hangs in trusses from the stem joints"],
"lookalikes":[("Other nightshades (potato, eggplant)","Same family, similar flowers — but tomato leaves are more deeply cut and the smell is unmistakable once you rub a leaf."),("Deadly nightshade / horsenettle","Wild nightshades can be toxic. Never eat fruit from a volunteer you can't positively identify — true tomato fruit grows on the soft fuzzy-stemmed plant you transplanted, not on a woody or spiny wild one.")],
"edible":{"parts":"Ripe fruit only","uses":"Fresh, sauced, canned, dried, fermented","caution":"Leaves and stems contain tomatine and are not for eating. Green unripe fruit is edible cooked but not raw in quantity."},
"companion":["Basil","Marigold","Carrot","Borage"],
"in_shop":True,"sku_hint":"heirloom tomato seed",
},
{
"slug":"okra","common":"Okra","latin":"Abelmoschus esculentus","family":"Malvaceae (Mallow)",
"category":"vegetable","tags":["edible","annual","full-sun","drought","heat-lover","in-shop"],
"summary":"The one crop that laughs at a Texas August. When everything else quits in the heat, okra is just getting started.",
"quick":{"Sun":"Full sun","Water":"Low once established — deeply drought-tough","Soil":"Tolerates poor soil, likes warmth","pH":"6.0–7.0","Hardiness":"Warm-season annual","Height":"4–8 ft","Spacing":"12–18 in","Days to harvest":"50–65"},
"sections":[
("Why okra belongs in every Texas garden","Okra evolved in hot, dry Africa and it shows. It thrives in the exact conditions that flatten tomatoes and lettuce — triple-digit heat, hard sun, lean soil. If you only grow one thing through a Gulf Coast summer, this is the safe bet."),
("Picking at the right size","This is the single skill that makes or breaks okra. Pods go from tender to woody fast — pick them at 2–4 inches, every single day during peak season. Miss two days and they're fibrous and only good for seed. The more you pick, the more the plant produces, so daily harvest actually increases your yield."),
("Handling the itch","Most okra varieties have fine spines that irritate skin. Wear long sleeves and gloves to harvest, or grow a spineless variety. The itch washes off; it's harmless, just annoying."),
],
"id_marks":["Tall single stalk, often reddish, with large lobed maple-like leaves","Big pale-yellow hibiscus flowers with a deep maroon center (it's in the same family as hibiscus and cotton)","Ribbed seed pods that point upward from the stem"],
"lookalikes":[("Ornamental hibiscus / cotton","Same family, similar flower — but okra makes the edible ribbed pod. None of the lookalikes are dangerous, just not productive food.")],
"edible":{"parts":"Young pods; leaves edible cooked; seeds can be roasted","uses":"Fried, stewed (gumbo), pickled, grilled, roasted","caution":"None of note. Mucilage ('slime') is reduced by high-heat cooking, acid, or drying."},
"companion":["Pepper","Eggplant","Basil","Sunflower"],
"in_shop":True,"sku_hint":"okra seed",
},
{
"slug":"sweet-potato","common":"Sweet Potato","latin":"Ipomoea batatas","family":"Convolvulaceae (Morning glory)",
"category":"vegetable","tags":["edible","perennial","full-sun","drought","survival","storage-crop","in-shop"],
"summary":"A survival staple disguised as a garden crop: massive calories, stores for months, and the leaves are edible greens all summer.",
"quick":{"Sun":"Full sun","Water":"Moderate; very drought-tolerant once vining","Soil":"Loose, sandy, low-fertility is fine","pH":"5.5–6.5","Hardiness":"Tender perennial grown as annual","Height":"Sprawling vine","Spacing":"12–18 in","Days to harvest":"90–120"},
"sections":[
("A true survival crop","Pound for pound of effort, few backyard crops return more storable calories than sweet potato. It tolerates poor soil, heat, and neglect, then hands you a dense, vitamin-rich tuber that keeps for months in a cool pantry without canning or refrigeration. That combination — high calories, long storage, low input — is exactly what you want in a food-security crop."),
("Two crops in one","While the tubers swell underground, the vine tips and young leaves are a genuine cooked green — mild, like spinach, and harvestable all summer without hurting the root harvest. Most Americans throw this food away; in much of the world it's the main reason the plant is grown."),
("Growing from slips","You don't plant seed — you plant 'slips,' the rooted sprouts that grow off a mature tuber. Set a sweet potato half-buried in damp sand or water, harvest the sprouts when they're 6 inches, root them, and plant out after the soil is warm. One grocery sweet potato can start an entire bed."),
("Curing for storage","Fresh-dug tubers are bland and bruise easily. Cure them at warm, humid conditions for about a week — this heals the skin and converts starch to sugar. Cured and stored cool and dark, they'll hold for months."),
],
"id_marks":["Trailing vine with heart-shaped or lobed leaves","Funnel-shaped pale purple or white morning-glory flowers","Milky sap in stems when broken","Edible tubers form on roots below the crown"],
"lookalikes":[("Ornamental morning glory / bindweed","Same family, similar flowers and heart leaves — but those make no edible tuber and some ornamental morning glory seed is toxic. Grow named edible varieties; don't dig and eat roots off a wild vine.")],
"edible":{"parts":"Tubers and young leaves/shoots","uses":"Roasted, mashed, fried; leaves sautéed like spinach","caution":"Eat leaves cooked. Don't confuse with toxic ornamental morning glory seed."},
"companion":["Bush bean","Thyme","Dill"],
"in_shop":True,"sku_hint":"sweet potato slips",
},
{
"slug":"collard-greens","common":"Collard Greens","latin":"Brassica oleracea (Acephala)","family":"Brassicaceae (Cabbage)",
"category":"vegetable","tags":["edible","cool-season","full-sun","beginner","cut-and-come-again"],
"summary":"The most forgiving green in the South. Hardy through frost, harvest leaf-by-leaf for months, and it actually tastes sweeter after a cold snap.",
"quick":{"Sun":"Full sun to part shade","Water":"Even moisture","Soil":"Rich, well-drained","pH":"6.0–7.0","Hardiness":"Cool-season; survives hard frost","Height":"2–3 ft","Spacing":"18–24 in","Days to harvest":"50–75; pick leaves anytime"},
"sections":[
("The Gulf Coast winter crop","While the rest of the country shuts down for winter, collards hit their stride. Plant in fall, harvest right through Texas winter. A frost doesn't kill them — it converts starches to sugars, so the leaves get noticeably sweeter after the first cold nights."),
("Harvest the right way","Don't cut the whole plant. Pick the lower, outer leaves and leave the growing crown — the plant keeps making new leaves from the center for months. One row of collards planted in October can feed a family deep into spring this way."),
],
"id_marks":["Large, flat, blue-green paddle-shaped leaves on a thick central stalk","Smooth waxy leaf surface (no curl, unlike kale)","Grows in a loose rosette, leafing upward as it ages"],
"lookalikes":[("Kale, cabbage, other brassicas","All the same species — none dangerous, all edible. Collards are the flat, smooth, heat-and-cold-tough one.")],
"edible":{"parts":"Leaves (and tender stems)","uses":"Braised, in soups, sautéed, raw when young","caution":"None."},
"companion":["Onion","Dill","Potato","Marigold"],
"in_shop":False,"sku_hint":"",
},
# ============================ HERBS ============================
{
"slug":"basil","common":"Basil","latin":"Ocimum basilicum","family":"Lamiaceae (Mint)",
"category":"herb","tags":["edible","annual","full-sun","beginner","container","in-shop"],
"summary":"The gateway herb. Fast, fragrant, foolproof, and it makes your tomatoes grow better while it's at it.",
"quick":{"Sun":"Full sun, 6+ hr","Water":"Even moisture, don't let it wilt","Soil":"Rich, well-drained","pH":"6.0–7.0","Hardiness":"Tender annual (hates frost)","Height":"12–24 in","Spacing":"10–12 in","Days to harvest":"3–4 weeks for first pinch"},
"sections":[
("Pinch to win","The whole secret to bushy, productive basil is pinching. The moment a stem shows its first flower bud, pinch the top two leaves off. This forces the plant to branch and stay leafy. Let it flower and it'll put energy into seed and the leaves turn bitter. Keep it pinched and one plant feeds you all summer."),
("Loves the heat, hates the cold","Basil is a true warm-season plant. Don't rush it into cold spring soil — wait until nights are reliably above 50°F. On the Gulf Coast it'll run from late spring until the first fall cool-down."),
],
"id_marks":["Square stems (a mint-family tell — roll it between your fingers)","Opposite, glossy oval leaves, intensely fragrant when brushed","White or purple flower spikes at the stem tips"],
"lookalikes":[("Other mint-family herbs","All have square stems; smell is the giveaway. Basil's scent is sweet and clove-like — nothing in the family is dangerous.")],
"edible":{"parts":"Leaves and flowers","uses":"Fresh, pesto, dried, infused oils, tea","caution":"None."},
"companion":["Tomato","Pepper","Oregano"],
"in_shop":True,"sku_hint":"basil seed",
},
{
"slug":"rosemary","common":"Rosemary","latin":"Salvia rosmarinus","family":"Lamiaceae (Mint)",
"category":"herb","tags":["edible","medicinal","perennial","full-sun","drought","container","in-shop"],
"summary":"Plant it once and it's there for a decade. Drought-proof, evergreen, and the easiest perennial herb to root from a cutting.",
"quick":{"Sun":"Full sun","Water":"Low — overwatering kills it","Soil":"Lean, sharp-draining, even rocky","pH":"6.0–7.0","Hardiness":"Evergreen perennial, hardy to ~15°F","Height":"2–5 ft","Spacing":"24–36 in","Days to harvest":"Snip anytime once established"},
"sections":[
("The drought champion of the herb bed","Rosemary is a Mediterranean shrub that wants exactly what kills most herbs: poor soil, sharp drainage, and to be left thirsty. The number one way people kill rosemary is kindness — too much water and rich soil rot the roots. Plant it lean and ignore it."),
("Free plants forever","Rosemary roots almost too easily from cuttings. Snip a 4–6 inch tip, strip the lower leaves, stick it in damp sand or a glass of water, and in a few weeks you have a new plant. This is exactly the kind of rooted cutting we propagate and mail."),
],
"id_marks":["Woody shrub with narrow, needle-like leaves (green above, pale below)","Powerfully piney-resinous smell when brushed","Small pale blue-to-violet flowers along the stems","Square young stems (mint family) turning woody with age"],
"lookalikes":[("Lavender","Similar gray-green needle look from a distance, but lavender's leaves are softer and the scent is floral, not piney. Neither is dangerous.")],
"edible":{"parts":"Leaves and flowers","uses":"Cooking, tea, infused oil; traditional medicinal use","caution":"Culinary amounts are safe; very large medicinal doses are not advised in pregnancy."},
"companion":["Sage","Thyme","Cabbage","Bean"],
"in_shop":True,"sku_hint":"rooted rosemary cutting",
},
{
"slug":"mint","common":"Mint","latin":"Mentha spp.","family":"Lamiaceae (Mint)",
"category":"herb","tags":["edible","medicinal","perennial","part-shade","container","vigorous"],
"summary":"Unkillable, useful, and a thug. Grow it — but grow it in a pot, or it will own your whole garden by next year.",
"quick":{"Sun":"Part shade to full sun","Water":"Likes consistent moisture","Soil":"Almost anything","pH":"6.0–7.5","Hardiness":"Tough perennial","Height":"1–2 ft","Spacing":"Contain it!","Days to harvest":"Snip anytime"},
"sections":[
("Always contain it","Mint spreads by underground runners and it does not respect property lines. Plant it in the open ground and within a season it'll be everywhere. The rule among growers: mint goes in a pot, period. A buried bottomless bucket works if you want it in a bed."),
("What it's good for","Beyond tea and cooking, mint is one of the classic settle-the-stomach herbs, and its strong scent confuses pests — a pot of mint near a doorway or in the garden earns its keep."),
],
"id_marks":["Square stems, opposite leaves, unmistakable cool menthol smell","Toothed, slightly fuzzy leaves","Spreads aggressively by surface and underground runners","Small white-to-purple flower spikes"],
"lookalikes":[("Other mint-family plants","Many look similar; the menthol smell confirms true mint. None in the smell-test group are dangerous.")],
"edible":{"parts":"Leaves and flowers","uses":"Tea, cooking, garnish, infused water","caution":"None in normal use."},
"companion":["Cabbage","Tomato (keep contained)","Pea"],
"in_shop":False,"sku_hint":"",
},
# ============================ FRUIT ============================
{
"slug":"fig","common":"Fig","latin":"Ficus carica","family":"Moraceae (Mulberry)",
"category":"fruit","tags":["edible","perennial","full-sun","drought","beginner","in-shop"],
"summary":"The perfect Texas backyard fruit: heat-loving, drought-tough, roots from a stick, and gives you fruit the same year you plant a cutting.",
"quick":{"Sun":"Full sun","Water":"Low once established","Soil":"Tolerates most; wants drainage","pH":"6.0–7.5","Hardiness":"Hardy to ~15°F; roots survive lower","Height":"10–20 ft (prunable)","Spacing":"10–15 ft","Days to harvest":"Fruit in 1–2 years from cutting"},
"sections":[
("Why figs love it here","Figs are built for hot, dry summers and mild winters — which describes most of Texas. They ask for almost nothing once rooted, shrug off drought, and have very few pests. For a beginner who wants real fruit fast, nothing beats a fig."),
("Free fig trees from cuttings","This is the magic of figs: a dormant cutting the thickness of a pencil, stuck in soil, will root and become a whole tree. One mature fig can start a dozen new trees a year. It's the single easiest fruit to propagate and share — and exactly what we root and mail."),
("Getting fruit, not just leaves","Most common Texas figs ('Celeste,' 'Brown Turkey,' and others) are self-fruitful — they don't need a pollinator. If your young tree drops fruit before ripening, it's usually water stress or youth; consistent moisture as fruit swells fixes it."),
],
"id_marks":["Large, deeply lobed, sandpapery leaves (the classic 'fig leaf' shape)","Milky white sap from any cut stem or leaf","Fruit grows directly on the branch, with no visible flower","Smooth gray bark"],
"lookalikes":[("Ornamental figs (rubber tree, etc.)","Same genus, similar milky sap, but not grown for edible fruit. Edible fig has the lobed sandpaper leaf.")],
"edible":{"parts":"Ripe fruit","uses":"Fresh, dried, preserves","caution":"Milky sap is a skin/eye irritant for some people — harmless once washed. Fruit must be ripe (soft, drooping) to be good."},
"companion":["Rosemary","Strawberry (as groundcover)"],
"in_shop":True,"sku_hint":"rooted fig cutting",
},
{
"slug":"blackberry","common":"Blackberry","latin":"Rubus spp.","family":"Rosaceae (Rose)",
"category":"fruit","tags":["edible","perennial","full-sun","native-adjacent","beginner"],
"summary":"Plant a row once and pick berries every summer for years. Thornless varieties make it a kid-friendly, fence-line food machine.",
"quick":{"Sun":"Full sun","Water":"Even moisture while fruiting","Soil":"Well-drained, tolerates clay if raised","pH":"5.5–6.5","Hardiness":"Hardy perennial","Height":"3–6 ft canes","Spacing":"3–4 ft","Days to harvest":"Fruit in year 2"},
"sections":[
("Understanding canes","Blackberries fruit on second-year canes (floricanes). First-year canes (primocanes) just grow; the next year they fruit, then die and are replaced. Knowing this is the whole game: after a cane fruits, cut it to the ground, and the new green canes take over for next year. Some newer varieties fruit on first-year canes too."),
("Texas-tough choices","Erect, thornless, heat-adapted varieties bred for the South (the 'Arapaho,' 'Natchez,' and Prime-Ark lines, among others) are the easy path. Trellis the canes on a simple two-wire fence and picking becomes effortless."),
],
"id_marks":["Arching canes, often thorny, with palmate (5-leaflet) toothed leaves","White-to-pink five-petaled rose-family flowers","Aggregate berry that pulls off WITH its core (this distinguishes it from raspberry, which leaves the core behind)","Canes root where the tips touch ground"],
"lookalikes":[("Dewberry (wild Rubus)","A trailing wild cousin, also edible and common on Texas roadsides — same safe berry, just lower-growing."),("Pokeweed berries","NOT a bramble — pokeweed has smooth purple-black berries in hanging clusters on a smooth red stalk and is TOXIC. Real blackberries grow on thorny/arching canes with compound leaves. Never eat a dark berry off a smooth herbaceous stalk.")],
"edible":{"parts":"Ripe berries (dull-black, pull free easily)","uses":"Fresh, jam, cobbler, frozen, wine","caution":"Eat only fully ripe, freely-detaching berries from a true bramble cane. See pokeweed lookalike warning."},
"companion":["Garlic","Chive","Tansy"],
"in_shop":False,"sku_hint":"",
},
# ============================ TEXAS NATIVES ============================
{
"slug":"texas-sage","common":"Texas Sage (Cenizo)","latin":"Leucophyllum frutescens","family":"Scrophulariaceae","category":"native",
"tags":["native-tx","drought","full-sun","perennial","pollinator","low-water"],
"summary":"The plant that blooms when it smells rain. A native silver shrub that needs zero irrigation and predicts Gulf storms better than the news.",
"quick":{"Sun":"Full sun","Water":"None once established — true xeric","Soil":"Lean, alkaline, rocky, sharp-draining","pH":"7.0–8.5","Hardiness":"Evergreen native, very heat/drought hardy","Height":"3–6 ft","Spacing":"4–6 ft","Days to harvest":"Ornamental/pollinator"},
"sections":[
("A weather forecaster in plant form","Texas sage is famous for bursting into purple bloom a day or two after a rise in humidity — which is why old-timers call it the 'barometer bush.' When the cenizo blooms, rain is usually near. It's a living illustration of why we built a weather tool into this site: growers have always read the sky and the plants together."),
("The ultimate low-water native","Cenizo evolved on the dry, alkaline soils of South and West Texas. It wants full brutal sun, lean rocky ground, and to be left completely alone. Irrigation and rich soil rot it. For a water-wise Texas yard, almost nothing is tougher."),
],
"id_marks":["Compact mounding shrub with small silvery-gray fuzzy leaves","Bell-shaped purple, magenta, or white flowers that appear in flushes after humidity rises","Thrives in the worst, driest, rockiest spot in the yard"],
"lookalikes":[("Russian sage, lavender","Similar silvery look from afar, but cenizo's bloom-on-humidity habit and bell flowers are distinctive. None dangerous.")],
"edible":None,
"companion":["Agave","Yucca","Native grasses"],
"in_shop":False,"sku_hint":"",
},
{
"slug":"prickly-pear","common":"Prickly Pear Cactus","latin":"Opuntia spp.","family":"Cactaceae (Cactus)","category":"native",
"tags":["native-tx","edible","drought","full-sun","perennial","survival"],
"summary":"Texas's edible cactus: pads (nopales) and fruit (tunas) are both food, it survives anything, and it roots from a single fallen pad.",
"quick":{"Sun":"Full sun","Water":"Essentially none needed","Soil":"Sandy, rocky, sharp drainage","pH":"6.0–8.0","Hardiness":"Extremely drought/heat hardy native","Height":"2–6 ft","Spacing":"3–5 ft","Days to harvest":"Pads year-round; fruit late summer"},
"sections":[
("Two foods from one survival plant","Prickly pear is a genuine survival food native to Texas. The young pads (nopales) are a cooked vegetable — mild, like green beans. The ripe fruit (tunas) are sweet and made into syrup, jelly, and juice. Both are loaded with water and nutrients in a plant that needs no care at all."),
("The glochid warning","The danger isn't the big spines — it's the glochids, the tiny hair-like barbs in clusters on the pads and fruit. They embed in skin and are miserable to remove. Always handle with thick gloves and tongs, and burn or scrape off the glochids before eating. This is the single most important safety point with prickly pear."),
("How it spreads","A pad that falls and touches soil will root and start a new plant. This is how prickly pear colonizes — and how you propagate it: lay a cut pad on dry soil for a few days to callus, then half-bury it."),
],
"id_marks":["Flat, oval, paddle-shaped green pads (modified stems) joined in chains","Clusters of tiny barbed glochids plus larger spines on the pads","Showy yellow, orange, or red flowers along the pad edges","Egg-shaped fruit (tunas) ripening red-purple in late summer"],
"lookalikes":[("Other cacti","Few true lookalikes in Texas; the flat jointed pads are distinctive. The real hazard is the glochids, not misidentification.")],
"edible":{"parts":"Young pads (nopales) and ripe fruit (tunas)","uses":"Pads grilled/sautéed; fruit as juice, syrup, jelly","caution":"CRITICAL: remove all glochids (tiny barbed hairs) before handling food. Wear gloves to harvest. Burn/scrape glochids off."},
"companion":["Agave","Yucca","Native wildflowers"],
"in_shop":False,"sku_hint":"",
},
# ============================ WILD & FORAGED ============================
{
"slug":"dandelion","common":"Dandelion","latin":"Taraxacum officinale","family":"Asteraceae (Aster)","category":"wild",
"tags":["edible","medicinal","wild","forage","beginner-forage"],
"summary":"The most useful 'weed' in the yard. Every part is edible, it's nearly impossible to misidentify fatally, and it's free everywhere.",
"quick":{"Sun":"Sun to part shade","Water":"Whatever falls","Soil":"Any","pH":"Any","Hardiness":"Tough perennial","Height":"6–12 in","Spacing":"n/a (wild)","Days to harvest":"Year-round leaves"},
"sections":[
("A safe first forage","Dandelion is one of the best plants to learn foraging on because the whole plant is edible and its key features are hard to fake: a basal rosette (leaves all from ground level, no leafy stalk), a single flower per hollow stem, and milky sap. Leaves are a bitter green (best young), flowers make wine and fritters, and the roasted root is a coffee substitute."),
("Know the one rule","Only forage from ground you know hasn't been sprayed with herbicide or sits along a road soaking up exhaust. The plant is safe; the chemistry of where it grows is the only real risk."),
],
"id_marks":["Leaves in a flat basal rosette, deeply toothed (the 'lion's tooth' that names it), all rising from the very base — no leaves up the stalk","A single yellow composite flower atop each smooth, hollow, leafless stem","Milky white sap in stem and leaves","Puffball seed head"],
"lookalikes":[("Cat's ear, sow thistle, hawkweed","Several yellow 'dandelion-like' Asteraceae exist. The good news: the common lookalikes are also non-toxic. True dandelion has ONE flower per hollow, leafless, unbranched stem and smooth (not hairy) leaves. If a stem is branched, solid, or leafy, it's a cousin — still generally safe, but that's how you tell.")],
"edible":{"parts":"Leaves, flowers, roots — all parts","uses":"Salad/cooked greens, flower wine/fritters, roasted-root coffee","caution":"Harvest only from unsprayed, non-roadside ground. Milky sap is bitter, not toxic."},
"companion":["(Wild — actually a beneficial dynamic-accumulator in beds)"],
"in_shop":False,"sku_hint":"",
},
{
"slug":"purslane","common":"Purslane","latin":"Portulaca oleracea","family":"Portulacaceae","category":"wild",
"tags":["edible","wild","forage","drought","survival","nutrient-dense"],
"summary":"A juicy 'weed' growing in your driveway cracks that's richer in omega-3s than most vegetables. Free, abundant, and delicious.",
"quick":{"Sun":"Full sun","Water":"Drought-proof succulent","Soil":"Any, even gravel","pH":"Any","Hardiness":"Warm-season annual","Height":"Ground-hugging mat","Spacing":"n/a (wild)","Days to harvest":"Summer"},
"sections":[
("Better than what you planted","Purslane is a succulent 'weed' most people pull and toss — yet it's one of the most nutritious leafy plants you can eat, notably high in omega-3 fatty acids, with a pleasant lemony, slightly salty crunch. It thrives in heat and drought in the worst soil. In a survival sense, free abundant calories and nutrition growing in sidewalk cracks is a gift."),
("The critical lookalike","This is the one wild edible where identification truly matters, because of spurge."),
],
"id_marks":["Thick, smooth, succulent (water-filled) reddish stems lying flat in a mat","Fat, paddle-shaped fleshy leaves clustered at stem tips","NO milky sap (clear juice only)","Tiny yellow flowers"],
"lookalikes":[("Spurge (Euphorbia) — DANGEROUS","This is the must-know. Spurge grows in the same spots with a similar sprawling habit, BUT spurge has thin, NON-succulent stems and bleeds MILKY WHITE SAP when broken, and its leaves are thin, not fleshy. Purslane has fat juicy stems and CLEAR sap. Rule: break a stem — milky sap means spurge, throw it out. Clear sap and fat succulent leaves means purslane.")],
"edible":{"parts":"Stems, leaves, flowers","uses":"Raw in salad, sautéed, pickled, in soups","caution":"MUST distinguish from milky-sapped spurge (toxic). Snap a stem: clear sap = safe purslane; white milky sap = discard."},
"companion":["(Wild groundcover; living mulch)"],
"in_shop":False,"sku_hint":"",
},
# ============================ SURVIVAL CALORIES ============================
{
"slug":"corn-dent","common":"Dent / Field Corn","latin":"Zea mays","family":"Poaceae (Grass)","category":"survival",
"tags":["edible","annual","full-sun","survival","storage-crop","staple-calorie"],
"summary":"The original American survival crop. Dent corn dries on the stalk, stores for a year, and grinds into cornmeal — true storable calories.",
"quick":{"Sun":"Full sun","Water":"Steady, especially at tasseling","Soil":"Rich, nitrogen-hungry","pH":"6.0–6.8","Hardiness":"Warm-season annual","Height":"6–10 ft","Spacing":"Plant in blocks, 10–12 in","Days to harvest":"90–120 (dry)"},
"sections":[
("Sweet corn vs survival corn","The corn you eat off the cob fresh is sweet corn — wonderful, but it doesn't store. Dent (field) corn and flint corn are the storage crops: you let them dry hard on the stalk, shell the kernels, and keep them for a year or grind them into cornmeal and grits. For food security, this is the corn that matters."),
("Plant in a block, not a row","Corn is wind-pollinated, so a single long row pollinates poorly and you get gap-toothed ears. Always plant corn in a square block of at least 4 rows so pollen falls across the whole patch. This one fact fixes most first-time corn failures."),
("The Three Sisters","Corn, beans, and squash are the classic companion trio: corn gives the beans a pole, beans fix nitrogen for the heavy-feeding corn, and squash shades the ground and blocks weeds. It's one of the most efficient survival-garden layouts ever devised."),
],
"id_marks":["Tall single grass stalk with broad strap leaves","Tassel (male flower) at the very top; ears (female) lower on the stalk with silk","Dent corn kernels show a dimple ('dent') on top when dry"],
"lookalikes":[("Sorghum, other tall grasses","Similar tall-grass look; corn's ears-with-silk and top tassel are unmistakable. None dangerous.")],
"edible":{"parts":"Kernels (dried, ground); fresh if harvested young","uses":"Cornmeal, grits, hominy, animal feed","caution":"Store fully dry to prevent mold. Nixtamalization (lime treatment) improves nutrition."},
"companion":["Bean","Squash","Sunflower"],
"in_shop":False,"sku_hint":"",
},
{
"slug":"winter-squash","common":"Winter Squash","latin":"Cucurbita spp.","family":"Cucurbitaceae (Gourd)","category":"survival",
"tags":["edible","annual","full-sun","survival","storage-crop","staple-calorie","in-shop"],
"summary":"Grow it in summer, eat it all winter. A hard-shelled squash stores for months on a shelf with no canning — dense, dependable calories.",
"quick":{"Sun":"Full sun","Water":"Deep, consistent","Soil":"Rich, lots of compost","pH":"6.0–6.8","Hardiness":"Warm-season annual","Height":"Sprawling vine","Spacing":"3–4 ft","Days to harvest":"85–120"},
"sections":[
("Why it's a survival cornerstone","Winter squash (butternut, acorn, hubbard, pumpkin and kin) earns its name not from when it grows but from when you eat it. Harvested in fall with a hard rind and cured, a good keeper squash sits on a pantry shelf for 3–6 months with zero processing — no canning, no freezing, no power. That shelf-stable, high-calorie, vitamin-rich profile is exactly what a food-security garden needs."),
("Curing and storage","Leave a 2-inch stem on, cure in a warm dry spot for a couple weeks to harden the skin, then store cool and dry. A cured butternut is one of the longest-keeping vegetables you can grow."),
("Beat the squash bugs","Vine borers and squash bugs are the main enemy. Butternut and other Cucurbita moschata types have solid stems that resist borers better than thin-stemmed varieties — a smart survival-garden pick for that reason alone."),
],
"id_marks":["Large sprawling vine with big lobed leaves and curling tendrils","Big yellow-orange trumpet flowers (separate male and female)","Hard-rinded fruit that doesn't dent under a thumbnail when mature"],
"lookalikes":[("Ornamental gourds","Same family, often inedible/bitter. Grow named edible varieties. Extreme bitterness in any squash = don't eat it (rare cucurbit toxin).")],
"edible":{"parts":"Mature flesh and seeds; flowers and young shoots too","uses":"Roasted, soups, pies; seeds roasted","caution":"Discard any squash that tastes intensely bitter (rare toxic cucurbitacins)."},
"companion":["Corn","Bean","Nasturtium"],
"in_shop":True,"sku_hint":"winter squash seed",
},
# ============================ COVER & SOIL ============================
{
"slug":"crimson-clover","common":"Crimson Clover","latin":"Trifolium incarnatum","family":"Fabaceae (Legume)","category":"cover",
"tags":["cover-crop","nitrogen-fixer","pollinator","cool-season","soil-builder"],
"summary":"A cover crop that feeds your soil for free. It pulls nitrogen out of the air, then you cut it down and it becomes fertilizer.",
"quick":{"Sun":"Full sun","Water":"Cool-season rains","Soil":"Most; improves as it grows","pH":"6.0–7.0","Hardiness":"Cool-season annual","Height":"12–18 in","Spacing":"Broadcast","Days to harvest":"Terminate at bloom"},
"sections":[
("Free fertilizer from the air","Legumes like crimson clover host bacteria on their roots that pull nitrogen out of the atmosphere and lock it into the soil. Grow it over winter on an empty bed, then cut it down before it sets seed and let it break down in place — you've just fertilized that bed for free and added organic matter at the same time. This is the heart of building soil instead of buying it."),
("Bonus: it feeds the bees","The deep crimson blooms are a magnet for pollinators in early spring, so a winter cover of clover also primes your garden's pollinator population right before the growing season."),
],
"id_marks":["Classic three-part clover leaflets","Striking elongated crimson-red flower heads (not round like white clover)","Low spreading habit, soft-hairy stems"],
"lookalikes":[("Other clovers/medics","All legumes, all soil-friendly, none dangerous. Crimson clover's deep-red elongated bloom is the tell.")],
"edible":None,
"companion":["(Precedes heavy feeders like corn, squash, tomato)"],
"in_shop":False,"sku_hint":"",
},
{
"slug":"sunflower","common":"Sunflower","latin":"Helianthus annuus","family":"Asteraceae (Aster)","category":"cover",
"tags":["edible","annual","full-sun","pollinator","beginner","in-shop","soil-builder"],
"summary":"Beauty with a job. It feeds pollinators, makes edible seeds, breaks up compacted soil with deep roots, and kids love growing it.",
"quick":{"Sun":"Full sun","Water":"Moderate; deep roots find their own","Soil":"Tolerates poor soil","pH":"6.0–7.5","Hardiness":"Warm-season annual","Height":"3–12 ft by variety","Spacing":"12–24 in","Days to harvest":"70–100 for seed"},
"sections":[
("More than a pretty face","Sunflowers send a deep taproot that breaks up compacted ground, their flowers are a top pollinator and beneficial-insect draw, and the seeds feed you, the birds, and the chickens. Tall varieties even make a quick summer privacy screen or a living trellis for beans."),
("Harvesting seed","When the back of the head turns yellow-brown and the seeds are plump and striped, cut the head and dry it in a ventilated spot away from birds. Rub the seeds free once fully dry. Save some to replant — open-pollinated sunflowers come true from saved seed."),
],
"id_marks":["Tall coarse stalk with big rough heart-shaped leaves","Large composite flower head that tracks the sun when young","Center disk of developing seeds ringed by yellow ray petals"],
"lookalikes":[("Other Helianthus / daisies","Many aster-family lookalikes; the giant single head and rough leaves are distinctive. None dangerous.")],
"edible":{"parts":"Seeds (and sprouts, petals)","uses":"Roasted seeds, oil, bird/chicken feed","caution":"None."},
"companion":["Corn","Cucumber","Bean"],
"in_shop":True,"sku_hint":"sunflower seed",
},
]

# ---- new almanac article tying weather + plants together (the "one new Jordan post" SEO add) ----
NEW_ALMANAC = {
"slug":"reading-the-weather-for-your-garden",
"title":"Reading the Weather for Your Garden (Frost, Heat & the 7-Day Window)",
"category":"growing","icon":"water.svg","read_min":8,
"summary":"How I use the 7-day forecast to decide what to plant, when to cover, and when to just wait. The single most useful skill I can hand a new grower — and why I put a live weather tool right on this site.",
"body":[
("p","People ask me what the most important tool in my greenhouse is. It isn't a fancy meter or a heated mat. It's the weather forecast, and knowing how to read it. Almost every gardening mistake I made early on came down to ignoring what the sky was about to do. So this is the habit I'd hand you first — and it's exactly why I built a live 7-day weather tool right into this site."),
("h","The two numbers that decide everything"),
("p","Forget the fancy stuff at first. Watch two things: the overnight low and the daytime high over the next seven days. The overnight low tells you about frost and cold stress. The daytime high tells you about heat stress and whether seeds will even germinate. Get in the habit of reading the week ahead, not just today, because the danger is almost always two or three days out."),
("h","Frost: the line that kills"),
("p","A light frost starts around 32°F; a hard freeze at 28°F and below will kill most tender plants outright. When I see a low in the 30s coming in the 7-day, that's my cue to act: cover tender plants with frost cloth or an old sheet in the late afternoon (trapping the day's ground heat), water the soil beforehand because moist soil holds warmth, and move anything in pots against the house or into the greenhouse. The forecast gives me a day or two of warning — that's all it takes."),
("tip","On the Gulf Coast our killing frosts are few but sudden. I keep frost cloth folded and ready from November through February so a surprise low never catches me flat-footed. Watching the 7-day means I'm never surprised."),
("h","Heat: the silent crop-killer"),
("p","Heat is sneakier than frost because it doesn't kill in a night — it just shuts plants down. Once daytime highs sit above the mid-90s, tomatoes drop their blossoms, lettuce bolts to seed, and newly-sown beds bake dry by noon. When I see a hot stretch coming, I hold off on transplanting, sow heat-lovers like okra and sweet potato instead, mulch heavily, and shift watering to early morning so plants go into the heat fully charged."),
("h","Germination is a temperature game"),
("p","Seeds don't read the calendar; they read soil temperature. Cool-season crops like lettuce, spinach, and peas germinate in cool soil and stall in heat. Warm-season crops like beans, squash, corn, and okra rot in cold wet soil and only wake up once it's warm. Reading the coming week's lows tells you whether the soil is heading the right direction before you waste seed."),
("table",["Coming 7-day pattern","What I plant / do"],[
["Lows steady above 55°F, highs under 90°F","Prime window — transplant tomatoes, peppers, start most things"],
["Lows dropping into the 30s","Cover tender crops; hold transplants; great time to sow cool-season greens"],
["Highs climbing past 95°F","Switch to heat-lovers (okra, sweet potato, southern peas); mulch; water at dawn"],
["A wet stretch incoming","Hold off sowing seed in beds (rot risk); good time to transplant established starts"],
]),
("h","Why the tool is right here on the site"),
("p","I added a live weather report to Texas Roots for a simple reason: the forecast is the first thing I check before I make any decision in the greenhouse, and it should be the first thing you check too. It pulls a current reading and the full 7-day outlook for wherever you are, so you can look at the week, look at what you're about to plant, and make the call the way a grower has always made it — by reading the sky first."),
("quote","The best growers I know aren't the ones with the most gear. They're the ones who read the week ahead and work with it instead of against it."),
("p","Start there. Check the seven-day before you plant, before you cover, before you water. Do that for one season and you'll waste less seed, lose fewer plants, and start to feel the rhythm of your own piece of ground. That's the whole game."),
],
}
