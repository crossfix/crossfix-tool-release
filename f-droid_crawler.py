# %%

import os
from github import Github
import re
from bs4 import BeautifulSoup
import util
from urllib.request import urlopen
prefix = "./f-droid/"
os.makedirs(prefix, exist_ok=True)

# %%
# download f-droid main database


all_link = "https://apt.izzysoft.de/fdroid/index.php/list/page/1?repo=main;doFilter=1;limit=0"

html = urlopen(all_link)

with open(prefix+"index.html", 'w', encoding='utf8') as f:
    f.write(html.read().decode(encoding='utf8'))


# %%

with open(prefix+"index.html", 'r', encoding='utf8') as f:
    html_body = f.read()

soup = BeautifulSoup(html_body, "html.parser")

# parse html
repo_link_list = []
ct = 1
for chi in soup.select(".approw"):
    tmp = []

    name = chi.select('.appdetailinner span.boldname')[0].text
    tmp.append(name)

    ver = ''
    for t in chi.select('.appdetailinner span.minor-details'):
        if "/" in t.text:
            # print(t.text)
            ver = t.text
            break
    tmp.append(ver)

    repo_link = ""
    for t in chi.select('.appdetailinner .paddedlink'):
        if t.text == 'Source':
            repo_link = t['href']
            # if 'https://github.com' not in repo_link:
            #     print(repo_link)
            #     repo_link = ""
            break
    repo_link = repo_link.strip()
    repo_link = repo_link.strip("/") # remove trailing "/" and space
    tmp.append(repo_link)
    repo_link_list.append(tmp)
    print(ct)
    ct += 1

util.dump_csv(prefix+"f-droid.csv", repo_link_list)

# %%

# extract version and release time
data = util.read_csv(prefix+"f-droid.csv")

new_data = []
for d in data:
    if d:
        ver_date = d[1]
        pattern = r'\/ (\d{4}-\d{2}-\d{2})'
        date = re.findall(pattern, ver_date)[0]
        ver = re.sub(pattern, '', ver_date).strip()
        tmp = [d[0], ver, date]
        tmp.extend(d[2:])
        while len(tmp) < 4:
            tmp.append("")
        new_data.append(tmp)

new_data.sort(reverse=True, key=lambda k: k[2])
util.dump_csv(prefix+"f-droid2.csv", new_data, encoding='utf-8-sig')

# %%

# add repo star info

from persontoken import MY_TOKEN
g = Github(MY_TOKEN)

data = util.read_csv(prefix+"f-droid2.csv", encoding='utf-8-sig')
github_repos = []
for row in data:
    url = row[-1]
    if "github" in url:
        try:
            repo_name = re.findall(r'https:\/\/github\.com\/(.*?\/[^\/]*)', url)
            print(url, repo_name)
            repo = g.get_repo(repo_name[0])
            row.append(repo.stargazers_count)
            github_repos.append(row)
        except Exception as e:
            print(e)

util.dump_csv(prefix+"f-droid-github.csv", github_repos, encoding='utf-8-sig')

# %%

# After filtering to get 2019, 300 stars repos

data = util.read_csv(prefix+'f-droid-github.csv', encoding='utf-8-sig')
new_data = list(filter(lambda x: int(x[-1]) > 300, data))
new_data = list(filter(lambda x: int(x[2].split("-")[0]) >= 2019, new_data))
new_data.sort(reverse=True, key=lambda k: k[2])
util.dump_csv(prefix+'f-droid-github-filter.csv', new_data, encoding='utf-8-sig')

# %%

# After filtering to get 2019, 300 stars repos

from persontoken import MY_TOKEN
g = Github(MY_TOKEN)

data = util.read_csv(prefix+'f-droid-github-filter.csv', encoding='utf-8-sig')
for row in data:
    # AnkiDroid Ⓝ,2.11.2,2020-06-15,https://github.com/ankidroid/Anki-Android,2663
    name, ver, d_time, url, star_ct = row
    repo_name = re.findall(r'https:\/\/github\.com\/(.*?\/[^\/]*)', url)
    repo = g.get_repo(repo_name[0])
    row.append(repo.stargazers_count)
