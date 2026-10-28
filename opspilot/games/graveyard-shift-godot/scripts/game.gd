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

func _ready() -> void:
	rng.randomize()
	_build_environment()
	_spawn_player()
	_build_hud()
	for i in 5:
		_spawn_enemy()

func _build_environment() -> void:
	# --- lighting + sky ---
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-52, -38, 0)
	sun.light_energy = 1.25
	sun.shadow_enabled = true
	add_child(sun)

	var we := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var sky_mat := ProceduralSkyMaterial.new()
	sky_mat.sky_horizon_color = Color(0.6, 0.7, 0.8)
	sky_mat.ground_horizon_color = Color(0.4, 0.45, 0.4)
	sky.sky_material = sky_mat
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.5
	env.fog_enabled = true
	env.fog_density = 0.004
	env.fog_light_color = Color(0.6, 0.68, 0.75)
	we.environment = env
	add_child(we)

	# --- ground (big grassy plane with collision) ---
	var ground := StaticBody3D.new()
	var gm := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(140, 140)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.34, 0.5, 0.26)
	plane.material = mat
	gm.mesh = plane
	ground.add_child(gm)
	var gcol := CollisionShape3D.new()
	var gbox := BoxShape3D.new()
	gbox.size = Vector3(140, 0.4, 140)
	gcol.shape = gbox
	gcol.position.y = -0.2
	ground.add_child(gcol)
	add_child(ground)

	# --- scatter the CC0 props into a little wilderness ---
	_scatter("res://assets/forest/tree.glb", 46, 8.0, 64.0)
	_scatter("res://assets/forest/tree-high.glb", 30, 8.0, 64.0)
	_scatter("res://assets/forest/rocks-low.glb", 22, 6.0, 60.0)
	_scatter("res://assets/forest/rocks-high.glb", 12, 10.0, 60.0)
	_scatter("res://assets/forest/plant.glb", 40, 4.0, 60.0)
	_scatter("res://assets/forest/stones.glb", 18, 5.0, 55.0)
	_scatter("res://assets/pirate/barrel.glb", 10, 5.0, 45.0)
	_scatter("res://assets/pirate/crate.glb", 8, 5.0, 45.0)
	_scatter("res://assets/pirate/chest.glb", 4, 8.0, 40.0)
	_scatter("res://assets/pirate/palm-straight.glb", 14, 12.0, 62.0)
	_scatter("res://assets/pirate/tower-watch.glb", 3, 20.0, 55.0)

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
