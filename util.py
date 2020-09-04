import csv
import inspect
import json
import re
import socket
import sys
import time
from datetime import timezone, datetime
from os import makedirs, remove
from os.path import splitext, basename, exists

import pytz
import requests
import socks
from loguru import logger
from requests.adapters import HTTPAdapter
from github.Issue import Issue

from persontoken import MY_TOKEN

REQ_TIMEOUT = 6
REQ_SLEEP = 3
MAX_RETRY = 10
LOCAL_TZ = 'Asia/Shanghai'

# sleep time should be set properly. Please following the Github restriction.
# If not, you will see below message.
#
# {
#     "message": "API rate limit exceeded for xxx.xxx.xxx.xxx.
#                 (But here's the good news: Authenticated requests get a higher rate limit.
#                 Check out the documentation for more details.)",
#     "documentation_url": "https://developer.github.com/v3/#rate-limiting"
# }
SP_GITHUB_HEADER = {
    'User-Agent': 'Mozilla/5.0 ven(Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/69.0.3497.100 Safari/537.36',
    'Accept': 'application/vnd.github.v3.text+json'
}
# Accept header config see here https://developer.github.com/v3/media/

SIMPLE_HEADER = {
    'User-Agent': 'Mozilla/5.0 ven(Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/69.0.3497.100 Safari/537.36'
}


def init_logger(this_filename_prefix, mode='time', clear=True):
    if mode == 'time':
        makedirs("./log/", exist_ok=True)
        file_name = splitext(basename(this_filename_prefix))[0]
        logger.add("./log/" + file_name + "_{time}.log", encoding="utf8", newline='')
    elif mode == 'fixed':
        makedirs("./log/", exist_ok=True)
        log_path = "./log/" + f"{this_filename_prefix}"
        if clear and exists(log_path):
            remove(log_path)
        logger.add(log_path, encoding="utf8", newline='')
    logger.info("==================================== NEW RUN ====================================")


def humanbytes(B) -> str:
    """
    Return the given bytes as a human friendly KB, MB, GB, or TB string

    Args:
        B: Byte value

    Returns:
        str: human friendly string
    """
    B = float(B)
    KB = float(1024)
    MB = float(KB ** 2)  # 1,048,576
    GB = float(KB ** 3)  # 1,073,741,824
    TB = float(KB ** 4)  # 1,099,511,627,776

    if B < KB:
        return '{0} {1}'.format(B, 'Bytes' if 0 == B > 1 else 'Byte')
    elif KB <= B < MB:
        return '{0:.2f} KB'.format(B / KB)
    elif MB <= B < GB:
        return '{0:.3f} MB'.format(B / MB)
    elif GB <= B < TB:
        return '{0:.4f} GB'.format(B / GB)
    elif TB <= B:
        return '{0:.4f} TB'.format(B / TB)


def drop_file_ext(file_path):
    """
    get basename and drop file extension
    :param file_path: file path
    :return: file name without extension
    """
    return splitext(basename(file_path))[0]


def save_json(json_obj, json_path):
    with open(json_path, 'w', encoding='utf8') as f:
        print(json.dumps(json_obj, indent=4), file=f)


def load_json(json_path):
    out = []
    try:
        with open(json_path, 'r', encoding='utf8') as f:
            out = json.load(f)
    except FileNotFoundError as e:
        logger.error(f"NOT Found {json_path}")
    return out


def read_xsv(path, separator, encoding='utf-8', reserved_null=False):
    out = []
    try:
        with open(path, 'r', encoding=encoding) as _f:
            tsvreader = csv.reader(_f, delimiter=separator)
            for line in tsvreader:
                if reserved_null:
                    out.append(list(s.strip() for s in line))
                else:
                    out.append(list(s.strip() for s in line if s.strip() != ''))
        if separator == ',':
            logger.info(f"read {len(out)} rows xsv [,][{encoding}] -- {path}")
        elif separator == '\t':
            logger.info(f"read {len(out)} rows xsv [tab][{encoding}] -- {path}")
        else:
            logger.info(f"read {len(out)} rows xsv [{separator}][{encoding}] -- {path}")
    except FileNotFoundError as e:
        logger.error(f"NOT Found {path}")
    return out


def dump_xsv(path, data, separator, header=None, encoding='utf-8'):
    with open(path, 'w', encoding=encoding, newline='') as _f:
        tsvwriter = csv.writer(_f, delimiter=separator)
        if header is not None:
            tsvwriter.writerow(header)
        tsvwriter.writerows(data)
    if separator == ',':
        logger.info(f"dump {len(data)} rows xsv [,][{encoding}] -- {path}")
    elif separator == '\t':
        logger.info(f"dump {len(data)} rows xsv [tab][{encoding}] -- {path}")
    else:
        logger.info(f"dump {len(data)} rows xsv [{separator}][{encoding}] -- {path}")


def read_tsv(path, encoding='utf-8'):
    return read_xsv(path, "\t", encoding=encoding)


def dump_tsv(path, data, header=None, encoding='utf-8'):
    dump_xsv(path, data, "\t", header=header, encoding=encoding)


def read_csv(path, encoding='utf-8'):
    return read_xsv(path, ",", encoding=encoding)


def dump_csv(path, data, header=None, encoding='utf-8'):
    dump_xsv(path, data, ",", header=header, encoding=encoding)


def get_col(a_list, col):
    if type(col) == int:
        return [row[col] for row in a_list]
    elif type(col) == list:
        return [[row[c] for c in col] for row in a_list]


