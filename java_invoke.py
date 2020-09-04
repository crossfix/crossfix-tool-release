import subprocess
import os
from loguru import logger
import shutil
import util
import json


#################################################
# Java version should up to 55 (Java 11)
#################################################

def sim(patch_dir, open_dir, clean=True):
    if not os.path.exists(patch_dir) or not os.path.exists(open_dir):
        raise FileNotFoundError(f"{patch_dir} or {open_dir} not exist")

    result_path = './tmp/_result'
    if clean and os.path.exists(result_path):
        shutil.rmtree(result_path)

    test_files = "./tmp/_sim"
    if clean and os.path.exists(test_files):
        shutil.rmtree(test_files)

    shutil.copytree(patch_dir, os.path.join(test_files, "patch"))
    shutil.copytree(open_dir, os.path.join(test_files, "open"))

    work_dir = os.path.dirname(__file__)
    logger.debug(f"Work at {os.path.abspath(work_dir)}")

    jar_path = 'lib/jplag-2.12.1-SNAPSHOT-jar-with-dependencies.jar'
    cmd = f"java -Dfile.encoding=utf-8 -jar {jar_path} -vp -m 100 -l java19 -r {result_path} -s {test_files}"
    logger.debug(cmd)

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, cwd=work_dir)
    try:
        outs, errs = proc.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        outs, errs = proc.communicate()

    outs = outs.decode()
    if outs != "" and not outs.isspace():
        logger.debug(f"Jplag-CLI-Out: {outs}")

    errs = errs.decode()
    if errs != "" and not errs.isspace():
        errs = errs.splitlines(keepends=True)
        errs = "".join(errs[:10])
        logger.error(f"Jplag-CLI-Err: {errs}")

    result = util.read_xsv(os.path.join(result_path, 'matches_max.csv'), ';')
    return result


def pom2json(pom_path, json_path, clean=True):
    if not os.path.exists(pom_path):
        raise FileNotFoundError(f"{pom_path} not exist")

    if clean and os.path.exists(json_path):
        os.remove(json_path)

    jar_path = 'lib/pom_convert-1.0-SNAPSHOT-jar-with-dependencies.jar'
    cmd = f"java -jar {jar_path} {pom_path} {json_path}"
    logger.debug(cmd)

    work_dir = os.path.dirname(os.path.abspath(__file__))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, cwd=work_dir)
    try:
        outs, errs = proc.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        outs, errs = proc.communicate()

    outs = outs.decode()
    if outs != "" and not outs.isspace():
        logger.debug(f"pom_convert-Out: {outs}")

    errs = errs.decode()
    if errs != "" and not errs.isspace():
        logger.error(f"pom_convert-Err: {errs}")

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            result = json.load(f)
        return result
    except Exception:
        logger.error(f"pom_convert output is broken.")
        return dict()


if __name__ == '__main__':
    util.init_logger(__file__)
    result = sim('testfiles/', 'testfiles/')
    result = sim('tmp/Jasig_CalendarPortlet_218edf8f6e55f41e1d6e54e9391affa390f83724', 'tmp/AAPS-Omnipod_AndroidAPS')
    print(result)

    # result = pom2json('pom_convert/pom.xml', 'pom_json.json')
    # print(result)
