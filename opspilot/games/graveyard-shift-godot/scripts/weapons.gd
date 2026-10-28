class_name Weapon
extends RefCounted
# A single auto-firing weapon. The player holds a list of these; each ticks on
# its own cooldown and fires without aiming (classic vampire-survivors). All the
# visual/damage work is delegated to helper methods on the game controller so
# weapons stay small and data-driven.

var id: String
var wname: String
var level: int = 1
var max_level: int = 8
var interval: float
var cd: float = 0.0

# id -> display name + base fire interval (seconds)
const DEFS := {
	"bolt":   {"name": "Silver Bolt",   "interval": 0.80},
	"spear":  {"name": "Bone Spear",    "interval": 1.50},
	"scythe": {"name": "Reaper Scythe",  "interval": 1.05},
	"nova":   {"name": "Holy Nova",     "interval": 2.30},
	"chain":  {"name": "Chain Smite",   "interval": 1.60},
	"aura":   {"name": "Grave Aura",    "interval": 0.50},
}

func _init(_id: String) -> void:
	id = _id
	wname = DEFS[_id]["name"]
	interval = DEFS[_id]["interval"]

func tick(delta: float, player: Node, game: Node) -> void:
	cd -= delta
	if cd <= 0.0:
		cd = interval
		fire(player, game)

func fire(player: Node, game: Node) -> void:
	var dm: float = player.damage_mult
	var origin: Vector3 = player.global_position
	match id:
		"bolt":
			var n := 1 + int(level / 2)   # 1,1,2,2,3,3,4...
			for t in game.nearest_enemies(origin, n):
				var d: Vector3 = t.global_position - origin
				d.y = 0.0
				game.spawn_projectile(origin + Vector3(0, 1.1, 0), d.normalized(),
					(8.0 + level * 3.0) * dm, 0, 34.0, 1.3)
		"spear":
			var t2 = game.nearest_enemy(origin)
			if t2:
				var d2: Vector3 = t2.global_position - origin
				d2.y = 0.0
				game.spawn_projectile(origin + Vector3(0, 1.1, 0), d2.normalized(),
					(14.0 + level * 5.0) * dm, 2 + level, 27.0, 1.9)
		"scythe":
			var r := 3.0 + level * 0.35
			game.ring_flash(origin, r, Color(0.92, 0.96, 1.0))
			for e in game.enemies_in_radius(origin, r):
				e.hit((10.0 + level * 4.0) * dm, origin)
		"nova":
			var r2 := 5.0 + level * 0.6
			game.ring_flash(origin, r2, Color(0.5, 0.85, 1.0))
			for e in game.enemies_in_radius(origin, r2):
				e.hit((12.0 + level * 5.0) * dm, origin)
		"chain":
			_chain(player, game, dm)
		"aura":
			var r3 := 2.6 + level * 0.3
			for e in game.enemies_in_radius(origin, r3):
				e.hit((4.0 + level * 2.0) * dm, origin)

func _chain(player: Node, game: Node, dm: float) -> void:
	var hops := 2 + level
	var hit: Array = []
	var pos: Vector3 = player.global_position
	for i in hops:
		var t = game.nearest_enemy_excluding(pos, hit)
		if t == null:
			break
		game.beam_flash(pos + Vector3(0, 1.0, 0), t.global_position + Vector3(0, 1.0, 0),
			Color(0.6, 0.8, 1.0))
		t.hit((8.0 + level * 3.0) * dm, pos)
		hit.append(t)
		pos = t.global_position

func level_up() -> void:
	level = min(max_level, level + 1)
	# a few weapons also speed up as they rank
	if id == "bolt" or id == "chain" or id == "aura":
		interval = float(DEFS[id]["interval"]) * pow(0.94, level - 1)

func label() -> String:
	return "%s  L%d" % [wname, level]
