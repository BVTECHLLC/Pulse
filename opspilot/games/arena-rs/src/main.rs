// BVTech: Breach Protocol — an ORIGINAL 3D survivors-like, Rust -> WebAssembly
// (macroquad). Same genre/feel as the big survivors games, but entirely our own
// theme (defend "the grid" from a digital breach) and our own art/code. No other
// game's characters, world, assets or code are used.
//
// Features: dense hordes, auto-fire + unlockable weapons (orbital drones, pulse
// nova, piercing rounds), pick-one-of-three level-up upgrades, enemy variety +
// a boss, data-shard XP with a magnet, pickups (repair / overclock / purge),
// particles, floating damage, screen shake, low-integrity vignette, and a touch
// joystick for phones.

use macroquad::camera::Camera; // for .matrix() world->screen projection
use macroquad::prelude::*;

const ARENA: f32 = 30.0;

fn window_conf() -> Conf {
    Conf {
        window_title: "BVTech: Breach Protocol".to_owned(),
        high_dpi: true,
        window_width: 1180,
        window_height: 760,
        ..Default::default()
    }
}

// ---------- palette ----------
fn col(r: f32, g: f32, b: f32, a: f32) -> Color {
    Color::new(r, g, b, a)
}
fn lerp_col(a: Color, b: Color, t: f32) -> Color {
    Color::new(
        a.r + (b.r - a.r) * t,
        a.g + (b.g - a.g) * t,
        a.b + (b.b - a.b) * t,
        a.a + (b.a - a.a) * t,
    )
}

// ---------- entities ----------
#[derive(Clone)]
struct Enemy {
    pos: Vec3,
    hp: f32,
    max_hp: f32,
    speed: f32,
    radius: f32,
    flash: f32,
    touch_cd: f32,
    kind: u8, // 0 grunt 1 fast 2 brute 3 drone 4 boss
    bob: f32,
}

struct Shot {
    pos: Vec3,
    vel: Vec3,
    life: f32,
    dmg: f32,
    pierce: i32,
    size: f32,
    trail: Vec<Vec3>,
}

struct Gem {
    pos: Vec3,
    value: f32,
    t: f32,
}

struct Pickup {
    pos: Vec3,
    kind: u8, // 0 repair 1 overclock(nova burst) 2 purge(bomb)
    t: f32,
}

struct Particle {
    pos: Vec3,
    vel: Vec3,
    life: f32,
    max: f32,
    size: f32,
    color: Color,
    gravity: f32,
}

struct FloatText {
    pos: Vec3,
    life: f32,
    text: String,
    color: Color,
}

#[derive(Clone, Copy, PartialEq)]
enum Up {
    Damage,
    FireRate,
    Multishot,
    Speed,
    MaxHp,
    Magnet,
    Orbital,
    Nova,
    Pierce,
    BigShot,
}

impl Up {
    fn title(&self) -> &'static str {
        match self {
            Up::Damage => "Sharper Rounds",
            Up::FireRate => "Overclocked Barrel",
            Up::Multishot => "Split Fire",
            Up::Speed => "Lighter Chassis",
            Up::MaxHp => "Reinforced Plating",
            Up::Magnet => "Shard Magnet",
            Up::Orbital => "Guardian Drone",
            Up::Nova => "Pulse Nova",
            Up::Pierce => "Railshot",
            Up::BigShot => "Heavy Slugs",
        }
    }
    fn desc(&self) -> &'static str {
        match self {
            Up::Damage => "+30% projectile damage",
            Up::FireRate => "+18% fire rate",
            Up::Multishot => "+1 projectile per shot",
            Up::Speed => "+12% move speed",
            Up::MaxHp => "+25 max integrity, repair 40",
            Up::Magnet => "+60% shard pickup range",
            Up::Orbital => "Add an orbiting guardian drone",
            Up::Nova => "Periodic damaging shockwave",
            Up::Pierce => "Shots pierce +1 enemy",
            Up::BigShot => "+40% projectile size & damage",
        }
    }
    fn icon(&self) -> &'static str {
        match self {
            Up::Damage => "🎯",
            Up::FireRate => "⚡",
            Up::Multishot => "🔱",
            Up::Speed => "🏃",
            Up::MaxHp => "🛡️",
            Up::Magnet => "🧲",
            Up::Orbital => "🛰️",
            Up::Nova => "💥",
            Up::Pierce => "➹",
            Up::BigShot => "🔵",
        }
    }
}

#[derive(PartialEq)]
enum Phase {
    Title,
    Playing,
    LevelUp,
    Dead,
}

struct Game {
    phase: Phase,
    player: Vec3,
    vel_smooth: Vec3,
    look: f32,
    hp: f32,
    max_hp: f32,
    speed: f32,
    level: u32,
    xp: f32,
    xp_need: f32,
    // weapon stats
    fire_cd: f32,
    fire_interval: f32,
    dmg: f32,
    shot_speed: f32,
    multishot: u32,
    pierce: i32,
    shot_size: f32,
    magnet: f32,
    orbitals: u32,
    orb_angle: f32,
    nova: u32,
    nova_cd: f32,
    // world
    enemies: Vec<Enemy>,
    shots: Vec<Shot>,
    gems: Vec<Gem>,
    pickups: Vec<Pickup>,
    parts: Vec<Particle>,
    floats: Vec<FloatText>,
    spawn_cd: f32,
    spawn_interval: f32,
    time: f32,
    kills: u32,
    wave: u32,
    next_boss: u32,
    shake: f32,
    hitstop: f32,
    cam: Vec3,
    choices: Vec<Up>,
    flash_level: f32,
}

