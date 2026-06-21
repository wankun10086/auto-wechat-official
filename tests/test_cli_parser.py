from cli import build_parser


def test_cli_accepts_mock_model_for_doctor_and_topic():
    parser = build_parser()

    doctor_args = parser.parse_args(["doctor", "--model", "mock"])
    topic_args = parser.parse_args([
        "from-topic",
        "AI Agent 产品趋势",
        "--model",
        "mock",
        "--image-model",
        "mock",
        "--no-images",
    ])

    assert doctor_args.model == "mock"
    assert topic_args.model == "mock"
    assert topic_args.image_model == "mock"
    assert topic_args.no_images is True
