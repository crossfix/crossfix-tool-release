import json
import ntpath
import os
import posixpath
import re
import subprocess
from collections import namedtuple
from shutil import unpack_archive
from typing import Tuple, Union

import Levenshtein
import requests
from loguru import logger
from lxml import etree

import nlp_util
import util
from xml_parser import ui_tokenize
from java_invoke import pom2json


# util.init_logger(__file__)


# gradle-to-js has bug when parsing plugin. !!! NOTE THAT !!!.
# https://github.com/ninetwozero/gradle-to-js/issues/29
# need already installed Node.js
def install_module():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    logger.info(f"npm install at {base_dir}")
    ex = subprocess.Popen("npm install",
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, cwd=base_dir)
    output, err = ex.communicate()
    status = ex.wait()
    logger.info(f"npm finished with status {status}\n{output.decode()}")


def gradle2json(gradle_path):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cli_path = os.path.join(base_dir, 'node_modules', 'gradle-to-js', 'cli.js')
    if not os.path.exists(cli_path):
        try:
            install_module()
        except Exception as e:
            raise e
    cmd = f"node {cli_path} {gradle_path}"
    logger.info(cmd)

    ex = subprocess.Popen(cmd,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, cwd=base_dir)
    output, err = ex.communicate()
    ex.wait()
    return json.loads(output, encoding='utf-8')


def find_all_pom(walk_dir):
    """
        find pom.xml "file in walk_dir recursively
    """
    logger.info(f"Find pom.xml at {walk_dir}")
    candidate_list = list()
    for r, d, files in os.walk(walk_dir):
        for f in files:
            if f.startswith("pom.xml"):
                # 'pom.xml'
                candidate_list.append(os.path.join(os.path.abspath(r), f))
    return candidate_list


def find_all_gradle(walk_dir):
    """
        find build.gradle(.kts) "file in walk_dir recursively
    """
    logger.info(f"Find build.gradle(.kts) at {walk_dir}")
    candidate_list = list()
    for r, d, files in os.walk(walk_dir):
        for f in files:
            if f.startswith("build.gradle"):
                # 'build.gradle' or 'build.gradle.kts'
                candidate_list.append(os.path.join(os.path.abspath(r), f))
    return candidate_list


def find_app_root(walk_dir):
    """
        find root of app by search gradle "com.android.application"
    """
    logger.info(f"Find app module at {walk_dir}")

    app_gradle_path = str()
    candidate_list = find_all_gradle(walk_dir)
    for c in candidate_list:
        if valid_gradle_regex(c):
            app_gradle_path = c
            break
    _rt_gradle_path = app_gradle_path if app_gradle_path != "" else "NOTHING"
    if app_gradle_path != "":
        logger.info(f"Found app module gradle at {_rt_gradle_path}")
    else:
        logger.error(f"NOT Found app module gradle at {walk_dir}")
    return os.path.dirname(app_gradle_path)


def valid_gradle_regex(path):
    """
    https://developer.android.com/studio/build#module-level
    valid it is a application gradle
    Args:
        path: gradle path

    Returns: True if it is a application gradle

    """
    plugin_pattern_multi = r"""id(?:[ \t]?)\((["']?)([A-Za-z0-9.]+)\1\)"""
    plugin_pattern_single = r"""(?:plugin)(?:\s*:\s*)(['"]?)(com\.android\.application)\1"""
    if not os.path.isfile(path):
        return False
    with open(path, encoding='utf-8') as _f:
        all_the_text = _f.read()
    flag = False
    result = re.findall(plugin_pattern_multi, all_the_text)
    for i in range(len(result)):
        if result[i][1] == "com.android.application":
            flag = True
            break
    if not flag:
        result = re.findall(plugin_pattern_single, all_the_text)
        for i in range(len(result)):
            if result[i][1] == "com.android.application":
                flag = True
                break
    if flag:
        logger.info(f"Valid gradle of [{path}]")
    else:
        logger.error(f"Invalid gradle of [{path}]")
    return flag


def check_gradle_at_root(root_path) -> Tuple[bool, Union[bytes, str]]:
    """
    Args:
        root_path: app project path

    Returns: True if exist: [True, the_path] or [False, ""]
    """
    gradle_path = os.path.join(root_path, "build.gradle")
    gradle_kt_path = os.path.join(root_path, "build.gradle.kts")
    if os.path.isfile(gradle_path):
        return valid_gradle_regex(gradle_path), gradle_path
    elif os.path.isfile(gradle_kt_path):
        return valid_gradle_regex(gradle_kt_path), gradle_kt_path
    else:
        return False, ""


