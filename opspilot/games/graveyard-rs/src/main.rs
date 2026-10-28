// BVTech: Graveyard Shift — an ORIGINAL survivors-like (bullet-heaven) in the
// Vampire-Survivors genre, built in Rust -> WebAssembly (macroquad). Everything
// here — art, characters, monsters, names — is our own; no other game's assets
// or code are used. Theme: a moonlit medieval graveyard, PG-13 Halloween fun.
// Original pixel-art creatures are billboarded in a 3D world; tombstones, the
// moon and fog give it depth. Classic survivors loop: auto-attack, hordes,
// soul-shard XP, pick-one-of-three upgrades, evolving weapons, timed bosses and
// difficulty that ramps up through the night.

use macroquad::camera::Camera; // world->screen projection for damage numbers
use macroquad::prelude::*;

const ARENA: f32 = 34.0;

fn window_conf() -> Conf {
    Conf {
        window_title: "BVTech: Graveyard Shift".to_owned(),
        high_dpi: true,
        window_width: 1180,
        window_height: 760,
        ..Default::default()
    }
}

fn col(r: f32, g: f32, b: f32, a: f32) -> Color { Color::new(r, g, b, a) }
fn lerp_col(a: Color, b: Color, t: f32) -> Color {
    Color::new(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t, a.b + (b.b - a.b) * t, a.a + (b.a - a.a) * t)
}

// ---------------- pixel-art sprite authoring ----------------
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
    hunter: Texture2D,
    bat: Texture2D,
    skeleton: Texture2D,
    ghoul: Texture2D,
    wraith: Texture2D,
    boss: Texture2D,
    shard: Texture2D,
    heart: Texture2D,
    chest: Texture2D,
}

fn build_art() -> Art {
    // shared palette
    let bone = col(0.92, 0.91, 0.82, 1.0);
    let bone_s = col(0.62, 0.62, 0.55, 1.0);
    let blk = col(0.07, 0.05, 0.10, 1.0);
    let red = col(0.85, 0.15, 0.17, 1.0);
    let cyan = col(0.35, 0.95, 0.95, 1.0);
    let grn = col(0.36, 0.72, 0.30, 1.0);
    let grn_d = col(0.20, 0.45, 0.20, 1.0);
    let cloak = col(0.44, 0.10, 0.16, 1.0);
    let cloak_d = col(0.30, 0.06, 0.11, 1.0);
    let skin = col(0.86, 0.80, 0.72, 1.0);
    let ghost = col(0.70, 0.82, 0.95, 0.85);
    let ghost_d = col(0.45, 0.58, 0.80, 0.7);
    let gold = col(0.96, 0.78, 0.30, 1.0);
    let brown = col(0.42, 0.26, 0.14, 1.0);
    let purp = col(0.46, 0.16, 0.48, 1.0);
    let purp_d = col(0.30, 0.10, 0.34, 1.0);

    // hunter: hat, cloak, face (14x20)
    let hunter = make_sprite(&[
        "....hhhh....",
        "...hhhhhh...",
        "..hhhhhhhh..",
        "....ffff....",
        "...fWfWf....",
        "...ffffff...",
        "..cccccccc..",
        ".ccccccccc c",
        "cc cccccc cc",
        ".c cccccc c.",
        ".ccckkkccc..",
        ".cck..kcc...",
        ".cc....cc...",
        "..cc..cc....",
        "..bb..bb....",
    ], &[('h', col(0.12,0.10,0.14,1.0)), ('f', skin), ('W', col(0.1,0.1,0.1,1.0)),
         ('c', cloak), ('k', col(0.75,0.72,0.3,1.0)), ('b', col(0.2,0.16,0.2,1.0))]);

    // bat: spread wings, body, red eyes (18x9)
    let bat = make_sprite(&[
        "ww..........ww",
        "wwww......wwww",
        "wwwwww..wwwwww",
        "wwwwwwwwwwwwww",
        "wwwbbbbbbbbwww",
        "wwbbEbbbbEbbww",
        ".wbbbbbbbbbbw.",
        "..wbbwbbwbbw..",
        "....w....w....",
    ], &[('w', blk), ('b', purp_d), ('E', red)]);

    // skeleton (12x18)
    let skeleton = make_sprite(&[
        "...bbbb...",
        "..bbbbbb..",
        "..bEbbEb..",
        "..bbbbbb..",
        "...bwwb...",
        "..bbbbbb..",
        ".bsbsbsbs.",
        ".bsbsbsbs.",
        ".bbbbbbbb.",
        "..b.bb.b..",
        "..b.bb.b..",
        "..b.bb.b..",
        ".bb.bb.bb.",
    ], &[('b', bone), ('s', bone_s), ('E', cyan), ('w', col(0.1,0.1,0.1,1.0))]);

    // ghoul: hunched toxic body, claws (16x14)
    let ghoul = make_sprite(&[
        "....gggg....",
        "...gggggg...",
        "..ggE gg Egg",
        "..gggwwwggg.",
        ".gggggggggg.",
        "ggggggggggdd",
        "gddggggggdd.",
        "d..ggggggg..",
        "..dggggggd..",
        "..gg.gg.gg..",
        "..d...d..d..",
    ], &[('g', grn), ('d', grn_d), ('E', col(0.95,0.9,0.3,1.0)), ('w', blk)]);

    // wraith: floating spectre (14x18)
    let wraith = make_sprite(&[
        "....gggg....",
        "...gggggg...",
        "..ggg..ggg..",
        "..gEg..gEg..",
        "..gggggggg..",
        ".gggggggggg.",
        ".gggggggggg.",
        ".dddddddddd.",
        ".gggggggggg.",
        "..dgggggd g.",
        "..g.dggd.g..",
        "...g.dd.g...",
        "....g..g....",
    ], &[('g', ghost), ('d', ghost_d), ('E', cyan)]);

    // boss — a towering vampire lord: cape, pale face, red eyes (22x30-ish)
    let boss = make_sprite(&[
        ".......KKKK.......",
        "......KKKKKK......",
        ".....KKKKKKKK.....",
        ".....KffffffK.....",
        "....KfRfffRfK....",
        "....KffWWffK.....",
        "....KfffffK......",
        "...CCCCCCCCCC...",
        "..CCCCCCCCCCCC..",
        ".CCCCRRRRRRCCCC.",
        "CCCCRRRRRRRRCCCC",
        "CCCRRRRRRRRRRCCC",
        "CCCCRRRRRRRRCCCC",
        ".CCCCRRRRRRCCCC.",
        "..CCCCCCCCCCCC..",
        "...CCCCCCCCCC...",
        "...CC.CCCC.CC...",
        "..CC..CCCC..CC..",
        ".CC...CCCC...CC.",
    ], &[('K', col(0.10,0.07,0.12,1.0)), ('f', col(0.82,0.78,0.80,1.0)), ('R', col(0.75,0.12,0.14,1.0)),
         ('W', col(0.9,0.2,0.2,1.0)), ('C', col(0.14,0.04,0.09,1.0))]);

    // soul shard (xp) 8x8
    let shard = make_sprite(&[
        "...gg...",
        "..gGGg..",
        ".gGGGGg.",
        "gGGGGGGg",
        "gGGGGGGg",
        ".gGGGGg.",
        "..gGGg..",
        "...gg...",
    ], &[('g', col(0.2,0.8,0.5,1.0)), ('G', col(0.5,1.0,0.7,1.0))]);
    let _ = purp;

    // heart / blood vial pickup 10x9
    let heart = make_sprite(&[
        ".rr..rr.",
        "rrrrrrrr",
        "rrrrrrrr",
        "rRrrrrRr",
        ".rrrrrr.",
        "..rrrr..",
        "...rr...",
    ], &[('r', red), ('R', col(1.0,0.5,0.5,1.0))]);

    // chest / cache pickup 12x9
    let chest = make_sprite(&[
        "gggggggggg",
        "gGGGGGGGGg",
        "gGggggggGg",
        "bbbbbbbbbb",
        "bYbbYYbbYb",
        "bbbYYYYbbb",
        "bbbbllbbbb",
        "bbbbbbbbbb",
    ], &[('g', gold), ('G', col(1.0,0.9,0.5,1.0)), ('b', brown), ('Y', gold), ('l', col(0.2,0.14,0.08,1.0))]);
    let _ = (cloak_d, purp_d);

    Art { hunter, bat, skeleton, ghoul, wraith, boss, shard, heart, chest }
}