fn weighted_pool(g: &Game) -> Vec<Up> {
    // offer a random 3 from a sensible pool (don't offer a first orbital/nova twice-heavy)
    let mut pool = vec![
        Up::Damage, Up::FireRate, Up::Multishot, Up::Speed, Up::MaxHp,
        Up::Magnet, Up::Pierce, Up::BigShot,
    ];
    if g.orbitals < 4 {
        pool.push(Up::Orbital);
        pool.push(Up::Orbital);
    }
    if g.nova < 3 {
        pool.push(Up::Nova);
        pool.push(Up::Nova);
    }
    // pick 3 distinct
    let mut chosen: Vec<Up> = Vec::new();
    let mut guard = 0;
    while chosen.len() < 3 && guard < 60 {
        let i = rand::gen_range(0, pool.len());
        let u = pool[i];
        if !chosen.contains(&u) {
            chosen.push(u);
        }
        guard += 1;
    }
    chosen
}

impl Game {
    fn new() -> Self {
        Game {
            phase: Phase::Title,
            player: vec3(0.0, 0.5, 0.0),
            vel_smooth: Vec3::ZERO,
            look: 0.0,
            hp: 100.0,
            max_hp: 100.0,
            speed: 8.5,
            level: 1,
            xp: 0.0,
            xp_need: 5.0,
            fire_cd: 0.0,
            fire_interval: 0.4,
            dmg: 16.0,
            shot_speed: 30.0,
            multishot: 1,
            pierce: 0,
            shot_size: 0.22,
            magnet: 4.0,
            orbitals: 0,
            orb_angle: 0.0,
            nova: 0,
            nova_cd: 0.0,
            enemies: Vec::new(),
            shots: Vec::new(),
            gems: Vec::new(),
            pickups: Vec::new(),
            parts: Vec::new(),
            floats: Vec::new(),
            spawn_cd: 0.0,
            spawn_interval: 1.1,
            time: 0.0,
            kills: 0,
            wave: 1,
            next_boss: 60,
            shake: 0.0,
            hitstop: 0.0,
            cam: vec3(0.0, 19.0, 15.0),
            choices: Vec::new(),
            flash_level: 0.0,
        }
    }
    fn reset(&mut self) {
        *self = Game::new();
        self.phase = Phase::Playing;
    }

    fn burst(&mut self, pos: Vec3, n: usize, color: Color, spd: f32, sz: f32, grav: f32) {
        for _ in 0..n {
            if self.parts.len() > 520 {
                break;
            }
            let a = rand::gen_range(0.0, std::f32::consts::TAU);
            let el = rand::gen_range(0.1f32, 1.0);
            let v = vec3(a.cos() * el, rand::gen_range(0.2f32, 1.0), a.sin() * el).normalize()
                * rand::gen_range(spd * 0.4, spd);
            let life = rand::gen_range(0.25f32, 0.6);
            self.parts.push(Particle {
                pos,
                vel: v,
                life,
                max: life,
                size: sz,
                color,
                gravity: grav,
            });
        }
    }

    fn floaty(&mut self, pos: Vec3, text: String, color: Color) {
        if self.floats.len() < 60 {
            self.floats.push(FloatText {
                pos,
                life: 0.8,
                text,
                color,
            });
        }
    }

    fn spawn_enemy(&mut self, boss: bool) {
        let a = rand::gen_range(0.0, std::f32::consts::TAU);
        let r = ARENA - 0.5;
        let pos = vec3(a.cos() * r, 0.5, a.sin() * r);
        let ws = 1.0 + (self.wave as f32 - 1.0) * 0.16;
        if boss {
            let hp = 900.0 * (1.0 + self.wave as f32 * 0.25);
            self.enemies.push(Enemy {
                pos: vec3(0.0, 0.8, -(ARENA - 2.0)),
                hp,
                max_hp: hp,
                speed: 2.4,
                radius: 2.4,
                flash: 0.0,
                touch_cd: 0.0,
                kind: 4,
                bob: 0.0,
            });
            return;
        }
        let roll = rand::gen_range(0.0f32, 1.0);
        let (kind, hp, speed, radius) = if roll < 0.18 + self.wave as f32 * 0.01 {
            (1u8, 9.0 * ws, 6.6, 0.5)
        } else if roll > 0.9 {
            (2u8, 60.0 * ws, 2.7, 1.1)
        } else if roll > 0.78 {
            (3u8, 16.0 * ws, 4.4, 0.6) // drone (hovers, weaves)
        } else {
            (0u8, 20.0 * ws, 3.8, 0.7)
        };
        self.enemies.push(Enemy {
            pos,
            hp,
            max_hp: hp,
            speed,
            radius,
            flash: 0.0,
            touch_cd: 0.0,
            kind,
            bob: rand::gen_range(0.0, 6.28),
        });
    }

    fn nearest(&self, from: Vec3) -> Option<usize> {
        let mut best = None;
        let mut bd = f32::MAX;
        for (i, e) in self.enemies.iter().enumerate() {
            let d = (e.pos - from).length_squared();
            if d < bd {
                bd = d;
                best = Some(i);
            }
        }
        best
    }

    fn apply_upgrade(&mut self, u: Up) {
        match u {
            Up::Damage => self.dmg *= 1.3,
            Up::FireRate => self.fire_interval = (self.fire_interval * 0.82).max(0.08),
            Up::Multishot => self.multishot += 1,
            Up::Speed => self.speed *= 1.12,
            Up::MaxHp => {
                self.max_hp += 25.0;
                self.hp = (self.hp + 40.0).min(self.max_hp);
            }
            Up::Magnet => self.magnet *= 1.6,
            Up::Orbital => self.orbitals += 1,
            Up::Nova => self.nova += 1,
            Up::Pierce => self.pierce += 1,
            Up::BigShot => {
                self.shot_size *= 1.4;
                self.dmg *= 1.2;
            }
        }
    }
}

