from agenttrace.services.report_renderer import render_markdown_report


def test_render_markdown_report_orders_sections_and_embeds_mermaid():
    sections = [
        {
            "section_id": 2,
            "title": "2. 학습 이정표",
            "body_markdown": "두 번째",
            "mermaid_diagram": None,
        },
        {
            "section_id": 1,
            "title": "1. 핵심 요약",
            "body_markdown": "첫 번째",
            "mermaid_diagram": "flowchart TD\n  A --> B",
        },
    ]

    markdown = render_markdown_report(sections)

    assert markdown.startswith("# 1. 핵심 요약")
    assert "# 2. 학습 이정표" in markdown
    assert "```mermaid\nflowchart TD\n  A --> B\n```" in markdown


def test_render_markdown_report_strips_existing_heading_marker():
    markdown = render_markdown_report(
        [{"section_id": 1, "title": "# 1. 핵심 요약", "body_markdown": "본문"}]
    )

    assert markdown.startswith("# 1. 핵심 요약")
    assert not markdown.startswith("##")
