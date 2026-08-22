from __future__ import annotations

from uuid import uuid4

import pytest

from vibesound.rendering import InvalidRenderRequestError, RenderCommand, RenderRequest


def test_render_request_requires_exactly_one_positive_range() -> None:
    with pytest.raises(InvalidRenderRequestError):
        RenderRequest()
    with pytest.raises(InvalidRenderRequestError):
        RenderRequest(bars=1, seconds=1.0)
    with pytest.raises(InvalidRenderRequestError):
        RenderRequest(bars=0)
    with pytest.raises(InvalidRenderRequestError):
        RenderRequest(seconds=0.0)
    with pytest.raises(InvalidRenderRequestError):
        RenderRequest(seconds=float("inf"))


def test_render_commands_validate_operation_fields_and_order() -> None:
    track_id = uuid4()
    scene_id = uuid4()
    with pytest.raises(InvalidRenderRequestError):
        RenderCommand(frame=0, operation="launch_slot", track_id=track_id)
    with pytest.raises(InvalidRenderRequestError):
        RenderCommand(frame=0, operation="launch_scene", scene_id=scene_id, track_id=track_id)
    with pytest.raises(InvalidRenderRequestError):
        RenderCommand(frame=0, operation="stop_all", track_id=track_id)
    with pytest.raises(InvalidRenderRequestError):
        RenderRequest(
            seconds=1.0,
            commands=(
                RenderCommand(frame=2, operation="stop_all"),
                RenderCommand(frame=1, operation="stop_all"),
            ),
        )


def test_commands_are_normalized_to_an_immutable_tuple() -> None:
    request = RenderRequest(
        seconds=1.0,
        commands=[RenderCommand(frame=0, operation="stop_all")],
    )

    assert isinstance(request.commands, tuple)