fn enemy_color(kind: u8, flash: f32) -> Color {
    let base = match kind {
        1 => col(1.0, 0.45, 0.85, 1.0),
        2 => col(0.7, 0.3, 1.0, 1.0),
        3 => col(0.3, 1.0, 0.9, 1.0),
        4 => col(1.0, 0.55, 0.15, 1.0),
        _ => col(1.0, 0.36, 0.28, 1.0),
    };
    if flash > 0.0 {
        lerp_col(base, WHITE, flash.min(1.0))
    } else {
        base
    }
}

fn update(g: &mut Game, dt: f32) {
    if g.hitstop > 0.0 {
        g.hitstop -= dt;
        // still advance particles/floats a touch for feel
    }
    let step = if g.hitstop > 0.0 { dt * 0.15 } else { dt };
    g.time += step;
    g.shake = (g.shake - dt * 2.0).max(0.0);
    g.flash_level = (g.flash_level - dt * 2.0).max(0.0);

    let new_wave = 1 + (g.time / 18.0) as u32;
    if new_wave > g.wave {
        g.wave = new_wave;
        g.spawn_interval = (1.1 * 0.9f32.powi(g.wave as i32 - 1)).max(0.22);
    }

    // movement: keyboard + touch joystick
    let mut mv = vec3(0.0, 0.0, 0.0);
    if is_key_down(KeyCode::W) || is_key_down(KeyCode::Up) {
        mv.z -= 1.0;
    }
    if is_key_down(KeyCode::S) || is_key_down(KeyCode::Down) {
        mv.z += 1.0;
    }
    if is_key_down(KeyCode::A) || is_key_down(KeyCode::Left) {
        mv.x -= 1.0;
    }
    if is_key_down(KeyCode::D) || is_key_down(KeyCode::Right) {
        mv.x += 1.0;
    }
    if let Some(j) = joystick_vec() {
        mv.x += j.x;
        mv.z += j.y;
    }
    if mv.length_squared() > 0.01 {
        mv = mv.normalize();
        g.player += mv * g.speed * step;
        g.look = mv.x.atan2(-mv.z);
        g.vel_smooth = g.vel_smooth.lerp(mv, 0.2);
    } else {
        g.vel_smooth = g.vel_smooth.lerp(Vec3::ZERO, 0.2);
    }
    let flat = vec3(g.player.x, 0.0, g.player.z);
    if flat.length() > ARENA - 0.6 {
        let c = flat.normalize() * (ARENA - 0.6);
        g.player.x = c.x;
        g.player.z = c.z;
    }

    // spawning
    g.spawn_cd -= step;
    if g.spawn_cd <= 0.0 && g.enemies.len() < 170 {
        let burst = 2 + (g.wave as usize / 2);
        for _ in 0..burst {
            g.spawn_enemy(false);
        }
        g.spawn_cd = g.spawn_interval;
    }
    // boss
    if g.time as u32 >= g.next_boss {
        g.spawn_enemy(true);
        g.next_boss += 70;
        g.shake = 1.0;
    }

    // enemies toward player
    let pp = g.player;
    for e in g.enemies.iter_mut() {
        let mut to = pp - e.pos;
        to.y = 0.0;
        let d = to.length();
        e.bob += step * 4.0;
        let mut dir = if d > 0.001 { to / d } else { Vec3::ZERO };
        if e.kind == 3 {
            // drone weaves sideways
            let perp = vec3(-dir.z, 0.0, dir.x);
            dir = (dir + perp * (e.bob.sin() * 0.6)).normalize_or_zero();
        }
        e.pos += dir * e.speed * step;
        e.pos.y = 0.5 + if e.kind == 3 { 0.6 + (e.bob.sin() * 0.25) } else { 0.0 };
        e.flash = (e.flash - step * 5.0).max(0.0);
        e.touch_cd = (e.touch_cd - step).max(0.0);
        if d < e.radius + 0.6 && e.touch_cd <= 0.0 {
            let dmg = match e.kind {
                4 => 26.0,
                2 => 16.0,
                1 => 6.0,
                _ => 10.0,
            };
            g.hp -= dmg;
            e.touch_cd = 0.6;
            g.shake = (g.shake + 0.4).min(1.2);
            g.flash_level = 1.0;
        }
    }

    // auto-fire
    g.fire_cd -= step;
    if g.fire_cd <= 0.0 {
        if let Some(i) = g.nearest(g.player) {
            let dir = {
                let mut d = g.enemies[i].pos - g.player;
                d.y = 0.0;
                d.normalize_or_zero()
            };
            if dir.length_squared() > 0.0 {
                let base = dir.x.atan2(dir.z);
                let spread = 0.15;
                for s in 0..g.multishot {
                    let off = if g.multishot == 1 {
                        0.0
                    } else {
                        (s as f32 - (g.multishot as f32 - 1.0) / 2.0) * spread
                    };
                    let a = base + off;
                    let v = vec3(a.sin(), 0.0, a.cos()) * g.shot_speed;
                    g.shots.push(Shot {
                        pos: g.player + vec3(0.0, 0.1, 0.0),
                        vel: v,
                        life: 1.5,
                        dmg: g.dmg,
                        pierce: g.pierce,
                        size: g.shot_size,
                        trail: Vec::new(),
                    });
                }
                g.look = base;
                g.fire_cd = g.fire_interval;
                let mz = g.player + dir * 0.8 + vec3(0.0, 0.1, 0.0);
                g.burst(mz, 5, col(1.0, 0.85, 0.3, 1.0), 6.0, 0.08, -2.0);
            }
        }
    }

    // nova
    if g.nova > 0 {
        g.nova_cd -= step;
        if g.nova_cd <= 0.0 {
            g.nova_cd = (3.2 - g.nova as f32 * 0.4).max(1.0);
            let radius = 5.0 + g.nova as f32 * 1.4;
            let ndmg = g.dmg * 1.6;
            let pc = g.player;
            for e in g.enemies.iter_mut() {
                if (e.pos - pc).length() < radius + e.radius {
                    e.hp -= ndmg;
                    e.flash = 1.0;
                }
            }
            g.burst(pc, 46, col(0.4, 0.9, 1.0, 1.0), 16.0, 0.16, 0.0);
            g.shake = (g.shake + 0.3).min(1.2);
        }
    }

    // orbitals
    if g.orbitals > 0 {
        g.orb_angle += step * 2.6;
        let orad = 2.6;
        let odmg = g.dmg * 0.6;
        let pc = g.player;
        let mut hits: Vec<(usize, f32)> = Vec::new();
        for k in 0..g.orbitals {
            let a = g.orb_angle + k as f32 * std::f32::consts::TAU / g.orbitals as f32;
            let op = pc + vec3(a.cos() * orad, 0.2, a.sin() * orad);
            for (ei, e) in g.enemies.iter().enumerate() {
                if (e.pos - op).length() < e.radius + 0.5 {
                    hits.push((ei, odmg * step * 8.0));
                }
            }
        }
        for (ei, d) in hits {
            if let Some(e) = g.enemies.get_mut(ei) {
                e.hp -= d;
                e.flash = e.flash.max(0.5);
            }
        }
    }

    // shots update + collision
    for s in g.shots.iter_mut() {
        s.trail.push(s.pos);
        if s.trail.len() > 6 {
            s.trail.remove(0);
        }
        s.pos += s.vel * step;
        s.life -= step;
        for e in g.enemies.iter_mut() {
            if e.hp <= 0.0 {
                continue;
            }
            if (e.pos - s.pos).length() < e.radius + s.size + 0.05 {
                e.hp -= s.dmg;
                e.flash = 1.0;
                if s.pierce > 0 {
                    s.pierce -= 1;
                } else {
                    s.life = 0.0;
                }
                break;
            }
        }
    }
    let arena2 = ARENA + 4.0;
    g.shots
        .retain(|s| s.life > 0.0 && (s.pos.x * s.pos.x + s.pos.z * s.pos.z) < arena2 * arena2);

    // deaths
    let mut dead = Vec::new();
    for (i, e) in g.enemies.iter().enumerate() {
        if e.hp <= 0.0 {
            dead.push(i);
        }
    }
    for &i in dead.iter().rev() {
        let e = g.enemies.remove(i);
        g.kills += 1;
        let (val, parts, sz) = match e.kind {
            4 => (40.0, 60, 0.3),
            2 => (5.0, 22, 0.22),
            _ => (1.0 + if e.kind == 3 { 1.0 } else { 0.0 }, 14, 0.16),
        };
        g.burst(e.pos, parts, enemy_color(e.kind, 0.0), 10.0, sz, 1.5);
        g.gems.push(Gem {
            pos: vec3(e.pos.x, 0.4, e.pos.z),
            value: val,
            t: 0.0,
        });
        if e.kind == 4 {
            g.shake = 1.2;
            // boss drops a pickup
            g.pickups.push(Pickup {
                pos: vec3(e.pos.x, 0.5, e.pos.z),
                kind: rand::gen_range(0u8, 3),
                t: 0.0,
            });
        } else if rand::gen_range(0.0f32, 1.0) < 0.012 {
            g.pickups.push(Pickup {
                pos: vec3(e.pos.x, 0.5, e.pos.z),
                kind: rand::gen_range(0u8, 3),
                t: 0.0,
            });
        }
    }

    // gems magnet + collect
    let pc = g.player;
    let mag = g.magnet;
    for gem in g.gems.iter_mut() {
        gem.t += step;
        let to = pc - gem.pos;
        let d = to.length();
        if d < mag {
            gem.pos += (to / d.max(0.001)) * (10.0 * step) * (1.0 - d / mag + 0.35);
        }
    }
    let mut got = 0.0;
    g.gems.retain(|gem| {
        if (gem.pos - pc).length() < 1.0 {
            got += gem.value;
            false
        } else {
            true
        }
    });
    if got > 0.0 {
        g.xp += got;
    }

    // pickups
    let mut use_pick: Vec<u8> = Vec::new();
    g.pickups.retain(|p| {
        if (p.pos - pc).length() < 1.1 {
            use_pick.push(p.kind);
            false
        } else {
            true
        }
    });
    for k in use_pick {
        match k {
            0 => {
                g.hp = (g.hp + 45.0).min(g.max_hp);
                g.floaty(g.player + vec3(0.0, 1.5, 0.0), "+45 REPAIR".into(), col(0.3, 1.0, 0.5, 1.0));
            }
            1 => {
                // overclock: brief rapid nova pulses
                let r = 8.0;
                let pcx = g.player;
                for e in g.enemies.iter_mut() {
                    if (e.pos - pcx).length() < r {
                        e.hp -= g.dmg * 2.5;
                        e.flash = 1.0;
                    }
                }
                g.burst(pcx, 70, col(1.0, 0.8, 0.2, 1.0), 20.0, 0.18, 0.0);
                g.floaty(g.player + vec3(0.0, 1.5, 0.0), "OVERCLOCK!".into(), col(1.0, 0.8, 0.2, 1.0));
            }
            _ => {
                // purge: clear most of the screen
                let pcx = g.player;
                for e in g.enemies.iter_mut() {
                    if e.kind != 4 {
                        e.hp -= 9999.0;
                    } else {
                        e.hp -= 300.0;
                    }
                    let _ = pcx;
                }
                g.shake = 1.2;
                g.floaty(g.player + vec3(0.0, 1.5, 0.0), "PURGE!".into(), col(0.6, 0.9, 1.0, 1.0));
            }
        }
    }

    // level ups -> pause for choice
    if g.xp >= g.xp_need {
        g.xp -= g.xp_need;
        g.xp_need = (g.xp_need * 1.3).round();
        g.level += 1;
        g.flash_level = 1.0;
        g.choices = weighted_pool(g);
        g.phase = Phase::LevelUp;
    }

    // particles
    for p in g.parts.iter_mut() {
        p.life -= dt;
        p.vel.y -= p.gravity * dt;
        p.pos += p.vel * dt;
    }
    g.parts.retain(|p| p.life > 0.0);
    for f in g.floats.iter_mut() {
        f.life -= dt;
        f.pos.y += dt * 1.6;
    }
    g.floats.retain(|f| f.life > 0.0);

    // camera smooth follow
    let want = g.player + vec3(0.0, 19.0, 15.0);
    g.cam = g.cam.lerp(want, 0.12);

    if g.hp <= 0.0 {
        g.hp = 0.0;
        g.phase = Phase::Dead;
        g.burst(g.player, 80, col(0.3, 0.8, 1.0, 1.0), 14.0, 0.2, 1.0);
    }
}

