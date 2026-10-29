extends CanvasLayer
# Main menu: title, pick a class, pick a difficulty, see banked soul-shards, and
# begin the run. The graveyard slowly orbits behind it (camera handled by game).

var game: Node
var sel_class := "rogue"
var sel_diff := "mid"
var _class_btns := {}
var _diff_btns := {}

func open(g: Node) -> void:
	game = g
	layer = 10
	_build()

func _build() -> void:
	var dim := ColorRect.new()
	dim.color = Color(0.02, 0.01, 0.05, 0.55)
	dim.anchor_right = 1.0
	dim.anchor_bottom = 1.0
	add_child(dim)

	var root := VBoxContainer.new()
	root.anchor_left = 0.5
	root.anchor_right = 0.5
	root.anchor_top = 0.08
	root.offset_left = -470
	root.offset_right = 470
	root.add_theme_constant_override("separation", 14)
	root.alignment = BoxContainer.ALIGNMENT_CENTER
	add_child(root)

	root.add_child(_title("GRAVEYARD SHIFT", 56, Color(1.0, 0.62, 0.22)))
	root.add_child(_title("Survive the night. The dead don't clock out.", 22, Color(0.85, 0.88, 1.0)))

	var meta: Dictionary = game._load_save()
	root.add_child(_title("Soul-shards banked: %d     •     Best: %s" % [
		int(meta.get("shards", 0)), _fmt(float(meta.get("best_time", 0.0)))], 18, Color(0.5, 0.85, 1.0)))

	root.add_child(_title("CHOOSE YOUR ADVENTURER", 24, Color(1.0, 0.85, 0.5)))
	var classes := HBoxContainer.new()
	classes.add_theme_constant_override("separation", 18)
	classes.alignment = BoxContainer.ALIGNMENT_CENTER
	root.add_child(classes)
	for id in game.CLASSES.keys():
		var c = game.CLASSES[id]
		var b := _card("%s\n\n%s" % [c["name"], c["blurb"]], Vector2(280, 180))
		b.pressed.connect(func(): sel_class = id; _restyle())
		_class_btns[id] = b
		classes.add_child(b)

	root.add_child(_title("DIFFICULTY", 24, Color(1.0, 0.85, 0.5)))
	var diffs := HBoxContainer.new()
	diffs.add_theme_constant_override("separation", 14)
	diffs.alignment = BoxContainer.ALIGNMENT_CENTER
	root.add_child(diffs)
	for id in game.DIFFS.keys():
		var d = game.DIFFS[id]
		var b := _card(str(d["name"]), Vector2(170, 56))
		b.pressed.connect(func(): sel_diff = id; _restyle())
		_diff_btns[id] = b
		diffs.add_child(b)

	var begin := _card("BEGIN THE SHIFT", Vector2(360, 66))
	begin.add_theme_font_size_override("font_size", 28)
	begin.pressed.connect(func(): game.start_run(sel_class, sel_diff))
	var hb := HBoxContainer.new()
	hb.alignment = BoxContainer.ALIGNMENT_CENTER
	hb.add_child(begin)
	root.add_child(hb)

	root.add_child(_title("Move: WASD / arrows    Dodge: Space    Weapons fire automatically", 16, Color(0.7, 0.75, 0.9)))
	_restyle()

func _title(t: String, size: int, col: Color) -> Label:
	var l := Label.new()
	l.text = t
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", col)
	l.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.9))
	l.add_theme_constant_override("outline_size", 7)
	return l

func _card(text: String, size: Vector2) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = size
	b.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	b.add_theme_font_size_override("font_size", 19)
	b.add_theme_color_override("font_color", Color(0.96, 0.97, 1.0))
	return b

func _style(selected: bool) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.17, 0.12, 0.26, 0.98) if selected else Color(0.09, 0.08, 0.15, 0.95)
	sb.border_color = Color(1.0, 0.62, 0.22) if selected else Color(0.4, 0.33, 0.55)
	sb.set_border_width_all(3 if selected else 2)
	sb.set_corner_radius_all(12)
	sb.set_content_margin_all(12)
	return sb

func _restyle() -> void:
	for id in _class_btns:
		var sb := _style(id == sel_class)
		_class_btns[id].add_theme_stylebox_override("normal", sb)
		_class_btns[id].add_theme_stylebox_override("hover", sb)
		_class_btns[id].add_theme_stylebox_override("pressed", sb)
		_class_btns[id].add_theme_stylebox_override("focus", sb)
	for id in _diff_btns:
		var sb := _style(id == sel_diff)
		_diff_btns[id].add_theme_stylebox_override("normal", sb)
		_diff_btns[id].add_theme_stylebox_override("hover", sb)
		_diff_btns[id].add_theme_stylebox_override("pressed", sb)
		_diff_btns[id].add_theme_stylebox_override("focus", sb)

func _fmt(t: float) -> String:
	return "%d:%02d" % [int(t) / 60, int(t) % 60]