def check_manifest_at_root(root_path) -> Tuple[bool, Union[bytes, str]]:
    """
    https://developer.android.com/guide/topics/manifest/manifest-intro#top_of_page
    "Every app project must have an AndroidManifest.xml file (with precisely that name)
    at the root of the project source set."

    Args:
        root_path: app project path

    Returns: True if exist
    """
    manifest_pattern = r"src\main\AndroidManifest.xml".split("\\")
    manifest_path = os.path.join(root_path, *manifest_pattern)
    return os.path.isfile(manifest_path), manifest_path


def get_permission(manifest_path):
    tree = etree.parse(manifest_path)
    root = tree.getroot()
    namespace = root.nsmap
    key = f'{{{namespace["android"]}}}name'

    child = root.findall("./uses-permission[@android:name]", namespace)
    attrib_list = list()
    for c in child:
        attrib_list.append(c.attrib[key])

    logger.info(f"Found {len(attrib_list)} permission(s) at {root.attrib['package']} of [{manifest_path}]")
    return root.attrib['package'], attrib_list


class GetKeyValue:
    """
    get value from nested dict
    """

    def __init__(self, o, mode='j'):
        self.json_object = None
        if mode == 'j':
            # json object
            self.json_object = o
        elif mode == 's':
            # string
            self.json_object = json.loads(o)
        else:
            raise Exception('Unexpected mode argument.Choose "j" or "s".')

        self.result_list = []

    def search_key(self, key):
        self.result_list = []
        self.__search(self.json_object, key)
        return self.result_list

    def __search(self, json_object, key):
        """
        BFS to get key
        """
        tmp = []
        tmp.append(self.json_object)
        while len(tmp) > 0:
            top = tmp.pop(0)
            if key in top.keys():
                self.result_list.append(top[key])
                return
            else:
                for k in top:
                    if isinstance(top[k], dict):
                        tmp.append(top[k])
                    if isinstance(top[k], list):
                        for item in top[k]:
                            if isinstance(item, dict):
                                tmp.append(item)
        return


def pom_dependency(pom_path):
    """
    get dependency list from pom.xml
    Args:
        pom_path: pom path
    Returns: dependency list
    [{
    'groupId': str,
    'artifactId': str,
    'version': str
    }]
    """
    json_path = f'./tmp/_pom_format.json'
    data = pom2json(pom_path, json_path, clean=True)
    if data and "data" in data:
        assert len(data["data"]) == data["len"]
        return data["data"]
    else:
        return list()


def gradle_dependency(gradle_path, mode=2) -> list:
    """
    get dependency list from build.gradle(.kts)
    [{
    'type': 'implementation', 'api', 'compile'
    'group': str,
    'name': str,
    'version': str
    }]
    Args:
        gradle_path: grade path
        mode: mode==1 use js package (!!!DEPRECATION!!!), mode==2 use pure regex
    Returns: list[dict]
    """
    if mode == 1:
        # DEPRECATION
        a_json = gradle2json(gradle_path)
        tmp = GetKeyValue(a_json)
        dependencies = tmp.search_key('dependencies')
        assert len(dependencies) == 1
        dependencies = dependencies[0]
        return dependencies
    elif mode == 2:
        # default to use
        gradle_text = []
        with open(gradle_path, 'r', encoding='utf8') as f:
            context = f.readlines()
            for r in context:
                gradle_text.append(r.strip())
        # find the start line of dependencies and level is lowest
        level = 0
        candi_start = []
        for i in range(len(gradle_text)):
            tmp = re.findall(r'''dependencies\s*{''', gradle_text[i])
            if tmp:
                candi_start.append((level, i, tmp))
            for j in range(len(gradle_text[i])):
                if gradle_text[i][j] == '{':
                    level += 1
                elif gradle_text[i][j] == '}':
                    level -= 1
        candi_start.sort(key=lambda k: k[0])
        if len(candi_start) == 0:
            return []
        token_start = candi_start[0][1]
        # find the end line of dependencies, use stack
        brackets = ['{']
        i = token_start + 1
        while len(brackets) > 0:
            assert i < len(gradle_text)
            for j in range(len(gradle_text[i])):
                if gradle_text[i][j] == '{':
                    brackets.append('{')
                elif gradle_text[i][j] == '}':
                    brackets.pop()
            i += 1
        token_end = i
        dependencies = []
        # print(token_start, token_end)
        # https://developer.android.com/studio/build/dependencies
        # https://docs.gradle.org/current/userguide/declaring_dependencies.html
        # adjust flexible dependencies item expression
        pat = [
            r'''(implementation|api|compile)\s*(\(?)\s*(['"])(.*):(.*):(.*)\3''',
            # implementation 'com.example.android:app-magic:12.3'
            # implementation('com.example.android:app-magic:12.3')

            r'''(implementation|api|compile)[\s(]*(?:group:|group\s*=)\s*(['"])(.*?)\2\s*,\s*(?:name:|name\s*=)\s*(['"])(.*?)\4\s*,\s*(?:version:|version\s*=)\s*(['"])(.*?)\6[\s)]*'''
            # implementation group: 'com.example.android', name: 'app-magic', version: '12.3'
            # implementation(group = "org.springframework", name = "spring-core", version = "2.5")

        ]
        # logger.debug(gradle_path)
        for i in range(token_start, token_end):
            # logger.debug(gradle_text[i])
            tmp = re.findall(pat[0], gradle_text[i])
            if tmp:
                assert len(tmp) < 2
                dependencies.append(
                    {
                        'type': tmp[0][0],
                        'group': tmp[0][3],
                        'name': tmp[0][4],
                        'version': tmp[0][5]
                    }
                )
                continue
            tmp = re.findall(pat[1], gradle_text[i])
            if tmp:
                assert len(tmp) < 2
                dependencies.append(
                    {
                        'type': tmp[0][0],
                        'group': tmp[0][2],
                        'name': tmp[0][4],
                        'version': tmp[0][6]
                    }
                )
                continue
        return dependencies


