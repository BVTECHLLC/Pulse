extends Node3D
# Graveyard Shift — main game controller. Builds the world from CC0 Kenney meshes,
# spawns the archer hero + a third-person camera, runs enemy waves, XP and the
# HUD. Code-driven so the whole thing is reproducible and easy to validate.

const ARCHER := "res://assets/forest/character-archer.glb"

var player: CharacterBody3D
var hud: CanvasLayer
var rng := RandomNumberGenerator.new()

var wave := 1
var kills := 0
var spawn_timer := 0.0
var enemies: Array = []
var _frame := 0  # dev-only: used by the `--shot` screenshot helper below
var _torches: Array = []  # flickering omni lights, animated in _process

func _ready() -> void:
	rng.randomize()
	_build_environment()
	_spawn_player()
	_build_hud()
	for i in 5:
		_spawn_enemy()

func _build_environment() -> void:
	# --- moonlit night ---
	var moon := DirectionalLight3D.new()
	moon.rotation_degrees = Vector3(-46, -120, 0)
	moon.light_color = Color(0.62, 0.70, 0.98)  # cold moonlight
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
	# thick spooky fog
	env.fog_enabled = true
	env.fog_light_color = Color(0.16, 0.18, 0.30)
	env.fog_density = 0.016
	env.fog_sky_affect = 0.5
	# a touch of bloom on the torches/moon
	env.glow_enabled = true
	env.glow_intensity = 0.5
	env.glow_bloom = 0.1
	we.environment = env
	add_child(we)

	# --- ground (dark graveyard turf) ---
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
	# --- tombstone rows (upright rocks read as headstones) ---
	var stones := [
		"res://assets/pirate/rocks-a.glb", "res://assets/pirate/rocks-b.glb",
		"res://assets/pirate/rocks-c.glb", "res://assets/forest/stones.glb",
	]
	for gx in range(-6, 7):
		for gz in range(-6, 7):
			if abs(gx) <= 1 and abs(gz) <= 1:
				continue  # keep the arena center clear
			if rng.randf() > 0.6:
				continue
			var p = load(stones[rng.randi() % stones.size()]).instantiate()
			p.position = Vector3(gx * 6.0 + rng.randf_range(-1.3, 1.3), 0.0, gz * 6.0 + rng.randf_range(-1.3, 1.3))
			p.rotation.y = rng.randf_range(-0.22, 0.22) + (PI if rng.randf() < 0.3 else 0.0)
			var s := rng.randf_range(0.8, 1.2)
			p.scale = Vector3(s, s * rng.randf_range(1.0, 1.6), s)  # stretched = headstone
			add_child(p)

	# --- bare trees looming at the edges ---
	_scatter("res://assets/forest/tree-high.glb", 26, 16.0, 78.0)
	_scatter("res://assets/forest/tree.glb", 18, 16.0, 78.0)

	# --- open graves, loose rubble, and loot ---
	_scatter("res://assets/pirate/hole.glb", 7, 8.0, 52.0)
	_scatter("res://assets/forest/rocks-low.glb", 14, 10.0, 60.0)
	_scatter("res://assets/pirate/barrel.glb", 7, 8.0, 56.0)
	_scatter("res://assets/pirate/crate.glb", 6, 8.0, 56.0)
	_scatter("res://assets/pirate/chest.glb", 5, 10.0, 52.0)

	# --- iron churchyard fence (with a gate gap) ---
	_fence_ring("res://assets/forest/fence.glb", 80.0, 60)

	# --- ruined crypt landmark ---
	_crypt(Vector3(-34, 0, -30))

	# --- a beached ghost ship, half-swallowed by fog ---
	var ghost = load("res://assets/pirate/ship-ghost.glb").instantiate()
	ghost.position = Vector3(48, 0, -46)
	ghost.rotation.y = -0.9
	ghost.scale = Vector3(2.2, 2.2, 2.2)
	add_child(ghost)

	# --- torches for warm pools of light + atmosphere ---
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
			continue  # leave a gap for the gate
		var n = ps.instantiate()
		n.position = Vector3(cos(a) * radius, 0.0, sin(a) * radius)
		n.rotation.y = a + PI / 2.0
		add_child(n)

func _crypt(center: Vector3) -> void:
	# a small ruined stone structure built from castle pieces
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
	# warm flickering light + a brazier + rising embers
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

func _spawn_player() -> void:
	player = CharacterBody3D.new()
	player.name = "Player"
	player.set_script(load("res://scripts/player.gd"))
	var mesh = load(ARCHER).instantiate()
	mesh.position.y = 0.0
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
	player.setup_camera()
	player.setup_anim()

func _build_hud() -> void:
	hud = CanvasLayer.new()
	hud.set_script(load("res://scripts/hud.gd"))
	add_child(hud)
	hud.build()

func _process(delta: float) -> void:
	# flicker the torches for a restless, candlelit feel
	var tnow := Time.get_ticks_msec() * 0.001
	for i in _torches.size():
		var t = _torches[i]
		if is_instance_valid(t):
			t.light_energy = 2.3 + sin(tnow * 9.0 + i * 1.7) * 0.35 + rng.randf_range(-0.18, 0.18)

	# cull dead enemy refs
	enemies = enemies.filter(func(e): return is_instance_valid(e))
	spawn_timer -= delta
	if spawn_timer <= 0.0 and enemies.size() < 14:
		_spawn_enemy()
		spawn_timer = max(0.7, 2.2 - wave * 0.15)
	if hud and player:
		hud.update_stats(player, wave, kills)

	# dev-only: `godot --path . -- --shot` renders a few frames then saves a PNG
	# and quits. No effect in normal play / web builds (no such user arg).
	_frame += 1
	if "--shot" in OS.get_cmdline_user_args() and _frame == 90:
		var img := get_viewport().get_texture().get_image()
		img.save_png("user://graveyard_shift_shot.png")
		print("SHOT_SAVED: ", OS.get_user_data_dir(), "/graveyard_shift_shot.png")
		get_tree().quit()

func _spawn_enemy() -> void:
	if player == null:
		return
	var e := CharacterBody3D.new()
	e.set_script(load("res://scripts/enemy.gd"))
	# reuse the archer mesh tinted dark/red as a "husk" (original enemy)
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
	var r := rng.randf_range(16.0, 26.0)
	e.position = player.position + Vector3(cos(a) * r, 0.5, sin(a) * r)
	e.game = self
	e.max_hp = 20.0 + wave * 6.0
	e.hp = e.max_hp
	add_child(e)
	enemies.append(e)

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

func on_enemy_killed(pos: Vector3) -> void:
	kills += 1
	if kills % 8 == 0:
		wave += 1
	if player:
		player.gain_xp(5)
	# a quick spark where the husk fell
	_death_puff(pos)

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
	p.amount = 24
	p.lifetime = 0.7
	p.one_shot = true
	p.explosiveness = 0.9
	p.position = pos + Vector3(0, 0.8, 0)
	add_child(p)
	p.emitting = true
	var tw := create_tween()
	tw.tween_interval(1.0)
	tw.tween_callback(p.queue_free)
