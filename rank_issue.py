import hashlib
import json
from shutil import ReadError

import redis
from github import Github
from loguru import logger

import nlp_util
import search_rank
import util
from crawlermy import contain_fix, issue_based_compare
from keywords import download_code, extract, find_app_root, check_manifest_at_root, get_permission, Permissions, \
    search_keywords, check_gradle_at_root, gradle_dependency, Dependencies, find_all_gradle, find_all_pom, \
    pom_dependency
from xml_parser import get_ui_descript

r = redis.Redis(host='vm.userx.cn', port=6379, password='pullre', db=0, decode_responses=True)


def _pre_calc(**kwargs):
    """
    pre-process some values
    :param kwargs: must need key of {title_list, body_list, keys_sea
                                    label_list, reply_list}
    :return: pre_calc dict = {
        "hit_count_title": hit_count_title,
        "hit_count_body": hit_count_body,
        "hit_count_hot": hit_count_hot,
        "hit_count_label": hit_count_label,
        "body_len": body_len,
        "stat": {
            "max-reply": max(reply_list),
            "max-body_len": max(body_len),
        },
    }
    """
    title_list = kwargs["title_list"]
    body_list = kwargs["body_list"]
    keys_sea = kwargs["keys_sea"]
    label_list = kwargs["label_list"]
    reply_list = kwargs["reply_list"]
    hot_k = nlp_util.get_hot_keys()
    c_label = nlp_util.get_concern_label()

    ess_keys = set()
    for r in keys_sea:
        for a_list in r:
            ess_keys = ess_keys.union(a_list)
    ess_keys = " ".join(list(ess_keys))
    ess_keys = nlp_util.stem_sentence(ess_keys)
    ess_keys = set(ess_keys)

    body_len = [nlp_util.word_count(b) for b in body_list]
    title_list, body_list = map(nlp_util.stem_corpus, [title_list, body_list])
    label_list = nlp_util.split_label(label_list)
    label_list = nlp_util.stem_corpus(label_list)

    hit_count_title = search_rank.get_key_sea_count_corpus(ess_keys, title_list, unique=True)
    hit_count_body = search_rank.get_key_sea_count_corpus(ess_keys, body_list, unique=True)
    hit_count_hot = search_rank.get_key_sea_count_corpus(hot_k, body_list, unique=False)
    hit_count_label = search_rank.get_key_sea_count_corpus(c_label, label_list, unique=False)

    return {
        "hit_count_title": hit_count_title,
        "hit_count_body": hit_count_body,
        "hit_count_hot": hit_count_hot,
        "hit_count_label": hit_count_label,
        "body_len": body_len,
        "stat": {
            "max-reply": max(reply_list),
            "max-body_len": max(body_len),
        },
    }


def url_hash(url) -> str:
    if isinstance(url, str):
        url = url.encode("utf-8")
    md5 = hashlib.md5()
    md5.update(url)
    return md5.hexdigest()


def _build_issue_dict(g, issue_html_url) -> dict:
    issue_ob = util.get_issue(g, issue_html_url)
    issue_dict = dict()
    issue_dict['html_url'] = issue_ob.html_url
    issue_dict['title'] = issue_ob.title
    if issue_ob.body is None:
        issue_dict['body'] = ""
    else:
        issue_dict['body'] = issue_ob.body
    issue_dict['id'] = issue_ob.id
    issue_dict['number'] = issue_ob.number
    issue_dict['state'] = issue_ob.state
    issue_dict['comments'] = issue_ob.comments  # reply count

    issue_dict['body_len'] = nlp_util.word_count(issue_dict['body'])
    issue_dict['fix'] = contain_fix(g, issue_ob)

    iss_body_tokens = nlp_util.tokenize(issue_dict['body'])
    iss_body_tokens = nlp_util.remove_meanless(iss_body_tokens)
    issue_dict['body_tokens'] = iss_body_tokens

    title_tokens = nlp_util.nlp_process(issue_dict['title'])
    body_list_tokens = nlp_util.nlp_process(issue_dict['body'])

    hot_k = nlp_util.get_hot_keys()
    hit_count_hot_title = search_rank.get_key_sea_count(hot_k, title_tokens, unique=False)
    issue_dict['hit_count_hot_title'] = hit_count_hot_title
    hit_count_hot_body = search_rank.get_key_sea_count(hot_k, body_list_tokens, unique=False)
    issue_dict['hit_count_hot_body'] = hit_count_hot_body

    labels = []
    for _it in issue_ob.labels:
        name = _it.name if _it.name else ""
        description = _it.description if _it.description else ""
        labels.append((name.lower(), description.lower()))
    issue_dict['labels'] = labels

    con_label = nlp_util.get_concern_label()
    labels_c = []
    for _it in issue_dict['labels']:
        name, descrip = _it
        for _c in con_label:
            if _c in name or _c in descrip:
                labels_c.append(_it)
    issue_dict['labels_c'] = labels_c

    return issue_dict


def _issue_cache(g, issue_html_url) -> dict:
    md5 = url_hash(issue_html_url)
    issue_dict = r.get(md5)
    if issue_dict:
        # if cache exist
        issue_dict = json.loads(issue_dict)
        is_same = md5 == url_hash(issue_dict['html_url'])
        if is_same:
            return issue_dict
        else:
            # if cache exist， but not valid
            logger.error(f"Hash conflict: {md5} {issue_dict['html_url']}")
            issue_dict = _build_issue_dict(g, issue_html_url)

    else:
        # if cache do not exist
        issue_dict = _build_issue_dict(g, issue_html_url)

    r.set(md5, json.dumps(issue_dict))
    return issue_dict