class Permissions:
    def __init__(self, xml_path, package_name, project_root, permissions):
        self.path = xml_path
        self.package_name = package_name
        self.project_root = project_root
        self.permissions = set()  # set of the strings of permissions name
        self._add(permissions)

    def simple_root(self, mode='nt'):
        if mode == 'nt':
            return ntpath.basename(self.project_root)
        elif mode == 'posix':
            return posixpath.basename(self.project_root)
        else:
            return os.path.basename(self.project_root)

    def __len__(self):
        return len(self.permissions)

    def compare(self, other_set):
        if type(other_set) != Permissions:
            raise Exception(f"Should be Class Permissions rather than {type(other_set)}")
        rt = {
            "same": self.permissions & other_set.permissions,
            "diff": self.permissions ^ other_set.permissions,
            "a-b": self.permissions - other_set.permissions,
            "b-a": other_set.permissions - self.permissions,
        }
        return rt

    def __repr__(self):
        str1 = f"Package {self.package_name}"
        str2 = "\n".join(sorted(list(self.permissions)))
        return f"{str1}\n{str2}\n"

    def _add(self, permissions):
        for p in permissions:
            self.permissions.add(p.lower())

    @staticmethod
    def valid_permissions(permission):
        # TODO check the permission is a android defined permission, not a custom
        pass

    @staticmethod
    def _short_permit(permit_str):
        assert len(permit_str) > 0
        return permit_str.lower().split(".")[-1]

    def keywords(self):
        rt = set()
        for p in self.permissions:
            rt.add(self._short_permit(p))
        return rt


def safe_get_ket(a_dict, key, default_return=None):
    if a_dict:
        if key in a_dict:
            if a_dict[key] != "":
                return a_dict[key]
            else:
                return default_return
    return default_return


class Dependencies:
    def __init__(self, name, dependencies):
        self.name = name
        self.dependencies = []  # DependItem list
        self._build(dependencies)
        self.dependencies.sort()

    def __len__(self):
        return len(self.dependencies)

    def _build(self, dependencies):
        _uniq_depen = set()
        for d in dependencies:
            if 'type' in d.keys():
                if d['type'] == 'implementation' or d['type'] == 'api' or d['type'] == 'compile':
                    # gradle
                    try:
                        d_group = safe_get_ket(d, 'group', default_return="null")
                        d_name = safe_get_ket(d, 'name', default_return="null")
                        d_version = safe_get_ket(d, 'version', default_return="null")
                        _uniq_depen.add(DependItem(d_group, d_name, d_version))
                    except Exception:
                        logger.error(f"Parsing DependItem failed: {d}")
            else:
                # maven
                try:
                    d_group = safe_get_ket(d, 'groupId', default_return="null")
                    d_name = safe_get_ket(d, 'artifactId', default_return="null")
                    d_version = safe_get_ket(d, 'version', default_return="null")
                    _uniq_depen.add(DependItem(d_group, d_name, d_version))
                except Exception:
                    logger.error(f"Parsing DependItem failed: {d}")
        self.dependencies = list(_uniq_depen)

    def __repr__(self):
        str1 = f"Package {self.name}"
        str2 = "\n".join(x.__repr__() for x in self.dependencies)
        return f"{str1}\n{str2}\n"

    def simple_dependencies(self):
        rt = set()
        for d in self.dependencies:
            rt.add(d.pure_name())
        return rt

    def keywords(self):
        # TODO may be add some nlp
        return self.simple_dependencies()


