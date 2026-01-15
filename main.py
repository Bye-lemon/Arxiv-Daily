import datetime
from functools import reduce
from itertools import count
from operator import ior
from pathlib import Path
from typing import Dict, Iterator, List

import arxiv
import requests
import tomli
import translators as ts
from jinja2 import Environment, FileSystemLoader

file_loader = FileSystemLoader("templates")
env = Environment(loader=file_loader)
YESTERDAY = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")


def compose(*functions):
    return reduce(lambda f, g: lambda x: f(g(x)), functions, lambda x: x)


def get_authors(authors: List[arxiv.Result.Author]) -> List[str]:
    return list(map(lambda x: x.name, authors))


def get_first_author(authors: List[arxiv.Result.Author]) -> str:
    return authors[0].name

def query_github_code(query: str) -> str:
    results = requests.get("https://api.github.com/search/repositories", params={
        "q": query,
        "sort": "stars",
        "order": "desc"
    }).json()
    return results["items"][0]["html_url"] if "total_count" in results and results["total_count"] > 0 else None

def query_paper_with_code(query: str) -> str:
    results = requests.get(
        "https://arxiv.paperswithcode.com/api/v0/papers/" + query
    ).json()
    return results["official"]["url"] if "official" in results and results["official"] and results["official"]["url"] else None

def get_main_infos(result: arxiv.Result) -> Dict[str, dict]:
    arxiv_id = result.entry_id.split("/")[-1]
    
    # Try multiple translators as fallback
    abstract = result.summary.replace("\n", " ")
    abstract_zh = ""
    for translator in ["google", "bing", "alibaba"]:
        try:
            abstract_zh = ts.translate_text(
                abstract,
                translator=translator,
                from_language="en",
                to_language="zh",
            )
            if abstract_zh:
                break
        except Exception as e:
            print(f"Translation failed with {translator}: {e}")
    
    meta_datas = dict(
        title=result.title.replace("\n", " "),
        authors=", ".join(get_authors(result.authors)),
        first_author=get_first_author(result.authors),
        update_time=result.updated.date().strftime("%Y-%m-%d"),
        submit_time=result.published.date().strftime("%Y-%m-%d"),
        primary_category=result.primary_category,
        pdf_link=result.pdf_url,
        abstract=abstract,
        abstract_zh=abstract_zh,
        github_code_link=query_github_code(result.title),
        paper_with_code_link=query_paper_with_code(arxiv_id.split('v')[0] if 'v' in arxiv_id else arxiv_id),
    )
    return dict({arxiv_id: meta_datas})


def query_arxiv(query: str, max_results: int = 50) -> Dict[str, dict]:
    client = arxiv.Client()
    search_agent = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.LastUpdatedDate,
    )
    return reduce(ior, map(get_main_infos, client.results(search_agent)))


def filter_last_day(infos: Dict[str, dict]) -> Dict[str, dict]:
    return dict(filter(lambda kv: kv[1]["update_time"] == YESTERDAY, infos.items()))


def filter_cs(infos: Dict[str, dict]) -> Dict[str, dict]:
    return dict(filter(lambda kv: kv[1]["primary_category"][:2] == "cs", infos.items()))


def merge_multi_query(query_results: Iterator[Dict[str, dict]]) -> Dict[str, dict]:
    return reduce(ior, query_results)


def convert2list(infos: Dict[str, dict]) -> List[dict]:
    return list(map(lambda kv: dict(arxiv_id=kv[0], **kv[1]), infos.items()))


def add_index(infos: List[dict]) -> List[dict]:
    return list(map(lambda kv: dict(index=kv[0], **kv[1]), enumerate(infos)))


def compose_query_keywords(keywords: List[str]) -> str:
    return " OR ".join(map(lambda x: f'"{x}"', keywords))


def main():
    with (
        Path("keywords.toml").open("rb") as config_file,
        Path("index.html").open("w", encoding="utf-8") as output_file,
    ):
        keywords = tomli.load(config_file)["keywords"]
        query_func = compose(
            compose(add_index, convert2list),
            compose(filter_cs, query_arxiv),
            compose_query_keywords,
        )
        paper_lists = dict(map(lambda kv: (kv[0], query_func(kv[1])), keywords.items()))
        output_file.write(
            env.get_template("index.html").render(
                date_str=YESTERDAY,
                paper_lists=tuple(
                    zip(count(), paper_lists.keys(), paper_lists.values())
                ),
            )
        )


if __name__ == "__main__":
    main()