// ---------------- shaded box meshes (tombstones, moon base, props) ----------------
fn shade(base: Color, normal: Vec3) -> Color {
    let l = vec3(-0.3, 1.0, 0.35).normalize();
    let d = normal.dot(l).max(0.0);
    let amb = 0.45;
    let b = amb + (1.0 - amb) * d;
    Color::new((base.r * b).min(1.0), (base.g * b).min(1.0), (base.b * b).min(1.0), base.a)
}
struct Boxer { mesh: Mesh }
impl Boxer {
    fn new() -> Self {
        let mut indices = Vec::with_capacity(36);
        for f in 0..6u16 { let o = f * 4; indices.extend_from_slice(&[o, o+1, o+2, o, o+2, o+3]); }
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

// camera-facing textured quad (upright cylindrical billboard), anchored at base
fn billboard(tex: &Texture2D, base: Vec3, w: f32, h: f32, right: Vec3, tint: Color) {
    let up = vec3(0.0, 1.0, 0.0);
    let r = right * (w * 0.5);
    let u = up * h;
    let bl = base - r; let br = base + r; let tr = base + r + u; let tl = base - r + u;
    let verts = vec![
        Vertex::new(bl.x,bl.y,bl.z, 0.0,1.0, tint),
        Vertex::new(br.x,br.y,br.z, 1.0,1.0, tint),
        Vertex::new(tr.x,tr.y,tr.z, 1.0,0.0, tint),
        Vertex::new(tl.x,tl.y,tl.z, 0.0,0.0, tint),
    ];
    draw_mesh(&Mesh { vertices: verts, indices: vec![0,1,2,0,2,3], texture: Some(tex.clone()) });
}

fn shadow(pos: Vec3, r: f32) {
    draw_plane(vec3(pos.x, 0.02, pos.z), vec2(r, r), None, col(0.0, 0.0, 0.0, 0.33));
}

// ---------------- entities ----------------
#[derive(Clone)]
struct Enemy { pos: Vec3, hp: f32, max_hp: f32, speed: f32, radius: f32, flash: f32, touch_cd: f32, kind: u8, bob: f32 }
struct Shot { pos: Vec3, vel: Vec3, life: f32, dmg: f32, pierce: i32, size: f32, kind: u8 }
struct Gem { pos: Vec3, value: f32, t: f32 }
struct Pickup { pos: Vec3, kind: u8, t: f32 }
struct Particle { pos: Vec3, vel: Vec3, life: f32, max: f32, size: f32, color: Color, gravity: f32 }
struct FloatText { pos: Vec3, life: f32, text: String, color: Color }
struct Familiar { ang: f32, pos: Vec3, cd: f32 }
struct Tomb { pos: Vec3, w: f32, h: f32, kind: u8 }

#[derive(Clone, Copy, PartialEq)]
enum Up { Damage, FireRate, Multishot, Speed, MaxHp, Magnet, Area, Garlic, Lantern, Nova, Volley, Familiar, Pierce, Regen }
impl Up {
    fn title(&self) -> &'static str {
        match self {
            Up::Damage => "Sharpened Silver", Up::FireRate => "Overclocked Censer",
            Up::Multishot => "Split Bolt", Up::Speed => "Swift Boots",
            Up::MaxHp => "Blessed Plating", Up::Magnet => "Rune Cache",
            Up::Area => "Wider Wards", Up::Garlic => "Garlic Firewall",
            Up::Lantern => "Holy Lantern", Up::Nova => "Rune Nova",
            Up::Volley => "Stake Volley", Up::Familiar => "Wisp Daemon",
            Up::Pierce => "Piercing Rounds", Up::Regen => "Patch Tuesday",
        }
    }
    fn desc(&self) -> &'static str {
        match self {
            Up::Damage => "+30% all damage", Up::FireRate => "+20% fire rate",
            Up::Multishot => "+1 bolt per shot", Up::Speed => "+12% move speed",
            Up::MaxHp => "+30 max HP, heal 50", Up::Magnet => "+60% pickup range",
            Up::Area => "+25% area of effect", Up::Garlic => "Damaging aura around you",
            Up::Lantern => "Add an orbiting holy lantern", Up::Nova => "Periodic holy shockwave",
            Up::Volley => "Fire a 3-stake spread", Up::Familiar => "A wisp that seeks the undead",
            Up::Pierce => "Shots pierce +1 enemy", Up::Regen => "Slowly regenerate HP",
        }
    }
    fn color(&self) -> Color {
        match self {
            Up::Damage => col(0.85,0.75,0.75,1.0), Up::FireRate => col(0.9,0.8,0.4,1.0),
            Up::Multishot => col(0.7,0.85,1.0,1.0), Up::Speed => col(0.6,0.9,0.7,1.0),
            Up::MaxHp => col(0.85,0.3,0.4,1.0), Up::Magnet => col(0.5,1.0,0.7,1.0),
            Up::Area => col(0.7,0.6,0.95,1.0), Up::Garlic => col(0.8,0.95,0.4,1.0),
            Up::Lantern => col(1.0,0.85,0.4,1.0), Up::Nova => col(1.0,0.9,0.6,1.0),
            Up::Volley => col(0.75,0.85,1.0,1.0), Up::Familiar => col(0.7,0.9,1.0,1.0),
            Up::Pierce => col(0.9,0.7,0.9,1.0), Up::Regen => col(0.5,1.0,0.6,1.0),
        }
    }
}

#[derive(PartialEq)]
enum Phase { Title, Playing, LevelUp, Dead }

