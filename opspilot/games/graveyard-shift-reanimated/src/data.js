import {V3_WEAPONS,V3_RELICS,V3_EVOLUTIONS} from './v3-content.js';
export const CHARACTERS = [
 {id:'arbalist',name:'Dusk Arbalist',role:'Marksman',model:'Ranger',icon:'➶',blurb:'Every arrow is a whispered goodbye.',weapon:'crossbow',hp:115,speed:5.5,damage:1.05,armor:1,skill:'Piercing Aim',passive:'Piercing spectral arrows.',unlock:0},
 {id:'starwitch',name:'Star Witch',role:'Meteor Mage',model:'Mage',icon:'☄',blurb:'The stars obey the last witch of midnight.',weapon:'meteor',hp:90,speed:5,damage:1.24,armor:0,skill:'Falling Stars',passive:'Meteor mastery and strong area damage.',unlock:3},
 {id:'bladedancer',name:'Moon Dancer',role:'Blademaster',model:'Rogue',icon:'◈',blurb:'A crescent of steel in the darkness.',weapon:'chakram',hp:111,speed:6.1,damage:1.1,armor:1,skill:'Blade Storm',passive:'Fast, piercing moon blades.',unlock:4},
 {id:'firedrake',name:'Cinder Herald',role:'Pyromancer',model:'Barbarian',icon:'♨',blurb:'The fire never learned mercy.',weapon:'wyrmfire',hp:128,speed:4.9,damage:1.14,armor:2,skill:'Infernal Breath',passive:'Scatter fire across an entire wave.',unlock:5},
 {id:'briar',name:'Briar Knight',role:'Guardian',model:'Knight',icon:'❋',blurb:'A walking fortress of living thorns.',weapon:'thorn',hp:172,speed:4.65,damage:1,armor:4,skill:'Thorn Crown',passive:'Orbiting defenses protect allies.',unlock:6},
 {id:'warlock',name:'Hex Gunner',role:'Spellshot',model:'Rogue_Hooded',icon:'⌁',blurb:'Runes, repeaters, and relentless fire.',weapon:'hexbolt',hp:98,speed:5.6,damage:1.22,armor:0,skill:'Hex Machine',passive:'Fast-fire magic bolts.',unlock:8},
 {id:'warden',name:'The Warden',role:'Survivor',model:'Knight',icon:'⚔',blurb:'Armor, resolve, and a sword that never rests.',weapon:'boneblades',hp:145,speed:5,damage:1,armor:3,skill:'Iron Will',passive:'Take 12% less damage.',unlock:0},
 {id:'hex',name:'Hex Weaver',role:'Arcanist',model:'Mage',icon:'✦',blurb:'Turns dark energy into beautiful destruction.',weapon:'ember',hp:90,speed:5.2,damage:1.2,armor:0,skill:'Arcane Hunger',passive:'12% more XP and spell damage.',unlock:0},
 {id:'ranger',name:'Night Ranger',role:'Hunter',model:'Ranger',icon:'➶',blurb:'Never outnumbered when arrows fly.',weapon:'shrapnel',hp:110,speed:5.6,damage:1.04,armor:1,skill:'Quickdraw',passive:'15% faster weapon cooldowns.',unlock:0},
 {id:'shade',name:'The Shade',role:'Assassin',model:'Rogue_Hooded',icon:'◈',blurb:'A whisper behind every enemy.',weapon:'voidlance',hp:92,speed:6.1,damage:1.15,armor:0,skill:'Ghost Step',passive:'15% faster movement.',unlock:3},
 {id:'bruiser',name:'Gravedigger',role:'Brawler',model:'Barbarian',icon:'⚒',blurb:'More monster than the monsters.',weapon:'scythe',hp:180,speed:4.6,damage:1.17,armor:4,skill:'Last Stand',passive:'+25% maximum HP.',unlock:4},
 {id:'alchemist',name:'Plague Doctor',role:'Scientist',model:'Mage',icon:'☣',blurb:'A cure for everything except curiosity.',weapon:'spores',hp:100,speed:5,damage:1.08,armor:1,skill:'Toxicology',passive:'Poison and area attacks are 18% stronger.',unlock:5},
 {id:'hacker',name:'Ghost Protocol',role:'Technomancer',model:'Rogue',icon:'⌘',blurb:'Unauthorized access to the afterlife.',weapon:'drone',hp:105,speed:5.35,damage:1.08,armor:0,skill:'Overclock',passive:'+15% projectile speed.',unlock:6},
 {id:'paladin',name:'Dawnbringer',role:'Templar',model:'Knight',icon:'☼',blurb:'Light is a weapon after midnight.',weapon:'nova',hp:135,speed:4.95,damage:1.08,armor:3,skill:'Second Sunrise',passive:'Regenerate 0.35 HP/s.',unlock:8},
 {id:'reaper',name:'The Reaper',role:'Harvester',model:'Rogue_Hooded',icon:'☠',blurb:'The grave finally learned to walk.',weapon:'orbit',hp:112,speed:5.5,damage:1.18,armor:1,skill:'Soul Collector',passive:'Earn 15% more souls per run.',unlock:10},
 {id:'storm',name:'Stormcaller',role:'Conduit',model:'Ranger',icon:'ϟ',blurb:'A thunderstorm wearing a human disguise.',weapon:'coil',hp:100,speed:5.15,damage:1.17,armor:0,skill:'Static Charge',passive:'Lightning chains to an additional target.',unlock:12}
];
export const MUTATORS = [
 {id:'standard',name:'Classic Shift',icon:'☽',detail:'The intended 12-minute survival experience.',reward:1,spawn:1,enemySpeed:1,playerDamage:1,playerHp:1},
 {id:'nightmare',name:'Nightmare Mode',icon:'☠',detail:'More enemies, faster pursuit, bigger rewards.',reward:1.5,spawn:1.6,enemySpeed:1.2,playerDamage:1,playerHp:1},
 {id:'glass',name:'Glass Cannon',icon:'✹',detail:'Deal 40% more damage, but start with 40% less health.',reward:1.25,spawn:1,enemySpeed:1,playerDamage:1.4,playerHp:.6},
 {id:'turbo',name:'Turbo Shift',icon:'ϟ',detail:'Accelerated movement and enemy swarms.',reward:1.2,spawn:1.3,enemySpeed:1.15,playerDamage:1,playerHp:1}
];
export const SKINS = [
 {id:'default',name:'Original',hex:'#3fd3e8',unlock:0},
 {id:'crimson',name:'Blood Moon',hex:'#ef627b',unlock:0},
 {id:'specter',name:'Specter',hex:'#91f5e7',unlock:2},
 {id:'royal',name:'Royal',hex:'#e8bd72',unlock:3},
 {id:'void',name:'Voidwalker',hex:'#ad88ff',unlock:4},
 {id:'toxic',name:'Biohazard',hex:'#a7ed79',unlock:5},
 {id:'frost',name:'Frostbound',hex:'#89c9ff',unlock:6},
 {id:'ember',name:'Infernal',hex:'#ff955b',unlock:8},
 {id:'pumpkin',name:'Jack-o-Lantern',hex:'#ff7a1a',unlock:0},
 {id:'wraith',name:'Wraith',hex:'#e2fff2',unlock:0}
];
// Pre-run blessings — pick one before every run for an instant build-defining edge.
export const BOONS = [
 {id:'fury',name:'Oath of Fury',icon:'⚔',desc:'+25% weapon damage for the whole run.'},
 {id:'fleet',name:'Fleet Spirit',icon:'➤',desc:'+15% movement speed — kite the horde with ease.'},
 {id:'bulwark',name:'Grave Bulwark',icon:'❖',desc:'+25% maximum health, fully healed.'},
 {id:'leech',name:'Blood Pact',icon:'✚',desc:'Lifesteal: heal for a sliver of all damage you deal.'},
 {id:'arsenal',name:'Hidden Arsenal',icon:'✦',desc:'Begin the run with a second random weapon.'},
 {id:'seer',name:'Eye of the Seer',icon:'◉',desc:'Start with +2 rerolls and +1 banish on level-ups.'},
 {id:'fortune',name:"Reaper's Fortune",icon:'◈',desc:'+35% coins and XP gained all run long.'},
];
export const MAPS = [
 {id:'cemetery',name:'Forgotten Cemetery',subtitle:'Where every shadow remembers.',icon:'☽',color:0x111b27,fog:0x101923,accent:'#7cd7bf',unlock:0},
 {id:'village',name:'The Forsaken Village',subtitle:'The bells stopped ringing years ago.',icon:'⌂',color:0x201b28,fog:0x201728,accent:'#e4a76e',unlock:3},
 {id:'facility',name:'Sector 13',subtitle:'Experiment terminated. Subjects remain.',icon:'⌬',color:0x0d2029,fog:0x0c1c25,accent:'#67d4ef',unlock:7},
 {id:'crypt',name:'The Sunken Crypt',subtitle:'Drowned halls where the tide never recedes.',icon:'⚱',color:0x0a1822,fog:0x081620,accent:'#5fb8d6',unlock:10},
 {id:'inferno',name:'Ashfall Reach',subtitle:'The furnace at the end of the shift.',icon:'♨',color:0x241009,fog:0x1e0b06,accent:'#ff8a4a',unlock:14},
 {id:'moor',name:'The Howling Moor',subtitle:'Wind, fog, and things that hunt in it.',icon:'☁',color:0x151c20,fog:0x121a1e,accent:'#9fb4c0',unlock:18},
 {id:'sanctum',name:'The Fallen Sanctum',subtitle:'Hallowed ground the dead reclaimed.',icon:'✠',color:0x1a1520,fog:0x15101c,accent:'#c6a0ff',unlock:22}
];
export const WEAPONS = [
 ...V3_WEAPONS,
 {id:'boneblades',name:'Bone Blades',icon:'⚔',rarity:'common',desc:'Seeking blades cut into the closest foes.',color:0xe1e8fa,damage:19,cooldown:1.05,projectiles:1},
 {id:'ember',name:'Ember Wand',icon:'✦',rarity:'common',desc:'Homing firebolts ignite the undead.',color:0xff9751,damage:17,cooldown:.82,projectiles:1},
 {id:'shrapnel',name:'Grave Scattergun',icon:'✹',rarity:'common',desc:'A brutal close-range cone of pellets.',color:0xf0c878,damage:12,cooldown:1.65,projectiles:5},
 {id:'voidlance',name:'Void Lance',icon:'◇',rarity:'uncommon',desc:'Piercing blasts tear through lines.',color:0x996eff,damage:23,cooldown:1.8,projectiles:1},
 {id:'tempest',name:'Storm Tempest',icon:'✺',rarity:'rare',desc:'Unleashes a full ring of crackling bolts in every direction.',color:0x7ec8ff,damage:18,cooldown:1.55,projectiles:10},
 {id:'starfall',name:'Starfall',icon:'☄',rarity:'epic',desc:'Calls a rain of blazing meteors crashing down around you.',color:0xffb14a,damage:30,cooldown:2.45,projectiles:3},
 {id:'scythe',name:'Spectral Scythe',icon:'☾',rarity:'uncommon',desc:'Cleave the crowd in a wide arc.',color:0xb5f4c1,damage:29,cooldown:2.15,projectiles:1},
 {id:'spores',name:'Plague Spores',icon:'☣',rarity:'uncommon',desc:'Poison all creatures nearby.',color:0x9cde67,damage:10,cooldown:2.2,projectiles:1},
 {id:'drone',name:'Sentry Drone',icon:'⌘',rarity:'rare',desc:'A clockwork ally attacks your enemies.',color:0x76deef,damage:13,cooldown:.75,projectiles:1},
 {id:'nova',name:'Solar Nova',icon:'☼',rarity:'rare',desc:'A radiant burst blows enemies away.',color:0xffe69e,damage:28,cooldown:4,projectiles:1},
 {id:'orbit',name:'Reaper Halo',icon:'◎',rarity:'uncommon',desc:'Orbiting blades shred nearby foes.',color:0xcf8cfc,damage:10,cooldown:0,projectiles:2},
 {id:'coil',name:'Arc Coil',icon:'ϟ',rarity:'rare',desc:'Lightning chains between multiple targets.',color:0x79c4ff,damage:17,cooldown:1.75,projectiles:3},
 {id:'frost',name:'Frozen Heart',icon:'❄',rarity:'uncommon',desc:'An icy ring slows approaching monsters.',color:0x90e8ff,damage:14,cooldown:3.3,projectiles:1},
 {id:'mines',name:'Soul Mines',icon:'✣',rarity:'common',desc:'Explosive traps punish the horde.',color:0xd8a5ff,damage:40,cooldown:3.9,projectiles:1},
 {id:'ravens',name:'Raven Swarm',icon:'❖',rarity:'rare',desc:'Summoned ravens dive at nearby enemies.',color:0xc3bcf3,damage:19,cooldown:1.6,projectiles:2},
 {id:'blood',name:'Blood Pact',icon:'♥',rarity:'rare',desc:'Steal life with vampiric bolts.',color:0xf66f91,damage:16,cooldown:1.3,projectiles:1}
];
export const PASSIVES = [
 {id:'might',name:'Giant Slayer',icon:'⚒',desc:'+10% weapon damage per rank.',max:12},
 {id:'haste',name:'Quick Hands',icon:'ϟ',desc:'8% shorter cooldowns per rank.',max:12},
 {id:'vitality',name:'Thick Skin',icon:'♥',desc:'+20 maximum HP per rank.',max:12},
 {id:'magnet',name:'Soul Magnet',icon:'◎',desc:'+25% pickup radius per rank.',max:12},
 {id:'boots',name:'Night Runner',icon:'➤',desc:'+8% movement speed per rank.',max:12},
 {id:'fortune',name:'Lucky Bones',icon:'✦',desc:'+12% gold per rank.',max:12},
 {id:'focus',name:'Scholar',icon:'✧',desc:'+10% XP per rank.',max:12},
 {id:'armor',name:'Iron Bark',icon:'⬡',desc:'Reduce damage taken by 1 per rank.',max:12},
 {id:'regen',name:'Rebirth',icon:'✚',desc:'Regain 0.3 HP/second per rank.',max:12},
 {id:'area',name:'Abyssal Reach',icon:'◉',desc:'+12% attack area per rank.',max:12},
 {id:'crit',name:'Keen Edge',icon:'⚔',desc:'+5% critical chance per rank.',max:12},
 {id:'greed',name:'Grave Robber',icon:'◆',desc:'+10% soul rewards per rank.',max:12}
];
export const EVOLUTIONS = [
 ...V3_EVOLUTIONS,
 {weapon:'boneblades',passive:'might',name:'Ossuary Requiem',effect:'Double seeking blades'},
 {weapon:'ember',passive:'focus',name:'Inferno Codex',effect:'Rapid burning salvos'},
 {weapon:'shrapnel',passive:'haste',name:'Midnight Barrage',effect:'Huge shotgun volley'},
 {weapon:'orbit',passive:'area',name:'Crown of Thorns',effect:'Massive spinning halo'},
 {weapon:'coil',passive:'crit',name:'Thunder Judgment',effect:'Lightning storms'},
 {weapon:'frost',passive:'regen',name:'Absolute Zero',effect:'Glacial burst'},
 {weapon:'scythe',passive:'vitality',name:'Harvest Moon',effect:'Devastating cleaves'},
 {weapon:'blood',passive:'magnet',name:'Crimson Covenant',effect:'Vampiric volleys'}
];
export const META = [
 {id:'power',name:'Weapon Mastery',icon:'⚔',desc:'+4% permanent damage per rank',max:20,base:70},
 {id:'health',name:'Body Armor',icon:'♥',desc:'+8 maximum HP per rank',max:20,base:50},
 {id:'speed',name:'Sprint Training',icon:'➤',desc:'+1.5% speed per rank',max:20,base:60},
 {id:'magnet',name:'Gravitation',icon:'◎',desc:'+6% XP pickup radius per rank',max:20,base:60},
 {id:'luck',name:'Fortune Finder',icon:'◆',desc:'+3% coins and souls per rank',max:20,base:90},
 {id:'resilience',name:'Second Chances',icon:'✚',desc:'+0.08 HP regen per second per rank',max:20,base:80}
];
export const ACHIEVEMENTS = [
 {id:'first',name:'First Blood',desc:'Defeat 1 enemy',reward:25},
 {id:'hundred',name:'Crowd Control',desc:'Defeat 100 enemies in a run',reward:75},
 {id:'fivehundred',name:'No Vacancy',desc:'Defeat 500 enemies in a run',reward:180},
 {id:'minutes',name:'Night Watch',desc:'Survive 5 minutes',reward:120},
 {id:'boss',name:'Head Hunter',desc:'Slay a boss',reward:150},
 {id:'victory',name:'Dawn Survivor',desc:'Survive the full night',reward:500},
 {id:'evolved',name:'Transcendence',desc:'Evolve a weapon',reward:150},
 {id:'collector',name:'Curator',desc:'Unlock 5 characters',reward:300}
];
export const findWeapon=id=>WEAPONS.find(w=>w.id===id);
export const findPassive=id=>PASSIVES.find(p=>p.id===id);
export const levelRequired=level=>Math.floor(12+level*6+level**1.38*2.5);
export const accountLevel=xp=>Math.floor(1+Math.sqrt(Math.max(0,xp)/140));
export const metaPrice=(upgrade,rank)=>Math.floor(upgrade.base * (rank+1)**1.6);

// Real, selectable E-slot abilities, with individual cooldowns.
export const RELICS=[
 ...V3_RELICS,
 {id:'nightfall',name:'Nightfall Burst',icon:'☀',cooldown:24,desc:'Expanding radiant shockwave. High damage and enormous knockback.'},
 {id:'frostbite',name:'Winter Veil',icon:'❄',cooldown:19,desc:'Freeze the crowd around you; slow enemies for six seconds.'},
 {id:'bloodwell',name:'Bloodwell',icon:'♥',cooldown:25,desc:'Sacrifice enemy health to heal yourself, then gain temporary armor.'},
 {id:'thunder',name:'Thunder Crown',icon:'ϟ',cooldown:21,desc:'Chain lightning lashes up to sixteen nearby enemies.'},
 {id:'sanctuary',name:'Sanctuary',icon:'✦',cooldown:28,desc:'Gain five seconds of immunity and a small emergency heal.'},
 {id:'gravity',name:'Void Singularity',icon:'◉',cooldown:22,desc:'Drag surrounding enemies inward, then detonate the singularity.'}
];
