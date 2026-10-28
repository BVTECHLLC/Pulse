extends CanvasLayer
# Run HUD: survive-to-dawn timer (top center), title + kills + level (top left),
# the carried weapons list, and health + XP bars (bottom left). Built in code.

var hp_bar: ColorRect
var xp_bar: ColorRect
var info: Label
var hp_text: Label
var timer: Label
var weps: Label

const FONT := Color(0.95, 0.97, 1.0)

func build() -> void:
	timer = _label(Vector2(0, 16), 40, Color(1.0, 0.85, 0.45))
	timer.anchor_left = 0.5
	timer.anchor_right = 0.5
	timer.offset_left = -120
	timer.offset_right = 120
	timer.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER

	info = _label(Vector2(24, 18), 24, FONT)

	weps = _label(Vector2(24, -150), 18, Color(0.8, 0.9, 1.0))
	weps.anchor_top = 1.0
	weps.anchor_bottom = 1.0

	# health bar
	_bar_bg(Vector2(24, -66), Vector2(320, 26), Color(0.1, 0.05, 0.05, 0.85))
	hp_bar = _bar(Vector2(27, -63), Vector2(314, 20), Color(0.85, 0.22, 0.25, 0.95))
	hp_text = _label(Vector2(30, -66), 16, FONT)
	hp_text.anchor_top = 1.0
	hp_text.anchor_bottom = 1.0

	# xp bar
	_bar_bg(Vector2(24, -34), Vector2(320, 16), Color(0.05, 0.05, 0.1, 0.85))
	xp_bar = _bar(Vector2(27, -31), Vector2(0, 10), Color(0.3, 0.75, 1.0, 0.95))

func _label(pos: Vector2, size: int, col: Color) -> Label:
	var l := Label.new()
	l.position = pos
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", col)
	l.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.85))
	l.add_theme_constant_override("outline_size", 6)
	add_child(l)
	return l

func _bar_bg(pos: Vector2, size: Vector2, col: Color) -> void:
	_bar(pos, size, col)

func _bar(pos: Vector2, size: Vector2, col: Color) -> ColorRect:
	var r := ColorRect.new()
	r.color = col
	r.anchor_top = 1.0
	r.anchor_bottom = 1.0
	r.position = pos
	r.size = size
	add_child(r)
	return r

func update_run(game: Node, player: Node) -> void:
	if timer:
		timer.text = "%s  /  %s" % [_fmt(game.run_time), _fmt(game.dawn)]
	if info:
		info.text = "GRAVEYARD SHIFT\nKills %d    Lv %d" % [game.kills, player.level]
	if weps:
		var names: Array = []
		for w in player.weapons:
			names.append(w.label())
		weps.text = "WEAPONS\n" + ("\n".join(names) if names.size() > 0 else "—")
	if hp_bar:
		hp_bar.size.x = 314.0 * clamp(player.hp / max(1.0, player.max_hp), 0.0, 1.0)
	if hp_text:
		hp_text.text = "%d / %d" % [int(round(player.hp)), int(round(player.max_hp))]
	if xp_bar:
		xp_bar.size.x = 314.0 * clamp(float(player.xp) / max(1.0, float(player.xp_need)), 0.0, 1.0)

func _fmt(t: float) -> String:
	return "%d:%02d" % [int(t) / 60, int(t) % 60]
