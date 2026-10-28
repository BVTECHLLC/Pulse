extends CanvasLayer
# Level-up "choose a perk" screen. Pauses the run and offers three cards drawn
# from: new auto-weapons, upgrades to weapons you already carry, and passive
# stat boosts. Picking one applies it, consumes a queued level-up, then shows
# the next choice or resumes. Built in code so it needs no .tscn.

var player: Node
var game: Node
var _cards_box: HBoxContainer
var _title: Label

const PASSIVES := [
	{"kind": "passive", "id": "hp",     "title": "Iron Vitality", "desc": "+30 Max HP\n& heal 30"},
	{"kind": "passive", "id": "dmg",    "title": "Dark Power",    "desc": "+15% all\ndamage"},
	{"kind": "passive", "id": "speed",  "title": "Swift Boots",   "desc": "+10% move\nspeed"},
	{"kind": "passive", "id": "regen",  "title": "Grave Mend",    "desc": "+1.5 HP/sec\nregen"},
	{"kind": "passive", "id": "armor",  "title": "Bone Plate",    "desc": "+2 armor\n(less damage)"},
	{"kind": "passive", "id": "pickup", "title": "Soul Magnet",   "desc": "+40% pickup\nrange"},
]

func open(p: Node, g: Node) -> void:
	player = p
	game = g
	process_mode = Node.PROCESS_MODE_ALWAYS
	layer = 10
	_build()
	_refresh()
	get_tree().paused = true
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

func _build() -> void:
	var dim := ColorRect.new()
	dim.color = Color(0.02, 0.01, 0.05, 0.8)
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

func _build_offers() -> Array:
	var offers: Array = []
	var owned: int = player.weapons.size()
	for id in Weapon.DEFS.keys():
		if not player.has_weapon(id):
			if owned < 6:
				offers.append({"kind": "weapon", "id": id,
					"title": "NEW\n" + str(Weapon.DEFS[id]["name"]), "desc": "Add this\nauto-weapon"})
		else:
			var w = player.get_weapon(id)
			if w.level < w.max_level:
				offers.append({"kind": "weaponup", "id": id,
					"title": str(Weapon.DEFS[id]["name"]) + "\nL" + str(w.level + 1), "desc": "Upgrade\nthis weapon"})
	for p in PASSIVES:
		offers.append(p)
	offers.shuffle()
	return offers

func _refresh() -> void:
	for c in _cards_box.get_children():
		c.queue_free()
	var remaining = player.pending_levels if player else 1
	_title.text = "LEVEL UP — CHOOSE A PERK  (x%d)" % max(1, remaining)
	var offers := _build_offers()
	for i in min(3, offers.size()):
		_cards_box.add_child(_make_card(offers[i]))

func _make_card(offer: Dictionary) -> Button:
	var b := Button.new()
	b.custom_minimum_size = Vector2(230, 200)
	b.text = "%s\n\n%s" % [offer.title, offer.desc]
	b.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	b.add_theme_font_size_override("font_size", 20)
	b.add_theme_color_override("font_color", Color(0.96, 0.97, 1.0))
	b.add_theme_color_override("font_hover_color", Color(1.0, 0.85, 0.5))
	var accent := Color(1.0, 0.62, 0.22) if offer.kind != "passive" else Color(0.5, 0.75, 1.0)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.10, 0.08, 0.16, 0.96)
	sb.border_color = Color(0.45, 0.33, 0.6)
	sb.set_border_width_all(2)
	sb.set_corner_radius_all(12)
	sb.set_content_margin_all(14)
	var sbh := sb.duplicate()
	sbh.bg_color = Color(0.18, 0.12, 0.26, 0.98)
	sbh.border_color = accent
	b.add_theme_stylebox_override("normal", sb)
	b.add_theme_stylebox_override("hover", sbh)
	b.add_theme_stylebox_override("pressed", sbh)
	b.add_theme_stylebox_override("focus", sbh)
	b.pressed.connect(_on_pick.bind(offer))
	return b

func _on_pick(offer: Dictionary) -> void:
	_apply(offer)
	if player:
		player.pending_levels = max(0, player.pending_levels - 1)
		if player.pending_levels > 0:
			_refresh()
			return
	_close()

func _apply(offer: Dictionary) -> void:
	if player == null:
		return
	match offer.kind:
		"weapon", "weaponup":
			player.add_weapon(String(offer.id))
		"passive":
			_apply_passive(String(offer.id))

func _apply_passive(id: String) -> void:
	match id:
		"hp":
			player.max_hp += 30.0
			player.hp = min(player.max_hp, player.hp + 30.0)
		"dmg":
			player.damage_mult *= 1.15
		"speed":
			player.move_mult *= 1.1
		"regen":
			player.regen += 1.5
		"armor":
			player.armor += 2.0
		"pickup":
			player.pickup_range *= 1.4

func _close() -> void:
	get_tree().paused = false
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	if game and game.has_method("_on_upgrade_closed"):
		game._on_upgrade_closed()
	queue_free()
