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
import requests



def is_html(response: requests.Response) -> bool:
    return (
        "Content-Type" in response.headers
        and "text/html" in response.headers["Content-Type"]
    )



def is_safe_path(path: str) -> bool:
    """ Prevents directory traversal attacks """
    if path.startswith("/"):
        return False

    safe_path = os.path.expanduser("~")
    try:
        real = os.path.realpath(os.path.join(safe_path, path))
        return os.path.commonpath((real, safe_path)) == safe_path

    except ValueError:
        return False
