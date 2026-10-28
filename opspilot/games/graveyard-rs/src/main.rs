// BVTech: Graveyard Shift (v2) — an ORIGINAL survivors-like (bullet-heaven),
// Rust -> WebAssembly (macroquad). Everything — art, characters, monsters,
// names — is our own; no other game's assets or code are used. Theme: a big
// moonlit graveyard decked out for Halloween / Día de los Muertos (marigolds,
// candles, papel-picado banners, sugar-skull calaveras). PG-13, cute + spooky.
//
// This version: a much bigger explorable map with 3D props you weave between,
// a JUMP/DODGE leap (with i-frames) so you can hop around and dodge, a dynamic
// chase camera, ~10 weapons (silver bolt, stake volley, holy lantern, rune
// nova, garlic firewall, wisp daemon, scythe sweep, bone spear, chain smite,
// moonbeam), rarity chests with big drops, more enemies + a calavera, timed
// bosses and a final boss, a kill-combo, and a lot more particle juice.

use macroquad::camera::Camera;
use macroquad::prelude::*;

const ARENA: f32 = 64.0;

fn window_conf() -> Conf {
    Conf { window_title: "BVTech: Graveyard Shift".to_owned(), high_dpi: true,
           window_width: 1180, window_height: 760, ..Default::default() }
}

fn col(r: f32, g: f32, b: f32, a: f32) -> Color { Color::new(r, g, b, a) }
fn lerp_col(a: Color, b: Color, t: f32) -> Color {
    Color::new(a.r+(b.r-a.r)*t, a.g+(b.g-a.g)*t, a.b+(b.b-a.b)*t, a.a+(b.a-a.a)*t)
}

// festive palette
const MARIGOLD: Color = Color { r: 1.0, g: 0.62, b: 0.12, a: 1.0 };
const CANDLE: Color = Color { r: 1.0, g: 0.82, b: 0.38, a: 1.0 };
const PAPEL: [Color; 5] = [
    Color { r: 1.0, g: 0.35, b: 0.55, a: 1.0 },   // pink
    Color { r: 0.3, g: 0.85, b: 0.9, a: 1.0 },    // cyan
    Color { r: 1.0, g: 0.82, b: 0.25, a: 1.0 },   // yellow
    Color { r: 0.55, g: 0.85, b: 0.35, a: 1.0 },  // green
    Color { r: 0.7, g: 0.45, b: 0.95, a: 1.0 },   // purple
];

// ---------------- sprites ----------------
fn make_sprite(rows: &[&str], pal: &[(char, Color)]) -> Texture2D {
    let h = rows.len();
    let w = rows.iter().map(|r| r.chars().count()).max().unwrap_or(1);
    let mut img = Image::gen_image_color(w as u16, h as u16, Color::new(0.0, 0.0, 0.0, 0.0));
    for (y, row) in rows.iter().enumerate() {
        for (x, ch) in row.chars().enumerate() {
            if ch == ' ' || ch == '.' { continue; }
            if let Some((_, c)) = pal.iter().find(|(k, _)| *k == ch) {
                img.set_pixel(x as u32, y as u32, *c);
            }
        }
    }
    let t = Texture2D::from_image(&img);
    t.set_filter(FilterMode::Nearest);
    t
}

struct Art {
    hunter: Texture2D, bat: Texture2D, skeleton: Texture2D, ghoul: Texture2D,
    wraith: Texture2D, calavera: Texture2D, boss: Texture2D, fin: Texture2D,
    shard: Texture2D, heart: Texture2D, chest: Texture2D, marigold: Texture2D, cross: Texture2D,
}

fn build_art() -> Art {
    let o = col(0.04, 0.03, 0.06, 1.0);       // outline
    let bone = col(0.95, 0.93, 0.85, 1.0);
    let bone_s = col(0.66, 0.65, 0.58, 1.0);
    let red = col(0.88, 0.16, 0.18, 1.0);
    let cyan = col(0.4, 0.98, 0.98, 1.0);
    let grn = col(0.38, 0.75, 0.32, 1.0);
    let grn_d = col(0.2, 0.45, 0.2, 1.0);
    let cloak = col(0.5, 0.12, 0.18, 1.0);
    let skin = col(0.88, 0.82, 0.72, 1.0);
    let ghost = col(0.74, 0.86, 0.98, 0.9);
    let ghost_d = col(0.46, 0.6, 0.85, 0.72);

    let hunter = make_sprite(&[
        "...oooooo...",
        "..ohhhhhho..",
        ".ohhhhhhhho.",
        "..offffffo..",
        "..ofWffWfo..",
        "..offffffo..",
        ".occcccccco.",
        "occccccccccо",
        "occ cccc cco",
        ".oc cccc co.",
        ".occkkkkcco.",
        ".ock oo kco.",
        ".occ    cco.",
        "..oc    co..",
        "..ob    bo..",
    ], &[('h', col(0.14,0.11,0.16,1.0)), ('f', skin), ('W', col(0.1,0.1,0.1,1.0)),
         ('c', cloak), ('k', CANDLE), ('b', col(0.2,0.16,0.2,1.0)), ('o', o), ('о', o)]);

    let bat = make_sprite(&[
        "oo..........oo",
        "owwo......owwo",
        "owwwwo..owwwwo",
        "owwwwwwwwwwwwo",
        "owwwEwwwwEwwwo",
        ".owwwwwwwwwwo.",
        "..owwowwowwo..",
        "...o.o..o.o...",
    ], &[('w', col(0.33,0.12,0.4,1.0)), ('E', red), ('o', o)]);

    let skeleton = make_sprite(&[
        "..oooo..",
        ".obbbbo.",
        ".obEbEo.",
        ".obbbbo.",
        "..owwo..",
        ".obbbbo.",
        "obsbsbbo",
        "obbbbbbo",
        ".obbbbo.",
        ".ob oo bo",
        ".ob oo bo",
        "obbo obbo",
    ], &[('b', bone), ('s', bone_s), ('E', cyan), ('w', col(0.1,0.1,0.1,1.0)), ('o', o)]);

    let ghoul = make_sprite(&[
        "...oooooo...",
        "..oggggggo..",
        ".ogEggggEgo.",
        ".oggwwwwggo.",
        "oggggggggggo",
        "oggggggggggo",
        "oddggggggddo",
        "od ogggggo do",
        "..oggggggo..",
        ".oggo oggo..",
        ".od o o do..",
    ], &[('g', grn), ('d', grn_d), ('E', col(0.98,0.9,0.3,1.0)), ('w', col(0.08,0.08,0.08,1.0)), ('o', o)]);

    let wraith = make_sprite(&[
        "...oooooo...",
        "..oggggggo..",
        ".ogg oo ggo.",
        ".ogEo oEgо..",
        ".oggggggggo.",
        "oggggggggggo",
        "oggggggggggo",
        "oddddddddddo",
        "ogggggggggо.",
        ".oggo oggo..",
        "..go dd og...",
        "...o do o....",
    ], &[('g', ghost), ('d', ghost_d), ('E', cyan), ('o', o), ('о', o)]);

    // calavera — a cute sugar skull with marigold-colored markings
    let calavera = make_sprite(&[
        "..oooooo..",
        ".obbbbbbo.",
        "obbbbbbbbo",
        "obMboobMbo",
        "obMboobMbo",
        "obbbPPbbbo",
        "obbMMMMbbo",
        "obwbwbwbbo",
        ".obbbbbbo.",
        "..oooooo..",
    ], &[('b', bone), ('M', MARIGOLD), ('P', col(1.0,0.4,0.6,1.0)), ('w', col(0.1,0.1,0.1,1.0)), ('o', o)]);

    // boss — towering caped lord, pale face, red eyes
    let boss = make_sprite(&[
        ".....ooooooo.....",
        "....oKKKKKKKo....",
        "...oKKKKKKKKKo...",
        "...oKffffffKo...",
        "..oKfRfffRfKo...",
        "..oKffWWffKo....",
        "..oKfffffKo.....",
        ".oCCCCCCCCCCo...",
        "oCCCCCCCCCCCCo..",
        "oCCCRRRRRRCCCo..",
        "oCCRRRRRRRRCCo..",
        "oCCRRRRRRRRRCCo.",
        "oCCRRRRRRRRCCo..",
        "oCCCRRRRRRCCCo..",
        ".oCCCCCCCCCCo...",
        "..oCCCCCCCCo....",
        "..oCCo oCCo.....",
        ".oCCo   oCCo....",
    ], &[('K', col(0.10,0.07,0.12,1.0)), ('f', col(0.84,0.8,0.82,1.0)), ('R', col(0.78,0.13,0.15,1.0)),
         ('W', col(0.95,0.2,0.2,1.0)), ('C', col(0.16,0.04,0.1,1.0)), ('o', o)]);

    let fin = make_sprite(&["."], &[('x', WHITE)]); // placeholder (unused slot)

    let shard = make_sprite(&[
        "...gg...", "..gGGg..", ".gGGGGg.", "gGGGGGGg",
        "gGGGGGGg", ".gGGGGg.", "..gGGg..", "...gg...",
    ], &[('g', col(0.2,0.85,0.5,1.0)), ('G', col(0.55,1.0,0.75,1.0))]);

    let heart = make_sprite(&[
        ".rr..rr.", "rRrrrRr.", "rrrrrrrr", "rrrrrrrr",
        ".rrrrrr.", "..rrrr..", "...rr...",
    ], &[('r', red), ('R', col(1.0,0.55,0.55,1.0))]);

    // chest — tinted per rarity at draw time
    let chest = make_sprite(&[
        "oooooooooo", "oGGGGGGGGo", "oGllllllGo", "oooooooooo",
        "oWbbYYbbWo", "ooobYYbooo", "oooolloooo", "oooooooooo",
    ], &[('G', col(0.8,0.6,0.2,1.0)), ('l', col(0.95,0.8,0.4,1.0)), ('b', col(0.42,0.26,0.14,1.0)),
         ('Y', CANDLE), ('W', col(0.95,0.85,0.5,1.0)), ('o', o)]);

    let marigold = make_sprite(&[
        "..y..y..", ".yMyyMy.", "yMMMMMMy", "yMMooMMy",
        "yMMMMMMy", ".yMMMMy.", "..yMMy..", "...gg...",
    ], &[('y', col(1.0,0.78,0.2,1.0)), ('M', MARIGOLD), ('o', col(0.6,0.3,0.05,1.0)), ('g', grn)]);

    let cross = make_sprite(&[
        "..oo..", "..bb..", "obbbbo", "obbbbo",
        "..bb..", "..bb..", "..bb..",
    ], &[('b', CANDLE), ('o', o)]);

    Art { hunter, bat, skeleton, ghoul, wraith, calavera, boss, fin, shard, heart, chest, marigold, cross }
}