// ---------- rendering ----------
fn make_camera(g: &Game) -> Camera3D {
    let mut cam_pos = g.cam;
    if g.shake > 0.0 {
        let s = g.shake * 0.5;
        cam_pos.x += rand::gen_range(-s, s);
        cam_pos.y += rand::gen_range(-s, s);
    }
    Camera3D {
        position: cam_pos,
        up: vec3(0.0, 1.0, 0.0),
        target: g.player + vec3(0.0, 0.5, 0.0),
        fovy: 0.82,
        ..Default::default()
    }
}

fn shadow(pos: Vec3, r: f32) {
    draw_plane(
        vec3(pos.x, 0.02, pos.z),
        vec2(r, r),
        None,
        col(0.0, 0.0, 0.0, 0.35),
    );
}

fn draw_enemy(e: &Enemy) {
    let c = enemy_color(e.kind, e.flash);
    shadow(e.pos, e.radius * 1.3);
    match e.kind {
        1 => {
            // fast: small spiky double-cube
            let s = e.radius * 1.3;
            draw_cube(e.pos, vec3(s, s * 0.7, s), None, c);
            draw_cube(e.pos + vec3(0.0, s * 0.5, 0.0), vec3(s * 0.5, s * 0.6, s * 0.5), None, c);
        }
        2 => {
            // brute: armored stack
            let s = e.radius * 1.6;
            draw_cube(e.pos, vec3(s, s * 0.9, s), None, c);
            draw_cube_wires(e.pos, vec3(s * 1.02, s * 0.92, s * 1.02), col(0.0, 0.0, 0.0, 0.6));
            draw_cube(e.pos + vec3(0.0, s * 0.6, 0.0), vec3(s * 0.7, s * 0.4, s * 0.7), None, lerp_col(c, WHITE, 0.2));
        }
        3 => {
            // drone: floating diamond-ish
            draw_sphere(e.pos, e.radius, None, c);
            draw_sphere_wires(e.pos, e.radius * 1.15, None, col(1.0, 1.0, 1.0, 0.25));
        }
        4 => {
            // boss: big multi-part
            let s = e.radius;
            draw_cube(e.pos, vec3(s * 1.6, s * 1.6, s * 1.6), None, c);
            draw_cube_wires(e.pos, vec3(s * 1.7, s * 1.7, s * 1.7), col(1.0, 0.9, 0.5, 0.7));
            let o = (e.bob).sin() * 0.3;
            draw_cube(e.pos + vec3(s * 1.3, o, 0.0), vec3(s * 0.6, s * 0.6, s * 0.6), None, lerp_col(c, RED, 0.3));
            draw_cube(e.pos + vec3(-s * 1.3, -o, 0.0), vec3(s * 0.6, s * 0.6, s * 0.6), None, lerp_col(c, RED, 0.3));
        }
        _ => {
            let s = e.radius * 1.5;
            draw_cube(e.pos, vec3(s, s, s), None, c);
            draw_cube_wires(e.pos, vec3(s * 1.03, s * 1.03, s * 1.03), col(0.0, 0.0, 0.0, 0.5));
        }
    }
    if e.hp < e.max_hp && e.kind != 4 {
        let frac = (e.hp / e.max_hp).clamp(0.0, 1.0);
        let w = e.radius * 1.6;
        draw_cube(e.pos + vec3(0.0, e.radius * 1.5, 0.0), vec3(w, 0.07, 0.07), None, col(0.2, 0.2, 0.2, 0.9));
        draw_cube(
            e.pos + vec3(-(w * (1.0 - frac)) * 0.5, e.radius * 1.5, 0.0),
            vec3(w * frac, 0.09, 0.09),
            None,
            col(0.3, 1.0, 0.4, 1.0),
        );
    }
}

