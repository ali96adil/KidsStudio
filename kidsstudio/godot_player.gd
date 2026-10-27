extends Node2D
## KidsStudio Rig-First Player v1: separate transparent layers, pivot joints,
## fixed delta-time playback and action beats. Preview is NOT release approval.

const FRAME := Vector2(1280.0, 720.0)
var _parts: Dictionary = {}
var _rig: Node2D
var _origin: Vector2 = Vector2.ZERO
var _beats: Array = []
var _elapsed: float = 0.0
var _duration: float = 12.0


func _parse_json(resource_path: String) -> Dictionary:
    var raw: String = FileAccess.get_file_as_string(resource_path)
    var value: Variant = JSON.parse_string(raw)
    if typeof(value) != TYPE_DICTIONARY:
        push_error("INVALID_JSON_RESOURCE: " + resource_path)
        get_tree().quit(1)
        return {}
    return value


func _ready() -> void:
    var manifest: Dictionary = _parse_json("res://rig.json")
    var scene: Dictionary = _parse_json("res://scene_spec.json")
    if manifest.is_empty() or scene.is_empty():
        return

    _duration = float(scene["duration_seconds"])
    _beats = scene["beats"]
    var canvas: Dictionary = manifest["canvas"]
    var width: float = float(canvas["width"])
    var height: float = float(canvas["height"])
    var scale_factor: float = min(1152.0 / width, 648.0 / height)
    _origin = (FRAME - Vector2(width, height) * scale_factor) / 2.0

    _rig = Node2D.new()
    _rig.name = "CharacterRig"
    _rig.position = _origin
    _rig.scale = Vector2.ONE * scale_factor
    add_child(_rig)

    var head_pivot: Vector2 = Vector2.ZERO
    for part in manifest["parts"]:
        if str(part["id"]) == "head":
            head_pivot = Vector2(float(part["pivot"][0]), float(part["pivot"][1]))
            break

    # Assemble all pivots first so the parent joint always exists.
    for part in manifest["parts"]:
        var joint: Node2D = Node2D.new()
        var part_id: String = str(part["id"])
        joint.name = part_id
        joint.z_as_relative = false
        joint.z_index = int(part["z"])
        _parts[part_id] = joint

    for part in manifest["parts"]:
        var part_id: String = str(part["id"])
        var px: float = float(part["pivot"][0])
        var py: float = float(part["pivot"][1])
        var pivot: Vector2 = Vector2(px, py)
        var joint: Node2D = _parts[part_id]

        # These face details follow head tilt, while ears retain own pivots.
        var head_child: bool = part_id in [
            "ear_left", "ear_right", "eyes", "mouth", "eyebrows", "nose"
        ]
        if head_child:
            joint.position = pivot - head_pivot
            (_parts["head"] as Node2D).add_child(joint)
        else:
            joint.position = pivot
            _rig.add_child(joint)

        var layer: Sprite2D = Sprite2D.new()
        layer.name = "Artwork"
        layer.centered = false
        layer.position = -pivot
        # Read PNG bytes directly: a newly exported Godot project may not have
        # an imported resource database yet. ImageTexture avoids editor/import
        # prerequisites for automated offline renders and native CI.
        var layer_image: Image = Image.new()
        var load_status: Error = layer_image.load(
            "res://assets/" + part_id + ".png"
        )
        if load_status != OK:
            push_error("RIG_LAYER_MISSING: " + part_id)
            get_tree().quit(1)
            return
        layer.texture = ImageTexture.create_from_image(layer_image)
        joint.add_child(layer)

    queue_redraw()


func _draw() -> void:
    draw_rect(Rect2(Vector2.ZERO, FRAME), Color("#f7f6ef"), true)


func _process(delta: float) -> void:
    if _rig == null or _beats.is_empty():
        return

    _elapsed += delta
    var t: float = fmod(_elapsed, _duration)
    var motion: String = "neutral"
    var phase: float = 0.0

    for beat in _beats:
        var start: float = float(beat["start"])
        var ending: float = float(beat["end"])
        if t >= start and t < ending:
            motion = str(beat["motion"])
            phase = (t - start) / (ending - start)
            break

    _rig.position = _origin
    for key in _parts:
        (_parts[key] as Node2D).rotation_degrees = 0.0

    var pulse: float = sin(PI * phase)
    var cycle: float = sin(TAU * phase)
    match motion:
        "wave_right":
            (_parts["arm_right"] as Node2D).rotation_degrees = -70.0 * pulse
            (_parts["head"] as Node2D).rotation_degrees = -7.0 * cycle
        "wave_left":
            (_parts["arm_left"] as Node2D).rotation_degrees = 70.0 * pulse
            (_parts["head"] as Node2D).rotation_degrees = -7.0 * cycle
        "head_tilt":
            (_parts["head"] as Node2D).rotation_degrees = -14.0 * cycle
        "jump":
            _rig.position.y -= 75.0 * pulse
        "walk":
            (_parts["leg_left"] as Node2D).rotation_degrees = -22.0 * cycle
            (_parts["leg_right"] as Node2D).rotation_degrees = 22.0 * cycle
            (_parts["arm_left"] as Node2D).rotation_degrees = 17.0 * cycle
            (_parts["arm_right"] as Node2D).rotation_degrees = -17.0 * cycle
        "neutral":
            pass
