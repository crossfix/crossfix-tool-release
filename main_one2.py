import csv
import json
import traceback
from copy import deepcopy

from github import Github
from loguru import logger

import nlp_util
import util
from crawlermy import fast_query, run_close_query, form_query, add_pos
from rank_issue import code_sim_wrap, rank_issue, android_plugin, java_plugin
from util import SS

#  before running, delete data2.csv，hist.txt，log/main_one2.log

util.init_logger('main_one2.log', mode='fixed', clear=False)
is_android = False
open_urls = util.read_csv('./openlist.txt', encoding='utf-8')
open_urls = util.get_col(open_urls, 0)
open_urls = util.uniq_list(open_urls)
ss = SS(ip="vm.userx.cn", port=7891)


def mian():
    from persontoken import MY_TOKEN
    g = Github(MY_TOKEN)
    done_open_urls = util.read_csv('./hist.txt')
    done_open_urls = util.get_col(done_open_urls, 0)

    _f = open("data2.csv", 'a+', encoding='utf-8-sig', newline='')
    _f2 = open("hist.txt", 'a+', encoding='utf-8', newline='')

    try:
        csvwriter = csv.writer(_f, delimiter=',')
        for i, open_url in enumerate(open_urls):
            if open_url in done_open_urls:
                continue
            this_row = [""] * 5
            # open_url = 'https://github.com/json-path/JsonPath/issues/460'
            logger.info("-" * 100)
            logger.info(open_url)
            open_iss_ob = util.get_issue(g, open_url)
            this_row[0] = open_url

            # stacktrace / condition / title
            repo_name = open_iss_ob.repository.full_name
            extra_rm = nlp_util.full_name_token(repo_name)  # remove the number and its name
            curr_q = fast_query(open_iss_ob.title, open_iss_ob.body)
            logger.info(f"curr_q, {curr_q}")

            # check sequence stacktrace, condition, title
            try_pair = [
                (True, False, 'body'),  # stacktrace in body
                (False, True, 'title'),  # condition in title
                (False, False, 'title'),  # title in title
                (False, False, 'other')  # title (no field constraint)
            ]
            try_hist = []
            all_fail = True
            for _fi, pair in enumerate(try_pair):
                trace, condition, pos = pair
                query_list = form_query(curr_q, extra_rm, trace=trace, condition=condition)
                query_chars = " ".join(query_list)
                query_chars = add_pos(query_chars, pos)
                logger.debug(f"query_chars, {query_chars}")
                if query_list:
                    close_iss = run_close_query(g, query_chars, is_android, depth=10, fallback_size=5)
                    try_hist.append(query_chars)
                    this_row[1] = query_chars
                    if close_iss["info"] == 'NORMAL':
                        all_fail = False
                    else:
                        if close_iss["info"] == 'FALLBACK':
                            all_fail = False
                            logger.info(f"[try {_fi}] FALLBACK failed query [Too few results], {query_chars}")
                        elif close_iss["info"] == 'EMPTY':
                            logger.info(f"[try {_fi}] FALLBACK failed query [Zero results], {query_chars}")

                    if close_iss["iss"]:
                        # open url, open info online, open info offline, close url, close info (rank property)
                        # 0       , 1               , 2                , 3        , 4

                        rank_list = []
                        for _c in close_iss["iss"]:
                            close_url, close_info = _c
                            if is_android:
                                plugin = android_plugin
                            else:
                                plugin = java_plugin
                            # open url, open info online, open info offline, close url, close info (rank property)
                            # 0       , 1               , 2                , 3        , 4
                            open_off = plugin(g, open_url)
                            close_off = plugin(g, close_url)
                            logger.debug(f"open {open_url}")
                            logger.debug(f"open offline rank, {open_off}=={len(open_off.keys())}")
                            logger.debug(f"close {close_url}")
                            logger.debug(f"close offline rank, {close_off}=={len(close_off.keys())}")
                            assert len(open_off.keys()) == len(close_off.keys())
                            all_empty = True
                            join_off = dict()
                            for _k in open_off.keys():
                                join = set(open_off[_k]) & set(close_off[_k])
                                join_off[_k] = list(join)
                                if join:
                                    all_empty = False
                                    close_info.insert(0, f"Off-SIM-{_k}")
                            logger.debug(f"join_off, {join_off}")
                            if all_empty:
                                this_row[2] = "empty offline"
                            else:
                                this_row[2] = json.dumps(join_off)

                            this_row[3] = close_url
                            flag = code_sim_wrap(g, open_url, close_url)
                            if flag:
                                close_info.insert(0, "Code-SIM")
                            this_row[4] = json.dumps(close_info)
                            rank_list.append(deepcopy(this_row))
                        rank_list = rank_issue(rank_list)
                        if rank_list:
                            csvwriter.writerows(rank_list)

                        if close_iss["info"] == 'NORMAL':
                            break

            if all_fail:
                write_list = []
                this_row[4] = 'NONE close issue'
                for col1 in try_hist:
                    this_row[1] = col1
                    write_list.append(deepcopy(this_row))
                csvwriter.writerows(write_list)

            print(open_url, file=_f2)

            _f.flush()
            _f2.flush()
    except Exception as e:
        logger.error(f"{open_url}, skip")
        print(f"{open_url}, skip", file=_f2)
        raise e
    finally:
        _f.close()
        _f2.close()


_flag = True
while _flag:
    try:
        mian()
        exit(0)
    # except OSError or ProtocolError or requests.exceptions.ConnectionError:
    #     logger.info("retry")
    except Exception:
        # _flag = False
        logger.error("PYERR")
        logger.error(traceback.format_exc())