struct Boss { active: bool, name: &'static str }

struct Game {
    phase: Phase,
    player: Vec3,
    face_right: bool,
    hp: f32, max_hp: f32, speed: f32,
    level: u32, xp: f32, xp_need: f32,
    // weapon stats
    fire_cd: f32, fire_interval: f32, dmg: f32, shot_speed: f32,
    multishot: u32, pierce: i32, area: f32, magnet: f32, regen: f32,
    garlic: u32, garlic_t: f32,
    lanterns: u32, orb_angle: f32,
    nova: u32, nova_cd: f32,
    volley: u32,
    familiars: Vec<Familiar>,
    // world
    enemies: Vec<Enemy>, shots: Vec<Shot>, gems: Vec<Gem>, pickups: Vec<Pickup>,
    parts: Vec<Particle>, floats: Vec<FloatText>, tombs: Vec<Tomb>,
    spawn_cd: f32, spawn_interval: f32,
    time: f32, kills: u32, wave: u32, next_boss: u32, boss: Boss, boss_idx: usize,
    shake: f32, hitstop: f32, cam: Vec3,
    choices: Vec<Up>, flash: f32, dmg_flash: f32,
}

const BOSS_NAMES: [&str; 5] = ["Count Null-Pointer", "The Bone Compiler", "Plague-Ghoul Prime",
                               "Wraith of the Witching Hour", "Lord Vlad Overflow"];
const PHASES: [&str; 4] = ["Dusk", "Midnight", "The Witching Hour", "Before Dawn"];

fn weighted_pool(g: &Game) -> Vec<Up> {
    let mut pool = vec![Up::Damage, Up::FireRate, Up::Multishot, Up::Speed, Up::MaxHp,
                        Up::Magnet, Up::Area, Up::Pierce, Up::Regen];
    if g.garlic < 4 { pool.push(Up::Garlic); }
    if g.lanterns < 5 { pool.push(Up::Lantern); pool.push(Up::Lantern); }
    if g.nova < 4 { pool.push(Up::Nova); }
    if g.volley < 3 { pool.push(Up::Volley); }
    if g.familiars.len() < 4 { pool.push(Up::Familiar); pool.push(Up::Familiar); }
    let mut chosen = Vec::new(); let mut guard = 0;
    while chosen.len() < 3 && guard < 80 {
        let u = pool[rand::gen_range(0, pool.len())];
        if !chosen.contains(&u) { chosen.push(u); }
        guard += 1;
    }
    chosen
}

impl Game {
    fn new() -> Self {
        let mut tombs = Vec::new();
        for _ in 0..26 {
            let a = rand::gen_range(0.0, std::f32::consts::TAU);
            let r = rand::gen_range(5.0f32, ARENA - 3.0);
            tombs.push(Tomb { pos: vec3(a.cos()*r, 0.0, a.sin()*r),
                              w: rand::gen_range(0.6f32, 1.1), h: rand::gen_range(0.8f32, 1.8),
                              kind: rand::gen_range(0u8, 3) });
        }
        Game {
            phase: Phase::Title, player: vec3(0.0, 0.0, 0.0), face_right: true,
            hp: 120.0, max_hp: 120.0, speed: 8.0,
            level: 1, xp: 0.0, xp_need: 4.0,
            fire_cd: 0.0, fire_interval: 0.55, dmg: 14.0, shot_speed: 26.0,
            multishot: 1, pierce: 0, area: 1.0, magnet: 4.5, regen: 0.0,
            garlic: 0, garlic_t: 0.0, lanterns: 0, orb_angle: 0.0, nova: 0, nova_cd: 0.0, volley: 0,
            familiars: Vec::new(),
            enemies: Vec::new(), shots: Vec::new(), gems: Vec::new(), pickups: Vec::new(),
            parts: Vec::new(), floats: Vec::new(), tombs,
            spawn_cd: 0.0, spawn_interval: 1.0,
            time: 0.0, kills: 0, wave: 1, next_boss: 60, boss: Boss { active: false, name: "" }, boss_idx: 0,
            shake: 0.0, hitstop: 0.0, cam: vec3(0.0, 16.0, 12.5),
            choices: Vec::new(), flash: 0.0, dmg_flash: 0.0,
        }
    }
    fn reset(&mut self) { *self = Game::new(); self.phase = Phase::Playing; }

    fn burst(&mut self, pos: Vec3, n: usize, color: Color, spd: f32, sz: f32, grav: f32) {
        for _ in 0..n {
            if self.parts.len() > 560 { break; }
            let a = rand::gen_range(0.0, std::f32::consts::TAU);
            let el = rand::gen_range(0.1f32, 1.0);
            let v = vec3(a.cos()*el, rand::gen_range(0.2f32,1.0), a.sin()*el).normalize() * rand::gen_range(spd*0.4, spd);
            let life = rand::gen_range(0.25f32, 0.6);
            self.parts.push(Particle { pos, vel: v, life, max: life, size: sz, color, gravity: grav });
        }
    }
    fn floaty(&mut self, pos: Vec3, text: String, color: Color) {
        if self.floats.len() < 70 { self.floats.push(FloatText { pos, life: 0.85, text, color }); }
    }

    fn spawn_at(&self, r: f32) -> Vec3 {
        // spawn on a ring around the PLAYER, just off-screen, clamped to the arena
        let a = rand::gen_range(0.0, std::f32::consts::TAU);
        let mut p = self.player + vec3(a.cos()*r, 0.0, a.sin()*r);
        let flat = vec3(p.x, 0.0, p.z);
        if flat.length() > ARENA - 1.0 { let c = flat.normalize() * (ARENA - 1.0); p.x = c.x; p.z = c.z; }
        p
    }
    fn spawn_enemy(&mut self, boss: bool) {
        let ws = 1.0 + (self.wave as f32 - 1.0) * 0.17;
        if boss {
            self.boss_idx = (self.boss_idx) % BOSS_NAMES.len();
            let hp = 1100.0 * (1.0 + self.wave as f32 * 0.3);
            self.enemies.push(Enemy { pos: self.spawn_at(17.0), hp, max_hp: hp,
                speed: 2.6, radius: 1.9, flash: 0.0, touch_cd: 0.0, kind: 4, bob: 0.0 });
            self.boss = Boss { active: true, name: BOSS_NAMES[self.boss_idx] };
            self.boss_idx += 1;
            return;
        }
        let pos = self.spawn_at(16.0);
        let roll = rand::gen_range(0.0f32, 1.0);
        let (kind, hp, speed, radius) = if roll < 0.30 {
            (0u8, 7.0*ws, 6.2, 0.6)   // bat — fast, weak
        } else if roll < 0.60 {
            (1u8, 16.0*ws, 3.6, 0.7)  // skeleton
        } else if roll < 0.82 {
            (2u8, 26.0*ws, 3.0, 0.8)  // ghoul — tanky
        } else {
            (3u8, 13.0*ws, 4.6, 0.7)  // wraith — floaty weaver
        };
        self.enemies.push(Enemy { pos, hp, max_hp: hp, speed, radius, flash: 0.0, touch_cd: 0.0,
            kind, bob: rand::gen_range(0.0, 6.28) });
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
            Up::FireRate => self.fire_interval = (self.fire_interval * 0.8).max(0.09),
            Up::Multishot => self.multishot += 1,
            Up::Speed => self.speed *= 1.12,
            Up::MaxHp => { self.max_hp += 30.0; self.hp = (self.hp + 50.0).min(self.max_hp); }
            Up::Magnet => self.magnet *= 1.6,
            Up::Area => self.area *= 1.25,
            Up::Garlic => self.garlic += 1,
            Up::Lantern => self.lanterns += 1,
            Up::Nova => self.nova += 1,
            Up::Volley => self.volley += 1,
            Up::Familiar => self.familiars.push(Familiar { ang: rand::gen_range(0.0, 6.28), pos: self.player, cd: 0.0 }),
            Up::Pierce => self.pierce += 1,
            Up::Regen => self.regen += 1.5,
        }
    }
}