class DependItem:

    def __init__(self, group, name, version):
        self._pat = r"""(['"]?)(.*):(.*):(.*)\1"""

        if group == '' and version == '':
            result = re.findall(self._pat, name)
            try:
                self.group = result[0][1].lower()
                self.name = result[0][2].lower()
                self.version = result[0][3].lower()
            except IndexError as e:
                logger.debug(f"Wrong format Depend ={group}-{name}-{version}=.")
                raise Exception("Wrong format Depend")
        else:
            self.group = group.lower()
            self.name = name.lower()
            self.version = version.lower()
        self._valid_field()

    def _valid_field(self):
        if self.group == '' or self.name == '' or self.version == '':
            raise Exception(f"Empty field ={self.group}-{self.name}-{self.version}=")

    def __hash__(self):
        return hash(self.group) ^ hash(self.name) ^ hash(self.version)

    def __eq__(self, other):
        return self.group == other.group and self.name == other.name and self.version == other.version

    def group_name_no_ver(self):
        return f"{self.group}:{self.name}"

    def pure_name(self):
        return f"{self.name}"

    def dict_repr(self):
        return {
            "group": self.group,
            "name": self.name,
            "version": self.version
        }

    def __repr__(self):
        return f"{self.group}:{self.name}:{self.version}"

    def __lt__(self, other):
        if self.group < other.group:
            return True
        else:
            if self.group == other.group and self.name < other.name:
                return True
            else:
                if self.group == other.group and self.name == other.name and self.version < other.version:
                    return True
                else:
                    return False

    def compare(self, other):
        weight = [74, 21, 5]
        group_w, name_w, ver_w = [weight[i] / sum(weight) for i in range(len(weight))]
        rt = 0
        if self.group == other.group:
            rt += group_w
        if self.name == other.name:
            rt += name_w
        if self.version == other.version:
            rt += ver_w
        return rt

    def fast_eq(self, other):
        return self.group == other.group and self.name == other.name


def _download(file_url, local_file_name, skip_if_exist=False):
    local_file_path = os.path.join(".", local_file_name)
    if skip_if_exist and os.path.exists(local_file_path):
        logger.info("Skip download, due to exist.")
        return local_file_path
    os.makedirs(os.path.dirname(local_file_path), exist_ok=True)

    # Using Linux command wget
    # -----------
    if False:
        cmd_call = 'wget {} -O {}'.format(file_url, local_file_path)
        logger.info(cmd_call)
        subprocess.call(cmd_call, shell=True)
    # +++++++++++

    # Using Windows PowerShell wget
    # -----------
    if False:
        wget_call = 'wget {} -O {}'.format(file_url, local_file_path)
        cmd_call = ["powershell.exe", "-ExecutionPolicy", "Unrestricted"]
        cmd_call.extend(wget_call.split())
        logger.info(" ".join(cmd_call))
        ex = subprocess.Popen(cmd_call, stdout=subprocess.PIPE, shell=True)
        status = ex.wait()
        logger.info(f"Download {local_file_name}, finished with the state {status}")
    # +++++++++++

    # Using python build-in method
    # -----------
    if True:
        r = requests.get(file_url, stream=True)
        try:
            logger.info("Estimated file size: {}".format(util.humanbytes(r.headers['Content-Length'])))
        except Exception as e:
            pass
        logger.info(f"Start download {local_file_name} from {file_url}")
        file_len = 0
        with open(local_file_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=2048):
                if chunk:
                    f.write(chunk)
                    file_len += len(chunk)
                print("\rFile size: {}".format(util.humanbytes(file_len)) + " " * 20, end='', flush=True)
            print("\r", end='', flush=True)
        logger.info("File size: {}".format(util.humanbytes(file_len)) + " " * 20)
        logger.info("Finished download")
    # +++++++++++
    return local_file_path