// ---------------- shaded box meshes (props) ----------------
fn shade(base: Color, normal: Vec3) -> Color {
    let l = vec3(-0.3, 1.0, 0.35).normalize();
    let d = normal.dot(l).max(0.0);
    let amb = 0.46;
    let b = amb + (1.0 - amb) * d;
    Color::new((base.r*b).min(1.0), (base.g*b).min(1.0), (base.b*b).min(1.0), base.a)
}
struct Boxer { mesh: Mesh }
impl Boxer {
    fn new() -> Self {
        let mut indices = Vec::with_capacity(36);
        for f in 0..6u16 { let o = f*4; indices.extend_from_slice(&[o,o+1,o+2,o,o+2,o+3]); }
        Boxer { mesh: Mesh { vertices: vec![Vertex::new(0.0,0.0,0.0,0.0,0.0,WHITE); 24], indices, texture: None } }
    }
    fn draw(&mut self, c: Vec3, h: Vec3, base: Color) {
        let (x0,x1)=(c.x-h.x,c.x+h.x); let (y0,y1)=(c.y-h.y,c.y+h.y); let (z0,z1)=(c.z-h.z,c.z+h.z);
        let faces: [(Vec3,[Vec3;4]);6] = [
            (vec3(0.0,1.0,0.0),[vec3(x0,y1,z1),vec3(x1,y1,z1),vec3(x1,y1,z0),vec3(x0,y1,z0)]),
            (vec3(0.0,-1.0,0.0),[vec3(x0,y0,z0),vec3(x1,y0,z0),vec3(x1,y0,z1),vec3(x0,y0,z1)]),
            (vec3(0.0,0.0,1.0),[vec3(x0,y0,z1),vec3(x1,y0,z1),vec3(x1,y1,z1),vec3(x0,y1,z1)]),
            (vec3(0.0,0.0,-1.0),[vec3(x1,y0,z0),vec3(x0,y0,z0),vec3(x0,y1,z0),vec3(x1,y1,z0)]),
            (vec3(1.0,0.0,0.0),[vec3(x1,y0,z1),vec3(x1,y0,z0),vec3(x1,y1,z0),vec3(x1,y1,z1)]),
            (vec3(-1.0,0.0,0.0),[vec3(x0,y0,z0),vec3(x0,y0,z1),vec3(x0,y1,z1),vec3(x0,y1,z0)]),
        ];
        let mut vi = 0;
        for (n, cs) in faces.iter() {
            let fc: [u8;4] = shade(base, *n).into();
            for p in cs.iter() { let v=&mut self.mesh.vertices[vi]; v.position=*p; v.color=fc; vi+=1; }
        }
        draw_mesh(&self.mesh);
    }
}

fn billboard(tex: &Texture2D, base: Vec3, w: f32, h: f32, right: Vec3, tint: Color) {
    let up = vec3(0.0,1.0,0.0);
    let r = right * (w*0.5); let u = up * h;
    let bl = base - r; let br = base + r; let tr = base + r + u; let tl = base - r + u;
    let verts = vec![
        Vertex::new(bl.x,bl.y,bl.z, 0.0,1.0, tint),
        Vertex::new(br.x,br.y,br.z, 1.0,1.0, tint),
        Vertex::new(tr.x,tr.y,tr.z, 1.0,0.0, tint),
        Vertex::new(tl.x,tl.y,tl.z, 0.0,0.0, tint),
    ];
    draw_mesh(&Mesh { vertices: verts, indices: vec![0,1,2,0,2,3], texture: Some(tex.clone()) });
}
fn shadow(pos: Vec3, r: f32) { draw_plane(vec3(pos.x, 0.02, pos.z), vec2(r, r), None, col(0.0,0.0,0.0,0.33)); }

// ---------------- entities ----------------
#[derive(Clone)]
struct Enemy { pos: Vec3, hp: f32, max_hp: f32, speed: f32, radius: f32, flash: f32, touch_cd: f32, kind: u8, bob: f32, slow: f32 }
struct Shot { pos: Vec3, vel: Vec3, life: f32, dmg: f32, pierce: i32, size: f32, kind: u8, spin: f32, home: bool }
struct Gem { pos: Vec3, value: f32, t: f32 }
struct Pickup { pos: Vec3, kind: u8, t: f32, rarity: u8 }
struct Particle { pos: Vec3, vel: Vec3, life: f32, max: f32, size: f32, color: Color, gravity: f32 }
struct FloatText { pos: Vec3, life: f32, text: String, color: Color, size: u16 }
struct Familiar { pos: Vec3 }
struct Prop { pos: Vec3, kind: u8, s: f32 }
struct FireZone { pos: Vec3, r: f32, life: f32, dmg: f32 }

#[derive(Clone, Copy, PartialEq)]
enum Up { Damage, FireRate, Multishot, Speed, MaxHp, Magnet, Area, Pierce, Regen, Luck,
          Garlic, Lantern, Nova, Volley, Familiar, Scythe, Spear, Smite, Moonbeam }
impl Up {
    fn title(&self) -> &'static str { match self {
        Up::Damage=>"Sharpened Silver", Up::FireRate=>"Overclocked Censer", Up::Multishot=>"Split Bolt",
        Up::Speed=>"Swift Boots", Up::MaxHp=>"Blessed Plating", Up::Magnet=>"Rune Cache",
        Up::Area=>"Wider Wards", Up::Pierce=>"Piercing Rounds", Up::Regen=>"Patch Tuesday", Up::Luck=>"Lucky Charm",
        Up::Garlic=>"Garlic Firewall", Up::Lantern=>"Holy Lantern", Up::Nova=>"Rune Nova", Up::Volley=>"Stake Volley",
        Up::Familiar=>"Wisp Daemon", Up::Scythe=>"Reaper's Scythe", Up::Spear=>"Bone Spear",
        Up::Smite=>"Chain Smite", Up::Moonbeam=>"Moonbeam",
    }}
    fn desc(&self) -> &'static str { match self {
        Up::Damage=>"+30% all damage", Up::FireRate=>"+20% fire rate", Up::Multishot=>"+1 bolt per shot",
        Up::Speed=>"+12% move speed", Up::MaxHp=>"+30 max HP, heal 60", Up::Magnet=>"+60% pickup range",
        Up::Area=>"+25% area of effect", Up::Pierce=>"Shots pierce +1 enemy", Up::Regen=>"Regenerate HP over time",
        Up::Luck=>"Better & more frequent drops",
        Up::Garlic=>"A burning aura around you", Up::Lantern=>"An orbiting holy lantern", Up::Nova=>"Periodic holy shockwave",
        Up::Volley=>"Fire a 3-stake spread", Up::Familiar=>"A wisp that hunts the undead",
        Up::Scythe=>"A scythe sweeps all around you", Up::Spear=>"A piercing bone lance",
        Up::Smite=>"Lightning that leaps between foes", Up::Moonbeam=>"A beam that sweeps the night",
    }}
    fn color(&self) -> Color { match self {
        Up::Damage=>col(0.9,0.8,0.8,1.0), Up::FireRate=>col(0.95,0.82,0.4,1.0), Up::Multishot=>col(0.7,0.85,1.0,1.0),
        Up::Speed=>col(0.6,0.95,0.7,1.0), Up::MaxHp=>col(0.9,0.35,0.45,1.0), Up::Magnet=>col(0.5,1.0,0.7,1.0),
        Up::Area=>col(0.72,0.6,0.95,1.0), Up::Pierce=>col(0.9,0.7,0.9,1.0), Up::Regen=>col(0.5,1.0,0.6,1.0),
        Up::Luck=>CANDLE, Up::Garlic=>col(0.82,0.95,0.42,1.0), Up::Lantern=>CANDLE, Up::Nova=>col(1.0,0.9,0.6,1.0),
        Up::Volley=>col(0.78,0.86,1.0,1.0), Up::Familiar=>col(0.72,0.9,1.0,1.0), Up::Scythe=>col(0.8,0.85,0.9,1.0),
        Up::Spear=>col(0.95,0.93,0.85,1.0), Up::Smite=>col(0.7,0.9,1.0,1.0), Up::Moonbeam=>col(0.95,0.95,0.7,1.0),
    }}
}

