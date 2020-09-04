from os.path import join, dirname, abspath, relpath
from os import makedirs

_project_root = abspath(join(dirname(__file__), "."))
EXTRACT_TMP = './tmp/'


def in_project(relative_path_to_project_root):
    return abspath(join(_project_root, relative_path_to_project_root))


def get_tmp():
    makedirs(EXTRACT_TMP, exist_ok=True)
    return in_project(EXTRACT_TMP)


def rela_path(path_a, path_b):
    return relpath(path_a, path_b)


if __name__ == '__main__':
    print(_project_root)
    print(get_tmp())
    print(in_project('model'))