def uniq_list(a_list):
    tmp_set = set()
    result = []
    for it in a_list:
        if it not in tmp_set:
            tmp_set.add(it)
            result.append(it)
    return result


class SS:
    """
    For proxy
    """

    def __init__(self, ip="127.0.0.1", port=1080):
        self.orig_socket = socket.socket
        socks.set_default_proxy(socks.SOCKS5, ip, port)
        socket.socket = socks.socksocket
        logger.warning(f"Set socket proxy to {ip}:{port}")

    def restore(self):
        socket.socket = self.orig_socket
        logger.warning("Restore proxy")

    def __del__(self):
        self.restore()


class Reload:
    """
    For redirect standard output
    """

    def __init__(self, path=None, postfix=None):
        if path is None:
            caller = inspect.stack()[1].filename
            now_time = str(datetime.now().isoformat())
            now_time = now_time.replace(":", "")
            now_time = now_time.replace(".", "")
            if postfix is None:
                postfix = ""
            else:
                postfix += "_"
            path = drop_file_ext(caller) + "_" + postfix + now_time + ".log"
        print("-" * 20, "Reload to", path, "-" * 20, flush=True)
        self.orig_stdout = sys.stdout
        self.opened = True
        self.log_file = open(path, 'w', encoding='utf8')
        sys.stdout = self

    def write(self, message):
        self.orig_stdout.write(message)
        self.log_file.write(message)

    def flush(self):
        self.orig_stdout.flush()
        self.log_file.flush()

    def close(self):
        if self.opened:
            print("-" * 20, "End of Reload", "-" * 20, flush=True)
            sys.stdout = self.orig_stdout
            self.log_file.close()
            self.opened = False
            print("End reload", flush=True)
        else:
            print("Already closed", flush=True)

    def __del__(self):
        self.close()
        print("Close by __del__", flush=True)


def get_gh_header(token=MY_TOKEN):
    SP_GITHUB_HEADER['Authorization'] = f'token {token}'
    return SP_GITHUB_HEADER


def _check_rate(this_head):
    try:
        ts = int(this_head['X-RateLimit-Reset'])
        utc_tc = datetime.utcfromtimestamp(ts).replace(tzinfo=timezone.utc)
        now = datetime.now(pytz.timezone(LOCAL_TZ))
        tm_diff = (utc_tc.astimezone(pytz.timezone(LOCAL_TZ)) - now).seconds
        logger.info(
            "Rate should lower than %.2f req per seconds." % (int(this_head['X-RateLimit-Remaining']) / tm_diff))
        logger.info(
            f"RateLimit-Limit {this_head['X-RateLimit-Remaining']}/"
            f"{this_head['X-RateLimit-Limit']}. Reset at TZ@{LOCAL_TZ} " +
            utc_tc.astimezone(pytz.timezone(LOCAL_TZ)).strftime('%Y-%m-%d %H:%M:%S') + ".")
    except Exception as e:
        logger.error(e)
        logger.error(this_head)


def get_github_content(url, sleep_time=REQ_SLEEP, retry_num=MAX_RETRY, check_rate=False, custom_header=get_gh_header(),
                       mode='json'):
    logger.info(f"Start parsing: {url}")
    time.sleep(sleep_time)

    s = requests.Session()
    s.mount('http://', HTTPAdapter(max_retries=retry_num))
    s.mount('https://', HTTPAdapter(max_retries=retry_num))
    res = s.get(url, headers=custom_header, timeout=REQ_TIMEOUT)
    response = res.text
    if res.status_code != 200:
        logger.error(res.content.decode(res.apparent_encoding))
    if check_rate or res.status_code != 200:
        _check_rate(res.headers)
    s.close()
    if mode == 'json':
        return json.loads(response)
    else:
        return response


def parse_json(url, debug=False, sleep_time=REQ_SLEEP, retry_num=MAX_RETRY):
    logger.info(f"Start parsing: {url}")

    if "github.com" in url:
        json_data = get_github_content(url, sleep_time, retry_num, check_rate=True)

    else:
        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=retry_num))
        s.mount('https://', HTTPAdapter(max_retries=retry_num))
        res = s.get(url, headers=SIMPLE_HEADER, timeout=REQ_TIMEOUT)
        json_str = res.text
        s.close()
        json_data = json.loads(json_str)

    if debug:
        logger.debug(json.dumps(json_data, indent=4))
        _reload = Reload("debug.txt")
        logger.debug(json.dumps(json_data, ensure_ascii=False, indent=4))
        _reload.close()
    logger.info("Finish parse URL.")
    return json_data


def std_table_name(repo_url, separation):
    tmp = separation.join(repo_url.split("/")[-2:]).replace("-", "_")
    result = ''.join([i for i in tmp if not i.isdigit()])
    return result


def re_issue(iss_url):
    pat = r'https:\/\/github\.com\/(.*?\/[^\/]*)\/(?:issues|pull)\/(\d+)'
    repo_name, iss_no = re.findall(pat, iss_url)[0]
    return repo_name, int(iss_no)


def get_issue(g, iss_url) -> Issue:
    pat = r'https:\/\/github\.com\/(.*?\/[^\/]*)\/(?:issues|pull)\/(\d+)'
    repo_name, iss_no = re.findall(pat, iss_url)[0]
    repo = g.get_repo(repo_name)
    iss_ob = repo.get_issue(int(iss_no))
    return iss_ob
