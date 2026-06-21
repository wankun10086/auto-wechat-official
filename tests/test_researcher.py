from src.content.researcher import TopicResearcher


def test_duckduckgo_redirect_urls_are_normalized():
    researcher = TopicResearcher()
    urls = researcher._dedupe_urls([
        "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa%3Fx%3D1&rut=abc",
        "https://example.com/b",
        "#",
    ])

    assert urls == ["https://example.com/a?x=1", "https://example.com/b"]
