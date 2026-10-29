extends CharacterBody3D
# The hero. Vampire-survivors style: you only move + dodge — every weapon fires
# automatically at nearby foes. Holds the weapon list, run stats, XP/leveling,
# and a dash with i-frames. The follow camera lives on the game controller so
# the hero can face its movement direction without spinning the view.

const SPEED := 6.2
const GRAVITY := 20.0
const DODGE_SPEED := 18.0

var game: Node3D
var anim: AnimationPlayer
var _cur_anim := ""

# --- run stats (grown by the pick-a-perk screen) ---
var max_hp := 110.0
var hp := 110.0
var armor := 0.0
var regen := 0.0
var move_mult := 1.0
var damage_mult := 1.0
var pickup_range := 4.5

var xp := 0
var level := 1
var xp_need := 6
var pending_levels := 0

var heal_on_kill := 0.0
var invuln := 0.0
var dodge_cd := 0.0
var dodge_cd_max := 1.4
var dodge_t := 0.0
var _dodge_dir := Vector3.ZERO
var _face := 0.0

var weapons: Array = []   # Array[Weapon]

func setup() -> void:
	anim = _find_anim(self)
	if anim:
		for a in ["idle", "walk", "sprint"]:
			if anim.has_animation(a):
				anim.get_animation(a).loop_mode = Animation.LOOP_LINEAR
		_play("idle")

func apply_class(id: String) -> void:
	match id:
		"rogue":
			max_hp = 95.0
			move_mult = 1.18
			dodge_cd_max = 0.95
			add_weapon("spear")
		"warrior":
			max_hp = 155.0
			armor = 3.0
			move_mult = 0.95
			add_weapon("scythe")
		"healer":
			max_hp = 115.0
			regen = 1.5
			pickup_range = 6.5
			heal_on_kill = 3.0
			add_weapon("nova")
		_:
			add_weapon("bolt")
	hp = max_hp

func add_weapon(id: String) -> void:
	if has_weapon(id):
		get_weapon(id).level_up()
	else:
		weapons.append(Weapon.new(id))

func has_weapon(id: String) -> bool:
	for w in weapons:
		if w.id == id:
			return true
	return false

func get_weapon(id: String):
	for w in weapons:
		if w.id == id:
			return w
	return null

func _find_anim(n: Node) -> AnimationPlayer:
	if n is AnimationPlayer:
		return n
	for c in n.get_children():
		var r := _find_anim(c)
		if r:
			return r
	return null

func _play(a: String, spd := 1.0) -> void:
	if anim == null or _cur_anim == a:
		return
	if anim.has_animation(a):
		anim.play(a, 0.15, spd)
		_cur_anim = a

func _physics_process(delta: float) -> void:
	invuln = max(0.0, invuln - delta)
	dodge_cd = max(0.0, dodge_cd - delta)
	dodge_t = max(0.0, dodge_t - delta)

	if regen > 0.0 and hp > 0.0:
		hp = min(max_hp, hp + regen * delta)

	if not is_on_floor():
		velocity.y -= GRAVITY * delta

	# movement input relative to the camera yaw (from the game's camera rig)
	var cam_yaw: float = game.cam_yaw if game else 0.0
	var input := Vector3.ZERO
	if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP): input.z -= 1.0
	if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN): input.z += 1.0
	if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT): input.x -= 1.0
	if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT): input.x += 1.0
	# dev-only: `--shot` auto-kites in a circle so headless renders show combat
	if "--shot" in OS.get_cmdline_user_args():
		var tt := Time.get_ticks_msec() * 0.001
		input = Vector3(cos(tt * 1.4), 0, sin(tt * 1.4))
	var dir := input.rotated(Vector3.UP, cam_yaw).normalized()

	# dodge/dash on Space (short burst + i-frames)
	if Input.is_key_pressed(KEY_SPACE) and dodge_cd <= 0.0:
		_dodge_dir = dir if dir.length() > 0.1 else Vector3(sin(_face), 0, cos(_face))
		dodge_t = 0.22
		dodge_cd = dodge_cd_max
		invuln = max(invuln, 0.34)

	if dodge_t > 0.0:
		velocity.x = _dodge_dir.x * DODGE_SPEED
		velocity.z = _dodge_dir.z * DODGE_SPEED
	else:
		velocity.x = dir.x * SPEED * move_mult
		velocity.z = dir.z * SPEED * move_mult

	move_and_slide()

	# face the way we're moving
	var planar := Vector2(velocity.x, velocity.z)
	if planar.length() > 0.4:
		_face = atan2(velocity.x, velocity.z)
	rotation.y = _face

	# animation from movement state
	var spd := planar.length()
	if dodge_t > 0.0:
		_play("sprint", 1.5)
	elif spd > 4.2:
		_play("sprint", 1.1)
	elif spd > 0.5:
		_play("walk", 1.3)
	else:
		_play("idle")

	# every weapon auto-fires on its own cadence
	if game and game.state == "play":
		for w in weapons:
			w.tick(delta, self, game)

func take_damage(amount: float) -> void:
	if invuln > 0.0:
		return
	hp -= max(1.0, amount - armor)
	invuln = 0.45
	if hp <= 0.0:
		hp = 0.0
		if game and game.has_method("on_player_death"):
			game.on_player_death()

func gain_xp(amount: int) -> void:
	xp += amount
	while xp >= xp_need:
		xp -= xp_need
		level += 1
		xp_need = int(xp_need * 1.25) + 3
		pending_levels += 1
	if pending_levels > 0 and game and game.has_method("request_upgrade"):
		game.request_upgrade()
