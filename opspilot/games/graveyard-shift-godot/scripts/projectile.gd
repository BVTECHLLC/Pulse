extends Node3D
# Generic projectile: flies straight along `dir`, deals `damage` to the first
# enemies it reaches, passes through `pierce` extra foes, then frees itself.
# Physics-free (distance checks) so there are no collision layers to wire up.

var dir := Vector3.FORWARD
var speed := 32.0
var life := 2.2
var damage := 10.0
var pierce := 0
var game: Node
var _hit: Array = []

func _process(delta: float) -> void:
	position += dir * speed * delta
	life -= delta
	if life <= 0.0:
		queue_free()
		return
	if game == null:
		return
	for e in game.enemies:
		if e in _hit or not is_instance_valid(e):
			continue
		if global_position.distance_to(e.global_position + Vector3(0, 0.9, 0)) < 1.35:
			if e.has_method("hit"):
				e.hit(damage, global_position)
			_hit.append(e)
			if pierce <= 0:
				queue_free()
				return
			pierce -= 1