fn update(g: &mut Game, dt: f32) {
    if g.hitstop > 0.0 { g.hitstop -= dt; }
    let step = if g.hitstop > 0.0 { dt * 0.12 } else { dt };
    g.time += step;
    g.shake = (g.shake - dt * 2.0).max(0.0);
    g.flash = (g.flash - dt * 2.0).max(0.0);
    g.dmg_flash = (g.dmg_flash - dt * 2.5).max(0.0);

    let new_wave = 1 + (g.time / 20.0) as u32;
    if new_wave > g.wave { g.wave = new_wave; g.spawn_interval = (1.0 * 0.9f32.powi(g.wave as i32 - 1)).max(0.2); }

    if g.regen > 0.0 { g.hp = (g.hp + g.regen * step).min(g.max_hp); }

    // movement
    let mut mv = vec3(0.0, 0.0, 0.0);
    if is_key_down(KeyCode::W) || is_key_down(KeyCode::Up) { mv.z -= 1.0; }
    if is_key_down(KeyCode::S) || is_key_down(KeyCode::Down) { mv.z += 1.0; }
    if is_key_down(KeyCode::A) || is_key_down(KeyCode::Left) { mv.x -= 1.0; }
    if is_key_down(KeyCode::D) || is_key_down(KeyCode::Right) { mv.x += 1.0; }
    if let Some(j) = joystick_vec() { mv.x += j.x; mv.z += j.y; }
    if mv.length_squared() > 0.01 {
        mv = mv.normalize();
        g.player += mv * g.speed * step;
        if mv.x.abs() > 0.05 { g.face_right = mv.x > 0.0; }
    }
    let flat = vec3(g.player.x, 0.0, g.player.z);
    if flat.length() > ARENA - 0.8 { let c = flat.normalize() * (ARENA - 0.8); g.player.x = c.x; g.player.z = c.z; }

    // spawn
    g.spawn_cd -= step;
    if g.spawn_cd <= 0.0 && g.enemies.len() < 180 {
        let burst = 3 + g.wave as usize;
        for _ in 0..burst { g.spawn_enemy(false); }
        g.spawn_cd = g.spawn_interval;
    }
    if g.time as u32 >= g.next_boss { g.spawn_enemy(true); g.next_boss += 75; g.shake = 1.0; }

    // enemies chase
    let pp = g.player;
    for e in g.enemies.iter_mut() {
        let mut to = pp - e.pos; to.y = 0.0;
        let d = to.length();
        e.bob += step * 5.0;
        let mut dir = if d > 0.001 { to / d } else { Vec3::ZERO };
        if e.kind == 3 { // wraith weaves
            let perp = vec3(-dir.z, 0.0, dir.x);
            dir = (dir + perp * (e.bob.sin() * 0.55)).normalize_or_zero();
        }
        e.pos += dir * e.speed * step;
        e.flash = (e.flash - step * 5.0).max(0.0);
        e.touch_cd = (e.touch_cd - step).max(0.0);
        if d < e.radius + 0.7 && e.touch_cd <= 0.0 {
            let dmg = match e.kind { 4 => 22.0, 2 => 12.0, 0 => 5.0, _ => 8.0 };
            g.hp -= dmg; e.touch_cd = 0.6; g.shake = (g.shake + 0.35).min(1.2); g.dmg_flash = 1.0;
        }
    }

    // auto-fire silver bolt (+ volley)
    g.fire_cd -= step;
    if g.fire_cd <= 0.0 {
        if let Some(i) = g.nearest(g.player) {
            let dir = { let mut d = g.enemies[i].pos - g.player; d.y = 0.0; d.normalize_or_zero() };
            if dir.length_squared() > 0.0 {
                let base = dir.x.atan2(dir.z);
                let spread = 0.14;
                let total = g.multishot + g.volley * 3;
                for s in 0..total {
                    let off = if total == 1 { 0.0 } else { (s as f32 - (total as f32 - 1.0)/2.0) * spread };
                    let a = base + off;
                    let v = vec3(a.sin(), 0.0, a.cos()) * g.shot_speed;
                    g.shots.push(Shot { pos: g.player + vec3(0.0, 1.0, 0.0), vel: v, life: 1.6,
                        dmg: g.dmg, pierce: g.pierce, size: 0.28 * g.area, kind: 0 });
                }
                g.fire_cd = g.fire_interval;
                let mz = g.player + dir * 0.8 + vec3(0.0, 1.0, 0.0);
                g.burst(mz, 4, col(0.9, 0.9, 0.7, 1.0), 6.0, 0.08, -2.0);
            }
        }
    }

    // garlic aura
    if g.garlic > 0 {
        g.garlic_t -= step;
        let radius = (2.4 + g.garlic as f32 * 0.7) * g.area;
        if g.garlic_t <= 0.0 {
            g.garlic_t = 0.5;
            let gd = g.dmg * 0.35 * g.garlic as f32;
            let pc = g.player;
            let mut hits = Vec::new();
            for (ei, e) in g.enemies.iter().enumerate() {
                if (vec3(e.pos.x,0.0,e.pos.z) - vec3(pc.x,0.0,pc.z)).length() < radius + e.radius { hits.push(ei); }
            }
            for ei in hits { if let Some(e) = g.enemies.get_mut(ei) { e.hp -= gd; e.flash = e.flash.max(0.4); } }
        }
    }

    // nova
    if g.nova > 0 {
        g.nova_cd -= step;
        if g.nova_cd <= 0.0 {
            g.nova_cd = (3.4 - g.nova as f32 * 0.4).max(1.1);
            let radius = (5.0 + g.nova as f32 * 1.5) * g.area;
            let nd = g.dmg * 1.7;
            let pc = g.player;
            for e in g.enemies.iter_mut() {
                if (vec3(e.pos.x,0.0,e.pos.z)-vec3(pc.x,0.0,pc.z)).length() < radius + e.radius { e.hp -= nd; e.flash = 1.0; }
            }
            g.burst(pc + vec3(0.0,0.5,0.0), 44, col(1.0, 0.95, 0.6, 1.0), 16.0, 0.16, 0.0);
            g.shake = (g.shake + 0.3).min(1.2);
        }
    }

    // lanterns (orbitals)
    if g.lanterns > 0 {
        g.orb_angle += step * 2.4;
        let orad = 2.8 * g.area;
        let od = g.dmg * 0.6;
        let pc = g.player;
        let mut hits: Vec<(usize, f32)> = Vec::new();
        for k in 0..g.lanterns {
            let a = g.orb_angle + k as f32 * std::f32::consts::TAU / g.lanterns as f32;
            let op = pc + vec3(a.cos()*orad, 0.6, a.sin()*orad);
            for (ei, e) in g.enemies.iter().enumerate() {
                if (e.pos + vec3(0.0,0.6,0.0) - op).length() < e.radius + 0.6 { hits.push((ei, od * step * 9.0)); }
            }
        }
        for (ei, d) in hits { if let Some(e) = g.enemies.get_mut(ei) { e.hp -= d; e.flash = e.flash.max(0.5); } }
    }

    // familiars (homing wisps)
    if !g.familiars.is_empty() {
        let pc = g.player;
        let targets: Vec<Vec3> = g.enemies.iter().map(|e| e.pos).collect();
        let fd = g.dmg * 0.5;
        let mut hits: Vec<(usize, f32)> = Vec::new();
        for f in g.familiars.iter_mut() {
            f.ang += step * 2.0;
            // drift toward nearest enemy, else orbit player
            let mut goal = pc + vec3(f.ang.cos()*3.2, 0.9, f.ang.sin()*3.2);
            let mut bd = f32::MAX;
            for t in &targets { let d = (*t - f.pos).length_squared(); if d < bd { bd = d; goal = *t + vec3(0.0,0.6,0.0); } }
            f.pos = f.pos.lerp(goal, 0.08);
            for (ei, e) in g.enemies.iter().enumerate() {
                if (e.pos + vec3(0.0,0.6,0.0) - f.pos).length() < e.radius + 0.5 { hits.push((ei, fd * step * 10.0)); }
            }
        }
        for (ei, d) in hits { if let Some(e) = g.enemies.get_mut(ei) { e.hp -= d; e.flash = e.flash.max(0.4); } }
    }

    // shots
    for s in g.shots.iter_mut() {
        s.pos += s.vel * step; s.life -= step;
        for e in g.enemies.iter_mut() {
            if e.hp <= 0.0 { continue; }
            if (e.pos + vec3(0.0,0.7,0.0) - s.pos).length() < e.radius + s.size + 0.1 {
                e.hp -= s.dmg; e.flash = 1.0;
                if s.pierce > 0 { s.pierce -= 1; } else { s.life = 0.0; }
                break;
            }
        }
    }
    let a2 = ARENA + 5.0;
    g.shots.retain(|s| s.life > 0.0 && (s.pos.x*s.pos.x + s.pos.z*s.pos.z) < a2*a2);

    // deaths
    let mut dead = Vec::new();
    for (i, e) in g.enemies.iter().enumerate() { if e.hp <= 0.0 { dead.push(i); } }
    for &i in dead.iter().rev() {
        let e = g.enemies.remove(i);
        g.kills += 1;
        let (val, parts) = match e.kind { 4 => (50.0, 60), 2 => (3.0, 20), _ => (1.0, 12) };
        let dustc = match e.kind { 0 => col(0.4,0.2,0.5,1.0), 1 => col(0.9,0.9,0.8,1.0), 2 => col(0.4,0.7,0.3,1.0), 3 => col(0.6,0.8,0.95,1.0), _ => col(0.8,0.2,0.2,1.0) };
        g.burst(e.pos + vec3(0.0,0.6,0.0), parts, dustc, 9.0, 0.16, 1.4);
        g.gems.push(Gem { pos: vec3(e.pos.x, 0.5, e.pos.z), value: val, t: 0.0 });
        if e.kind == 4 {
            g.shake = 1.2; g.boss = Boss { active: false, name: "" };
            g.pickups.push(Pickup { pos: vec3(e.pos.x, 0.5, e.pos.z), kind: rand::gen_range(0u8, 3), t: 0.0 });
            g.floaty(e.pos + vec3(0.0, 3.0, 0.0), "VANQUISHED!".into(), col(1.0, 0.85, 0.3, 1.0));
        } else if rand::gen_range(0.0f32, 1.0) < 0.014 {
            g.pickups.push(Pickup { pos: vec3(e.pos.x, 0.5, e.pos.z), kind: rand::gen_range(0u8, 3), t: 0.0 });
        }
    }

    // gems magnet + collect
    let pc = g.player; let mag = g.magnet;
    for gem in g.gems.iter_mut() {
        gem.t += step;
        let to = pc - gem.pos; let d = to.length();
        if d < mag { gem.pos += (to / d.max(0.001)) * (11.0 * step) * (1.0 - d / mag + 0.4); }
    }
    let mut got = 0.0;
    g.gems.retain(|gem| { if (gem.pos - pc).length() < 1.1 { got += gem.value; false } else { true } });
    if got > 0.0 { g.xp += got; }

    // pickups
    let mut use_pick = Vec::new();
    g.pickups.retain(|p| { if (p.pos - pc).length() < 1.2 { use_pick.push(p.kind); false } else { true } });
    for k in use_pick {
        match k {
            0 => { g.hp = (g.hp + 50.0).min(g.max_hp); g.floaty(g.player + vec3(0.0,2.0,0.0), "+50 HP".into(), col(0.4,1.0,0.5,1.0)); }
            1 => { // holy water: big nova
                let pcx = g.player;
                for e in g.enemies.iter_mut() { if (e.pos - pcx).length() < 10.0 { e.hp -= g.dmg * 3.0; e.flash = 1.0; } }
                g.burst(pcx + vec3(0.0,0.6,0.0), 80, col(1.0,0.95,0.6,1.0), 20.0, 0.18, 0.0);
                g.shake = 1.0; g.floaty(g.player + vec3(0.0,2.0,0.0), "HOLY WATER!".into(), col(1.0,0.9,0.4,1.0));
            }
            _ => { // soul cache: XP
                g.xp += 10.0; g.floaty(g.player + vec3(0.0,2.0,0.0), "+10 SOULS".into(), col(0.5,1.0,0.7,1.0));
            }
        }
    }

    // level up
    if g.xp >= g.xp_need {
        g.xp -= g.xp_need;
        g.xp_need = (g.xp_need * 1.28 + 1.0).round();
        g.level += 1; g.flash = 1.0;
        g.choices = weighted_pool(g);
        g.phase = Phase::LevelUp;
    }

    // particles + floats
    for p in g.parts.iter_mut() { p.life -= dt; p.vel.y -= p.gravity * dt; p.pos += p.vel * dt; }
    g.parts.retain(|p| p.life > 0.0);
    for f in g.floats.iter_mut() { f.life -= dt; f.pos.y += dt * 1.7; }
    g.floats.retain(|f| f.life > 0.0);

    let want = g.player + vec3(0.0, 16.0, 12.5);
    g.cam = g.cam.lerp(want, 0.12);

    if g.hp <= 0.0 { g.hp = 0.0; g.phase = Phase::Dead; g.burst(g.player + vec3(0.0,0.8,0.0), 90, col(0.7,0.2,0.2,1.0), 14.0, 0.2, 1.0); }
}

