extends CharacterBody3D
# A "husk" enemy. Walks toward the player, deals contact damage on a cooldown,
# takes arrow damage via hit(), flashes white when struck, and awards XP to the
# player + reports the kill to the game when it dies.

const GRAVITY := 20.0

var game: Node3D
var max_hp := 24.0
var hp := 24.0
var speed := 3.2
var touch_cd := 0.0
var flash := 0.0
var dying := false
var anim: AnimationPlayer
var _mats: Array = []

func _ready() -> void:
	# a tiny random speed spread so the swarm isn't a rigid blob
	speed += randf_range(-0.4, 0.8)
	_collect_materials(self)
	anim = _find_anim(self)
	if anim and anim.has_animation("walk"):
		anim.get_animation("walk").loop_mode = Animation.LOOP_LINEAR
		anim.play("walk", 0.2, randf_range(1.0, 1.4))

func _find_anim(n: Node) -> AnimationPlayer:
	if n is AnimationPlayer:
		return n
	for c in n.get_children():
		var r := _find_anim(c)
		if r:
			return r
	return null

func _collect_materials(node: Node) -> void:
	# cache a unique material per surface so we can flash on hit + tint red
	if node is MeshInstance3D:
		var mi := node as MeshInstance3D
		var count := mi.get_surface_override_material_count()
		for i in count:
			var base = mi.mesh.surface_get_material(i) if mi.mesh else null
			var m: StandardMaterial3D
			if base is StandardMaterial3D:
				m = base.duplicate()
			else:
				m = StandardMaterial3D.new()
			# menacing dark-red tint so husks read as enemies, not the hero
			m.albedo_color = Color(0.85, 0.28, 0.28)
			mi.set_surface_override_material(i, m)
			_mats.append(m)
	for c in node.get_children():
		_collect_materials(c)

func _physics_process(delta: float) -> void:
	touch_cd = max(0.0, touch_cd - delta)
	if flash > 0.0:
		flash = max(0.0, flash - delta * 4.0)
		var c := Color(0.85, 0.28, 0.28).lerp(Color(1, 1, 1), flash)
		for m in _mats:
			m.albedo_color = c

	if not is_on_floor():
		velocity.y -= GRAVITY * delta

	if game and is_instance_valid(game.player):
		var to_player: Vector3 = game.player.global_position - global_position
		to_player.y = 0.0
		var dist := to_player.length()
		var dir := to_player.normalized()
		velocity.x = dir.x * speed
		velocity.z = dir.z * speed
		if dir.length() > 0.01:
			rotation.y = atan2(dir.x, dir.z)
		# contact damage
		if dist < 1.6 and touch_cd <= 0.0:
			if game.player.has_method("take_damage"):
				game.player.take_damage(8.0)
			touch_cd = 0.8
			if anim and anim.has_animation("attack-melee-right"):
				anim.play("attack-melee-right", 0.1, 1.6)
	else:
		velocity.x = 0.0
		velocity.z = 0.0

	move_and_slide()

func hit(amount: float, _from: Vector3 = Vector3.ZERO) -> void:
	if dying:
		return
	hp -= amount
	flash = 1.0
	if game and game.has_method("spawn_damage_number"):
		game.spawn_damage_number(global_position + Vector3(0, 1.8, 0), int(round(amount)))
	if hp <= 0.0:
		_die()

func _die() -> void:
	dying = true
	# award XP + spark immediately, then let the death animation play out
	if game and game.has_method("on_enemy_killed"):
		game.on_enemy_killed(global_position)
	set_physics_process(false)
	if anim and anim.has_animation("die"):
		anim.play("die", 0.1)
		await get_tree().create_timer(0.8).timeout
	queue_free()
