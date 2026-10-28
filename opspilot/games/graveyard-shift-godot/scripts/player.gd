extends CharacterBody3D
# The archer hero: third-person movement relative to a spring-arm camera,
# mouse-look, jump, and a bow that fires arrows. Health + XP + leveling.

const SPEED := 6.5
const JUMP := 7.5
const GRAVITY := 20.0
const MOUSE_SENS := 0.004

var game: Node3D
var spring: SpringArm3D
var cam: Camera3D
var anim: AnimationPlayer
var _cur_anim := ""
var yaw := 0.0
var pitch := -0.25

var max_hp := 120.0
var hp := 120.0
var xp := 0
var level := 1
var xp_need := 8
var fire_cd := 0.0
var fire_interval := 0.45
var damage := 14.0
var invuln := 0.0

# upgrade-driven stats (grown via the level-up pick-a-perk screen)
var move_mult := 1.0
var multishot := 1
var spread := 0.09      # radians between multishot arrows
var pierce := 0         # extra enemies an arrow passes through
var regen := 0.0        # hp per second
var pending_levels := 0 # queued level-ups awaiting an upgrade choice

func setup_camera() -> void:
	spring = SpringArm3D.new()
	spring.spring_length = 6.5
	spring.position = Vector3(0, 1.6, 0)
	spring.rotation.x = pitch
	add_child(spring)
	cam = Camera3D.new()
	cam.position = Vector3(0, 0, 0)
	spring.add_child(cam)
	cam.current = true
	# capture the mouse for look (click re-captures on web)
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func setup_anim() -> void:
	anim = _find_anim(self)
	if anim:
		for a in ["idle", "walk", "sprint"]:
			if anim.has_animation(a):
				anim.get_animation(a).loop_mode = Animation.LOOP_LINEAR
		_play("idle")

func _find_anim(n: Node) -> AnimationPlayer:
	if n is AnimationPlayer:
		return n
	for c in n.get_children():
		var r := _find_anim(c)
		if r:
			return r
	return null

func _play(a: String, speed := 1.0) -> void:
	if anim == null or _cur_anim == a:
		return
	if anim.has_animation(a):
		anim.play(a, 0.15, speed)
		_cur_anim = a

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		yaw -= event.relative.x * MOUSE_SENS
		pitch = clamp(pitch - event.relative.y * MOUSE_SENS, -1.1, 0.3)
		if spring:
			spring.rotation.x = pitch
	elif event is InputEventMouseButton and event.pressed:
		if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
			Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _physics_process(delta: float) -> void:
	invuln = max(0.0, invuln - delta)
	fire_cd = max(0.0, fire_cd - delta)

	# passive regeneration
	if regen > 0.0 and hp > 0.0:
		hp = min(max_hp, hp + regen * delta)

	# gravity
	if not is_on_floor():
		velocity.y -= GRAVITY * delta

	# movement relative to camera yaw
	var input := Vector3.ZERO
	if Input.is_key_pressed(KEY_W): input.z -= 1.0
	if Input.is_key_pressed(KEY_S): input.z += 1.0
	if Input.is_key_pressed(KEY_A): input.x -= 1.0
	if Input.is_key_pressed(KEY_D): input.x += 1.0
	var dir := input.rotated(Vector3.UP, yaw).normalized()
	velocity.x = dir.x * SPEED * move_mult
	velocity.z = dir.z * SPEED * move_mult
	if Input.is_key_pressed(KEY_SPACE) and is_on_floor():
		velocity.y = JUMP

	move_and_slide()

	# face aim (camera) direction while moving/attacking
	rotation.y = yaw

	# drive locomotion animation from movement state
	var hspeed := Vector2(velocity.x, velocity.z).length()
	if not is_on_floor():
		_play("fall")
	elif hspeed > 4.5:
		_play("sprint", 1.1)
	elif hspeed > 0.6:
		_play("walk", 1.3)
	else:
		_play("idle")

	# auto/hold-fire with left mouse (survivors-friendly)
	if Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT) and fire_cd <= 0.0:
		_shoot()
		fire_cd = fire_interval

func _shoot() -> void:
	if game == null:
		return
	var fwd := -global_transform.basis.z
	fwd.y = 0.0
	fwd = fwd.normalized()
	# fan the multishot arrows out around the aim direction
	for i in multishot:
		var off := (float(i) - float(multishot - 1) * 0.5) * spread
		_spawn_arrow(fwd.rotated(Vector3.UP, off))

func _spawn_arrow(dir: Vector3) -> void:
	var arrow := Node3D.new()
	arrow.set_script(load("res://scripts/arrow.gd"))
	var m = load("res://assets/forest/weapon-arrow.glb").instantiate()
	m.rotation_degrees = Vector3(90, 0, 0)
	m.scale = Vector3(1.4, 1.4, 1.4)
	arrow.add_child(m)
	arrow.dir = dir
	arrow.damage = damage
	arrow.pierce = pierce
	arrow.game = game
	game.add_child(arrow)
	arrow.global_position = global_position + Vector3(0, 1.1, 0) + dir * 0.8

func take_damage(amount: float) -> void:
	if invuln > 0.0:
		return
	hp -= amount
	invuln = 0.4
	if hp <= 0.0:
		hp = 0.0
		# simple respawn to keep the slice playable
		global_position = Vector3(0, 2, 0)
		hp = max_hp

func gain_xp(amount: int) -> void:
	xp += amount
	while xp >= xp_need:
		xp -= xp_need
		level += 1
		xp_need = int(xp_need * 1.3) + 2
		pending_levels += 1
	# hand level-ups to the game, which opens the pick-a-perk screen
	if pending_levels > 0 and game and game.has_method("request_upgrade"):
		game.request_upgrade()