#[derive(PartialEq)]
enum Phase { Title, Playing, LevelUp, Dead, Win }
struct Boss { active: bool, name: &'static str }

struct Game {
    phase: Phase,
    player: Vec3, py: f32, vy: f32, dodge_cd: f32, iframe: f32, hurt_cd: f32, dash: Vec3,
    face_right: bool,
    hp: f32, max_hp: f32, speed: f32,
    level: u32, xp: f32, xp_need: f32,
    fire_cd: f32, fire_interval: f32, dmg: f32, shot_speed: f32,
    multishot: u32, pierce: i32, area: f32, magnet: f32, regen: f32, luck: f32,
    garlic: u32, garlic_t: f32, lanterns: u32, orb_angle: f32, nova: u32, nova_cd: f32, volley: u32,
    scythe: u32, scythe_t: f32, scythe_ang: f32, spear: u32, spear_t: f32,
    smite: u32, smite_t: f32, smite_arcs: Vec<(Vec3, Vec3, f32)>,
    moonbeam: u32, beam_ang: f32,
    familiars: Vec<Familiar>,
    enemies: Vec<Enemy>, shots: Vec<Shot>, gems: Vec<Gem>, pickups: Vec<Pickup>,
    parts: Vec<Particle>, floats: Vec<FloatText>, props: Vec<Prop>, fires: Vec<FireZone>,
    spawn_cd: f32, spawn_interval: f32,
    time: f32, kills: u32, wave: u32, next_boss: u32, boss: Boss, boss_idx: usize, final_spawned: bool,
    combo: u32, combo_t: f32,
    shake: f32, hitstop: f32, cam: Vec3, petal_t: f32,
    choices: Vec<Up>, flash: f32, dmg_flash: f32,
}

const BOSS_NAMES: [&str; 5] = ["Count Null-Pointer", "The Bone Compiler", "Plague-Ghoul Prime",
                               "La Catrina Calavera", "Lord Vlad Overflow"];
const PHASES: [&str; 5] = ["Dusk", "Midnight", "The Witching Hour", "Día de los Muertos", "Before Dawn"];
const WIN_TIME: u32 = 600; // survive 10 minutes to see dawn

fn weighted_pool(g: &Game) -> Vec<Up> {
    let mut pool = vec![Up::Damage, Up::FireRate, Up::Multishot, Up::Speed, Up::MaxHp,
                        Up::Magnet, Up::Area, Up::Pierce, Up::Regen, Up::Luck];
    if g.garlic < 5 { pool.push(Up::Garlic); }
    if g.lanterns < 6 { pool.push(Up::Lantern); pool.push(Up::Lantern); }
    if g.nova < 5 { pool.push(Up::Nova); }
    if g.volley < 4 { pool.push(Up::Volley); }
    if g.familiars.len() < 5 { pool.push(Up::Familiar); pool.push(Up::Familiar); }
    if g.scythe < 5 { pool.push(Up::Scythe); pool.push(Up::Scythe); }
    if g.spear < 5 { pool.push(Up::Spear); pool.push(Up::Spear); }
    if g.smite < 5 { pool.push(Up::Smite); pool.push(Up::Smite); }
    if g.moonbeam < 4 { pool.push(Up::Moonbeam); pool.push(Up::Moonbeam); }
    let mut chosen = Vec::new(); let mut guard = 0;
    while chosen.len() < 3 && guard < 120 {
        let u = pool[rand::gen_range(0, pool.len())];
        if !chosen.contains(&u) { chosen.push(u); }
        guard += 1;
    }
    chosen
}

impl Game {
    fn new() -> Self {
        let mut props = Vec::new();
        // tombstones, crosses, crypts, dead trees scattered across the big map
        for _ in 0..120 {
            let a = rand::gen_range(0.0, std::f32::consts::TAU);
            let r = rand::gen_range(4.0f32, ARENA - 3.0);
            let p = vec3(a.cos()*r, 0.0, a.sin()*r);
            let kind = rand::gen_range(0u8, 5); // 0 slab 1 cross 2 crypt 3 tree 4 candle
            props.push(Prop { pos: p, kind, s: rand::gen_range(0.75f32, 1.5) });
        }
        Game {
            phase: Phase::Title, player: vec3(0.0,0.0,0.0), py: 0.0, vy: 0.0, dodge_cd: 0.0, iframe: 0.0, hurt_cd: 0.0, dash: Vec3::ZERO,
            face_right: true,
            hp: 130.0, max_hp: 130.0, speed: 8.4,
            level: 1, xp: 0.0, xp_need: 4.0,
            fire_cd: 0.0, fire_interval: 0.52, dmg: 15.0, shot_speed: 27.0,
            multishot: 1, pierce: 0, area: 1.0, magnet: 4.8, regen: 0.0, luck: 0.0,
            garlic: 0, garlic_t: 0.0, lanterns: 0, orb_angle: 0.0, nova: 0, nova_cd: 0.0, volley: 0,
            scythe: 0, scythe_t: 0.0, scythe_ang: 0.0, spear: 0, spear_t: 0.0,
            smite: 0, smite_t: 0.0, smite_arcs: Vec::new(), moonbeam: 0, beam_ang: 0.0,
            familiars: Vec::new(),
            enemies: Vec::new(), shots: Vec::new(), gems: Vec::new(), pickups: Vec::new(),
            parts: Vec::new(), floats: Vec::new(), props, fires: Vec::new(),
            spawn_cd: 0.0, spawn_interval: 0.95,
            time: 0.0, kills: 0, wave: 1, next_boss: 55, boss: Boss { active:false, name:"" }, boss_idx: 0, final_spawned: false,
            combo: 0, combo_t: 0.0,
            shake: 0.0, hitstop: 0.0, cam: vec3(0.0,18.0,14.0), petal_t: 0.0,
            choices: Vec::new(), flash: 0.0, dmg_flash: 0.0,
        }
    }
    fn reset(&mut self) { *self = Game::new(); self.phase = Phase::Playing; }