// ---------------- rendering ----------------
fn make_camera(g: &Game) -> Camera3D {
    let mut cp = g.cam;
    if g.shake > 0.0 { let s = g.shake * 0.45; cp.x += rand::gen_range(-s, s); cp.y += rand::gen_range(-s, s); }
    Camera3D { position: cp, up: vec3(0.0,1.0,0.0), target: g.player + vec3(0.0, 1.0, 0.0), fovy: 0.85, ..Default::default() }
}

fn enemy_tex<'a>(art: &'a Art, kind: u8) -> (&'a Texture2D, f32, f32) {
    match kind {
        0 => (&art.bat, 2.0, 1.1),
        1 => (&art.skeleton, 1.5, 2.3),
        2 => (&art.ghoul, 2.0, 1.9),
        3 => (&art.wraith, 1.7, 2.3),
        _ => (&art.boss, 4.2, 5.6),
    }
}

fn draw_world(g: &Game, bx: &mut Boxer, art: &Art) {
    let cam = make_camera(g);
    let right = {
        let fwd = (cam.target - cam.position).normalize();
        fwd.cross(vec3(0.0,1.0,0.0)).normalize()
    };
    set_camera(&cam);

    // ground + fog ring
    draw_plane(vec3(0.0,0.0,0.0), vec2(ARENA+8.0, ARENA+8.0), None, col(0.05,0.07,0.06,1.0));
    draw_grid((ARENA as u32)*2, 1.0, col(0.12,0.22,0.16,0.35), col(0.06,0.10,0.08,1.0));
    // boundary fog ring
    let seg = 80;
    let pulse = 0.5 + 0.3 * (get_time() as f32 * 1.2).sin();
    for i in 0..seg {
        let a0 = i as f32 / seg as f32 * std::f32::consts::TAU;
        let a1 = (i+1) as f32 / seg as f32 * std::f32::consts::TAU;
        let p0 = vec3(a0.cos()*ARENA, 0.05, a0.sin()*ARENA);
        let p1 = vec3(a1.cos()*ARENA, 0.05, a1.sin()*ARENA);
        draw_line_3d(p0, p1, col(0.35, 0.3, 0.5, 0.35 + 0.3*pulse));
    }
    // the moon (big pale sphere far behind)
    draw_sphere(vec3(-8.0, 20.0, -ARENA - 10.0), 7.0, None, col(0.92, 0.92, 0.84, 1.0));
    draw_sphere(vec3(-8.0, 20.0, -ARENA - 10.0), 7.6, None, col(0.8, 0.85, 0.95, 0.12));

    // tombstones (shaded) — only those reasonably near the view
    for t in &g.tombs {
        if (vec3(t.pos.x,0.0,t.pos.z) - vec3(g.player.x,0.0,g.player.z)).length() > 30.0 { continue; }
        shadow(t.pos, t.w*2.2);
        let stone = col(0.30, 0.31, 0.34, 1.0);
        match t.kind {
            0 => { // slab
                bx.draw(t.pos + vec3(0.0, t.h*0.5, 0.0), vec3(t.w, t.h, 0.18), stone);
                bx.draw(t.pos + vec3(0.0, t.h, 0.0), vec3(t.w*0.5, t.w*0.5, 0.2), stone);
            }
            1 => { // cross
                bx.draw(t.pos + vec3(0.0, t.h*0.55, 0.0), vec3(0.14, t.h*0.55, 0.14), stone);
                bx.draw(t.pos + vec3(0.0, t.h*0.8, 0.0), vec3(t.w*0.5, 0.14, 0.14), stone);
            }
            _ => { // crypt block
                bx.draw(t.pos + vec3(0.0, t.h*0.4, 0.0), vec3(t.w*1.1, t.h*0.4, t.w*0.8), col(0.24,0.25,0.27,1.0));
            }
        }
    }

    // collect billboards (enemies, gems, pickups, player, familiars) and sort back-to-front
    enum Spr<'a> { Tex(&'a Texture2D, f32, f32, Color), }
    let mut sprites: Vec<(Vec3, Spr)> = Vec::new();
    for e in &g.enemies {
        let (tex, w, h) = enemy_tex(art, e.kind);
        let fly = match e.kind { 0 => 1.3 + (e.bob).sin()*0.35, 3 => 1.1 + (e.bob*0.5).sin()*0.3, _ => 0.0 };
        let tint = if e.flash > 0.0 { lerp_col(WHITE, col(2.0,0.6,0.6,1.0), e.flash.min(1.0)) } else { WHITE };
        shadow(e.pos, e.radius*2.0);
        sprites.push((vec3(e.pos.x, fly, e.pos.z), Spr::Tex(tex, w, h, tint)));
        // boss HP handled in HUD; small enemies show a tick when hurt
    }
    for gem in &g.gems {
        let y = 0.4 + (gem.t*4.0).sin()*0.12;
        sprites.push((vec3(gem.pos.x, y, gem.pos.z), Spr::Tex(&art.shard, 0.7, 0.7, WHITE)));
    }
    for p in &g.pickups {
        let tex = match p.kind { 0 => &art.heart, 1 => &art.heart, _ => &art.chest };
        let y = 0.5 + (get_time() as f32 * 3.0 + p.pos.x).sin()*0.12;
        let tint = if p.kind == 1 { col(0.6,0.9,1.0,1.0) } else { WHITE };
        sprites.push((vec3(p.pos.x, y, p.pos.z), Spr::Tex(tex, 1.0, 1.0, tint)));
    }
    for f in &g.familiars {
        sprites.push((f.pos, Spr::Tex(&art.shard, 0.8, 0.8, col(0.7,0.9,1.0,1.0))));
    }
    // player
    shadow(g.player, 1.1);
    let pbob = (get_time() as f32 * 6.0).sin() * 0.06;
    sprites.push((vec3(g.player.x, 0.0_f32.max(pbob), g.player.z), Spr::Tex(&art.hunter, 1.7 * if g.face_right {1.0} else {1.0}, 2.4, WHITE)));

    let cp = cam.position;
    sprites.sort_by(|a, b| {
        let da = (a.0 - cp).length_squared(); let db = (b.0 - cp).length_squared();
        db.partial_cmp(&da).unwrap_or(std::cmp::Ordering::Equal)
    });
    for (pos, s) in &sprites {
        match s { Spr::Tex(tex, w, h, tint) => billboard(tex, *pos, *w, *h, right, *tint) }
    }

    // lanterns drawn as glowing spheres
    if g.lanterns > 0 {
        for k in 0..g.lanterns {
            let a = g.orb_angle + k as f32 * std::f32::consts::TAU / g.lanterns as f32;
            let op = g.player + vec3(a.cos()*2.8*g.area, 0.9, a.sin()*2.8*g.area);
            draw_sphere(op, 0.35, None, col(1.0, 0.9, 0.5, 1.0));
            draw_sphere(op, 0.5, None, col(1.0, 0.85, 0.4, 0.2));
        }
    }
    // garlic aura ring
    if g.garlic > 0 {
        let radius = (2.4 + g.garlic as f32 * 0.7) * g.area;
        let seg = 40;
        for i in 0..seg {
            let a0 = i as f32 / seg as f32 * std::f32::consts::TAU;
            let a1 = (i+1) as f32 / seg as f32 * std::f32::consts::TAU;
            draw_line_3d(g.player + vec3(a0.cos()*radius, 0.1, a0.sin()*radius),
                         g.player + vec3(a1.cos()*radius, 0.1, a1.sin()*radius),
                         col(0.7, 0.95, 0.4, 0.3));
        }
    }

    // shots as glowing bolts
    for s in &g.shots {
        draw_sphere(s.pos, s.size, None, col(0.85, 0.92, 1.0, 1.0));
        draw_sphere(s.pos, s.size*1.6, None, col(0.6, 0.8, 1.0, 0.2));
    }
    // particles
    for p in &g.parts {
        let a = (p.life / p.max).clamp(0.0, 1.0);
        draw_cube(p.pos, vec3(p.size,p.size,p.size), None, Color::new(p.color.r,p.color.g,p.color.b,a));
    }
}

