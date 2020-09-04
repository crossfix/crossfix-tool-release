import base64
import fnmatch
import json
import os
import re
import string
import time
import urllib.request
from collections import namedtuple
from datetime import datetime, timezone

import javalang
from github import Github
from github import RateLimitExceededException
from github.Issue import Issue
from loguru import logger
from plagcheck import check
from requests.exceptions import ReadTimeout
from unidiff import PatchSet
from unidiff.errors import UnidiffParseError

import java_invoke
import keywords
import nlp_util
import util


# util.init_logger(__file__)

# using token

# filter: for open issue, generate query

def rate_limited_retry(times=3):
    def decorator(func):
        def ret(*args, **kwargs):
            for _i in range(times):
                if _i > 0:
                    logger.debug(f"Retry the {_i} times.")
                try:
                    return func(*args, **kwargs)
                except RateLimitExceededException as e:
                    if _i == times - 1:
                        # 最后一次尝试失效
                        raise Exception("Failed too many times")

                    limits = g.get_rate_limit()
                    reset = limits.search.reset.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    PADDING = 5
                    seconds = PADDING + (reset - now).total_seconds()
                    logger.debug(f"Rate limit exceeded")
                    logger.debug(f"Reset is in {seconds:.3g} seconds.")
                    if seconds > 0.0:
                        logger.debug(f"Waiting for {seconds:.3g} seconds...")
                        time.sleep(seconds)
                        logger.debug("Done waiting - resume!")
                except ReadTimeout as e:
                    logger.debug("ReadTimeout... Retry")

        return ret

    return decorator


@rate_limited_retry()
def api_wait_search(git):
    limits = git.get_rate_limit()  # 包含网络请求
    logger.info("Remain %d times ..." % limits.search.remaining)
    if limits.search.remaining <= 3:
        seconds = (limits.search.reset - datetime.now()).total_seconds()
        if seconds > 0:
            logger.debug("Waiting for %d seconds ..." % seconds)
            time.sleep(seconds)
            logger.debug("Done waiting - resume!")


def _intercept_code_section(body):
    start = False
    inside_str = ""
    str_list = []
    for line in body.splitlines():
        if re.findall(r'^\s*`+', line):
            if not start:
                # [start of code block] start == False
                start = True
                inside_str = re.sub(r'^\s*`+', "", line)
            else:
                # [end of code block] start == True
                start = False
                assert inside_str
                str_list.append(inside_str)
                inside_str = ""
        elif start:
            inside_str = inside_str + "\n" + line

    result = []
    for _item in str_list:
        if "Exception" in _item or "Error" in _item:
            result.append(_item)
    return result


def _parse_exception_name(text):
    exception_name = ""
    if "Exception" in text and "." in text:
        names = text.split(".")
        exception_name = names[len(names) - 1]
    return exception_name


def parse_exception(body):
    """
    parse code block, or parse a line in body
    """
    a_exception = namedtuple('LogException', ['name', 'msg', 'cause'])
    exception_name = ""
    exception_rest = ""
    if "Caused by:" in body:
        for line in body.splitlines():
            cause_result = re.search(r'Caused by(\s*:?\s*)([^:\s]*)(: ([^:\n]*))?', line)
            if cause_result:
                exception_name = cause_result.group(2)
                exception_rest = cause_result.group(4) if cause_result.group(4) else ""
                logger.debug("exception name: " + exception_name + " ####: #### " + exception_rest)
                return a_exception._make([exception_name, exception_rest, True])
    else:  # fallback, normal Exception
        for line in body.splitlines():
            cause = re.search(r'([a-zA-Z.]*(Exception|Error))(\s*:\s*)([^:\n]+)', line)
            if cause:
                exception_name = cause.group(1)
                exception_rest = cause.group(4) if cause.group(3) else ""
                logger.debug("exception name: " + exception_name + " ####: #### " + exception_rest)
                return a_exception._make([exception_name, exception_rest, False])
    return a_exception._make([exception_name, exception_rest, False])


def parse_diff(diff_url, file):
    # TODO
    logger.debug("url:" + diff_url)
    diff = urllib.request.urlopen(diff_url)
    encode = diff.headers.get_charsets()[0]
    patch = PatchSet(diff, encoding=encode)
    for p in patch:
        logger.debug("PARSERD:" + str(p))
        if p.is_removed:
            logger.debug("removed:" + str(p))
        token = list(javalang.tokenizer.tokenize(file.patch))
        logger.debug("token:" + str(token))