    fn burst(&mut self, pos: Vec3, n: usize, color: Color, spd: f32, sz: f32, grav: f32) {
        for _ in 0..n {
            if self.parts.len() > 700 { break; }
            let a = rand::gen_range(0.0, std::f32::consts::TAU);
            let el = rand::gen_range(0.1f32, 1.0);
            let v = vec3(a.cos()*el, rand::gen_range(0.2f32,1.0), a.sin()*el).normalize() * rand::gen_range(spd*0.4, spd);
            let life = rand::gen_range(0.25f32, 0.65);
            self.parts.push(Particle { pos, vel: v, life, max: life, size: sz, color, gravity: grav });
        }
    }
    fn floaty(&mut self, pos: Vec3, text: String, color: Color, size: u16) {
        if self.floats.len() < 90 { self.floats.push(FloatText { pos, life: 0.9, text, color, size }); }
    }
    fn spawn_at(&self, r: f32) -> Vec3 {
        let a = rand::gen_range(0.0, std::f32::consts::TAU);
        let mut p = self.player + vec3(a.cos()*r, 0.0, a.sin()*r);
        let flat = vec3(p.x, 0.0, p.z);
        if flat.length() > ARENA - 1.0 { let c = flat.normalize()*(ARENA-1.0); p.x=c.x; p.z=c.z; }
        p
    }
    fn spawn_enemy(&mut self, boss: bool, final_boss: bool) {
        let ws = 1.0 + (self.wave as f32 - 1.0) * 0.18;
        if boss {
            let idx = if final_boss { 4 } else { self.boss_idx % 4 };
            let mult = if final_boss { 4.0 } else { 1.0 };
            let hp = 1200.0 * (1.0 + self.wave as f32 * 0.32) * mult;
            self.enemies.push(Enemy { pos: self.spawn_at(18.0), hp, max_hp: hp,
                speed: if final_boss {3.0} else {2.6}, radius: if final_boss {2.6} else {1.9},
                flash: 0.0, touch_cd: 0.0, kind: 4, bob: 0.0, slow: 0.0 });
            self.boss = Boss { active: true, name: BOSS_NAMES[idx] };
            if !final_boss { self.boss_idx += 1; }
            return;
        }
        let roll = rand::gen_range(0.0f32, 1.0);
        let (kind, hp, speed, radius) = if roll < 0.26 { (0u8, 7.0*ws, 6.4, 0.6) }
            else if roll < 0.50 { (1u8, 16.0*ws, 3.7, 0.7) }
            else if roll < 0.70 { (2u8, 28.0*ws, 3.0, 0.85) }
            else if roll < 0.86 { (3u8, 13.0*ws, 4.8, 0.7) }
            else { (5u8, 20.0*ws, 4.0, 0.7) }; // calavera
        self.enemies.push(Enemy { pos: self.spawn_at(17.0), hp, max_hp: hp, speed, radius,
            flash: 0.0, touch_cd: 0.0, kind, bob: rand::gen_range(0.0,6.28), slow: 0.0 });
    }
    fn nearest(&self, from: Vec3) -> Option<usize> {
        let mut best = None; let mut bd = f32::MAX;
        for (i, e) in self.enemies.iter().enumerate() {
            let d = (e.pos - from).length_squared();
            if d < bd { bd = d; best = Some(i); }
        }
        best
    }
    fn apply_upgrade(&mut self, u: Up) {
        match u {
            Up::Damage => self.dmg *= 1.3,
            Up::FireRate => self.fire_interval = (self.fire_interval*0.8).max(0.08),
            Up::Multishot => self.multishot += 1,
            Up::Speed => self.speed *= 1.12,
            Up::MaxHp => { self.max_hp += 30.0; self.hp = (self.hp+60.0).min(self.max_hp); }
            Up::Magnet => self.magnet *= 1.6,
            Up::Area => self.area *= 1.25,
            Up::Pierce => self.pierce += 1,
            Up::Regen => self.regen += 1.6,
            Up::Luck => self.luck += 1.0,
            Up::Garlic => self.garlic += 1,
            Up::Lantern => self.lanterns += 1,
            Up::Nova => self.nova += 1,
            Up::Volley => self.volley += 1,
            Up::Familiar => self.familiars.push(Familiar { pos: self.player }),
            Up::Scythe => self.scythe += 1,
            Up::Spear => self.spear += 1,
            Up::Smite => self.smite += 1,
            Up::Moonbeam => self.moonbeam += 1,
        }
    }
    fn open_chest(&mut self, pos: Vec3, rarity: u8) {
        let n = 8 + rarity as usize * 10;
        for _ in 0..n {
            let a = rand::gen_range(0.0, std::f32::consts::TAU);
            self.gems.push(Gem { pos: pos + vec3(a.cos()*0.5, 0.5, a.sin()*0.5),
                value: 2.0 + rarity as f32 * 2.0, t: 0.0 });
        }
        self.hp = (self.hp + 25.0 + rarity as f32 * 20.0).min(self.max_hp);
        self.burst(pos + vec3(0.0,0.6,0.0), 50, CANDLE, 16.0, 0.18, 0.6);
        let names = ["SOUL CACHE!", "RICH CACHE!", "GILDED CACHE!"];
        self.floaty(pos + vec3(0.0,2.2,0.0), names[rarity.min(2) as usize].into(), CANDLE, 28);
        self.shake = (self.shake + 0.4).min(1.2);
    }
}

fn update(g: &mut Game, dt: f32) {
    if g.hitstop > 0.0 { g.hitstop -= dt; }
    let step = if g.hitstop > 0.0 { dt*0.12 } else { dt };
    g.time += step;
    g.shake = (g.shake - dt*2.0).max(0.0);
    g.flash = (g.flash - dt*2.0).max(0.0);
    g.dmg_flash = (g.dmg_flash - dt*2.5).max(0.0);
    g.dodge_cd = (g.dodge_cd - dt).max(0.0);
    g.iframe = (g.iframe - dt).max(0.0);
    g.hurt_cd = (g.hurt_cd - dt).max(0.0);
    g.combo_t = (g.combo_t - dt).max(0.0);
    if g.combo_t <= 0.0 { g.combo = 0; }
    g.petal_t -= dt;

    let new_wave = 1 + (g.time/18.0) as u32;
    if new_wave > g.wave { g.wave = new_wave; g.spawn_interval = (0.95*0.9f32.powi(g.wave as i32 -1)).max(0.17); }
    if g.regen > 0.0 { g.hp = (g.hp + g.regen*step).min(g.max_hp); }

    // win at dawn
    if g.time as u32 >= WIN_TIME && !g.boss.active { g.phase = Phase::Win; return; }

    // movement
    let mut mv = vec3(0.0,0.0,0.0);
    if is_key_down(KeyCode::W)||is_key_down(KeyCode::Up) { mv.z -= 1.0; }
    if is_key_down(KeyCode::S)||is_key_down(KeyCode::Down) { mv.z += 1.0; }
    if is_key_down(KeyCode::A)||is_key_down(KeyCode::Left) { mv.x -= 1.0; }
    if is_key_down(KeyCode::D)||is_key_down(KeyCode::Right) { mv.x += 1.0; }
    if let Some(j) = joystick_vec() { mv.x += j.x; mv.z += j.y; }
    let moving = mv.length_squared() > 0.01;
    if moving { mv = mv.normalize(); if mv.x.abs()>0.05 { g.face_right = mv.x>0.0; } }

    // JUMP / DODGE leap
    let want_dodge = is_key_pressed(KeyCode::Space) || is_key_pressed(KeyCode::LeftShift) || dodge_tap();
    if want_dodge && g.dodge_cd <= 0.0 {
        g.vy = 8.5; g.iframe = 0.5; g.dodge_cd = 1.1;
        let d = if moving { mv } else { vec3(if g.face_right {1.0} else {-1.0}, 0.0, 0.0) };
        g.dash = d * 15.0;
        g.burst(g.player + vec3(0.0,0.2,0.0), 14, col(0.8,0.9,1.0,1.0), 7.0, 0.1, 1.0);
    }
    g.vy -= 22.0 * step; g.py += g.vy * step;
    if g.py < 0.0 { g.py = 0.0; g.vy = 0.0; }
    // apply move + dash
    g.player += mv * g.speed * step;
    g.player += g.dash * step;
    g.dash = g.dash.lerp(Vec3::ZERO, (10.0*step).min(1.0));
    let flat = vec3(g.player.x, 0.0, g.player.z);
    if flat.length() > ARENA - 1.0 { let c = flat.normalize()*(ARENA-1.0); g.player.x=c.x; g.player.z=c.z; }

    // spawn hordes
    g.spawn_cd -= step;
    if g.spawn_cd <= 0.0 && g.enemies.len() < 210 {
        let burst = 2 + g.wave as usize;
        for _ in 0..burst { g.spawn_enemy(false, false); }
        g.spawn_cd = g.spawn_interval;
    }
    // bosses + final boss
    if g.time as u32 >= g.next_boss && !(g.time as u32 >= WIN_TIME - 60) {
        g.spawn_enemy(true, false); g.next_boss += 70; g.shake = 1.0;
        g.floaty(g.player + vec3(0.0,3.5,0.0), "A BOSS APPROACHES".into(), col(1.0,0.4,0.4,1.0), 30);
    }
    if g.time as u32 >= WIN_TIME - 60 && !g.final_spawned {
        g.final_spawned = true; g.spawn_enemy(true, true); g.shake = 1.2;
        g.floaty(g.player + vec3(0.0,3.5,0.0), "THE NIGHT LORD RISES".into(), col(1.0,0.3,0.3,1.0), 34);
    }

    // enemies chase
    let pp = g.player;
    for e in g.enemies.iter_mut() {
        e.slow = (e.slow - step).max(0.0);
        let sp = if e.slow > 0.0 { e.speed*0.45 } else { e.speed };
        let mut to = pp - e.pos; to.y = 0.0;
        let d = to.length(); e.bob += step*5.0;
        let mut dir = if d>0.001 { to/d } else { Vec3::ZERO };
        if e.kind==3 { let perp = vec3(-dir.z,0.0,dir.x); dir = (dir + perp*(e.bob.sin()*0.55)).normalize_or_zero(); }
        e.pos += dir * sp * step;
        e.flash = (e.flash - step*5.0).max(0.0);
        e.touch_cd = (e.touch_cd - step).max(0.0);
        if d < e.radius+0.7 && e.touch_cd <= 0.0 && g.iframe <= 0.0 && g.hurt_cd <= 0.0 && g.py < 1.2 {
            let dmg = match e.kind { 4=>22.0, 2=>12.0, 0=>5.0, _=>8.0 };
            g.hp -= dmg; e.touch_cd = 0.6; g.hurt_cd = 0.45; // brief grace so a pile can't stack-kill
            g.shake = (g.shake+0.35).min(1.2); g.dmg_flash = 1.0;
        }
    }

    // ---- weapons ----
    // silver bolt (+volley)
    g.fire_cd -= step;
    if g.fire_cd <= 0.0 {
        if let Some(i) = g.nearest(g.player) {
            let dir = { let mut d = g.enemies[i].pos - g.player; d.y=0.0; d.normalize_or_zero() };
            if dir.length_squared() > 0.0 {
                let base = dir.x.atan2(dir.z); let spread = 0.14;
                let total = g.multishot + g.volley*3;
                for s in 0..total {
                    let off = if total==1 {0.0} else {(s as f32 - (total as f32-1.0)/2.0)*spread};
                    let a = base+off; let v = vec3(a.sin(),0.0,a.cos())*g.shot_speed;
                    g.shots.push(Shot { pos: g.player+vec3(0.0,1.0,0.0), vel: v, life:1.7, dmg:g.dmg,
                        pierce:g.pierce, size:0.3*g.area, kind:0, spin:0.0, home:false });
                }
                g.fire_cd = g.fire_interval;
            }
        }
    }
    // bone spear
    if g.spear > 0 {
        g.spear_t -= step;
        if g.spear_t <= 0.0 {
            g.spear_t = (1.1 - g.spear as f32*0.1).max(0.4);
            if let Some(i) = g.nearest(g.player) {
                let dir = { let mut d = g.enemies[i].pos - g.player; d.y=0.0; d.normalize_or_zero() };
                let a = dir.x.atan2(dir.z);
                for k in 0..g.spear {
                    let off = (k as f32 - (g.spear as f32-1.0)/2.0)*0.12;
                    let aa = a+off; let v = vec3(aa.sin(),0.0,aa.cos())*38.0;
                    g.shots.push(Shot { pos: g.player+vec3(0.0,1.0,0.0), vel:v, life:1.4, dmg:g.dmg*1.6,
                        pierce:99, size:0.5*g.area, kind:1, spin:a, home:false });
                }
            }
        }
    }
    // scythe sweep (rotating melee ring)
    if g.scythe > 0 {
        g.scythe_ang += step * 3.4;
        g.scythe_t -= step;
        if g.scythe_t <= 0.0 {
            g.scythe_t = 0.25;
            let radius = (3.0 + g.scythe as f32*0.5)*g.area;
            let sd = g.dmg * 0.5 * g.scythe as f32;
            let pc = g.player;
            let mut hits = Vec::new();
            for (ei,e) in g.enemies.iter().enumerate() {
                if (vec3(e.pos.x,0.0,e.pos.z)-vec3(pc.x,0.0,pc.z)).length() < radius+e.radius { hits.push(ei); }
            }
            for ei in hits { if let Some(e)=g.enemies.get_mut(ei){ e.hp-=sd; e.flash=e.flash.max(0.4);} }
        }
    }
    // chain smite
    if g.smite > 0 {
        g.smite_t -= step;
        g.smite_arcs.retain_mut(|a| { a.2 -= dt; a.2 > 0.0 });
        if g.smite_t <= 0.0 {
            g.smite_t = (1.6 - g.smite as f32*0.15).max(0.6);
            if let Some(i0) = g.nearest(g.player) {
                let mut from = g.player + vec3(0.0,1.0,0.0);
                let mut hit: Vec<usize> = Vec::new();
                let chain = 2 + g.smite as usize;
                let dmg = g.dmg * 1.3;
                let mut cur = Some(i0);
                for _ in 0..chain {
                    if let Some(ci) = cur {
                        if let Some(e) = g.enemies.get_mut(ci) {
                            e.hp -= dmg; e.flash = 1.0;
                            let to = e.pos + vec3(0.0,0.9,0.0);
                            g.smite_arcs.push((from, to, 0.18));
                            from = to; hit.push(ci);
                        }
                        // next nearest not already hit
                        let mut best=None; let mut bd=f32::MAX;
                        for (ei,e) in g.enemies.iter().enumerate() {
                            if hit.contains(&ei) {continue;}
                            let d=(e.pos - from).length_squared();
                            if d<bd && d < 100.0 { bd=d; best=Some(ei); }
                        }
                        cur = best;
                    }
                }
            }
        }
    }
    // moonbeam (rotating beam)
    if g.moonbeam > 0 {
        g.beam_ang += step * (0.9 + g.moonbeam as f32*0.15);
        let dir = vec3(g.beam_ang.cos(), 0.0, g.beam_ang.sin());
        let len = 16.0 * g.area;
        let bd = g.dmg * 1.2 * step * 6.0;
        let pc = g.player;
        for e in g.enemies.iter_mut() {
            let rel = vec3(e.pos.x-pc.x, 0.0, e.pos.z-pc.z);
            let t = rel.dot(dir);
            if t > 0.0 && t < len {
                let perp = (rel - dir*t).length();
                if perp < 1.0 + e.radius { e.hp -= bd; e.flash = e.flash.max(0.3); }
            }
        }
    }
    // garlic aura
    if g.garlic > 0 {
        g.garlic_t -= step;
        let radius = (2.6 + g.garlic as f32*0.7)*g.area;
        if g.garlic_t <= 0.0 {
            g.garlic_t = 0.5;
            let gd = g.dmg*0.35*g.garlic as f32; let pc=g.player;
            let mut hits=Vec::new();
            for (ei,e) in g.enemies.iter().enumerate() {
                if (vec3(e.pos.x,0.0,e.pos.z)-vec3(pc.x,0.0,pc.z)).length() < radius+e.radius { hits.push(ei); }
            }
            for ei in hits { if let Some(e)=g.enemies.get_mut(ei){ e.hp-=gd; e.flash=e.flash.max(0.4);} }
        }
    }
    // nova
    if g.nova > 0 {
        g.nova_cd -= step;
        if g.nova_cd <= 0.0 {
            g.nova_cd = (3.4 - g.nova as f32*0.4).max(1.0);
            let radius=(5.0+g.nova as f32*1.5)*g.area; let nd=g.dmg*1.7; let pc=g.player;
            for e in g.enemies.iter_mut() { if (vec3(e.pos.x,0.0,e.pos.z)-vec3(pc.x,0.0,pc.z)).length()<radius+e.radius { e.hp-=nd; e.flash=1.0; } }
            g.burst(pc+vec3(0.0,0.5,0.0), 46, CANDLE, 16.0, 0.16, 0.0); g.shake=(g.shake+0.3).min(1.2);
        }
    }
    // lanterns
    if g.lanterns > 0 {
        g.orb_angle += step*2.4; let orad=2.9*g.area; let od=g.dmg*0.6; let pc=g.player;
        let mut hits:Vec<(usize,f32)>=Vec::new();
        for k in 0..g.lanterns {
            let a=g.orb_angle + k as f32*std::f32::consts::TAU/g.lanterns as f32;
            let op=pc+vec3(a.cos()*orad,0.9,a.sin()*orad);
            for (ei,e) in g.enemies.iter().enumerate() { if (e.pos+vec3(0.0,0.6,0.0)-op).length()<e.radius+0.6 { hits.push((ei,od*step*9.0)); } }
        }
        for (ei,d) in hits { if let Some(e)=g.enemies.get_mut(ei){ e.hp-=d; e.flash=e.flash.max(0.5);} }
    }
    // familiars
    if !g.familiars.is_empty() {
        let pc=g.player; let targets:Vec<Vec3>=g.enemies.iter().map(|e|e.pos).collect();
        let fd=g.dmg*0.5; let mut hits:Vec<(usize,f32)>=Vec::new();
        let tnow = get_time() as f32;
        for (fi,f) in g.familiars.iter_mut().enumerate() {
            let mut goal = pc + vec3((tnow+fi as f32).cos()*3.4, 1.0, (tnow+fi as f32).sin()*3.4);
            let mut bd=f32::MAX;
            for t in &targets { let d=(*t-f.pos).length_squared(); if d<bd { bd=d; goal=*t+vec3(0.0,0.6,0.0); } }
            f.pos = f.pos.lerp(goal, 0.08);
            for (ei,e) in g.enemies.iter().enumerate() { if (e.pos+vec3(0.0,0.6,0.0)-f.pos).length()<e.radius+0.5 { hits.push((ei,fd*step*10.0)); } }
        }
        for (ei,d) in hits { if let Some(e)=g.enemies.get_mut(ei){ e.hp-=d; e.flash=e.flash.max(0.4);} }
    }

    // shots
    for s in g.shots.iter_mut() {
        s.pos += s.vel*step; s.life -= step;
        for e in g.enemies.iter_mut() {
            if e.hp<=0.0 {continue;}
            if (e.pos+vec3(0.0,0.7,0.0)-s.pos).length() < e.radius+s.size+0.1 {
                e.hp -= s.dmg; e.flash=1.0;
                if s.pierce>0 { s.pierce-=1; } else { s.life=0.0; }
                break;
            }
        }
    }
    let a2=ARENA+5.0;
    g.shots.retain(|s| s.life>0.0 && (s.pos.x*s.pos.x+s.pos.z*s.pos.z)<a2*a2);

    // fire zones (unused weapon slot kept for future) - decay
    for f in g.fires.iter_mut() { f.life -= step; }
    g.fires.retain(|f| f.life > 0.0);

    // deaths
    let mut dead=Vec::new();
    for (i,e) in g.enemies.iter().enumerate() { if e.hp<=0.0 { dead.push(i); } }
    for &i in dead.iter().rev() {
        let e = g.enemies.remove(i);
        g.kills += 1; g.combo += 1; g.combo_t = 3.0;
        let (val,parts) = match e.kind { 4=>(60.0,70), 2=>(3.0,22), 5=>(2.0,18), _=>(1.0,13) };
        let dustc = match e.kind { 0=>col(0.4,0.2,0.5,1.0),1=>col(0.95,0.93,0.82,1.0),2=>col(0.4,0.7,0.3,1.0),3=>col(0.6,0.8,0.95,1.0),5=>MARIGOLD,_=>col(0.85,0.2,0.2,1.0) };
        g.burst(e.pos+vec3(0.0,0.6,0.0), parts, dustc, 9.0, 0.16, 1.4);
        if e.kind==5 { g.burst(e.pos+vec3(0.0,0.8,0.0), 16, MARIGOLD, 6.0, 0.14, 0.8); } // marigold petals
        g.gems.push(Gem { pos: vec3(e.pos.x,0.5,e.pos.z), value: val, t:0.0 });
        if e.kind==4 {
            g.shake=1.2; g.boss=Boss{active:false,name:""};
            let fb = e.radius > 2.4;
            g.pickups.push(Pickup { pos: vec3(e.pos.x,0.5,e.pos.z), kind:3, t:0.0, rarity: if fb {2} else {rand::gen_range(1u8,3)} });
            g.floaty(e.pos+vec3(0.0,3.0,0.0), "VANQUISHED!".into(), CANDLE, 30);
            if fb { g.phase = Phase::Win; }
        } else {
            let drop = 0.012 + g.luck*0.01;
            if rand::gen_range(0.0f32,1.0) < drop {
                let k = rand::gen_range(0u8,10);
                let (kind,rar) = if k<5 {(0u8,0u8)} else if k<8 {(1u8,0u8)} else {(3u8, if g.luck>1.0 {rand::gen_range(0u8,2)} else {0})};
                g.pickups.push(Pickup { pos: vec3(e.pos.x,0.5,e.pos.z), kind, t:0.0, rarity:rar });
            }
        }
    }

    // gems magnet + collect
    let pc=g.player; let mag=g.magnet;
    for gem in g.gems.iter_mut() {
        gem.t += step;
        let to=pc-gem.pos; let d=to.length();
        if d<mag { gem.pos += (to/d.max(0.001))*(12.0*step)*(1.0-d/mag+0.4); }
    }
    let mut got=0.0;
    g.gems.retain(|gem| { if (gem.pos-pc).length()<1.2 { got+=gem.value; false } else { true } });
    if got>0.0 { g.xp += got; }

    // pickups
    let mut use_pick=Vec::new();
    g.pickups.retain(|p| { if (p.pos-pc).length()<1.3 { use_pick.push((p.kind,p.rarity,p.pos)); false } else { true } });
    for (k,rar,pos) in use_pick {
        match k {
            0 => { g.hp=(g.hp+50.0).min(g.max_hp); g.floaty(g.player+vec3(0.0,2.0,0.0),"+50 HP".into(),col(0.4,1.0,0.5,1.0),26); }
            1 => { // marigold: holy burst
                let pcx=g.player;
                for e in g.enemies.iter_mut(){ if (e.pos-pcx).length()<11.0 { e.hp-=g.dmg*3.0; e.flash=1.0; } }
                g.burst(pcx+vec3(0.0,0.6,0.0),80,MARIGOLD,20.0,0.18,0.0); g.shake=1.0;
                g.floaty(g.player+vec3(0.0,2.0,0.0),"MARIGOLD BURST!".into(),MARIGOLD,28);
            }
            _ => g.open_chest(pos, rar),
        }
    }

    // level up
    if g.xp >= g.xp_need {
        g.xp -= g.xp_need; g.xp_need = (g.xp_need*1.27+1.0).round();
        g.level += 1; g.flash=1.0; g.choices=weighted_pool(g); g.phase=Phase::LevelUp;
    }

    // particles + floats + ambient petals
    for p in g.parts.iter_mut() { p.life-=dt; p.vel.y-=p.gravity*dt; p.pos+=p.vel*dt; }
    g.parts.retain(|p| p.life>0.0);
    for f in g.floats.iter_mut() { f.life-=dt; f.pos.y+=dt*1.8; }
    g.floats.retain(|f| f.life>0.0);
    if g.petal_t <= 0.0 {
        g.petal_t = 0.25;
        let a=rand::gen_range(0.0,std::f32::consts::TAU); let r=rand::gen_range(4.0f32,16.0);
        let p = g.player + vec3(a.cos()*r, rand::gen_range(6.0f32,9.0), a.sin()*r);
        g.parts.push(Particle{ pos:p, vel:vec3(rand::gen_range(-0.4,0.4),-1.0,rand::gen_range(-0.4,0.4)), life:3.0, max:3.0, size:0.12, color:MARIGOLD, gravity:0.1 });
    }

    let want = g.player + vec3(0.0, 18.0, 14.0);
    g.cam = g.cam.lerp(want, 0.11);

    if g.hp<=0.0 { g.hp=0.0; g.phase=Phase::Dead; g.burst(g.player+vec3(0.0,0.8,0.0),90,col(0.7,0.2,0.2,1.0),14.0,0.2,1.0); }
}

// ---------------- rendering ----------------
fn make_camera(g: &Game) -> Camera3D {
    let mut cp=g.cam;
    if g.shake>0.0 { let s=g.shake*0.45; cp.x+=rand::gen_range(-s,s); cp.y+=rand::gen_range(-s,s); }
    Camera3D { position:cp, up:vec3(0.0,1.0,0.0), target:g.player+vec3(0.0,1.0,0.0), fovy:0.9, ..Default::default() }
}
fn enemy_tex<'a>(art:&'a Art, kind:u8)->(&'a Texture2D,f32,f32){ match kind {
    0=>(&art.bat,2.1,1.1), 1=>(&art.skeleton,1.6,2.4), 2=>(&art.ghoul,2.2,2.0),
    3=>(&art.wraith,1.8,2.4), 5=>(&art.calavera,1.7,1.7), _=>(&art.boss,4.6,6.0),
}}

