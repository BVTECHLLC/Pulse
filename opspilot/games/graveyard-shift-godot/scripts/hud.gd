extends CanvasLayer
# Minimal, clean HUD: a health bar + XP bar bottom-left, wave/kills/level
# readouts top-left, and a crosshair in the center. Built in code so the whole
# game stays reproducible from scripts.

var hp_bar: ColorRect
var hp_bg: ColorRect
var xp_bar: ColorRect
var xp_bg: ColorRect
var info: Label
var hp_text: Label

func build() -> void:
	var font_col := Color(0.95, 0.97, 1.0)

	# --- top-left info ---
	info = Label.new()
	info.position = Vector2(24, 18)
	info.add_theme_font_size_override("font_size", 24)
	info.add_theme_color_override("font_color", font_col)
	info.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.8))
	info.add_theme_constant_override("outline_size", 6)
	add_child(info)

	# --- crosshair ---
	var cross := Label.new()
	cross.text = "+"
	cross.add_theme_font_size_override("font_size", 28)
	cross.add_theme_color_override("font_color", Color(1, 1, 1, 0.75))
	cross.anchor_left = 0.5
	cross.anchor_top = 0.5
	cross.position = Vector2(-9, -20)
	add_child(cross)

	# --- health bar (bottom-left) ---
	hp_bg = _bar(Vector2(24, -66), Vector2(320, 26), Color(0.1, 0.05, 0.05, 0.85))
	hp_bar = _bar(Vector2(27, -63), Vector2(314, 20), Color(0.85, 0.22, 0.25, 0.95))
	hp_text = Label.new()
	hp_text.position = Vector2(30, -66)
	hp_text.add_theme_font_size_override("font_size", 16)
	hp_text.add_theme_color_override("font_color", font_col)
	hp_text.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.9))
	hp_text.add_theme_constant_override("outline_size", 4)
	hp_text.anchor_top = 1.0
	hp_text.anchor_bottom = 1.0
	add_child(hp_text)

	# --- xp bar (just under health) ---
	xp_bg = _bar(Vector2(24, -34), Vector2(320, 16), Color(0.05, 0.05, 0.1, 0.85))
	xp_bar = _bar(Vector2(27, -31), Vector2(0, 10), Color(0.3, 0.75, 1.0, 0.95))

func _bar(pos: Vector2, size: Vector2, col: Color) -> ColorRect:
	var r := ColorRect.new()
	r.color = col
	r.anchor_top = 1.0
	r.anchor_bottom = 1.0
	r.position = pos
	r.size = size
	add_child(r)
	return r

func update_stats(player: Node, wave: int, kills: int) -> void:
	if info:
		info.text = "GRAVEYARD SHIFT\nWave %d   Kills %d   Lv %d" % [wave, kills, player.level]
	if hp_bar:
		var frac: float = clamp(player.hp / max(1.0, player.max_hp), 0.0, 1.0)
		hp_bar.size.x = 314.0 * frac
	if hp_text:
		hp_text.text = "%d / %d" % [int(round(player.hp)), int(round(player.max_hp))]
	if xp_bar:
		var xf: float = clamp(float(player.xp) / max(1.0, float(player.xp_need)), 0.0, 1.0)
		xp_bar.size.x = 314.0 * xf
