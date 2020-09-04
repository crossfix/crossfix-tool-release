import csv
import re
import time
import urllib.request
from datetime import datetime, timezone

import javalang
from github import Github
from github import RateLimitExceededException
from loguru import logger
from requests.exceptions import ReadTimeout
from unidiff import PatchSet

import util
import base64
import json

# util.init_logger(__file__)

from util import SS

ss = SS(port=7890)

# using token
from persontoken import MY_TOKEN
g = Github(MY_TOKEN)


def build_graph(g, full_name):
    repo = g.get_repo(full_name)
    issues = repo.get_issues()
    self_full_name = repo.full_name
    graph = dict()
    for i in range(issues.totalCount):
        issue = issues[i]
        print(issue.html_url)
        events = issue.get_timeline()
        for event_it in events:
            # repo = issue_ob.repository
            # logger.debug("repo: " + str(repo.full_name))
            # logger.debug("id: " + str(event.commit_id))

            if event_it.event == 'cross-referenced':
                # this issue cites by other issue (other isue cites this issue)
                # print(event_it.source.issue.number)
                print(event_it.source.issue.repository.full_name)
                ref_full_name = event_it.source.issue.repository.full_name
                if ref_full_name != self_full_name:
                    if ref_full_name not in graph:
                        graph[ref_full_name] = {
                            'ref': 0,
                            'cite': 0
                        }
                    graph[ref_full_name]['ref'] += 1
            elif event_it.body:
                # this issue cites other issue
                name_no_list = re.findall(r'https:\/\/github\.com\/(\S*?\/[^\s\/]*)\/issues\/(\d+)', event_it.body)
                for t in name_no_list:
                    ref_full_name, no = t
                    if ref_full_name != self_full_name:
                        if ref_full_name not in graph:
                            graph[ref_full_name] = {
                                'ref': 0,
                                'cite': 0
                            }
                        print(ref_full_name)
                        graph[ref_full_name]['cite'] += 1
        print(graph)
    return graph


def load_json(file_path):
    try:
        with open(file_path, 'r') as load_f:
            data = json.load(load_f)
            return data
    except FileNotFoundError:
        return dict()


def dump_json(file_path, data):
    with open(file_path, 'w') as f:
        json.dump(data, f)


SKIP_EXSIST = True
while True:
    try:
        urls = util.read_csv('f-droid/f-droid-github-filter.csv')
        urls = util.get_col(urls, 3)
        for url in urls:
            data = load_json("graph.json")
            this_repo = "/".join(url.split("/")[-2:])
            if SKIP_EXSIST and this_repo in data:
                continue
            graph = build_graph(g, this_repo)
            data[this_repo] = graph
            dump_json("graph.json", data)
        exit(0)
    except:
        import traceback
        traceback.print_exc()