fn draw_world(g:&Game, bx:&mut Boxer, art:&Art) {
    let cam=make_camera(g);
    let right={ let fwd=(cam.target-cam.position).normalize(); fwd.cross(vec3(0.0,1.0,0.0)).normalize() };
    set_camera(&cam);

    draw_plane(vec3(0.0,0.0,0.0), vec2(ARENA*2.0+10.0, ARENA*2.0+10.0), None, col(0.05,0.07,0.06,1.0));
    draw_grid((ARENA as u32), 2.0, col(0.11,0.2,0.15,0.3), col(0.06,0.09,0.07,1.0));

    // the moon
    draw_sphere(vec3(-14.0, 26.0, -ARENA-16.0), 9.0, None, col(0.93,0.93,0.85,1.0));
    draw_sphere(vec3(-14.0, 26.0, -ARENA-16.0), 9.8, None, col(0.8,0.85,0.95,0.1));

    // papel-picado banners around the near perimeter (festive)
    let bander = 48usize;
    for i in 0..bander {
        let a0=i as f32/bander as f32*std::f32::consts::TAU;
        let p0=vec3(a0.cos()*(ARENA-2.0), 4.0 + (a0*4.0).sin()*0.4, a0.sin()*(ARENA-2.0));
        if (vec3(p0.x,0.0,p0.z)-vec3(g.player.x,0.0,g.player.z)).length() > 40.0 { continue; }
        let c=PAPEL[i%5];
        draw_cube(p0, vec3(0.5,0.6,0.08), None, c);
    }

    // props (tombstones, crosses, crypts, trees, candles)
    let stone=col(0.3,0.31,0.34,1.0);
    for p in &g.props {
        if (vec3(p.pos.x,0.0,p.pos.z)-vec3(g.player.x,0.0,g.player.z)).length() > 34.0 { continue; }
        shadow(p.pos, p.s*2.0);
        match p.kind {
            0 => { bx.draw(p.pos+vec3(0.0,p.s*0.6,0.0), vec3(p.s*0.7,p.s*0.7,0.2), stone);
                   bx.draw(p.pos+vec3(0.0,p.s*1.2,0.0), vec3(p.s*0.4,p.s*0.4,0.22), stone); }
            1 => { bx.draw(p.pos+vec3(0.0,p.s*0.7,0.0), vec3(0.14,p.s*0.7,0.14), stone);
                   bx.draw(p.pos+vec3(0.0,p.s*1.0,0.0), vec3(p.s*0.45,0.14,0.14), stone); }
            2 => { bx.draw(p.pos+vec3(0.0,p.s*0.6,0.0), vec3(p.s*1.3,p.s*0.6,p.s*1.0), col(0.24,0.25,0.27,1.0));
                   bx.draw(p.pos+vec3(0.0,p.s*1.1,0.0), vec3(p.s*0.9,p.s*0.3,p.s*0.7), col(0.28,0.29,0.31,1.0)); }
            3 => { bx.draw(p.pos+vec3(0.0,p.s*1.0,0.0), vec3(0.22,p.s*1.4,0.22), col(0.22,0.15,0.1,1.0));
                   bx.draw(p.pos+vec3(p.s*0.5,p.s*1.6,0.0), vec3(p.s*0.5,0.14,0.14), col(0.22,0.15,0.1,1.0));
                   bx.draw(p.pos+vec3(-p.s*0.4,p.s*2.0,0.0), vec3(0.14,p.s*0.5,0.14), col(0.22,0.15,0.1,1.0)); }
            _ => { bx.draw(p.pos+vec3(0.0,0.2,0.0), vec3(0.14,0.3,0.14), col(0.85,0.82,0.7,1.0));
                   draw_sphere(p.pos+vec3(0.0,0.55,0.0), 0.16, None, CANDLE);
                   draw_sphere(p.pos+vec3(0.0,0.55,0.0), 0.3, None, col(1.0,0.8,0.3,0.18)); }
        }
    }

    // billboards sorted back-to-front
    let mut sprites: Vec<(Vec3,&Texture2D,f32,f32,Color)> = Vec::new();
    for e in &g.enemies {
        let (tex,w,h)=enemy_tex(art,e.kind);
        let fly = match e.kind {0=>1.3+(e.bob).sin()*0.35, 3=>1.1+(e.bob*0.5).sin()*0.3, _=>0.0};
        let tint = if e.flash>0.0 { lerp_col(WHITE, col(2.0,0.6,0.6,1.0), e.flash.min(1.0)) } else { WHITE };
        shadow(e.pos, e.radius*2.0);
        sprites.push((vec3(e.pos.x,fly,e.pos.z),tex,w,h,tint));
    }
    for gem in &g.gems { let y=0.4+(gem.t*4.0).sin()*0.12; sprites.push((vec3(gem.pos.x,y,gem.pos.z),&art.shard,0.75,0.75,WHITE)); }
    for p in &g.pickups {
        let (tex,base) = match p.kind {0=>(&art.heart,WHITE),1=>(&art.marigold,WHITE),_=>(&art.chest, [WHITE, col(0.7,0.85,1.0,1.0), col(1.0,0.7,0.9,1.0)][p.rarity.min(2) as usize])};
        let y=0.55+(get_time() as f32*3.0+p.pos.x).sin()*0.12;
        let sz = if p.kind==2 {1.3} else {1.0};
        sprites.push((vec3(p.pos.x,y,p.pos.z),tex,sz,sz,base));
    }
    for f in &g.familiars { sprites.push((f.pos,&art.shard,0.85,0.85,col(0.7,0.9,1.0,1.0))); }
    // player (lifted by jump)
    shadow(g.player, 1.1 - (g.py*0.12).min(0.6));
    let pbob=(get_time() as f32*6.0).sin()*0.05;
    let ptint = if g.iframe>0.0 { col(0.6,0.9,1.0,0.6) } else { WHITE };
    sprites.push((vec3(g.player.x, g.py + pbob.max(0.0), g.player.z), &art.hunter, 1.8, 2.5, ptint));

    let cp=cam.position;
    sprites.sort_by(|a,b| { let da=(a.0-cp).length_squared(); let db=(b.0-cp).length_squared(); db.partial_cmp(&da).unwrap_or(std::cmp::Ordering::Equal) });
    for (pos,tex,w,h,tint) in &sprites { billboard(tex,*pos,*w,*h,right,*tint); }

    // lanterns
    if g.lanterns>0 {
        for k in 0..g.lanterns { let a=g.orb_angle+k as f32*std::f32::consts::TAU/g.lanterns as f32;
            let op=g.player+vec3(a.cos()*2.9*g.area,0.9,a.sin()*2.9*g.area);
            draw_sphere(op,0.35,None,CANDLE); draw_sphere(op,0.52,None,col(1.0,0.85,0.4,0.2)); }
    }
    // scythe ring
    if g.scythe>0 {
        let radius=(3.0+g.scythe as f32*0.5)*g.area; let seg=48;
        for i in 0..seg { let a0=g.scythe_ang+i as f32/seg as f32*std::f32::consts::TAU;
            let a1=g.scythe_ang+(i+1) as f32/seg as f32*std::f32::consts::TAU;
            let fade=((i as f32/seg as f32)*2.0-1.0).abs();
            draw_line_3d(g.player+vec3(a0.cos()*radius,0.3,a0.sin()*radius), g.player+vec3(a1.cos()*radius,0.3,a1.sin()*radius), col(0.85,0.9,1.0,0.1+0.4*(1.0-fade))); }
    }
    // garlic ring
    if g.garlic>0 {
        let radius=(2.6+g.garlic as f32*0.7)*g.area; let seg=40;
        for i in 0..seg { let a0=i as f32/seg as f32*std::f32::consts::TAU; let a1=(i+1) as f32/seg as f32*std::f32::consts::TAU;
            draw_line_3d(g.player+vec3(a0.cos()*radius,0.1,a0.sin()*radius), g.player+vec3(a1.cos()*radius,0.1,a1.sin()*radius), col(0.75,0.95,0.4,0.3)); }
    }
    // moonbeam
    if g.moonbeam>0 {
        let dir=vec3(g.beam_ang.cos(),0.0,g.beam_ang.sin()); let len=16.0*g.area;
        let a=g.player+vec3(0.0,0.6,0.0); let b=a+dir*len;
        draw_line_3d(a,b,col(0.95,0.95,0.75,0.8)); draw_line_3d(a+vec3(0.0,0.05,0.0),b+vec3(0.0,0.05,0.0),col(1.0,1.0,0.9,0.4));
    }
    // chain smite arcs
    for (f,t,_) in &g.smite_arcs { draw_line_3d(*f,*t,col(0.7,0.9,1.0,0.9)); draw_line_3d(*f+vec3(0.1,0.1,0.0),*t,col(0.9,0.95,1.0,0.5)); }

    // shots
    for s in &g.shots {
        match s.kind {
            1 => { let d=s.vel.normalize_or_zero(); draw_line_3d(s.pos-d*0.7, s.pos+d*0.7, col(0.95,0.93,0.85,1.0)); draw_sphere(s.pos,s.size*0.6,None,WHITE); }
            _ => { draw_sphere(s.pos,s.size,None,col(0.85,0.92,1.0,1.0)); draw_sphere(s.pos,s.size*1.6,None,col(0.6,0.8,1.0,0.2)); }
        }
    }
    // particles
    for p in &g.parts { let a=(p.life/p.max).clamp(0.0,1.0); draw_cube(p.pos,vec3(p.size,p.size,p.size),None,Color::new(p.color.r,p.color.g,p.color.b,a)); }
}