def download_code_file(repo_fullname, sha, path, local_file_name, skip_if_exist=False):
    file_url = f'https://github.com/{repo_fullname}/raw/{sha}/{path}'
    local_file_path = _download(file_url, local_file_name, skip_if_exist=skip_if_exist)
    return local_file_path


def download_code(repo_url: str, local_file_name, sha=None, skip_if_exist=False):
    def get_api(repo_url):
        tmp = 'https://api.github.com/repos/{}'
        return tmp.format("/".join(repo_url.split("/")[-2:]))

    def get_download_url(repo_url, sha=None, branch=None):
        repo_fullname = "/".join(repo_url.split("/")[-2:])
        if sha:
            return f'https://github.com/{repo_fullname}/archive/{sha}.zip'
        else:
            if branch is None:
                branch = util.parse_json(get_api(repo_url))['default_branch']
            return f'https://github.com/{repo_fullname}/archive/{branch}.zip'

    file_url = get_download_url(repo_url, sha=sha)

    local_file_path = _download(file_url, local_file_name, skip_if_exist=skip_if_exist)
    return local_file_path


def extract(compressed_file: str, path_to_extract: str):
    logger.info(f"extract [{compressed_file}] to [{path_to_extract}]")
    base_name = os.path.splitext(os.path.basename(compressed_file))[0]
    ex_dir = os.path.join(path_to_extract, base_name)
    os.makedirs(ex_dir, exist_ok=True)
    unpack_archive(compressed_file, ex_dir)
    return os.path.abspath(ex_dir)


def match_word():
    pass


def similarity(token, key, mode='levenshtein2'):
    # The larger the similar value, the better
    if mode == 'simple':
        if key in token or token in key:
            rt = 1
        else:
            rt = 0
    elif mode == 'levenshtein2':
        rt = Levenshtein.ratio(token, key)
    elif mode == 'Levenshtein1':
        size_diff = max(len(token), len(key)) - min(len(token), len(key))
        rt = 1 - (Levenshtein.distance(token, key) - size_diff) / min(len(token), len(key))
    elif mode == 'cut':
        splited_token = re.split(r'[-_\s]+', token)
        splited_token = [i for i in splited_token if i]
        uni_tokens = " ".join(splited_token)
        rt = Levenshtein.ratio(uni_tokens, key)

    # elif mode == 'jaro':
    #     rt = Levenshtein.jaro_winkler(token, key)
    # not good

    # logger.debug(f"{rt}, {token}, {key}")
    return rt


def compress_dict(a_dict):
    # remove the key with zero value, and sum of value
    com = {x: y for x, y in a_dict.items() if y != 0}
    count = 0
    for x, y in a_dict.items():
        if x != '__corpus_len__':
            count += y
    com['__corpus_len__'] = count
    return com


def remove_null(a_list, index):
    # get non-zero column from a list
    out = []
    for row in a_list:
        if row[index] != 0:
            out.append(row)
    return out


def boost_ui_check(nlped_body, keywords):
    key_sea = set()
    for keys_3 in keywords:
        file_name, object_class_name, object_id = keys_3
        key_sea = key_sea.union(set(file_name))
        key_sea.add(object_class_name)
        key_sea = key_sea.union(set(object_id))

    # key_sea = set(nlp_util.stemming(key_sea))
    count = dict.fromkeys(key_sea, 0)
    for b in nlped_body:
        if b in count:
            count[b] += 1
    return compress_dict(count)


def weighted_ui_match(count_dict, keywords, weight):
    score_list = []
    w1, w2, w3 = weight
    for i in range(len(keywords)):
        score = 0
        file_name, object_class_name, object_id = keywords[i]
        # 1. file_name
        for w in file_name:
            if w in count_dict:
                score += w1 * (count_dict[w] / count_dict['__corpus_len__'])
        # 2. object_class_name
        if object_class_name in count_dict:
            score += w2 * (count_dict[object_class_name] / count_dict['__corpus_len__'])
        # 3. object_id
        for w in object_id:
            if w in count_dict:
                score += w3 * (count_dict[w] / count_dict['__corpus_len__'])
        score_list.append(score)
    return score_list


