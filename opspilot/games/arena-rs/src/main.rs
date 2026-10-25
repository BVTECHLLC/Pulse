// BVTech: Breach Protocol — a Rust → WebAssembly 3D survivors game (macroquad).
// You are a BVTech sentinel defending the grid: survive escalating waves of
// "breaches", auto-firing countermeasures, collecting data shards to level up.
// Original art/code; stylized low-poly neon. First playable slice — built to be
// cranked up in fidelity (models, shaders, effects) over time.

use macroquad::prelude::*;

const ARENA: f32 = 26.0; // play radius

fn window_conf() -> Conf {
    Conf {
        window_title: "BVTech: Breach Protocol".to_owned(),
        high_dpi: true,
        window_width: 1100,
        window_height: 720,
        ..Default::default()
    }
}

#[derive(Clone)]
struct Enemy {
    pos: Vec3,
    hp: f32,
    max_hp: f32,
    speed: f32,
    radius: f32,
    hit_flash: f32,
    touch_cd: f32,
    kind: u8, // 0 grunt, 1 fast, 2 brute
}

struct Shot {
    pos: Vec3,
    vel: Vec3,
    life: f32,
    dmg: f32,
}

struct Gem {
    pos: Vec3,
    spin: f32,
    value: f32,
}

#[derive(PartialEq)]
enum Phase {
    Title,
    Playing,
    Dead,
}

struct Game {
    phase: Phase,
    player: Vec3,
    look: f32, // facing angle (for the little barrel)
    hp: f32,
    max_hp: f32,
    speed: f32,
    level: u32,
    xp: f32,
    xp_need: f32,
    fire_cd: f32,
    fire_interval: f32,
    dmg: f32,
    shot_speed: f32,
    multishot: u32,
    enemies: Vec<Enemy>,
    shots: Vec<Shot>,
    gems: Vec<Gem>,
    spawn_cd: f32,
    spawn_interval: f32,
    time: f32,
    kills: u32,
    wave: u32,
    shake: f32,
}

impl Game {
    fn new() -> Self {
        Game {
            phase: Phase::Title,
            player: vec3(0.0, 0.5, 0.0),
            look: 0.0,
            hp: 100.0,
            max_hp: 100.0,
            speed: 8.5,
            level: 1,
            xp: 0.0,
            xp_need: 5.0,
            fire_cd: 0.0,
            fire_interval: 0.42,
            dmg: 18.0,
            shot_speed: 26.0,
            multishot: 1,
            enemies: Vec::new(),
            shots: Vec::new(),
            gems: Vec::new(),
            spawn_cd: 0.0,
            spawn_interval: 1.3,
            time: 0.0,
            kills: 0,
            wave: 1,
            shake: 0.0,
        }
    }

    fn reset(&mut self) {
        *self = Game::new();
        self.phase = Phase::Playing;
    }

    fn nearest_enemy(&self) -> Option<usize> {
        let mut best = None;
        let mut bd = f32::MAX;
        for (i, e) in self.enemies.iter().enumerate() {
            let d = (e.pos - self.player).length_squared();
            if d < bd {
                bd = d;
                best = Some(i);
            }
        }
        best
    }

    fn spawn_enemy(&mut self) {
        let a = rand::gen_range(0.0, std::f32::consts::TAU);
        let r = ARENA - 1.0;
        let pos = vec3(a.cos() * r, 0.5, a.sin() * r);
        let roll = rand::gen_range(0.0f32, 1.0);
        let wave_scale = 1.0 + (self.wave as f32 - 1.0) * 0.18;
        let (kind, hp, speed, radius) = if roll < 0.15 + self.wave as f32 * 0.01 {
            (1u8, 10.0 * wave_scale, 6.2, 0.55) // fast
        } else if roll > 0.9 {
            (2u8, 55.0 * wave_scale, 2.6, 1.15) // brute
        } else {
            (0u8, 22.0 * wave_scale, 3.7, 0.7) // grunt
        };
        self.enemies.push(Enemy {
            pos,
            hp,
            max_hp: hp,
            speed,
            radius,
            hit_flash: 0.0,
            touch_cd: 0.0,
            kind,
        });
    }

    fn level_up(&mut self) {
        self.level += 1;
        self.xp -= self.xp_need;
        self.xp_need = (self.xp_need * 1.33).round();
        // rotate through a few upgrades automatically for the slice
        match self.level % 4 {
            0 => {
                self.multishot += 1;
            }
            1 => {
                self.fire_interval = (self.fire_interval * 0.86).max(0.1);
            }
            2 => {
                self.dmg += 9.0;
            }
            _ => {
                self.max_hp += 20.0;
                self.hp = (self.hp + 35.0).min(self.max_hp);
                self.speed += 0.4;
            }
        }
        self.shake = (self.shake + 0.25).min(0.6);
    }
}

