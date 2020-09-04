from unittest import TestCase

from keywords import *


class Test(TestCase):
    def test_download_extract2(self):
        local_file_path = download_code('https://github.com/apache/druid', '.\./tmp/apache_druid.zip')
        ex_dir = extract('.\./tmp/apache_druid.zip', "./tmp")
        print(ex_dir)

    def test_download_extract(self):
        # download, extract source code
        local_file_path = download_code('https://github.com/nextcloud/android', 'nextcloud.zip')
        ex_dir = extract(local_file_path, "./tmp")

    def test_download_extract(self):
        # download a commit files
        local_file_path = download_code_file('boto/boto3', '73887e59661d', '/boto3/s3/inject.py',
                                             './tmp/inject_73887e5.py')

    def test_find_all_gradle(self):
        ex_dir = r"D:\A-work\extern-bugine\tmp140\AnySoftKeyboard_AnySoftKeyboard_master"
        # ex_dir = r"D:\A-work\extern-bugine\tmp140\PaulWoitaschek_Voice_master"
        paths = find_all_gradle(ex_dir)
        depens = []
        for p in paths:
            tmp = gradle_dependency(p)
            if tmp:
                depens.extend(gradle_dependency(p))
                logger.debug(p)
                logger.debug(tmp)
        logger.info(f"Dependency {len(depens)}======={depens}")
        name = 'AnySoftKeyboard_AnySoftKeyboard_master'
        depen_ob = Dependencies(name, depens)
        logger.debug(depen_ob)
        logger.debug(depen_ob.simple_dependencies())

    def test_gradle(self):
        text = """dependencies {
    api 'com.android.support:appcompat-v7:27.1.1'
    implementation 'com.android.support.test.espresso:espresso-core:3.0.2'
    implementation group: 'com.example.android', name: 'app-magic', version: '12.3'
    api group: 'com.example.android', name: 'app-magic', version: '12.3'
    
    implementation('com.example.android:app-magic:12.3')
    implementation(group = "org.springframework", name = "spring-core", version = "2.5")
}
"""
        path = "tmp/_test_build.gradle"
        with open(path, 'w', encoding='utf8') as f:
            print(text, file=f)
        depen = gradle_dependency(path)
        assert len(depen) == 6
        print(f"len: {len(depen)}, {depen}")
