"""Prepare a reviewed animation manifest from independently inspected batch videos.

This never marks animation QA as PASS. It only pins inspected hashes and
requires explicit QA decisions before composition.
"""
from __future__ import annotations

import copy

from .m67_batch_inspection import inspect_batch


class AnimationManifestError(ValueError):
    pass


def attach_animations(manifest, batch, root, workspace):
    inspected = inspect_batch(manifest, batch, root, workspace)
    if inspected["status"] != "RENDERS_VERIFIED_PENDING_QA":
        raise AnimationManifestError(inspected.get("reason", "inspection failed"))
    if manifest.get("public_release_authorized") is not False:
        raise AnimationManifestError("unsafe release flag")
    result = copy.deepcopy(manifest)
    for asset, video in zip(result["assets"], inspected["videos"]):
        asset["godot_animation"] = video["path"]
        asset["godot_animation_sha256"] = video["sha256"]
        asset["godot_animation_qa"] = "PENDING"
    return result