fn draw_world(g: &Game) {
    let cam = make_camera(g);
    set_camera(&cam);

    // floor
    draw_plane(vec3(0.0, 0.0, 0.0), vec2(ARENA + 6.0, ARENA + 6.0), None, col(0.04, 0.05, 0.11, 1.0));
    draw_grid(((ARENA) as u32) * 2, 1.0, col(0.14, 0.42, 0.85, 0.5), col(0.07, 0.09, 0.2, 1.0));
    // boundary ring (pulsing)
    let seg = 72;
    let pulse = 0.6 + 0.4 * (get_time() as f32 * 2.0).sin();
    for i in 0..seg {
        let a0 = i as f32 / seg as f32 * std::f32::consts::TAU;
        let a1 = (i + 1) as f32 / seg as f32 * std::f32::consts::TAU;
        let p0 = vec3(a0.cos() * ARENA, 0.06, a0.sin() * ARENA);
        let p1 = vec3(a1.cos() * ARENA, 0.06, a1.sin() * ARENA);
        draw_line_3d(p0, p1, col(0.2, 0.7, 1.0, 0.5 + 0.4 * pulse));
    }

    // gems
    for gem in &g.gems {
        let y = 0.4 + (gem.t * 4.0).sin() * 0.08;
        draw_cube(vec3(gem.pos.x, y, gem.pos.z), vec3(0.3, 0.3, 0.3), None, col(0.2, 1.0, 0.55, 1.0));
        draw_cube_wires(vec3(gem.pos.x, y, gem.pos.z), vec3(0.4, 0.4, 0.4), col(0.6, 1.0, 0.8, 0.5));
    }
    // pickups
    for p in &g.pickups {
        let c = match p.kind {
            0 => col(0.3, 1.0, 0.5, 1.0),
            1 => col(1.0, 0.8, 0.2, 1.0),
            _ => col(0.5, 0.85, 1.0, 1.0),
        };
        let y = 0.5 + (get_time() as f32 * 3.0 + p.pos.x).sin() * 0.15;
        draw_cube(vec3(p.pos.x, y, p.pos.z), vec3(0.5, 0.5, 0.5), None, c);
        draw_cube_wires(vec3(p.pos.x, y, p.pos.z), vec3(0.62, 0.62, 0.62), WHITE);
    }

    for e in &g.enemies {
        draw_enemy(e);
    }

    // shots + trails
    for s in &g.shots {
        for (i, t) in s.trail.iter().enumerate() {
            let a = i as f32 / s.trail.len().max(1) as f32;
            draw_sphere(*t, s.size * (0.3 + a * 0.5), None, col(1.0, 0.8, 0.3, a * 0.5));
        }
        draw_sphere(s.pos, s.size, None, col(1.0, 0.9, 0.4, 1.0));
    }

    // orbitals
    if g.orbitals > 0 {
        for k in 0..g.orbitals {
            let a = g.orb_angle + k as f32 * std::f32::consts::TAU / g.orbitals as f32;
            let op = g.player + vec3(a.cos() * 2.6, 0.3, a.sin() * 2.6);
            draw_sphere(op, 0.42, None, col(0.4, 0.95, 1.0, 1.0));
            draw_sphere_wires(op, 0.5, None, col(1.0, 1.0, 1.0, 0.3));
        }
    }

    // particles
    for p in &g.parts {
        let a = (p.life / p.max).clamp(0.0, 1.0);
        let c = Color::new(p.color.r, p.color.g, p.color.b, a);
        draw_cube(p.pos, vec3(p.size, p.size, p.size), None, c);
    }

    // player
    shadow(g.player, 1.1);
    let bob = (get_time() as f32 * 3.0).sin() * 0.05;
    let pp = g.player + vec3(0.0, bob, 0.0);
    draw_cube(pp, vec3(0.95, 0.95, 0.95), None, col(0.2, 0.75, 1.0, 1.0));
    let glow = 0.4 + 0.4 * (get_time() as f32 * 5.0).sin();
    draw_cube_wires(pp, vec3(1.02, 1.02, 1.02), col(0.6, 0.95, 1.0, 0.3 + glow * 0.4));
    draw_cube(pp + vec3(0.0, 0.6, 0.0), vec3(0.4, 0.3, 0.4), None, col(0.7, 0.95, 1.0, 1.0));
    let bx = g.look.sin();
    let bz = g.look.cos();
    draw_cube(pp + vec3(bx * 0.75, 0.0, bz * 0.75), vec3(0.32, 0.32, 0.32), None, WHITE);
}