// damage/float text projected from 3D
fn draw_floats(g: &Game, cam: &Camera3D) {
    set_default_camera();
    let m = cam.matrix(); let sw = screen_width(); let sh = screen_height();
    for f in &g.floats {
        let clip = m * f.pos.extend(1.0);
        if clip.w <= 0.0 { continue; }
        let ndc = clip.truncate() / clip.w;
        let x = (ndc.x*0.5+0.5)*sw; let y = (1.0-(ndc.y*0.5+0.5))*sh;
        let a = (f.life/0.85).clamp(0.0,1.0);
        let c = Color::new(f.color.r,f.color.g,f.color.b,a);
        let d = measure_text(&f.text, None, 26, 1.0);
        draw_text(&f.text, x - d.width/2.0, y, 26.0, c);
    }
}

fn bar(x: f32, y: f32, w: f32, h: f32, frac: f32, c: Color) {
    draw_rectangle(x, y, w, h, col(1.0,1.0,1.0,0.08));
    draw_rectangle(x, y, w*frac.clamp(0.0,1.0), h, c);
    draw_rectangle_lines(x, y, w, h, 2.0, col(1.0,1.0,1.0,0.22));
}
fn ctext(s: &str, y: f32, size: u16, c: Color) {
    let d = measure_text(s, None, size, 1.0);
    draw_text(s, screen_width()/2.0 - d.width/2.0, y, size as f32, c);
}