fn draw_floats(g:&Game, cam:&Camera3D) {
    set_default_camera();
    let m=cam.matrix(); let sw=screen_width(); let sh=screen_height();
    for f in &g.floats {
        let clip=m*f.pos.extend(1.0); if clip.w<=0.0 {continue;}
        let ndc=clip.truncate()/clip.w;
        let x=(ndc.x*0.5+0.5)*sw; let y=(1.0-(ndc.y*0.5+0.5))*sh;
        let a=(f.life/0.9).clamp(0.0,1.0); let c=Color::new(f.color.r,f.color.g,f.color.b,a);
        let d=measure_text(&f.text,None,f.size,1.0);
        draw_text(&f.text, x-d.width/2.0, y, f.size as f32, c);
    }
}

fn bar(x:f32,y:f32,w:f32,h:f32,frac:f32,c:Color){ draw_rectangle(x,y,w,h,col(1.0,1.0,1.0,0.08)); draw_rectangle(x,y,w*frac.clamp(0.0,1.0),h,c); draw_rectangle_lines(x,y,w,h,2.0,col(1.0,1.0,1.0,0.22)); }
fn ctext(s:&str,y:f32,size:u16,c:Color){ let d=measure_text(s,None,size,1.0); draw_text(s,screen_width()/2.0-d.width/2.0,y,size as f32,c); }