// ---------- HUD + screens ----------
fn bar(x: f32, y: f32, w: f32, h: f32, frac: f32, c: Color) {
    draw_rectangle(x, y, w, h, col(1.0, 1.0, 1.0, 0.08));
    draw_rectangle(x, y, w * frac.clamp(0.0, 1.0), h, c);
    draw_rectangle_lines(x, y, w, h, 2.0, col(1.0, 1.0, 1.0, 0.25));
}
fn ctext(s: &str, y: f32, size: u16, c: Color) {
    let d = measure_text(s, None, size, 1.0);
    draw_text(s, screen_width() / 2.0 - d.width / 2.0, y, size as f32, c);
}

fn draw_floats(g: &Game, cam: &Camera3D) {
    set_default_camera();
    let m = cam.matrix();
    let sw = screen_width();
    let sh = screen_height();
    for f in &g.floats {
        let clip = m * f.pos.extend(1.0);
        if clip.w <= 0.0 {
            continue;
        }
        let ndc = clip.truncate() / clip.w;
        let x = (ndc.x * 0.5 + 0.5) * sw;
        let y = (1.0 - (ndc.y * 0.5 + 0.5)) * sh;
        let a = (f.life / 0.8).clamp(0.0, 1.0);
        let c = Color::new(f.color.r, f.color.g, f.color.b, a);
        let d = measure_text(&f.text, None, 24, 1.0);
        draw_text(&f.text, x - d.width / 2.0, y, 24.0, c);
    }
}