fn enemy_color(kind: u8, flash: f32) -> Color {
    let base = match kind {
        1 => Color::new(1.0, 0.45, 0.85, 1.0), // fast: pink
        2 => Color::new(0.75, 0.25, 1.0, 1.0),  // brute: violet
        _ => Color::new(1.0, 0.33, 0.25, 1.0),  // grunt: red-orange
    };
    if flash > 0.0 {
        let f = flash.min(1.0);
        Color::new(
            base.r + (1.0 - base.r) * f,
            base.g + (1.0 - base.g) * f,
            base.b + (1.0 - base.b) * f,
            1.0,
        )
    } else {
        base
    }
}

fn update(g: &mut Game, dt: f32) {
    g.time += dt;
    g.shake = (g.shake - dt).max(0.0);

    // wave scaling over time
    let new_wave = 1 + (g.time / 22.0) as u32;
    if new_wave > g.wave {
        g.wave = new_wave;
        g.spawn_interval = (1.3 * 0.9f32.powi(g.wave as i32 - 1)).max(0.28);
    }

    // movement
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
    if mv.length_squared() > 0.0 {
        mv = mv.normalize();
        g.player += mv * g.speed * dt;
        g.look = mv.x.atan2(-mv.z);
    }
    // clamp to arena
    let flat = vec3(g.player.x, 0.0, g.player.z);
    if flat.length() > ARENA - 0.6 {
        let c = flat.normalize() * (ARENA - 0.6);
        g.player.x = c.x;
        g.player.z = c.z;
    }

    // spawning
    g.spawn_cd -= dt;
    if g.spawn_cd <= 0.0 {
        let burst = 1 + (g.wave / 3) as usize;
        for _ in 0..burst {
            g.spawn_enemy();
        }
        g.spawn_cd = g.spawn_interval;
    }

    // enemies move toward player
    for e in g.enemies.iter_mut() {
        let to = g.player - e.pos;
        let d = to.length();
        if d > 0.001 {
            e.pos += (to / d) * e.speed * dt;
        }
        e.hit_flash = (e.hit_flash - dt * 4.0).max(0.0);
        e.touch_cd = (e.touch_cd - dt).max(0.0);
        // contact damage
        if d < e.radius + 0.6 && e.touch_cd <= 0.0 {
            g.hp -= match e.kind {
                2 => 16.0,
                1 => 7.0,
                _ => 10.0,
            };
            e.touch_cd = 0.6;
            g.shake = (g.shake + 0.2).min(0.7);
        }
    }

    // auto-fire at nearest
    g.fire_cd -= dt;
    if g.fire_cd <= 0.0 {
        if let Some(i) = g.nearest_enemy() {
            let dir = (g.enemies[i].pos - g.player).normalize_or_zero();
            if dir.length_squared() > 0.0 {
                let base = dir.x.atan2(dir.z);
                let spread = 0.17;
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
                        life: 1.4,
                        dmg: g.dmg,
                    });
                }
                g.look = base;
                g.fire_cd = g.fire_interval;
            }
        }
    }

    // shots
    for s in g.shots.iter_mut() {
        s.pos += s.vel * dt;
        s.life -= dt;
    }
    // shot vs enemy
    for s in g.shots.iter_mut() {
        if s.life <= 0.0 {
            continue;
        }
        for e in g.enemies.iter_mut() {
            if e.hp <= 0.0 {
                continue;
            }
            if (e.pos - s.pos).length() < e.radius + 0.28 {
                e.hp -= s.dmg;
                e.hit_flash = 1.0;
                s.life = 0.0;
                break;
            }
        }
    }
    g.shots.retain(|s| s.life > 0.0 && flatlen(s.pos) < ARENA + 4.0);

    // deaths -> gems
    let mut dead = Vec::new();
    for (i, e) in g.enemies.iter().enumerate() {
        if e.hp <= 0.0 {
            dead.push(i);
        }
    }
    for &i in dead.iter().rev() {
        let e = g.enemies.remove(i);
        g.kills += 1;
        let val = match e.kind {
            2 => 5.0,
            1 => 2.0,
            _ => 1.0,
        };
        g.gems.push(Gem {
            pos: vec3(e.pos.x, 0.4, e.pos.z),
            spin: 0.0,
            value: val,
        });
    }

    // gems: drift to player when close, collect
    for gem in g.gems.iter_mut() {
        gem.spin += dt * 3.0;
        let to = g.player - gem.pos;
        let d = to.length();
        if d < 4.5 {
            gem.pos += (to / d.max(0.001)) * (9.0 * dt) * (1.0 - (d / 4.5) + 0.3);
        }
    }
    let mut got = 0.0;
    g.gems.retain(|gem| {
        if (gem.pos - g.player).length() < 0.9 {
            got += gem.value;
            false
        } else {
            true
        }
    });
    if got > 0.0 {
        g.xp += got;
        while g.xp >= g.xp_need {
            g.level_up();
        }
    }

    if g.hp <= 0.0 {
        g.hp = 0.0;
        g.phase = Phase::Dead;
    }
}

fn flatlen(p: Vec3) -> f32 {
    (p.x * p.x + p.z * p.z).sqrt()
}

fn draw_world(g: &Game) {
    // camera: angled top-down chase
    let mut cam_pos = g.player + vec3(0.0, 17.0, 13.0);
    if g.shake > 0.0 {
        cam_pos.x += rand::gen_range(-g.shake, g.shake);
        cam_pos.y += rand::gen_range(-g.shake, g.shake);
    }
    set_camera(&Camera3D {
        position: cam_pos,
        up: vec3(0.0, 1.0, 0.0),
        target: g.player,
        fovy: 0.9,
        ..Default::default()
    });

    // ground + grid (neon)
    draw_plane(
        vec3(0.0, 0.0, 0.0),
        vec2(ARENA + 3.0, ARENA + 3.0),
        None,
        Color::new(0.05, 0.05, 0.12, 1.0),
    );
    draw_grid(
        (ARENA as u32) * 2,
        1.0,
        Color::new(0.16, 0.5, 0.9, 0.55),
        Color::new(0.08, 0.1, 0.22, 1.0),
    );
    // arena boundary ring
    let seg = 64;
    for i in 0..seg {
        let a0 = i as f32 / seg as f32 * std::f32::consts::TAU;
        let a1 = (i + 1) as f32 / seg as f32 * std::f32::consts::TAU;
        let p0 = vec3(a0.cos() * ARENA, 0.05, a0.sin() * ARENA);
        let p1 = vec3(a1.cos() * ARENA, 0.05, a1.sin() * ARENA);
        draw_line_3d(p0, p1, Color::new(0.2, 0.7, 1.0, 0.8));
    }

    // gems
    for gem in &g.gems {
        draw_cube(
            gem.pos + vec3(0.0, (gem.spin).sin() * 0.1, 0.0),
            vec3(0.32, 0.32, 0.32),
            None,
            Color::new(0.2, 1.0, 0.55, 1.0),
        );
    }

    // enemies
    for e in &g.enemies {
        let c = enemy_color(e.kind, e.hit_flash);
        let s = e.radius * 1.5;
        draw_cube(e.pos, vec3(s, s, s), None, c);
        draw_cube_wires(e.pos, vec3(s, s, s), Color::new(0.0, 0.0, 0.0, 0.5));
        // hp pip
        if e.hp < e.max_hp {
            let frac = (e.hp / e.max_hp).clamp(0.0, 1.0);
            draw_cube(
                e.pos + vec3(0.0, s * 0.9, 0.0),
                vec3(s * frac, 0.08, 0.08),
                None,
                Color::new(0.3, 1.0, 0.4, 1.0),
            );
        }
    }

    // shots
    for s in &g.shots {
        draw_sphere(s.pos, 0.17, None, Color::new(1.0, 0.85, 0.2, 1.0));
    }

    // player: body + facing barrel
    let pulse = 0.5 + 0.5 * (get_time() as f32 * 4.0).sin();
    draw_cube(
        g.player,
        vec3(0.9, 0.9, 0.9),
        None,
        Color::new(0.2, 0.75, 1.0, 1.0),
    );
    draw_cube_wires(
        g.player,
        vec3(0.95, 0.95, 0.95),
        Color::new(0.6, 0.95, 1.0, 0.4 + 0.4 * pulse),
    );
    let bx = g.look.sin();
    let bz = g.look.cos();
    draw_cube(
        g.player + vec3(bx * 0.7, 0.0, bz * 0.7),
        vec3(0.3, 0.3, 0.3),
        None,
        Color::new(0.9, 0.97, 1.0, 1.0),
    );
}

fn bar(x: f32, y: f32, w: f32, h: f32, frac: f32, col: Color) {
    draw_rectangle(x, y, w, h, Color::new(1.0, 1.0, 1.0, 0.08));
    draw_rectangle(x, y, w * frac.clamp(0.0, 1.0), h, col);
    draw_rectangle_lines(x, y, w, h, 2.0, Color::new(1.0, 1.0, 1.0, 0.25));
}

fn draw_hud(g: &Game) {
    set_default_camera();
    let sw = screen_width();
    // top-left: HP + level/xp
    draw_text("INTEGRITY", 24.0, 34.0, 22.0, Color::new(0.7, 0.9, 1.0, 1.0));
    bar(24.0, 42.0, 260.0, 18.0, g.hp / g.max_hp, Color::new(0.2, 0.85, 1.0, 1.0));
    draw_text(
        &format!("{:.0}/{:.0}", g.hp, g.max_hp),
        296.0,
        57.0,
        20.0,
        WHITE,
    );
    draw_text(
        &format!("LVL {}", g.level),
        24.0,
        86.0,
        22.0,
        Color::new(1.0, 0.85, 0.3, 1.0),
    );
    bar(90.0, 72.0, 194.0, 14.0, g.xp / g.xp_need, Color::new(0.3, 1.0, 0.55, 1.0));

    // top-right stats
    let t = g.time as u32;
    let stat = format!("TIME {:02}:{:02}    KILLS {}    WAVE {}", t / 60, t % 60, g.kills, g.wave);
    let dim = measure_text(&stat, None, 24, 1.0);
    draw_text(&stat, sw - dim.width - 24.0, 40.0, 24.0, Color::new(0.8, 0.9, 1.0, 1.0));

    // vignette-ish hurt flash
    if g.hp / g.max_hp < 0.3 {
        let a = 0.12 + 0.12 * (get_time() as f32 * 6.0).sin().abs();
        draw_rectangle(0.0, 0.0, sw, screen_height(), Color::new(1.0, 0.1, 0.2, a));
    }
}

fn center_text(s: &str, y: f32, size: u16, col: Color) {
    let d = measure_text(s, None, size, 1.0);
    draw_text(s, screen_width() / 2.0 - d.width / 2.0, y, size as f32, col);
}

#[macroquad::main(window_conf)]
async fn main() {
    rand::srand(macroquad::miniquad::date::now() as u64);
    let mut g = Game::new();
    loop {
        let dt = get_frame_time().min(0.05);
        clear_background(Color::new(0.03, 0.03, 0.08, 1.0));

        match g.phase {
            Phase::Title => {
                // idle starfield-ish backdrop
                draw_world(&g);
                set_default_camera();
                draw_rectangle(
                    0.0,
                    0.0,
                    screen_width(),
                    screen_height(),
                    Color::new(0.02, 0.02, 0.06, 0.55),
                );
                center_text("BVTECH: BREACH PROTOCOL", 180.0, 56, Color::new(0.3, 0.8, 1.0, 1.0));
                center_text("Defend the grid. Survive the breach.", 230.0, 28, Color::new(0.8, 0.9, 1.0, 1.0));
                center_text("WASD / Arrows to move  ·  you auto-fire  ·  grab data shards to level up", 300.0, 24.0 as u16, WHITE);
                center_text("Press SPACE or click to begin", 360.0, 30, Color::new(1.0, 0.85, 0.3, 1.0));
                center_text("A BVTech original · built in Rust + WebAssembly", 420.0, 20, Color::new(0.6, 0.7, 0.85, 1.0));
                if is_key_pressed(KeyCode::Space) || is_mouse_button_pressed(MouseButton::Left) {
                    g.reset();
                }
            }
            Phase::Playing => {
                update(&mut g, dt);
                draw_world(&g);
                draw_hud(&g);
            }
            Phase::Dead => {
                draw_world(&g);
                draw_hud(&g);
                set_default_camera();
                draw_rectangle(
                    0.0,
                    0.0,
                    screen_width(),
                    screen_height(),
                    Color::new(0.1, 0.0, 0.05, 0.6),
                );
                center_text("GRID BREACHED", 200.0, 60, Color::new(1.0, 0.35, 0.4, 1.0));
                let t = g.time as u32;
                center_text(
                    &format!("You held out {:02}:{:02}  ·  {} breaches neutralized  ·  level {}", t / 60, t % 60, g.kills, g.level),
                    260.0,
                    26,
                    WHITE,
                );
                center_text("Press R or click to redeploy", 330.0, 30, Color::new(1.0, 0.85, 0.3, 1.0));
                if is_key_pressed(KeyCode::R) || is_mouse_button_pressed(MouseButton::Left) {
                    g.reset();
                }
            }
        }

        next_frame().await;
    }
}