fn draw_hud(g:&Game) {
    set_default_camera();
    let sw=screen_width();
    if g.hp/g.max_hp<0.3 { let a=0.1+0.12*(get_time() as f32*6.0).sin().abs(); draw_rectangle(0.0,0.0,sw,screen_height(),col(0.5,0.0,0.05,a)); }
    if g.dmg_flash>0.0 { draw_rectangle(0.0,0.0,sw,screen_height(),col(0.6,0.0,0.05,g.dmg_flash*0.18)); }
    if g.flash>0.0 { draw_rectangle(0.0,0.0,sw,screen_height(),col(0.5,1.0,0.6,g.flash*0.1)); }

    draw_text("HP",24.0,34.0,22.0,col(1.0,0.6,0.6,1.0));
    bar(56.0,20.0,260.0,18.0,g.hp/g.max_hp,col(0.85,0.2,0.3,1.0));
    draw_text(&format!("{:.0}/{:.0}",g.hp,g.max_hp),324.0,35.0,18.0,WHITE);
    draw_text(&format!("LVL {}",g.level),24.0,66.0,22.0,col(0.6,1.0,0.7,1.0));
    bar(110.0,52.0,206.0,14.0,g.xp/g.xp_need,col(0.4,0.95,0.6,1.0));

    let t=g.time as u32;
    let phase=PHASES[((g.time/120.0) as usize).min(PHASES.len()-1)];
    let stat=format!("{}   ·   {:02}:{:02}   ·   {} slain   ·   wave {}",phase,t/60,t%60,g.kills,g.wave);
    let d=measure_text(&stat,None,22,1.0); draw_text(&stat,sw-d.width-24.0,34.0,22.0,col(0.85,0.85,0.95,1.0));

    if g.combo >= 5 { let s=format!("x{} COMBO",g.combo); let d=measure_text(&s,None,26,1.0); draw_text(&s, sw/2.0-d.width/2.0, 56.0, 26.0, lerp_col(CANDLE,MARIGOLD,(g.combo as f32/60.0).min(1.0))); }

    // dodge indicator
    let dready = g.dodge_cd<=0.0;
    draw_text(if dready {"LEAP READY (space)"} else {"leap recharging"}, 24.0, 92.0, 18.0, if dready {col(0.6,0.9,1.0,1.0)} else {col(0.5,0.5,0.6,1.0)});

    // weapon chips
    let mut chips=Vec::new();
    if g.multishot>1 {chips.push(format!("x{} bolt",g.multishot));}
    if g.volley>0 {chips.push(format!("volley {}",g.volley));}
    if g.scythe>0 {chips.push(format!("scythe {}",g.scythe));}
    if g.spear>0 {chips.push(format!("spear {}",g.spear));}
    if g.smite>0 {chips.push(format!("smite {}",g.smite));}
    if g.moonbeam>0 {chips.push(format!("moonbeam {}",g.moonbeam));}
    if g.garlic>0 {chips.push(format!("garlic {}",g.garlic));}
    if g.lanterns>0 {chips.push(format!("{} lantern",g.lanterns));}
    if g.nova>0 {chips.push(format!("nova {}",g.nova));}
    if !g.familiars.is_empty() {chips.push(format!("{} wisp",g.familiars.len()));}
    let chip=chips.join("  ·  ");
    if !chip.is_empty() { draw_text(&chip,24.0,screen_height()-22.0,18.0,col(0.75,0.8,0.95,0.85)); }

    if g.boss.active {
        if let Some(b)=g.enemies.iter().find(|e|e.kind==4) {
            let bw=(sw*0.5).min(560.0); let bx0=sw/2.0-bw/2.0;
            ctext(g.boss.name,86.0,24,col(1.0,0.4,0.4,1.0));
            bar(bx0,96.0,bw,16.0,b.hp/b.max_hp,col(0.8,0.1,0.2,1.0));
        }
    }
    draw_joystick();
}