fn draw_hud(g: &Game) {
    set_default_camera();
    let sw = screen_width();
    draw_text("INTEGRITY", 24.0, 34.0, 22.0, col(0.7, 0.9, 1.0, 1.0));
    bar(24.0, 42.0, 280.0, 18.0, g.hp / g.max_hp, col(0.2, 0.85, 1.0, 1.0));
    draw_text(&format!("{:.0}/{:.0}", g.hp, g.max_hp), 316.0, 57.0, 20.0, WHITE);
    draw_text(&format!("LVL {}", g.level), 24.0, 86.0, 22.0, col(1.0, 0.85, 0.3, 1.0));
    bar(96.0, 72.0, 208.0, 14.0, g.xp / g.xp_need, col(0.3, 1.0, 0.55, 1.0));

    let t = g.time as u32;
    let stat = format!("TIME {:02}:{:02}    KILLS {}    WAVE {}", t / 60, t % 60, g.kills, g.wave);
    let d = measure_text(&stat, None, 24, 1.0);
    draw_text(&stat, sw - d.width - 24.0, 40.0, 24.0, col(0.8, 0.9, 1.0, 1.0));

    // weapon chips
    let mut chips: Vec<String> = Vec::new();
    if g.multishot > 1 {
        chips.push(format!("x{} shots", g.multishot));
    }
    if g.pierce > 0 {
        chips.push(format!("pierce {}", g.pierce));
    }
    if g.orbitals > 0 {
        chips.push(format!("{} drones", g.orbitals));
    }
    if g.nova > 0 {
        chips.push(format!("nova {}", g.nova));
    }
    let chip = chips.join("   ·   ");
    if !chip.is_empty() {
        draw_text(&chip, 24.0, screen_height() - 22.0, 20.0, col(0.7, 0.85, 1.0, 0.8));
    }

    if g.hp / g.max_hp < 0.3 {
        let a = 0.12 + 0.12 * (get_time() as f32 * 6.0).sin().abs();
        draw_rectangle(0.0, 0.0, sw, screen_height(), col(1.0, 0.1, 0.2, a));
    }
    if g.flash_level > 0.0 {
        draw_rectangle(0.0, 0.0, sw, screen_height(), col(0.3, 1.0, 0.6, g.flash_level * 0.12));
    }

    draw_joystick();
}

fn draw_levelup(g: &Game) {
    set_default_camera();
    let sw = screen_width();
    let sh = screen_height();
    draw_rectangle(0.0, 0.0, sw, sh, col(0.02, 0.04, 0.1, 0.78));
    ctext("LEVEL UP — CHOOSE AN UPGRADE", 110.0, 40, col(0.3, 1.0, 0.6, 1.0));
    ctext("click a card, or press 1 · 2 · 3", 150.0, 24, col(0.8, 0.9, 1.0, 0.8));
    let cw = 300.0_f32.min((sw - 80.0) / 3.0);
    let gap = 24.0;
    let total = cw * 3.0 + gap * 2.0;
    let x0 = sw / 2.0 - total / 2.0;
    let y = 210.0;
    let ch = 230.0;
    for (i, u) in g.choices.iter().enumerate() {
        let x = x0 + i as f32 * (cw + gap);
        let hover = mouse_in(x, y, cw, ch);
        let bg = if hover {
            col(0.12, 0.2, 0.35, 0.95)
        } else {
            col(0.08, 0.12, 0.22, 0.9)
        };
        draw_rectangle(x, y, cw, ch, bg);
        draw_rectangle_lines(x, y, cw, ch, 2.0, col(0.3, 0.8, 1.0, if hover { 1.0 } else { 0.4 }));
        draw_text(u.icon(), x + 20.0, y + 56.0, 44.0, WHITE);
        draw_text(&format!("{}", i + 1), x + cw - 36.0, y + 44.0, 30.0, col(1.0, 0.85, 0.3, 1.0));
        draw_text(u.title(), x + 20.0, y + 104.0, 26.0, col(0.9, 0.97, 1.0, 1.0));
        // wrap desc
        let words: Vec<&str> = u.desc().split(' ').collect();
        let mut line = String::new();
        let mut ly = y + 140.0;
        for w in words {
            let trial = if line.is_empty() {
                w.to_string()
            } else {
                format!("{} {}", line, w)
            };
            if measure_text(&trial, None, 20, 1.0).width > cw - 40.0 {
                draw_text(&line, x + 20.0, ly, 20.0, col(0.75, 0.85, 1.0, 0.9));
                ly += 24.0;
                line = w.to_string();
            } else {
                line = trial;
            }
        }
        if !line.is_empty() {
            draw_text(&line, x + 20.0, ly, 20.0, col(0.75, 0.85, 1.0, 0.9));
        }
    }
}