def search_keywords(body: list or str, keywords, mode, tol=0.5, **aux):
    # closed body
    #   1. mode == 'depen' or 'permit' , body is processed
    #   2. mode == 'ui' body is raw
    # body = [word1, word2, word3, ...]
    # token may be a compound word, consider whether to divide it further
    # Consider whether to stemming

    if mode == 'depen' or mode == 'permit':
        candidate = list()
        Key = namedtuple('Key', ['body', 'focus', 'sim'])
        for token in body:
            like_keys = []
            for key in keywords:
                like_keys.append((token, key, similarity(token, key, mode='simple')))
            like_keys.sort(key=lambda k: k[-1], reverse=True)  # sort similarity from large to small
            # every token get the most similar keywords
            if like_keys and like_keys[0] and like_keys[0][-1] > tol:
                _tmp = Key._make(like_keys[0])
                logger.debug(_tmp)
                candidate.append(_tmp)
        if 'min_len' in aux:
            candidate = list(filter(lambda x: len(x[0]) > aux['min_len'], candidate))
            candidate = list(filter(lambda x: len(x[1]) > aux['min_len'], candidate))
        return candidate
    if mode == 'ui':
        stem_ui_data = ui_tokenize(keywords, stem=True)
        nlped_body = nlp_util.nlp_process(body)
        # logger.debug(nlped_body)

        # Query the number of occurrences of stemmed UI in the body
        lookup_dict = boost_ui_check(nlped_body, stem_ui_data)
        logger.debug(f"UI lookup_dict: {lookup_dict}")
        weight = [0.1, 0.5, 0.4]

        # Give a high score to the UI with many appearances and sort it
        #Giving points algorithm may need improvement! ! ! !
        score_list = weighted_ui_match(lookup_dict, stem_ui_data, weight)
        candidate = sorted(zip(keywords, score_list), reverse=True, key=lambda x: x[1])
        candidate = remove_null(candidate, index=1)

        # option parms threshold，min_len
        if 'threshold' in aux:
            candidate = list(filter(lambda x: int(x[-1]) > aux['threshold'], candidate))
        if 'min_len' in aux:
            candidate = list(filter(lambda x: len(x[0]) > aux['min_len'], candidate))
            candidate = list(filter(lambda x: len(x[1]) > aux['min_len'], candidate))
        return candidate


if __name__ == '__main__':
    # # a open issue
    # issue_link = 'https://github.com/nextcloud/android/issues/5709'

    # # download and extract code
    # local_file_path = download_code('https://github.com/nextcloud/android', 'nextcloud.zip')
    # ex_dir = extract(local_file_path, "./tmp")

    # assuming this is a android project, check Gradle and android manifest
    ex_dir = "D:\\A-work\\pullrecommend\\tmp\\nextcloud"
    p = ex_dir
    root = find_app_root(p)
    is_path, path = check_manifest_at_root(root)
    if is_path:
        name, p_list = get_permission(path)
        permit_ob = Permissions(path, name, p, p_list)
        # logger.debug(permit_ob)
        logger.debug(name)
        logger.debug(f"Permissions: {len(permit_ob)}")
        logger.debug(sorted(permit_ob.permissions))
    else:
        exit(1)
    logger.debug("-" * 50)

    is_path, path = check_gradle_at_root(root)
    if is_path:
        a_json = gradle_dependency(path)
        depen_ob = Dependencies(name, a_json)
        # logger.debug(depen_ob)
        logger.debug(f"Dependencies: {len(depen_ob)}")
        logger.debug(depen_ob.dependencies)
    else:
        exit(2)
    logger.debug("=" * 50)

    # get keywords
    logger.debug(permit_ob.keywords())
    logger.debug(depen_ob.keywords())

    # # example
    # # issue_link = 'https://github.com/nextcloud/android/issues/5709'
    # from persontoken import MY_TOKEN
    # g = Github(MY_TOKEN)
    # repo = g.get_repo("nextcloud/android")
    # iss_ob = repo.get_issue(number=5709)

    # test
    # with open("tmp5709.data", 'w', encoding='utf8') as f:
    #     print(iss_ob.body, file=f)
    # tmp_corpus = iss_ob.body

    with open("tmp5709.data", 'r', encoding='utf8') as f:
        tmp_corpus = f.read()
    tmp_corpus = nlp_util.tokenize(tmp_corpus)
    tmp_corpus = nlp_util.remove_meanless(tmp_corpus)

    _per_keys = permit_ob.keywords()
    out = search_keywords(tmp_corpus, _per_keys)
    out.sort(key=lambda k: k[-1], reverse=True)
    logger.debug(f"{len(out)}======={out}")

    _denp_keys = depen_ob.keywords()
    out = search_keywords(tmp_corpus, _denp_keys)
    out.sort(key=lambda k: k[-1], reverse=True)
    logger.debug(f"{len(out)}======={out}")
