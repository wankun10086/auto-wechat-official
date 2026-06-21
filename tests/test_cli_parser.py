from types import SimpleNamespace

import pytest

from cli import build_parser, _ensure_image_requirement_args, _ensure_required_ai_image


def test_cli_accepts_mock_model_for_doctor_and_topic():
    parser = build_parser()

    doctor_args = parser.parse_args(["doctor", "--model", "mock", "--live", "--skip-image-live"])
    topic_args = parser.parse_args([
        "from-topic",
        "AI Agent 产品趋势",
        "--model",
        "mock",
        "--image-model",
        "mock",
        "--require-ai-image",
    ])

    assert doctor_args.model == "mock"
    assert doctor_args.live is True
    assert doctor_args.skip_image_live is True
    assert topic_args.model == "mock"
    assert topic_args.image_model == "mock"
    assert topic_args.require_ai_image is True


def test_require_ai_image_gate_only_fails_when_enabled():
    _ensure_required_ai_image(SimpleNamespace(require_ai_image=False), {"ai_images": []})

    with pytest.raises(SystemExit):
        _ensure_required_ai_image(SimpleNamespace(require_ai_image=True), {"ai_images": []})


def test_require_ai_image_conflicts_with_no_images():
    with pytest.raises(SystemExit):
        _ensure_image_requirement_args(SimpleNamespace(require_ai_image=True, no_images=True))