fn levelup_pick(g: &Game) -> Option<usize> {
    if is_key_pressed(KeyCode::Key1) {
        return Some(0);
    }
    if is_key_pressed(KeyCode::Key2) {
        return Some(1);
    }
    if is_key_pressed(KeyCode::Key3) {
        return Some(2);
    }
    if is_mouse_button_pressed(MouseButton::Left) || tap_pressed() {
        let sw = screen_width();
        let cw = 300.0_f32.min((sw - 80.0) / 3.0);
        let gap = 24.0;
        let total = cw * 3.0 + gap * 2.0;
        let x0 = sw / 2.0 - total / 2.0;
        let y = 210.0;
        let ch = 230.0;
        for i in 0..g.choices.len() {
            let x = x0 + i as f32 * (cw + gap);
            if mouse_in(x, y, cw, ch) {
                return Some(i);
            }
        }
    }
    None
}

// ---------- input helpers (mouse + touch) ----------
fn mouse_in(x: f32, y: f32, w: f32, h: f32) -> bool {
    let (mx, my) = mouse_position();
    let p = if let Some(t) = touches().first() {
        t.position
    } else {
        vec2(mx, my)
    };
    p.x >= x && p.x <= x + w && p.y >= y && p.y <= y + h
}
fn tap_pressed() -> bool {
    touches().iter().any(|t| t.phase == TouchPhase::Started)
}

// virtual joystick anchored bottom-left; active when a pointer is held there (or anywhere on touch)
fn joy_base() -> Vec2 {
    vec2(120.0, screen_height() - 120.0)
}
fn joystick_vec() -> Option<Vec2> {
    // touch anywhere on the left half drives movement from the joystick base
    let base = joy_base();
    let ts = touches();
    for t in ts.iter() {
        if t.position.x < screen_width() * 0.55 {
            let d = t.position - base;
            let len = d.length().min(70.0);
            if len > 6.0 {
                let v = d.normalize() * (len / 70.0);
                return Some(vec2(v.x, v.y));
            }
        }
    }
    None
}
fn draw_joystick() {
    // only show on touch devices (when there is an active touch) — cheap heuristic:
    if touches().is_empty() {
        return;
    }
    let base = joy_base();
    draw_circle_lines(base.x, base.y, 70.0, 2.0, col(1.0, 1.0, 1.0, 0.25));
    if let Some(v) = joystick_vec() {
        draw_circle(base.x + v.x * 70.0, base.y + v.y * 70.0, 26.0, col(0.4, 0.8, 1.0, 0.5));
    } else {
        draw_circle(base.x, base.y, 26.0, col(0.4, 0.8, 1.0, 0.3));
    }
}

#[macroquad::main(window_conf)]
async fn main() {
    rand::srand(macroquad::miniquad::date::now() as u64);
    let mut g = Game::new();
    loop {
        let dt = get_frame_time().min(0.05);
        clear_background(col(0.02, 0.03, 0.07, 1.0));
        let cam = make_camera(&g);

        match g.phase {
            Phase::Title => {
                draw_world(&g);
                set_default_camera();
                draw_rectangle(0.0, 0.0, screen_width(), screen_height(), col(0.02, 0.03, 0.08, 0.55));
                ctext("BVTECH: BREACH PROTOCOL", 170.0, 54, col(0.3, 0.8, 1.0, 1.0));
                ctext("Defend the grid. Survive the breach.", 220.0, 26, col(0.85, 0.92, 1.0, 1.0));
                ctext("Move: WASD / arrows / drag on phone   ·   You auto-fire.", 282.0, 22, WHITE);
                ctext("Grab data shards to level up and pick powerful upgrades.", 312.0, 22, WHITE);
                ctext("Press SPACE or tap to deploy", 376.0, 30, col(1.0, 0.85, 0.3, 1.0));
                ctext("An original BVTech game · Rust + WebAssembly", 430.0, 20, col(0.6, 0.72, 0.9, 1.0));
                if is_key_pressed(KeyCode::Space) || is_mouse_button_pressed(MouseButton::Left) || tap_pressed() {
                    g.reset();
                }
            }
            Phase::Playing => {
                update(&mut g, dt);
                draw_world(&g);
                draw_floats(&g, &cam);
                draw_hud(&g);
                if is_key_pressed(KeyCode::Escape) || is_key_pressed(KeyCode::P) {
                    // quick pause on title overlay feel: just skip for now
                }
            }
            Phase::LevelUp => {
                draw_world(&g);
                draw_floats(&g, &cam);
                draw_hud(&g);
                draw_levelup(&g);
                if let Some(i) = levelup_pick(&g) {
                    if let Some(&u) = g.choices.get(i) {
                        g.apply_upgrade(u);
                        g.burst(g.player, 40, col(0.3, 1.0, 0.6, 1.0), 12.0, 0.16, 0.0);
                        g.phase = Phase::Playing;
                    }
                }
            }
            Phase::Dead => {
                draw_world(&g);
                draw_hud(&g);
                set_default_camera();
                draw_rectangle(0.0, 0.0, screen_width(), screen_height(), col(0.12, 0.0, 0.05, 0.6));
                ctext("GRID BREACHED", 200.0, 58, col(1.0, 0.35, 0.4, 1.0));
                let t = g.time as u32;
                ctext(
                    &format!("Held {:02}:{:02}   ·   {} breaches neutralized   ·   level {}", t / 60, t % 60, g.kills, g.level),
                    258.0,
                    26,
                    WHITE,
                );
                ctext("Press R or tap to redeploy", 322.0, 30, col(1.0, 0.85, 0.3, 1.0));
                if is_key_pressed(KeyCode::R) || is_mouse_button_pressed(MouseButton::Left) || tap_pressed() {
                    g.reset();
                }
            }
        }

        next_frame().await;
    }
}
