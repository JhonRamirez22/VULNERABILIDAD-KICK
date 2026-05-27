from ddgs import DDGS

def web_research_agent(query):
    with DDGS() as ddgs:
        results = [r for r in ddgs.text(query, max_results=5)]
        return results

if __name__ == "__main__":
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "últimas actualizaciones de Python 2026"
    for res in web_research_agent(query):
        print(f"- {res['title']}: {res['href']}")