def _get_remove_patch(patch):
    # get patch start by "-"
    removed = ""
    for line in patch.splitlines():
        if line.startswith("-"):
            removed = removed + line[1:] + "\n"
        # else:
        #    removed = removed + line + "\n"
    return removed


def commit_diff_prepare(patch_url, other_repo_full_name):
    # prepare for code diff, download patch code and other repo code(default branch)
    patch_body = util.get_github_content(patch_url, mode='text')
    sha = re.search(r'From ([0-9a-fA-F]+)', patch_body).group(1)

    repo_name = r"/".join(patch_url.split(r'/')[-4:-2])
    diff_url = patch_url.replace(".patch", ".diff")
    diff = util.get_github_content(diff_url, mode='text')

    patch = PatchSet(diff, metadata_only=True)
    focus_paths = set()
    for _fi in patch.modified_files:
        focus_paths.add(_fi.path)
    for _fi in patch.added_files:
        focus_paths.add(_fi.path)
    logger.debug(focus_paths)

    local_prefix = f'./tmp/{repo_name.replace("/", "_")}_{sha}/'
    for p in focus_paths:
        local_file_name = os.path.join(local_prefix, p)
        keywords.download_code_file(repo_name, sha, p, local_file_name)

    local_file_path = keywords.download_code(f'https://github.com/{other_repo_full_name}',
                                             f'./tmp/{other_repo_full_name.replace("/", "_")}.zip',
                                             skip_if_exist=True)
    ex_dir = keywords.extract(local_file_path, "./tmp")
    return local_prefix, ex_dir


def _get_res_by_ext(loc_res_dir, exten_list):
    """
    get files by extension list
    Args:
        loc_res_dir: directory to walk
        exten_list: list like ['c', 'h', 'cpp', 'hpp']

    Returns:
        file list
    """

    files_list = list()
    for r, d, files in os.walk(loc_res_dir):
        for ext in exten_list:
            code_files = fnmatch.filter(files, '*.' + ext)
            if len(code_files) > 0:
                tmp_paths = [os.path.join(os.path.abspath(r), f) for f in code_files]
                files_list.extend(tmp_paths)
    logger.info("Found %d CODE files" % (len(files_list)))
    return files_list


def moss_compare(a_dir, b_dir):
    """
    use moss to compare two folder of codes
    """
    language = 'java'
    ext = ['java']
    userid = '553660367'
    moss = check(language, userid)
    files_list = _get_res_by_ext(a_dir, ext)
    for f in files_list:
        moss.addFile(f)
    files_list = _get_res_by_ext(b_dir, ext)
    for f in files_list:
        moss.addFile(f)
    moss.submit()
    logger.debug(moss.getHomePage())
    result = moss.getResults()
    return result


def have_close_trigger(body: str, number: int) -> bool:
    pat = r'(?:close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)[:\s]+#*(\d+)'
    body = body.lower()
    num_list = re.findall(pat, body)
    flag = False
    for i in num_list:
        if int(i) == number:
            flag = True
            break
    return flag


def last_commits(g, issue_ob: Issue, fast_mod=False):
    # 获取当前 issue 的关联 commit
    is_pr = issue_ob.pull_request
    # logger.debug(is_pr)
    this_repo = issue_ob.repository.full_name
    commits = []
    flag = False
    if is_pr is None:
        events = issue_ob.get_timeline()
        for event_it in events:
            if event_it.event == 'cross-referenced':
                ref_name, _ = util.re_issue(event_it.source.issue.html_url)
                if ref_name == this_repo:
                    if have_close_trigger(event_it.source.issue.body, issue_ob.number):
                        commits.append(event_it.source.issue.pull_request.patch_url)
                        if fast_mod:
                            flag = True
                            break
            if event_it.commit_url:
                repo_name = re.findall(r'https://api\.github\.com/repos/(.*?/[^/]*)/commits/([0-9a-zA-Z]+)',
                                       event_it.commit_url)
                tmp_repo, sha = repo_name[0]
                repo = g.get_repo(tmp_repo)
                commit = repo.get_commit(sha)
                if tmp_repo == this_repo and commit.files:
                    commits.append(sha)
                    if fast_mod:
                        flag = True
                        break
    if fast_mod:
        return flag
    return this_repo, commits


