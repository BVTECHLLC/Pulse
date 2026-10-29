// New content is intentionally data-first, to keep the armory and random loot expandable.
export const V3_WEAPONS=[
 {id:'crossbow',name:'Phantom Crossbow',icon:'➶',rarity:'common',desc:'Piercing spectral bolts with luminous tracer tails.',color:0x84efdb,damage:26,cooldown:1.12,projectiles:1,model:'crossbow_common'},
 {id:'meteor',name:'Starfall Grimoire',icon:'☄',rarity:'rare',desc:'Falling meteors burst into fiery impact zones.',color:0xff954b,damage:46,cooldown:3.35,projectiles:1,model:'spellBook'},
 {id:'chakram',name:'Moon Chakrams',icon:'◈',rarity:'uncommon',desc:'Wide spinning discs pierce packs of enemies.',color:0x82efff,damage:24,cooldown:1.55,projectiles:2,model:'dagger_rare'},
 {id:'crystal',name:'Crystal Fusillade',icon:'✧',rarity:'uncommon',desc:'A fan of jagged violet shards.',color:0xc09aff,damage:14,cooldown:1.28,projectiles:5,model:'staff_uncommon'},
 {id:'sunbow',name:'Sunpiercer Bow',icon:'☀',rarity:'rare',desc:'Golden arrows pierce and scorch enemies in a line.',color:0xffd382,damage:31,cooldown:1.65,projectiles:2,model:'crossbow_rare'},
 {id:'widow',name:'Widowmaker Daggers',icon:'✣',rarity:'common',desc:'Rapid precision knives that critically strike.',color:0xff72a2,damage:13,cooldown:.45,projectiles:1,model:'dagger_common'},
 {id:'spirits',name:'Wraith Lantern',icon:'♧',rarity:'rare',desc:'Summon seeking blue spirits that orbit and hunt.',color:0x80a9ff,damage:21,cooldown:1.4,projectiles:2,model:'artifact'},
 {id:'quakes',name:'Gravestone Hammer',icon:'⚒',rarity:'uncommon',desc:'Shockwaves erupt from the earth and knock enemies back.',color:0xe4b47b,damage:41,cooldown:3.1,projectiles:1,model:'hammer_common'},
 {id:'wyrmfire',name:'Dragonbreath',icon:'♨',rarity:'rare',desc:'A huge conical blast of embers and dragon fire.',color:0xff6747,damage:16,cooldown:1.7,projectiles:9,model:'staff_rare'},
 {id:'thorn',name:'Thornstorm',icon:'❋',rarity:'uncommon',desc:'Rotating thorn blades form a defensive wall.',color:0x98db83,damage:15,cooldown:0,projectiles:3,model:'axe_rare'},
 {id:'hexbolt',name:'Hex Repeater',icon:'⌁',rarity:'uncommon',desc:'A high velocity triple cursed projectile stream.',color:0xe194ff,damage:18,cooldown:.63,projectiles:3,model:'staff_common'},
 {id:'fuse',name:'Powder Keg',icon:'✹',rarity:'rare',desc:'Exploding cursed barrels detonate across the battlefield.',color:0xffb65d,damage:58,cooldown:3.6,projectiles:1,model:'barrelDark'},
];
export const V3_RELICS=[
 {id:'meteorstorm',name:'Meteor Storm',icon:'☄',cooldown:27,desc:'Rain explosive meteors onto the 12 nearest enemies.'},
 {id:'timewarp',name:'Chrono Rift',icon:'⌛',cooldown:28,desc:'Greatly slows nearby monsters for eight seconds.'},
 {id:'earthshatter',name:'Earthshatter',icon:'⚒',cooldown:23,desc:'Powerful circular ground slam and knockback.'},
 {id:'phoenix',name:'Phoenix Rebirth',icon:'♨',cooldown:36,desc:'Heal and ignite all surrounding enemies.'},
 {id:'reaper',name:'Reaper’s Mark',icon:'☠',cooldown:32,desc:'Deal devastating damage to the toughest nearby targets.'},
 {id:'mushroom',name:'Spore Cloud',icon:'☣',cooldown:19,desc:'A poisonous mist that slows the entire horde.'}
];
export const V3_EVOLUTIONS=[
 {weapon:'crossbow',passive:'crit',name:'Eclipse Ballista',effect:'Heavy spectral piercing bolts'},
 {weapon:'meteor',passive:'area',name:'Heavenfall Cataclysm',effect:'Meteor showers and huge eruptions'},
 {weapon:'chakram',passive:'haste',name:'Moonblade Cyclone',effect:'Massive rotating cutting discs'},
 {weapon:'crystal',passive:'focus',name:'Prismatic Apocalypse',effect:'Crystal shotgun fusillades'},
 {weapon:'sunbow',passive:'might',name:'Solar Judgment',effect:'Triple scorching rays'},
 {weapon:'widow',passive:'crit',name:'Venomous Kiss',effect:'Rapid empowered daggers'},
 {weapon:'spirits',passive:'magnet',name:'Spectral Legion',effect:'An army of wraith spirits'},
 {weapon:'quakes',passive:'vitality',name:'Worldbreaker',effect:'Larger earthquaking pulses'},
 {weapon:'wyrmfire',passive:'area',name:'Infernal Tempest',effect:'Wide cone of dragon fire'},
 {weapon:'thorn',passive:'armor',name:'Briar Crown',effect:'Expanded thorn circle'},
 {weapon:'hexbolt',passive:'haste',name:'Arcane Minigun',effect:'Rapid enchanted bullet storms'},
 {weapon:'fuse',passive:'fortune',name:'Cataclysm Kegs',effect:'Exploding barrels across the map'}
];
export const CHEST_REWARDS=[
 {id:'coins',name:'Gold Cache',color:0xffd37d,detail:'+100 coins and a burst of souls'},
 {id:'heal',name:'Sanctuary Flask',color:0x83e9b5,detail:'Restore health and recharge your relic'},
 {id:'xp',name:'Soul Reservoir',color:0xb994ff,detail:'Gain a huge amount of run XP'},
 {id:'weapon',name:'Arcane Catalyst',color:0x8fd9ff,detail:'Upgrade one owned weapon'},
 {id:'legendary',name:'Legendary Reliquary',color:0xffae53,detail:'Upgrade two weapons and gain a relic charge'}
];
