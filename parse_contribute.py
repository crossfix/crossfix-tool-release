from github import Github
from github.GithubException import RateLimitExceededException

from util import SS, init_logger
import csv
import re
from loguru import logger
import traceback

# change this: open a GitHub account and get your API token
import util

from crawlermy import contain_fix, is_android_repo, search_exception, api_wait_search


# issue_file = open('issues_file_contribute.csv', mode='a+')
# issue_writer = csv.writer(issue_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)


def filter_non_en(text):
    chinese_char = re.search(u'[\u4e00-\u9fff]', text)
    if chinese_char:
        return True
    return False


# def has_fix(issue, repo):
#     # Get pull request to the issue
#     pr = issue.pull_request
#     # print(pr)
#     if pr is not None:
#         print("is pull request" + issue.html_url)
#         return True
#     else:
#         # Get events for that issue
#         events = issue.get_events()
#         found = False
#         for event in events:
#             if event.commit_id is not None:
#                 found = True
#         return found
#     return False


def is_nonbug(text):
    text = text.lower()
    if re.match(r".*\?", text):
        # match "?"
        return True
    if "how " in text or "what " in text:
        return True
    if re.match(r"\blicense\s?", text):
        return True
    if re.match(r"\blogo\s?", text):
        return True
    if re.match(r"\bquestion\s?", text):
        return True
    if "doc" in text:
        return True
    return False


# for issues without label, assume that it is a bug
def select_issue_label(labels):
    is_bug = True
    for lbl in labels:
        label = lbl.name.lower()
        print("label:" + label)
        if "bug" in label:
            is_bug = True
        elif "enhancement" in label:
            is_bug = False
        elif "question" in label:
            is_bug = False
        elif "doc" in label:
            is_bug = False
        elif "logo" in label:
            is_bug = False
        elif "web" in label:
            is_bug = False
    return is_bug


def is_invalid(issue_ob):
    keywords = {'invalid', }
    flag = False
    for lab in issue_ob.labels:
        if flag:
            break
        for key in keywords:
            if key in lab.name:
                flag = True
                break
    return flag


def is_feature_request(issue_ob):
    keywords = {'feature', 'enhancement'}
    flag = False
    for lab in issue_ob.labels:
        # 1. find label
        if flag:
            break
        for key in keywords:
            if key in lab.name:
                flag = True
                break
    if not flag:
        # 2. if no such label, find it in title
        for key in keywords:
            if key in issue_ob.title.lower():
                flag = True
                break
    return flag


def get_top_java_repo(g, id, only_android=False):
    file_name = f"openissues_repo_{str(id)}.csv"
    data = util.read_csv(file_name)
    repos = util.get_col(data, 0)
    old_repos = set(repos)

    repos = g.search_repositories(query='language:java', sort="stars", order="desc", language="Java")
    ilistdict = dict()

    with open(file_name, "a+", encoding="utf-8") as file:
        for index in range(repos.totalCount):
            api_wait_search(g)
            repo = repos[index]
            if repo.full_name in old_repos:
                continue
            if only_android ^ is_android_repo(g, repo.full_name):
                # 相同为True
                logger.info(f"skip {repo.full_name}")
                continue
            file.write(repo.full_name + "," + repo.html_url + "\n")
            file.flush()


def download_new_issues(g, urls, id, shuffle=False):
    if shuffle:
        import random
        random.shuffle(urls)

    with open(f"openissues_{str(id)}.csv", "a+", encoding="utf-8") as fp:
        for url in urls:
            repo_name = "/".join(url.split("/")[-2:])
            repo = g.get_repo(repo_name)
            iss = repo.get_issues(state='open')
            selected_no = 0
            for i in iss:
                # skipping issues from same repo
                if selected_no > 20:
                    break
                logger.info("repo:" + repo.full_name + ":" + i.html_url + ", label:" + str(i.get_labels().totalCount))
                if contain_fix(g, i) or i.pull_request:
                    logger.info("fixed repo:" + repo.full_name + ":" + i.html_url)
                elif i.get_labels() is None or select_issue_label(i.get_labels()):
                    if i.body is None or filter_non_en(i.body) or filter_non_en(i.title) or is_nonbug(i.title) or is_invalid(i):
                        logger.info("chinese issues:" + i.title + ":" + i.html_url)
                    else:
                        if search_exception(i.body):
                            logger.info("selected issues:" + i.title + ":" + i.html_url)
                            # !!! important
                            fp.write(repo.full_name + "," + i.html_url + "," + i.title + "\n")
                            fp.flush()
                            selected_no = selected_no + 1
                    # ilistdict[i.html_url] = repo.full_name
                else:
                    logger.info("nonselected issues:" + i.title + ":" + i.html_url)


if __name__ == "__main__":
    init_logger(__file__)

    from persontoken import MY_TOKENs

    tklen = len(MY_TOKENs)
    tk_i = 0
    ss = SS(port=7890)
    android = False
    id = 12
    while True:
        g = Github(MY_TOKENs[tk_i % tklen])
        try:
            # get_top_java_repo(g, 6, only_android=False)

            if android:
                urls = util.read_csv('f-droid/f-droid-github-filter.csv')
                urls = util.get_col(urls, 3)
            else:
                urls = util.read_csv('java_repo_list.csv')
                urls = util.get_col(urls, 1)
            download_new_issues(g, urls, id, shuffle=True)
        except RateLimitExceededException:
            logger.error(traceback.format_exc())
            tk_i += 1
        else:
            logger.error(traceback.format_exc())
