import fnmatch
import os
from collections import deque

from loguru import logger
from lxml import etree

import util
from nlp_util import unif_name, last_dot


def find_local_res(walk_dir):
    # RES_DIR_KEY = 'src\\main\\res'
    RES_DIR_KEY = os.path.join(*'src\\main\\res\\layout'.split("\\"))
    # use the system path separator
    logger.info(f"Find path end with {RES_DIR_KEY}")
    loc_res_dir = str()
    for r, d, files in os.walk(walk_dir):
        path = os.path.abspath(r)
        if os.path.isdir(path) and path.endswith(RES_DIR_KEY):
            loc_res_dir = path
            break
    result = loc_res_dir if loc_res_dir != "" else "NOTHING"
    logger.info(f"Found {result}")
    return result


def get_res_xml_list(loc_res_dir):
    """
    Args:
        loc_res_dir: "NOTHING" or a string of path

    Returns:

    """
    xml_list = list()
    if loc_res_dir == "NOTHING":
        logger.info(f"Found {len(xml_list)} xml files in {loc_res_dir}")
        return xml_list
    for r, d, files in os.walk(loc_res_dir):
        xml_files = fnmatch.filter(files, '*.xml')
        if len(xml_files) > 0:
            tmp_paths = [os.path.join(os.path.abspath(r), f) for f in xml_files]
            xml_list.extend(tmp_paths)
    logger.info(f"Found {len(xml_list)} xml files in {loc_res_dir}")
    return xml_list


def android_id(raw_id):
    return raw_id.split("/")[-1]


def bfs_xml(xml_path_list):
    """
    generate csv description file
    """
    data = []
    for xml_path in xml_path_list:
        tree = etree.parse(xml_path)
        queue = deque()
        queue.append(tree.getroot())
        file_name = util.drop_file_ext(xml_path)
        while len(queue) > 0:
            top = queue.popleft()
            for child in top:
                queue.append(child)
            for atr in top.attrib:
                if atr.endswith("id"):
                    data.append((file_name, top.tag, android_id(top.attrib[atr])))
                    # file_name, object_class_name, object_id
    return data


def get_ui_descript(repo_path):
    logger.info(f'Search descript in {repo_path}')
    loc_res_dir = find_local_res(repo_path)
    xml_list = get_res_xml_list(loc_res_dir)
    data = bfs_xml(xml_list)
    return data


def ui_descript_process(repo_path, ext_path="./tmp"):
    data = get_ui_descript(repo_path)

    save_file_path = os.path.join(ext_path, util.drop_file_ext(repo_path) + ".csv")
    util.dump_csv(save_file_path, data)
    return save_file_path


def ui_tokenize(data, stem=False):
    # file_name, object_class_name, object_id
    # account_setup, com.google.android.material.button.MaterialButton, centered_refresh_button
    rt = []
    for row in data:
        file_name, object_class_name, object_id = row
        file_name = unif_name(file_name, stem=stem)
        object_class_name = last_dot(object_class_name, stem=stem)
        object_id = unif_name(object_id, stem=stem)
        # process 1,3 column, leave 2 column original
        rt.append([file_name, object_class_name, object_id])
    # list of [list, str, list]
    return rt


if __name__ == '__main__':

    path = "./tmp"
    file_list = os.listdir(path)

    repo_list = list()
    for file in file_list:
        tmp_path = os.path.join(os.path.abspath(path), file)
        if os.path.isdir(tmp_path):
            repo_list.append(tmp_path)

    logger.debug(repo_list)

    for repo in repo_list:
        logger.debug(repo)
        # loc_res_dir = find_local_res(repo)
        # xml_list = get_res_xml_list(loc_res_dir)
        # bfs_xml(xml_list, os.path.join(work_path.get_tmp(), util.drop_file_ext(repo) + ".csv"))
        path = ui_descript_process(repo)
        logger.debug(path)