fn draw_hud(g: &Game) {
    set_default_camera();
    let sw = screen_width();
    // vignette
    // low-hp + damage flash
    if g.hp / g.max_hp < 0.3 {
        let a = 0.1 + 0.12 * (get_time() as f32 * 6.0).sin().abs();
        draw_rectangle(0.0, 0.0, sw, screen_height(), col(0.5, 0.0, 0.05, a));
    }
    if g.dmg_flash > 0.0 { draw_rectangle(0.0,0.0,sw,screen_height(), col(0.6,0.0,0.05, g.dmg_flash*0.18)); }
    if g.flash > 0.0 { draw_rectangle(0.0,0.0,sw,screen_height(), col(0.5,1.0,0.6, g.flash*0.10)); }

    draw_text("HP", 24.0, 34.0, 22.0, col(1.0,0.6,0.6,1.0));
    bar(56.0, 20.0, 260.0, 18.0, g.hp/g.max_hp, col(0.85,0.2,0.3,1.0));
    draw_text(&format!("{:.0}/{:.0}", g.hp, g.max_hp), 324.0, 35.0, 18.0, WHITE);
    draw_text(&format!("LVL {}", g.level), 24.0, 66.0, 22.0, col(0.6,1.0,0.7,1.0));
    bar(110.0, 52.0, 206.0, 14.0, g.xp/g.xp_need, col(0.4,0.95,0.6,1.0));

    let t = g.time as u32;
    let phase = PHASES[((g.time/60.0) as usize).min(PHASES.len()-1)];
    let stat = format!("{}   ·   {:02}:{:02}   ·   {} slain   ·   wave {}", phase, t/60, t%60, g.kills, g.wave);
    let d = measure_text(&stat, None, 22, 1.0);
    draw_text(&stat, sw - d.width - 24.0, 34.0, 22.0, col(0.85,0.85,0.95,1.0));

    // weapon chips
    let mut chips = Vec::new();
    if g.multishot > 1 { chips.push(format!("x{} bolt", g.multishot)); }
    if g.volley > 0 { chips.push(format!("volley {}", g.volley)); }
    if g.garlic > 0 { chips.push(format!("garlic {}", g.garlic)); }
    if g.lanterns > 0 { chips.push(format!("{} lantern", g.lanterns)); }
    if g.nova > 0 { chips.push(format!("nova {}", g.nova)); }
    if !g.familiars.is_empty() { chips.push(format!("{} wisp", g.familiars.len())); }
    if g.pierce > 0 { chips.push(format!("pierce {}", g.pierce)); }
    let chip = chips.join("   ·   ");
    if !chip.is_empty() { draw_text(&chip, 24.0, screen_height()-22.0, 19.0, col(0.75,0.8,0.95,0.85)); }

    // boss bar
    if g.boss.active {
        if let Some(b) = g.enemies.iter().find(|e| e.kind == 4) {
            let bw = (sw*0.5).min(540.0);
            let bx0 = sw/2.0 - bw/2.0;
            ctext(g.boss.name, 70.0, 24, col(1.0,0.4,0.4,1.0));
            bar(bx0, 80.0, bw, 16.0, b.hp/b.max_hp, col(0.8,0.1,0.2,1.0));
        }
    }

    draw_joystick();
}

