from langchain.tools import tool


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the public web via DuckDuckGo and return the top results (title, URL, snippet).
    Use for current events or facts not in your training data."""
    try:
        from ddgs import DDGS
        with DDGS() as ddg:
            results = ddg.text(query, max_results=max_results)
        if not results:
            return "No results found."
        lines = []
        for r in results:
            lines.append(f"Title: {r.get('title', '')}")
            lines.append(f"URL: {r.get('href', '')}")
            lines.append(f"Snippet: {r.get('body', '')}")
            lines.append("")
        return "\n".join(lines).strip()
    except Exception as exc:
        return f"Web search failed: {exc}"