def prepare_repo(g, issue_url):
    issue_dict = _issue_cache(g, issue_url)

    repo_name, iss_no = util.re_issue(issue_url)
    try:
        local_file_path = download_code(f'https://github.com/{repo_name}',
                                        f'./tmp/{repo_name.replace("/", "_")}.zip',
                                        skip_if_exist=True)
        ex_dir = extract(local_file_path, "./tmp")
    except ReadError:
        local_file_path = download_code(f'https://github.com/{repo_name}',
                                        f'./tmp/{repo_name.replace("/", "_")}.zip',
                                        skip_if_exist=False)
        ex_dir = extract(local_file_path, "./tmp")
    return ex_dir, repo_name, issue_dict


def java_plugin(g, issue_url):
    ex_dir, repo_name, issue_dict = prepare_repo(g, issue_url)
    # Dependency
    gradle_paths = find_all_gradle(ex_dir)
    if gradle_paths:
        raw_depens = []
        for p in gradle_paths:
            tmp = gradle_dependency(p)
            if tmp:
                raw_depens.extend(tmp)
    else:
        pom_paths = find_all_pom(ex_dir)
        raw_depens = []
        for p in pom_paths:
            tmp = pom_dependency(p)
            if tmp:
                raw_depens.extend(tmp)
    if raw_depens:
        # logger.debug(raw_depens)
        depen_ob = Dependencies(repo_name, raw_depens)
        # logger.debug(depen_ob)
        _denp_keys = depen_ob.keywords()
        # logger.debug(_denp_keys)
        denp_key_w = search_keywords(issue_dict["body_tokens"], _denp_keys, mode='depen', min_len=2)
        denp_key_w.sort(key=lambda k: k[-1], reverse=True)
        logger.info(f"Dependency {len(denp_key_w)}=={denp_key_w}")
        return {
            "depen": util.get_col(denp_key_w, 0)
        }
    else:
        return {
            "depen": list()
        }


def android_plugin(g, issue_url):
    ex_dir, repo_name, issue_dict = prepare_repo(g, issue_url)

    root = find_app_root(ex_dir)

    # Permission
    is_path, path = check_manifest_at_root(root)
    if not is_path:
        per_key_w = []
    else:
        name, p_list = get_permission(path)
        permit_ob = Permissions(path, name, ex_dir, p_list)
        _per_keys = permit_ob.keywords()
        per_key_w = search_keywords(issue_dict["body_tokens"], _per_keys, mode='permit', min_len=2)
        per_key_w.sort(key=lambda k: k[-1], reverse=True)
    logger.info(f"Permission {len(per_key_w)}=={per_key_w}")

    # Dependency
    is_path, path = check_gradle_at_root(root)
    if not is_path:
        denp_key_w = []
    else:
        a_json = gradle_dependency(path)
        depen_ob = Dependencies(repo_name, a_json)
        _denp_keys = depen_ob.keywords()
        denp_key_w = search_keywords(issue_dict["body_tokens"], _denp_keys, mode='depen', min_len=2)
        denp_key_w.sort(key=lambda k: k[-1], reverse=True)
    logger.info(f"Dependency {len(denp_key_w)}=={denp_key_w}")

    # UI
    ui_data = get_ui_descript(ex_dir)
    ui_key_w = search_keywords(issue_dict["body"], ui_data, mode='ui', threshold=0.5, min_len=3)
    # remove the match rate less than 0.5
    logger.info(f"UI {len(ui_key_w)}=={ui_key_w}")

    return {
        "depen": util.get_col(denp_key_w, 0),
        "permit": util.get_col(per_key_w, 0),
        "ui": util.get_col(ui_key_w, 0)
    }


def code_sim_wrap(g, open_issue_url, close_issue_url):
    # use jplag offline, due to moss upload limit
    open_iss_ob = util.get_issue(g, open_issue_url)
    close_iss_ob = util.get_issue(g, close_issue_url)
    code_sim = issue_based_compare(g, open_iss_ob, close_iss_ob, mode='jplag')
    logger.debug(f"Code-sim: {code_sim}")
    return code_sim


def dependency_rate(open_issue_url, close_issue_url):
    pass


def ui_rate(open_issue_url, close_issue_url):
    pass


def permission_rate(open_issue_url, close_issue_url):
    pass


def issue_quality(g, open_issue_url, close_issue_url):
    pass


def rank_issue(a_list: list):
    # open url, open info online, open info offline, close url, close info (rank property)
    # 0       , 1               , 2                , 3        , 4
    if not a_list:
        return []
    score_list = []
    for row in a_list:
        assert len(row) == 5
        score = 0
        info = row[4]
        if "Com-Off" in info:
            score += 2
        if "HAVE-FIX" in info:
            score += 1
        if "Code-SIM" in info:
            score += 2
        score_list.append(score)
        # TODO add issue_quality to score
    tmp = list(zip(a_list, score_list))
    tmp = sorted(tmp, key=lambda k: k[-1], reverse=True)
    a_list, score_list = zip(*tmp)
    return a_list


if __name__ == '__main__':
    from persontoken import MY_TOKEN

    g = Github(MY_TOKEN)
    url = 'https://github.com/json-path/JsonPath/issues/280'
    _issue_cache(g, issue_html_url=url)
    open_u = 'https://github.com/confluentinc/ksql/issues/5906'
    close_u = 'https://github.com/confluentinc/ksql/issues/5062'
    code_sim_wrap(g, open_u, close_u)