fn draw_levelup(g: &Game) {
    set_default_camera();
    let sw = screen_width(); let sh = screen_height();
    draw_rectangle(0.0,0.0,sw,sh, col(0.02,0.02,0.06,0.80));
    ctext("LEVEL UP :  CHOOSE A BLESSING", 110.0, 38, col(0.6,1.0,0.7,1.0));
    ctext("click a card, or press 1 · 2 · 3", 148.0, 22, col(0.8,0.85,0.95,0.8));
    let cw = 300.0_f32.min((sw-80.0)/3.0);
    let gap = 24.0; let total = cw*3.0 + gap*2.0;
    let x0 = sw/2.0 - total/2.0; let y = 205.0; let ch = 235.0;
    for (i, u) in g.choices.iter().enumerate() {
        let x = x0 + i as f32 * (cw+gap);
        let hover = mouse_in(x, y, cw, ch);
        draw_rectangle(x, y, cw, ch, if hover { col(0.14,0.10,0.20,0.96) } else { col(0.09,0.07,0.15,0.92) });
        draw_rectangle_lines(x, y, cw, ch, 2.0, col(0.6,0.9,0.5, if hover {1.0} else {0.4}));
        draw_rectangle(x+20.0, y+22.0, 36.0, 36.0, u.color());
        draw_rectangle_lines(x+20.0, y+22.0, 36.0, 36.0, 2.0, col(1.0,1.0,1.0,0.3));
        draw_text(&format!("{}", i+1), x+cw-36.0, y+46.0, 30.0, col(0.6,1.0,0.7,1.0));
        draw_text(u.title(), x+20.0, y+108.0, 25.0, col(0.95,0.97,1.0,1.0));
        // wrap desc
        let mut line = String::new(); let mut ly = y+146.0;
        for w in u.desc().split(' ') {
            let trial = if line.is_empty() { w.to_string() } else { format!("{} {}", line, w) };
            if measure_text(&trial, None, 20, 1.0).width > cw-40.0 {
                draw_text(&line, x+20.0, ly, 20.0, col(0.78,0.85,0.95,0.9)); ly += 24.0; line = w.to_string();
            } else { line = trial; }
        }
        if !line.is_empty() { draw_text(&line, x+20.0, ly, 20.0, col(0.78,0.85,0.95,0.9)); }
    }
}

fn levelup_pick(g: &Game) -> Option<usize> {
    if is_key_pressed(KeyCode::Key1) { return Some(0); }
    if is_key_pressed(KeyCode::Key2) { return Some(1); }
    if is_key_pressed(KeyCode::Key3) { return Some(2); }
    if is_mouse_button_pressed(MouseButton::Left) || tap_pressed() {
        let sw = screen_width();
        let cw = 300.0_f32.min((sw-80.0)/3.0);
        let gap = 24.0; let total = cw*3.0+gap*2.0;
        let x0 = sw/2.0 - total/2.0; let y = 205.0; let ch = 235.0;
        for i in 0..g.choices.len() { let x = x0 + i as f32*(cw+gap); if mouse_in(x,y,cw,ch) { return Some(i); } }
    }
    None
}

// ---------- input helpers ----------
fn mouse_in(x: f32, y: f32, w: f32, h: f32) -> bool {
    let (mx,my) = mouse_position();
    let p = if let Some(t) = touches().first() { t.position } else { vec2(mx,my) };
    p.x >= x && p.x <= x+w && p.y >= y && p.y <= y+h
}
fn tap_pressed() -> bool { touches().iter().any(|t| t.phase == TouchPhase::Started) }
fn joy_base() -> Vec2 { vec2(120.0, screen_height()-120.0) }
fn joystick_vec() -> Option<Vec2> {
    let base = joy_base();
    for t in touches().iter() {
        if t.position.x < screen_width()*0.55 {
            let d = t.position - base; let len = d.length().min(70.0);
            if len > 6.0 { let v = d.normalize()*(len/70.0); return Some(vec2(v.x, v.y)); }
        }
    }
    None
}
fn draw_joystick() {
    if touches().is_empty() { return; }
    let base = joy_base();
    draw_circle_lines(base.x, base.y, 70.0, 2.0, col(1.0,1.0,1.0,0.25));
    if let Some(v) = joystick_vec() { draw_circle(base.x+v.x*70.0, base.y+v.y*70.0, 26.0, col(0.6,0.9,0.5,0.5)); }
    else { draw_circle(base.x, base.y, 26.0, col(0.6,0.9,0.5,0.3)); }
}

#[macroquad::main(window_conf)]
async fn main() {
    rand::srand(macroquad::miniquad::date::now() as u64);
    let art = build_art();
    let mut g = Game::new();
    let mut bx = Boxer::new();
    loop {
        let dt = get_frame_time().min(0.05);
        clear_background(col(0.03, 0.03, 0.08, 1.0));
        let cam = make_camera(&g);
        match g.phase {
            Phase::Title => {
                draw_world(&g, &mut bx, &art);
                set_default_camera();
                draw_rectangle(0.0,0.0,screen_width(),screen_height(), col(0.02,0.02,0.07,0.55));
                ctext("BVTech: GRAVEYARD SHIFT", 170.0, 54, col(0.75,0.95,0.7,1.0));
                ctext("Survive the night. The dead don't clock out.", 220.0, 26, col(0.9,0.92,1.0,1.0));
                ctext("Move: WASD / arrows / drag on phone  ·  You attack automatically.", 284.0, 22, WHITE);
                ctext("Grab soul shards to level up and pick blessings. Outlast the bosses till dawn.", 314.0, 22, WHITE);
                ctext("Press SPACE or tap to begin the shift", 378.0, 30, col(0.95,0.85,0.4,1.0));
                ctext("An original BVTech game · Rust + WebAssembly", 430.0, 20, col(0.6,0.7,0.85,1.0));
                if is_key_pressed(KeyCode::Space) || is_mouse_button_pressed(MouseButton::Left) || tap_pressed() { g.reset(); }
            }
            Phase::Playing => {
                update(&mut g, dt);
                draw_world(&g, &mut bx, &art);
                draw_floats(&g, &cam);
                draw_hud(&g);
            }
            Phase::LevelUp => {
                draw_world(&g, &mut bx, &art);
                draw_floats(&g, &cam);
                draw_hud(&g);
                draw_levelup(&g);
                if let Some(i) = levelup_pick(&g) {
                    if let Some(&u) = g.choices.get(i) {
                        g.apply_upgrade(u);
                        g.burst(g.player + vec3(0.0,0.6,0.0), 40, col(0.5,1.0,0.6,1.0), 12.0, 0.16, 0.0);
                        g.phase = Phase::Playing;
                    }
                }
            }
            Phase::Dead => {
                draw_world(&g, &mut bx, &art);
                draw_hud(&g);
                set_default_camera();
                draw_rectangle(0.0,0.0,screen_width(),screen_height(), col(0.1,0.0,0.04,0.62));
                ctext("YOU FELL BEFORE DAWN", 200.0, 54, col(1.0,0.4,0.4,1.0));
                let t = g.time as u32;
                ctext(&format!("Survived {:02}:{:02}   ·   {} undead slain   ·   level {}", t/60, t%60, g.kills, g.level), 258.0, 25, WHITE);
                ctext("Press R or tap to take another shift", 322.0, 30, col(0.95,0.85,0.4,1.0));
                if is_key_pressed(KeyCode::R) || is_mouse_button_pressed(MouseButton::Left) || tap_pressed() { g.reset(); }
            }
        }
        next_frame().await;
    }
}
