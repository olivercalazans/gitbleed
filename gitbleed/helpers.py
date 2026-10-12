# Copyright 2026 Oliver R. Calazans Jeronimo
# Modified from the original project git-dumper (Copyright (c) 2017 Maxime Arthaud)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import urllib.parse

import bs4
import dulwich.objects
import requests

from display import Display
from check   import is_safe_path, is_html



def normalize_url(url: str) -> str:    
    url = url.rstrip("/")
    if url.endswith("HEAD"):
        url = url[:-4]
    
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    
    return url.rstrip("/")



def get_indexed_files(response: requests.Response) -> list:
    html  = bs4.BeautifulSoup(response.text, "html.parser")
    files = []

    for link in html.find_all("a"):
        url = urllib.parse.urlparse(link.get("href"))

        if (
            url.path
            and is_safe_path(url.path)
            and not url.scheme
            and not url.netloc
        ):
            files.append(url.path)

    return files



def create_intermediate_dirs(path: str):
    dirname, basename = os.path.split(path)

    if dirname and not os.path.exists(dirname):
        try:
            os.makedirs(dirname)
        except FileExistsError:
            pass



def get_referenced_sha1(obj_file):
    """ Return all the referenced SHA1 in the given object file """
    objs = []

    if isinstance(obj_file, dulwich.objects.Commit):
        objs.append(obj_file.tree.decode())
        for parent in obj_file.parents:
            objs.append(parent.decode())

    elif isinstance(obj_file, dulwich.objects.Tree):
        for item in obj_file.iteritems():
            objs.append(item.sha.decode())

    elif isinstance(obj_file, dulwich.objects.Tag):
        objs.append(obj_file.object[1].decode())

    elif isinstance(obj_file, dulwich.objects.Blob):
        pass

    else:
        Display.warning(f"Unexpected object type: {obj_file}")

    return objs



def verify_response(response: requests.Response) -> tuple[bool, bool, str]:
    Display.response(response)

    if response.status_code >= 400:
        return False, False, None

    elif response.status_code >= 300 and "Location" in response.headers:
        return False, True, (
            f"Moved to {response.headers['Location']}. Code {response.status_code}"
        )

    elif (
        "Content-Length" in response.headers
        and response.headers["Content-Length"] == 0
    ):
        return False, True, "Responded with a zero-length body"

    elif is_html(response):
        return False, True, f"{response.url} responded with a HTML"

    else:
        return True, False, None



def write_file_atomic(path: str, content):
    mode = "wb" if isinstance(content, (bytes, bytearray)) else "w"
    tmp  = path + ".tmp"

    try:
        with open(tmp, mode) as f:
            f.write(content)
        
        os.replace(tmp, path)

    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise



def write_stream_atomic(path: str, chunks):
    tmp = path + ".tmp"

    try:
        with open(tmp, "wb") as f:
            for chunk in chunks:
                f.write(chunk)
    
        os.replace(tmp, path)
    
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise