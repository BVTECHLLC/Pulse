extends Node3D
# Graveyard Shift — main controller. A 3D vampire-survivors run: auto-firing
# weapons, swarming husks, XP gems, pick-a-perk level-ups, a survive-to-dawn
# timer, and persistent soul-shards between runs. World is built from CC0
# Kenney meshes; everything is code-driven so it validates headlessly.

const ARCHER := "res://assets/forest/character-archer.glb"

var player: CharacterBody3D
var hud: CanvasLayer
var rng := RandomNumberGenerator.new()

var state := "menu"        # "menu" | "play" | "over"
var run_time := 0.0
var dawn := 420.0          # survive 7:00 to win
var kills := 0
var spawn_timer := 0.0
var enemies: Array = []
var gems: Array = []

# chosen at the main menu
var chosen_class := "rogue"
var chosen_diff := "mid"
var menu: CanvasLayer
# difficulty multipliers (set by _apply_difficulty)
var diff_hp := 1.0
var diff_spawn := 1.0
var diff_dmg := 1.0
var diff_reward := 1.0

const DIFFS := {
	"dusk":      {"name": "Dusk",      "hp": 0.8, "spawn": 1.3,  "dmg": 0.75, "reward": 0.8},
	"mid":       {"name": "Midnight",  "hp": 1.0, "spawn": 1.0,  "dmg": 1.0,  "reward": 1.0},
	"nightmare": {"name": "Nightmare", "hp": 1.5, "spawn": 0.72, "dmg": 1.3,  "reward": 1.7},
}
const CLASSES := {
	"rogue":   {"name": "Rogue",   "blurb": "Fast & evasive.\nStarts: Bone Spear.\nQuicker dodge, less HP."},
	"warrior": {"name": "Warrior", "blurb": "Tanky bruiser.\nStarts: Reaper Scythe.\n+HP, +armor, slower."},
	"healer":  {"name": "Healer",  "blurb": "Sustain build.\nStarts: Holy Nova.\nRegen, heal on kill, big magnet."},
}

# follow camera (decoupled from the hero so facing doesn't spin the view)
var cam_rig: Node3D
var cam: Camera3D
var cam_yaw := 0.0
const CAM_DIST := 11.0
const CAM_HEIGHT := 8.0

var _upgrade_open := false
var _frame := 0
var _torches: Array = []

func _ready() -> void:
	rng.randomize()
	_build_environment()
	_build_camera()
	if "--shot" in OS.get_cmdline_user_args():
		start_run("rogue", "mid")   # dev render skips the menu
	else:
		_show_menu()

func _show_menu() -> void:
	state = "menu"
	menu = CanvasLayer.new()
	menu.set_script(load("res://scripts/menu.gd"))
	add_child(menu)
	menu.open(self)
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

func start_run(class_id: String, diff_id: String) -> void:
	chosen_class = class_id
	chosen_diff = diff_id
	_apply_difficulty(diff_id)
	if menu and is_instance_valid(menu):
		menu.queue_free()
	_spawn_player()
	_build_hud()
	run_time = 0.0
	kills = 0
	for i in 3:
		_spawn_enemy()
	spawn_timer = 2.5   # brief calm before the swarm builds
	state = "play"
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _apply_difficulty(diff_id: String) -> void:
	var d = DIFFS.get(diff_id, DIFFS["mid"])
	diff_hp = d["hp"]
	diff_spawn = d["spawn"]
	diff_dmg = d["dmg"]
	diff_reward = d["reward"]

# --------------------------------------------------------------------------- #
# World
# --------------------------------------------------------------------------- #
func _build_environment() -> void:
	var moon := DirectionalLight3D.new()
	moon.rotation_degrees = Vector3(-46, -120, 0)
	moon.light_color = Color(0.62, 0.70, 0.98)
	moon.light_energy = 0.6
	moon.shadow_enabled = true
	add_child(moon)

	var we := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var sky_mat := ProceduralSkyMaterial.new()
	sky_mat.sky_top_color = Color(0.015, 0.02, 0.06)
	sky_mat.sky_horizon_color = Color(0.09, 0.08, 0.17)
	sky_mat.ground_bottom_color = Color(0.02, 0.02, 0.04)
	sky_mat.ground_horizon_color = Color(0.07, 0.07, 0.12)
	sky.sky_material = sky_mat
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.32
	env.ambient_light_color = Color(0.32, 0.36, 0.55)
	env.fog_enabled = true
	env.fog_light_color = Color(0.16, 0.18, 0.30)
	env.fog_density = 0.016
	env.fog_sky_affect = 0.5
	env.glow_enabled = true
	env.glow_intensity = 0.5
	env.glow_bloom = 0.1
	we.environment = env
	add_child(we)

	var ground := StaticBody3D.new()
	var gm := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(170, 170)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.11, 0.15, 0.12)
	mat.roughness = 1.0
	plane.material = mat
	gm.mesh = plane
	ground.add_child(gm)
	var gcol := CollisionShape3D.new()
	var gbox := BoxShape3D.new()
	gbox.size = Vector3(170, 0.4, 170)
	gcol.shape = gbox
	gcol.position.y = -0.2
	ground.add_child(gcol)
	add_child(ground)

	_build_graveyard()

func _build_graveyard() -> void:
	var stones := [
		"res://assets/pirate/rocks-a.glb", "res://assets/pirate/rocks-b.glb",
		"res://assets/pirate/rocks-c.glb", "res://assets/forest/stones.glb",
	]
	for gx in range(-6, 7):
		for gz in range(-6, 7):
			if abs(gx) <= 1 and abs(gz) <= 1:
				continue
			if rng.randf() > 0.6:
				continue
			var p = load(stones[rng.randi() % stones.size()]).instantiate()
			p.position = Vector3(gx * 6.0 + rng.randf_range(-1.3, 1.3), 0.0, gz * 6.0 + rng.randf_range(-1.3, 1.3))
			p.rotation.y = rng.randf_range(-0.22, 0.22) + (PI if rng.randf() < 0.3 else 0.0)
			var s := rng.randf_range(0.8, 1.2)
			p.scale = Vector3(s, s * rng.randf_range(1.0, 1.6), s)
			add_child(p)

	_scatter("res://assets/forest/tree-high.glb", 26, 16.0, 78.0)
	_scatter("res://assets/forest/tree.glb", 18, 16.0, 78.0)
	_scatter("res://assets/pirate/hole.glb", 7, 8.0, 52.0)
	_scatter("res://assets/forest/rocks-low.glb", 14, 10.0, 60.0)
	_scatter("res://assets/pirate/barrel.glb", 7, 8.0, 56.0)
	_scatter("res://assets/pirate/crate.glb", 6, 8.0, 56.0)
	_scatter("res://assets/pirate/chest.glb", 5, 10.0, 52.0)
	_fence_ring("res://assets/forest/fence.glb", 80.0, 60)
	_crypt(Vector3(-34, 0, -30))

	var ghost = load("res://assets/pirate/ship-ghost.glb").instantiate()
	ghost.position = Vector3(48, 0, -46)
	ghost.rotation.y = -0.9
	ghost.scale = Vector3(2.2, 2.2, 2.2)
	add_child(ghost)

	for t in [Vector3(-9, 0, -9), Vector3(11, 0, -7), Vector3(-6, 0, 13),
			Vector3(15, 0, 15), Vector3(-22, 0, 3), Vector3(5, 0, -23),
			Vector3(24, 0, 6), Vector3(-14, 0, 22)]:
		_torch(t)

func _scatter(path: String, count: int, min_r: float, max_r: float) -> void:
	var ps := load(path)
	if ps == null:
		return
	for i in count:
		var n = ps.instantiate()
		var a := rng.randf() * TAU
		var r := rng.randf_range(min_r, max_r)
		n.position = Vector3(cos(a) * r, 0.0, sin(a) * r)
		n.rotation.y = rng.randf() * TAU
		var s := rng.randf_range(0.9, 1.3)
		n.scale = Vector3(s, s, s)
		add_child(n)

func _fence_ring(path: String, radius: float, count: int) -> void:
	var ps := load(path)
	if ps == null:
		return
	for i in count:
		var a := TAU * float(i) / float(count)
		if a > 2.95 and a < 3.45:
			continue
		var n = ps.instantiate()
		n.position = Vector3(cos(a) * radius, 0.0, sin(a) * radius)
		n.rotation.y = a + PI / 2.0
		add_child(n)

func _crypt(center: Vector3) -> void:
	var gate = load("res://assets/pirate/castle-gate.glb").instantiate()
	gate.position = center
	gate.scale = Vector3(1.7, 1.7, 1.7)
	add_child(gate)
	for o in [Vector3(-4.5, 0, 0), Vector3(4.5, 0, 0), Vector3(0, 0, -4.5)]:
		var w = load("res://assets/pirate/castle-wall.glb").instantiate()
		w.position = center + o
		w.rotation.y = rng.randf_range(-0.12, 0.12)
		w.scale = Vector3(1.7, 1.7, 1.7)
		add_child(w)
	var tower = load("res://assets/pirate/tower-complete-small.glb").instantiate()
	tower.position = center + Vector3(0, 0, -9)
	tower.scale = Vector3(1.5, 1.5, 1.5)
	add_child(tower)

func _torch(pos: Vector3) -> void:
	var light := OmniLight3D.new()
	light.light_color = Color(1.0, 0.58, 0.24)
	light.light_energy = 2.4
	light.omni_range = 16.0
	light.position = pos + Vector3(0, 2.6, 0)
	add_child(light)
	_torches.append(light)

	var post = load("res://assets/pirate/barrel.glb").instantiate()
	post.position = pos
	post.scale = Vector3(0.8, 1.1, 0.8)
	add_child(post)

	var p := GPUParticles3D.new()
	var pm := ParticleProcessMaterial.new()
	pm.direction = Vector3(0, 1, 0)
	pm.spread = 18.0
	pm.initial_velocity_min = 0.7
	pm.initial_velocity_max = 1.6
	pm.gravity = Vector3(0, 0.6, 0)
	pm.scale_min = 0.08
	pm.scale_max = 0.22
	pm.color = Color(1.0, 0.55, 0.2)
	p.process_material = pm
	var em := SphereMesh.new()
	em.radius = 0.09
	em.height = 0.18
	var emmat := StandardMaterial3D.new()
	emmat.emission_enabled = true
	emmat.emission = Color(1.0, 0.6, 0.2)
	emmat.albedo_color = Color(1.0, 0.6, 0.2)
	em.material = emmat
	p.draw_pass_1 = em
	p.amount = 18
	p.lifetime = 1.3
	p.position = pos + Vector3(0, 2.5, 0)
	add_child(p)
	p.emitting = true

# --------------------------------------------------------------------------- #
# Camera + player + HUD
# --------------------------------------------------------------------------- #
func _build_camera() -> void:
	cam_rig = Node3D.new()
	add_child(cam_rig)
	cam = Camera3D.new()
	cam.position = Vector3(0, CAM_HEIGHT, CAM_DIST)
	cam.rotation_degrees = Vector3(-33, 0, 0)
	cam_rig.add_child(cam)
	cam.current = true
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _spawn_player() -> void:
	player = CharacterBody3D.new()
	player.name = "Player"
	player.set_script(load("res://scripts/player.gd"))
	var mesh = load(ARCHER).instantiate()
	player.add_child(mesh)
	var col := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.4
	cap.height = 1.5
	col.shape = cap
	col.position.y = 0.75
	player.add_child(col)
	player.position = Vector3(0, 2, 0)
	add_child(player)
	player.game = self
	player.setup()
	player.apply_class(chosen_class)

	# small persistent bonus from banked soul-shards (meta-progression)
	var meta := _load_save()
	var bonus: float = min(60.0, floor(float(meta.get("shards", 0)) / 25.0) * 5.0)
	player.max_hp += bonus
	player.hp = player.max_hp
	player.invuln = 2.5   # spawn protection
	if cam_rig:
		cam_rig.global_position = player.global_position

func _build_hud() -> void:
	hud = CanvasLayer.new()
	hud.set_script(load("res://scripts/hud.gd"))
	add_child(hud)
	hud.build()

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		cam_yaw -= event.relative.x * 0.004
	elif event is InputEventMouseButton and event.pressed:
		if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
			Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	if state == "over" and event is InputEventKey and event.pressed and event.keycode == KEY_SPACE:
		get_tree().reload_current_scene()

# --------------------------------------------------------------------------- #
# Run loop
# --------------------------------------------------------------------------- #
func _process(delta: float) -> void:
	_frame += 1
	var tnow := Time.get_ticks_msec() * 0.001
	for i in _torches.size():
		var t = _torches[i]
		if is_instance_valid(t):
			t.light_energy = 2.3 + sin(tnow * 9.0 + i * 1.7) * 0.35 + rng.randf_range(-0.15, 0.15)

	if state == "menu":
		cam_yaw += delta * 0.07   # slow orbit over the graveyard behind the menu
		if cam_rig:
			cam_rig.global_position = cam_rig.global_position.lerp(Vector3.ZERO, 2.0 * delta)
			cam_rig.rotation.y = cam_yaw
		if "--menushot" in OS.get_cmdline_user_args() and _frame == 70:
			var mimg := get_viewport().get_texture().get_image()
			mimg.save_png("user://gys_menu.png")
			print("MENU_SHOT: ", OS.get_user_data_dir(), "/gys_menu.png")
			get_tree().quit()
		return

	if cam_rig and is_instance_valid(player):
		cam_rig.global_position = cam_rig.global_position.lerp(player.global_position, 8.0 * delta)
		cam_rig.rotation.y = cam_yaw

	if state != "play":
		_shot_check()
		return

	run_time += delta
	enemies = enemies.filter(func(e): return is_instance_valid(e))
	_update_gems(delta)

	spawn_timer -= delta
	var cap: int = min(80, 16 + int(run_time / 18.0) * 6)
	if spawn_timer <= 0.0 and enemies.size() < cap:
		var burst: int = 1 + int(run_time / 70.0)
		for b in burst:
			_spawn_enemy()
		spawn_timer = max(0.45, 1.7 - run_time * 0.0016) * diff_spawn

	if run_time >= dawn:
		_win()

	if hud and is_instance_valid(player):
		hud.update_run(self, player)

	_shot_check()

func _update_gems(delta: float) -> void:
	gems = gems.filter(func(g): return is_instance_valid(g))
	if not is_instance_valid(player):
		return
	var pr: float = player.pickup_range
	for g in gems:
		g.rotate_y(delta * 3.0)
		var d: float = g.global_position.distance_to(player.global_position)
		if d < pr:
			g.global_position = g.global_position.lerp(player.global_position + Vector3(0, 0.8, 0), 12.0 * delta)
			if d < 1.0:
				player.gain_xp(int(g.get_meta("value", 1)))
				g.queue_free()

func _spawn_enemy() -> void:
	if not is_instance_valid(player):
		return
	var e := CharacterBody3D.new()
	e.set_script(load("res://scripts/enemy.gd"))
	var mesh = load(ARCHER).instantiate()
	e.add_child(mesh)
	var col := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.4
	cap.height = 1.5
	col.shape = cap
	col.position.y = 0.75
	e.add_child(col)
	var a := rng.randf() * TAU
	var r := rng.randf_range(22.0, 34.0)
	e.position = player.position + Vector3(cos(a) * r, 0.5, sin(a) * r)
	e.game = self
	e.max_hp = (12.0 + run_time * 0.8) * diff_hp
	# occasional heavy "tomb-brute"
	if rng.randf() < 0.12 + run_time * 0.0003:
		e.max_hp *= 2.4
		mesh.scale = Vector3(1.5, 1.5, 1.5)
		e.speed = 2.4
	e.hp = e.max_hp
	add_child(e)
	enemies.append(e)

# --------------------------------------------------------------------------- #
# Combat helpers used by weapons.gd
# --------------------------------------------------------------------------- #
func nearest_enemy(from: Vector3):
	var best = null
	var bd := INF
	for e in enemies:
		if not is_instance_valid(e):
			continue
		var d: float = from.distance_squared_to(e.global_position)
		if d < bd:
			bd = d
			best = e
	return best

func nearest_enemy_excluding(from: Vector3, excl: Array):
	var best = null
	var bd := INF
	for e in enemies:
		if not is_instance_valid(e) or e in excl:
			continue
		var d: float = from.distance_squared_to(e.global_position)
		if d < bd:
			bd = d
			best = e
	return best

func nearest_enemies(from: Vector3, n: int) -> Array:
	var arr: Array = []
	for e in enemies:
		if is_instance_valid(e):
			arr.append(e)
	arr.sort_custom(func(x, y): return from.distance_squared_to(x.global_position) < from.distance_squared_to(y.global_position))
	return arr.slice(0, n)

func enemies_in_radius(center: Vector3, radius: float) -> Array:
	var out: Array = []
	var r2 := radius * radius
	for e in enemies:
		if is_instance_valid(e) and center.distance_squared_to(e.global_position) <= r2:
			out.append(e)
	return out

func spawn_projectile(from: Vector3, dir: Vector3, dmg: float, pierce: int, speed: float, scl: float) -> void:
	var p := Node3D.new()
	p.set_script(load("res://scripts/projectile.gd"))
	var m = load("res://assets/forest/weapon-arrow.glb").instantiate()
	m.rotation_degrees = Vector3(90, 0, 0)
	m.scale = Vector3(scl, scl, scl)
	p.add_child(m)
	p.dir = dir
	p.damage = dmg
	p.pierce = pierce
	p.speed = speed
	p.game = self
	add_child(p)
	p.global_position = from

func ring_flash(center: Vector3, radius: float, color: Color) -> void:
	var mi := MeshInstance3D.new()
	var tm := TorusMesh.new()
	tm.inner_radius = radius * 0.72
	tm.outer_radius = radius
	mi.mesh = tm
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(color.r, color.g, color.b, 0.55)
	mat.emission_enabled = true
	mat.emission = color
	mat.emission_energy_multiplier = 2.2
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mi.material_override = mat
	mi.position = center + Vector3(0, 0.4, 0)
	add_child(mi)
	mi.scale = Vector3(0.6, 0.6, 0.6)
	var tw := create_tween()
	tw.set_parallel(true)
	tw.tween_property(mi, "scale", Vector3(1.05, 1.05, 1.05), 0.28)
	tw.tween_property(mat, "albedo_color:a", 0.0, 0.28)
	tw.chain().tween_callback(mi.queue_free)

func beam_flash(a: Vector3, b: Vector3, color: Color) -> void:
	var mi := MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = 0.07
	cyl.bottom_radius = 0.07
	cyl.height = a.distance_to(b)
	mi.mesh = cyl
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.emission_enabled = true
	mat.emission = color
	mat.emission_energy_multiplier = 3.0
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mi.material_override = mat
	add_child(mi)
	mi.global_position = (a + b) * 0.5
	# orient the cylinder's Y axis along (b - a)
	var up := (b - a).normalized()
	var right := up.cross(Vector3.FORWARD)
	if right.length() < 0.01:
		right = up.cross(Vector3.RIGHT)
	right = right.normalized()
	var fwd := right.cross(up).normalized()
	mi.global_transform.basis = Basis(right, up, fwd)
	var tw := create_tween()
	tw.tween_property(mat, "albedo_color:a", 0.0, 0.16)
	tw.tween_callback(mi.queue_free)

# --------------------------------------------------------------------------- #
# Kills, XP gems, level-ups, FX
# --------------------------------------------------------------------------- #
func on_enemy_killed(pos: Vector3) -> void:
	kills += 1
	if is_instance_valid(player) and player.heal_on_kill > 0.0:
		player.hp = min(player.max_hp, player.hp + player.heal_on_kill)
	var val := 1
	if kills % 12 == 0:
		val = 5   # occasional rich shard
	spawn_gem(pos, val)
	_death_puff(pos)

func spawn_gem(pos: Vector3, value: int) -> void:
	var mi := MeshInstance3D.new()
	var m := SphereMesh.new()
	m.radius = 0.22 if value < 5 else 0.34
	m.height = m.radius * 2.0
	mi.mesh = m
	var col := Color(0.4, 0.9, 1.0) if value < 5 else Color(1.0, 0.8, 0.3)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = col
	mat.emission_enabled = true
	mat.emission = col
	mat.emission_energy_multiplier = 2.6
	mi.material_override = mat
	mi.position = pos + Vector3(0, 0.6, 0)
	mi.set_meta("value", value)
	add_child(mi)
	gems.append(mi)

func request_upgrade() -> void:
	if _upgrade_open or player == null or player.pending_levels <= 0:
		return
	_upgrade_open = true
	var u := CanvasLayer.new()
	u.set_script(load("res://scripts/upgrades.gd"))
	add_child(u)
	u.open(player, self)

func _on_upgrade_closed() -> void:
	_upgrade_open = false

func spawn_damage_number(world_pos: Vector3, amount: int) -> void:
	var lbl := Label3D.new()
	lbl.text = str(amount)
	lbl.font_size = 64
	lbl.pixel_size = 0.008
	lbl.modulate = Color(1.0, 0.92, 0.4)
	lbl.outline_size = 12
	lbl.outline_modulate = Color(0, 0, 0, 0.8)
	lbl.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	lbl.no_depth_test = true
	lbl.position = world_pos + Vector3(randf_range(-0.3, 0.3), 0, 0)
	add_child(lbl)
	var tw := create_tween()
	tw.set_parallel(true)
	tw.tween_property(lbl, "position:y", lbl.position.y + 1.6, 0.7)
	tw.tween_property(lbl, "modulate:a", 0.0, 0.7)
	tw.chain().tween_callback(lbl.queue_free)

func _death_puff(pos: Vector3) -> void:
	var p := GPUParticles3D.new()
	var mat := ParticleProcessMaterial.new()
	mat.direction = Vector3(0, 1, 0)
	mat.spread = 60.0
	mat.initial_velocity_min = 2.0
	mat.initial_velocity_max = 5.0
	mat.gravity = Vector3(0, -6, 0)
	mat.scale_min = 0.4
	mat.scale_max = 0.9
	mat.color = Color(1.0, 0.5, 0.2)
	p.process_material = mat
	var mesh := SphereMesh.new()
	mesh.radius = 0.12
	mesh.height = 0.24
	p.draw_pass_1 = mesh
	p.amount = 20
	p.lifetime = 0.7
	p.one_shot = true
	p.explosiveness = 0.9
	p.position = pos + Vector3(0, 0.8, 0)
	add_child(p)
	p.emitting = true
	var tw := create_tween()
	tw.tween_interval(1.0)
	tw.tween_callback(p.queue_free)

# --------------------------------------------------------------------------- #
# Win / lose + meta-progression
# --------------------------------------------------------------------------- #
func on_player_death() -> void:
	if state != "play":
		return
	_end(false)

func _win() -> void:
	if state != "play":
		return
	_end(true)

func _end(victory: bool) -> void:
	state = "over"
	var earned: int = int((kills + int(run_time / 8.0) + (120 if victory else 0)) * diff_reward)
	var meta := _load_save()
	meta["shards"] = int(meta.get("shards", 0)) + earned
	meta["best_time"] = max(float(meta.get("best_time", 0.0)), run_time)
	_save_save(meta)
	var title := "YOU SURVIVED TILL DAWN" if victory else "YOU FELL IN THE DARK"
	var sub := "Kills %d   •   Time %s   •   +%d soul-shards (banked: %d)" % [
		kills, _fmt_time(run_time), earned, int(meta["shards"])]
	_show_end(title, sub, victory)

func _show_end(title: String, sub: String, victory: bool) -> void:
	var cl := CanvasLayer.new()
	cl.layer = 20
	add_child(cl)
	var dim := ColorRect.new()
	dim.color = Color(0.02, 0.01, 0.05, 0.8)
	dim.anchor_right = 1.0
	dim.anchor_bottom = 1.0
	cl.add_child(dim)
	var box := VBoxContainer.new()
	box.anchor_left = 0.5
	box.anchor_top = 0.5
	box.anchor_right = 0.5
	box.anchor_bottom = 0.5
	box.offset_left = -400
	box.offset_top = -120
	box.offset_right = 400
	box.add_theme_constant_override("separation", 18)
	box.alignment = BoxContainer.ALIGNMENT_CENTER
	cl.add_child(box)
	var t := Label.new()
	t.text = title
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	t.add_theme_font_size_override("font_size", 48)
	t.add_theme_color_override("font_color", Color(0.5, 1.0, 0.5) if victory else Color(1.0, 0.45, 0.4))
	t.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.9))
	t.add_theme_constant_override("outline_size", 10)
	box.add_child(t)
	var s := Label.new()
	s.text = sub
	s.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	s.add_theme_font_size_override("font_size", 22)
	s.add_theme_color_override("font_color", Color(0.95, 0.96, 1.0))
	box.add_child(s)
	var again := Label.new()
	again.text = "Press SPACE to play again"
	again.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	again.add_theme_font_size_override("font_size", 26)
	again.add_theme_color_override("font_color", Color(1.0, 0.62, 0.22))
	box.add_child(again)
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

func _fmt_time(t: float) -> String:
	return "%d:%02d" % [int(t) / 60, int(t) % 60]

func _load_save() -> Dictionary:
	if FileAccess.file_exists("user://gys_save.json"):
		var f := FileAccess.open("user://gys_save.json", FileAccess.READ)
		if f:
			var d = JSON.parse_string(f.get_as_text())
			if typeof(d) == TYPE_DICTIONARY:
				return d
	return {"shards": 0, "best_time": 0.0}

func _save_save(d: Dictionary) -> void:
	var f := FileAccess.open("user://gys_save.json", FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(d))

# --------------------------------------------------------------------------- #
# Dev-only screenshot: `godot --path . -- --shot` renders then quits.
# --------------------------------------------------------------------------- #
func _shot_check() -> void:
	if "--shot" in OS.get_cmdline_user_args() and _frame == 260:
		var img := get_viewport().get_texture().get_image()
		img.save_png("user://graveyard_shift_shot.png")
		print("SHOT_SAVED: ", OS.get_user_data_dir(), "/graveyard_shift_shot.png")
		get_tree().quit()
