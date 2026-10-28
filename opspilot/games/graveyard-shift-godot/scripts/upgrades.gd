extends CanvasLayer
# Level-up "pick a perk" screen. Pauses the game and shows three random upgrade
# cards; clicking one applies it, consumes one queued level-up, then shows the
# next choice or resumes play. Built in code so it needs no .tscn.

var player: Node
var game: Node
var _cards_box: HBoxContainer
var _title: Label

# id, title, description — applied in _apply()
const POOL := [
	{"id": "hp", "title": "Iron Vitality", "desc": "+30 Max HP\nand heal 30"},
	{"id": "dmg", "title": "Keen Arrows", "desc": "+20% arrow\ndamage"},
	{"id": "rate", "title": "Quickdraw", "desc": "+12% fire\nrate"},
	{"id": "speed", "title": "Swift Boots", "desc": "+10% move\nspeed"},
	{"id": "multi", "title": "Split Shot", "desc": "+1 arrow\nper shot"},
	{"id": "pierce", "title": "Piercing Tips", "desc": "Arrows pierce\n+1 enemy"},
	{"id": "regen", "title": "Grave Mend", "desc": "+1.5 HP/sec\nregeneration"},
]

func open(p: Node, g: Node) -> void:
	player = p
	game = g
	process_mode = Node.PROCESS_MODE_ALWAYS  # keep running while the tree is paused
	layer = 10
	_build()
	_refresh()
	get_tree().paused = true
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

func _build() -> void:
	var dim := ColorRect.new()
	dim.color = Color(0.02, 0.01, 0.05, 0.78)
	dim.anchor_right = 1.0
	dim.anchor_bottom = 1.0
	add_child(dim)

	var center := CenterContainer.new()
	center.anchor_right = 1.0
	center.anchor_bottom = 1.0
	add_child(center)

	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 22)
	col.alignment = BoxContainer.ALIGNMENT_CENTER
	center.add_child(col)

	_title = Label.new()
	_title.text = "LEVEL UP — CHOOSE A PERK"
	_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_title.add_theme_font_size_override("font_size", 34)
	_title.add_theme_color_override("font_color", Color(1.0, 0.62, 0.22))
	_title.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.9))
	_title.add_theme_constant_override("outline_size", 8)
	col.add_child(_title)

	_cards_box = HBoxContainer.new()
	_cards_box.add_theme_constant_override("separation", 20)
	_cards_box.alignment = BoxContainer.ALIGNMENT_CENTER
	col.add_child(_cards_box)

func _refresh() -> void:
	for c in _cards_box.get_children():
		c.queue_free()
	var pool := POOL.duplicate()
	pool.shuffle()
	var remaining = player.pending_levels if player else 0
	_title.text = "LEVEL UP — CHOOSE A PERK  (x%d)" % max(1, remaining)
	for i in min(3, pool.size()):
		_cards_box.add_child(_make_card(pool[i]))

func _make_card(up: Dictionary) -> Button:
	var b := Button.new()
	b.custom_minimum_size = Vector2(230, 190)
	b.text = "%s\n\n%s" % [up.title, up.desc]
	b.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	b.add_theme_font_size_override("font_size", 20)
	b.add_theme_color_override("font_color", Color(0.96, 0.97, 1.0))
	b.add_theme_color_override("font_hover_color", Color(1.0, 0.85, 0.5))
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.10, 0.08, 0.16, 0.96)
	sb.border_color = Color(0.5, 0.35, 0.7)
	sb.set_border_width_all(2)
	sb.set_corner_radius_all(12)
	sb.set_content_margin_all(14)
	var sb_hover := sb.duplicate()
	sb_hover.bg_color = Color(0.18, 0.12, 0.26, 0.98)
	sb_hover.border_color = Color(1.0, 0.62, 0.22)
	b.add_theme_stylebox_override("normal", sb)
	b.add_theme_stylebox_override("hover", sb_hover)
	b.add_theme_stylebox_override("pressed", sb_hover)
	b.add_theme_stylebox_override("focus", sb_hover)
	b.pressed.connect(_on_pick.bind(String(up.id)))
	return b

func _on_pick(id: String) -> void:
	_apply(id)
	if player:
		player.pending_levels = max(0, player.pending_levels - 1)
		if player.pending_levels > 0:
			_refresh()
			return
	_close()

func _apply(id: String) -> void:
	if player == null:
		return
	match id:
		"hp":
			player.max_hp += 30.0
			player.hp = min(player.max_hp, player.hp + 30.0)
		"dmg":
			player.damage *= 1.2
		"rate":
			player.fire_interval = max(0.1, player.fire_interval * 0.88)
		"speed":
			player.move_mult *= 1.1
		"multi":
			player.multishot += 1
		"pierce":
			player.pierce += 1
		"regen":
			player.regen += 1.5

func _close() -> void:
	get_tree().paused = false
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	if game and game.has_method("_on_upgrade_closed"):
		game._on_upgrade_closed()
	queue_free()