def code_compare_func(mode):
    if mode == 'moss':
        return moss_compare
    elif mode == 'jplag':
        return java_invoke.sim


def issue_based_compare(g, open_iss: Issue, closed_iss: Issue, mode='jplag'):
    """
    Args:
        open_iss: open issue object
        closed_iss: closed issue object
        mode: 'moss', 'jplag'
    Returns:
        True means similar
    """

    compare_func = code_compare_func(mode)

    if open_iss.repository.full_name == closed_iss.repository.full_name:
        return True
    is_pr = closed_iss.pull_request
    # logger.debug(is_pr)
    flag = False
    try:
        if is_pr:
            patch_local_prefix, open_ex_dir = commit_diff_prepare(is_pr.patch_url, open_iss.repository.full_name)
            result = compare_func(patch_local_prefix, open_ex_dir)
            if result:
                logger.debug(result)
                flag = True
        else:
            closed_repo, closed_commits = last_commits(g, closed_iss)
            if closed_commits:
                # use last commit
                last_com = closed_commits[-1]
                if last_com.startswith("http"):
                    patch_url = last_com
                else:
                    patch_url = f'https://github.com/{closed_repo}/commit/{last_com}.patch'
                patch_local_prefix, open_ex_dir = commit_diff_prepare(patch_url, open_iss.repository.full_name)
                result = compare_func(patch_local_prefix, open_ex_dir)
                if result:
                    logger.debug(result)
                    flag = True
    except UnidiffParseError:
        return False
    return flag


def contain_fix(g, issue_ob) -> bool:
    return last_commits(g, issue_ob, fast_mod=True)


@rate_limited_retry()
def extract_bugfix(g, iss_url):
    files = []
    url = "https://github.com/Mexator/SWP-Attendance-tracking-Android-frontend/issues/13"
    # api_wait_search(g)

    issues = g.search_issues(query="ManualMarkingFragment")

    for issue in issues:
        # Get pull request to the issue
        is_pr = issue.pull_request
        logger.debug(is_pr)
        if is_pr is not None:
            logger.debug(is_pr.url)
            logger.debug(is_pr.diff_url)
        else:
            logger.debug(issue.body)
            logger.debug(str(issue.comments))
            # Get events for that issue
            events = issue.get_events()
            for event in events:
                repo = issue.repository
                logger.debug("repo: " + str(repo))
                logger.debug("id: " + str(event.commit_id))
                commit = repo.get_commit(event.commit_id)
                if commit.files:
                    files = commit.files
                    for file in files:
                        if file.deletions > 0:
                            logger.debug(file.deletions)
                            logger.debug("patch:" + file.patch)
                            logger.debug("*******************************")
                            diff_url = event.commit_url.replace("api.", "")
                            diff_url = diff_url.replace("repos/", "")
                            diff_url = diff_url.replace("commits", "commit")
                            diff_url = diff_url + "?diff=unified"
                            logger.debug("url:" + diff_url)
                            removed_patch = _get_remove_patch(file.patch)
                            token = list(javalang.tokenizer.tokenize(removed_patch))
                            # 拿到删除行的token
                            logger.debug("token:" + str(token))
                    logger.debug(str(commit.files))
                logger.debug(event.commit_url)
                logger.debug(event.event)


def get_topic(repo_full_name):
    url = f'https://api.github.com/repos/{repo_full_name}/topics'
    header = util.get_gh_header()
    header['Accept'] = 'application/vnd.github.mercy-preview+json'
    json_ob = util.get_github_content(url, custom_header=header)
    return json_ob['names']


def get_readme(repo_full_name):
    url = f'https://api.github.com/repos/{repo_full_name}/readme'
    json_ob = util.get_github_content(url)
    if 'content' in json_ob:
        return json_ob['content']
    else:
        return b''


def is_android_repo(g, repo_full_name):
    repo = g.get_repo(repo_full_name)
    # topic
    topics = repo.get_topics()
    flag = False
    for t in topics:
        if 'android' in t.lower():
            flag = True
            break
    if flag:
        return flag

    # brief description
    if repo.description and 'android' in repo.description.lower():
        return True
    # README
    readme = get_readme(repo_full_name)
    if 'android' in base64.b64decode(readme).decode().lower():
        return True
    return False


def search_android(body):
    tmp = str(body).lower()
    score = 0
    if "android" in tmp:
        score += 1
    if "steps" and "reproduce" in tmp:
        score += 1
    return score


