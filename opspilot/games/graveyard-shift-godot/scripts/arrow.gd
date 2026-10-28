extends Node3D
# A bow arrow. Flies straight along `dir`, checks distance to live enemies each
# frame, deals `damage` on the first hit, then frees itself. Kept physics-free
# so there are no collision layers to configure — simple and reliable.

var dir := Vector3.FORWARD
var speed := 30.0
var life := 2.2
var damage := 14.0
var pierce := 0          # extra enemies to pass through before stopping
var game: Node3D
var _hit: Array = []     # enemies already struck (no double hits)

func _process(delta: float) -> void:
	position += dir * speed * delta
	# gentle arc so it reads like a real shot
	position.y -= 1.2 * delta
	life -= delta
	if life <= 0.0:
		queue_free()
		return
	if game == null:
		return
	for e in game.enemies:
		if e in _hit or not is_instance_valid(e):
			continue
		if global_position.distance_to(e.global_position + Vector3(0, 0.9, 0)) < 1.3:
			if e.has_method("hit"):
				e.hit(damage, global_position)
			_hit.append(e)
			if pierce <= 0:
				queue_free()
				return
			pierce -= 1
