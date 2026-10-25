// All world geometry and spawn locations are canonical on the server.
export const WIDTH=132, HEIGHT=94, TILE=32;
export const START={x:24.5,y:33.5};
export const places=[
 {name:'PINEBELL',sub:'Town of little miracles',x:24,y:33,r:17,color:'#f7b9ce'},
 {name:'MOONBERRY GROVE',sub:'Where the trees hum',x:64,y:18,r:13,color:'#caa7ff'},
 {name:'SODA SHORE',sub:'A seaside of sweet surprises',x:77,y:53,r:14,color:'#80e7ff'},
 {name:'NEON BOARDWALK',sub:'Arcade lights and impossible games',x:106,y:23,r:16,color:'#fa80db'},
 {name:'THE SPARK YARD',sub:'Friendly duels, zero stakes',x:109,y:47,r:15,color:'#ffb25b'},
 {name:'CASSETTE COMMONS',sub:'Make a place of your own',x:105,y:75,r:17,color:'#94e5e4'}
];
export const houses=[
 {x:10,y:21,w:7,h:6,kind:'pink',name:'Poppy Residence'},
 {x:23,y:20,w:7,h:6,kind:'blue',name:'Starlight House'},
 {x:35,y:21,w:7,h:6,kind:'yellow',name:'Mothlight Mercantile'},
 {x:12,y:39,w:7,h:6,kind:'mint',name:'Dreamer Cottage'},
 {x:32,y:41,w:8,h:6,kind:'lilac',name:'Pinebell Library'},
 {x:56,y:10,w:7,h:6,kind:'lilac',name:'Mushroom Museum'},
 {x:73,y:12,w:8,h:6,kind:'mint',name:'The Moonberry Inn'},
 {x:63,y:47,w:7,h:6,kind:'yellow',name:'Sunpop Snacks'},
 {x:75,y:45,w:7,h:6,kind:'pink',name:'The Soda Hotel'},
 {x:67,y:58,w:8,h:6,kind:'blue',name:'Coastal Post'},
 {x:99,y:13,w:8,h:6,kind:'pink',name:'Circuit Carnival'},
 {x:112,y:19,w:8,h:6,kind:'blue',name:'Neon Noodle Club'},
 {x:97,y:68,w:8,h:6,kind:'mint',name:'Casette House Studio'},
 {x:112,y:74,w:8,h:6,kind:'lilac',name:'House of Oddities'}
];
export const signalNodes=[
 {id:'pine-tower',x:29.5,y:37.5,name:'Pinebell Radio',wave:'A broadcast of laughter'},
 {id:'grove-tower',x:65.5,y:27.5,name:'Moonberry Frequency',wave:'A lullaby from the trees'},
 {id:'shore-tower',x:82.5,y:55.5,name:'Soda Shore Station',wave:'The sound of the tide'},
 {id:'neon-tower',x:111.5,y:32.5,name:'Neon Midnight',wave:'The arcade is still awake'},
 {id:'yard-tower',x:104.5,y:57.5,name:'The Spark Station',wave:'A friendly victory jingle'},
 {id:'commons-tower',x:109.5,y:80.5,name:'Cassette Commons',wave:'A song from home'}
];
export const chests=[
 {id:'pinebell-gift',x:30.5,y:38.5,tier:1},{id:'wildway-cache',x:48.5,y:34.5,tier:2},
 {id:'grove-relic',x:54.5,y:27.5,tier:3},{id:'moonberry-gift',x:69.5,y:25.5,tier:3},
 {id:'shore-treasure',x:76.5,y:40.5,tier:4},{id:'pier-parcel',x:83.5,y:54.5,tier:4},
 {id:'arcade-stash',x:112.5,y:28.5,tier:4},{id:'yard-supply',x:102.5,y:60.5,tier:3},
 {id:'commons-timecapsule',x:120.5,y:81.5,tier:5},{id:'moon-woods',x:57.5,y:6.5,tier:5}
];
export const npcs=[
 {id:'pip',name:'Uncle Pip',role:'Quest Giver',x:25.5,y:30.5,palette:1,dialogue:["Shhh... hear that? Exactly. The world is losing its music.","Six radio towers are broadcasting broken songs. Tune any three and recover the Lost Mixtape! No fighting needed."],quest:true},
 {id:'mira',name:'Mira',role:'Mothlight Shop',x:38.5,y:29.5,palette:3,dialogue:["Hey, superstar! A good backpack is a life philosophy.","Come on in. I’ve got snacks, gear and a very questionable warranty."],shop:true},
 {id:'juno',name:'Juno',role:'The Stargazer',x:17.5,y:34.5,palette:2,dialogue:["I wrote a wish on a paper airplane and it flew straight into the moon.","The Moonberry Grove lies northeast. Bring comfortable shoes."]},
 {id:'ziggy',name:'Ziggy',role:'Town DJ',x:23.5,y:39.5,palette:4,dialogue:["The beat is not dead. The beat is just... buffering.","Press F for your Echo Burst when things get crowded. You’re welcome!"]},
 {id:'dottie',name:'Dottie',role:'Librarian',x:37.5,y:48.5,palette:5,dialogue:["Long ago, seven bells kept our world awake.","The strange broadcasts are connected. Can you hear the signal hiding in the static?"]},
 {id:'nix',name:'Nix',role:'Grove Keeper',x:67.5,y:23.5,palette:2,dialogue:["The trees here whisper in key. Or at least they used to.","An enormous Hushling lurks beyond the grove. Its silence is rather rude."],quest:true},
 {id:'oliver',name:'Oliver',role:'Soda Vendor',x:67.5,y:55.5,palette:1,dialogue:["You made it to Soda Shore! Where every day tastes like Saturday.","Psst... head east for a gorgeous view of the water."]},
 {id:'tess',name:'Tess',role:'Coastal Mechanic',x:78.5,y:55.5,palette:4,dialogue:["Everything here runs on optimism and spare parts.","The world used to hum. We can fix that, right?"]},
 {id:'orbit',name:'Orbit',role:'Arcade Host',x:104.5,y:26.5,palette:3,dialogue:["The highest score is the number of friends you made. Corny? Yes. Correct? Also yes.","The Memory Jam machine is free to play!"]},
 {id:'switch',name:'Switch',role:'Dungeon Guide',x:54.5,y:31.5,palette:5,dialogue:["Three Rifts. Three weird problems. One excellent team.","Bring friends to the portal, or dive in solo if you are feeling spicy."]},
 {id:'coach',name:'Coach Bit',role:'PvP Referee',x:103.5,y:48.5,palette:2,dialogue:["Sparring is voluntary. It's not a license to bother anyone.","Everyone fights on even footing, and nobody loses their belongings."]},
 {id:'tilly',name:'Tilly',role:'Home Agent',x:107.5,y:73.5,palette:0,dialogue:["A home is where you leave that one sock you swear you will find later.","Buy your own room, then decorate however you like!"]},
 {id:'pixel',name:'Pixel',role:'Fishing Pal',x:81.5,y:57.5,palette:1,dialogue:["Soda Shore fish are made of pixels, not cola. Probably.","Try the fishing challenge right here on the pier."]},
 {id:'reed',name:'Reed',role:'Neighborhood DJ',x:110.5,y:78.5,palette:4,dialogue:["A new song, a new signal, a new friend.","The quietest corners are often the most interesting."]}
];
// Defined on a logical-grid coordinate system. The same collision is enforced server-side.
const hash=(x,y,s=0)=>{let n=(x*374761393+y*668265263+s*1274126177)|0;n=Math.imul(n^(n>>>13),1274126177);return ((n^(n>>>16))>>>0)/4294967295;};
const grass=()=>Array.from({length:HEIGHT},()=>Array(WIDTH).fill(0));
export function generateMap(){
 const g=grass();
 for(let y=0;y<HEIGHT;y++)for(let x=0;x<WIDTH;x++){
  if(x<2||y<2||x>WIDTH-3||y>HEIGHT-3)g[y][x]=4;
  else if(x>=86&&x<=96&&y>=38&&y<=69)g[y][x]=3;
  else if((x>=82&&x<=96&&y>=42&&hash(x,y,5)>.65)||(x>=84&&x<=96&&y>=36&&y<=69))g[y][x]=3;
  else if(y>60&&x>54&&hash(x,y,7)>.45)g[y][x]=2;
  else g[y][x]=0;
 }
 const lay=(x1,y1,x2,y2,type)=>{for(let y=y1;y<=y2;y++)for(let x=x1;x<=x2;x++)if(y>=2&&y<HEIGHT-2&&x>=2&&x<WIDTH-2)g[y][x]=type;};
 // Connecting roads give the world a sense of scale and ensure real routes between towns.
 lay(7,30,45,36,1);lay(21,25,27,42,1);lay(35,25,40,47,1);lay(13,45,38,48,1);
 lay(44,32,73,35,1);lay(52,20,57,35,1);lay(52,18,78,21,1);lay(63,20,69,29,1);
 lay(73,32,77,56,1);lay(63,53,85,58,1);lay(74,51,81,54,1);
 // East expansion: arcades, an opt-in duel court, neighborhoods, and interconnected trails.
 lay(77,31,112,34,1);lay(103,21,110,38,1);lay(102,19,120,22,1);
 lay(98,39,119,58,6);lay(101,36,114,40,1);lay(105,56,110,78,1);
 lay(95,72,123,80,1);lay(96,69,122,71,1);
 lay(81,53,99,55,1);lay(95,54,105,58,1);
 lay(106,42,116,53,6);
 lay(99,24,117,29,5);lay(100,74,121,78,5);
 // Sand beaches, a pier and small decorative cobblestone town square.
 lay(81,37,85,66,2);lay(84,53,91,55,5);lay(86,53,103,55,1);
 lay(19,31,30,35,5);lay(60,18,72,21,5);
 for(const h of houses){lay(h.x-1,h.y+h.h,h.x+h.w,h.y+h.h+1,1);}
 // Park ponds (walkable tile 2 indicates sand; water 3 is blocked).
 for(let y=10;y<17;y++)for(let x=12;x<22;x++)if(((x-17)**2)/30+((y-13)**2)/9<1)g[y][x]=3;
 for(let y=54;y<60;y++)for(let x=9;x<17;x++)if(((x-13)**2)/17+((y-57)**2)/7<1)g[y][x]=3;
 // Trees are generated deterministically, visible to all players and solid.
 const trees=[];
 for(let y=4;y<HEIGHT-4;y++)for(let x=4;x<WIDTH-4;x++){
  if(g[y][x]!==0)continue;
  const near=(x>6&&x<45&&y>17&&y<50)||(x>48&&x<80&&y>9&&y<29)||(x>59&&x<83&&y>43&&y<64)||(x>98&&x<126&&y>10&&y<84);
  const chance=near?.035:.145;
  if(hash(x,y,19)<chance && hash(x,y,38)>.09)trees.push({x,y,variant:Math.floor(hash(x,y,77)*4)});
 }
 const blocked=new Set();
 for(let y=0;y<HEIGHT;y++)for(let x=0;x<WIDTH;x++)if(g[y][x]===3||g[y][x]===4)blocked.add(x+','+y);
 for(const h of houses)for(let y=h.y;y<h.y+h.h;y++)for(let x=h.x;x<h.x+h.w;x++)blocked.add(x+','+y);
 for(const t of trees)blocked.add(t.x+','+t.y);
 for(const npc of npcs)blocked.delete(Math.floor(npc.x)+','+Math.floor(npc.y));
 const safe=(x,y)=>!blocked.has(Math.floor(x)+','+Math.floor(y)) && x>2&&y>2&&x<WIDTH-2&&y<HEIGHT-2;
 return {tiles:g,trees,blocked,safe};
}
export const world=generateMap();
export const mobs=[
 {id:'a1',kind:'sprout',x:45.5,y:27.5,level:2},{id:'a2',kind:'sprout',x:47.5,y:39.5,level:2},
 {id:'a3',kind:'sprout',x:49.5,y:24.5,level:2},{id:'a4',kind:'sprout',x:43.5,y:47.5,level:2},
 {id:'a5',kind:'sprout',x:48.5,y:47.5,level:2},{id:'a6',kind:'sprout',x:53.5,y:40.5,level:2},
 {id:'b1',kind:'mop',x:8.5,y:49.5,level:1},{id:'b2',kind:'mop',x:32.5,y:56.5,level:1},
 {id:'b3',kind:'mop',x:17.5,y:52.5,level:1},{id:'b4',kind:'mop',x:46.5,y:16.5,level:1},
 {id:'c1',kind:'gremlin',x:61.5,y:30.5,level:4},{id:'c2',kind:'gremlin',x:68.5,y:36.5,level:4},
 {id:'c3',kind:'gremlin',x:55.5,y:49.5,level:4},{id:'c4',kind:'gremlin',x:78.5,y:36.5,level:4},
 {id:'d1',kind:'wisp',x:50.5,y:8.5,level:6},{id:'d2',kind:'wisp',x:69.5,y:8.5,level:6},
 {id:'d3',kind:'wisp',x:81.5,y:27.5,level:6},{id:'d4',kind:'wisp',x:86.5,y:27.5,level:6},
 {id:'boss1',kind:'hushling',x:80.5,y:9.5,level:10,boss:true},
 {id:'n1',kind:'glitch',x:105.5,y:32.5,level:5},{id:'n2',kind:'glitch',x:116.5,y:33.5,level:5},
 {id:'n3',kind:'glitch',x:121.5,y:25.5,level:5},{id:'n4',kind:'glitch',x:98.5,y:29.5,level:5},
 {id:'h1',kind:'bopper',x:98.5,y:63.5,level:7},{id:'h2',kind:'bopper',x:121.5,y:62.5,level:7},
 {id:'h3',kind:'bopper',x:124.5,y:84.5,level:7},{id:'h4',kind:'bopper',x:92.5,y:83.5,level:7}
];
export const mobDefs={
 sprout:{name:'Static Sprout',maxHp:35,atk:5,def:1,xp:18,coins:[3,9],speed:.7,range:5},
 mop:{name:'Mothmop',maxHp:26,atk:4,def:0,xp:12,coins:[2,6],speed:.5,range:4},
 gremlin:{name:'Gumdrop Gremlin',maxHp:68,atk:10,def:3,xp:43,coins:[8,18],speed:.75,range:6},
 wisp:{name:'Lantern Wisp',maxHp:100,atk:14,def:5,xp:65,coins:[11,27],speed:.9,range:7},
 hushling:{name:'The Hushling',maxHp:640,atk:21,def:7,xp:430,coins:[120,220],speed:.58,range:8},
 glitch:{name:'Glitch Jelly',maxHp:92,atk:10,def:4,xp:42,coins:[8,14],speed:.9,range:5},
 bopper:{name:'Cassette Bopper',maxHp:128,atk:13,def:6,xp:61,coins:[11,20],speed:.8,range:5},
 riftling:{name:'Lost Frequency',maxHp:120,atk:14,def:5,xp:56,coins:[10,19],speed:1,range:9},
 riftboss:{name:'The Feedback King',maxHp:420,atk:24,def:9,xp:270,coins:[90,140],speed:.8,range:9}
};
export const items={
 'fizzy-pop':{id:'fizzy-pop',name:'Fizzy Pop',icon:'🥤',rarity:'common',slot:'consumable',heal:45,price:25,description:'A bubbly pick-me-up. Restores 45 HP.'},
 'moon-candy':{id:'moon-candy',name:'Moon Candy',icon:'🍬',rarity:'uncommon',slot:'consumable',heal:110,price:65,description:'Tastes like a wish. Restores 110 HP.'},
 'stick':{id:'stick',name:'Brave Stick',icon:'🪵',rarity:'common',slot:'weapon',atk:2,price:12,description:'The official stick of doing your best.'},
 'spoon':{id:'spoon',name:'Static Spoon',icon:'🥄',rarity:'uncommon',slot:'weapon',atk:6,price:65,description:'A spoon that hums when danger approaches.'},
 'bat':{id:'bat',name:'Meteor Bat',icon:'🏏',rarity:'rare',slot:'weapon',atk:12,price:230,description:'Made from a very friendly meteor.'},
 'glow-rod':{id:'glow-rod',name:'Glow Rod',icon:'✨',rarity:'epic',slot:'weapon',atk:22,price:950,description:'A tiny constellation on a stick.'},
 'starcaller':{id:'starcaller',name:'Starcaller',icon:'🌟',rarity:'legendary',slot:'weapon',atk:39,price:5000,description:'It remembers a song the stars forgot.'},
 'sweater':{id:'sweater',name:'Lucky Sweater',icon:'🧥',rarity:'common',slot:'armor',def:2,price:30,description:'The heartiest knit in Pinebell.'},
 'vest':{id:'vest',name:'Dandelion Vest',icon:'🌼',rarity:'uncommon',slot:'armor',def:5,price:95,description:'Very fashionable against monsters.'},
 'coat':{id:'coat',name:'Afterglow Coat',icon:'🧥',rarity:'rare',slot:'armor',def:9,price:320,description:'Still warm from yesterday’s sunset.'},
 'aura':{id:'aura',name:'Prism Poncho',icon:'🌈',rarity:'epic',slot:'armor',def:15,price:1300,description:'All the colors agree you look great.'},
 'halo':{id:'halo',name:'Halo Hoodie',icon:'💫',rarity:'legendary',slot:'armor',def:25,price:5400,description:'A wearable pocket sunrise.'},
 'disc':{id:'disc',name:'Chromatic Cassette',icon:'📼',rarity:'rare',slot:'trinket',price:240,description:'A collectible hit from the year that never happened.'},
 'sunglasses':{id:'sunglasses',name:'Neon Shades',icon:'🕶️',rarity:'uncommon',slot:'trinket',price:95,description:'Look cool while making questionable choices.'},
 'antenna':{id:'antenna',name:'Rabbit-Ear Antenna',icon:'📡',rarity:'rare',slot:'weapon',atk:14,price:300,description:'Perfect reception. Questionable ergonomics.'},
 'skateboard':{id:'skateboard',name:'Moon-Flip Board',icon:'🛹',rarity:'epic',slot:'trinket',price:750,description:'For doing kickflips over existential dread.'},
 'vinyl':{id:'vinyl',name:'Midnight Vinyl',icon:'💿',rarity:'epic',slot:'trinket',price:620,description:'A record of the song nobody remembered.'},
 'saber':{id:'saber',name:'Comet Umbrella',icon:'☂️',rarity:'rare',slot:'weapon',atk:16,price:390,description:'A little rain, a lot of stardust.'},
 'megaphone':{id:'megaphone',name:'Thunder Megaphone',icon:'📣',rarity:'epic',slot:'weapon',atk:25,price:1500,description:'Please use your inside voice.'},
 'dreamwire':{id:'dreamwire',name:'Dreamwire Radio',icon:'📻',rarity:'legendary',slot:'weapon',atk:36,price:4900,description:'Tune to something wonderful.'},
 'disco-jacket':{id:'disco-jacket',name:'Disco Jacket',icon:'🪩',rarity:'rare',slot:'armor',def:11,price:330,description:'Every encounter is a dance-off.'},
 'cloudcoat':{id:'cloudcoat',name:'Cloud-Circuit Coat',icon:'☁️',rarity:'epic',slot:'armor',def:17,price:1600,description:'Stormproof and stylish.'},
 'hologram':{id:'hologram',name:'Hologram Hoodie',icon:'🌀',rarity:'legendary',slot:'armor',def:27,price:5300,description:'Never entirely in the same dimension.'},
 'pixel-soda':{id:'pixel-soda',name:'Pixel Pop',icon:'🧃',rarity:'common',slot:'consumable',heal:70,price:42,description:'A crisp square of delicious flavor.'},
 'bot-buddy':{id:'bot-buddy',name:'BOT-01 Companion',icon:'🤖',rarity:'common',slot:'pet',price:75,description:'A tiny floating friend. Purely cosmetic; never gives PvP bonuses.'},
 'pixel-frog':{id:'pixel-frog',name:'Byte Frog',icon:'🐸',rarity:'uncommon',slot:'pet',price:280,description:'Croaks in perfect binary. Cosmetic companion.'},
 'cassette-cat':{id:'cassette-cat',name:'Cassette Cat',icon:'🐈',rarity:'rare',slot:'pet',price:850,description:'A mysterious cat that purrs at 44.1kHz.'},
 'holo-moth':{id:'holo-moth',name:'Hologram Moth',icon:'🦋',rarity:'epic',slot:'pet',price:2900,description:'Its wings play little melodies. Cosmetic only.'},
 'moon-snail':{id:'moon-snail',name:'Moon Snail',icon:'🐌',rarity:'legendary',slot:'pet',price:9999,description:'A gentle companion from the far side of the dial.'},
 'super-snack':{id:'super-snack',name:'Cosmic Bento',icon:'🍱',rarity:'uncommon',slot:'consumable',heal:160,price:115,description:'Noodles from somewhere far away.'}
};
export const lootWeights={common:68,uncommon:21,rare:8,epic:2.6,legendary:.4};
export const lootByRarity={common:['stick','sweater','fizzy-pop','pixel-soda','bot-buddy'],uncommon:['spoon','vest','moon-candy','sunglasses','super-snack','pixel-frog'],rare:['bat','coat','disc','antenna','saber','disco-jacket','cassette-cat'],epic:['glow-rod','aura','skateboard','vinyl','megaphone','cloudcoat','holo-moth'],legendary:['starcaller','halo','dreamwire','hologram','moon-snail']};
export const shopStock=['fizzy-pop','moon-candy','pixel-soda','super-snack','spoon','vest','bat','coat','sunglasses','antenna','bot-buddy'];