def parse_condition(body) -> str:
    tmp = str(body).lower()
    for line in tmp.splitlines():
        cause_result = re.search('(.*) (when|if|while) (.*)', line)
        if cause_result:
            return cause_result.group(3)
    return ""


def search_exception(body):
    if body:
        if "beginning of crash" in body:
            # logger.debug("android crash:" + body)
            return True
        elif "Caused by" in body:
            # logger.debug("Causedby" + body)
            return True
        elif "<code>" in body:
            # logger.debug("code:" + body)
            return True
        elif "Exception" in body:
            return True
    return False


def query_over_size(query_list, max_lenth=256):
    query_list = util.uniq_list(query_list)
    query_chars = " ".join(query_list)
    if len(query_chars) <= max_lenth:
        return False
    else:
        return True


def query_limiter(query_list, max_lenth=256, try_times=5):
    # try to summary
    logger.debug(f"query_list: {query_list}")
    for _ in range(try_times):
        query_list.sort(reverse=True, key=lambda k: len(k))
        query_list[0] = cut_text(query_list[0], 70)  # here 70 is a magic number
        if not query_over_size(query_list, max_lenth=max_lenth):
            break
    logger.debug(f"filter query_list: {query_list}")
    return query_list


def cut_text(text, size):
    if len(text) <= size:
        return text
    punct = set()
    for item in string.punctuation:
        punct.add(item)
    for item in string.whitespace:
        punct.add(item)
    last_index = 0
    previous_char = False
    for i in range(size):
        if text[i:i + 1] in punct:
            if previous_char:
                last_index = i
                previous_char = False
        else:
            previous_char = True
    return text[:last_index]


def fast_query(title: str, body: str) -> dict:
    # 给 open issue 的 title 和 body 生成 query
    curr_q = dict()
    curr_q['title'] = title

    ################ exception
    exception = []
    if search_exception(body):
        # get code blocks
        # str_list = _intercept_code_section(body)
        # logger.debug("exception:" + str(str_list))
        for line_text in body.splitlines():
            a_exception = parse_exception(line_text)
            if len(a_exception.name) > 0:
                logger.debug("parse:" + a_exception.__str__())
                short_name = a_exception.name.split(".")[-1]  # 只要 package 名字的最后部分
                a_exception._replace(name=short_name)
                exception.append(a_exception)
    curr_q['exception'] = exception

    ################ condition
    condition = parse_condition(title)
    if len(condition) > 0:
        if "crash" not in condition and ("crash" in title or "crash" in body):
            condition += " crash"
    curr_q['condition'] = condition
    return curr_q


def add_pos(query: str, pos):
    # pos: 'title' or 'body' or 'other'
    if pos == 'title':
        query += " in:title"
    elif pos == 'body':
        query += " in:body,comments"
    return query


def select_detail_exception(exception_list):
    assert exception_list
    for i in range(len(exception_list)):
        if exception_list[i].cause:
            return exception_list[i].name, exception_list[i].msg
    detail = None
    for _item in exception_list:
        exception_name, exception_info, is_cause = _item
        if (not exception_name.isspace()) and (not exception_info.isspace()):
            detail = exception_name, exception_info
            break
    if detail:
        return detail
    else:
        return exception_list[0]


def form_query(curr_q: dict, ignore_token, trace: bool, condition: bool, max_lenth=256):
    # acceptable input of
    # trace,   condition
    # T,       T   -> trace + condition
    # T,       F   -> trace
    # F,       T   -> condition
    # F,       F   -> title

    result = []
    # assert trace ^ condition or not (trace and condition)
    if trace and curr_q['exception']:
        exception_name, exception_info = select_detail_exception(curr_q['exception'])
        result.append(exception_name)
        if not query_over_size(result, max_lenth=max_lenth):
            if condition:
                if curr_q['condition']:
                    size = max_lenth - 20 - len(exception_name) - len(curr_q['condition'])
            else:
                size = max_lenth - 20 - len(exception_name)
            short_info = cut_text(exception_info, size)
            result.append(short_info)
    if condition and curr_q['condition'] != "":
        tmp = nlp_util.tokenize(curr_q['condition'])
        tmp = nlp_util.remove_meanless(tmp, ignore_token)
        result.extend(tmp)

    if not (trace or condition):  # both are false
        title_as_query = curr_q['title']
        title_as_query = nlp_util.tokenize(title_as_query)
        title_as_query = nlp_util.remove_meanless(title_as_query, ignore_token)
        result.extend(title_as_query)
        if query_over_size(result, max_lenth=max_lenth):
            result = query_limiter(result, max_lenth=max_lenth)
    return util.uniq_list(result)