fn draw_levelup(g:&Game) {
    set_default_camera();
    let sw=screen_width(); let sh=screen_height();
    draw_rectangle(0.0,0.0,sw,sh,col(0.02,0.02,0.06,0.8));
    ctext("LEVEL UP :  CHOOSE A BLESSING",110.0,38,col(0.6,1.0,0.7,1.0));
    ctext("click a card, or press 1 · 2 · 3",148.0,22,col(0.8,0.85,0.95,0.8));
    let cw=300.0_f32.min((sw-80.0)/3.0); let gap=24.0; let total=cw*3.0+gap*2.0;
    let x0=sw/2.0-total/2.0; let y=205.0; let ch=235.0;
    for (i,u) in g.choices.iter().enumerate() {
        let x=x0+i as f32*(cw+gap);
        let hover=mouse_in(x,y,cw,ch);
        draw_rectangle(x,y,cw,ch, if hover {col(0.14,0.1,0.2,0.96)} else {col(0.09,0.07,0.15,0.92)});
        draw_rectangle_lines(x,y,cw,ch,2.0,col(0.6,0.9,0.5, if hover {1.0} else {0.4}));
        draw_rectangle(x+20.0,y+22.0,36.0,36.0,u.color()); draw_rectangle_lines(x+20.0,y+22.0,36.0,36.0,2.0,col(1.0,1.0,1.0,0.3));
        draw_text(&format!("{}",i+1),x+cw-36.0,y+46.0,30.0,col(0.6,1.0,0.7,1.0));
        draw_text(u.title(),x+20.0,y+108.0,25.0,col(0.95,0.97,1.0,1.0));
        let mut line=String::new(); let mut ly=y+146.0;
        for w in u.desc().split(' ') {
            let trial=if line.is_empty(){w.to_string()}else{format!("{} {}",line,w)};
            if measure_text(&trial,None,20,1.0).width>cw-40.0 { draw_text(&line,x+20.0,ly,20.0,col(0.78,0.85,0.95,0.9)); ly+=24.0; line=w.to_string(); } else { line=trial; }
        }
        if !line.is_empty() { draw_text(&line,x+20.0,ly,20.0,col(0.78,0.85,0.95,0.9)); }
    }
}
fn levelup_pick(g:&Game)->Option<usize>{
    if is_key_pressed(KeyCode::Key1){return Some(0);} if is_key_pressed(KeyCode::Key2){return Some(1);} if is_key_pressed(KeyCode::Key3){return Some(2);}
    if is_mouse_button_pressed(MouseButton::Left)||tap_pressed(){
        let sw=screen_width(); let cw=300.0_f32.min((sw-80.0)/3.0); let gap=24.0; let total=cw*3.0+gap*2.0;
        let x0=sw/2.0-total/2.0; let y=205.0; let ch=235.0;
        for i in 0..g.choices.len(){ let x=x0+i as f32*(cw+gap); if mouse_in(x,y,cw,ch){return Some(i);} }
    }
    None
}

// ---- input helpers ----
fn mouse_in(x:f32,y:f32,w:f32,h:f32)->bool{ let (mx,my)=mouse_position(); let p=if let Some(t)=touches().first(){t.position}else{vec2(mx,my)}; p.x>=x&&p.x<=x+w&&p.y>=y&&p.y<=y+h }
fn tap_pressed()->bool{ touches().iter().any(|t|t.phase==TouchPhase::Started) }
fn dodge_tap()->bool{ // a tap on the RIGHT half of the screen triggers leap on touch devices
    touches().iter().any(|t| t.phase==TouchPhase::Started && t.position.x > screen_width()*0.55)
}
fn joy_base()->Vec2{ vec2(120.0,screen_height()-120.0) }
fn joystick_vec()->Option<Vec2>{
    let base=joy_base();
    for t in touches().iter(){ if t.position.x<screen_width()*0.55 { let d=t.position-base; let len=d.length().min(70.0); if len>6.0 { let v=d.normalize()*(len/70.0); return Some(vec2(v.x,v.y)); } } }
    None
}
fn draw_joystick(){
    if touches().is_empty(){return;}
    let base=joy_base();
    draw_circle_lines(base.x,base.y,70.0,2.0,col(1.0,1.0,1.0,0.25));
    if let Some(v)=joystick_vec(){ draw_circle(base.x+v.x*70.0,base.y+v.y*70.0,26.0,col(0.6,0.9,0.5,0.5)); } else { draw_circle(base.x,base.y,26.0,col(0.6,0.9,0.5,0.3)); }
    // leap button hint (right)
    draw_circle_lines(screen_width()-90.0, screen_height()-110.0, 44.0, 2.0, col(0.6,0.9,1.0,0.35));
    draw_text("LEAP", screen_width()-116.0, screen_height()-104.0, 20.0, col(0.7,0.9,1.0,0.7));
}

#[macroquad::main(window_conf)]
async fn main() {
    rand::srand(macroquad::miniquad::date::now() as u64);
    let art=build_art();
    let mut g=Game::new();
    let mut bx=Boxer::new();
    let _=&art.fin;
    loop {
        let dt=get_frame_time().min(0.05);
        clear_background(col(0.03,0.03,0.08,1.0));
        let cam=make_camera(&g);
        match g.phase {
            Phase::Title => {
                draw_world(&g,&mut bx,&art);
                set_default_camera();
                draw_rectangle(0.0,0.0,screen_width(),screen_height(),col(0.02,0.02,0.07,0.55));
                ctext("BVTech: GRAVEYARD SHIFT",160.0,54,col(0.75,0.95,0.7,1.0));
                ctext("Survive the night. The dead don't clock out.",210.0,26,col(0.9,0.92,1.0,1.0));
                ctext("Move: WASD / arrows / drag   ·   SPACE or tap right = LEAP (dodge)",274.0,22,WHITE);
                ctext("You attack on your own. Grab soul shards, pick blessings, outlast the bosses.",304.0,22,WHITE);
                ctext("Last until dawn (10:00) or fell the Night Lord to win.",334.0,22,col(0.8,0.85,0.95,1.0));
                ctext("Press SPACE or tap to begin the shift",388.0,30,col(0.95,0.85,0.4,1.0));
                ctext("An original BVTech game · Rust + WebAssembly",438.0,20,col(0.6,0.7,0.85,1.0));
                if is_key_pressed(KeyCode::Space)||is_mouse_button_pressed(MouseButton::Left)||tap_pressed(){ g.reset(); }
            }
            Phase::Playing => { update(&mut g,dt); draw_world(&g,&mut bx,&art); draw_floats(&g,&cam); draw_hud(&g); }
            Phase::LevelUp => {
                draw_world(&g,&mut bx,&art); draw_floats(&g,&cam); draw_hud(&g); draw_levelup(&g);
                if let Some(i)=levelup_pick(&g){ if let Some(&u)=g.choices.get(i){ g.apply_upgrade(u); g.burst(g.player+vec3(0.0,0.6,0.0),40,col(0.5,1.0,0.6,1.0),12.0,0.16,0.0); g.phase=Phase::Playing; } }
            }
            Phase::Dead => {
                draw_world(&g,&mut bx,&art); draw_hud(&g);
                set_default_camera();
                draw_rectangle(0.0,0.0,screen_width(),screen_height(),col(0.1,0.0,0.04,0.62));
                ctext("YOU FELL BEFORE DAWN",200.0,54,col(1.0,0.4,0.4,1.0));
                let t=g.time as u32;
                ctext(&format!("Survived {:02}:{:02}   ·   {} undead slain   ·   level {}",t/60,t%60,g.kills,g.level),258.0,25,WHITE);
                ctext("Press R or tap to take another shift",322.0,30,col(0.95,0.85,0.4,1.0));
                if is_key_pressed(KeyCode::R)||is_mouse_button_pressed(MouseButton::Left)||tap_pressed(){ g.reset(); }
            }
            Phase::Win => {
                draw_world(&g,&mut bx,&art); draw_hud(&g);
                set_default_camera();
                draw_rectangle(0.0,0.0,screen_width(),screen_height(),col(0.1,0.06,0.0,0.6));
                ctext("🌅 YOU SURVIVED THE NIGHT!".trim_start_matches("🌅 "),190.0,54,CANDLE);
                let t=g.time as u32;
                ctext(&format!("Dawn breaks   ·   {:02}:{:02}   ·   {} undead slain   ·   level {}",t/60,t%60,g.kills,g.level),252.0,25,WHITE);
                ctext("Press R or tap for another shift",318.0,30,col(0.95,0.85,0.4,1.0));
                if is_key_pressed(KeyCode::R)||is_mouse_button_pressed(MouseButton::Left)||tap_pressed(){ g.reset(); }
            }
        }
        next_frame().await;
    }
}