# not use
# @rate_limited_retry()
# def run_open_query(g, import_string, output_path):
#     # 去找 open 的 issue 生成 query
#     # 使用 fast_query()
#     # api_wait_search(g)
#     # query_string = f"language:Java \"{import_string}\""
#     # 已经不用
#
#     # ilinks = g.search_issues(query='type:Issues ' + import_string, state='open', language='java')
#     query = import_string
#     ilinks = g.search_issues(query=query, state='open', language='java', type='issue')
#
#     logger.debug("size:" + str(ilinks.totalCount))
#
#     with open(output_path, "w+", encoding="utf-8", newline='') as file:
#         csvwriter = csv.writer(file, delimiter=',', quotechar='"')
#         for i in range(ilinks.totalCount):
#             api_wait_search(g)
#             issue = ilinks[i]
#             logger.debug(issue.url)
#             if search_android(issue.body) >= 0:
#                 # open issue link, open issue 对应去搜索 closed 的 query
#                 curr_q = fast_query(issue.title, issue.body)
#                 if len(curr_q) > 0:
#                     str_q = " ".join(curr_q)
#                     logger.debug(str(issue.html_url) + "," + str_q)
#                     csvwriter.writerow([str(issue.html_url), str_q])
#             file.flush()
#
#     logger.debug("size:", str(ilinks.totalCount))


@rate_limited_retry()
def run_close_query(g, query: str, only_android: bool,
                    look_depth=20, depth=10,
                    fallback_size=5,
                    ban_fallback=False):
    logger.debug(f'[{len(query)}], {query}')
    ilinks = g.search_issues(query=query, state='closed', language='java')
    # remove issue filter type:issue

    logger.debug("size:" + str(ilinks.totalCount))

    results = dict()
    results["iss"] = list()
    results["info"] = 'NORMAL'
    for i in range(min(ilinks.totalCount, look_depth)):
        if len(results["iss"]) > depth:
            break
        api_wait_search(g)
        issue = ilinks[i]
        logger.debug(issue.url)

        iss_info = []
        # if search_android(issue.body) >= 0:
        if only_android ^ is_android_repo(g, issue.repository.full_name):
            # True when: 1. search only android project T + the issue is android project
            #            2. search java project(exclude android) F + the issue is not android project
            continue
        if contain_fix(g, issue):
            iss_info.append("HAVE-FIX")
        brief = fast_query(issue.title, issue.body)  # TODO add brief
        iss_info.append(brief)
        if len(iss_info) > 0:
            # iss_info_str = " ".join(iss_info)
            iss_info_str = json.dumps(iss_info)
            logger.debug(str(issue.html_url) + "," + iss_info_str)
            results["iss"].append([str(issue.html_url), iss_info])
    if not ban_fallback:
        if len(results["iss"]) == 0:
            results["info"] = 'EMPTY'
        elif len(results["iss"]) < fallback_size:
            results["info"] = 'FALLBACK'
    return results


if __name__ == '__main__':
    from persontoken import MY_TOKEN

    g = Github(MY_TOKEN)
    # extract_bugfix("")
    # results = run_open_query(g, "crash", "crash.csv")
    # results = run_open_query(g, "permission Android")
    # print(run_close_query(g, "google action button page", depth=20))

    # https://api.github.com/repos/arquivo/pwa-technologies/issues/931
    # https://api.github.com/repos/wordpress-mobile/WordPress-Android/issues/9685
    # https://api.github.com/repos/tlaplus/tlaplus/issues/477

    ss = util.SS(port=7890)

    # repo = g.get_repo("tlaplus/tlaplus")
    # print(repo.get_topics())
    # print(get_topic("tlaplus/tlaplus"))
    #
    # print(is_android_repo(g, 'nextcloud/android'))
    # print(is_android_repo(g, 'arduino/Arduino'))
    import util

    issue_ob = util.get_issue(g, 'https://github.com/apache/dubbo/issues/6489')
    print(contain_fix(g, issue_ob))
    # a = 'org.springframework.beans.factory.BeanCreationException'
    # a = "a" * 50 + "....." + "ac" * 30
    # a = "-" * 77
    # print(cut_text(a, 54))
